"""Trang 4 – Sự kiện FTSE (bước B6.14): CAAR và CAFF theo ngày sự kiện cho hai nhóm có dải tin cậy;
bảng kiểm định; đồ thị hệ số DiD; cân bằng nhóm đối chứng; ghi chú giới hạn."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.app import data_access as da
from src.app.components import charts, status_bar
from src.app.components.states import empty
from src.app.components.ui import header, md, pal, plot, section, table_html
from src.common import fmt
from src.common.config import control_group, events, ftse_universe, is_demo


def _stats_table(df: pd.DataFrame) -> None:
    rows = []
    for r in df.itertuples():
        star = "✅" if pd.notna(r.p_value) and r.p_value < 0.05 else ""
        est = (f"{fmt.frac_pct(r.estimate, 1)} CAR > 0" if r.test == "Dấu tổng quát"
               else fmt.num(r.estimate * (100 if r.metric == "CAR" else 1), 3, True) + ("%" if r.metric == "CAR" else ""))
        rows.append([r.group, r.window, r.test, est, fmt.num(r.statistic, 2, True), fmt.num(r.p_value, 4),
                     fmt.num(r.p_holm, 4), str(int(r.n)) if pd.notna(r.n) else "—", star])
    md(table_html(["Nhóm", "Cửa sổ", "Kiểm định", "Ước lượng", "Thống kê", "p", "p Holm", "N", "p<5%"], rows, left=(0, 1, 2)))


def render() -> None:
    header("Sự kiện FTSE", "Nhóm cổ phiếu vào rổ có lợi suất và dòng vốn ngoại bất thường so với nhóm đối chứng không?")
    status_bar.render()
    p = pal()
    ev = events()
    fu = ftse_universe()
    if not fu.empty and not fu["verified"].astype(str).str.lower().eq("true").all():
        st.warning("Danh sách FTSE trong config/ftse_universe.csv đang là DỰ KIẾN (verified = false) – cần đối chiếu thông báo "
                   "chính thức của FTSE Russell trước khi diễn giải kết quả." + (" Kết quả hiện chạy trên dữ liệu MẪU." if is_demo() else ""))
    eid = st.segmented_control("Mốc sự kiện", ev["event_id"].tolist(), default="E3", key="p4_ev",
                               format_func=lambda e: f"{e} · {ev.set_index('event_id').loc[e, 'label']} "
                                                     f"({ev.set_index('event_id').loc[e, 'event_date']:%d/%m/%Y})") or "E3"
    e = ev.set_index("event_id").loc[eid]
    st.caption(e["description"])
    aar = da.table("event_aar")
    if aar.empty:
        empty("Chưa có kết quả nghiên cứu sự kiện – chạy `python -m src.data.rebuild_all`.")
        return
    aar = aar[(aar["event_id"] == eid) & (aar["variant"] == "base")]
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        section("CAAR (%)", "Mô hình thị trường, ước lượng [−130; −11] · dải 95%")
        plot(charts.caar_chart(aar, p, "CAAR"), "p4_caar")
    with c2:
        section("CAFF – dòng vốn ngoại bất thường lũy kế", "AFF = nf − trung bình nf cửa sổ ước lượng")
        plot(charts.caar_chart(aar, p, "CAFF"), "p4_caff")
    stats = da.table("stats_results")
    s = stats[(stats["event_id"] == eid) & (stats["variant"] == "base")]
    t1, t2, t3 = st.tabs(["H3a · Lợi suất bất thường (CAR)", "H3b · Dòng vốn & thanh khoản bất thường", "H3c · Chênh lệch kép (E3)"])
    with t1:
        _stats_table(s[(s["hypothesis"] == "H3a")].sort_values(["window", "group", "test"]))
    with t2:
        metric = st.radio("Chỉ tiêu", ["CAFF", "CAVol"], horizontal=True, key="p4_m",
                          format_func=lambda m: {"CAFF": "Dòng vốn ngoại (CAFF)", "CAVol": "Thanh khoản (ln TV)"}[m])
        _stats_table(s[(s["hypothesis"] == "H3b") & (s["metric"] == metric)].sort_values(["window", "group", "test"]))
    with t3:
        did = stats[(stats["hypothesis"] == "H3c") & (stats["variant"] == "base")]
        if did.empty:
            empty("Chưa đủ dữ liệu cửa sổ [−60; +60] quanh E3.")
        else:
            rows = [[r.metric, r.model, r.test, fmt.num(r.estimate, 4, True), fmt.num(r.statistic, 2, True), fmt.num(r.p_value, 4),
                     f"[{fmt.num(r.ci_lo, 4)}; {fmt.num(r.ci_hi, 4)}]", str(int(r.n)) if pd.notna(r.n) else "—", r.note or ""]
                    for r in did.itertuples()]
            md(table_html(["y", "Mô hình", "Kiểm định", "δ", "t", "p", "KTC 95%", "N", "Ghi chú"], rows, left=(0, 1, 2, 8)))
            coefs = da.table("did_coefs")
            if not coefs.empty:
                outcome = st.radio("Biến kết quả", coefs["outcome"].unique().tolist(), horizontal=True, key="p4_did")
                plot(charts.did_coef_chart(coefs, p, outcome), "p4_didc")
            st.caption("Sau E3 hiện có ít phiên hơn cửa sổ +60 dự kiến; hệ số trước sự kiện ≈ 0 ủng hộ giả định xu hướng song song.")
    section("Nhóm đối chứng", "Ghép 1–1 theo phân vị vốn hóa và thanh khoản 120 phiên trước E1, láng giềng gần nhất không hoàn lại")
    bal = da.table("control_balance")
    cg = control_group()
    c1, c2 = st.columns([1.4, 1])
    with c1:
        if not cg.empty:
            md(table_html(["Mã FTSE", "Đối chứng", "Khoảng cách", "Đối chứng PA2 (thanh khoản)"],
                          [[r.ftse_symbol, r.control_symbol, fmt.num(float(r.distance), 3), r.control_symbol_liq] for r in cg.head(30).itertuples()],
                          left=(0, 1, 3)))
    with c2:
        if not bal.empty:
            md(table_html(["Biến", "Trung vị FTSE", "Trung vị đối chứng", "Mann–Whitney p"],
                          [[r.variable, fmt.num(r.median_ftse, 3), fmt.num(r.median_control, 3), fmt.num(r.mw_p, 3)] for r in bal.itertuples()],
                          left=(0,)))
        md('<div class="ffr-insight" style="margin-top:10px"><b>Giới hạn</b><br>Mẫu xử lý nhỏ (~27 mã) nên độ mạnh thống kê hạn chế; '
           'các mốc trùng biến động vĩ mô (lãi suất, tỷ giá); kết quả là mô tả, không khẳng định quan hệ nhân quả. '
           'Mã có tỷ trọng ≥ 3% dùng VN-Index loại trừ chính mã làm lợi suất thị trường.</div>')
