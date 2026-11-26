"""Trang 3 – Ra-đa khối ngoại (bước B5.11): bảng xếp hạng NF, nf, z, chuỗi, U, hấp thụ; HHI theo thời gian;
dòng vốn theo nhóm FTSE/VN30/đối chứng/ngành; tỷ lệ hấp thụ; bộ lọc nhóm và khoảng phiên."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.analytics import narrative
from src.app import data_access as da
from src.app.components import charts, status_bar
from src.app.components import widgets as W
from src.app.components.states import empty, safe_block
from src.app.components.ui import colored, esc, header, kpi, md, pal, plot, soft_chip, table_html
from src.app.theme import ABSORB_COLORS, color_for
from src.common import fmt
from src.finance.domestic import ABSORB_LABELS


def extra_insight(date, s_) -> str:
    """Hai ý nối: khối ngoại mua/bán ròng đáng kể cùng chiều giá ở bao nhiêu mã dẫn dắt; nhóm FTSE khác đối chứng thế nào."""
    from src.analytics.diagnosis import CODIR_MIN_NF, top_leaders
    top = s_[s_["symbol"].isin(top_leaders(s_))]
    nf_i = top["nf"]
    same = top[(np.sign(top["net_flow"].fillna(0)) == np.sign(top["C"])) & (nf_i.abs() >= CODIR_MIN_NF)]
    g = da.groups(date, "universe").set_index("group_name")
    out = (f"Ở 10 mã dẫn dắt, khối ngoại mua/bán ròng ≥ 5% GTGD cùng chiều giá tại {len(same)}/{len(top)} mã"
           + (f" ({', '.join(same['symbol'].head(4))})" if len(same) else "") + " – quan hệ cùng phiên, không phải nhân quả.")
    if {"FTSE", "CONTROL"} <= set(g.index):
        a, b = g.loc["FTSE", "net_flow"], g.loc["CONTROL", "net_flow"]
        out += f" Nhóm FTSE ròng {fmt.bn(a)} so với nhóm đối chứng {fmt.bn(b)}."
    return esc(out)


@safe_block("bảng xếp hạng")
def ranking(date, group: str) -> None:
    s = da.stock_day(date)
    s = s[s["is_valid"]]
    top5 = set(s.reindex(s["C"].abs().sort_values(ascending=False).index).head(5)["symbol"])   # nối với trang Dẫn dắt
    if group != "Toàn sàn":
        key = {"Nhóm FTSE": "FTSE", "Nhóm đối chứng": "CONTROL", "VN30": "VN30"}.get(group)
        s = s[s["symbol"].isin(da.universe(key))] if key else s[s["sector"] == group]
    sort = st.segmented_control("Sắp xếp", ["Mua ròng", "Bán ròng", "|z| lớn nhất", "Room gần cạn"], default="Mua ròng",
                                key="p3_sort", label_visibility="collapsed") or "Mua ròng"
    s = {"Mua ròng": s.sort_values("net_flow", ascending=False), "Bán ròng": s.sort_values("net_flow"),
         "|z| lớn nhất": s.reindex(s["z_nf"].abs().sort_values(ascending=False).index),
         "Room gần cạn": s.sort_values("U", ascending=False)}[sort].head(15)
    rows = [[f'<span class="ffr-sym">{r.symbol}</span>' + (' <span class="ffr-chip" style="background:rgba(245,179,65,.18);'
             'color:#F5B341">Top 5 đóng góp</span>' if r.symbol in top5 else '') + f' <small>{r.sector}</small>',
             colored(r.ret, fmt.pct(r.ret * 100)),
             colored(r.net_flow, fmt.bn(r.net_flow, 1)), fmt.num(r.nf, 3, True), fmt.frac_pct(r.FPR, 1),
             colored(r.z_nf, fmt.num(r.z_nf, 2, True)), fmt.num(r.pct60_nf, 0), f"{int(r.streak):+d}" + (" ↺" if r.reversal else ""),
             fmt.frac_pct(r.U, 1) + (" *" if r.room_changed else ""), soft_chip(ABSORB_LABELS[r.absorb_state], ABSORB_COLORS[r.absorb_state])]
            for r in s.itertuples()]
    md(table_html(["Mã", "%", "NF", "nf", "FPR", "z (60)", "Phân vị 60", "Chuỗi", "Room đã dùng", "Chiều giá – ngoại"], rows, left=(0,)))
    st.caption("Nhãn 'Top 5 đóng góp': mã nằm trong 5 mã ảnh hưởng điểm VN-Index nhiều nhất phiên. "
               "Chuỗi: + mua ròng / − bán ròng liên tiếp; ↺ đảo chiều sau chuỗi ≥ 3. * room thay đổi so với phiên trước "
               "(phát hành thêm/đổi giới hạn). z và phân vị chỉ dùng 60 phiên trước (không nhìn trước).")


@safe_block("khối ngoại theo ngành")
def sector_foreign(date) -> None:
    g = da.groups(date, "sector").sort_values("net_flow", ascending=False)
    rows = [[f"<b>{esc(r.group_name)}</b>", fmt.num(r.FB / 1e9, 1), fmt.num(r.FS / 1e9, 1), colored(r.net_flow, fmt.num(r.net_flow / 1e9, 1, True)),
             fmt.num(r.nf, 3, True), fmt.frac_pct(r.FPR, 1), soft_chip(ABSORB_LABELS[r.absorb_state], ABSORB_COLORS[r.absorb_state])]
            for r in g.itertuples()]
    md(table_html(["Ngành", "Mua (tỷ)", "Bán (tỷ)", "Ròng (tỷ)", "nf", "FPR", "Ngoại – nội"], rows, left=(0, 6)))


@safe_block("lũy kế theo nhóm")
def group_windows(date) -> None:
    sess = [x for x in da.sessions() if x <= date]
    g = da.groups(None, "universe")
    d = da.daily().set_index("trade_date")["NF_total"]
    rows = []
    names = {"FTSE": "Nhóm FTSE", "CONTROL": "Nhóm đối chứng", "VN30": "VN30"}
    for key, lbl in [("ALL", "Toàn sàn HOSE")] + list(names.items()):
        cells = [f"<b>{lbl}</b>"]
        for n in (1, 5, 20, 60):
            win = sess[-n:]
            v = d.reindex(win).sum() if key == "ALL" else g[(g["group_name"] == key) & g["trade_date"].isin(win)]["net_flow"].sum()
            cells.append(colored(v, fmt.num(v / 1e9, 0, True)))
        rows.append(cells)
    md(table_html(["Nhóm", "1 phiên", "5 phiên", "20 phiên", "60 phiên"], rows, left=(0,)))
    st.caption("Khối ngoại ròng cộng dồn (tỷ đồng); phiên SSI chưa công bố khối ngoại không được tính.")


@safe_block("chuỗi mua bán ròng")
def streaks(date) -> None:
    s = da.stock_day(date)
    s = s[s["is_valid"] & s["streak"].notna()]
    rows = []
    for lbl, df in (("Mua ròng", s.nlargest(6, "streak")), ("Bán ròng", s.nsmallest(6, "streak"))):
        for i, r in enumerate(df.itertuples()):
            rows.append([lbl if i == 0 else "", f'<span class="ffr-sym">{r.symbol}</span>', f"{int(r.streak):+d}",
                         colored(r.net_flow, fmt.num(r.net_flow / 1e9, 1, True)), colored(r.ret, fmt.pct(r.ret * 100, 1))])
    md(table_html(["Chiều", "Mã", "Số phiên", "Ròng (tỷ)", "Giá %"], rows, left=(0, 1)))


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
    D = W.load(date)
    rng = d[d["trade_date"].between(lo, hi)]
    t1, t2, t3 = st.tabs(["Mua bán trong phiên", "Theo ngành & nhóm", "Diễn biến nhiều phiên"])

    with t1:
        k = st.columns(4)
        for c, h in zip(k, [kpi("Khối ngoại ròng HOSE", fmt.bn(x["NF_total"]), color_for(x["NF_total"], p),
                                sub=f"z = {fmt.num(x['z_NF_total'], 2, True)} so với 60 phiên"),
                            kpi("Top 5 mã / tổng |ròng|", fmt.frac_pct(x["top5_share_flow"], 0), sub="mức tập trung của dòng vốn"),
                            kpi("HHI dòng vốn", fmt.num(x["HHI"], 3),
                                sub=f"≈ trải đều trên {fmt.num(1 / x['HHI'] if x['HHI'] else float('nan'), 0)} mã"),
                            kpi("Tỷ trọng GD khối ngoại", fmt.frac_pct(x["FPR_total"], 1), sub="phần còn lại thuộc khối nội")]):
            with c:
                md(h)
        c1, c2 = st.columns([1.25, 2], gap="small")
        with c1, W.card("p3_top"):
            W.w_foreign_top(D)
        with c2, W.card("p3_flow"):
            W.w_foreign_flow(D)
        s_ = da.stock_day(date)
        s_ = s_[s_["is_valid"]]
        md(f'<div class="ffr-lead">{esc(narrative.foreign_summary(x, s_.nlargest(5, "net_flow"), s_.nsmallest(5, "net_flow")))} '
           f'{extra_insight(date, s_)}</div>')
        with W.card("p3_rank"):
            W.title("Bảng xếp hạng dòng vốn", f"Phiên {date:%d/%m/%Y} · {group} · chọn cách sắp xếp")
            ranking(date, group)

    with t2:
        c1, c2 = st.columns([1.4, 1], gap="small")
        with c1, W.card("p3_sec"):
            W.title("Khối ngoại theo ngành", f"Phiên {date:%d/%m/%Y} · sắp theo giá trị ròng")
            sector_foreign(date)
        with c2, W.card("p3_gw"):
            W.title("Lũy kế theo nhóm", "Tỷ đồng · 1 / 5 / 20 / 60 phiên")
            group_windows(date)
        with W.card("p3_groups"):
            W.title("Dòng vốn theo nhóm và ngành", f"Cộng dồn {lo:%d/%m/%Y} – {hi:%d/%m/%Y} · 3 nhóm chính, 5 ngành mua ròng và "
                                                   "5 ngành bán ròng nhiều nhất · tỷ đồng")
            g = da.groups()
            g = g[g["trade_date"].between(lo, hi)]
            uni = g[g["group_type"].isin(["universe", "sector"])].groupby(["group_type", "group_name"])["net_flow"].sum().div(1e9).reset_index()
            sec = uni[uni["group_type"] == "sector"]
            uni = pd.concat([uni[uni["group_type"] == "universe"], sec.nlargest(5, "net_flow"), sec.nsmallest(5, "net_flow")])
            uni = uni.drop_duplicates("group_name")
            uni["group_name"] = uni["group_name"].replace({"FTSE": "★ Nhóm FTSE", "CONTROL": "★ Đối chứng", "VN30": "★ VN30"})
            fig = charts.sector_bars(uni.rename(columns={"net_flow": "val"}), "val", p, " tỷ")
            fig.update_traces(textposition="auto", insidetextanchor="end",
                              text=[fmt.num(v, 0, True, " tỷ") for v in fig.data[0].x])
            plot(fig, "p3_groups")

    with t3:
        c1, c2 = st.columns([1.4, 1], gap="small")
        with c1, W.card("p3_hhi"):
            W.title("Mức tập trung dòng vốn (HHI)", f"{lo:%d/%m/%Y} – {hi:%d/%m/%Y} · càng cao = dòng vốn dồn vào ít mã")
            plot(charts.line(rng.assign(HHI_ma=rng["HHI"].rolling(10).mean()), "trade_date",
                             {"HHI": "HHI", "HHI_ma": "Trung bình 10 phiên"}, p), "p3_hhi")
        with c2, W.card("p3_streak"):
            W.title("Chuỗi mua / bán ròng dài nhất", f"Tính đến phiên {date:%d/%m/%Y}")
            streaks(date)
        with W.card("p3_abs"):
            W.title("Chiều giá so với chiều khối ngoại", "Mã–phiên khối ngoại bán ròng đáng kể mà giá vẫn tăng = \"Giá tăng dù ngoại bán\"")
            absorb(lo, hi, group)


@safe_block("trạng thái hấp thụ")
def absorb(lo, hi, group: str) -> None:
    p = pal()
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
