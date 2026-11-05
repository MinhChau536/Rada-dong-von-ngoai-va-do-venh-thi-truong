"""Trang 3 – Ra-đa khối ngoại (bước B5.11): bảng xếp hạng NF, nf, z, chuỗi, U, hấp thụ; HHI theo thời gian;
dòng vốn theo nhóm FTSE/VN30/đối chứng/ngành; tỷ lệ hấp thụ; bộ lọc nhóm và khoảng phiên."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.app import data_access as da
from src.app.components import charts, status_bar
from src.app.components.states import empty, safe_block
from src.app.components.ui import colored, header, kpi, md, pal, plot, section, soft_chip, table_html
from src.app.theme import ABSORB_COLORS, color_for
from src.common import fmt
from src.finance.domestic import ABSORB_LABELS


@safe_block("bảng xếp hạng")
def ranking(date, group: str) -> None:
    s = da.stock_day(date)
    s = s[s["is_valid"]]
    if group != "Toàn sàn":
        key = {"Nhóm FTSE": "FTSE", "Nhóm đối chứng": "CONTROL", "VN30": "VN30"}.get(group)
        s = s[s["symbol"].isin(da.universe(key))] if key else s[s["sector"] == group]
    sort = st.segmented_control("Sắp xếp", ["Mua ròng", "Bán ròng", "|z| lớn nhất", "Room gần cạn"], default="Mua ròng",
                                key="p3_sort", label_visibility="collapsed") or "Mua ròng"
    s = {"Mua ròng": s.sort_values("net_flow", ascending=False), "Bán ròng": s.sort_values("net_flow"),
         "|z| lớn nhất": s.reindex(s["z_nf"].abs().sort_values(ascending=False).index),
         "Room gần cạn": s.sort_values("U", ascending=False)}[sort].head(15)
    rows = [[f'<span class="ffr-sym">{r.symbol}</span> <small>{r.sector}</small>', colored(r.ret, fmt.pct(r.ret * 100)),
             colored(r.net_flow, fmt.bn(r.net_flow, 1)), fmt.num(r.nf, 3, True), fmt.frac_pct(r.FPR, 1),
             colored(r.z_nf, fmt.num(r.z_nf, 2, True)), fmt.num(r.pct60_nf, 0), f"{int(r.streak):+d}" + (" ↺" if r.reversal else ""),
             fmt.frac_pct(r.U, 1) + (" *" if r.room_changed else ""), soft_chip(ABSORB_LABELS[r.absorb_state], ABSORB_COLORS[r.absorb_state])]
            for r in s.itertuples()]
    md(table_html(["Mã", "%", "NF", "nf", "FPR", "z (60)", "Phân vị 60", "Chuỗi", "Room đã dùng", "Hấp thụ"], rows, left=(0,)))
    st.caption("Chuỗi: + mua ròng / − bán ròng liên tiếp; ↺ đảo chiều sau chuỗi ≥ 3. * room thay đổi so với phiên trước "
               "(phát hành thêm/đổi giới hạn). z và phân vị chỉ dùng 60 phiên trước (không nhìn trước).")


def render() -> None:
    header("Ra-đa khối ngoại", "Dòng vốn ngoại tập trung vào đâu, có đi cùng giá không, và khối nội phản ứng ra sao")
    status_bar.render()
    p = pal()
    sess = da.sessions()
    sectors = sorted(da.groups(None, "sector")["group_name"].unique())
    c1, c2, c3 = st.columns([1, 1.2, 2.5])
    date = c1.selectbox("Phiên", sess[::-1], format_func=lambda d: f"{d:%d/%m/%Y}", key="p3_date")
    group = c2.selectbox("Nhóm", ["Toàn sàn", "Nhóm FTSE", "Nhóm đối chứng", "VN30"] + sectors, key="p3_group")
    lo, hi = c3.select_slider("Khoảng phiên", options=sess, value=(sess[max(0, len(sess) - 120)], sess[-1]),
                              format_func=lambda d: f"{d:%d/%m/%Y}", key="p3_range")
    d = da.daily()
    x = d.set_index("trade_date").loc[date]
    k = st.columns(5)
    for c, h in zip(k, [kpi("NF toàn sàn", fmt.bn(x["NF_total"]), color_for(x["NF_total"], p)),
                        kpi("z tổng NF (60 phiên)", fmt.num(x["z_NF_total"], 2, True)),
                        kpi("HHI tập trung", fmt.num(x["HHI"], 3), sub="→1 khi dồn vào 1 mã"),
                        kpi("Top 5 / Σ|NF|", fmt.frac_pct(x["top5_share_flow"], 0)),
                        kpi("FPR toàn sàn", fmt.frac_pct(x["FPR_total"], 1), sub="phần còn lại thuộc khối nội")]):
        with c:
            md(h)
    section("Bảng xếp hạng dòng vốn", f"Phiên {date:%d/%m/%Y} · {group}")
    ranking(date, group)
    rng = d[d["trade_date"].between(lo, hi)]
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        section("Mức tập trung HHI theo thời gian")
        plot(charts.line(rng.assign(HHI_ma=rng["HHI"].rolling(10).mean()), "trade_date",
                         {"HHI": "HHI", "HHI_ma": "Trung bình 10 phiên"}, p), "p3_hhi")
    with c2:
        section("NF toàn sàn lũy kế (tỷ đồng)")
        plot(charts.line(rng.assign(cum=rng["NF_total"].cumsum() / 1e9), "trade_date", {"cum": "NF lũy kế"}, p), "p3_cum")
    section("Dòng vốn theo nhóm", "Cộng dồn trong khoảng phiên đã chọn")
    g = da.groups()
    g = g[g["trade_date"].between(lo, hi)]
    uni = g[g["group_type"].isin(["universe", "sector"])].groupby(["group_type", "group_name"])["net_flow"].sum().div(1e9).reset_index()
    uni["group_name"] = uni["group_name"].replace({"FTSE": "★ Nhóm FTSE", "CONTROL": "★ Đối chứng", "VN30": "★ VN30"})
    plot(charts.sector_bars(uni.rename(columns={"net_flow": "val"}), "val", p, " tỷ"), "p3_groups")
    section("Trạng thái hấp thụ của khối nội", "Tỷ lệ mã–phiên khối ngoại bán ròng có ý nghĩa mà giá vẫn tăng (khối nội hấp thụ)")
    sr = da.stock_range(lo, hi)
    sr = sr[sr["is_valid"]]
    if group != "Toàn sàn":
        key = {"Nhóm FTSE": "FTSE", "Nhóm đối chứng": "CONTROL", "VN30": "VN30"}.get(group)
        sr = sr[sr["symbol"].isin(da.universe(key))] if key else sr[sr["sector"] == group]
    if sr.empty:
        empty("Không có dữ liệu cho nhóm đã chọn.")
        return
    cnt = sr.groupby(["trade_date", "absorb_state"]).size().unstack(fill_value=0)
    fig = go.Figure()
    for st_ in ["absorb", "joint_sell", "joint_buy", "domestic_take"]:
        if st_ in cnt:
            fig.add_trace(go.Bar(x=cnt.index, y=cnt[st_], name=ABSORB_LABELS[st_], marker_color=ABSORB_COLORS[st_]))
    fig.update_layout(barmode="stack")
    plot(charts._lay(fig, p, 300, hovermode="x unified"), "p3_abs")
    sell = sr[sr["absorb_state"].isin(["absorb", "joint_sell"])]
    rate = (sell["absorb_state"] == "absorb").mean() if len(sell) else float("nan")
    st.caption(f"Tỷ lệ hấp thụ trong khoảng: {fmt.frac_pct(rate, 1)} ({len(sell)} quan sát bán ròng có ý nghĩa). "
               "Mua ròng khối nội = − bán ròng khối ngoại nên không dựng chỉ số “sức mạnh dòng tiền nội” riêng. "
               "Tỷ trọng lô lẻ và mua/bán chủ động chỉ có khi bộ ghi streaming chạy (kênh OL, X-TRADE).")
