-- ============================================================
-- Migracja 006 — Brąz: numer wersji sprawozdania (version_no)
-- ============================================================
-- Wersjonowanie resubmisji liczone w BAZIE (nie w dashboardzie):
-- per business_key, wg daty przekazania (report_generated): v1 = najstarsza.
-- Liczone razem z is_current (najnowsza = TRUE). Backfill istniejących wierszy.
-- ============================================================

ALTER TABLE bronze_report ADD COLUMN IF NOT EXISTS version_no INTEGER;

WITH v AS (
    SELECT id,
           ROW_NUMBER() OVER (PARTITION BY business_key ORDER BY report_generated) AS vno,
           (report_generated = MAX(report_generated) OVER (PARTITION BY business_key)) AS cur
    FROM bronze_report
)
UPDATE bronze_report b
SET version_no = v.vno,
    is_current = v.cur
FROM v
WHERE b.id = v.id;

COMMENT ON COLUMN bronze_report.version_no IS 'Numer wersji sprawozdania w grupie business_key (v1=najstarsza wg report_generated). Liczony w bronze_ingest razem z is_current.';
