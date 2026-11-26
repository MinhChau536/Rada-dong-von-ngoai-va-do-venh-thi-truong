"""Trang 5 – Watchlist Impact (bước B7.1, B7.8): quản lý danh sách; bảng hồ sơ phản ứng; so sánh hiệu suất chuẩn hóa;
phản ứng theo loại phiên; thẻ chi tiết từng mã."""
from __future__ import annotations

from typing import List

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.analytics import watchlist_impact as wi
from src.app import data_access as da
from src.app.components import charts, status_bar
from src.app.components.states import empty, no_data_reason, safe_block
from src.app.components.ui import colored, esc, header, kpi, md, pal, plot, section, soft_chip, table_html
from src.app.theme import ABSORB_COLORS, WEB_SESSION_COLORS as SESSION_COLORS, color_for
from src.common import fmt
from src.finance.breadth import SESSION_TYPES
from src.finance.domestic import ABSORB_LABELS


@st.cache_data(ttl=60, show_spinner=False)

def _ro() -> bool:
    """Bản công khai: danh mục theo dõi chỉ xem (không cho khách sửa danh mục dùng chung)."""
    from src.common.config import public_mode
    return public_mode()

def profiles(symbols: tuple, date) -> dict:
    d = pd.Timestamp(date)
    day = da.daily()
    st_all = da.stock_day(d)
    hist = pd.concat([da.stock_hist(s) for s in symbols] + [st_all], ignore_index=True)
    hist = hist.drop_duplicates(["trade_date", "symbol"])
    intra = da.table("fact_intraday")
    res = wi.compute(hist, day, intra, list(symbols), as_of=d)
    return {"profile": res["profile"], "reaction": res["reaction"], "stats": res["stats"]}


def _changed() -> None:
    da.clear_cache()
    st.cache_data.clear()
    st.rerun()


def manage(wl: List[str]) -> None:
    """Quản lý danh mục: mỗi mã có nút ✕ xóa ngay; thêm nhiều mã cùng lúc; xóa hết / khôi phục mặc định."""
    from src.common.config import get
    p = pal()
    mx = int(get("watchlist_max", 15))
    md(f'<div class="ffr-lbl" style="margin:4px 0 6px">Danh mục đang theo dõi · {len(wl)}/{mx} mã · bấm vào mã để xóa</div>')
    if wl:
        per = 8
        for i in range(0, len(wl), per):
            cols = st.columns(per)
            for c, s in zip(cols, wl[i:i + per]):
                if c.button(s, icon=":material/close:", key=f"p5_del_{s}", width="stretch", help=f"Xóa {s} khỏi danh mục", disabled=_ro()):
                    wi.remove(s)
                    st.toast(f"Đã xóa {s}")
                    _changed()
    else:
        md(f'<div class="ffr-card" style="color:{p["muted"]}">Danh mục trống – thêm mã bên dưới.</div>')
    ver = st.session_state.get("p5_form_ver", 0)            # đổi key sau mỗi thao tác → ô chọn tự trống
    c1, c2, c3, c4 = st.columns([3, 1, 1, 1.2], vertical_alignment="bottom")
    new = c1.multiselect("Thêm mã", [s for s in da.symbols() if s not in wl], key=f"p5_add_many_{ver}",
                         placeholder="Chọn một hoặc nhiều mã HOSE…")
    if c2.button("Thêm", icon=":material/add:", width="stretch", disabled=not new or _ro(), key="p5_add_btn"):
        room = mx - len(wl)
        for s in new[:max(room, 0)]:
            wi.add(s, "người dùng thêm")
        if len(new) > room:
            st.warning(f"Tối đa {mx} mã – chỉ thêm {max(room, 0)} mã đầu.")
        st.session_state["p5_form_ver"] = ver + 1
        _changed()
    confirm = c4.checkbox("Xác nhận xóa hết", key=f"p5_confirm_clear_{ver}")
    if c3.button("Xóa hết", icon=":material/delete:", width="stretch", disabled=not (wl and confirm) or _ro(), key="p5_clear_btn"):
        wi.clear()
        st.session_state["p5_form_ver"] = ver + 1
        _changed()
    sel = st.session_state.get("selected_symbol")
    if sel and sel not in wl:
        a, b, c = st.columns([4, 1.2, 1.2], vertical_alignment="center")
        a.info(f"Đang xem tạm **{sel}** (mở từ ô tra cứu / trang Tổng quan) – chưa thuộc danh mục.")
        if b.button(f"Thêm {sel}", icon=":material/add:", width="stretch", key="p5_add_sel", disabled=_ro()):
            wi.add(sel, "người dùng thêm")
            _changed()
        if c.button("Bỏ xem tạm", icon=":material/close:", width="stretch", key="p5_drop_sel"):
            st.session_state.pop("selected_symbol", None)
            st.rerun()
    st.caption("Danh mục lưu trong DuckDB (bảng watchlist) – giữ nguyên sau khi tải lại trang và dùng chung với bot Telegram. "
               "Không đọc tài khoản giao dịch.")


@safe_block("bảng hồ sơ")
def profile_table(pf: pd.DataFrame) -> None:
    p = pal()
    rows = []
    for r in pf.itertuples():
        if not r.has_data:
            rows.append([f'<span class="ffr-sym">{r.symbol}</span>'] + ["—"] * 10 + [no_data_reason(symbol=r.symbol)])
            continue
        rows.append([f'<span class="ffr-sym">{r.symbol}</span>', fmt.price(r.close), colored(r.ret, fmt.pct(r.ret * 100)),
                     colored(r.ER_I, fmt.num(r.ER_I * 100, 2, True)), colored(r.ER_M, fmt.num(r.ER_M * 100, 2, True)),
                     colored(r.C, fmt.num(r.C, 2, True)) + (f" <small>#{r.leader_rank}</small>" if r.leader_rank and r.leader_rank <= 10 else ""),
                     colored(r.net_flow, fmt.bn(r.net_flow, 1)), fmt.num(r.pct60_nf, 0), f"{int(r.streak):+d}",
                     soft_chip(ABSORB_LABELS[r.absorb_state], ABSORB_COLORS[r.absorb_state]),
                     fmt.frac_pct(r.U, 1), f"{fmt.num(r.beta_dimson, 2)} / {fmt.num(r.beta_intraday, 2)}"])
    md(table_html(["Mã", "Giá", "%", "ERᴵ (đ.%)", "ERᴹ (đ.%)", "Đóng góp (đ)", "NN ròng", "Phân vị nf 60", "Chuỗi",
                   "Hấp thụ", "Room", "βᴰ / βᴵᴰ"], rows, left=(0,)))


@st.cache_data(ttl=600, show_spinner=False)
def company_info(symbol: str, date) -> dict:
    """Thông tin nguồn lực doanh nghiệp từ SSI FastConnect V3: danh mục chứng khoán (tên, ngành ICB, số CP niêm yết)
    + lịch sử giao dịch trong kho (vốn hóa, room ngoại, thanh khoản, tỷ trọng VN-Index)."""
    import json
    from src.data import database as db
    raw = db.query_df("SELECT payload FROM raw_securities WHERE symbol = ? ORDER BY as_of DESC LIMIT 1", [symbol])
    meta = json.loads(raw["payload"].iat[0]) if not raw.empty else {}
    h = da.stock_hist(symbol)
    h = h[h["trade_date"] <= pd.Timestamp(date)]
    if h.empty:
        return {"symbol": symbol, "meta": meta}
    last = h.iloc[-1]
    y = h.tail(250)
    shares = float(meta.get("listedShare") or last.get("listed_share") or np.nan)
    tv20 = float(h["tv"].tail(20).mean())
    first = pd.Timestamp(meta.get("firstTradingDate")) if meta.get("firstTradingDate") else pd.Timestamp(h["trade_date"].iloc[0])
    groups = [lbl for key, lbl in (("VN30", "VN30"), ("FTSE", "Nhóm FTSE (dự kiến)"), ("CONTROL", "Nhóm đối chứng"))
              if symbol in da.universe(key)]
    return {"symbol": symbol, "meta": meta, "name": meta.get("symbolNameVi") or symbol, "icb": meta.get("icbName") or "—",
            "sector": last.get("sector") or "—", "family": last.get("family") if isinstance(last.get("family"), str) else None,
            "first": first, "first_is_data": not meta.get("firstTradingDate"), "close": float(last["close"]),
            "shares": shares, "mcap": float(last["close"]) * shares if shares == shares else np.nan,
            "w": float(last.get("w") or np.nan), "room": float(last.get("room") or np.nan),
            "remain": float(last.get("remain") or np.nan), "U": float(last.get("U") or np.nan),
            "tv20": tv20,
            "ret1y": float(y["close"].iloc[-1] / y["close"].iloc[0] - 1) * 100 if len(y) > 1 else np.nan,
            "vol1y": float(y["ret"].std() * np.sqrt(250) * 100), "groups": groups, "n_sessions": len(h)}


def company_card(ci: dict) -> None:
    """Khối đầu tab mã: tên, ngành, niêm yết, vốn hóa, cổ phiếu niêm yết, room ngoại, thanh khoản."""
    p = pal()
    if "close" not in ci:
        empty(no_data_reason(None, ci["symbol"]))
        return
    tags = "".join(f'<span class="ffr-chip" style="background:var(--ffr-soft);color:var(--ffr-accent);border:1px solid var(--ffr-border);margin-right:6px">{esc(g)}</span>'
                   for g in ci["groups"] + ([f"Họ {ci['family']}"] if ci.get("family") else []))
    years = (pd.Timestamp.today() - ci["first"]).days / 365.25
    since = (f"từ {ci['first']:%d/%m/%Y}" + (" (đầu kho dữ liệu)" if ci["first_is_data"] else "")
             + (f" · {years:.0f} năm" if not ci["first_is_data"] else ""))
    tiles = [("Vốn hóa", fmt.bn(ci["mcap"], 0, False), f"giá {fmt.price(ci['close'])} × số CP niêm yết"),
             ("Cổ phiếu niêm yết", fmt.num(ci["shares"] / 1e6, 1, False, " tr"), "SSI danh mục chứng khoán"),
             ("Tỷ trọng VN-Index", fmt.num(ci["w"] * 100, 2, False, "%"), "vốn hóa / tổng rổ VN-Index"),
             ("Room ngoại đã dùng", fmt.frac_pct(ci["U"], 1), f"còn {fmt.num(ci['remain'] / 1e6, 1, False, ' tr')} / "
                                                             f"{fmt.num(ci['room'] / 1e6, 1, False, ' tr')} CP"),
             ("GTGD TB 20 phiên", fmt.bn(ci["tv20"], 1, False), "thanh khoản khớp lệnh"),
             ("Lợi suất 1 năm", fmt.pct(ci["ret1y"], 1), f"biến động năm {fmt.num(ci['vol1y'], 1, False, '%')}")]
    tile_html = "".join(f'<div class="wl-tile"><small>{l}</small><b>{v}</b><span>{sub}</span></div>' for l, v, sub in tiles)
    md(f'<div class="wl-co"><div class="wl-co-head"><div><div class="wl-co-sym">{esc(ci["symbol"])}</div>'
       f'<div class="wl-co-name">{esc(ci["name"])}</div>'
       f'<div class="wl-co-meta">HOSE · {esc(ci["sector"])} · ICB: {esc(ci["icb"])} · niêm yết/giao dịch {since}</div>'
       f'<div style="margin-top:8px">{tags}</div></div>'
       f'</div><div class="wl-tiles">{tile_html}</div>'
       f'<div class="wl-co-note">Nguồn: SSI FastConnect V3 (danh mục chứng khoán + giao dịch ngày). Vốn hóa tính theo số cổ phiếu niêm yết, '
       f'chưa trừ cổ phiếu quỹ; {ci["n_sessions"]} phiên có trong kho.</div></div>')


WL_CSS = """<style>
.wl-co { border:1px solid var(--ffr-border); border-radius:16px; padding:20px 24px; margin:6px 0 16px; background:var(--ffr-card); }
.wl-co-head { display:flex; justify-content:space-between; gap:20px; flex-wrap:wrap; }
.wl-co-sym { font-size:30px; font-weight:600; color:var(--ffr-accent); letter-spacing:-.01em; line-height:1; }
.wl-co-name { font-size:16px; font-weight:700; margin-top:6px; }
.wl-co-meta, .wl-co-note { font-size:13px; color:var(--ffr-muted); margin-top:4px; }
.wl-co-note { margin-top:10px; font-style:italic; }
.wl-tile small { font-size:13px; font-weight:500; color:var(--ffr-muted); }
.wl-tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:10px; margin-top:14px; }
.wl-tile { border:1px solid rgba(148,163,184,.18); border-radius:12px; padding:10px 12px; background:rgba(255,255,255,.03); }
.wl-tile b { display:block; font-size:19px; font-weight:600; margin:4px 0 2px; font-variant-numeric:tabular-nums; }
.wl-tile span { font-size:13px; opacity:.7; }
</style>"""


def overview_tab(syms, wl, data, date) -> None:
    p = pal()
    pf = data["profile"]
    section("Hồ sơ phản ứng hôm nay", "ERᴵ = r − r_VNI · ERᴹ = r − trung vị thị trường · β Dimson 120 phiên · β nội ngày 5 phút vs VN30")
    profile_table(pf)
    for s in pf.itertuples():
        md(f'<div style="font-size:13px;margin:3px 0">• {esc(s.sentence)}</div>')
    st.caption("Câu nhận định sinh từ khuôn câu cố định (không dùng mô hình ngôn ngữ) – thông tin phân tích, không phải khuyến nghị.")
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        section("So sánh hiệu suất chuẩn hóa = 100", "Mã watchlist so với VN-Index, VN30 (1 năm)")
        series = {}
        d0 = pd.Timestamp(date) - pd.Timedelta(days=365)
        for code, name in (("VNINDEX", "VN-Index"), ("VN30", "VN30")):
            h = da.index_hist(code).set_index("trade_date")["value"]
            series[name] = h[(h.index >= d0) & (h.index <= date)]
        for s in syms[:4]:
            h = da.stock_hist(s).set_index("trade_date")["close"]
            series[s] = h[(h.index >= d0) & (h.index <= date)]
        plot(charts.line_comparison(series, p), "p5_perf")
    with c2:
        section("Phản ứng theo loại phiên", "Lợi suất VƯỢT TRỘI so với trung vị thị trường (ERᴹ, điểm %) – RQ4")
        rx = data["reaction"]
        fig = go.Figure()
        for code, lbl in SESSION_TYPES.items():
            r = rx[rx["session_type"] == code]
            fig.add_trace(go.Bar(x=r["symbol"], y=r["mean_er_pct"], name=lbl, marker_color=SESSION_COLORS[code],
                                 customdata=r["n"], hovertemplate="%{x}: %{y:.2f}% (%{customdata} phiên)<extra>" + lbl + "</extra>"))
        fig.update_layout(barmode="group")
        plot(charts._lay(fig, p, 330), "p5_react")
        kw = data["stats"]
        if not kw.empty:
            k = kw[kw["test"] == "Kruskal–Wallis"]
            st.caption("Kruskal–Wallis trên ERᴹ (chỉ khi mỗi loại ≥ 15 phiên; p < 0,05: mã phản ứng KHÁC thị trường theo loại phiên): " + " · ".join(
                f"{r.group}: p = {fmt.num(r.p_value, 4)}" for r in k.itertuples()))
    exposure_block(wl, data, date)


@safe_block("mức phơi nhiễm")
def exposure_block(wl, data, date) -> None:
    """Mức phơi nhiễm của watchlist với nhóm dẫn dắt – trả lời câu "tác động lên danh mục theo dõi" của đề tài."""
    from src.analytics import diagnosis as dg
    p = pal()
    if not wl:
        return
    hist = pd.concat([da.stock_hist(s) for s in wl], ignore_index=True)
    e = dg.watch_exposure(wl, date, hist, da.daily(), data["profile"], market=da.stock_day(date))
    section("Mức phơi nhiễm của watchlist", "Watchlist chịu tác động của nhóm dẫn dắt và độ vênh chỉ số đến đâu")
    cols = st.columns(4)
    items = [kpi("Mã trong nhóm dẫn dắt", f"{len(e['lead'])}/{e['n']}", None, ", ".join(e["lead"]) or "không mã nào trong 10 mã |C| lớn nhất toàn sàn"),
             kpi("Mã thuộc họ Vingroup", f"{len(e['vin'])}/{e['n']}", None, ", ".join(e["vin"]) or "—"),
             kpi("β Dimson bình quân", fmt.num(e["beta"], 2), None, ">1: biến động mạnh hơn thị trường"),
             kpi("Thua trung vị khi D cao", fmt.frac_pct(e["lose_hiD"], 0),
                 p["down"] if (e["lose_hiD"] or 0) > 0.5 else p["up"],
                 f"{e['n_hiD']} phiên D ≥ phân vị 80 · ERᴹ TB {fmt.num(e['er_hiD'], 2, True)} đ.%")]
    for c, h in zip(cols, items):
        with c:
            md(h)
    st.caption("Phiên D cao = độ vênh ở phân vị ≥ 80 của 250 phiên trước (chỉ số bị kéo bởi nhóm vốn hóa lớn). "
               "Tỷ lệ thua cao nghĩa là khi chỉ số 'đẹp' nhờ vài mã lớn, danh mục này thường không đi theo.")


def symbol_tab(pick: str, data, date) -> None:
    """Tab riêng một mã: thông tin doanh nghiệp → chỉ số phiên → giá & dòng vốn ngoại → phản ứng theo loại phiên."""
    p = pal()
    company_card(company_info(pick, date))
    pf = data["profile"]
    rr = pf[pf["symbol"] == pick]
    if rr.empty or not rr.iloc[0]["has_data"]:
        empty(no_data_reason(date, pick))
        return
    r = rr.iloc[0]
    section(f"Phiên {pd.Timestamp(date):%d/%m/%Y}", f"{pick} so với thị trường, đóng góp chỉ số và khối ngoại")
    cols = st.columns(6)
    items = [kpi("Lợi suất", fmt.pct(r["ret"] * 100), color_for(r["ret"], p), f"vs trung vị {fmt.num(r['ER_M'] * 100, 2, True)} đ.%"),
             kpi("Đóng góp VN-Index", fmt.num(r["C"], 2, True, " đ"), color_for(r["C"], p),
                 f"hạng dẫn dắt #{r['leader_rank']}" if pd.notna(r["leader_rank"]) else ""),
             kpi("NN ròng", fmt.bn(r["net_flow"], 1), color_for(r["net_flow"], p), f"z60 = {fmt.num(r['z_nf'], 2, True)}"),
             kpi("Room đã dùng", fmt.frac_pct(r["U"], 1), p["down"] if (r["U"] or 0) >= 0.95 else None),
             kpi("β OLS / Dimson", f"{fmt.num(r['beta_ols'], 2)} / {fmt.num(r['beta_dimson'], 2)}"),
             kpi("Loại phiên hôm nay", SESSION_TYPES.get(r["today_type"], "—"), None,
                 f"TB mã trong loại này: {fmt.pct(r['today_type_mean_pct'])} ({int(r['today_type_n'])} phiên)")]
    for c, h in zip(cols, items):
        with c:
            md(h)
    md(f'<div class="ffr-insight" style="margin:10px 0">{esc(r["sentence"])}</div>')
    h = da.stock_hist(pick)
    h = h[h["trade_date"] <= date].tail(250).copy()
    c1, c2 = st.columns([1.4, 1], gap="medium")
    with c1:
        section("Giá đóng cửa 250 phiên", "MA20 · MA50 · khối lượng")
        full = da.stock_hist(pick)
        full = full[full["trade_date"] <= date]
        h["ma20"] = full["close"].rolling(20).mean().tail(250).values
        h["ma50"] = full["close"].rolling(50).mean().tail(250).values
        fig = go.Figure()
        fig.add_bar(x=h["trade_date"], y=h["vol"] / 1e6, name="KL (triệu CP)", yaxis="y2", marker_color="rgba(148,163,184,.35)")
        fig.add_scatter(x=h["trade_date"], y=h["close"], name="Giá", line=dict(color=p["accent"], width=2))
        fig.add_scatter(x=h["trade_date"], y=h["ma20"], name="MA20", line=dict(color=p["ma20"], width=1.2))
        fig.add_scatter(x=h["trade_date"], y=h["ma50"], name="MA50", line=dict(color=p["ma50"], width=1.2))
        plot(charts._lay(fig, p, 340, hovermode="x unified", legend=dict(orientation="h", y=-0.15, x=0),
                         yaxis2=dict(overlaying="y", side="right", showgrid=False, range=[0, float(h["vol"].max() / 1e6 * 4 or 1)]),
                         margin=dict(l=8, r=8, t=10, b=8)), f"p5_px_{pick}")
    with c2:
        section("Khối ngoại 60 phiên", "Ròng (tỷ đồng) · lũy kế")
        f = h.tail(60)
        fig = go.Figure()
        fig.add_bar(x=f["trade_date"], y=f["net_flow"] / 1e9, name="Ròng", marker_color=[color_for(v, p) for v in f["net_flow"].fillna(0)])
        fig.add_scatter(x=f["trade_date"], y=(f["net_flow"].fillna(0) / 1e9).cumsum(), name="Lũy kế", yaxis="y2",
                        line=dict(color=p["text"], width=2))
        plot(charts._lay(fig, p, 340, legend=dict(orientation="h", y=-0.15, x=0),
                         yaxis2=dict(overlaying="y", side="right", showgrid=False), margin=dict(l=8, r=8, t=10, b=8)), f"p5_ff_{pick}")
    c1, c2 = st.columns([1.4, 1], gap="medium")
    with c1:
        hh = h.tail(120)
        plot(charts.line(hh.assign(nf_ma=hh["nf"].rolling(5).mean()), "trade_date", {"nf": "nf", "nf_ma": "nf trung bình 5 phiên"}, p,
                         280, f"Dòng vốn ngoại chuẩn hóa nf của {pick} – 120 phiên"), f"p5_nf_{pick}")
    with c2:
        rx = data["reaction"]
        rx = rx[rx["symbol"] == pick]
        lbl = [SESSION_TYPES.get(c, c).replace(" ", "<br>", 1) for c in rx["session_type"]]   # nhãn 2 dòng, không xoay/cắt chữ
        fig = go.Figure(go.Bar(x=lbl, y=rx["mean_er_pct"],
                               marker_color=[SESSION_COLORS.get(c, p["muted"]) for c in rx["session_type"]],
                               text=[fmt.num(v, 2, True) for v in rx["mean_er_pct"]], textposition="outside", cliponaxis=False,
                               customdata=rx["n"], hovertemplate="%{x}: %{y:.2f}% (%{customdata} phiên)<extra></extra>"))
        fig.update_layout(title=f"{pick} hơn/kém trung vị thị trường theo loại phiên (ERᴹ TB, điểm %)")
        charts._lay(fig, p, 300, showlegend=False)
        fig.update_xaxes(tickangle=0, tickfont=dict(size=11))
        plot(fig, f"p5_rx_{pick}")


def render() -> None:
    header("Watchlist Impact", "Trạng thái thị trường và dòng vốn đã tác động thế nào đến từng mã bạn theo dõi · "
           "mức phơi nhiễm với nhóm dẫn dắt")
    status_bar.render()
    st.markdown(WL_CSS, unsafe_allow_html=True)
    wi.ensure_default()
    wl = wi.get_watchlist()
    manage(wl)
    sess = da.sessions()
    date = st.selectbox("Phiên", sess[::-1], format_func=lambda d: f"Phiên {d:%d/%m/%Y}", key="p5_date")
    sel = st.session_state.get("selected_symbol")
    # mã đang xem tạm (mở từ ô tra cứu) đứng ngay sau tab tổng quan
    syms = list(dict.fromkeys(([sel] if sel and sel not in wl else []) + wl))
    if not syms:
        empty("Danh mục trống – thêm mã ở mục Quản lý.")
        return
    data = profiles(tuple(syms), date)
    tabs = st.tabs(["Toàn danh mục"] + [f"{s}" + (" (xem tạm)" if s not in wl else "") for s in syms])
    with tabs[0]:
        overview_tab(syms, wl, data, date)
    for t, s in zip(tabs[1:], syms):
        with t:
            symbol_tab(s, data, date)
