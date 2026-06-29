"""Faza 2 — Brąz: wczytanie paczek xBRL-CSV ze strefy lądowania do bazy (as-is).

Czego uczy:
- strefa lądowania (landing) + idempotencja (ten sam plik nie wchodzi dwa razy)
- czytanie paczki .zip w pamięci (bez rozpakowywania na dysk)
- rozdział: kontekst raportu (1 wiersz) vs deklaracje vs fakty (3 tabele)
- wersjonowanie instancji (resubmisja) przez business_key + is_current

Zasada brązu: dane wchodzą DOKŁADNIE jak w źródle. Wartości jako TEKST, bez rzutowania.
"""
import os
import re
import csv
import io
import json
import glob
import zipfile
from datetime import datetime

import yaml
import psycopg2
import psycopg2.extras


def load_config():
    with open("config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def connect_db(cfg):
    d = cfg["database"]
    return psycopg2.connect(host=d["host"], port=d["port"], user=d["user"],
                            password=d["password"], dbname=d["dbname"])


# ── pomocnicze: czytanie plików z wnętrza zipa ───────────────────────────────
def _read_csv(zf: zipfile.ZipFile, name: str) -> list[dict]:
    """Wczytaj CSV z paczki jako listę słowników (klucz = nagłówek kolumny)."""
    raw = zf.read(name).decode("utf-8-sig")           # utf-8-sig usuwa BOM jeśli jest
    return list(csv.DictReader(io.StringIO(raw)))


def _find(names: list[str], suffix: str) -> str | None:
    """Znajdź w paczce ścieżkę kończącą się na dany fragment (np. '/parameters.csv')."""
    for n in names:
        if n.endswith(suffix):
            return n
    return None


# ── parsowanie jednej paczki ─────────────────────────────────────────────────
def parse_package(zip_path: str) -> dict:
    fname = os.path.basename(zip_path)
    stem = fname[:-4] if fname.lower().endswith(".zip") else fname   # bez .zip

    # 1. Metadane z NAZWY pliku (timestamp generacji jest tylko tutaj)
    #    wzór: LEI.CONS_COUNTRY_MODULEVER_MODULE_PERIOD_GENTS
    m = re.search(r"\.([A-Z]+)_([A-Z]{2})_[A-Z0-9]+_([A-Z0-9]+)_(\d{4}-\d{2}-\d{2})_(\d{17})", stem)
    consolidation = m.group(1) if m else None
    country       = m.group(2) if m else None
    module_fn     = m.group(3) if m else None
    gents         = m.group(5) if m else None
    report_generated = datetime.strptime(gents, "%Y%m%d%H%M%S%f") if gents else None

    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()

        # 2. report.json → wersja frameworku + moduł (autorytatywne)
        rj_name = _find(names, "/reports/report.json")
        framework_version, module, taxonomy = None, module_fn, None
        if rj_name:
            rj = json.loads(zf.read(rj_name).decode("utf-8-sig"))
            ext = rj.get("documentInfo", {}).get("extends", [])
            if ext:
                taxonomy = ext[0]
                mm = re.search(r"/pillar3/(\d+\.\d+)/mod/(\w+)\.json", taxonomy)
                if mm:
                    framework_version = mm.group(1)
                    module = mm.group(2).upper()

        # 3. parameters.csv → kontekst raportu (waluta, okres, skala, entityID)
        params = {}
        pn = _find(names, "/parameters.csv")
        if pn:
            for row in _read_csv(zf, pn):
                params[row["name"]] = row["value"]
        entity = params.get("entityID", "")             # "rs:7LTW...CON"
        ent_clean = entity.split(":", 1)[-1]            # "7LTW...CON"
        lei = ent_clean.split(".")[0] if "." in ent_clean else ent_clean

        def _int(x):
            try: return int(x)
            except (TypeError, ValueError): return None

        # 4. FilingIndicators.csv → deklaracje true/false
        indicators = []
        fin = _find(names, "/FilingIndicators.csv")
        if fin:
            for row in _read_csv(zf, fin):
                indicators.append((row["templateID"], row["reported"].strip().lower() == "true"))

        # 5. wszystkie k_*.csv → fakty (datapoint, factValue)
        facts = []
        for n in names:
            base = os.path.basename(n)
            if base.lower().startswith("k_") and base.lower().endswith(".csv"):
                template_file = base[:-4]               # "k_61.00"
                for row in _read_csv(zf, n):
                    dp = row.get("datapoint")
                    val = row.get("factValue")
                    if dp is not None and val is not None:
                        facts.append((template_file, dp, val))

    ref_period = params.get("refPeriod")
    business_key = f"{lei}|{consolidation}|{ref_period}|{module}"

    return {
        "source_file": fname, "lei": lei, "consolidation": consolidation,
        "country": country, "module": module, "ref_period": ref_period,
        "base_currency": params.get("baseCurrency"),
        "decimals_monetary": _int(params.get("decimalsMonetary")),
        "decimals_percentage": _int(params.get("decimalsPercentage")),
        "decimals_integer": _int(params.get("decimalsInteger")),
        "taxonomy": taxonomy, "framework_version": framework_version,
        "report_generated": report_generated, "business_key": business_key,
        "indicators": indicators, "facts": facts,
    }


# ── zapis do bazy ────────────────────────────────────────────────────────────
def ingest(conn, p: dict):
    cur = conn.cursor()
    # 1. manifest raportu
    cur.execute("""
        INSERT INTO bronze_report
          (source_file, lei, consolidation, country, module, ref_period,
           base_currency, decimals_monetary, decimals_percentage, decimals_integer,
           taxonomy, framework_version, report_generated, business_key)
        VALUES (%(source_file)s,%(lei)s,%(consolidation)s,%(country)s,%(module)s,%(ref_period)s,
                %(base_currency)s,%(decimals_monetary)s,%(decimals_percentage)s,%(decimals_integer)s,
                %(taxonomy)s,%(framework_version)s,%(report_generated)s,%(business_key)s)
        RETURNING id""", p)
    report_id = cur.fetchone()[0]

    # 2. deklaracje
    psycopg2.extras.execute_batch(cur,
        "INSERT INTO bronze_filing_indicator (report_id, template_id, reported) VALUES (%s,%s,%s)",
        [(report_id, t, r) for t, r in p["indicators"]], page_size=500)

    # 3. fakty
    psycopg2.extras.execute_batch(cur,
        "INSERT INTO bronze_fact (report_id, template_file, datapoint_code, fact_value) VALUES (%s,%s,%s,%s)",
        [(report_id, tf, dp, val) for tf, dp, val in p["facts"]], page_size=1000)

    # 4. przelicz version_no + is_current dla całej grupy (per business_key, wg daty przekazania)
    #    v1 = najstarsza, najwyższy numer = najnowsza = is_current=TRUE
    cur.execute("""
        WITH v AS (
            SELECT id,
                   ROW_NUMBER() OVER (PARTITION BY business_key ORDER BY report_generated) AS vno,
                   (report_generated = MAX(report_generated) OVER (PARTITION BY business_key)) AS cur
            FROM bronze_report WHERE business_key = %s
        )
        UPDATE bronze_report b
        SET version_no = v.vno, is_current = v.cur
        FROM v WHERE b.id = v.id""", (p["business_key"],))

    conn.commit()                                       # commit per plik
    cur.close()
    return report_id, len(p["indicators"]), len(p["facts"])


def loaded_files(conn) -> set:
    cur = conn.cursor()
    cur.execute("SELECT source_file FROM bronze_report")
    s = {r[0] for r in cur.fetchall()}
    cur.close()
    return s


def main():
    cfg = load_config()
    conn = connect_db(cfg)
    landing = os.path.join(cfg["paths"]["bronze"], "landing")

    already = loaded_files(conn)
    zips = sorted(glob.glob(os.path.join(landing, "*.zip")))
    print(f"=== Brąz: ingest xBRL-CSV ===\nW landing: {len(zips)} paczek, w bazie już: {len(already)}\n")

    new = skipped = 0
    for zp in zips:
        fname = os.path.basename(zp)
        if fname in already:
            print(f"POMIJAM (już w bazie): {fname}")
            skipped += 1
            continue
        try:
            p = parse_package(zp)
            rid, n_ind, n_fact = ingest(conn, p)
            print(f"WCZYTANO: {fname}\n  LEI={p['lei']} okres={p['ref_period']} fw={p['framework_version']} "
                  f"-> report_id={rid}, deklaracji={n_ind}, faktów={n_fact}")
            new += 1
        except Exception as e:
            conn.rollback()
            print(f"BŁĄD przy {fname}: {e}  (pominięto, reszta leci dalej)")

    print(f"\n=== Gotowe: nowych {new}, pominiętych {skipped} ===")
    conn.close()


if __name__ == "__main__":
    main()
