-- ============================================================
-- Migracja 004 — Srebro: rekoncyliacja strukturalna (data quality)
-- ============================================================
-- Kontrola, NIE prezentacja: czy każdy fakt ma DOKŁADNIE jedno miejsce
-- (komórkę) w definicji swojego szablonu? Używa encji definicji tabel DPM
-- (tableversion, tableversioncell) tylko do WERYFIKACJI — koordynaty/etykiety
-- do wyświetlania zostają na złoto.
-- Wynik: podsumowanie per raport × szablon + lista sierot (fakt bez komórki).
-- ============================================================

DROP TABLE IF EXISTS silver_reconciliation;
DROP TABLE IF EXISTS silver_orphan_fact;

-- Podsumowanie pokrycia: ile faktów, ile z komórką, ile sierot
CREATE TABLE silver_reconciliation (
    id            SERIAL PRIMARY KEY,
    report_id     INTEGER NOT NULL REFERENCES bronze_report(id) ON DELETE CASCADE,
    table_code    VARCHAR(20) NOT NULL,
    facts_total   INTEGER NOT NULL,
    facts_mapped  INTEGER NOT NULL,        -- fakty z dokładnie jedną komórką
    facts_orphan  INTEGER NOT NULL,        -- fakty bez komórki w definicji szablonu
    checked_at    TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_recon_report ON silver_reconciliation(report_id);

COMMENT ON TABLE silver_reconciliation IS 'Srebro DQ: rekoncyliacja fakt↔komórka per raport×szablon. facts_orphan>0 = anomalia (fakt bez miejsca w układzie tabeli).';

-- Detal sierot (fakt, który nie trafił w żadną komórkę swojego szablonu)
CREATE TABLE silver_orphan_fact (
    id             SERIAL PRIMARY KEY,
    report_id      INTEGER NOT NULL REFERENCES bronze_report(id) ON DELETE CASCADE,
    silver_fact_id INTEGER NOT NULL,
    datapoint_code VARCHAR(30) NOT NULL,
    table_code     VARCHAR(20) NOT NULL,
    metric_name    TEXT
);
CREATE INDEX IF NOT EXISTS idx_orphan_report ON silver_orphan_fact(report_id);

COMMENT ON TABLE silver_orphan_fact IS 'Srebro DQ: fakty bez komórki w definicji szablonu (do zbadania — np. dp w CSV bez miejsca w układzie taksonomii).';
