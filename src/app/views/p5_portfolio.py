"""Khối "Tối ưu danh mục theo khẩu vị rủi ro" của trang Watchlist (src/analytics/portfolio.py)."""
from __future__ import annotations

from typing import List

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.analytics import portfolio as P
from src.analytics import watchlist_impact as wi
from src.app.components import charts
from src.app.components.ui import colored, esc, kpi, md, pal, plot, section, table_html
from src.app.theme import color_for
from src.common import fmt
from src.common.config import get

LOOKBACKS = {"6 tháng": 125, "1 năm": 250, "2 năm": 500}
METHOD_COLORS = {"equal": "#94A3B8", "min_var": "#0891B2", "risk_parity": "#7C3AED", "max_sharpe": "#F59E0B", "target": "#DC2626"}


@st.cache_data(ttl=600, show_spinner="Đang tối ưu danh mục…")
def _analyze(symbols: tuple, profile: str, date, lookback: int, max_w: float, tv: float):
    a = P.analyze(list(symbols), profile, date, lookback, max_w, tv)
    if not a["ok"]:
        return a
    a["frontier"] = P.frontier(a["est"], a["max_w"])
    a["div"] = P.diversifiers(a["port_ret"], list(symbols), date, lookback)
    return a


@st.cache_data(ttl=600, show_spinner="Đang kiểm chứng ngoài mẫu…")
def _backtest(symbols: tuple, date, lookback: int, max_w: float, tv: float) -> pd.DataFrame:
    months = int(get("portfolio.backtest_months", 24))
    rf = float(get("portfolio.risk_free", 0.045))
    out = {}
    for k in ("target", "min_var", "equal"):
        s = P.walk_forward(list(symbols), k, max_w, tv, date, lookback, months, rf)
        if not s.empty:
            out[P.METHODS[k]] = s
    if not out:
        return pd.DataFrame()
    df = pd.DataFrame(out).dropna()
    m = P.market_returns(date, 5000)
    df["VN-Index"] = m.reindex(df.index).fillna(0)
    return df


def _pct(v, d=1):
    return fmt.pct(None if v is None or pd.isna(v) else v * 100, d)


def backtest_block(wl: List[str], date, lookback: int, mw: float, tv: float, key: str = "pf_bt") -> pd.DataFrame:
    """Walk-forward: tái cân bằng đầu mỗi tháng chỉ bằng dữ liệu trước thời điểm đó; so với VN-Index."""
    p = pal()
    bt = _backtest(tuple(sorted(wl)), date, int(lookback), float(mw), float(tv))
    if bt.empty:
        st.info("Chưa đủ dữ liệu để kiểm chứng ngoài mẫu (cần ≥ 2 mã có lịch sử đủ dài).")
        return bt
    cum = (1 + bt).cumprod() * 100
    fig = go.Figure()
    for c in cum.columns:
        fig.add_trace(go.Scatter(x=cum.index, y=cum[c], name=c, mode="lines",
                                 line=dict(width=2.6 if c == P.METHODS["target"] else 1.6,
                                           dash="dot" if c == "VN-Index" else None)))
    fig.update_layout(title="Giá trị danh mục ngoài mẫu (= 100 lúc bắt đầu)")
    plot(charts._lay(fig, p, 360), key)
    ann = (1 + bt).prod() ** (250 / len(bt)) - 1
    vol_ = bt.std() * np.sqrt(250)
    mdd = ((1 + bt).cumprod() / (1 + bt).cumprod().cummax() - 1).min()
    sharpe = (ann - float(get("portfolio.risk_free", 0.045))) / vol_
    excess = ann - ann["VN-Index"]
    md(table_html(["Ngoài mẫu", "Lợi suất năm", "Biến động năm", "Sharpe", "Sụt giảm tối đa", "Hơn/kém VN-Index", "Số phiên"],
                  [[f"<b>{c}</b>", colored(ann[c], _pct(ann[c])), _pct(vol_[c]), fmt.num(sharpe[c], 2), _pct(mdd[c]),
                    "—" if c == "VN-Index" else colored(excess[c], _pct(excess[c])), str(len(bt))] for c in bt.columns],
                  left=(0,)))
    return bt


def render(wl: List[str], date) -> None:
    p = pal()
    section("Tối ưu danh mục theo khẩu vị rủi ro",
            "Phân bổ tỷ trọng cho các mã đang theo dõi · kiểm chứng ngoài mẫu · gợi ý đa dạng hóa", new=True)
    if len(wl) < 2:
        md(f'<div class="ffr-card" style="color:{p["muted"]}">Cần ít nhất 2 mã trong danh mục để tối ưu.</div>')
        return
    profs = P.profiles()
    c1, c2, c3, c4 = st.columns([2.2, 1.2, 1.3, 1.3])
    choice = c1.segmented_control("Khẩu vị rủi ro", list(profs) + ["Tùy chỉnh"], default="Cân bằng", key="pf_prof") or "Cân bằng"
    lb = c2.selectbox("Dữ liệu ước lượng", list(LOOKBACKS), index=1, key="pf_lb")
    base = profs["Cân bằng" if choice == "Tùy chỉnh" else choice]
    if choice == "Tùy chỉnh":
        tv = c3.slider("Biến động năm tối đa", 0.08, 0.50, base.target_vol, 0.01, format="%.2f", key="pf_tv")
        mw = c4.slider("Tỷ trọng tối đa 1 mã", 0.10, 1.0, base.max_weight, 0.05, format="%.2f", key="pf_mw")
    else:
        tv, mw = base.target_vol, base.max_weight
        c3.markdown(kpi("Biến động mục tiêu", f"≤ {tv:.0%}/năm"), unsafe_allow_html=True)
        c4.markdown(kpi("Trần tỷ trọng", f"{mw:.0%}/mã"), unsafe_allow_html=True)
    st.caption(f"Khẩu vị **{choice}**: {base.note if choice != 'Tùy chỉnh' else 'tự đặt mức biến động và trần tỷ trọng.'}")
    a = _analyze(tuple(sorted(wl)), base.name, date, LOOKBACKS[lb], float(mw), float(tv))
    if not a["ok"]:
        st.warning(a["reason"])
        return
    if a["dropped"]:
        st.caption("Loại khỏi tối ưu do thiếu dữ liệu: " + ", ".join(a["dropped"]))
    res, syms = a["results"], a["est"]["symbols"]
    t = res["target"]
    if (a["est"]["mu"] < 0).all():
        st.warning("Tất cả các mã đều có lợi suất trung bình âm trong cửa sổ ước lượng – lợi suất kỳ vọng dựa trên quá khứ "
                   "nên mọi phương án đều âm. Hãy ưu tiên phương án rủi ro thấp và xem phần kiểm chứng ngoài mẫu.")
    cols = st.columns(6)
    items = [kpi("Lợi suất kỳ vọng/năm", _pct(t["ret"]), color_for(t["ret"], p), "trung bình lịch sử, đã co"),
             kpi("Biến động/năm", _pct(t["vol"]), p["down"] if t["vol"] > tv * 1.05 else p["up"], f"mục tiêu ≤ {tv:.0%}"),
             kpi("Sharpe", fmt.num(t["sharpe"], 2), color_for(t["sharpe"], p), f"rf = {a['rf']:.1%}"),
             kpi("Beta với VN-Index", fmt.num(t["beta"], 2), None, f"phù hợp ≤ {base.max_beta:.1f}"),
             kpi("Sụt giảm tối đa", _pct(t["mdd"]), p["down"], f"{a['d0']:%m/%Y} – {a['d1']:%m/%Y}"),
             kpi("VaR 95% 1 ngày", _pct(t["var95"], 2), p["down"], f"CVaR {_pct(t['cvar95'], 2)}")]
    for c, h in zip(cols, items):
        with c:
            md(h)

    g1, g2 = st.columns([1.1, 1], gap="medium")
    with g1:
        rows = []
        for s in syms:
            rows.append([f'<span class="ffr-sym">{s}</span>'] +
                        [f'<b>{res[k]["w"][s]:.0%}</b>' if k == "target" else f'{res[k]["w"][s]:.0%}' for k in P.METHODS])
        for lbl, key, f in (("Lợi suất kỳ vọng", "ret", _pct), ("Biến động", "vol", _pct), ("Sharpe", "sharpe", lambda v: fmt.num(v, 2)),
                            ("Sụt giảm tối đa", "mdd", _pct), ("Số mã hiệu dụng", "eff_n", lambda v: fmt.num(v, 1))):
            rows.append([f"<i>{lbl}</i>"] + [f(res[k][key]) for k in P.METHODS])
        md(table_html(["Tỷ trọng"] + list(P.METHODS.values()), rows, left=(0,)))
        st.caption("Phương án in đậm = theo khẩu vị đã chọn. Hiệp phương sai co Ledoit–Wolf; lợi suất kỳ vọng = trung bình "
                   "lịch sử co 50% về trung bình chung để giảm sai số ước lượng.")
    with g2:
        fr = a["frontier"]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=fr["vol"] * 100, y=fr["ret"] * 100, mode="lines", name="Biên hiệu quả",
                                 line=dict(color=p["accent"], width=2.5)))
        sd = np.sqrt(np.diag(a["est"]["cov"]))
        fig.add_trace(go.Scatter(x=sd * 100, y=a["est"]["mu"] * 100, mode="markers+text", text=syms, textposition="top center",
                                 name="Từng mã", marker=dict(color=p["muted"], size=8)))
        for k, lbl in P.METHODS.items():
            fig.add_trace(go.Scatter(x=[res[k]["vol"] * 100], y=[res[k]["ret"] * 100], mode="markers", name=lbl,
                                     marker=dict(color=METHOD_COLORS[k], size=13 if k == "target" else 10,
                                                 symbol="star" if k == "target" else "diamond")))
        fig.add_vline(x=tv * 100, line_dash="dot", line_color="#DC2626", annotation_text=f"mục tiêu {tv:.0%}")
        fig.update_layout(xaxis_title="Biến động năm (%)", yaxis_title="Lợi suất kỳ vọng năm (%)")
        plot(charts._lay(fig, p, 360), "pf_frontier")

    h1, h2 = st.columns(2, gap="medium")
    with h1:
        rc = pd.Series(t["risk_contrib"], index=syms)
        fig = go.Figure()
        fig.add_trace(go.Bar(x=syms, y=t["w"].values * 100, name="Tỷ trọng (%)", marker_color=p["accent"]))
        fig.add_trace(go.Bar(x=syms, y=rc.values * 100, name="Đóng góp rủi ro (%)", marker_color="#F59E0B"))
        fig.update_layout(barmode="group", title="Tỷ trọng và đóng góp rủi ro – phương án theo khẩu vị")
        plot(charts._lay(fig, p, 320), "pf_rc")
    with h2:
        cm = a["corr"]
        fig = go.Figure(go.Heatmap(z=cm.values, x=cm.columns, y=cm.index, zmin=-1, zmax=1, colorscale="RdBu_r",
                                   text=np.round(cm.values, 2), texttemplate="%{text}", showscale=False))
        fig.update_layout(title="Tương quan lợi suất ngày")
        plot(charts._lay(fig, p, 320), "pf_corr")

    pages = st.session_state.get("_pages", {})
    if "backtest" in pages:
        st.page_link(pages["backtest"], label="Kiểm chứng ngoài mẫu (walk-forward) của danh mục này → trang Backtest",
                     icon=":material/history:")

    s1, s2 = st.columns([1.2, 1], gap="medium")
    with s1:
        md('<div class="ffr-lbl" style="margin:6px 0">Gợi ý tối ưu (theo quy tắc)</div>')
        md('<div class="ffr-insight">' + "<br>".join(esc(x) for x in a["suggest"]) + "</div>")
    with s2:
        dv = a["div"]
        md('<div class="ffr-lbl" style="margin:6px 0">Mã bổ sung để đa dạng hóa · tương quan thấp với danh mục · GTGD ≥ 50 tỷ</div>')
        if dv is None or dv.empty:
            st.caption("Chưa tìm được ứng viên.")
        else:
            for r in dv.itertuples():
                a1, a2 = st.columns([4, 1], vertical_alignment="center")
                a1.markdown(f"**{r.symbol}** · {r.sector} · tương quan {r.corr:+.2f} · biến động {r.vol:.0%}/năm · "
                            f"GTGD {r.tv20 / 1e9:,.0f} tỷ/phiên".replace(",", "."))
                if a2.button("➕", key=f"pf_add_{r.symbol}", help=f"Thêm {r.symbol} vào danh mục"):
                    wi.add(r.symbol, "gợi ý đa dạng hóa")
                    st.cache_data.clear()
                    st.rerun()

    with st.expander("💰 Quy đổi ra số cổ phiếu theo số vốn"):
        cap = st.number_input("Số vốn (triệu đồng)", 10.0, 1e6, 100.0, 10.0, key="pf_cap") * 1e6
        prices = a["info"].set_index("symbol")["close"] if not a["info"].empty else pd.Series(dtype=float)
        al = P.allocate_shares(t["w"], prices, cap)
        if al.empty:
            st.caption("Thiếu giá đóng cửa.")
        else:
            md(table_html(["Mã", "Tỷ trọng", "Giá", "Số CP (lô 100)", "Giá trị"],
                          [[r.symbol, f"{r.weight:.0%}", fmt.price(r.price), f"{r.shares:,}".replace(",", "."),
                            fmt.num(r.value / 1e6, 1, False, " tr")] for r in al.itertuples()], left=(0,)))
            st.caption(f"Tiền mặt còn lại ≈ {al['cash_left'].iloc[0] / 1e6:,.1f} triệu đồng (do làm tròn lô 100).".replace(",", "X")
                       .replace(".", ",").replace("X", "."))
    st.caption("⚠️ Công cụ định lượng tham khảo dựa trên dữ liệu quá khứ (biến động, tương quan thay đổi theo thời gian; lợi suất "
               "kỳ vọng lịch sử rất nhiễu). Không phải khuyến nghị đầu tư; không tính phí giao dịch, thuế, thanh khoản thực tế.")
