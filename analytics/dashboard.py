"""EBA Pillar 3 — dashboard (Streamlit) na warstwie złota.

Uruchomienie (na komputerze, w katalogu repo):  streamlit run analytics/dashboard.py
Źródło danych: gold_cell (prezentacja) + bronze_report + bank + silver_reconciliation.
"""
import os
import yaml
import psycopg2
import pandas as pd
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="EBA Pillar 3", layout="wide")

# ── połączenie + zapytania (cache, żeby nie łączyć się przy każdej interakcji) ──
def _cfg():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, "config.yaml")
    if not os.path.exists(path):
        path = "config.yaml"
    return yaml.safe_load(open(path, encoding="utf-8"))["database"]


@st.cache_resource
def get_conn():
    d = _cfg()
    c = psycopg2.connect(host=d["host"], port=d["port"], user=d["user"],
                         password=d["password"], dbname=d["dbname"])
    c.autocommit = True
    return c


@st.cache_data(ttl=120)
def q(sql, params=None):
    return pd.read_sql(sql, get_conn(), params=params)


def fmt(dt, vnum, vtext):
    """Formatowanie wartości wg typu danych DPM (m=kwota, p=procent, i/r=liczby)."""
    if vnum is None or pd.isna(vnum):
        return (vtext or "").strip()
    if dt == "p":
        return f"{vnum * 100:.2f}%"
    if dt == "m":
        return f"{vnum:,.0f}"
    if dt == "i":
        return f"{int(vnum):,}"
    if dt == "r":
        return f"{vnum:,.4f}".rstrip("0").rstrip(".")
    return str(vnum)


st.title("🏦 EBA Pillar 3 — przeglądarka ujawnień")
st.caption("Dane z pipeline'u brąz→srebro→złoto · źródło: EBA Pillar 3 Data Hub")

try:
    reports = q("""
        SELECT br.id, COALESCE(b.nazwa, br.lei) AS bank, br.country, br.ref_period,
               br.framework_version, br.is_current, br.lei, br.report_generated, br.version_no
        FROM bronze_report br LEFT JOIN bank b ON b.lei = br.lei
        ORDER BY bank, br.ref_period DESC
    """)
except Exception as e:
    st.error(f"Brak połączenia z bazą: {e}")
    st.stop()

if reports.empty:
    st.warning("Brak raportów w bazie. Uruchom pipeline (python pipeline.py).")
    st.stop()

st.sidebar.header("Wybór")
reports["okres"] = reports["ref_period"].astype(str)

# numer WERSJI czytany z bazy (bronze_report.version_no — liczony w bronze_ingest)
reports["wersja"] = reports["version_no"]
reports["n_wersji"] = reports.groupby(["lei", "okres"])["id"].transform("count")
reports["data_przekazania"] = reports["report_generated"].astype(str).str.slice(0, 10)

# dwa filtry KASKADOWE: opcje Okresu zależą od Banku i odwrotnie
banks_all = sorted(reports["bank"].unique())
okresy_all = sorted(reports["okres"].unique(), reverse=True)

# opcje Banku zależą od aktualnie wybranego Okresu (z sesji)
sel_okres = st.session_state.get("f_okres", "(wszystkie)")
bank_opts = ["(wszystkie)"] + (sorted(reports[reports["okres"] == sel_okres]["bank"].unique())
                               if sel_okres != "(wszystkie)" else banks_all)
if st.session_state.get("f_bank") not in bank_opts:      # zresetuj, jeśli stara wartość już niedostępna
    st.session_state["f_bank"] = "(wszystkie)"
f_bank = st.sidebar.selectbox("Bank", bank_opts, key="f_bank")

# opcje Okresu zależą od wybranego Banku
okres_opts = ["(wszystkie)"] + (sorted(reports[reports["bank"] == f_bank]["okres"].unique(), reverse=True)
                                if f_bank != "(wszystkie)" else okresy_all)
if st.session_state.get("f_okres") not in okres_opts:
    st.session_state["f_okres"] = "(wszystkie)"
f_okres = st.sidebar.selectbox("Okres", okres_opts, key="f_okres")

flt = reports.copy()
if f_bank != "(wszystkie)":
    flt = flt[flt["bank"] == f_bank]
if f_okres != "(wszystkie)":
    flt = flt[flt["okres"] == f_okres]

if flt.empty:
    st.sidebar.warning("Brak sprawozdań dla tej kombinacji.")
    st.warning("Ten bank nie złożył sprawozdania w tym okresie. Zmień filtr.")
    st.stop()

# selektor WERSJI sprawozdania (mapowanie po id — etykiety mogą się powtarzać)
flt = flt.sort_values(["bank", "okres", "wersja"])
both = (f_bank != "(wszystkie)") and (f_okres != "(wszystkie)")

def _opt_label(i):
    r = flt[flt["id"] == i].iloc[0]
    ver = f"v{r['wersja']}/{r['n_wersji']}"
    sub = f" · przekazano {r['data_przekazania']}" if r["data_przekazania"] and r["data_przekazania"] != "NaT" else ""
    cur = " ✓ aktualna" if r["is_current"] else ""
    # gdy wybrany konkretny bank+okres → sama wersja; inaczej dołóż bank·okres
    head = "" if both else f"{r['bank']} · {r['okres']} · "
    return f"{head}{ver}{sub}{cur}"

etk = "Wersja" if both else "Sprawozdanie"
sel_id = st.sidebar.selectbox(f"{etk} ({len(flt)})", flt["id"].tolist(), format_func=_opt_label)
rep = reports[reports["id"] == sel_id].iloc[0]
rid = int(rep["id"])

templates = q("SELECT DISTINCT table_code FROM gold_cell WHERE report_id=%(r)s ORDER BY table_code",
              {"r": rid})
tlist = templates["table_code"].tolist()
tbl = st.sidebar.selectbox("Szablon", tlist,
                           index=tlist.index("K_61.00") if "K_61.00" in tlist else 0)

tab1, tab2, tab3, tab4 = st.tabs(["📋 Ujawnienie", "🗂 Przegląd", "📊 Porównanie", "✅ Jakość"])

# ── TAB 1: odtworzone ujawnienie (pivot wiersze × kolumny) ──
with tab1:
    st.subheader(f"{tbl} — {rep['bank']} ({rep['ref_period']})")
    cells = q("""
        SELECT row_code, row_label, col_code, col_label, data_type, value_num, value_text
        FROM gold_cell WHERE report_id=%(r)s AND table_code=%(t)s
    """, {"r": rid, "t": tbl})
    if cells.empty:
        st.info("Brak komórek dla tego szablonu.")
    else:
        cells["val"] = cells.apply(lambda x: fmt(x["data_type"], x["value_num"], x["value_text"]), axis=1)
        cells["wiersz"] = cells["row_label"].fillna(cells["row_code"])
        cells["kolumna"] = cells["col_label"].fillna(cells["col_code"])
        row_order = cells.sort_values("row_code")["wiersz"].drop_duplicates().tolist()
        col_order = cells.sort_values("col_code")["kolumna"].drop_duplicates().tolist()
        piv = cells.pivot_table(index="wiersz", columns="kolumna", values="val", aggfunc="first")
        piv = piv.reindex(index=row_order, columns=col_order)
        st.dataframe(piv.fillna(""), use_container_width=True, height=600)
        st.caption("Kwoty (m) w EUR · procenty (p) ×100% · puste = nie zaraportowano.")

# ── TAB 2: przegląd wszystkich raportów ──
with tab2:
    st.subheader("Wczytane raporty")
    view = reports[["bank", "country", "ref_period", "framework_version", "is_current", "lei"]].copy()
    view.columns = ["Bank", "Kraj", "Okres", "Framework", "Aktualny", "LEI"]
    st.dataframe(view, use_container_width=True, hide_index=True)
    c1, c2, c3 = st.columns(3)
    c1.metric("Raportów", len(reports))
    c2.metric("Banków", reports["bank"].nunique())
    c3.metric("Aktualnych", int(reports["is_current"].sum()))

# ── TAB 3: porównanie wskaźnika między bankami ──
with tab3:
    st.subheader("Porównanie wskaźnika między bankami")
    st.caption("Aktualne wersje raportów (is_current), na jedną datę referencyjną — jeden raport na bank.")
    # 1. okres referencyjny (kluczowy filtr — bez niego mieszają się kwartały)
    periods = q("SELECT DISTINCT ref_period FROM bronze_report WHERE is_current ORDER BY ref_period DESC")["ref_period"].astype(str).tolist()
    period = st.selectbox("Okres referencyjny", periods, key="cmp_period")
    # 2. szablon — tylko te obecne dla wybranego okresu
    all_tbl = q("""SELECT DISTINCT gc.table_code FROM gold_cell gc
                   JOIN bronze_report br ON br.id=gc.report_id AND br.is_current
                   WHERE br.ref_period=%(p)s ORDER BY gc.table_code""", {"p": period})["table_code"].tolist()
    if not all_tbl:
        st.info("Brak danych dla tego okresu.")
    else:
        ctbl = st.selectbox("Szablon", all_tbl,
                            index=all_tbl.index("K_61.00") if "K_61.00" in all_tbl else 0, key="cmp_tbl")
        rows = q("""SELECT DISTINCT row_code, row_label FROM gold_cell
                    WHERE table_code=%(t)s AND row_label IS NOT NULL ORDER BY row_code""", {"t": ctbl})
        row_lbl = st.selectbox("Pozycja (wiersz)", rows["row_label"])
        rcode = rows[rows["row_label"] == row_lbl].iloc[0]["row_code"]
        cols = q("""SELECT DISTINCT col_code, col_label FROM gold_cell
                    WHERE table_code=%(t)s ORDER BY col_code""", {"t": ctbl})
        col_lbl = st.selectbox("Kolumna", cols["col_label"], help="a. T = data referencyjna raportu")
        ccode = cols[cols["col_label"] == col_lbl].iloc[0]["col_code"]
        # 3. jeden wiersz na bank: is_current + wybrany okres
        data = q("""
            SELECT COALESCE(b.nazwa, br.lei) AS bank, gc.data_type, gc.value_num
            FROM gold_cell gc
            JOIN bronze_report br ON br.id = gc.report_id AND br.is_current AND br.ref_period=%(p)s
            LEFT JOIN bank b ON b.lei = br.lei
            WHERE gc.table_code=%(t)s AND gc.row_code=%(r)s AND gc.col_code=%(c)s
              AND gc.value_num IS NOT NULL
        """, {"p": period, "t": ctbl, "r": rcode, "c": ccode})
        if data.empty:
            st.info("Brak danych liczbowych dla tego przekroju.")
        else:
            dt = data["data_type"].iloc[0]
            data["wartość"] = data["value_num"] * (100 if dt == "p" else 1)
            unit = "%" if dt == "p" else ("EUR" if dt == "m" else "")
            fig = px.bar(data.sort_values("wartość", ascending=False),
                         x="bank", y="wartość", text_auto=".2f",
                         title=f"{row_lbl} [{col_lbl}] · {period} ({unit})")
            fig.update_layout(xaxis_title="", yaxis_title=unit)
            st.plotly_chart(fig, use_container_width=True)

# ── TAB 4: jakość danych (rekoncyliacja) ──
with tab4:
    st.subheader("Jakość — rekoncyliacja fakt ↔ komórka")
    recon = q("""
        SELECT COALESCE(b.nazwa, br.lei) AS bank, sr.table_code,
               sr.facts_total, sr.facts_mapped, sr.facts_orphan
        FROM silver_reconciliation sr
        JOIN bronze_report br ON br.id = sr.report_id
        LEFT JOIN bank b ON b.lei = br.lei
        WHERE sr.facts_orphan > 0
        ORDER BY sr.facts_orphan DESC
    """)
    tot = q("SELECT SUM(facts_total) t, SUM(facts_mapped) m, SUM(facts_orphan) o FROM silver_reconciliation")
    c1, c2, c3 = st.columns(3)
    c1.metric("Faktów (złoto)", int(tot["t"].iloc[0] or 0))
    c2.metric("Z komórką", int(tot["m"].iloc[0] or 0))
    c3.metric("Sieroty", int(tot["o"].iloc[0] or 0))
    if recon.empty:
        st.success("Brak sierot — każdy fakt ma miejsce w definicji szablonu.")
    else:
        st.warning("Fakty bez komórki w układzie szablonu (do zbadania):")
        recon.columns = ["Bank", "Szablon", "Faktów", "Z komórką", "Sierot"]
        st.dataframe(recon, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Walidacja XBRL (Arelle) — reguły EBA z taksonomii")
    runs = q("""
        SELECT COALESCE(b.nazwa, br.lei) AS bank, br.ref_period::text AS okres,
               br.framework_version AS fw, r.status, r.n_errors, r.n_warnings, r.note
        FROM xbrl_validation_run r
        JOIN bronze_report br ON br.id = r.report_id
        LEFT JOIN bank b ON b.lei = br.lei
        ORDER BY bank, okres
    """)
    if runs.empty:
        st.info("Brak wyników walidacji XBRL. Uruchom: `python validate_arelle.py`")
    else:
        runs.columns = ["Bank", "Okres", "Framework", "Status", "Błędy", "Ostrzeżenia", "Uwaga"]
        st.dataframe(runs, use_container_width=True, hide_index=True)
        st.markdown(f"**Naruszenia dla wybranego raportu** — {rep['bank']} · {rep['okres']}:")
        viol = q("""SELECT rule_code AS "Reguła", severity AS "Severity", message AS "Komunikat"
                    FROM xbrl_validation_result WHERE report_id=%(r)s ORDER BY severity""", {"r": rid})
        if viol.empty:
            st.success("Brak naruszeń — raport zgodny z regułami EBA (lub nie był walidowany).")
        else:
            st.dataframe(viol, use_container_width=True, hide_index=True)
