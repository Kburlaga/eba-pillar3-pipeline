"""Faza 2 — Bronze: wczytanie plików XBRL do bazy danych (surowe, as-is).

Co ten skrypt robi (i czego uczy o data engineeringu):
1. Znajduje pliki XBRL w katalogu bronze/ — bez względu na nazwę
2. Parsuje XML (XBRL = XML z metadanymi finansowymi)
3. Ekstrahuje datapointy — każdy fakt liczbowy z kontekstem
4. Wpisuje surowe dane do tabel disclosure_table i disclosure_data_point
5. Rejestruje raport w tabeli report (powiązanie bank ↔ okres ↔ plik)

Zasada Bronze: dane wchodzą DOKŁADNIE tak jak w źródle. Żadnych transformacji.
"""
import os
import re
import glob
import xml.etree.ElementTree as ET
from datetime import datetime
import psycopg2
import psycopg2.extras
import yaml


def load_config():
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def connect_db(cfg):
    return psycopg2.connect(
        host=cfg["database"]["host"],
        port=cfg["database"]["port"],
        user=cfg["database"]["user"],
        password=cfg["database"]["password"],
        dbname=cfg["database"]["dbname"],
    )


def find_xbrl_files(bronze_dir: str) -> list:
    """Znajdź wszystkie pliki .xbrl w bronze (rekurencyjnie)."""
    return glob.glob(os.path.join(bronze_dir, "**", "*.xbrl"), recursive=True)


def parse_xbrl(filepath: str) -> dict:
    """Parsuj plik XBRL i zwróć surowe datapointy.

    XBRL to XML. Każdy fakt (liczba) jest w elemencie <fact> lub <ix:nonFraction>
    z atrybutami: name (co to za wskaźnik), contextRef (który bank/okres/jednostka),
    unitRef (w jakiej jednostce), decimals (precyzja).
    """
    tree = ET.parse(filepath)
    root = tree.getroot()

    # Przestrzenie nazw XBRL
    ns = {
        "xbrli": "http://www.xbrl.org/2003/instance",
        "xbrldi": "http://xbrl.org/2006/xbrldi",
        "link": "http://www.xbrl.org/2003/linkbase",
        "eba": "http://www.eba.europa.eu/xbrl/crr/dict/met",
    }

    # Szukamy faktów — różne tagi w zależności od wersji XBRL
    facts = []
    for elem in root.iter():
        # Fakt może być w dowolnym elemencie który ma atrybuty contextRef + unitRef
        ctx = elem.get("contextRef")
        unit = elem.get("unitRef")
        dec = elem.get("decimals")
        if ctx and unit and elem.text and elem.text.strip():
            name = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            facts.append(
                {
                    "name": name,
                    "value": elem.text.strip(),
                    "contextRef": ctx,
                    "unitRef": unit,
                    "decimals": dec,
                }
            )

    # Szukamy elementów nonFraction (inline XBRL)
    for elem in root.iter():
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag == "nonFraction":
            name = elem.get("name", "")
            ctx = elem.get("contextRef", "")
            unit = elem.get("unitRef", "")
            dec = elem.get("decimals", "")
            val = elem.text.strip() if elem.text else ""
            fmt = elem.get("format", "")
            if name and val:
                facts.append(
                    {
                        "name": name,
                        "value": val,
                        "contextRef": ctx,
                        "unitRef": unit,
                        "decimals": dec,
                        "format": fmt,
                    }
                )

    # Wyciągamy metadane z nazwy pliku
    filename = os.path.basename(filepath)
    lei_match = re.search(r"([A-Z0-9]{20})", filename)
    module_match = re.search(r"PILLAR3\d+_(\w+)_", filename)
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", filename)

    return {
        "filepath": filepath,
        "filename": filename,
        "lei": lei_match.group(1) if lei_match else "UNKNOWN",
        "module": module_match.group(1) if module_match else "UNKNOWN",
        "reporting_date": date_match.group(1) if date_match else None,
        "fact_count": len(facts),
        "facts": facts,
    }


def ingest_to_bronze(conn, parsed: dict) -> int:
    """Wpisz surowe dane do Bronze (tabele report, disclosure_table, disclosure_data_point).

    Zwraca report_id.
    """
    cur = conn.cursor()

    # 1. Znajdź lub utwórz bank (po LEI)
    cur.execute(
        "SELECT id FROM bank WHERE lei = %s",
        (parsed["lei"],),
    )
    bank_row = cur.fetchone()
    if not bank_row:
        # Dla DUMMYLEI tworzymy wpis tymczasowy
        cur.execute(
            "INSERT INTO bank (lei, nazwa, kraj, kategoria) VALUES (%s, %s, %s, %s) RETURNING id",
            (parsed["lei"], f"Test Bank {parsed['lei'][:8]}", "XX", "testowy"),
        )
        bank_id = cur.fetchone()[0]
    else:
        bank_id = bank_row[0]

    # 2. Znajdź lub utwórz okres raportowy
    if parsed["reporting_date"]:
        date_obj = datetime.strptime(parsed["reporting_date"], "%Y-%m-%d")
        year = date_obj.year
        month = date_obj.month
        if month <= 3:
            okres = f"{year}-Q1"
        elif month <= 6:
            okres = f"{year}-Q2"
        elif month <= 9:
            okres = f"{year}-Q3"
        else:
            okres = f"{year}-Q4"

        cur.execute(
            "SELECT id FROM reporting_period WHERE okres = %s",
            (okres,),
        )
        period_row = cur.fetchone()
        if not period_row:
            cur.execute(
                "INSERT INTO reporting_period (okres, data_od, data_do, status) VALUES (%s, %s, %s, %s) RETURNING id",
                (okres, f"{year}-01-01", parsed["reporting_date"], "testowy"),
            )
            period_id = cur.fetchone()[0]
        else:
            period_id = period_row[0]
    else:
        # Fallback
        cur.execute("SELECT id FROM reporting_period LIMIT 1")
        period_id = cur.fetchone()[0]

    # 3. Wpisz raport (jeden raport na plik XBRL)
    cur.execute(
        """INSERT INTO report (bank_id, period_id, data_publikacji, status, source_type, source_path)
           VALUES (%s, %s, %s, 'pobrany', 'XBRL', %s)
           RETURNING id""",
        (
            bank_id,
            period_id,
            parsed["reporting_date"],
            parsed["filename"],
        ),
    )
    report_id = cur.fetchone()[0]

    # 4. Wpisz tabelę (jeden plik XBRL = jeden szablon = jedna disclosure_table)
    template_code = None
    # Znajdź template dla tego modułu
    cur.execute(
        """SELECT et.id FROM eba_template et
           JOIN eba_module em ON et.module_id = em.id
           WHERE em.code = %s LIMIT 1""",
        (parsed["module"],),
    )
    template_row = cur.fetchone()
    if template_row:
        template_code = template_row[0]

    cur.execute(
        """INSERT INTO disclosure_table (report_id, template_id, nazwa_tabeli, liczba_wierszy, liczba_kolumn)
           VALUES (%s, %s, %s, %s, %s) RETURNING id""",
        (
            report_id,
            template_code,
            parsed["filename"],
            len(parsed["facts"]),
            1,
        ),
    )
    table_id = cur.fetchone()[0]

    # 5. Wpisz datapointy (każdy fakt)
    batch = []
    for fact in parsed["facts"]:
        batch.append(
            (
                table_id,
                fact.get("name", "")[:200],
                fact.get("contextRef", "")[:200],
                fact.get("value", "")[:500],
                fact.get("unitRef", "")[:50],
            )
        )

    psycopg2.extras.execute_batch(
        cur,
        """INSERT INTO disclosure_data_point (table_id, row_code, column_code, wartosc, jednostka)
           VALUES (%s, %s, %s, %s, %s)""",
        batch,
        page_size=1000,
    )

    conn.commit()
    cur.close()
    return report_id


def main():
    cfg = load_config()
    conn = connect_db(cfg)
    bronze_dir = cfg["paths"]["bronze"]

    files = find_xbrl_files(bronze_dir)
    print(f"=== Faza 2: Bronze Ingest ===\nZnaleziono {len(files)} plików XBRL\n")

    total_facts = 0
    for filepath in sorted(files):
        print(f"Parsowanie: {os.path.basename(filepath)}")
        parsed = parse_xbrl(filepath)
        print(f"  LEI: {parsed['lei']}, Moduł: {parsed['module']}, "
              f"Data: {parsed['reporting_date']}, Faktów: {parsed['fact_count']}")
        report_id = ingest_to_bronze(conn, parsed)
        total_facts += parsed["fact_count"]
        print(f"  → report_id={report_id}, zapisane w Bronze\n")

    print(f"=== Gotowe: {total_facts} datapointów w {len(files)} raportach ===")

    # Podsumowanie z bazy
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM disclosure_data_point")
    total_db = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM report")
    reports_db = cur.fetchone()[0]
    print(f"Baza: {reports_db} raportów, {total_db} datapointów")
    conn.close()


if __name__ == "__main__":
    main()