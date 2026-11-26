"""Trang Sự kiện nâng hạng FTSE (bước B6.14) – bối cảnh nghiên cứu, trình bày cho người đọc không chuyên:
câu hỏi bằng lời thường → dòng thời gian các mốc → 27 mã chính thức → hiệu suất cộng dồn từ E1 → biểu đồ lợi suất &
dòng vốn ngoại "vượt bình thường" quanh mốc (có dải tin cậy, tách 6 mã All-World và 21 mã All-Cap) → bảng kết quả gọn có
kết luận bằng chữ → chênh lệch kép (DiD) → nhóm đối chứng → bảng kiểm định đầy đủ. Mọi phần hiện sẵn, không cần mở."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.app import data_access as da
from src.app.components import charts, status_bar
from src.app.components import widgets as W
from src.app.components.states import empty
from src.app.components.ui import esc, header, md, pal, plot, table_html
from src.common import fmt
from src.common.config import control_group, events, ftse_universe

GROUP_LBL = {"FTSE": "Nhóm FTSE (27 mã)", "CONTROL": "Nhóm đối chứng", "FTSE−CONTROL": "FTSE − đối chứng",
             "FTSE_AW": "6 mã All-World", "FTSE_SC": "21 mã All-Cap"}
EV_EXPLAIN = {"E1": "FTSE Russell công bố nâng hạng Việt Nam lên thị trường mới nổi thứ cấp.",
              "E2": "Kỳ rà soát giữa kỳ xác nhận giữ nguyên lộ trình nâng hạng.",
              "L1": "Công bố danh sách 27 mã vào rổ – lần đầu thị trường biết CỤ THỂ mã nào được chọn.",
              "L2": "Hạn chót điều chỉnh danh sách (xác nhận chính thức từ 07/09/2026).",
              "E3": "Phiên cuối trước hiệu lực – các quỹ thụ động mua vào để mô phỏng rổ mới."}


def _stats_table(df: pd.DataFrame) -> None:
    rows = []
    for r in df.itertuples():
        star = "Có" if pd.notna(r.p_value) and r.p_value < 0.05 else "—"
        est = (f"{fmt.frac_pct(r.estimate, 1)} CAR > 0" if r.test == "Dấu tổng quát"
               else fmt.num(r.estimate * (100 if r.metric == "CAR" else 1), 3, True) + ("%" if r.metric == "CAR" else ""))
        rows.append([GROUP_LBL.get(r.group, r.group), r.metric, r.window, r.test, est, fmt.num(r.statistic, 2, True),
                     fmt.num(r.p_value, 4), fmt.num(r.p_holm, 4), str(int(r.n)) if pd.notna(r.n) else "—", star])
    md(table_html(["Nhóm", "Chỉ tiêu", "Cửa sổ", "Kiểm định", "Ước lượng", "Thống kê", "p", "p Holm", "N", "p<5%"], rows,
                  left=(0, 1, 2, 3)))


def _summary(s: pd.DataFrame, hyp: str, metric: str, scale: float, unit: str) -> None:
    """Mỗi cửa sổ một dòng – FTSE, đối chứng, chênh lệch, 2 nhóm con, p Holm, kết luận bằng chữ."""
    rows = []
    for w in sorted(s["window"].dropna().unique(), key=lambda x: (len(x), x)):
        x = s[(s["hypothesis"] == hyp) & (s["metric"] == metric) & (s["window"] == w)]
        get_ = lambda g: x[(x["group"] == g) & (x["test"] == "t cắt ngang")]  # noqa: E731
        f, c, aw, sc = get_("FTSE"), get_("CONTROL"), get_("FTSE_AW"), get_("FTSE_SC")
        d = x[(x["group"] == "FTSE−CONTROL") & x["test"].astype(str).str.startswith("Welch")]
        if f.empty or c.empty:
            continue
        ph = d["p_holm"].iloc[0] if not d.empty and pd.notna(d["p_holm"].iloc[0]) else (d["p_value"].iloc[0] if not d.empty else float("nan"))
        verdict = ("Có khác biệt có ý nghĩa" if pd.notna(ph) and ph < 0.05 else
                   "Khác biệt yếu (p < 0,10)" if pd.notna(ph) and ph < 0.10 else "Không có bằng chứng bất thường")
        g = lambda df: fmt.num(df["estimate"].iloc[0] * scale, 2, True) + unit if not df.empty else "—"  # noqa: E731
        rows.append([f"{w} phiên", g(f), g(c), g(d), g(aw), g(sc), fmt.num(ph, 3), verdict])
    if rows:
        md(table_html(["Cửa sổ quanh mốc", "Nhóm FTSE", "Đối chứng", "Chênh lệch", "6 mã All-World", "21 mã All-Cap",
                       "p Holm", "Kết luận"], rows, left=(0, 7)))
    else:
        empty("Chưa có kết quả cho mốc này.")


def _timeline(ev: pd.DataFrame) -> None:
    items = "".join(
        f'<div class="ft-ev"><b>{r.event_id}</b><span>{r.event_date:%d/%m/%Y}</span><em>{esc(r.label)}</em>'
        f'<small>{esc(EV_EXPLAIN.get(r.event_id, ""))}</small></div>' for r in ev.sort_values("event_date").itertuples())
    md('<style>.ft-tl{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px;margin:4px 0 6px}'
       '.ft-ev{border:1px solid var(--ffr-border);border-radius:12px;padding:12px 16px;'
       'background:var(--ffr-card);display:flex;flex-direction:column;gap:2px}.ft-ev b{color:var(--ffr-accent);font-size:15px;font-weight:600}'
       '.ft-ev span{font-weight:600;font-size:14px}.ft-ev em{font-style:normal;font-size:14px}.ft-ev small{color:var(--ffr-muted);font-size:13px;'
       'line-height:1.4}</style>' + f'<div class="ft-tl">{items}</div>')


def _universe() -> None:
    fu = ftse_universe()
    if fu.empty or "size_class" not in fu:
        return
    rows = []
    for cls, lbl in (("Large", "Vốn hóa lớn – vào cả All-World"), ("Mid", "Vốn hóa vừa – vào cả All-World"),
                     ("Small", "Vốn hóa nhỏ – chỉ vào All-Cap")):
        sy = fu[fu["size_class"] == cls]["symbol"].tolist()
        if sy:
            rows.append([f"<b>{lbl}</b>", str(len(sy)), " · ".join(f'<span class="ffr-sym">{s}</span>' for s in sy)])
    md(table_html(["Nhóm", "Số mã", "Mã cổ phiếu"], rows, left=(0, 2)))
    st.caption("Nguồn: FTSE Russell công bố ngày 21/08/2026; đối chiếu Dragon Capital và Vietstock. Nhóm All-World có dòng tiền "
               "quỹ thụ động lớn hơn nhiều, nên được tách riêng khi phân tích.")


def _cum_groups(p) -> None:
    g = da.groups(None, "universe")
    if g.empty:
        return
    e1 = events().set_index("event_id").loc["E1", "event_date"]
    g = g[pd.to_datetime(g["trade_date"]) >= e1].copy()
    fig = go.Figure()
    for k, lbl, col, w in (("FTSE", "Nhóm FTSE (27 mã)", p["accent"], 2.4), ("CONTROL", "Nhóm đối chứng", "#94A3B8", 1.6),
                           ("VN30", "VN30", "#818CF8", 1.2)):
        x = g[g["group_name"] == k].sort_values("trade_date")
        if x.empty:
            continue
        cum = ((1 + x["ret_eq"].fillna(0)).cumprod() - 1) * 100
        fig.add_scatter(x=x["trade_date"], y=cum, name=f"{lbl} ({fmt.pct(cum.iloc[-1], 1)})", line=dict(color=col, width=w))
    for r in events().itertuples():
        if r.event_date >= e1:
            fig.add_vline(x=r.event_date, line=dict(color=p["muted"], width=1, dash="dot"))
            fig.add_annotation(x=r.event_date, y=1, yref="paper", text=r.event_id, showarrow=False, font=dict(color=p["muted"], size=12),
                               yanchor="bottom")
    fig.add_hline(y=0, line=dict(color=p["muted"], width=1))
    plot(charts._lay(fig, p, 360, hovermode="x unified", legend=dict(orientation="h", y=-0.15, x=0),
                     margin=dict(l=8, r=8, t=24, b=8), yaxis_title="Lợi suất cộng dồn (%)"), "p4_cum")


def render() -> None:
    header("Sự kiện nâng hạng FTSE", "27 mã vào rổ FTSE có tăng giá hoặc được khối ngoại mua nhiều hơn bình thường không?")
    status_bar.render()
    p = pal()
    ev = events().sort_values("event_date")
    st.caption("So 27 mã được chọn vào rổ FTSE với nhóm đối chứng có quy mô tương tự. \"Lợi suất vượt dự kiến\" = lợi suất thực tế − "
               "mức dự kiến theo VN-Index (ước lượng từ các phiên trước mốc). Kết quả mô tả, không khẳng định nhân quả.")
    aar = da.table("event_aar")
    stats = da.table("stats_results")
    t1, t2, t3, t4 = st.tabs(["Tổng quan sự kiện", "Biến động quanh các mốc", "So với nhóm đối chứng", "Bảng kiểm định"])

    with t1:
        with W.card("p4_tl"):
            W.title("Dòng thời gian nâng hạng", "5 mốc dùng trong phân tích")
            _timeline(ev)
        with W.card("p4_cumc"):
            W.title("Hiệu suất cộng dồn từ khi công bố nâng hạng (E1)", "Lợi suất bình quân đồng trọng số · nhóm FTSE so với đối chứng và VN30")
            _cum_groups(p)
        with W.card("p4_uni"):
            W.title("27 mã vào rổ FTSE (danh sách chính thức)", "FTSE All-Cap; 6 mã đồng thời vào FTSE All-World")
            _universe()

    if aar.empty:
        with t2:
            empty("Chưa có kết quả nghiên cứu sự kiện – chạy `python -m src.data.rebuild_all`.")
        return
    have = [e for e in ev["event_id"] if e in set(aar["event_id"])]
    default = "L1" if "L1" in have else (have[-1] if have else None)
    with t2:
        eid = st.segmented_control("Chọn mốc sự kiện", have, default=default, key="p4_ev",
                                   format_func=lambda e: f"{e} · {ev.set_index('event_id').loc[e, 'label']} "
                                                         f"({ev.set_index('event_id').loc[e, 'event_date']:%d/%m/%Y})") or default
        a = aar[(aar["event_id"] == eid) & (aar["variant"] == "base")]
        st.caption(f"{eid}: {EV_EXPLAIN.get(eid, ev.set_index('event_id').loc[eid, 'description'])}")
        c1, c2 = st.columns(2, gap="small")
        with c1, W.card("p4_caar"):
            W.title("Lợi suất vượt dự kiến, cộng dồn quanh mốc (%)",
                    "Trục ngang: số phiên trước (−) / sau (+) mốc · dải mờ = khoảng tin cậy 95% · nét chấm = 2 nhóm con")
            plot(charts.caar_chart(a, p, "CAAR"), "p4_caar_fig")
        with c2, W.card("p4_caff"):
            W.title("Khối ngoại mua ròng vượt bình thường, cộng dồn",
                    "nf (ròng / GTGD) so với mức bình quân trước mốc · dương = khối ngoại mua nhiều hơn thường lệ")
            plot(charts.caar_chart(a, p, "CAFF"), "p4_caff_fig")
        s = stats[(stats["event_id"] == eid) & (stats["variant"] == "base")]
        with W.card("p4_s1"):
            W.title("Kết quả: lợi suất vượt dự kiến (CAR)", "Trung bình nhóm trong từng cửa sổ · p hiệu chỉnh Holm cho chênh lệch FTSE − đối chứng")
            _summary(s, "H3a", "CAR", 100, "%")
        with W.card("p4_s2"):
            W.title("Kết quả: khối ngoại mua ròng vượt bình thường (CAFF)", "Cùng cách đọc · đơn vị: nf cộng dồn")
            _summary(s, "H3b", "CAFF", 1, "")

    with t3:
        with W.card("p4_did"):
            W.title("Chênh lệch kép (DiD) quanh phiên điều chỉnh rổ E3",
                    "So thay đổi trước/sau E3 của nhóm FTSE với nhóm đối chứng · hệ số trước E3 ≈ 0 → giả định xu hướng song song hợp lý")
            did = stats[(stats["hypothesis"] == "H3c") & (stats["variant"] == "base")]
            if did.empty:
                empty("Chưa đủ dữ liệu cửa sổ quanh E3.")
            else:
                rows = [[r.metric, r.model, r.test, fmt.num(r.estimate, 4, True), fmt.num(r.statistic, 2, True), fmt.num(r.p_value, 4),
                         f"[{fmt.num(r.ci_lo, 4)}; {fmt.num(r.ci_hi, 4)}]", str(int(r.n)) if pd.notna(r.n) else "—", r.note or ""]
                        for r in did.itertuples()]
                md(table_html(["Biến kết quả", "Mô hình", "Kiểm định", "δ (tác động)", "t", "p", "KTC 95%", "N", "Ghi chú"], rows,
                              left=(0, 1, 2, 8)))
                coefs = da.table("did_coefs")
                if not coefs.empty:
                    outcome = st.radio("Biến kết quả", coefs["outcome"].unique().tolist(), horizontal=True, key="p4_did")
                    plot(charts.did_coef_chart(coefs, p, outcome), "p4_didc")
                st.caption("Chỉ có 27 cặp mã nên sai số cụm kém tin cậy.")
        c1, c2 = st.columns([1.3, 1], gap="small")
        with c1, W.card("p4_cg"):
            W.title("Nhóm đối chứng", "Mỗi mã FTSE ghép 1 mã không vào rổ có vốn hóa và thanh khoản gần nhất (120 phiên trước E1)")
            cg = control_group()
            if not cg.empty:
                md(table_html(["Mã FTSE", "Đối chứng", "Khoảng cách", "Đối chứng phương án 2 (thanh khoản)"],
                              [[f'<span class="ffr-sym">{r.ftse_symbol}</span>', r.control_symbol, fmt.num(float(r.distance), 3),
                                r.control_symbol_liq] for r in cg.itertuples()], left=(0, 1, 3)))
        with c2, W.card("p4_bal"):
            W.title("Hai nhóm có cân bằng không?", "Trung vị vốn hóa/thanh khoản trước E1 · p > 0,05 = không khác biệt (ghép tốt)")
            bal = da.table("control_balance")
            if not bal.empty:
                md(table_html(["Biến", "Trung vị FTSE", "Trung vị đối chứng", "Mann–Whitney p"],
                              [[r.variable, fmt.num(r.median_ftse, 3), fmt.num(r.median_control, 3), fmt.num(r.mw_p, 3)]
                               for r in bal.itertuples()], left=(0,)))
            st.caption("Giới hạn: mẫu nhỏ (27 mã) nên độ mạnh thống kê hạn chế; các mốc trùng biến động vĩ mô; kết quả mô tả, "
                       "không khẳng định nhân quả. Mã có tỷ trọng ≥ 3% dùng VN-Index loại trừ chính mã làm lợi suất thị trường.")

    with t4:
        with W.card("p4_full"):
            W.title("Bảng kiểm định đầy đủ", f"Mốc {eid} (đổi ở tab Biến động quanh các mốc) · t, BMP, BMP hiệu chỉnh Kolari–Pynnönen, dấu, "
                                             "Welch, Mann–Whitney · p Holm")
            s = stats[(stats["event_id"] == eid) & (stats["variant"] == "base")]
            _stats_table(s[s["hypothesis"].isin(["H3a", "H3b"])].sort_values(["hypothesis", "metric", "window", "group", "test"]))
