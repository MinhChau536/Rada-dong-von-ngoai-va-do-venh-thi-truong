"""
Trang 1 – Tổng quan thị trường (bước B4.5, bảng 11.4, Hình 2a–2d).

Bố cục lưới thẻ (src/app/components/widgets.py, phong cách cổng thông tin chứng khoán):
thanh trạng thái → giới thiệu → 4 thẻ chỉ số (HOSE, VN30, HNX, UPCoM) → chất lượng xu hướng → [top 10 | nhóm dẫn dắt] →
danh mục theo dõi → diễn biến chỉ số + sức khỏe → [khối ngoại top/nhóm | diễn biến mua–bán–ròng + nhận định] →
[thanh khoản | độ rộng | ngành] → độ rộng theo rổ → bản đồ thị trường → cổ phiếu nổi bật chi tiết → so sánh hiệu suất.
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
from src.app.components import widgets as W
from src.app.components.states import empty, safe_block
from src.app.components.ui import (colored, esc, header, kpi, md, pal, plot, section, soft_chip, spark, table_html)
from src.app.theme import ABSORB_COLORS, SESSION_COLORS, color_for
from src.common import fmt
from src.common.config import events, get
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
    if True:                                                 # bỏ đồng hồ "sức khỏe" – một thang duy nhất ở trang Chẩn đoán
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
    s = s[s["tv"] >= float(get("outlook.movers_min_tv_bn", 10)) * 1e9]     # cùng bộ lọc GTGD với PDF
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
    c1, c2 = st.columns([1, 1.35], gap="medium")
    with c1:
        plot(charts.line_comparison(series, p), "p1_perf")
    with c2:
        keys = ["1T", "1Th", "3Th", "6Th", "YTD", "1N"]
        md(table_html(["Chỉ số / Mã"] + keys,
                      [[f'<span class="ffr-sym">{esc(n)}</span>'] + [colored(r.get(k), fmt.pct(r.get(k))) for k in keys]
                       for n, r in rows.items()], left=(0,)))
        st.caption("T = tuần · Th = tháng · N = năm · YTD = từ đầu năm. Lợi suất kỳ = P_t / P_{t−k} − 1.")


def render_conclusion(data: Dict) -> None:
    """Một câu kết luận của phiên (cùng logic trang Chẩn đoán) + lối sang trang Chẩn đoán."""
    from src.finance.breadth import session_type_label
    x, lead = data["day"], data["leaders"]
    v = data["stock"][data["stock"]["is_valid"]]
    main = lead[lead["side"] == ("neg" if x["dI"] < 0 else "pos")].head(2)
    nf = v["net_flow"].fillna(0)
    same = ((np.sign(nf) == np.sign(v["C"])) & (nf != 0)).astype(float)
    cod = float((v["C"].abs() * same).sum() / max(v["C"].abs().sum(), 1e-9))
    top = v[v["symbol"].isin(main["symbol"])]
    fx = ("Khối ngoại " + ("bán" if top["net_flow"].sum() < 0 else "mua") + " ròng ở chính các mã này"
          if len(top) and np.sign(top["net_flow"].sum()) == np.sign(top["C"].sum()) else "Khối ngoại không giao dịch cùng chiều ở các mã này")
    md(f'<div class="ffr-insight" style="margin-top:10px"><b>Kết luận phiên:</b> Phiên {session_type_label(x["session_type"]).lower()}. '
       f'Năm mã tạo {fmt.frac_pct(x["CR5"], 0)} biến động, dẫn đầu {", ".join(main["symbol"])}. {fx}; '
       f'{fmt.frac_pct(cod, 0)} biến động điểm đến từ các mã khối ngoại giao dịch cùng chiều giá.</div>')
    if "chan-doan" in st.session_state.get("_pages", {}):
        st.page_link(st.session_state["_pages"]["chan-doan"], label="Xem chẩn đoán đầy đủ 5 bước →", icon=":material/insights:")


def render_footer() -> None:
    md(f'<div class="ffr-foot"><span>Nguồn: SSI FastConnect V3 (REST + WebSocket) · giờ Việt Nam'
       f' · phương pháp tại trang "Phương pháp & giới hạn"</span>'
       f'<span>{get("app.disclaimer")}</span></div>')


def render() -> None:
    sess = da.sessions()
    header("Tổng quan thị trường", "Chỉ số, độ vênh, mã dẫn dắt, dòng vốn khối ngoại và tác động lên danh mục theo dõi")
    c1, c2 = st.columns([1.35, 4], vertical_alignment="center", gap="small")   # chọn phiên ngay dưới banner, cạnh thanh trạng thái
    with c1:
        date = st.selectbox("Phiên", sess[::-1], format_func=lambda d: f"📅 Phiên {d:%d/%m/%Y}", key="p1_date",
                            label_visibility="collapsed", help="Xem lại một phiên bất kỳ trong lịch sử")
    with c2:
        status_bar.render(date, show_session=False)        # ô chọn phiên bên trái đã hiện phiên
    about.render_intro()
    data, D = load_overview(date), W.load(date)
    # 1. Bốn chỉ số + chất lượng xu hướng + kết luận phiên
    render_index_cards(data)
    with W.card("p1_trend"):
        W.title("Chất lượng xu hướng hôm nay", "Chỉ số có phản ánh số đông cổ phiếu không")
        render_trend_quality(data)
        render_conclusion(data)
    # 2. Diễn biến chỉ số
    with W.card("p1_chart"):
        W.title("Diễn biến chỉ số", "Nến ngày · MA20 · MA50 · khối lượng · mốc FTSE")
        render_index_chart(data)
    # 3. Thanh khoản · độ rộng · ngành
    for i, (col, fn) in enumerate(zip(st.columns(3, gap="small"), (W.w_liquidity, W.w_breadth, W.w_sectors))):
        with col, W.card(f"p1_r3{i}"):
            fn(D)
    # 4. Top 10 cổ phiếu · nhóm dẫn dắt
    c1, c2 = st.columns([1.15, 1], gap="small")
    with c1, W.card("p1_top"):
        W.w_top(D)
    with c2, W.card("p1_lead"):
        W.w_leaders(D)
        if st.button("Xem chi tiết dẫn dắt & độ vênh →", key="p1_to_p2"):
            st.switch_page(st.session_state["_pages"]["dan-dat"])
    # 5. Khối ngoại
    c1, c2 = st.columns([1, 2], gap="small")
    with c1, W.card("p1_ft"):
        W.w_foreign_top(D)
    with c2, W.card("p1_ff"):
        W.w_foreign_flow(D)
        s = data["stock"][data["stock"]["is_valid"]]
        md(f'<div class="ffr-insight" style="margin-top:8px">{esc(narrative.foreign_summary(data["day"], s.nlargest(5, "net_flow"), s.nsmallest(5, "net_flow")))}</div>')
        if st.button("Xem Ra-đa khối ngoại →", key="p1_to_p3"):
            st.switch_page(st.session_state["_pages"]["khoi-ngoai"])
    # 6. Bản đồ thị trường + độ rộng theo rổ
    with W.card("p1_map"):
        W.w_map(D)
    with W.card("p1_basket"):
        W.title("Độ rộng theo rổ cổ phiếu", "HOSE toàn sàn · VN30 · nhóm FTSE · đối chứng · watchlist")
        render_breadth(data)
    # 7. Cổ phiếu nổi bật + so sánh hiệu suất
    with W.card("p1_movers"):
        W.title("Cổ phiếu nổi bật – bảng chi tiết", "HOSE · GTGD ≥ 10 tỷ · khối lượng, khối ngoại, hiệu suất 20 phiên")
        render_movers(data)
    with W.card("p1_perf"):
        W.title("So sánh hiệu suất", "Chuẩn hóa = 100 · chỉ số và mã đang chọn")
        render_performance(data)
    # 8. Danh mục theo dõi – cuối trang
    with W.card("p1_wl"):
        W.title("Danh mục theo dõi hôm nay", "Kết nối trang Watchlist Impact · bấm để xem hồ sơ")
        render_watchlist_strip(data)
    render_footer()
