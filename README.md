# EBA Pillar 3 Data Pipeline

An end-to-end **data engineering pipeline** that ingests, decodes and analyses
European banks' **Pillar 3** prudential disclosures published through the
[EBA Pillar 3 Data Hub](https://edap-public.eba.europa.eu/).

Raw regulatory `xBRL-CSV` packages → **machine-readable, fully-labelled financial
facts** → reconstructed disclosure tables identical to EBA's official rendering.

> **Context.** A learning project built to practice the full data-engineering
> lifecycle (medallion architecture, reference-data resolution, orchestration,
> data quality, visualisation) on a domain the author knows well — bank
> regulatory reporting (XBRL, DPM, FINREP/COREP). Real EBA data, real EBA
> taxonomy (DPM 2.0).

---

## What it does

Takes an opaque regulatory fact like:

```
datapoint,factValue
dp134665,49868956058.0555
```

and turns it into:

```
Bank:    DEUTSCHE BANK AG  (LEI 7LTWFZYICNSX8D621K86)
Metric:  Common Equity Tier 1 (CET1) capital
Period:  a. T (2026-03-31)
Value:   49,868,956,058 EUR
```

…then reassembles the full **EU KM1 / OV1 / …** templates with row & column
labels — matching what the EBA portal displays.

## Architecture — Medallion (Bronze / Silver / Gold)

```
 xBRL-CSV .zip (EBA)
        │  parser (pure Python: zipfile + csv)
        ▼
 ┌──────────────┐   raw, as-is (text), version-aware
 │   BRONZE     │   bronze_report · bronze_filing_indicator · bronze_fact
 └──────┬───────┘
        │  resolve meaning via DPM 2.0
        ▼
 ┌──────────────┐   metric + dimensions + typed value
 │   SILVER     │   silver_fact · silver_fact_dimension  (+ DQ reconciliation)
 └──────┬───────┘
        │  presentation
        ▼
 ┌──────────────┐   fact placed in its table cell + labels
 │    GOLD      │   gold_cell  →  HTML render of the disclosure
 └──────────────┘
```

Interactive diagrams (open the HTML in a browser):

- [`docs/system_uml.html`](docs/system_uml.html) — full system
- [`docs/bronze_schema.html`](docs/bronze_schema.html) — bronze table relations
- [`docs/silver_resolution.html`](docs/silver_resolution.html) — meaning-resolution chain
- [`docs/render_k_61_00_2.html`](docs/render_k_61_00_2.html) — reconstructed KM1 (Deutsche Bank)

## Key ideas

- **Bronze = raw, faithful.** Values stored as text, exactly as filed. Package
  versioning: re-submissions of the same report (`business_key` + `is_current`).
- **DPM 2.0 is version-aware.** A datapoint code `dpNNNN` = a stable `VariableID`;
  its definition is versioned as `VariableVID` valid for a release window
  (`StartReleaseID ≤ R < EndReleaseID`) — like reading the version of a law in
  force on a given date. Each fact is resolved against the release its report
  declares (`report.json`).
- **Meaning vs presentation.** Silver carries *meaning* (metric + dimensions,
  decoded from the heavily-normalised DPM dictionary). Table coordinates and
  row/column labels are *presentation* and live in Gold.
- **Data quality.** Structural reconciliation checks every fact maps to exactly
  one cell of its template (surfaces real anomalies).
- **Human-readable.** Bank legal names resolved from [GLEIF](https://www.gleif.org/) by LEI.

## Tech stack

PostgreSQL · Python (psycopg2, pandas) · **Prefect** (orchestration) ·
**watchdog** (landing-zone auto-trigger) · Docker Compose · Streamlit *(planned)*.
DPM 2.0 reference dictionary loaded from EBA's Access database into a `dpm2_ref` schema.

## Repository layout

```
bronze_ingest_csv.py   Bronze: parse xBRL-CSV packages → DB
silver_build.py        Silver: resolve dp → metric + dimensions (+ typing)
silver_reconcile.py    Silver DQ: fact ↔ template-cell reconciliation
gold_build.py          Gold: place facts in table cells + labels
gold_render.py         Render a template (report_id, table_code) → HTML
enrich_banks.py        Master data: bank names from GLEIF
pipeline.py            Prefect flow — runs the whole chain
watch_landing.py       Watcher — drop a .zip, pipeline runs itself
migrate_dpm2_to_pg.py  Load DPM 2.0 (Access .accdb) → PostgreSQL
db/init.sql            Schema (source of truth)
db/migrations/         Forward schema migrations
docs/                  Architecture diagrams + sample renders (HTML)
```

## Getting started

Prerequisites: PostgreSQL, Python 3.10+, the EBA **DPM 2.0** database and a few
Pillar 3 `xBRL-CSV` packages (see *Data* below).

```bash
cp config.example.yaml config.yaml      # then edit credentials
pip install -r requirements.txt
docker compose up -d                    # PostgreSQL (+ Prefect, Streamlit)
python migrate_dpm2_to_pg.py            # load DPM 2.0 reference dictionary
# drop Pillar 3 .zip packages into bronze/landing/ then:
python pipeline.py                      # bronze → silver → reconcile → gold
python gold_render.py 1 K_61.00         # render a disclosure to HTML
```

Automatic mode:

```bash
python watch_landing.py                 # then just drop .zip files into bronze/landing/
```

## Validation (XBRL formulas, via Arelle)

EBA defines its validation rules as **XBRL formula assertions** in the taxonomy
(the same rules also live in the DPM `operation*` tables). Instead of
re-implementing them, the pipeline runs the **real engine**:

```bash
python validate_arelle.py     # validates bronze/landing/*.zip against EBA taxonomy
```

[Arelle](https://arelle.org/) loads each xBRL-CSV report package (Load From OIM),
resolves the taxonomy (local 4.1 packages from `master_data/` + online for other
releases) and executes the formula assertions. Results land in
`xbrl_validation_run` / `xbrl_validation_result` and show in the dashboard
(Quality tab). Note: filings published by the EBA already passed validation, so
this mostly confirms "pass" — the value here is demonstrating the real
validation step end-to-end. Run on demand (loading the DTS is heavy).

Currently the local taxonomy packages cover **framework 4.1**, so 4.1 reports
validate fully (and pass — they are published filings). Reports on **4.2** are
marked `skipped` until the 4.2 taxonomy package is added (its online entry point
is not reachable; the package must be downloaded from the EBA).

*Planned (educational):* a second path that transforms the EBA rules straight
from the DPM `operation*` tables into executable checks, to compare both engines
on the same rules.

## Data & disclaimer

Uses **public** EBA Pillar 3 disclosure data and the EBA DPM 2.0 taxonomy.
Large reference data (DPM Access DB, taxonomy packages) and bank filings are
**not** included in this repo — download them from the
[EBA Data Hub](https://edap-public.eba.europa.eu/) and
[DPM Data Dictionary](https://www.eba.europa.eu/risk-and-data-analysis/reporting/dpm-data-dictionary).
This is an independent educational project, not affiliated with the EBA.

## Status

Working end-to-end: Bronze → Silver (meaning + dimensions + DQ) → Gold (render),
orchestrated (Prefect) and auto-triggered (watcher), verified 1:1 against EBA's
official template rendering. Next: cross-bank benchmarking, interactive Streamlit
dashboard, EBA validation rules.

## License

[MIT](LICENSE) © 2026 Krzysztof Burlaga
