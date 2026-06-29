-- ============================================================
-- Migracja 001 — Brąz pod realny format xBRL-CSV (datapoint variant)
-- ============================================================
-- Uruchamiana na ŻYWEJ bazie (init.sql działa tylko na pustym wolumenie).
-- Usuwa stare tabele-atrapy (były pod XML-dummy), tworzy 3 tabele brązu.
-- dpm2_ref i master data (bank, okresy, moduły, szablony, reguły) NIETKNIĘTE.
-- ============================================================

-- --- 1. Usuń stare tabele-atrapy (dzieci najpierw) ---
DROP TABLE IF EXISTS disclosure_data_point CASCADE;   -- dummy: komórki XML
DROP TABLE IF EXISTS disclosure_table      CASCADE;   -- dummy: tabela na plik
DROP TABLE IF EXISTS validation_result     CASCADE;   -- pusta, FK do starego report; odbudujemy w srebrze
DROP TABLE IF EXISTS report                CASCADE;   -- dummy: raport XML

-- --- 2. bronze_report — jeden wiersz na wczytaną paczkę (.zip) ---
CREATE TABLE bronze_report (
    id                  SERIAL PRIMARY KEY,                  -- klucz techniczny (joiny)
    source_file         VARCHAR(300) NOT NULL UNIQUE,        -- nazwa pliku; UNIQUE = ten sam plik raz (idempotencja)
    lei                 VARCHAR(20),                         -- z entityID (parameters.csv)
    consolidation       VARCHAR(10),                         -- CON / IND
    country             VARCHAR(5),                          -- z nazwy pliku (DE, ES…)
    module              VARCHAR(20),                         -- CODIS, FINDIS… (z report.json)
    ref_period          DATE,                                -- refPeriod (parameters.csv)
    base_currency       VARCHAR(15),                         -- iso4217:EUR
    decimals_monetary   INTEGER,                             -- np. -3 = w tysiącach
    decimals_percentage INTEGER,
    decimals_integer    INTEGER,
    taxonomy            VARCHAR(200),                        -- pełny URL z report.json (extends)
    framework_version   VARCHAR(10),                         -- "4.2" wyłuskane z taxonomy -> dpm2_ref.release.Code
    report_generated    TIMESTAMP,                           -- timestamp z nazwy pliku = NUMER WERSJI
    business_key        VARCHAR(120),                        -- lei|consolidation|ref_period|module = tożsamość logiczna
    is_current          BOOLEAN DEFAULT TRUE,                -- TRUE = najnowsza wersja sprawozdania
    loaded_at           TIMESTAMP DEFAULT now()              -- ślad audytowy
);
CREATE INDEX idx_bronze_report_bkey ON bronze_report(business_key);
CREATE INDEX idx_bronze_report_lei  ON bronze_report(lei);

COMMENT ON TABLE bronze_report IS 'Brąz: manifest paczki xBRL-CSV. Wspólny kontekst raportu (waluta, okres, skala, wersja taksonomii) trzymany RAZ.';
COMMENT ON COLUMN bronze_report.business_key IS 'Grupuje wersje tego samego sprawozdania (resubmisje). Niezależny od timestampu.';
COMMENT ON COLUMN bronze_report.is_current IS 'Dokładnie jeden TRUE na business_key = najnowszy report_generated. Srebro/złoto czytają tylko TRUE.';

-- --- 3. bronze_filing_indicator — co bank zadeklarował (true/false per szablon) ---
CREATE TABLE bronze_filing_indicator (
    id          SERIAL PRIMARY KEY,
    report_id   INTEGER NOT NULL REFERENCES bronze_report(id) ON DELETE CASCADE,
    template_id VARCHAR(20) NOT NULL,                        -- K_61.00
    reported    BOOLEAN NOT NULL                             -- true/false
);
CREATE INDEX idx_bfi_report ON bronze_filing_indicator(report_id);

COMMENT ON TABLE bronze_filing_indicator IS 'Brąz: samodeklaracja banku które szablony złożył. Kontrola kompletności (srebro) krzyżuje z disclosure_requirement.';

-- --- 4. bronze_fact — surowe fakty (1 wiersz = 1 komórka z CSV) ---
CREATE TABLE bronze_fact (
    id             SERIAL PRIMARY KEY,
    report_id      INTEGER NOT NULL REFERENCES bronze_report(id) ON DELETE CASCADE,
    template_file  VARCHAR(20) NOT NULL,                     -- z nazwy pliku CSV: k_61.00
    datapoint_code VARCHAR(30) NOT NULL,                     -- dp134665 (= dp + VariableID)
    fact_value     TEXT NOT NULL                             -- RAW: liczba-jako-tekst LUB narracja; bez rzutowania
);
CREATE INDEX idx_bf_report ON bronze_fact(report_id);
CREATE INDEX idx_bf_dp     ON bronze_fact(datapoint_code);

COMMENT ON TABLE bronze_fact IS 'Brąz: surowe fakty as-is. fact_value jako TEXT (typowanie i rozszyfrowanie dp->metryka = srebro).';
