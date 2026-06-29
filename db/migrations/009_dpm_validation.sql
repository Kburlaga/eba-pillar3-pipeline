-- ============================================================
-- Migracja 009 — Etap B: walidacja regułami DPM (rules-as-data)
-- ============================================================
-- Reguły EBA z DPM (operationversion.Expression) przepisane na ewaluator,
-- uruchomione na gold_cell. Druga droga do tych samych reguł co Arelle (taksonomia).
-- Zakres: klasa LINIOWA wewnątrz-tabelowa ({rA}={rB}+{rC}, {set}>=0, >=, <=).
-- ============================================================

DROP TABLE IF EXISTS dpm_validation_result;
DROP TABLE IF EXISTS dpm_validation_run;

CREATE TABLE dpm_validation_run (
    id              SERIAL PRIMARY KEY,
    report_id       INTEGER NOT NULL REFERENCES bronze_report(id) ON DELETE CASCADE,
    rules_evaluated INTEGER NOT NULL,
    n_passed        INTEGER NOT NULL,
    n_failed        INTEGER NOT NULL,
    n_skipped       INTEGER NOT NULL,        -- brak danych operandu (default:null)
    status          VARCHAR(20) NOT NULL,    -- all_pass / failures
    ran_at          TIMESTAMP DEFAULT now(),
    UNIQUE(report_id)
);

CREATE TABLE dpm_validation_result (    -- tylko NARUSZENIA
    id            SERIAL PRIMARY KEY,
    report_id     INTEGER NOT NULL REFERENCES bronze_report(id) ON DELETE CASCADE,
    operation_vid INTEGER,
    table_code    VARCHAR(20),
    col_code      VARCHAR(20),
    op            VARCHAR(4),
    lhs_val       NUMERIC,
    rhs_val       NUMERIC,
    expression    TEXT,
    checked_at    TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_dpmval_report ON dpm_validation_result(report_id);

COMMENT ON TABLE dpm_validation_run IS 'Etap B: walidacja regułami DPM (operationversion) na gold_cell — podsumowanie per raport. Druga droga vs Arelle.';
COMMENT ON TABLE dpm_validation_result IS 'Etap B: naruszenia reguł liniowych DPM (LHS vs RHS poza tolerancją).';
