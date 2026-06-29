-- ============================================================
-- Migracja 003 — Srebro: warstwa ZNACZENIOWA oparta na ContextID
-- ============================================================
-- Korekta: koordynaty tabeli (cell/row/col + etykiety) to PREZENTACJA -> złoto.
-- Znaczenie faktu = metryka (PropertyID) + wymiary (ContextID -> contextcomposition).
-- Ten sam VariableVID bywa w wielu komórkach => adres nie jest znaczeniem.
--
-- Nazwy: i wymiar, i członek nazywają się przez item.Name:
--   contextcomposition.PropertyID -> item (IsProperty=true)  = nazwa WYMIARU
--   contextcomposition.ItemID     -> item (IsProperty=false) = nazwa CZŁONKA
--   variableversion.PropertyID    -> item                    = nazwa METRYKI
-- ============================================================

DROP TABLE IF EXISTS silver_fact_dimension;
DROP TABLE IF EXISTS silver_fact;

-- Fakt z nadanym znaczeniem (1 wiersz na fakt)
CREATE TABLE silver_fact (
    id                  SERIAL PRIMARY KEY,
    report_id           INTEGER NOT NULL REFERENCES bronze_report(id) ON DELETE CASCADE,
    bronze_fact_id      INTEGER NOT NULL,
    datapoint_code      VARCHAR(30) NOT NULL,
    variable_id         INTEGER,
    variable_vid        INTEGER,                          -- wersja ważna dla release'u raportu
    metric_property_id  INTEGER,                          -- PropertyID = metryka
    metric_name         TEXT,                             -- co jest mierzone
    is_metric           BOOLEAN,
    data_type           VARCHAR(5),                       -- m/p/i/r/s/d/e
    data_type_name      VARCHAR(40),
    value_text          TEXT,
    value_num           NUMERIC,                          -- NULL dla string/date/enum
    context_id          INTEGER,                          -- klucz do wymiarów (NULL = bezwymiarowy)
    dim_count           INTEGER DEFAULT 0,                -- ile wymiarów
    resolution_status   VARCHAR(30) NOT NULL              -- resolved / unresolved
);
CREATE INDEX IF NOT EXISTS idx_silver_report ON silver_fact(report_id);
CREATE INDEX IF NOT EXISTS idx_silver_vvid   ON silver_fact(variable_vid);
CREATE INDEX IF NOT EXISTS idx_silver_dp     ON silver_fact(datapoint_code);
CREATE INDEX IF NOT EXISTS idx_silver_ctx    ON silver_fact(context_id);

COMMENT ON TABLE silver_fact IS 'Srebro: znaczenie faktu = metryka + (wymiary w silver_fact_dimension). Koordynaty tabeli/etykiety = prezentacja, w złocie.';

-- Rozkład wymiarowy (N wierszy na fakt; wierne odbicie contextcomposition)
CREATE TABLE silver_fact_dimension (
    id                   SERIAL PRIMARY KEY,
    silver_fact_id       INTEGER NOT NULL REFERENCES silver_fact(id) ON DELETE CASCADE,
    report_id            INTEGER NOT NULL,                -- dla wygodnego filtrowania
    dimension_property_id INTEGER,                        -- PropertyID = wymiar
    dimension_name       TEXT,                            -- np. "Residual maturity"
    member_item_id       INTEGER,                         -- ItemID = członek
    member_name          TEXT                             -- np. ">= 1 year"
);
CREATE INDEX IF NOT EXISTS idx_sfd_fact ON silver_fact_dimension(silver_fact_id);
CREATE INDEX IF NOT EXISTS idx_sfd_dim  ON silver_fact_dimension(dimension_name);
CREATE INDEX IF NOT EXISTS idx_sfd_mem  ON silver_fact_dimension(member_name);

COMMENT ON TABLE silver_fact_dimension IS 'Srebro: rozkład wymiarowy faktu (wymiar=członek). Z DPM contextcomposition; nazwy z item.Name.';
