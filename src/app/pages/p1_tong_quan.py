"""
Trang 1 – Tổng quan thị trường (bước B4.5, bảng 11.4, Hình 2a–2d).

Giữ ĐÚNG thứ tự khối của render() trong giao_dien/thi_truong.py (giữa kỳ) và chèn 3 khối mới:
thanh trạng thái → giới thiệu → (a) 4 thẻ chỉ số → (b) chất lượng xu hướng [MỚI] → (c) danh mục theo dõi →
(d) diễn biến chỉ số + sức khỏe → (e) mã dẫn dắt [MỚI] → (f) độ rộng → (g) bản đồ nhiệt + ngành →
(h) dòng vốn khối ngoại [MỚI] → (i) cổ phiếu nổi bật → (j) so sánh hiệu suất → (k) chân trang.
Mỗi khối là một hàm render_x(data); dữ liệu đọc một lần qua load_overview(session_date).
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd
import streamlit as st

from src.analytics import narrative
from src.analytics.health import market_health, period_returns
from src.analytics.watchlist_impact import get_watchlist
from src.app import data_access as da
from src.app.components import about, charts, status_bar
from src.app.components.states import empty, safe_block
from src.app.components.ui import (colored, esc, header, kpi, md, pal, plot, section, soft_chip, spark, table_html)
from src.app.theme import ABSORB_COLORS, SESSION_COLORS, color_for
from src.common import fmt
from src.common.config import events, get, is_demo
from src.finance.breadth import breadth_summary, session_type_label
from src.finance.domestic import ABSORB_LABELS

INDEX_ORDER = [("VNINDEX", "VN-Index"), ("VN30", "VN30"), ("HNXINDEX", "HNX-Index"), ("UPCOMINDEX", "UPCoM-Index")]
PERIODS = {"1Th": 31, "3Th": 92, "6Th": 183, "1N": 365, "3N": 1095}


@st.cache_data(ttl=60, show_spinner=False)
def load_overview(session_date) -> Dict:
    d = pd.Timestamp(session_date)
    day_all = da.daily()
    day = day_all[day_all["trade_date"] <= d]
    st_day = da.stock_day(d)
    sp = da.sparks(d, 30)
    return {"date": d, "day": day.iloc[-1], "day_hist": day, "stock": st_day, "leaders": da.leaders(d),
            "groups": da.groups(d), "sparks": sp.groupby("symbol")["close"].apply(lambda s: s.tail(30).tolist()).to_dict(),
            "index": {code: da.index_hist(code) for code, _ in INDEX_ORDER}}


# ── (a) 4 thẻ chỉ số ──────────────────────────────────────────────────────────
@safe_block("thẻ chỉ số")
def render_index_cards(data: Dict) -> None:
    p, d = pal(), data["date"]
    cols = st.columns(4)
    for col, (code, name) in zip(cols, INDEX_ORDER):
        h = data["index"][code]
        h = h[h["trade_date"] <= d]
        with col:
            if h.empty or h["trade_date"].iloc[-1] != d:
                md(f'<div class="ffr-card"><div class="ffr-lbl">{name}</div><div class="ffr-val" style="color:{p["muted"]}">—</div>'
                   f'<div class="ffr-meta">Không có dữ liệu phiên {d:%d/%m/%Y}</div></div>')
                continue
            last = h.iloc[-1]
            chg, rc = last["change"], last["ratio_change"]
            clr = color_for(chg, p)
            r = period_returns(h.set_index("trade_date")["value"])
            md(f'<div class="ffr-card"><div style="display:flex;justify-content:space-between"><div class="ffr-lbl">{name}</div>'
               f'<div class="ffr-lbl" style="letter-spacing:0">{d:%d/%m/%Y}</div></div>'
               f'<div class="ffr-val">{fmt.num(last["value"])}</div>'
               f'<div class="ffr-chg" style="color:{clr}">{fmt.arrow(chg)} {fmt.num(chg, 2, True)} ({fmt.pct(rc)})</div>'
               f'<div style="margin-top:4px">{spark(h["value"].tail(int(get("windows.sparkline_index", 40))), clr)}</div>'
               f'<div class="ffr-meta"><span>Thấp–Cao: {fmt.num(last["low"], 1)} – {fmt.num(last["high"], 1)}</span></div>'
               f'<div class="ffr-meta"><span>KL: {fmt.num(last["vol"] / 1e6, 1)} tr</span><span>1Th '
               f'{colored(r["1Th"], fmt.pct(r["1Th"], 1))} · YTD {colored(r["YTD"], fmt.pct(r["YTD"], 1))}</span></div></div>')


# ── (b) chất lượng xu hướng ───────────────────────────────────────────────────
@safe_block("chất lượng xu hướng")
def render_trend_quality(data: Dict) -> None:
    p, x = pal(), data["day"]
    stype = x["session_type"]
    sc = SESSION_COLORS.get(stype, p["muted"])
    items = [
        ("Trung vị cổ phiếu HOSE", fmt.pct(x["median_ret_pct"]), color_for(x["median_ret_pct"], p),
         f'{int(x["n_valid"])} mã hợp lệ · IQR {fmt.num(x["IQR_pct"], 1)}%', "(1) r = P_c/P_ref − 1; trung vị trên Ω_t; (3) IQR = Q75 − Q25"),
        ("Độ vênh D", fmt.num(x["D"], 2, True, " đ.%"), p["accent"] if x["D"] >= 0 else p["down"],
         f'Phân vị {fmt.num(x.get("D_pct250"), 0)}% · 250 phiên trước', "(2) D = r_VNI − median(r_i); phân vị chỉ dùng dữ liệu đến t−1"),
        ("Top 5 đóng góp (CR5)", fmt.frac_pct(x["CR5"], 0), p["text"],
         f'của tổng |đóng góp| · ε = {fmt.num(x["eps"], 2, True)} đ', "(5) CR5 = Σ|C| top5 / Σ|C|"),
        ("Khối ngoại ròng HOSE", fmt.bn(x["NF_total"]), color_for(x["NF_total"], p),
         f'z60 = {fmt.num(x["z_NF_total"], 2, True)} · HHI {fmt.num(x["HHI"], 3)}', "(6) NF = FB − FS; (7) HHI; (8) z theo 60 phiên trước"),
    ]
    cols = st.columns(5)
    for c, (lbl, val, clr, sub, tip) in zip(cols, items):
        with c:
            md(kpi(lbl, val, clr, sub, tip))
    with cols[4]:
        md(kpi("Loại phiên", soft_chip(session_type_label(stype), sc), None,
               f'{int(x["n_sessions_same_type_5"])}/5 phiên gần nhất cùng loại' + (" · ⚠ độ vênh cao" if x["high_divergence"] else ""),
               "Quy tắc mục 8.2: dấu r_VNI × dấu AD; |r_VNI| < 0,1% = đi ngang"))


# ── (c) danh mục theo dõi ─────────────────────────────────────────────────────
@safe_block("danh mục theo dõi")
def render_watchlist_strip(data: Dict) -> None:
    p = pal()
    wl = get_watchlist()
    s = data["stock"].set_index("symbol")
    cols = st.columns(min(5, max(1, len(wl))))
    for i, sym in enumerate(wl[:10]):
        with cols[i % len(cols)]:
            if sym not in s.index or not bool(s.loc[sym, "is_valid"]):
                md(f'<div class="ffr-card"><b class="ffr-sym">{sym}</b><div class="ffr-meta">chưa có dữ liệu phiên</div></div>')
                continue
            r = s.loc[sym]
            clr = color_for(r["ret"], p)
            ab = r["absorb_state"]
            md(f'<div class="ffr-card" style="padding:10px 12px"><div style="display:flex;justify-content:space-between">'
               f'<b class="ffr-sym">{sym}</b><b style="color:{clr}">{fmt.pct(r["ret"] * 100)}</b></div>'
               f'<div style="display:flex;justify-content:space-between;align-items:center;gap:6px"><div>'
               f'<div style="font-size:18px;font-weight:800">{fmt.price(r["close"])}</div>'
               f'<div style="font-size:11px;color:{p["muted"]}">vs trung vị {fmt.num(r["ER_M"] * 100, 2, True)} đ.% · NN {fmt.bn(r["net_flow"], 0)}</div>'
               f'</div><div style="width:80px">{spark(data["sparks"].get(sym, []), clr, 80, 30, False)}</div></div>'
               f'<div style="margin-top:5px">{soft_chip(ABSORB_LABELS[ab], ABSORB_COLORS[ab])}</div></div>')
            if st.button("Xem hồ sơ →", key=f"wl_go_{sym}", width="stretch"):
                st.session_state["selected_symbol"] = sym
                st.switch_page(st.session_state["_pages"]["watchlist"])


# ── (d) diễn biến chỉ số + sức khỏe ───────────────────────────────────────────
@safe_block("diễn biến chỉ số")
def render_index_chart(data: Dict) -> None:
    p = pal()
    c_chart, c_health = st.columns([3, 1], gap="medium")
    with c_chart:
        o1, o2, o3 = st.columns([2.6, 2.5, 1.4])
        code = o1.segmented_control("Chỉ số", [c for c, _ in INDEX_ORDER], default="VNINDEX", key="p1_idx",
                                    format_func=lambda c: {"VNINDEX": "VNI", "VN30": "VN30", "HNXINDEX": "HNX",
                                                           "UPCOMINDEX": "UPCoM"}[c], label_visibility="collapsed") or "VNINDEX"
        per = o2.segmented_control("Kỳ", list(PERIODS), default="6Th", key="p1_per", label_visibility="collapsed") or "6Th"
        kind = o3.segmented_control("Kiểu", ["Nến", "Đường"], default="Nến", key="p1_kind", label_visibility="collapsed") or "Nến"
        show_ev = st.toggle("Đánh dấu mốc FTSE (E1, E2, E3)", value=True, key="p1_ev")
        h = data["index"][code]
        h = h[h["trade_date"] <= data["date"]]
        if h.empty:
            empty("Không có dữ liệu chỉ số.")
        else:
            cutoff = h["trade_date"].max() - pd.Timedelta(days=PERIODS[per])
            view = h[h["trade_date"] >= cutoff - pd.Timedelta(days=80)]
            fig = charts.index_chart(view, dict(INDEX_ORDER)[code], kind, p, events() if show_ev else None)
            fig.update_xaxes(range=[cutoff, h["trade_date"].max() + pd.Timedelta(days=2)])
            plot(fig, "p1_idx_chart")
    with c_health:
        render_health(data)


def render_health(data: Dict) -> None:
    p, x = pal(), data["day"]
    vni = data["index"]["VNINDEX"]
    vni = vni[vni["trade_date"] <= data["date"]]
    s = data["stock"]
    pm = float(s.loc[s["is_valid"], "above_ma20"].mean() * 100) if not s.empty else None
    h = market_health(vni["value"], x["pct_up"], pm, x.get("D_pct250"))
    md('<div class="ffr-lbl">Sức khỏe thị trường</div>')
    if not h.get("available"):
        empty("Chưa đủ dữ liệu để chấm điểm.")
        return
    plot(charts.gauge(h["score"], p), "p1_gauge")
    clr = p["up"] if h["score"] >= 70 else p["ref"] if h["score"] >= 40 else p["down"]
    rows = "".join(f'<div class="ffr-comp"><span>{v["label"]} <small>({v["weight"]}%)</small></span><b>{v["detail"]}</b></div>'
                   f'<div class="ffr-track"><i style="width:{max(2, v["score"]):.0f}%;background:{color_for(v["score"] - 50, p)}"></i></div>'
                   for v in h["components"].values())
    md(f'<div style="text-align:center;font-weight:800;color:{clr};margin:-8px 0 6px">{h["label"]}</div>{rows}')
    st.caption(f"Điểm theo quy tắc (tổng trọng số {h['weights_sum']}%) – chỉ để tham khảo, không phải khuyến nghị.")


# ── (e) mã dẫn dắt ────────────────────────────────────────────────────────────
@safe_block("mã dẫn dắt")
def render_leaders(data: Dict) -> None:
    p, x, lead = pal(), data["day"], data["leaders"]
    if lead.empty:
        empty("Chưa có dữ liệu đóng góp điểm.")
        return
    c1, c2 = st.columns([1.15, 1], gap="medium")
    with c1:
        pos = lead[lead["side"] == "pos"].head(5)
        neg = lead[lead["side"] == "neg"].head(5)
        both = pd.concat([pos, neg])
        fig = charts.diverging_bars(both["symbol"].tolist(), both["C"].tolist(), p, 330,
                                    title=f"Đóng góp điểm hôm nay · ΔVN-Index = {fmt.num(x['dI'], 2, True)} điểm")
        plot(fig, "p1_leaders")
        rest = x["sumC"] - both["C"].sum()
        n_rest = int(x["n_valid"]) - len(both)
        st.caption(f"Còn lại {n_rest} mã: {fmt.num(rest, 2, True)} điểm · sai số tái lập ε = {fmt.num(x['eps'], 2, True)} điểm "
                   f"(ΣC + ε = ΔVN-Index)")
    with c2:
        g = data["groups"]
        fam = g[g["group_type"] == "family"].sort_values("C", ascending=False)
        sec = g[g["group_type"] == "sector"].copy()
        sec = sec.reindex(sec["C"].abs().sort_values(ascending=False).index).head(5)
        both = pd.concat([fam.assign(kind="Họ"), sec.assign(kind="Ngành")])
        mx = max(both["C"].abs().max(), 1e-9)
        rows = ""
        for r in both.itertuples():
            w = abs(r.C) / mx * 100
            name = {"VINGROUP": "Nhóm Vingroup", "MASAN": "Nhóm Masan", "GELEX": "Nhóm Gelex", "HOAPHAT": "Hòa Phát"}.get(r.group_name, r.group_name)
            rows += (f'<div class="ffr-comp"><span>{esc(name)} <small>· {r.kind}</small></span>'
                     f'<b style="color:{color_for(r.C, p)}">{fmt.num(r.C, 2, True)}</b></div>'
                     f'<div class="ffr-track"><i style="width:{w:.0f}%;background:{color_for(r.C, p)}"></i></div>')
        vin = fam[fam["group_name"] == "VINGROUP"]
        ex = (f'<div style="font-size:12px;color:{p["muted"]};margin-top:8px">VN-Index loại trừ nhóm Vingroup: '
              f'{colored(vin["index_ex_group_ret_pct"].iloc[0], fmt.pct(vin["index_ex_group_ret_pct"].iloc[0]))} '
              f'(thực tế {fmt.pct(x["r_vni_pct"])})</div>') if not vin.empty else ""
        md(f'<div class="ffr-card"><div class="ffr-lbl">Theo họ cổ phiếu và ngành (điểm)</div>{rows}{ex}</div>')
        md('<div style="height:10px"></div>')
        md(f'<div class="ffr-insight"><b>Nhận định theo quy tắc</b><br>{esc(narrative.market_summary(x, lead))}</div>')
        if st.button("Xem chi tiết dẫn dắt & độ vênh →", key="p1_to_p2"):
            st.switch_page(st.session_state["_pages"]["dan-dat"])


# ── (f) độ rộng ───────────────────────────────────────────────────────────────
@safe_block("độ rộng thị trường")
def render_breadth(data: Dict) -> None:
    p = pal()
    s = data["stock"]
    baskets = {"★ HOSE toàn sàn": None, "VN30": da.universe("VN30"), "Nhóm FTSE": da.universe("FTSE"),
               "Nhóm đối chứng": da.universe("CONTROL"), "Watchlist": get_watchlist()}
    name = st.selectbox("Rổ", list(baskets), key="p1_basket", label_visibility="collapsed",
                        format_func=lambda n: f"{n} · {len(s) if baskets[n] is None else len(baskets[n])} mã")
    sub = s if baskets[name] is None else s[s["symbol"].isin(baskets[name])]
    b = breadth_summary(sub)
    if not b["available"]:
        empty("Rổ không có mã hợp lệ trong phiên này.")
        return
    t = b["total"]
    w = lambda n: n / t * 100  # noqa: E731
    seg = [(b["ceiling"], p["ceiling"]), (b["up"], p["up"]), (b["unch"], p["ref"]), (b["down"], p["down"]), (b["floor"], p["floor"])]
    bar = "".join(f'<div style="width:{w(n):.2f}%;background:{c}"></div>' for n, c in seg)
    md(f'<div class="ffr-card"><div style="display:flex;justify-content:space-between"><div class="ffr-lbl">Tương quan tăng / giảm · '
       f'{t} mã · phiên {data["date"]:%d/%m/%Y}</div><div class="ffr-lbl" style="letter-spacing:0">AD = {fmt.num(b["AD"], 2, True)}</div></div>'
       f'<div class="ffr-bar">{bar}</div><div class="ffr-legend">'
       f'<span style="color:{p["up"]}">▲ {b["advancing"]} tăng ({w(b["advancing"]):.0f}%) · <span style="color:{p["ceiling"]}">{b["ceiling"]} trần</span></span>'
       f'<span style="color:{p["ref"]}">■ {b["unch"]} đứng giá</span>'
       f'<span style="color:{p["down"]}">▼ {b["declining"]} giảm ({w(b["declining"]):.0f}%) · <span style="color:{p["floor"]}">{b["floor"]} sàn</span></span></div></div>')
    md('<div style="height:8px"></div>')
    cols = st.columns(5)
    items = [kpi("LS đồng trọng số", fmt.pct(b["eq_ret_pct"]), color_for(b["eq_ret_pct"], p)),
             kpi("% mã trên MA20", fmt.num(b["pct_above_ma20"], 0, False, "%"), color_for((b["pct_above_ma20"] or 50) - 50, p)),
             kpi("Vượt đỉnh 20 phiên", str(b["new_high20"]), p["up"]),
             kpi("Thủng đáy 20 phiên", str(b["new_low20"]), p["down"]),
             kpi("Tổng GTGD khớp", fmt.num(b["tv_bn"], 0, False, " tỷ"))]
    for c, h in zip(cols, items):
        with c:
            md(h)


# ── (g) bản đồ nhiệt + ngành ──────────────────────────────────────────────────
@safe_block("bản đồ nhiệt")
def render_heatmap(data: Dict) -> None:
    p = pal()
    c_map, c_sec = st.columns([3, 2], gap="medium")
    with c_map:
        plot(charts.treemap(data["stock"], p), "p1_treemap")
    with c_sec:
        o1, o2 = st.columns(2)
        hz = o1.segmented_control("Kỳ", [1, 5, 20], default=1, key="p1_sec_h", format_func=lambda h: f"{h} phiên",
                                  label_visibility="collapsed") or 1
        metric = o2.segmented_control("Chỉ tiêu", ["% giá", "Khối ngoại"], default="% giá", key="p1_sec_m",
                                      label_visibility="collapsed") or "% giá"
        dates = [x for x in da.sessions() if x <= data["date"]][-hz:]
        g = da.groups(None, "sector")
        g = g[g["trade_date"].isin(dates)]
        st_rng = da.stock_range(dates[0], dates[-1])
        if metric == "% giá":
            # Lợi suất ngành bình quân theo vốn hóa (w) trong kỳ
            st_rng = st_rng[st_rng["is_valid"]]
            st_rng["wr"] = st_rng["w"] * st_rng["ret"]
            agg = st_rng.groupby(["trade_date", "sector"]).agg(wr=("wr", "sum"), w=("w", "sum")).reset_index()
            agg["r"] = agg["wr"] / agg["w"]
            sec = agg.groupby("sector")["r"].apply(lambda r: ((1 + r).prod() - 1) * 100).reset_index()
            sec.columns = ["group_name", "val"]
            plot(charts.sector_bars(sec, "val", p), "p1_secbar")
        else:
            sec = g.groupby("group_name")["net_flow"].sum().div(1e9).reset_index(name="val")
            plot(charts.sector_bars(sec, "val", p, " tỷ"), "p1_secbar_f")


# ── (h) dòng vốn khối ngoại ───────────────────────────────────────────────────
@safe_block("dòng vốn khối ngoại")
def render_foreign_today(data: Dict) -> None:
    p, x = pal(), data["day"]
    s = data["stock"][data["stock"]["is_valid"]]
    c1, c2 = st.columns([1, 1.1], gap="medium")
    with c1:
        top = pd.concat([s.nlargest(5, "net_flow"), s.nsmallest(5, "net_flow")])
        plot(charts.diverging_bars(top["symbol"].tolist(), (top["net_flow"] / 1e9).tolist(), p, 330, "{:+.0f}",
                                   "Top mua và bán ròng (tỷ đồng)"), "p1_fbar")
    with c2:
        g = data["groups"]
        uni = g[g["group_type"] == "universe"].set_index("group_name")
        sec = g[g["group_type"] == "sector"]
        sec = sec.reindex(sec["net_flow"].abs().sort_values(ascending=False).index).head(2)
        rows = []
        for nm, label in (("FTSE", "Nhóm FTSE"), ("CONTROL", "Đối chứng"), ("VN30", "VN30")):
            if nm in uni.index:
                r = uni.loc[nm]
                rows.append([f"<b>{label}</b>", f'{int(r["n"])} mã', colored(r["net_flow"], fmt.bn(r["net_flow"])),
                             fmt.num(r["nf"], 3, True), soft_chip(ABSORB_LABELS[r["absorb_state"]], ABSORB_COLORS[r["absorb_state"]])])
        for r in sec.itertuples():
            rows.append([f"<b>{esc(r.group_name)}</b>", "ngành", colored(r.net_flow, fmt.bn(r.net_flow)), fmt.num(r.nf, 3, True),
                         soft_chip(ABSORB_LABELS[r.absorb_state], ABSORB_COLORS[r.absorb_state])])
        md(table_html(["Nhóm", "Số mã", "Ròng", "nf", "Hấp thụ"], rows))
        st.caption(f"Mức tham gia khối ngoại FPR = {fmt.frac_pct(x['FPR_total'], 1)} GTGD · tỷ trọng lô lẻ: "
                   f"{'chưa có (cần kênh OL thời gian thực)' if 'oddlot_share' not in x else fmt.frac_pct(x['oddlot_share'], 1)}. "
                   "Trạng thái hấp thụ chỉ gán khi |nf| ≥ 0,05 và |r| ≥ 0,5%.")
        md(f'<div class="ffr-insight" style="margin-top:6px">{esc(narrative.foreign_summary(x, s.nlargest(5, "net_flow"), s.nsmallest(5, "net_flow")))}</div>')
        if st.button("Xem Ra-đa khối ngoại →", key="p1_to_p3"):
            st.switch_page(st.session_state["_pages"]["khoi-ngoai"])


# ── (i) cổ phiếu nổi bật ──────────────────────────────────────────────────────
def _movers(df: pd.DataFrame, sparks: Dict, extra: str) -> str:
    p = pal()
    rows = []
    for i, r in enumerate(df.itertuples(), 1):
        clr = color_for(r.ret, p)
        ex = (fmt.num(r.vol_ratio, 2, False, "×") if extra == "vol" else fmt.num(r.C, 2, True) if extra == "C"
              else fmt.num(r.tv / 1e9, 1))
        rows.append([f'<span style="color:{p["muted"]}">{i}</span>',
                     f'<span class="ffr-sym">{r.symbol}</span> <small style="color:{p["muted"]}">{esc(r.sector)}</small>',
                     fmt.price(r.close), colored(r.close - r.ref, fmt.num(r.close - r.ref, 0, True)),
                     f'<span class="ffr-chip" style="background:{clr};color:#fff">{fmt.pct(r.ret * 100)}</span>',
                     fmt.num(r.vol, 0), ex, colored(r.net_flow, fmt.num(r.net_flow / 1e9, 1, True)),
                     colored(r.ret_20d, fmt.pct(r.ret_20d, 1)),
                     f'<div style="width:110px">{spark(sparks.get(r.symbol, []), clr, 110, 24, False)}</div>'])
    head = {"vol": "KL/TB20", "C": "Đóng góp (đ)", "tv": "GTGD (tỷ)"}[extra]
    return table_html(["#", "Mã", "Giá", "+/−", "%", "Khối lượng", head, "NN ròng (tỷ)", "20 phiên", "30 phiên gần nhất"], rows)


@safe_block("cổ phiếu nổi bật")
def render_movers(data: Dict) -> None:
    s = data["stock"][data["stock"]["is_valid"]].copy()
    n = 10
    tabs = st.tabs(["Tăng mạnh nhất", "Giảm mạnh nhất", "GTGD lớn", "Đột biến khối lượng", "Đóng góp điểm lớn"])
    with tabs[0]:
        md(_movers(s.nlargest(n, "ret"), data["sparks"], "tv"))
    with tabs[1]:
        md(_movers(s.nsmallest(n, "ret"), data["sparks"], "tv"))
    with tabs[2]:
        md(_movers(s.nlargest(n, "tv"), data["sparks"], "tv"))
    with tabs[3]:
        md(_movers(s[s["vol_ratio"] >= 2].nlargest(n, "vol_ratio"), data["sparks"], "vol"))
    with tabs[4]:
        md(_movers(s.reindex(s["C"].abs().sort_values(ascending=False).index).head(n), data["sparks"], "C"))
    pick = st.selectbox("Mở hồ sơ mã", ["—"] + sorted(s["symbol"]), key="p1_pick", label_visibility="collapsed",
                        format_func=lambda v: "🔎 Chọn mã để mở hồ sơ trong Watchlist Impact…" if v == "—" else v)
    if pick != "—":
        st.session_state["selected_symbol"] = pick
        st.session_state["p1_pick"] = "—"
        st.switch_page(st.session_state["_pages"]["watchlist"])


# ── (j) so sánh hiệu suất ─────────────────────────────────────────────────────
@safe_block("so sánh hiệu suất")
def render_performance(data: Dict) -> None:
    p, d = pal(), data["date"]
    wl = get_watchlist()
    target = st.session_state.get("selected_symbol") or (wl[0] if wl else "FPT")
    series, rows = {}, {}
    for code, name in INDEX_ORDER:
        h = data["index"][code]
        h = h[h["trade_date"] <= d].set_index("trade_date")["value"]
        rows[name] = period_returns(h)
        if code in ("VNINDEX", "VN30"):
            series[name] = h[h.index >= d - pd.Timedelta(days=365)]
    sh = da.stock_hist(target)
    if not sh.empty:
        s = sh[sh["trade_date"] <= d].set_index("trade_date")["close"]
        series[target] = s[s.index >= d - pd.Timedelta(days=365)]
        rows[target] = period_returns(s)
    c1, c2 = st.columns([1, 1.2], gap="medium")
    with c1:
        plot(charts.line_comparison(series, p), "p1_perf")
    with c2:
        keys = ["1T", "1Th", "3Th", "6Th", "YTD", "1N"]
        md(table_html(["Chỉ số / Mã"] + keys,
                      [[f'<span class="ffr-sym">{esc(n)}</span>'] + [colored(r.get(k), fmt.pct(r.get(k))) for k in keys]
                       for n, r in rows.items()], left=(0,)))
        st.caption("T = tuần · Th = tháng · N = năm · YTD = từ đầu năm. Lợi suất kỳ = P_t / P_{t−k} − 1.")


def render_footer() -> None:
    md(f'<div class="ffr-foot"><span>Nguồn: SSI FastConnect Data (chính), VPBankS NEO API (phụ) · giờ Việt Nam'
       f'{" · ĐANG DÙNG DỮ LIỆU MẪU TỔNG HỢP" if is_demo() else ""} · phương pháp tại trang "Phương pháp & giới hạn"</span>'
       f'<span>{get("app.disclaimer")}</span></div>')


def render() -> None:
    sess = da.sessions()
    c1, c2 = st.columns([5, 1.3], vertical_alignment="bottom")
    with c1:
        header("Tổng quan thị trường", "Chỉ số, độ vênh, mã dẫn dắt, dòng vốn khối ngoại và tác động lên danh mục theo dõi")
    with c2:
        date = st.selectbox("Phiên", sess[::-1], format_func=lambda d: f"Phiên {d:%d/%m/%Y}", key="p1_date",
                            label_visibility="collapsed")
    status_bar.render(date)
    about.render_intro()
    data = load_overview(date)
    render_index_cards(data)
    section("Chất lượng xu hướng hôm nay", "Chỉ số có phản ánh số đông cổ phiếu không", new=True)
    render_trend_quality(data)
    section("Danh mục theo dõi hôm nay", "Kết nối trang Watchlist Impact · bấm để xem hồ sơ")
    render_watchlist_strip(data)
    section("Diễn biến chỉ số", "Nến ngày · MA20 · MA50 · khối lượng · mốc FTSE")
    render_index_chart(data)
    section("Mã dẫn dắt VN-Index", "Đóng góp điểm C = I(t−1) × tỷ trọng vốn hóa × lợi suất", new=True)
    render_leaders(data)
    section("Độ rộng thị trường", "Đo trên rổ đã chọn · phiên đang xem")
    render_breadth(data)
    section("Bản đồ nhiệt & dòng tiền theo ngành", "Diện tích = giá trị giao dịch · màu = % thay đổi · viền đậm = |NN ròng| lớn")
    render_heatmap(data)
    section("Dòng vốn khối ngoại hôm nay", "Giá trị ròng · trạng thái khối nội · nhóm FTSE và đối chứng", new=True)
    render_foreign_today(data)
    section("Cổ phiếu nổi bật", "Toàn sàn HOSE")
    render_movers(data)
    section("So sánh hiệu suất", "Chuẩn hóa = 100 · chỉ số và mã đang chọn")
    render_performance(data)
    render_footer()
