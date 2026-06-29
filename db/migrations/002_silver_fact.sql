-- ============================================================
-- Migracja 002 — Srebro-1: silver_fact (rozszyfrowanie + typowanie)
-- ============================================================
-- bronze_fact (surowy dp + tekst) -> silver_fact (znaczenie + liczba).
-- Rozszyfrowanie dp -> VariableVID per okno release'u (logika "aktu prawnego"),
-- typ danych przez property->datatype, wartość liczbowa przez TRIM+cast.
-- Tabela jest PRZEBUDOWYWANA od zera z brązu (loader: TRUNCATE + INSERT...SELECT).
-- ============================================================

DROP TABLE IF EXISTS silver_fact;                        -- silver = pochodne z brązu, można odbudować

CREATE TABLE silver_fact (
    id                SERIAL PRIMARY KEY,
    report_id         INTEGER NOT NULL REFERENCES bronze_report(id) ON DELETE CASCADE,
    bronze_fact_id    INTEGER NOT NULL,                  -- lineage: z którego wiersza brązu
    datapoint_code    VARCHAR(30) NOT NULL,              -- dp134665 (jak w brązie)
    variable_id       INTEGER,                           -- 134665 (po odcięciu "dp")
    variable_vid      INTEGER,                           -- wersja ważna dla release'u raportu
    is_metric         BOOLEAN,                           -- czy datapoint jest metryką
    data_type         VARCHAR(5),                        -- kod DPM: m/p/i/r/s/d/e
    data_type_name    VARCHAR(40),                       -- monetary/percentage/integer/decimal/string/date/enumeration
    value_text        TEXT,                              -- surowa wartość (kopia z brązu)
    value_num         NUMERIC,                           -- wartość liczbowa (NULL dla tekstu/daty/enum)
    table_code        VARCHAR(20),                       -- K_61.00 (szablon)
    cell_code         VARCHAR(60),                       -- {K_61.00, r0320, c0010}
    row_code          VARCHAR(20),                       -- 0320
    col_code          VARCHAR(20),                       -- 0010
    row_label         TEXT,                              -- "1. Common Equity Tier 1 (CET1) capital" (NULL dla wierszy otwartych)
    col_label         TEXT,                              -- "a. T"
    resolution_status VARCHAR(30) NOT NULL               -- resolved / unresolved
);
CREATE INDEX IF NOT EXISTS idx_silver_report ON silver_fact(report_id);
CREATE INDEX IF NOT EXISTS idx_silver_vvid   ON silver_fact(variable_vid);
CREATE INDEX IF NOT EXISTS idx_silver_dp     ON silver_fact(datapoint_code);

COMMENT ON TABLE silver_fact IS 'Srebro-1: fakt z nadanym znaczeniem. dp rozszyfrowany na VariableVID (per release), typ danych z DPM, wartość otypowana. Analiza: JOIN do bronze_report WHERE is_current.';
COMMENT ON COLUMN silver_fact.resolution_status IS 'resolved = znaleziono VariableVID; no_version_for_release = zmienna istnieje, brak wersji dla tego release; unknown_variable = brak VariableID w DPM (luka metadanych).';
