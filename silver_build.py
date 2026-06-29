"""Srebro — przebuduj warstwę znaczeniową z brązu (metryka + wymiary).

Znaczenie faktu = metryka (co) + wymiary (w jakim przekroju). NIE koordynaty tabeli
(adres komórki/etykiety = prezentacja -> złoto), bo ten sam VariableVID bywa w wielu komórkach.

Łańcuch (każda warstwa przetestowana osobno na realnych danych, 100% pokrycia):
  bronze_fact
    -> VariableID (odetnij 'dp')
    -> VariableVID  (okno release'u raportu: Start <= R < End)            [logika "aktu prawnego"]
    -> property -> datatype  (typ: monetary/percentage/integer/decimal/string/date/enum)
    -> item (po VariableVID.PropertyID)  = nazwa METRYKI
    -> value_num  (btrim + cast; NULL dla tekstu/daty/enum)
    -> contextcomposition (po VariableVID.ContextID) = wymiary:
         PropertyID -> item = nazwa WYMIARU,  ItemID -> item = nazwa CZŁONKA

Strategia: PRZEBUDOWA od zera (TRUNCATE + odtworzenie). Idempotentne.
"""
import yaml
import psycopg2


def main():
    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))["database"]
    conn = psycopg2.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                            password=cfg["password"], dbname=cfg["dbname"])
    cur = conn.cursor()

    # 0. czyść (dziecko najpierw przez CASCADE)
    cur.execute("TRUNCATE silver_fact, silver_fact_dimension RESTART IDENTITY")

    # 1. RESOLVED: fakt + VariableVID (okno release) + metryka + typ + wartość + context_id
    cur.execute(r"""
        CREATE TEMP TABLE _resolved ON COMMIT DROP AS
        SELECT bf.id            AS bronze_fact_id,
               bf.report_id,
               bf.datapoint_code,
               bf.fact_value,
               CAST(REPLACE(bf.datapoint_code, 'dp', '') AS INTEGER) AS variable_id,
               vv."VariableVID" AS variable_vid,
               vv."PropertyID"  AS metric_property_id,
               btrim(mit."Name") AS metric_name,
               vv."ContextID"   AS context_id,
               (p."IsMetric" <> 0) AS is_metric,
               dt."Code"        AS data_type,
               dt."Name"        AS data_type_name
        FROM bronze_fact bf
        JOIN bronze_report br        ON bf.report_id = br.id
        JOIN dpm2_ref.release rel    ON rel."Code" = br.framework_version
        LEFT JOIN dpm2_ref.variableversion vv
               ON vv."VariableID" = CAST(REPLACE(bf.datapoint_code, 'dp', '') AS INTEGER)
              AND vv."StartReleaseID" <= rel."ReleaseID"
              AND (vv."EndReleaseID" IS NULL OR vv."EndReleaseID" > rel."ReleaseID")
        LEFT JOIN dpm2_ref.property p  ON p."PropertyID" = vv."PropertyID"
        LEFT JOIN dpm2_ref.datatype dt ON dt."DataTypeID" = p."DataTypeID"
        LEFT JOIN dpm2_ref.item mit    ON mit."ItemID" = vv."PropertyID"   -- nazwa metryki
    """)
    cur.execute('CREATE INDEX ON _resolved (bronze_fact_id)')
    cur.execute('CREATE INDEX ON _resolved (context_id)')

    # 2. silver_fact (1 wiersz / fakt); dim_count z contextcomposition
    cur.execute(r"""
        INSERT INTO silver_fact
          (report_id, bronze_fact_id, datapoint_code, variable_id, variable_vid,
           metric_property_id, metric_name, is_metric, data_type, data_type_name,
           value_text, value_num, context_id, dim_count, resolution_status)
        SELECT
           r.report_id, r.bronze_fact_id, r.datapoint_code, r.variable_id, r.variable_vid,
           r.metric_property_id, r.metric_name, r.is_metric, r.data_type, r.data_type_name,
           r.fact_value,
           CASE WHEN btrim(r.fact_value) ~ '^-?[0-9]+(\.[0-9]+)?$'
                THEN btrim(r.fact_value)::numeric END,
           r.context_id,
           COALESCE((SELECT COUNT(*) FROM dpm2_ref.contextcomposition cc
                     WHERE cc."ContextID" = r.context_id), 0),
           CASE WHEN r.variable_vid IS NULL THEN 'unresolved' ELSE 'resolved' END
        FROM _resolved r
    """)
    n_fact = cur.rowcount

    # 3. silver_fact_dimension (N wierszy / fakt): rozłóż context na wymiar=członek z nazwami
    cur.execute(r"""
        INSERT INTO silver_fact_dimension
          (silver_fact_id, report_id, dimension_property_id, dimension_name, member_item_id, member_name)
        SELECT sf.id, sf.report_id,
               cc."PropertyID", btrim(dim."Name"),
               cc."ItemID",     btrim(mem."Name")
        FROM silver_fact sf
        JOIN dpm2_ref.contextcomposition cc ON cc."ContextID" = sf.context_id
        LEFT JOIN dpm2_ref.item dim ON dim."ItemID" = cc."PropertyID"   -- nazwa wymiaru
        LEFT JOIN dpm2_ref.item mem ON mem."ItemID" = cc."ItemID"       -- nazwa członka
        WHERE sf.context_id IS NOT NULL
    """)
    n_dim = cur.rowcount

    conn.commit()
    print(f"OK: silver_fact={n_fact}, silver_fact_dimension={n_dim}")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
