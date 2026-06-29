-- ============================================================
-- EBA Pillar 3 Pipeline — schemat bazy danych v2
-- Oparty na EBA Framework 4.1 / DPM 2.0 (Release 4.2, 2025-11-25)
-- ============================================================
-- 
-- Źródła danych referencyjnych:
--   - DPM2 Database v4.2 (Access .accdb)
--   - Annotated Table Layout XLSX (EBA Framework 4.1)
--   - 8 modułów Pillar 3 Disclosure: CODIS, FINDIS, REMDIS, ESGDIS,
--     GSIIDIS, MRELTLACDIS, IRRBBDIS, P3DH
--   - 192 szablonów raportowych

-- ============================================================
-- 1. MASTER DATA — słowniki referencyjne
-- ============================================================

-- Spis banków raportujących w ramach Filaru III
CREATE TABLE IF NOT EXISTS bank (
    id              SERIAL PRIMARY KEY,
    lei             VARCHAR(20) UNIQUE NOT NULL,
    nazwa           VARCHAR(200) NOT NULL,
    kraj            VARCHAR(100) NOT NULL,
    kategoria       VARCHAR(20) NOT NULL,
    url_disclosures VARCHAR(500),
    aktywny         BOOLEAN DEFAULT TRUE,
    data_dodania    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE bank IS 'Spis banków raportujących w ramach Filaru III. LEI (Legal Entity Identifier) to unikalny identyfikator w UE.';
COMMENT ON COLUMN bank.kategoria IS 'G-SII, O-SII, duży, mały — różne kategorie = różne wymagania raportowe';

-- Okresy raportowe
CREATE TABLE IF NOT EXISTS reporting_period (
    id      SERIAL PRIMARY KEY,
    okres   VARCHAR(7) UNIQUE NOT NULL,
    data_od DATE NOT NULL,
    data_do DATE NOT NULL,
    status  VARCHAR(20) DEFAULT 'oczekiwany'
);

COMMENT ON TABLE reporting_period IS 'Okresy raportowe — banki publikują dane kwartalnie (Pillar 3)';

-- Moduły taksonomii EBA (grupy szablonów)
CREATE TABLE IF NOT EXISTS eba_module (
    id      SERIAL PRIMARY KEY,
    code    VARCHAR(20) UNIQUE NOT NULL,
    nazwa   VARCHAR(200) NOT NULL,
    opis    TEXT
);

COMMENT ON TABLE eba_module IS 'Moduły taksonomii EBA — grupy szablonów zgrupowane tematycznie (odpowiada ModuleVersion.Code w DPM2)';

-- Szablony EBA (template)
CREATE TABLE IF NOT EXISTS eba_template (
    id              SERIAL PRIMARY KEY,
    template_code   VARCHAR(20) UNIQUE NOT NULL,
    nazwa           VARCHAR(300) NOT NULL,
    module_id       INTEGER REFERENCES eba_module(id),
    wersja_taksonomii VARCHAR(20) DEFAULT 'v4.1',
    kategoria_banku VARCHAR(20),
    opis            TEXT
);

COMMENT ON TABLE eba_template IS 'Taksonomia EBA — lista szablonów Pillar 3 (192 kody z Framework 4.1).';

-- ============================================================
-- 2. BRONZE — surowe dane (xBRL-CSV, datapoint variant)
-- Patrz też: db/migrations/001_bronze_csv.sql (zmiana na żywej bazie)
-- ============================================================

-- Manifest paczki .zip (jeden wiersz na wczytane sprawozdanie)
CREATE TABLE IF NOT EXISTS bronze_report (
    id                  SERIAL PRIMARY KEY,
    source_file         VARCHAR(300) NOT NULL UNIQUE,        -- ten sam plik raz (idempotencja)
    lei                 VARCHAR(20),
    consolidation       VARCHAR(10),                         -- CON / IND
    country             VARCHAR(5),
    module              VARCHAR(20),                         -- CODIS, FINDIS…
    ref_period          DATE,
    base_currency       VARCHAR(15),
    decimals_monetary   INTEGER,
    decimals_percentage INTEGER,
    decimals_integer    INTEGER,
    taxonomy            VARCHAR(200),                        -- z report.json (extends)
    framework_version   VARCHAR(10),                         -- "4.2" -> dpm2_ref.release.Code
    report_generated    TIMESTAMP,                           -- timestamp z nazwy = NUMER WERSJI
    business_key        VARCHAR(120),                        -- lei|consolidation|ref_period|module
    version_no          INTEGER,                             -- numer wersji w grupie (v1=najstarsza)
    is_current          BOOLEAN DEFAULT TRUE,                -- najnowsza wersja sprawozdania
    loaded_at           TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_bronze_report_bkey ON bronze_report(business_key);
CREATE INDEX IF NOT EXISTS idx_bronze_report_lei  ON bronze_report(lei);

COMMENT ON TABLE bronze_report IS 'Brąz: manifest paczki xBRL-CSV. Wspólny kontekst raportu trzymany RAZ; business_key+is_current = wersjonowanie resubmisji.';

-- Deklaracje banku: które szablony złożył (true/false)
CREATE TABLE IF NOT EXISTS bronze_filing_indicator (
    id          SERIAL PRIMARY KEY,
    report_id   INTEGER NOT NULL REFERENCES bronze_report(id) ON DELETE CASCADE,
    template_id VARCHAR(20) NOT NULL,
    reported    BOOLEAN NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bfi_report ON bronze_filing_indicator(report_id);

-- Surowe fakty: 1 wiersz = 1 komórka CSV
CREATE TABLE IF NOT EXISTS bronze_fact (
    id             SERIAL PRIMARY KEY,
    report_id      INTEGER NOT NULL REFERENCES bronze_report(id) ON DELETE CASCADE,
    template_file  VARCHAR(20) NOT NULL,                     -- k_61.00
    datapoint_code VARCHAR(30) NOT NULL,                     -- dp134665 (= dp + VariableID)
    fact_value     TEXT NOT NULL                             -- RAW jako tekst; bez rzutowania
);
CREATE INDEX IF NOT EXISTS idx_bf_report ON bronze_fact(report_id);
CREATE INDEX IF NOT EXISTS idx_bf_dp     ON bronze_fact(datapoint_code);

COMMENT ON TABLE bronze_fact IS 'Brąz: surowe fakty as-is. Rozszyfrowanie dp->metryka i typowanie = srebro.';

-- ============================================================
-- 3. SILVER — rozszyfrowanie + walidacja
-- Patrz też: db/migrations/002_silver_fact.sql, silver_build.py
-- ============================================================

-- Fakt z nadanym ZNACZENIEM = metryka + wymiary (koordynaty tabeli/etykiety = prezentacja -> złoto)
CREATE TABLE IF NOT EXISTS silver_fact (
    id                  SERIAL PRIMARY KEY,
    report_id           INTEGER NOT NULL REFERENCES bronze_report(id) ON DELETE CASCADE,
    bronze_fact_id      INTEGER NOT NULL,
    datapoint_code      VARCHAR(30) NOT NULL,
    variable_id         INTEGER,
    variable_vid        INTEGER,                          -- wersja ważna dla release'u raportu
    metric_property_id  INTEGER,                          -- PropertyID = metryka
    metric_name         TEXT,                             -- co jest mierzone (item.Name)
    is_metric           BOOLEAN,
    data_type           VARCHAR(5),                       -- m/p/i/r/s/d/e
    data_type_name      VARCHAR(40),
    value_text          TEXT,
    value_num           NUMERIC,                          -- NULL dla string/date/enum
    context_id          INTEGER,                          -- klucz do wymiarów (NULL = bezwymiarowy)
    dim_count           INTEGER DEFAULT 0,
    resolution_status   VARCHAR(30) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_silver_report ON silver_fact(report_id);
CREATE INDEX IF NOT EXISTS idx_silver_vvid   ON silver_fact(variable_vid);
CREATE INDEX IF NOT EXISTS idx_silver_dp     ON silver_fact(datapoint_code);
CREATE INDEX IF NOT EXISTS idx_silver_ctx    ON silver_fact(context_id);

-- Rozkład wymiarowy faktu (N wierszy na fakt; z DPM contextcomposition, nazwy z item.Name)
CREATE TABLE IF NOT EXISTS silver_fact_dimension (
    id                    SERIAL PRIMARY KEY,
    silver_fact_id        INTEGER NOT NULL REFERENCES silver_fact(id) ON DELETE CASCADE,
    report_id             INTEGER NOT NULL,
    dimension_property_id INTEGER,                        -- PropertyID = wymiar
    dimension_name        TEXT,                           -- np. "Residual maturity"
    member_item_id        INTEGER,                        -- ItemID = członek
    member_name           TEXT                            -- np. ">= 1 year"
);
CREATE INDEX IF NOT EXISTS idx_sfd_fact ON silver_fact_dimension(silver_fact_id);
CREATE INDEX IF NOT EXISTS idx_sfd_dim  ON silver_fact_dimension(dimension_name);
CREATE INDEX IF NOT EXISTS idx_sfd_mem  ON silver_fact_dimension(member_name);

-- DQ: rekoncyliacja strukturalna fakt↔komórka (patrz silver_reconcile.py, migracja 004)
CREATE TABLE IF NOT EXISTS silver_reconciliation (
    id            SERIAL PRIMARY KEY,
    report_id     INTEGER NOT NULL REFERENCES bronze_report(id) ON DELETE CASCADE,
    table_code    VARCHAR(20) NOT NULL,
    facts_total   INTEGER NOT NULL,
    facts_mapped  INTEGER NOT NULL,
    facts_orphan  INTEGER NOT NULL,
    checked_at    TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_recon_report ON silver_reconciliation(report_id);

CREATE TABLE IF NOT EXISTS silver_orphan_fact (
    id             SERIAL PRIMARY KEY,
    report_id      INTEGER NOT NULL REFERENCES bronze_report(id) ON DELETE CASCADE,
    silver_fact_id INTEGER NOT NULL,
    datapoint_code VARCHAR(30) NOT NULL,
    table_code     VARCHAR(20) NOT NULL,
    metric_name    TEXT
);
CREATE INDEX IF NOT EXISTS idx_orphan_report ON silver_orphan_fact(report_id);

CREATE TABLE IF NOT EXISTS validation_rule (
    id              SERIAL PRIMARY KEY,
    template_id     INTEGER REFERENCES eba_template(id),
    nazwa           VARCHAR(200) NOT NULL,
    opis            TEXT,
    typ             VARCHAR(30) NOT NULL,
    severity        VARCHAR(10) DEFAULT 'ERROR',
    threshold_value VARCHAR(50)
);

COMMENT ON COLUMN validation_rule.threshold_value IS 'Parametr reguły przechowywany w bazie, nie w kodzie. Np. 3.0 dla outlier_threshold, 6 dla max_report_age_months. Kod Pythona czyta tę wartość, nie ma jej zahardcodowanej.';

CREATE TABLE IF NOT EXISTS validation_result (
    id                  SERIAL PRIMARY KEY,
    report_id           INTEGER NOT NULL REFERENCES bronze_report(id) ON DELETE CASCADE,
    rule_id             INTEGER NOT NULL REFERENCES validation_rule(id),
    passed              BOOLEAN NOT NULL,
    wartosc_oczekiwana  VARCHAR(200),
    wartosc_rzeczywista VARCHAR(200),
    komunikat           TEXT,
    data_walidacji      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 4. INDEKSY
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_validation_report ON validation_result(report_id);
CREATE INDEX IF NOT EXISTS idx_bank_kraj ON bank(kraj);

-- ============================================================
-- 5. SEED DATA — dane referencyjne z EBA Framework 4.1
-- ============================================================

-- Moduły Pillar 3 (z DPM2 ModuleVersion v2.0.0, Release 5)
INSERT INTO eba_module (code, nazwa, opis) VALUES
    ('CODIS', 'Common disclosures', 'Wspólne ujawnienia — kluczowe wskaźniki, fundusze własne, ryzyko'),
    ('FINDIS', 'Financial disclosures', 'Ujawnienia finansowe — ekspozycje kredytowe, NPL, jakość aktywów'),
    ('REMDIS', 'Remuneration disclosures', 'Polityka wynagrodzeń — REM1-REM5'),
    ('ESGDIS', 'ESG disclosures', 'Ujawnienia ESG — GAR, BTAR, ryzyko klimatyczne'),
    ('GSIIDIS', 'G-SII disclosures', 'Wskaźniki dla globalnych banków systemowo ważnych'),
    ('MRELTLACDIS', 'MREL/TLAC disclosures', 'Wymogi MREL i TLAC — zdolność do pokrycia strat'),
    ('IRRBBDIS', 'IRRBB disclosures', 'Ryzyko stopy procentowej w portfelu bankowym'),
    ('P3DH', 'Pillar 3 Data Hub process', 'Dane kontaktowe i metadane procesu P3DH');

-- Szablony Pillar 3 (192 kody — z Annotated Table Layout, EBA Framework 4.1)
-- Grupowane wg modułu — CODIS (główne ujawnienia)
INSERT INTO eba_template (template_code, nazwa, module_id, wersja_taksonomii) VALUES
    ('K_00.02', 'Accompanying narrative CODIS', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_60.00.a', 'EU OV1 – Overview of total risk exposure amounts (I)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_60.00.b', 'EU OV1 – Overview of total risk exposure amounts (II)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_60.00.c', 'EU OV1 – Overview of total risk exposure amounts (III)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_61.00', 'EU KM1 - Key metrics template', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_62.01', 'EU INS1 - Insurance participations', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_62.02', 'EU INS2 - Financial conglomerates information on own funds', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_63.01.a', 'EU CMS1 – Comparison of modelled and standardised RWA at risk level', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_63.01.b', 'EU CMS1 – Comparison of modelled and standardised RWA at risk level', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_63.01.c', 'EU CMS1 – Comparison of modelled and standardised RWA at risk level', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_63.01.d', 'EU CMS1 – Comparison of modelled and standardised RWA at risk level', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_63.01.e', 'EU CMS1 – Comparison of modelled and standardised RWA at risk level', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_63.02.a', 'EU CMS2 – Comparison of modelled and standardised RWA for credit risk', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_63.02.b', 'EU CMS2 – Comparison of modelled and standardised RWA for credit risk', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_63.02.c', 'EU CMS2 – Comparison of modelled and standardised RWA for credit risk', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_64.01.a', 'EU LI1 - Differences between accounting and prudential scope (I)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_64.01.b', 'EU LI1 - Differences between accounting and prudential scope (II)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_64.01.c', 'EU LI1 - Differences between accounting and prudential scope (III)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_64.01.d', 'EU LI1 - Differences between accounting and prudential scope (IV)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_64.02', 'EU LI3 - Outline of differences in scopes of consolidation', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_64.03.a', 'EU LI2 - Main sources of differences (I)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_64.03.b', 'EU LI2 - Main sources of differences (II)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_65.00', 'EU PV1: Prudent valuation adjustments (PVA)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_66.01.a', 'EU CC1 - Composition of regulatory own funds (I)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_66.01.b', 'EU CC1 - Composition of regulatory own funds (II)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_66.02.a', 'EU CC2 - reconciliation of regulatory own funds to balance sheet (I)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_66.02.b', 'EU CC2 - reconciliation of regulatory own funds to balance sheet (II)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_66.02.c', 'EU CC2 - reconciliation of regulatory own funds to balance sheet (III)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_66.02.d', 'EU CC2 - reconciliation of regulatory own funds to balance sheet (IV)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_66.02.e', 'EU CC2 - reconciliation of regulatory own funds to balance sheet (V)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_66.02.f', 'EU CC2 - reconciliation of regulatory own funds to balance sheet (VI)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_67.01.a', 'EU CCyB1 - Geographical distribution of credit exposures (I)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_67.01.b', 'EU CCyB1 - Geographical distribution of credit exposures (II)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_67.02', 'EU CCyB2 - Amount of institution-specific countercyclical capital buffer', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_70.00', 'EU LR1 - LRSum: Summary reconciliation of accounting assets', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_71.00', 'EU LR2 - LRCom: Leverage ratio common disclosure', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_72.00', 'EU LR3 - LRSpl: Split-up of on balance sheet exposures', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_73.00.a', 'EU LIQ1 - Quantitative information of LCR (I)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_73.00.b', 'EU LIQ1 - Quantitative information of LCR (II)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_73.00.c', 'EU LIQ1 - Quantitative information of LCR (III)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_73.00.d', 'EU LIQ1 - Quantitative information of LCR (IV)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_73.00.e', 'EU LIQ1 - Quantitative information of LCR (V)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_74.00.a', 'EU LIQ2: Net Stable Funding Ratio (I)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_74.00.b', 'EU LIQ2: Net Stable Funding Ratio (II)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_74.00.c', 'EU LIQ2: Net Stable Funding Ratio (III)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_74.00.d', 'EU LIQ2: Net Stable Funding Ratio (IV)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_74.00.e', 'EU LIQ2: Net Stable Funding Ratio (V)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_74.00.f', 'EU LIQ2: Net Stable Funding Ratio (VI)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_01.00.a', 'EU CAE1 – Exposures to crypto-assets (I)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_01.00.b', 'EU CAE1 – Exposures to crypto-assets (II)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_02.00', 'EU CCR1 – Analysis of CCR exposure by approach', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_03.00', 'EU CCR3 – Standardised approach – CCR exposures', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_04.00.a', 'EU CCR4 – IRB approach – CCR exposures by PD scale (I)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_04.00.b', 'EU CCR4 – IRB approach – CCR exposures by PD scale (II)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_05.00.a', 'EU CCR5 – Composition of collateral for CCR exposures (I)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_05.00.b', 'EU CCR5 – Composition of collateral for CCR exposures (II)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_06.00', 'EU CCR6 – Credit derivatives exposures', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_07.00', 'EU CCR7 – RWEA flow statements of CCR under IMM', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_08.00', 'EU CCR8 – Exposures to CCPs', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_09.01', 'EU-SEC1 - Securitisation exposures in non-trading book', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_09.02', 'EU-SEC2 - Securitisation exposures in trading book', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_09.03', 'EU-SEC3 - Securitisation exposures — originator/sponsor', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_09.04', 'EU-SEC4 - Securitisation exposures — investor', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_09.05', 'EU-SEC5 - Exposures securitised — default and credit risk adjustments', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_10.00', 'EU MR1 - Market risk under standardised approach', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_11.00.a', 'EU MR2-A - Market risk under IMA — RWEA', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_11.00.b', 'EU MR2-A - Market risk under IMA — Own funds requirements', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_12.00', 'EU MR2-B - RWA flow statements of market risk under IMA', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_13.00', 'EU MR3 - IMA values for trading portfolios', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_18.01.a', 'EU CVA 1 – CVA risk Reduced Basic Approach — OFR components', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_18.01.b', 'EU CVA 1 – CVA risk Reduced Basic Approach — OFRs', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_18.02.a', 'EU CVA 2 – CVA risk Full Basic Approach — OFRs', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_18.02.b', 'EU CVA 2 – CVA risk Full Basic Approach — Hedges', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_18.03', 'EU CVA3 – CVA risk under Standardised Approach', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_18.04', 'EU CVA4 – RWEA flow statements of CVA risk', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_19.01', 'EU OR1 - Operational risk losses', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_19.02.a', 'EU OR2 - Business Indicator components (I)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_19.02.b', 'EU OR2 - Business Indicator components (II)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_19.02.c', 'EU OR2 - Business indicator components (III)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_19.03', 'EU OR3 - Operational risk own funds requirements', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_23.00', 'EU CR3 – CRM techniques overview', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_24.00', 'EU CR4 – standardised approach – Credit risk and CRM effects', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_25.00', 'EU CR5 – standardised approach', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_26.00.a', 'EU CR6 – IRB approach – Credit risk by PD range (I)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_26.00.b', 'EU CR6 – IRB approach – Credit risk by PD range (II)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_26.01', 'EU CR6-A – Scope of IRB and SA approaches', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_27.01', 'EU CR7 – IRB approach – Effect on RWEAs of credit derivatives', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_27.02.a', 'EU CR7-A – IRB approach – Extent of CRM techniques (I)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_27.02.b', 'EU CR7-A – IRB approach – Extent of CRM techniques (II)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_28.00', 'EU CR8 – RWEA flow statements of credit risk under IRB', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_29.00', 'EU CR9 – IRB approach – Back-testing of PD', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_29.01.a', 'EU CR9.1 – Back-testing of PD per exposure class (I)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_29.01.b', 'EU CR9.1 – Back-testing of PD per exposure class (II)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_29.02.a', 'EU CR10 – Specialised lending and equity (I)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_29.02.b', 'EU CR10 – Specialised lending and equity (II)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1'),
    ('K_29.02.c', 'EU CR10 – Specialised lending and equity (III)', (SELECT id FROM eba_module WHERE code='CODIS'), 'v4.1');

-- FINDIS (Financial disclosures)
INSERT INTO eba_template (template_code, nazwa, module_id, wersja_taksonomii) VALUES
    ('K_00.01', 'Accompanying narrative FINDIS', (SELECT id FROM eba_module WHERE code='FINDIS'), 'v4.1'),
    ('K_20.01', 'EU AE1 - Encumbered and unencumbered assets', (SELECT id FROM eba_module WHERE code='FINDIS'), 'v4.1'),
    ('K_20.02', 'EU AE2 - Collateral received and own debt securities', (SELECT id FROM eba_module WHERE code='FINDIS'), 'v4.1'),
    ('K_20.03', 'EU AE3 - Sources of encumbrance', (SELECT id FROM eba_module WHERE code='FINDIS'), 'v4.1'),
    ('K_21.01.a', 'EU CR1: Performing and non-performing exposures (I)', (SELECT id FROM eba_module WHERE code='FINDIS'), 'v4.1'),
    ('K_21.01.b', 'EU CR1: Performing and non-performing exposures (II)', (SELECT id FROM eba_module WHERE code='FINDIS'), 'v4.1'),
    ('K_21.01.c', 'EU CR1: Performing and non-performing exposures (III)', (SELECT id FROM eba_module WHERE code='FINDIS'), 'v4.1'),
    ('K_21.01.d', 'EU CR1: Performing and non-performing exposures (IV)', (SELECT id FROM eba_module WHERE code='FINDIS'), 'v4.1'),
    ('K_21.01.e', 'EU CR1: Performing and non-performing exposures (V)', (SELECT id FROM eba_module WHERE code='FINDIS'), 'v4.1'),
    ('K_21.01.f', 'EU CR1: Performing and non-performing exposures (VI)', (SELECT id FROM eba_module WHERE code='FINDIS'), 'v4.1'),
    ('K_21.02', 'EU CR1-A: Maturity of exposures', (SELECT id FROM eba_module WHERE code='FINDIS'), 'v4.1'),
    ('K_22.01', 'EU CR2: Changes in stock of non-performing loans', (SELECT id FROM eba_module WHERE code='FINDIS'), 'v4.1'),
    ('K_22.02.a', 'EU CR2a: Changes in stock of NPL and net accumulated recoveries (I)', (SELECT id FROM eba_module WHERE code='FINDIS'), 'v4.1'),
    ('K_22.02.b', 'EU CR2a: Changes in stock of NPL and net accumulated recoveries (II)', (SELECT id FROM eba_module WHERE code='FINDIS'), 'v4.1'),
    ('K_80.00.a', 'EU CQ1: Credit quality of forborne exposures (I)', (SELECT id FROM eba_module WHERE code='FINDIS'), 'v4.1'),
    ('K_80.00.b', 'EU CQ1: Credit quality of forborne exposures (II)', (SELECT id FROM eba_module WHERE code='FINDIS'), 'v4.1'),
    ('K_80.00.c', 'EU CQ1: Credit quality of forborne exposures (III)', (SELECT id FROM eba_module WHERE code='FINDIS'), 'v4.1'),
    ('K_80.00.d', 'EU CQ1: Credit quality of forborne exposures (IV)', (SELECT id FROM eba_module WHERE code='FINDIS'), 'v4.1'),
    ('K_80.00.e', 'EU CQ1: Credit quality of forborne exposures (V)', (SELECT id FROM eba_module WHERE code='FINDIS'), 'v4.1'),
    ('K_81.00', 'EU CQ2: Quality of forbearance', (SELECT id FROM eba_module WHERE code='FINDIS'), 'v4.1'),
    ('K_82.00.a', 'EU CQ3: Credit quality by past due days (I)', (SELECT id FROM eba_module WHERE code='FINDIS'), 'v4.1'),
    ('K_82.00.b', 'EU CQ3: Credit quality by past due days (II)', (SELECT id FROM eba_module WHERE code='FINDIS'), 'v4.1'),
    ('K_82.00.c', 'EU CQ3: Credit quality by past due days (III)', (SELECT id FROM eba_module WHERE code='FINDIS'), 'v4.1'),
    ('K_83.01.a', 'EU CQ4: Quality of NPE by geography (I)', (SELECT id FROM eba_module WHERE code='FINDIS'), 'v4.1'),
    ('K_83.01.b', 'EU CQ4: Quality of NPE by geography (II)', (SELECT id FROM eba_module WHERE code='FINDIS'), 'v4.1'),
    ('K_83.01.c', 'EU CQ4: Quality of NPE by geography (III)', (SELECT id FROM eba_module WHERE code='FINDIS'), 'v4.1'),
    ('K_83.01.d', 'EU CQ4: Quality of NPE by geography (IV)', (SELECT id FROM eba_module WHERE code='FINDIS'), 'v4.1'),
    ('K_83.01.e', 'EU CQ4: Quality of NPE by geography (V)', (SELECT id FROM eba_module WHERE code='FINDIS'), 'v4.1'),
    ('K_84.01', 'EU CQ5: Credit quality of loans by industry', (SELECT id FROM eba_module WHERE code='FINDIS'), 'v4.1'),
    ('K_85.00', 'EU CQ6: Collateral valuation — loans and advances', (SELECT id FROM eba_module WHERE code='FINDIS'), 'v4.1'),
    ('K_86.00', 'EU CQ7: Collateral obtained by taking possession', (SELECT id FROM eba_module WHERE code='FINDIS'), 'v4.1'),
    ('K_87.00.a', 'EU CQ8: Collateral vintage breakdown (I)', (SELECT id FROM eba_module WHERE code='FINDIS'), 'v4.1'),
    ('K_87.00.b', 'EU CQ8: Collateral vintage breakdown (II)', (SELECT id FROM eba_module WHERE code='FINDIS'), 'v4.1');

-- REMDIS (Remuneration)
INSERT INTO eba_template (template_code, nazwa, module_id, wersja_taksonomii) VALUES
    ('K_30.01', 'EU REM1 - Remuneration awarded for the financial year', (SELECT id FROM eba_module WHERE code='REMDIS'), 'v4.1'),
    ('K_30.02', 'EU REM2 - Special payments to identified staff', (SELECT id FROM eba_module WHERE code='REMDIS'), 'v4.1'),
    ('K_30.03', 'EU REM3 - Deferred remuneration', (SELECT id FROM eba_module WHERE code='REMDIS'), 'v4.1'),
    ('K_30.04', 'EU REM4 - Remuneration of 1 million EUR or more', (SELECT id FROM eba_module WHERE code='REMDIS'), 'v4.1'),
    ('K_30.05.a', 'EU REM5 - Remuneration of identified staff (I)', (SELECT id FROM eba_module WHERE code='REMDIS'), 'v4.1'),
    ('K_30.05.b', 'EU REM5 - Remuneration of identified staff (II)', (SELECT id FROM eba_module WHERE code='REMDIS'), 'v4.1');

-- ESGDIS (ESG disclosures)
INSERT INTO eba_template (template_code, nazwa, module_id, wersja_taksonomii) VALUES
    ('K_00.03', 'Accompanying narrative ESGDIS', (SELECT id FROM eba_module WHERE code='ESGDIS'), 'v4.1'),
    ('K_41.00', 'Template 1 - Indicators of climate change transition risk', (SELECT id FROM eba_module WHERE code='ESGDIS'), 'v4.1'),
    ('K_42.00.a', 'Template 2 - Loans collateralised by immovable property (I)', (SELECT id FROM eba_module WHERE code='ESGDIS'), 'v4.1'),
    ('K_42.00.b', 'Template 2 - Loans collateralised by immovable property (II)', (SELECT id FROM eba_module WHERE code='ESGDIS'), 'v4.1'),
    ('K_43.00.a', 'Template 3 - Alignment metrics (I)', (SELECT id FROM eba_module WHERE code='ESGDIS'), 'v4.1'),
    ('K_43.00.b', 'Template 3 - Alignment metrics (II)', (SELECT id FROM eba_module WHERE code='ESGDIS'), 'v4.1'),
    ('K_44.00', 'Template 4 - Exposures to top 20 carbon-intensive firms', (SELECT id FROM eba_module WHERE code='ESGDIS'), 'v4.1'),
    ('K_45.00.a', 'Template 5 - Exposures subject to physical risk (I)', (SELECT id FROM eba_module WHERE code='ESGDIS'), 'v4.1'),
    ('K_45.00.b', 'Template 5 - Exposures subject to physical risk (II)', (SELECT id FROM eba_module WHERE code='ESGDIS'), 'v4.1'),
    ('K_46.00.a', 'Template 6 - Summary of GAR KPIs (I)', (SELECT id FROM eba_module WHERE code='ESGDIS'), 'v4.1'),
    ('K_46.00.b', 'Template 6 - Summary of GAR KPIs (II)', (SELECT id FROM eba_module WHERE code='ESGDIS'), 'v4.1'),
    ('K_47.00.a', 'Template 7 - Assets for GAR calculation (I)', (SELECT id FROM eba_module WHERE code='ESGDIS'), 'v4.1'),
    ('K_47.00.b', 'Template 7 - Assets for GAR calculation (II)', (SELECT id FROM eba_module WHERE code='ESGDIS'), 'v4.1'),
    ('K_48.00.a', 'Template 8 - GAR (%) (I)', (SELECT id FROM eba_module WHERE code='ESGDIS'), 'v4.1'),
    ('K_48.00.b', 'Template 8 - GAR (%) (II)', (SELECT id FROM eba_module WHERE code='ESGDIS'), 'v4.1'),
    ('K_48.00.c', 'Template 8 - GAR (%) (III)', (SELECT id FROM eba_module WHERE code='ESGDIS'), 'v4.1'),
    ('K_48.00.d', 'Template 8 - GAR (%) (IV)', (SELECT id FROM eba_module WHERE code='ESGDIS'), 'v4.1'),
    ('K_48.00.e', 'Template 8 - GAR (%) (V)', (SELECT id FROM eba_module WHERE code='ESGDIS'), 'v4.1'),
    ('K_49.01', 'Template 9.1 - Assets for BTAR calculation', (SELECT id FROM eba_module WHERE code='ESGDIS'), 'v4.1'),
    ('K_49.02.a', 'Template 9.2 - BTAR % (I)', (SELECT id FROM eba_module WHERE code='ESGDIS'), 'v4.1'),
    ('K_49.02.b', 'Template 9.2 - BTAR % (II)', (SELECT id FROM eba_module WHERE code='ESGDIS'), 'v4.1'),
    ('K_49.02.c', 'Template 9.2 - BTAR % (III)', (SELECT id FROM eba_module WHERE code='ESGDIS'), 'v4.1'),
    ('K_49.02.d', 'Template 9.2 - BTAR % (IV)', (SELECT id FROM eba_module WHERE code='ESGDIS'), 'v4.1'),
    ('K_49.03.a', 'Template 9.3 - Summary BTAR % (I)', (SELECT id FROM eba_module WHERE code='ESGDIS'), 'v4.1'),
    ('K_49.03.b', 'Template 9.3 - Summary BTAR % (II)', (SELECT id FROM eba_module WHERE code='ESGDIS'), 'v4.1'),
    ('K_50.00', 'Template 10 - Other climate mitigating actions', (SELECT id FROM eba_module WHERE code='ESGDIS'), 'v4.1');

-- GSIIDIS (G-SII)
INSERT INTO eba_template (template_code, nazwa, module_id, wersja_taksonomii) VALUES
    ('K_00.06', 'Accompanying narrative G-SIIs', (SELECT id FROM eba_module WHERE code='GSIIDIS'), 'v4.1'),
    ('K_100.00', 'Section 1 - General Information', (SELECT id FROM eba_module WHERE code='GSIIDIS'), 'v4.1'),
    ('K_101.00', 'Section 2 - Total exposures', (SELECT id FROM eba_module WHERE code='GSIIDIS'), 'v4.1'),
    ('K_102.00', 'Section 3 - Intra-Financial System Assets', (SELECT id FROM eba_module WHERE code='GSIIDIS'), 'v4.1'),
    ('K_103.00', 'Section 4 - Intra-Financial System Liabilities', (SELECT id FROM eba_module WHERE code='GSIIDIS'), 'v4.1'),
    ('K_104.00', 'Section 5 - Securities Outstanding', (SELECT id FROM eba_module WHERE code='GSIIDIS'), 'v4.1'),
    ('K_105.00', 'Section 6 - Payments made in reporting year', (SELECT id FROM eba_module WHERE code='GSIIDIS'), 'v4.1'),
    ('K_106.00', 'Section 7 - Assets Under Custody', (SELECT id FROM eba_module WHERE code='GSIIDIS'), 'v4.1'),
    ('K_107.00', 'Section 8 - Underwritten Transactions', (SELECT id FROM eba_module WHERE code='GSIIDIS'), 'v4.1'),
    ('K_108.00', 'Section 9 - Trading Volume', (SELECT id FROM eba_module WHERE code='GSIIDIS'), 'v4.1'),
    ('K_109.00', 'Section 10 - Notional Amount of OTC Derivatives', (SELECT id FROM eba_module WHERE code='GSIIDIS'), 'v4.1'),
    ('K_110.00', 'Section 11 - Trading and AFS Securities', (SELECT id FROM eba_module WHERE code='GSIIDIS'), 'v4.1'),
    ('K_111.00', 'Section 12 - Level 3 Assets', (SELECT id FROM eba_module WHERE code='GSIIDIS'), 'v4.1'),
    ('K_112.00', 'Section 13 - Cross-Jurisdictional Claims', (SELECT id FROM eba_module WHERE code='GSIIDIS'), 'v4.1'),
    ('K_113.00', 'Section 14 - Cross-Jurisdictional Liabilities', (SELECT id FROM eba_module WHERE code='GSIIDIS'), 'v4.1');

-- MRELTLACDIS
INSERT INTO eba_template (template_code, nazwa, module_id, wersja_taksonomii) VALUES
    ('K_00.05', 'Accompanying narrative MREL/TLACDIS', (SELECT id FROM eba_module WHERE code='MRELTLACDIS'), 'v4.1'),
    ('K_90.01', 'EU KM2 - Key metrics MREL/TLAC', (SELECT id FROM eba_module WHERE code='MRELTLACDIS'), 'v4.1'),
    ('K_91.00.a', 'EU TLAC1 - Composition MREL/TLAC (I)', (SELECT id FROM eba_module WHERE code='MRELTLACDIS'), 'v4.1'),
    ('K_91.00.b', 'EU TLAC1 - Composition MREL/TLAC (II)', (SELECT id FROM eba_module WHERE code='MRELTLACDIS'), 'v4.1'),
    ('K_93.00', 'EU ILAC - Internal loss absorbing capacity', (SELECT id FROM eba_module WHERE code='MRELTLACDIS'), 'v4.1'),
    ('K_95.00.a', 'EU TLAC2a - Creditor ranking non-resolution (I)', (SELECT id FROM eba_module WHERE code='MRELTLACDIS'), 'v4.1'),
    ('K_95.00.b', 'EU TLAC2a - Creditor ranking non-resolution (II)', (SELECT id FROM eba_module WHERE code='MRELTLACDIS'), 'v4.1'),
    ('K_96.00.a', 'EU TLAC2b - Creditor ranking non-resolution (I)', (SELECT id FROM eba_module WHERE code='MRELTLACDIS'), 'v4.1'),
    ('K_96.00.b', 'EU TLAC2b - Creditor ranking non-resolution (II)', (SELECT id FROM eba_module WHERE code='MRELTLACDIS'), 'v4.1'),
    ('K_97.00.a', 'EU TLAC3a - Creditor ranking resolution (I)', (SELECT id FROM eba_module WHERE code='MRELTLACDIS'), 'v4.1'),
    ('K_97.00.b', 'EU TLAC3a - Creditor ranking resolution (II)', (SELECT id FROM eba_module WHERE code='MRELTLACDIS'), 'v4.1'),
    ('K_98.00.a', 'EU TLAC3b - Creditor ranking resolution (I)', (SELECT id FROM eba_module WHERE code='MRELTLACDIS'), 'v4.1'),
    ('K_98.00.b', 'EU TLAC3b - Creditor ranking resolution (II)', (SELECT id FROM eba_module WHERE code='MRELTLACDIS'), 'v4.1');

-- IRRBBDIS
INSERT INTO eba_template (template_code, nazwa, module_id, wersja_taksonomii) VALUES
    ('K_00.04', 'Accompanying narrative IRRBBDIS', (SELECT id FROM eba_module WHERE code='IRRBBDIS'), 'v4.1'),
    ('K_68.00', 'EU IRRBB1 - Interest rate risks of non-trading book', (SELECT id FROM eba_module WHERE code='IRRBBDIS'), 'v4.1');

-- P3DH (data kontaktowe)
INSERT INTO eba_template (template_code, nazwa, module_id, wersja_taksonomii) VALUES
    ('X_01.00', 'Institutions contact person for Pillar 3 Data Hub Process', (SELECT id FROM eba_module WHERE code='P3DH'), 'v4.1');

-- Przykładowe banki (polskie, G-SIB i duże europejskie)
INSERT INTO bank (lei, nazwa, kraj, kategoria, url_disclosures) VALUES
    ('259400L3WXYON7RM6B64', 'PKO Bank Polski S.A.', 'Polska', 'duży', 'https://www.pkobp.pl/relacje-inwestorskie/'),
    ('5493000OSXBYZKM8OW67', 'Bank Pekao S.A.', 'Polska', 'duży', 'https://www.pekao.com.pl/relacje-inwestorskie.html'),
    ('549300GM50WEVG4DKV43', 'mBank S.A.', 'Polska', 'duży', 'https://www.mbank.pl/relacje-inwestorskie/'),
    ('2594007C6P4H4K9UTK68', 'ING Bank Śląski S.A.', 'Polska', 'duży', 'https://www.ing.pl/relacje-inwestorskie'),
    ('529900NNUPAGJNYKKU75', 'Santander Bank Polska S.A.', 'Polska', 'duży', 'https://www.santander.pl/relacje-inwestorskie'),
    ('529900JKFB1P4A3L7F95', 'BNP Paribas S.A.', 'Francja', 'G-SII', 'https://invest.bnpparibas/'),
    ('7LTWFZYICNSX8D621K86', 'Deutsche Bank AG', 'Niemcy', 'G-SII', 'https://investor-relations.db.com/'),
    ('213800RGSWBH3Y4AJW20', 'Erste Group Bank AG', 'Austria', 'O-SII', 'https://www.erstegroup.com/en/investors');

-- Okresy raportowe (od Q4 2024 do Q4 2025)
INSERT INTO reporting_period (okres, data_od, data_do, status) VALUES
    ('2024-Q4', '2024-10-01', '2024-12-31', 'opublikowany'),
    ('2025-Q1', '2025-01-01', '2025-03-31', 'opublikowany'),
    ('2025-Q2', '2025-04-01', '2025-06-30', 'opublikowany'),
    ('2025-Q3', '2025-07-01', '2025-09-30', 'oczekiwany'),
    ('2025-Q4', '2025-10-01', '2025-12-31', 'oczekiwany');

-- Ogólne reguły walidacyjne EBA (typy reguł)
-- Wartości progowe (threshold_value) są w bazie — kod Pythona je czyta, nie ma ich zahardcodowanych.
INSERT INTO validation_rule (template_id, nazwa, opis, typ, severity, threshold_value) VALUES
    (NULL, 'Kompletność szablonów', 'Wszystkie wymagane szablony dla danej kategorii banku muszą być zaraportowane', 'kompletnosc', 'ERROR', NULL),
    (NULL, 'Spójność sum kontrolnych', 'Sumy cząstkowe w szablonie muszą być równe sumom całkowitym zdefiniowanym w taksonomii', 'spojnosc', 'ERROR', NULL),
    (NULL, 'Zakres dat', 'Data publikacji raportu nie może być późniejsza niż 6 miesięcy od końca okresu raportowego', 'zakres', 'WARNING', '6'),
    (NULL, 'Kompletność datapointów', 'Każdy wymagany datapoint wg taksonomii EBA musi być wypełniony', 'kompletnosc', 'ERROR', NULL),
    (NULL, 'Próg outliera', 'Wartość uznawana za outlier jeśli odbiega o więcej niż N odchyleń standardowych od mediany sektorowej', 'outlier', 'WARNING', '3.0'),
    -- Reguły dla szablonu KM1 (kluczowe wskaźniki)
    ((SELECT id FROM eba_template WHERE template_code='K_61.00'),
     'KM1: CET1 ratio > 4.5%', 'Wskaźnik CET1 nie może być niższy niż wymóg minimalny 4.5%', 'spojnosc', 'ERROR', '4.5'),
    ((SELECT id FROM eba_template WHERE template_code='K_61.00'),
     'KM1: LCR > 100%', 'Wskaźnik LCR nie może być niższy niż 100%', 'spojnosc', 'ERROR', '100'),
    -- Reguła dla OV1 (całkowite RWA)
    ((SELECT id FROM eba_template WHERE template_code='K_60.00.a'),
     'OV1: Suma RWA = suma ekspozycji', 'Całkowite RWA powinno być równe sumie RWA z poszczególnych kategorii ryzyka', 'spojnosc', 'ERROR', NULL);
