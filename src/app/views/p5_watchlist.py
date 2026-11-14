"""Trang 5 – Watchlist Impact (bước B7.1, B7.8): quản lý danh sách; bảng hồ sơ phản ứng; so sánh hiệu suất chuẩn hóa;
phản ứng theo loại phiên; thẻ chi tiết từng mã; tin liên quan (nguồn bổ trợ)."""
from __future__ import annotations

from typing import List

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.analytics import watchlist_impact as wi
from src.app import data_access as da
from src.app.components import charts, status_bar
from src.app.components.states import empty, no_data_reason, safe_block
from src.app.components.ui import colored, esc, header, kpi, md, pal, plot, section, soft_chip, table_html
from src.app.theme import ABSORB_COLORS, SESSION_COLORS, color_for
from src.common import fmt
from src.finance.breadth import SESSION_TYPES
from src.finance.domestic import ABSORB_LABELS


@st.cache_data(ttl=60, show_spinner=False)
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
    md(f'<div class="ffr-lbl" style="margin:4px 0 6px">Danh mục đang theo dõi · {len(wl)}/{mx} mã · bấm ✕ để xóa</div>')
    if wl:
        per = 8
        for i in range(0, len(wl), per):
            cols = st.columns(per)
            for c, s in zip(cols, wl[i:i + per]):
                if c.button(f"✕  {s}", key=f"p5_del_{s}", width="stretch", help=f"Xóa {s} khỏi danh mục"):
                    wi.remove(s)
                    st.toast(f"Đã xóa {s}")
                    _changed()
    else:
        md(f'<div class="ffr-card" style="color:{p["muted"]}">Danh mục trống – thêm mã bên dưới.</div>')
    ver = st.session_state.get("p5_form_ver", 0)            # đổi key sau mỗi thao tác → ô chọn tự trống
    c1, c2, c3, c4 = st.columns([3, 1, 1, 1.2], vertical_alignment="bottom")
    new = c1.multiselect("Thêm mã", [s for s in da.symbols() if s not in wl], key=f"p5_add_many_{ver}",
                         placeholder="Chọn một hoặc nhiều mã HOSE…")
    if c2.button("➕ Thêm", width="stretch", disabled=not new, key="p5_add_btn"):
        room = mx - len(wl)
        for s in new[:max(room, 0)]:
            wi.add(s, "người dùng thêm")
        if len(new) > room:
            st.warning(f"Tối đa {mx} mã – chỉ thêm {max(room, 0)} mã đầu.")
        st.session_state["p5_form_ver"] = ver + 1
        _changed()
    confirm = c4.checkbox("Xác nhận xóa hết", key=f"p5_confirm_clear_{ver}")
    if c3.button("🗑 Xóa hết", width="stretch", disabled=not (wl and confirm), key="p5_clear_btn"):
        wi.clear()
        st.session_state["p5_form_ver"] = ver + 1
        _changed()
    sel = st.session_state.get("selected_symbol")
    if sel and sel not in wl:
        a, b, c = st.columns([4, 1.2, 1.2], vertical_alignment="center")
        a.info(f"Đang xem tạm **{sel}** (mở từ ô tra cứu / trang Tổng quan) – chưa thuộc danh mục.")
        if b.button(f"➕ Thêm {sel}", width="stretch", key="p5_add_sel"):
            wi.add(sel, "người dùng thêm")
            _changed()
        if c.button("✕ Bỏ xem tạm", width="stretch", key="p5_drop_sel"):
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


def render() -> None:
    header("Watchlist Impact", "Trạng thái thị trường và dòng vốn đã tác động thế nào đến từng mã bạn theo dõi · "
           "tối ưu danh mục theo khẩu vị rủi ro")
    status_bar.render()
    wi.ensure_default()
    wl = wi.get_watchlist()
    manage(wl)
    p = pal()
    sess = da.sessions()
    date = st.selectbox("Phiên", sess[::-1], format_func=lambda d: f"Phiên {d:%d/%m/%Y}", key="p5_date")
    sel = st.session_state.get("selected_symbol")
    syms = list(dict.fromkeys(wl + ([sel] if sel and sel not in wl else [])))
    if not syms:
        empty("Danh mục trống – thêm mã ở mục Quản lý.")
        return
    data = profiles(tuple(syms), date)
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
        section("Phản ứng theo loại phiên", "Lợi suất trung bình (%) của mã trong từng loại phiên – RQ4")
        rx = data["reaction"]
        fig = go.Figure()
        for code, lbl in SESSION_TYPES.items():
            r = rx[rx["session_type"] == code]
            fig.add_trace(go.Bar(x=r["symbol"], y=r["mean_ret_pct"], name=lbl, marker_color=SESSION_COLORS[code],
                                 customdata=r["n"], hovertemplate="%{x}: %{y:.2f}% (%{customdata} phiên)<extra>" + lbl + "</extra>"))
        fig.update_layout(barmode="group")
        plot(charts._lay(fig, p, 330), "p5_react")
        kw = data["stats"]
        if not kw.empty:
            k = kw[kw["test"] == "Kruskal–Wallis"]
            st.caption("Kruskal–Wallis (chỉ khi mỗi loại ≥ 15 phiên): " + " · ".join(
                f"{r.group}: p = {fmt.num(r.p_value, 4)}" for r in k.itertuples()))
    from src.app.views import p5_portfolio
    p5_portfolio.render(wl, date)
    section("Chi tiết từng mã")
    pick = st.selectbox("Mã", syms, index=syms.index(sel) if sel in syms else 0, key="p5_pick")
    r = pf[pf["symbol"] == pick].iloc[0]
    if not r["has_data"]:
        empty(no_data_reason(date, pick))
        return
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
    h = da.stock_hist(pick)
    h = h[h["trade_date"] <= date].tail(120)
    plot(charts.line(h.assign(nf_ma=h["nf"].rolling(5).mean()), "trade_date", {"nf": "nf", "nf_ma": "nf trung bình 5 phiên"}, p,
                     260, f"Dòng vốn ngoại chuẩn hóa nf của {pick} – 120 phiên"), "p5_nf")
    with st.expander("📰 Tin liên quan (nguồn ngoài SSI – Google News RSS)"):
        from src.analytics.news import latest
        items = latest(pick)
        if not items:
            st.caption("Không lấy được tin (mạng bị chặn hoặc chưa có tin).")
        for it in items:
            st.markdown(f"- [{it['title']}]({it['link']}) · _{it['source']}_ · {it['date']}")
        st.caption("Nhãn: Nguồn ngoài SSI – chỉ để tham khảo bối cảnh.")
