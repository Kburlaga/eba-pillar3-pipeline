"""Złoto/render — odtwórz ujawnienie (szablon z wartościami) jako HTML z gold_cell.

Użycie: python gold_render.py [report_id] [table_code]   (domyślnie 2  K_61.00 = KM1 Deutsche)
Pivot: wiersze = pozycje (row_label), kolumny = okresy (col_label), wartości w komórkach.
Formatowanie wg data_type: m=kwota (separatory), p=procent (x100 %), i=liczba całk., r=dziesiętna.
"""
import sys
import yaml
import psycopg2


def fmt(dt, vtext, vnum):
    if vnum is None:
        return (vtext or "").strip()
    if dt == "p":
        return f"{vnum * 100:.2f}%"
    if dt == "m":
        return f"{vnum:,.0f}"            # kwota: separatory tysięcy
    if dt == "i":
        return f"{int(vnum):,}"
    if dt == "r":
        return f"{vnum:,.4f}".rstrip("0").rstrip(".")
    return str(vnum)


def main():
    report_id = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    table_code = sys.argv[2] if len(sys.argv) > 2 else "K_61.00"

    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))["database"]
    conn = psycopg2.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                            password=cfg["password"], dbname=cfg["dbname"])
    cur = conn.cursor()

    # nagłówek: bank (nazwa z master po LEI) + okres + framework
    cur.execute("""SELECT br.lei, COALESCE(b.nazwa, br.lei) AS nazwa, br.country, br.ref_period, br.framework_version
                   FROM bronze_report br LEFT JOIN bank b ON b.lei = br.lei WHERE br.id=%s""", (report_id,))
    lei, nazwa, country, period, fw = cur.fetchone()

    cur.execute("""
        SELECT row_code, row_label, col_code, col_label, data_type, value_text, value_num
        FROM gold_cell WHERE report_id=%s AND table_code=%s
    """, (report_id, table_code))
    rows_data = cur.fetchall()
    cur.close(); conn.close()

    # zbierz osie
    cols = {}   # col_code -> col_label
    rows = {}   # row_code -> row_label
    cells = {}  # (row_code,col_code) -> (dt,vtext,vnum)
    for rc, rl, cc, cl, dt, vt, vn in rows_data:
        cols[cc] = cl or cc
        rows[rc] = rl or rc
        cells[(rc, cc)] = (dt, vt, vn)
    col_codes = sorted(cols)
    row_codes = sorted(rows)

    # HTML
    th = "".join(f'<th>{cols[c]}<div class="code">c{c}</div></th>' for c in col_codes)
    body = []
    for rc in row_codes:
        tds = []
        for cc in col_codes:
            v = cells.get((rc, cc))
            tds.append(f'<td class="num">{fmt(*v)}</td>' if v else '<td class="empty"></td>')
        body.append(f'<tr><th class="rh">{rows[rc]}<div class="code">r{rc}</div></th>{"".join(tds)}</tr>')

    html = f"""<!DOCTYPE html><html lang="pl"><head><meta charset="utf-8">
<title>{table_code} — {lei}</title>
<style>
 body{{font-family:"Segoe UI",Tahoma,sans-serif;background:#eef1f6;margin:0;padding:24px;}}
 h1{{font-size:17px;color:#1f3864;margin:0 0 2px;}}
 p.sub{{color:#555;margin:0 0 16px;font-size:13px;}}
 table{{border-collapse:collapse;background:#fff;font-size:12.5px;box-shadow:0 1px 4px #0002;}}
 th,td{{border:1px solid #cdd6e6;padding:5px 9px;}}
 thead th{{background:#4472C4;color:#fff;font-weight:600;text-align:center;vertical-align:bottom;}}
 th.rh{{background:#eef3fc;text-align:left;font-weight:500;max-width:380px;color:#222;}}
 td.num{{text-align:right;font-variant-numeric:tabular-nums;}}
 td.empty{{background:#fafbfd;}}
 .code{{font-size:9px;color:#90a0bf;font-weight:400;}}
 thead th .code{{color:#cdd9f5;}}
 .corner{{background:#1f3864;}}
</style></head><body>
<h1>{table_code} — {nazwa}</h1>
<p class="sub">{nazwa} · LEI {lei} · kraj {country} · okres {period} · framework {fw} · render z gold_cell</p>
<table><thead><tr><th class="corner"></th>{th}</tr></thead>
<tbody>{"".join(body)}</tbody></table>
<p class="sub" style="margin-top:14px">Kwoty (m) w EUR z separatorami · procenty (p) ×100% · puste = nie zaraportowano.
Komórki bez stałej etykiety wiersza pokazują kod (rXXXX) — wiersze otwarte.</p>
</body></html>"""

    out = f"docs/render_{table_code.replace('.','_').lower()}_{report_id}.html"
    open(out, "w", encoding="utf-8").write(html)
    print(f"OK: {out}  (wierszy={len(row_codes)}, kolumn={len(col_codes)}, komórek={len(cells)})")


if __name__ == "__main__":
    main()
