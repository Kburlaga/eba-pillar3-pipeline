-- ============================================================
-- Migracja 008 — Krzyżowa kontrola srebra vs Arelle
-- ============================================================
-- Niezależna weryfikacja: nasze srebro (dp→metryka+wymiary z DPM) vs fakty
-- wyekstrahowane przez Arelle z taksonomii (xBRL-JSON / saveLoadableOIM).
-- Porównujemy: liczbę faktów, multizbiór wartości numerycznych, liczbę wymiarów.
-- ============================================================

DROP TABLE IF EXISTS silver_crosscheck;

CREATE TABLE silver_crosscheck (
    id              SERIAL PRIMARY KEY,
    report_id       INTEGER NOT NULL REFERENCES bronze_report(id) ON DELETE CASCADE,
    arelle_facts    INTEGER,        -- faktów danych wg Arelle
    silver_facts    INTEGER,        -- silver_fact
    values_matched  INTEGER,        -- zgodnych wartości (multizbiór)
    only_arelle     INTEGER,        -- wartości tylko u Arelle
    only_silver     INTEGER,        -- wartości tylko w srebrze
    arelle_dims     INTEGER,        -- wymiarów (par) wg Arelle
    silver_dims     INTEGER,        -- silver_fact_dimension
    status          VARCHAR(20) NOT NULL,   -- match / mismatch / error
    note            TEXT,
    checked_at      TIMESTAMP DEFAULT now(),
    UNIQUE(report_id)
);
CREATE INDEX IF NOT EXISTS idx_xcheck_report ON silver_crosscheck(report_id);

COMMENT ON TABLE silver_crosscheck IS 'Krzyżowa kontrola: srebro (DPM) vs ekstrakcja Arelle (taksonomia). status=match gdy liczby+wartości+wymiary się zgadzają.';
