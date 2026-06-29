"""Krzyżowa kontrola srebra vs Arelle (pkt 1).

Dla każdego raportu z bronze/landing:
  - Arelle eksportuje fakty do xBRL-JSON (saveLoadableOIM) — koncept (metryka) + wymiary + wartość,
    rozwiązane z TAKSONOMII (niezależnie od naszego mapowania DPM).
  - Porównujemy z naszym srebrem (silver_fact / silver_fact_dimension, zbudowanym z DPM):
      liczba faktów danych, multizbiór wartości numerycznych, liczba par wymiarów.
Wynik -> silver_crosscheck. Cel edukacyjny: te same fakty dwiema drogami muszą się zgadzać.
On-demand (ciężkie: ładowanie DTS ~2 min/raport).
"""
import os, sys, glob, json, subprocess, tempfile
from collections import Counter
import yaml, psycopg2

LANDING = os.path.join("bronze", "landing")
TAXO = os.path.join("master_data", "extracted", "taxo")
CORE_DIMS = {"concept", "entity", "period", "unit", "language", "noteId"}


def cfg(): return yaml.safe_load(open("config.yaml", encoding="utf-8"))["database"]
def packages(fw): return "|".join(sorted(glob.glob(os.path.join(TAXO, f"EBA_XBRL_{fw}_*.zip"))))


def export_facts(report_zip, fw, out_json):
    pkg = packages(fw)
    if not pkg:
        return False
    cmd = [sys.executable, "-m", "arelle.CntlrCmdLine", "--file", report_zip,
           "--packages", pkg, "--plugins", "loadFromOIM|saveLoadableOIM",
           "--saveLoadableOIM", out_json, "--logLevel", "error"]
    subprocess.run(cmd, capture_output=True, timeout=1200)
    return os.path.exists(out_json)


def numval(v):
    try:
        if isinstance(v, str) and v.strip().lower() in ("true", "false"):
            return None
        return round(float(v), 6)
    except (TypeError, ValueError):
        return None


def main():
    conn = psycopg2.connect(**{k: cfg()[k] for k in ("host","port","user","password","dbname")})
    cur = conn.cursor()
    cur.execute("SELECT source_file, id, framework_version FROM bronze_report")
    by_file = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
    scratch = tempfile.mkdtemp(prefix="xcheck_")

    for zp in sorted(glob.glob(os.path.join(LANDING, "*.zip"))):
        info = by_file.get(os.path.basename(zp))
        if not info:
            continue
        rid, fw = info
        out = os.path.join(scratch, f"{rid}.json")
        cur.execute("DELETE FROM silver_crosscheck WHERE report_id=%s", (rid,))
        try:
            ok = export_facts(zp, fw, out)
        except subprocess.TimeoutExpired:
            ok = False
        if not ok:
            cur.execute("INSERT INTO silver_crosscheck (report_id,status,note) VALUES (%s,'error',%s)",
                        (rid, f"Arelle nie wyeksportował faktów (fw {fw})"))
            conn.commit(); print(f"report {rid}: error (export)"); continue

        facts = json.load(open(out, encoding="utf-8"))["facts"]
        data = [f for f in facts.values() if f.get("dimensions", {}).get("concept") != "fi:filed"]
        a_num = Counter(x for x in (numval(f.get("value")) for f in data) if x is not None)
        a_dims = sum(len([k for k in f.get("dimensions", {}) if k not in CORE_DIMS]) for f in data)

        cur.execute("SELECT COUNT(*) FROM silver_fact WHERE report_id=%s", (rid,)); s_facts = cur.fetchone()[0]
        cur.execute("SELECT value_num FROM silver_fact WHERE report_id=%s AND value_num IS NOT NULL", (rid,))
        s_num = Counter(round(float(r[0]), 6) for r in cur.fetchall())
        cur.execute("SELECT COUNT(*) FROM silver_fact_dimension WHERE report_id=%s", (rid,)); s_dims = cur.fetchone()[0]

        matched = sum((a_num & s_num).values())
        only_a = sum((a_num - s_num).values())
        only_s = sum((s_num - a_num).values())
        if len(data) == s_facts and only_a == 0 and only_s == 0:
            # fakty i wartości zgodne; rozróżnij pełną zgodność od różnicy w wymiarach
            status = "match" if a_dims == s_dims else "values_match"
        else:
            status = "mismatch"
        cur.execute("""INSERT INTO silver_crosscheck
            (report_id, arelle_facts, silver_facts, values_matched, only_arelle, only_silver,
             arelle_dims, silver_dims, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (rid, len(data), s_facts, matched, only_a, only_s, a_dims, s_dims, status))
        conn.commit()
        print(f"report {rid} ({fw}): {status} | facts A/S={len(data)}/{s_facts} "
              f"values matched={matched} (A-only={only_a}, S-only={only_s}) dims A/S={a_dims}/{s_dims}")

    cur.close(); conn.close(); print("=== Gotowe ===")


if __name__ == "__main__":
    main()
