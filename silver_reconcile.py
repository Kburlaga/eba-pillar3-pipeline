"""Srebro DQ — rekoncyliacja strukturalna: czy każdy fakt ma miejsce (komórkę) w definicji szablonu.

Używa definicji tabel DPM (tableversion, tableversioncell) WYŁĄCZNIE do weryfikacji
integralności — nie do prezentacji. Wynik:
  - silver_reconciliation: podsumowanie per raport × szablon (total / mapped / orphan)
  - silver_orphan_fact:     detal faktów bez komórki

Mapowanie fakt→komórka (przetestowane wcześniej, 100% poza nielicznymi sierotami):
  kod tabeli = 'K' || template_file[1:]   (subkod małą literą, np. K_60.00.a)
  okno release na tableversion + dopasowanie VariableVID w tableversioncell
"""
import yaml
import psycopg2


def main():
    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))["database"]
    conn = psycopg2.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                            password=cfg["password"], dbname=cfg["dbname"])
    cur = conn.cursor()
    cur.execute("TRUNCATE silver_reconciliation, silver_orphan_fact RESTART IDENTITY")

    # 1. każdy fakt + jego kod tabeli + release; ma_komorke? (LEFT JOIN do definicji tabeli)
    cur.execute(r"""
        CREATE TEMP TABLE _chk ON COMMIT DROP AS
        SELECT sf.id            AS silver_fact_id,
               sf.report_id,
               sf.datapoint_code,
               sf.metric_name,
               sf.variable_vid,
               ('K' || substr(bf.template_file, 2)) AS table_code,
               rel."ReleaseID"  AS relid
        FROM silver_fact sf
        JOIN bronze_fact bf       ON bf.id = sf.bronze_fact_id
        JOIN bronze_report br     ON br.id = sf.report_id
        JOIN dpm2_ref.release rel ON rel."Code" = br.framework_version
    """)
    cur.execute('CREATE INDEX ON _chk (variable_vid)')

    # 2. które fakty mają komórkę (okno release tabeli + dopasowanie kodu tabeli + VariableVID)
    cur.execute(r"""
        CREATE TEMP TABLE _hascell ON COMMIT DROP AS
        SELECT DISTINCT c.silver_fact_id
        FROM _chk c
        JOIN dpm2_ref.tableversion tv
               ON tv."Code" = c.table_code
              AND tv."StartReleaseID" <= c.relid
              AND (tv."EndReleaseID" IS NULL OR tv."EndReleaseID" > c.relid)
        JOIN dpm2_ref.tableversioncell tvc
               ON tvc."TableVID" = tv."TableVID"
              AND tvc."VariableVID" = c.variable_vid
    """)
    cur.execute('CREATE INDEX ON _hascell (silver_fact_id)')

    # 3. podsumowanie per raport × szablon
    cur.execute(r"""
        INSERT INTO silver_reconciliation (report_id, table_code, facts_total, facts_mapped, facts_orphan)
        SELECT c.report_id, c.table_code,
               COUNT(*) AS facts_total,
               COUNT(h.silver_fact_id) AS facts_mapped,
               COUNT(*) - COUNT(h.silver_fact_id) AS facts_orphan
        FROM _chk c
        LEFT JOIN _hascell h ON h.silver_fact_id = c.silver_fact_id
        GROUP BY c.report_id, c.table_code
    """)

    # 4. detal sierot
    cur.execute(r"""
        INSERT INTO silver_orphan_fact (report_id, silver_fact_id, datapoint_code, table_code, metric_name)
        SELECT c.report_id, c.silver_fact_id, c.datapoint_code, c.table_code, c.metric_name
        FROM _chk c
        LEFT JOIN _hascell h ON h.silver_fact_id = c.silver_fact_id
        WHERE h.silver_fact_id IS NULL
    """)

    conn.commit()

    cur.execute("SELECT SUM(facts_total), SUM(facts_mapped), SUM(facts_orphan) FROM silver_reconciliation")
    tot, mp, orph = cur.fetchone()
    print(f"OK rekoncyliacja: faktów={tot}, z komórką={mp}, sierot={orph}")
    cur.execute("SELECT report_id, datapoint_code, table_code, LEFT(metric_name,40) FROM silver_orphan_fact ORDER BY report_id")
    rows = cur.fetchall()
    if rows:
        print("Sieroty (fakt bez komórki):")
        for r in rows:
            print(f"   report {r[0]}: {r[1]} w {r[2]} | {r[3]}")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
