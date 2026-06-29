"""Złoto — przebuduj gold_cell (prezentacja: fakt + adres w tabeli + etykiety).

Źródło: silver_fact (wartość/typ) + definicje tabel DPM:
  kod tabeli = 'K' || template_file[1:]   (subkod małą literą)
  tableversion (okno release) -> tableversioncell (po VariableVID) -> CellCode {tabela, rXXXX, cYYYY}
  headerversion: Code -> Label (Direction Y=wiersz, X=kolumna)
Tylko fakty Z komórką (INNER JOIN). Przebudowa od zera (idempotentne).
"""
import yaml
import psycopg2


def main():
    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))["database"]
    conn = psycopg2.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                            password=cfg["password"], dbname=cfg["dbname"])
    cur = conn.cursor()
    cur.execute("TRUNCATE gold_cell RESTART IDENTITY")

    # 1. fakt + kod tabeli + release (z silver, bo tam wartość/typ; template z brązu)
    cur.execute(r"""
        CREATE TEMP TABLE _f ON COMMIT DROP AS
        SELECT sf.id sfid, sf.report_id, sf.datapoint_code, sf.variable_vid,
               sf.data_type, sf.value_text, sf.value_num,
               ('K' || substr(bf.template_file, 2)) AS table_code,
               rel."ReleaseID" AS relid
        FROM silver_fact sf
        JOIN bronze_fact bf       ON bf.id = sf.bronze_fact_id
        JOIN bronze_report br     ON br.id = sf.report_id
        JOIN dpm2_ref.release rel ON rel."Code" = br.framework_version
    """)
    cur.execute('CREATE INDEX ON _f (variable_vid)')

    # 2. komórka (adres) + kody wiersza/kolumny
    cur.execute(r"""
        CREATE TEMP TABLE _c ON COMMIT DROP AS
        SELECT f.sfid,
               tv."TableVID" AS table_vid,
               (regexp_match(tvc."CellCode", ', r([0-9A-Za-z]+)'))[1] AS row_code,
               (regexp_match(tvc."CellCode", ', c([0-9A-Za-z]+)'))[1] AS col_code
        FROM _f f
        JOIN dpm2_ref.tableversion tv
               ON tv."Code" = f.table_code
              AND tv."StartReleaseID" <= f.relid
              AND (tv."EndReleaseID" IS NULL OR tv."EndReleaseID" > f.relid)
        JOIN dpm2_ref.tableversioncell tvc
               ON tvc."TableVID" = tv."TableVID"
              AND tvc."VariableVID" = f.variable_vid
    """)
    cur.execute('CREATE INDEX ON _c (sfid)')
    cur.execute('CREATE INDEX ON _c (table_vid)')

    # 3. INSERT gold_cell + etykiety (wiersz Y, kolumna X)
    cur.execute(r"""
        INSERT INTO gold_cell
          (report_id, table_code, datapoint_code, variable_vid, row_code, col_code,
           row_label, col_label, data_type, value_text, value_num)
        SELECT f.report_id, f.table_code, f.datapoint_code, f.variable_vid,
               c.row_code, c.col_code, rh."Label", ch."Label",
               f.data_type, f.value_text, f.value_num
        FROM _f f
        JOIN _c c ON c.sfid = f.sfid
        LEFT JOIN (SELECT tvh."TableVID", hv."Code", hv."Label"
                   FROM dpm2_ref.tableversionheader tvh
                   JOIN dpm2_ref.headerversion hv ON hv."HeaderVID" = tvh."HeaderVID"
                   JOIN dpm2_ref.header h ON h."HeaderID" = hv."HeaderID" AND h."Direction" = 'Y') rh
               ON rh."TableVID" = c.table_vid AND rh."Code" = c.row_code
        LEFT JOIN (SELECT tvh."TableVID", hv."Code", hv."Label"
                   FROM dpm2_ref.tableversionheader tvh
                   JOIN dpm2_ref.headerversion hv ON hv."HeaderVID" = tvh."HeaderVID"
                   JOIN dpm2_ref.header h ON h."HeaderID" = hv."HeaderID" AND h."Direction" = 'X') ch
               ON ch."TableVID" = c.table_vid AND ch."Code" = c.col_code
    """)
    n = cur.rowcount
    conn.commit()
    print(f"OK: gold_cell = {n}")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
