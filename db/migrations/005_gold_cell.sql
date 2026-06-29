-- ============================================================
-- Migracja 005 — Złoto: gold_cell (warstwa PREZENTACJI)
-- ============================================================
-- Fakt z adresem w tabeli + etykietami = gotowe pod wyświetlanie/render.
-- Tu mieszkają koordynaty (cell/row/col + etykiety) — świadomie poza srebrem.
-- Źródło: silver_fact (wartość/typ) + definicje tabel DPM (tableversioncell, headerversion).
-- Tylko fakty Z komórką (sieroty pominięte; są w silver_orphan_fact).
-- ============================================================

DROP TABLE IF EXISTS gold_cell;

CREATE TABLE gold_cell (
    id             SERIAL PRIMARY KEY,
    report_id      INTEGER NOT NULL REFERENCES bronze_report(id) ON DELETE CASCADE,
    table_code     VARCHAR(20) NOT NULL,        -- K_61.00
    datapoint_code VARCHAR(30),
    variable_vid   INTEGER,
    row_code       VARCHAR(20),                 -- 0010
    col_code       VARCHAR(20),                 -- 0010
    row_label      TEXT,                        -- "1. Common Equity Tier 1 (CET1) capital"
    col_label      TEXT,                        -- "a. T"
    data_type      VARCHAR(5),                  -- m/p/i/r/s/d/e (do formatowania)
    value_text     TEXT,
    value_num      NUMERIC
);
CREATE INDEX IF NOT EXISTS idx_gold_cell_rt ON gold_cell(report_id, table_code);

COMMENT ON TABLE gold_cell IS 'Złoto/prezentacja: fakt umiejscowiony w tabeli (wiersz/kolumna + etykiety), gotowy do renderu i dashboardu.';
