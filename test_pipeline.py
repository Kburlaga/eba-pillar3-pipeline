"""Testy integralności pipeline'u — sprawdzenie czy Fazy 0-2 działają poprawnie.

Testy:
1. Połączenie z bazą
2. DPM2 — 54 tabele, >5M wierszy
3. Seed data — banki, okresy, moduły, szablony, reguły walidacji
4. Bronze — raporty powiązane z tabelami i datapointami
5. Jakość danych — próbki faktycznych wartości
"""
import sys
import psycopg2
import yaml

PASS = 0
FAIL = 0
WARN = 0


def check(condition, msg):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {msg}")
    else:
        FAIL += 1
        print(f"  ❌ {msg}")


def warn(condition, msg):
    global WARN
    if not condition:
        WARN += 1
        print(f"  ⚠️  {msg}")


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


def test_connection(conn):
    print("\n" + "=" * 60)
    print("TEST 1: Połączenie z bazą danych")
    print("=" * 60)
    cur = conn.cursor()
    cur.execute("SELECT version()")
    ver = cur.fetchone()[0]
    check(True, f"Połączono z PostgreSQL: {ver[:50]}...")
    cur.close()


def test_dpm2(conn):
    print("\n" + "=" * 60)
    print("TEST 2: DPM2 — schemat referencyjny (dpm2_ref)")
    print("=" * 60)
    cur = conn.cursor()

    # Czy schemat istnieje
    cur.execute("SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name='dpm2_ref')")
    check(cur.fetchone()[0], "Schemat 'dpm2_ref' istnieje")

    # Liczba tabel
    cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='dpm2_ref'")
    table_count = cur.fetchone()[0]
    check(table_count == 54, f"54 tabele (jest: {table_count})")

    # Całkowita liczba wierszy
    total_rows = 0
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='dpm2_ref' ORDER BY table_name")
    tables = [r[0] for r in cur.fetchall()]
    for table in tables:
        cur.execute(f'SELECT COUNT(*) FROM dpm2_ref."{table}"')
        rows = cur.fetchone()[0]
        total_rows += rows
        if rows == 0:
            warn(False, f"Tabela {table}: 0 wierszy (pusta)")

    check(total_rows > 5_000_000, f"Łącznie >5M wierszy (jest: {total_rows:,})")

    # Kluczowe tabele
    key_tables = {
        "concept": 800_000,
        "contextcomposition": 1_700_000,
        "tableversioncell": 300_000,
        "variableversion": 250_000,
        "operandreference": 500_000,
    }
    for table, expected_min in key_tables.items():
        cur.execute(f'SELECT COUNT(*) FROM dpm2_ref."{table}"')
        rows = cur.fetchone()[0]
        check(rows > expected_min, f"{table}: {rows:,} wierszy (> {expected_min:,})")

    cur.close()


def test_seed_data(conn):
    print("\n" + "=" * 60)
    print("TEST 3: Seed data — dane referencyjne")
    print("=" * 60)
    cur = conn.cursor()

    # Banki
    cur.execute("SELECT COUNT(*) FROM bank")
    bank_count = cur.fetchone()[0]
    check(bank_count >= 8, f"Banki: {bank_count} (min 8)")

    cur.execute("SELECT lei, nazwa, kraj, kategoria FROM bank WHERE kraj = 'Polska' ORDER BY nazwa")
    pl_banks = cur.fetchall()
    check(len(pl_banks) == 5, f"Polskie banki: {len(pl_banks)} (oczekiwano 5)")
    for lei, nazwa, kraj, kat in pl_banks:
        print(f"     {nazwa} ({lei[:12]}...) — {kat}")

    # Okresy
    cur.execute("SELECT COUNT(*) FROM reporting_period")
    period_count = cur.fetchone()[0]
    check(period_count >= 5, f"Okresy raportowe: {period_count} (min 5)")

    cur.execute("SELECT okres, status FROM reporting_period ORDER BY okres")
    for okres, status in cur.fetchall():
        print(f"     {okres} — {status}")

    # Moduły EBA
    cur.execute("SELECT COUNT(*) FROM eba_module")
    module_count = cur.fetchone()[0]
    check(module_count == 8, f"Moduły EBA: {module_count} (oczekiwano 8)")

    # Szablony
    cur.execute("SELECT COUNT(*) FROM eba_template")
    template_count = cur.fetchone()[0]
    check(template_count == 192, f"Szablony EBA: {template_count} (oczekiwano 192)")

    # Reguły walidacji
    cur.execute("SELECT COUNT(*) FROM validation_rule")
    rule_count = cur.fetchone()[0]
    check(rule_count >= 8, f"Reguły walidacji: {rule_count} (min 8)")

    # Reguły z threshold_value
    cur.execute("SELECT nazwa, threshold_value, severity FROM validation_rule WHERE threshold_value IS NOT NULL ORDER BY id")
    rules_with_threshold = cur.fetchall()
    check(len(rules_with_threshold) >= 4, f"Reguły z progiem: {len(rules_with_threshold)} (min 4)")
    for nazwa, thresh, sev in rules_with_threshold:
        print(f"     {nazwa}: threshold={thresh}, severity={sev}")

    cur.close()


def test_bronze_data(conn):
    print("\n" + "=" * 60)
    print("TEST 4: Bronze — dane z XBRL")
    print("=" * 60)
    cur = conn.cursor()

    # Raporty
    cur.execute("SELECT COUNT(*) FROM report")
    report_count = cur.fetchone()[0]
    check(report_count == 12, f"Raporty: {report_count} (oczekiwano 12)")

    cur.execute("""
        SELECT r.id, b.nazwa, rp.okres, r.source_path, r.status
        FROM report r
        JOIN bank b ON r.bank_id = b.id
        JOIN reporting_period rp ON r.period_id = rp.id
        ORDER BY r.id
    """)
    reports = cur.fetchall()
    for rid, bank, okres, source, status in reports:
        short = source[:60] if source else "Brak"
        print(f"     report #{rid}: {bank} | {okres} | {short} | {status}")

    # Disclosure tables
    cur.execute("SELECT COUNT(*) FROM disclosure_table")
    table_count = cur.fetchone()[0]
    check(table_count == 12, f"Tabele disclosure: {table_count} (oczekiwano 12)")

    # Datapointy
    cur.execute("SELECT COUNT(*) FROM disclosure_data_point")
    dp_count = cur.fetchone()[0]
    check(dp_count == 12749, f"Datapointy: {dp_count:,} (oczekiwano 12,749)")

    # Powiązania: każdy report ma disclosure_table
    cur.execute("""
        SELECT COUNT(*) FROM report r
        LEFT JOIN disclosure_table dt ON dt.report_id = r.id
        WHERE dt.id IS NULL
    """)
    orphan_reports = cur.fetchone()[0]
    check(orphan_reports == 0, f"Raporty bez tabel: {orphan_reports} (0 = OK)")

    # Każda disclosure_table ma datapointy
    cur.execute("""
        SELECT COUNT(*) FROM disclosure_table dt
        LEFT JOIN disclosure_data_point dp ON dp.table_id = dt.id
        WHERE dp.id IS NULL
    """)
    orphan_tables = cur.fetchone()[0]
    warn(orphan_tables == 0, f"Tabele bez datapointów: {orphan_tables} (P3DH ma 0 faktów — to OK)")

    # Rozkład datapointów per moduł
    cur.execute("""
        SELECT em.code, COUNT(ddp.id) as cnt
        FROM disclosure_data_point ddp
        JOIN disclosure_table dt ON ddp.table_id = dt.id
        JOIN report r ON dt.report_id = r.id
        LEFT JOIN eba_template et ON dt.template_id = et.id
        LEFT JOIN eba_module em ON et.module_id = em.id
        GROUP BY em.code
        ORDER BY cnt DESC
    """)
    print("\n     Datapointy per moduł:")
    for code, cnt in cur.fetchall():
        print(f"       {code}: {cnt:,}")

    cur.close()


def test_data_quality(conn):
    print("\n" + "=" * 60)
    print("TEST 5: Jakość danych — próbki")
    print("=" * 60)
    cur = conn.cursor()

    # Próbka datapointów z CODIS (największy moduł: 5135 faktów)
    cur.execute("""
        SELECT ddp.row_code, ddp.wartosc, ddp.jednostka, ddp.column_code
        FROM disclosure_data_point ddp
        JOIN disclosure_table dt ON ddp.table_id = dt.id
        WHERE dt.nazwa_tabeli LIKE '%CODIS%'
        ORDER BY ddp.id
        LIMIT 10
    """)
    samples = cur.fetchall()
    check(len(samples) > 0, f"Próbka CODIS: {len(samples)} wierszy")
    print("     Pierwsze 10 datapointów z CODIS:")
    for row_code, wartosc, jednostka, col_code in samples:
        val_display = wartosc[:50] if wartosc else "NULL"
        unit_display = jednostka[:20] if jednostka else "-"
        print(f"       {row_code[:40]:40s} = {val_display:20s} [{unit_display}]")

    # Różnorodność jednostek
    cur.execute("SELECT DISTINCT jednostka, COUNT(*) FROM disclosure_data_point WHERE jednostka IS NOT NULL GROUP BY jednostka ORDER BY COUNT(*) DESC LIMIT 10")
    units = cur.fetchall()
    check(len(units) > 0, f"Różnych jednostek: {len(units)}")
    print("\n     Najczęstsze jednostki:")
    for unit, cnt in units:
        print(f"       {unit}: {cnt:,}")

    # NULL check
    cur.execute("SELECT COUNT(*) FROM disclosure_data_point WHERE wartosc IS NULL")
    null_values = cur.fetchone()[0]
    check(null_values == 0, f"NULL values: {null_values} (0 = OK)")

    # Wartości numeryczne vs nienumeryczne
    cur.execute("""
        SELECT COUNT(*) FROM disclosure_data_point
    WHERE wartosc ~ '^-?[0-9]+(\\.[0-9]+)?$'
    """)
    numeric = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM disclosure_data_point")
    total = cur.fetchone()[0]
    numeric_pct = round(numeric / total * 100, 1) if total > 0 else 0
    check(numeric > 0, f"Wartości numeryczne: {numeric:,} / {total:,} ({numeric_pct}%)")
    print(f"     Wartości nienumeryczne (tekstowe): {total - numeric:,}")

    cur.close()


def test_constraints(conn):
    print("\n" + "=" * 60)
    print("TEST 6: Integralność referencyjna")
    print("=" * 60)
    cur = conn.cursor()

    # FK: report -> bank
    cur.execute("""
        SELECT COUNT(*) FROM report r
        LEFT JOIN bank b ON r.bank_id = b.id
        WHERE b.id IS NULL
    """)
    check(cur.fetchone()[0] == 0, "FK report→bank: OK")

    # FK: report -> reporting_period
    cur.execute("""
        SELECT COUNT(*) FROM report r
        LEFT JOIN reporting_period rp ON r.period_id = rp.id
        WHERE rp.id IS NULL
    """)
    check(cur.fetchone()[0] == 0, "FK report→period: OK")

    # FK: disclosure_table -> report
    cur.execute("""
        SELECT COUNT(*) FROM disclosure_table dt
        LEFT JOIN report r ON dt.report_id = r.id
        WHERE r.id IS NULL
    """)
    check(cur.fetchone()[0] == 0, "FK table→report: OK")

    # FK: disclosure_data_point -> disclosure_table
    cur.execute("""
        SELECT COUNT(*) FROM disclosure_data_point ddp
        LEFT JOIN disclosure_table dt ON ddp.table_id = dt.id
        WHERE dt.id IS NULL
    """)
    check(cur.fetchone()[0] == 0, "FK datapoint→table: OK")

    # Unikalność bank.lei
    cur.execute("SELECT lei, COUNT(*) FROM bank GROUP BY lei HAVING COUNT(*) > 1")
    check(len(cur.fetchall()) == 0, "UNIQUE bank.lei: OK")

    # Unikalność report (bank_id, period_id, source_path)
    cur.execute("SELECT bank_id, period_id, source_path, COUNT(*) FROM report GROUP BY bank_id, period_id, source_path HAVING COUNT(*) > 1")
    check(len(cur.fetchall()) == 0, "UNIQUE report(bank,period,source): OK")

    cur.close()


def main():
    global PASS, FAIL, WARN
    cfg = load_config()

    try:
        conn = connect_db(cfg)
    except Exception as e:
        print(f"❌ Nie można połączyć z bazą: {e}")
        sys.exit(1)

    test_connection(conn)
    test_dpm2(conn)
    test_seed_data(conn)
    test_bronze_data(conn)
    test_data_quality(conn)
    test_constraints(conn)

    conn.close()

    print("\n" + "=" * 60)
    print(f"WYNIKI: ✅ {PASS} | ❌ {FAIL} | ⚠️ {WARN}")
    print("=" * 60)

    if FAIL > 0:
        print(f"\n❌ {FAIL} testów NIE PRZESZŁO — sprawdź powyżej.")
        sys.exit(1)
    else:
        print(f"\n✅ Wszystkie {PASS} testów przeszło pomyślnie! Pipeline działa poprawnie.")
        if WARN > 0:
            print(f"   ({WARN} ostrzeżeń — sprawdź powyżej.)")


if __name__ == "__main__":
    main()