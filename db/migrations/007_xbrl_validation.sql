-- ============================================================
-- Migracja 007 — Walidacja XBRL (Arelle) — wyniki
-- ============================================================
-- Walidacja paczek xBRL-CSV względem taksonomii EBA (formuły) przez Arelle.
-- Dwie tabele: run (per raport: status + liczniki) + result (detal naruszeń asercji).
-- ============================================================

DROP TABLE IF EXISTS xbrl_validation_result;
DROP TABLE IF EXISTS xbrl_validation_run;

-- Jeden wiersz na uruchomienie walidacji raportu
CREATE TABLE xbrl_validation_run (
    id          SERIAL PRIMARY KEY,
    report_id   INTEGER NOT NULL REFERENCES bronze_report(id) ON DELETE CASCADE,
    status      VARCHAR(20) NOT NULL,        -- validated / skipped / error
    n_errors    INTEGER DEFAULT 0,
    n_warnings  INTEGER DEFAULT 0,
    engine      VARCHAR(30) DEFAULT 'arelle',
    note        TEXT,                        -- np. powód skip (brak taksonomii 4.2)
    ran_at      TIMESTAMP DEFAULT now(),
    UNIQUE(report_id)
);

-- Detal: pojedyncze naruszenie/komunikat asercji
CREATE TABLE xbrl_validation_result (
    id          SERIAL PRIMARY KEY,
    report_id   INTEGER NOT NULL REFERENCES bronze_report(id) ON DELETE CASCADE,
    rule_code   VARCHAR(80),                 -- id asercji / kod reguły EBA (np. v6478_m)
    severity    VARCHAR(20),                 -- ERROR / WARNING / INCONSISTENCY
    message     TEXT,
    checked_at  TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_xval_report ON xbrl_validation_result(report_id);

COMMENT ON TABLE xbrl_validation_run IS 'Walidacja XBRL (Arelle): status per raport. status=skipped gdy brak taksonomii dla wersji frameworku.';
COMMENT ON TABLE xbrl_validation_result IS 'Walidacja XBRL: naruszenia/komunikaty asercji formuł EBA per raport.';
