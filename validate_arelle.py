"""Walidacja XBRL przez Arelle — waliduje paczki xBRL-CSV z bronze/landing/
względem taksonomii EBA (formuły/asercje), wynik zapisuje do bazy.

Reguły EBA pochodzą z taksonomii (nie piszemy własnych). Arelle:
  - ładuje xBRL-CSV (plugin loadFromOIM)
  - rozwiązuje taksonomię: lokalne paczki (master_data/extracted/taxo, framework 4.1)
    + dociąga brakujące online z eba.europa.eu (cache)
  - --formula run uruchamia asercje walidacyjne

Wynik per raport: xbrl_validation_run (status + liczniki) + xbrl_validation_result (naruszenia).
Uruchomienie: python validate_arelle.py   (ciężkie — ładowanie DTS; on-demand, poza głównym flow)
"""
import os
import sys
import glob
import json
import subprocess
import tempfile

import yaml
import psycopg2

LANDING = os.path.join("bronze", "landing")
TAXO_DIR = os.path.join("master_data", "extracted", "taxo")
# kody oznaczające, że NIE udało się załadować taksonomii/raportu (nie da się walidować)
# -> raport oznaczamy 'skipped' (brak taksonomii), a nie jako naruszenia danych
LOAD_ERR_CODES = {"IOerror", "oime:invalidTaxonomy", "arelleOIMloader:error",
                  "FileNotLoadable", "oime:invalidJSON",
                  "webCache:retrievalError", "xbrlce:unresolvableBaseMetadataFile",
                  "xbrlce:unresolvableMetadataFile", "xbrlce:invalidTaxonomy"}


def cfg_db():
    return yaml.safe_load(open("config.yaml", encoding="utf-8"))["database"]


def packages(fw: str) -> str:
    """Paczki taksonomii TYLKO dla wersji frameworku raportu (np. 4.1 albo 4.2).
    Mieszanie wersji powoduje tpe:packageRewriteOverlap (nakładające reguły URL)."""
    pk = sorted(glob.glob(os.path.join(TAXO_DIR, f"EBA_XBRL_{fw}_*.zip")))
    return "|".join(pk)


def run_arelle(report_zip: str, log_path: str, pkg: str):
    cmd = [sys.executable, "-m", "arelle.CntlrCmdLine",
           "--file", report_zip,
           "--packages", pkg,
           "--validate", "--formula", "run",
           "--plugins", "loadFromOIM",
           "--logFile", log_path, "--logLevel", "warning"]
    subprocess.run(cmd, capture_output=True, timeout=1200)


def parse_log(log_path: str):
    if not os.path.exists(log_path):
        return [], [{"code": "noLog", "level": "error", "text": "Arelle nie zapisał logu"}]
    recs = json.load(open(log_path, encoding="utf-8")).get("log", [])
    out = []
    for r in recs:
        m = r.get("message", {})
        out.append({"code": r.get("code"), "level": r.get("level"),
                    "text": (m.get("text", "") if isinstance(m, dict) else str(m))})
    load_errs = [r for r in out if r["code"] in LOAD_ERR_CODES]
    return out, load_errs


def main():
    conn = psycopg2.connect(**{k: cfg_db()[k] for k in ("host", "port", "user", "password", "dbname")})
    cur = conn.cursor()
    # mapowanie source_file -> (report_id, framework_version)
    cur.execute("SELECT source_file, id, framework_version FROM bronze_report")
    by_file = {r[0]: (r[1], r[2]) for r in cur.fetchall()}

    zips = sorted(glob.glob(os.path.join(LANDING, "*.zip")))
    print(f"=== Walidacja XBRL (Arelle): {len(zips)} paczek ===")
    scratch = tempfile.mkdtemp(prefix="arelle_")

    for zp in zips:
        fname = os.path.basename(zp)
        info = by_file.get(fname)
        if info is None:
            print(f"POMIJAM (brak w bazie): {fname}")
            continue
        rid, fw = info
        pkg = packages(fw)
        log_path = os.path.join(scratch, f"{rid}.json")
        if not pkg:
            # brak lokalnej paczki taksonomii dla tej wersji frameworku
            cur.execute("DELETE FROM xbrl_validation_result WHERE report_id=%s", (rid,))
            cur.execute("DELETE FROM xbrl_validation_run WHERE report_id=%s", (rid,))
            cur.execute("""INSERT INTO xbrl_validation_run (report_id,status,n_errors,n_warnings,note)
                           VALUES (%s,'skipped',0,0,%s)""", (rid, f"brak paczki taksonomii {fw} w {TAXO_DIR}"))
            conn.commit()
            print(f"{fname}: skipped (brak taksonomii {fw})")
            continue
        try:
            run_arelle(zp, log_path, pkg)
            recs, load_errs = parse_log(log_path)
        except subprocess.TimeoutExpired:
            recs, load_errs = [], [{"code": "timeout", "level": "error", "text": "Arelle timeout"}]

        viol = [r for r in recs if r["level"] in ("error", "warning", "inconsistency")
                and r["code"] not in LOAD_ERR_CODES]
        n_err = sum(1 for r in viol if r["level"] == "error")
        n_warn = sum(1 for r in viol if r["level"] == "warning")

        if load_errs:
            # nie udało się rozwiązać taksonomii (np. brak paczki 4.2) — nie walidowano
            status = "skipped"
            note = "brak/niedostępna taksonomia: " + load_errs[0]["text"][:200]
            viol, n_err, n_warn = [], 0, 0   # to nie są naruszenia danych
        else:
            status, note = "validated", None

        # zapis (czyść poprzednie wyniki tego raportu)
        cur.execute("DELETE FROM xbrl_validation_result WHERE report_id=%s", (rid,))
        cur.execute("DELETE FROM xbrl_validation_run WHERE report_id=%s", (rid,))
        cur.execute("""INSERT INTO xbrl_validation_run (report_id, status, n_errors, n_warnings, note)
                       VALUES (%s,%s,%s,%s,%s)""", (rid, status, n_err, n_warn, note))
        for r in viol:
            cur.execute("""INSERT INTO xbrl_validation_result (report_id, rule_code, severity, message)
                           VALUES (%s,%s,%s,%s)""", (rid, (r["code"] or "")[:80], r["level"], r["text"]))
        conn.commit()
        print(f"{fname}: {status} (err={n_err}, warn={n_warn})" + (f" — {note[:60]}" if note else ""))

    cur.close()
    conn.close()
    print("=== Gotowe ===")


if __name__ == "__main__":
    main()
