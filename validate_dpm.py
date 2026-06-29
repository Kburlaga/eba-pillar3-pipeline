"""Etap B — walidacja regułami DPM (rules-as-data).

Reguły EBA są zdefiniowane w DPM jako dane (dpm2_ref.operationversion.Expression).
Tu PRZEPISUJEMY je na wykonywalny ewaluator (nie piszemy własnych) i uruchamiamy
na gold_cell. To druga, niezależna droga do tych samych reguł co Arelle (taksonomia).

Zakres: klasa LINIOWA wewnątrz-tabelowa:
  with {tTBL, cCOL|c*, default: 0|null, ...}: <LHS> (=|>=|<=) <RHS>
  gdzie LHS/RHS = sumy wierszy {rXXXX} (+ ewentualne stałe / zbiory {(r..,r..)}).
Reguły złożone (między-tabelowe, preconditiony, c-mieszane) — pomijane (nieobsługiwane).

Wynik: dpm_validation_run (podsumowanie) + dpm_validation_result (naruszenia).
"""
import re
import yaml
import psycopg2

SCOPE = re.compile(r"^\s*with\s*\{t(K_[0-9.]+),\s*(c\d{4}|c\*)[^}]*default:\s*(\w+)[^}]*\}:\s*(.+)$", re.S)
ROW = re.compile(r"\{?r(\d{4})\}?")


def cfg():
    return yaml.safe_load(open("config.yaml", encoding="utf-8"))["database"]


def parse_rule(vid, expr, start, end):
    """Zwróć słownik reguły liniowej albo None (gdy nieobsługiwana)."""
    m = SCOPE.match(expr.replace("\n", " "))
    if not m:
        return None
    tbl, col, deflt, body = m.groups()
    mo = re.search(r"(>=|<=|=)", body)
    if not mo:
        return None
    op, lhs, rhs = mo.group(1), body[:mo.start()], body[mo.end():]
    # tylko wiersze {rXXXX}, liczby, +/-, nawiasy — inaczej odrzuć (nie liniowa)
    leftover = re.sub(r"\{?r\d{4}\}?|[\d\s().,+\-]", "", lhs + rhs)
    if leftover.strip():
        return None
    lhs_rows = ROW.findall(lhs)
    rhs_terms = [(-1 if s == "-" else 1, r) for s, r in re.findall(r"([+\-]?)\s*\{?r(\d{4})\}?", rhs)]
    # stałe po prawej (nie należące do rNNNN)
    rhs_const = sum(float(x) for x in re.findall(r"(?<![r\d])([+\-]?\d+(?:\.\d+)?)(?!\d)", rhs))
    return dict(vid=vid, tbl=tbl, col=col, deflt=deflt, op=op,
                lhs=lhs_rows, rhs=rhs_terms, const=rhs_const, expr=expr.strip(),
                start=start, end=end)


def main():
    conn = psycopg2.connect(**{k: cfg()[k] for k in ("host", "port", "user", "password", "dbname")})
    cur = conn.cursor()

    # 1. wczytaj i sparsuj reguły liniowe K_
    cur.execute(r"""SELECT "OperationVID","Expression","StartReleaseID","EndReleaseID"
                    FROM dpm2_ref.operationversion WHERE "Expression" LIKE '%{tK\_%' ESCAPE '\' """)
    rules = [r for r in (parse_rule(*row) for row in cur.fetchall()) if r]
    print(f"Reguł liniowych DPM sparsowanych: {len(rules)}")

    # mapowanie framework -> ReleaseID
    cur.execute('SELECT "Code","ReleaseID" FROM dpm2_ref.release')
    rel = {code: rid for code, rid in cur.fetchall()}

    # raporty + ich release
    cur.execute("SELECT id, framework_version FROM bronze_report")
    reports = cur.fetchall()

    cur.execute("TRUNCATE dpm_validation_run, dpm_validation_result RESTART IDENTITY")

    for rid, fw in reports:
        R = rel.get(fw)
        # tabele obecne w gold_cell dla tego raportu
        cur.execute("SELECT DISTINCT table_code FROM gold_cell WHERE report_id=%s", (rid,))
        have = {r[0] for r in cur.fetchall()}
        # wartości tego raportu do pamięci: (table,col,row)->value_num
        cur.execute("SELECT table_code,col_code,row_code,value_num FROM gold_cell WHERE report_id=%s AND value_num IS NOT NULL", (rid,))
        val = {(t, c, r): float(v) for t, c, r, v in cur.fetchall()}
        cols_by_tbl = {}
        for (t, c, r) in val:
            cols_by_tbl.setdefault(t, set()).add(c)

        ev = passed = failed = skipped = 0
        for p in rules:
            # reguła ważna dla release raportu?
            if R is None or not (p["start"] <= R and (p["end"] is None or p["end"] > R)):
                continue
            if p["tbl"] not in have:
                continue
            cols = [p["col"][1:]] if p["col"] != "c*" else sorted(cols_by_tbl.get(p["tbl"], []))
            for col in cols:
                def v(row):
                    x = val.get((p["tbl"], col, row))
                    if x is None:
                        return 0.0 if p["deflt"] == "0" else None
                    return x
                lv = [v(r) for r in p["lhs"]]
                rv = [(s, v(r)) for s, r in p["rhs"]]
                if any(x is None for x in lv) or any(x is None for _, x in rv):
                    skipped += 1
                    continue
                L = sum(lv)
                Rr = sum(s * x for s, x in rv) + p["const"]
                tol = max(1.0, abs(Rr) * 1e-4)
                ok = (abs(L - Rr) <= tol) if p["op"] == "=" else (L >= Rr - tol if p["op"] == ">=" else L <= Rr + tol)
                ev += 1
                if ok:
                    passed += 1
                else:
                    failed += 1
                    cur.execute("""INSERT INTO dpm_validation_result
                        (report_id,operation_vid,table_code,col_code,op,lhs_val,rhs_val,expression)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (rid, p["vid"], p["tbl"], col, p["op"], L, Rr, p["expr"][:500]))
        status = "all_pass" if failed == 0 else "failures"
        cur.execute("""INSERT INTO dpm_validation_run (report_id,rules_evaluated,n_passed,n_failed,n_skipped,status)
                       VALUES (%s,%s,%s,%s,%s,%s)""", (rid, ev, passed, failed, skipped, status))
        conn.commit()
        print(f"report {rid} ({fw}): evaluated={ev} pass={passed} fail={failed} skip={skipped} -> {status}")

    cur.close(); conn.close(); print("=== Gotowe ===")


if __name__ == "__main__":
    main()
