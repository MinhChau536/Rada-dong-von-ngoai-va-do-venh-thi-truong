"""
Thẻ (widget) dùng chung cho các trang Tổng quan thị trường, Dẫn dắt & độ vênh, Ra-đa khối ngoại – phong cách các
cổng thông tin chứng khoán phổ biến: khung thẻ + tiêu đề + thanh tab, mỗi thẻ là một bảng top 10 hoặc một biểu đồ nhỏ.
Toàn bộ số liệu đọc từ kho chỉ báo (SSI FastConnect V3); số liệu ngoài nguồn (P/E, hàng hóa, tỷ giá…) không hiển thị.

    with card("ten_the"):        # khung thẻ có viền, nền, bo góc (CSS div[class*="st-key-tcw"] trong theme.py)
        title("Tiêu đề", "dòng phụ")
        w_top(D)                   # hoặc nội dung tự vẽ
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.analytics import outlook
from src.analytics.health import period_returns
from src.app import data_access as da
from src.app.components import charts, status_bar
from src.app.components.states import safe_block
from src.app.components.ui import esc, md, pal, plot
from src.app.theme import color_for
from src.common import fmt
from src.common.config import get

INDEX_ORDER = [("VNINDEX", "HOSE · VN-Index"), ("VN30", "VN30"), ("HNXINDEX", "HNX"), ("UPCOMINDEX", "UPCoM")]
WEEKDAYS = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]


@st.cache_data(ttl=60, show_spinner=False)
def load(session_date) -> Dict:
    d = pd.Timestamp(session_date)
    day = da.daily()
    day = day[pd.to_datetime(day["trade_date"]) <= d].copy()
    day["trade_date"] = pd.to_datetime(day["trade_date"])
    sess = [s for s in da.sessions() if s <= d]
    rng = da.stock_range(sess[-20], d) if len(sess) >= 20 else da.stock_range(sess[0], d)
    rng["trade_date"] = pd.to_datetime(rng["trade_date"])
    return {"date": d, "day": day.iloc[-1], "hist": day, "stock": da.stock_day(d), "leaders": da.leaders(d),
            "groups": da.groups(d), "range": rng, "sess": sess,
            "index": {c: da.index_hist(c) for c, _ in INDEX_ORDER}}


# ── khung thẻ ────────────────────────────────────────────────────────────────
def card(key: str):
    """Khung thẻ: container có key 'tcw_<key>' để CSS nhận diện (viền, nền, tab navy)."""
    return st.container(border=True, key=f"tcw_{key}")


def title(text: str, sub: str = "") -> None:
    md(f'<div class="tc-title">{esc(text)}</div>' + (f'<div class="tc-sub">{esc(sub)}</div>' if sub else ""))


def _chg(v, text: str) -> str:
    return f'<span style="color:{color_for(v, pal())};font-weight:600">{text}</span>'


def table(headers: List[str], rows: List[List[str]], left=(0, 1), height: int = 0) -> None:
    th = "".join(f'<th class="{"l" if i in left else ""}">{h}</th>' for i, h in enumerate(headers))
    tr = "".join("<tr>" + "".join(f'<td class="{"l" if i in left else ""}">{c}</td>' for i, c in enumerate(r)) + "</tr>"
                 for r in rows)
    style = f' style="max-height:{height}px;overflow:auto"' if height else ""
    md(f'<div class="tc-tw"{style}><table class="tc-t"><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>')


def _sym(s: str) -> str:
    return f'<b class="tc-sym">{esc(s)}</b>'


def _fig(fig: go.Figure, h: int, dates: bool = False, **kw) -> go.Figure:
    charts._lay(fig, pal(), h, margin=dict(l=4, r=4, t=8, b=4), showlegend=kw.pop("showlegend", False), **kw)
    if dates:
        fig.update_xaxes(tickformat="%d/%m", hoverformat="%d/%m/%Y")      # ngày kiểu Việt Nam, không "Oct 4"
    return fig


# ── 1. Chỉ số ────────────────────────────────────────────────────────────────
@safe_block("chỉ số")
def w_indices(D: Dict) -> None:
    p, d, x = pal(), D["date"], D["day"]
    title("Chỉ số thị trường")
    t1, t2 = st.tabs(["Hôm nay", "Hiệu suất"])
    with t1:
        v = D["index"]["VNINDEX"]
        v = v[v["trade_date"] <= d].tail(60)
        if not v.empty:
            ref = v["value"].iloc[-2] if len(v) > 1 else v["value"].iloc[-1]
            c = color_for(v["value"].iloc[-1] - ref, p)
            fig = go.Figure(go.Scatter(x=v["trade_date"], y=v["value"], mode="lines", line=dict(color=c, width=1.8),
                                       fill="tozeroy", fillcolor="rgba(22,163,74,.12)" if c == p["up"] else "rgba(220,38,38,.10)",
                                       hovertemplate="%{x|%d/%m}: %{y:,.2f}<extra></extra>"))
            fig.add_hline(y=ref, line=dict(color=p["ref"], width=1, dash="dot"))
            _fig(fig, 150, dates=True)
            fig.update_yaxes(range=[v["value"].min() * .99, v["value"].max() * 1.01])
            plot(fig, "tc_vni")
        rows = []
        for code, name in INDEX_ORDER:
            h = D["index"][code]
            h = h[h["trade_date"] <= d]
            if h.empty or h["trade_date"].iloc[-1] != d:
                rows.append([name, "—", "—", "—"])
                continue
            r = h.iloc[-1]
            rows.append([f"<b>{name}</b>", f"<b>{fmt.num(r['value'])}</b>", _chg(r["change"], f"{fmt.arrow(r['change'])} {fmt.num(r['change'], 2, True)}"),
                         _chg(r["change"], fmt.pct(r["ratio_change"]))])
        table(["Chỉ số", "Điểm", "+/-", "%"], rows, left=(0,))
        tot = max(int(x["n_up"] + x["n_unch"] + x["n_down"]), 1)
        seg = [(int(x["n_down"]), p["down"]), (int(x["n_unch"]), p["ref"]), (int(x["n_up"]), p["up"])]
        bar = "".join(f'<i style="width:{n / tot * 100:.2f}%;background:{c}">{n}</i>' for n, c in seg if n)
        md(f'<div class="tc-row"><span>GTGD khớp <b>{fmt.bn(x["tv_total"], 0, False)}</b></span>'
           f'<span>NN ròng <b style="color:{color_for(x["NF_total"], p)}">{fmt.bn(x["NF_total"])}</b></span></div>'
           f'<div class="tc-breadth">{bar}</div><div class="tc-row"><span style="color:{p["down"]}">Giảm {int(x["n_down"])}</span>'
           f'<span style="color:{p["ref"]}">Đứng {int(x["n_unch"])}</span><span style="color:{p["up"]}">Tăng {int(x["n_up"])}</span></div>')
    with t2:
        rows = []
        for code, name in INDEX_ORDER:
            h = D["index"][code]
            h = h[h["trade_date"] <= d]
            if h.empty:
                continue
            r = period_returns(h.set_index("trade_date")["value"])
            rows.append([f"<b>{name}</b>"] + [_chg(r.get(k), fmt.pct(r.get(k), 1)) for k in ("1T", "1Th", "3Th", "YTD", "1N")])
        table(["Chỉ số", "1 tuần", "1 tháng", "3 tháng", "YTD", "1 năm"], rows, left=(0,))
        md(f'<div class="tc-note">Lợi suất theo giá đóng cửa chỉ số đến phiên {d:%d/%m/%Y}.</div>')


# ── 2. Top 10 cổ phiếu ───────────────────────────────────────────────────────
@safe_block("top 10 cổ phiếu")
def w_top(D: Dict) -> None:
    v = D["stock"][D["stock"]["is_valid"]].copy()
    min_tv = 1e9                                                      # lọc thanh khoản ≥ 1 tỷ cho bảng top
    liq = v[v["tv"] >= min_tv]
    title("Top 10 cổ phiếu HOSE")
    tabs = st.tabs(["Tăng giá", "Giảm giá", "GTGD", "KL đột biến"])
    picks = [liq.nlargest(10, "ret"), liq.nsmallest(10, "ret"), v.nlargest(10, "tv"),
             liq[liq["vol_ratio"] >= 2].nlargest(10, "vol_ratio") if "vol_ratio" in v else v.head(0)]
    for tab, df, extra in zip(tabs, picks, ["GTGD tỷ", "GTGD tỷ", "GTGD tỷ", "KL/TB20"]):
        with tab:
            rows = []
            for i, r in enumerate(df.itertuples(), 1):
                ex = fmt.num(r.vol_ratio, 1, False, "×") if extra == "KL/TB20" else fmt.num(r.tv / 1e9, 1)
                rows.append([str(i), _sym(r.symbol), _chg(r.ret, fmt.price(r.close)),
                             _chg(r.ret, fmt.num(r.close - r.ref, 0, True)), _chg(r.ret, fmt.pct(r.ret * 100)), ex])
            table(["#", "Mã", "Giá", "+/-", "%", extra], rows or [["", "Không có mã thỏa điều kiện", "", "", "", ""]])
    md(f'<div class="tc-note">Bảng tăng/giảm/đột biến chỉ xét mã có GTGD ≥ {fmt.num(min_tv / 1e9, 0)} tỷ đồng.</div>')


# ── 3. Nhóm dẫn dắt ──────────────────────────────────────────────────────────
def _lead_fig(df: pd.DataFrame, h: int = 300) -> go.Figure:
    p = pal()
    fig = go.Figure(go.Bar(x=df["symbol"], y=df["C"], marker_color=[color_for(c, p) for c in df["C"]],
                           text=[fmt.num(c, 2, True) for c in df["C"]], textposition="outside", cliponaxis=False,
                           hovertemplate="%{x}: %{y:+.2f} điểm<extra></extra>"))
    _fig(fig, h)
    fig.update_xaxes(tickangle=-45, type="category")
    return fig


@safe_block("nhóm dẫn dắt")
def w_leaders(D: Dict) -> None:
    lead = D["leaders"]
    title("Nhóm dẫn dắt VN-Index", "Điểm đóng góp của từng mã vào thay đổi chỉ số")
    t1, t2 = st.tabs(["Phiên này", "20 phiên"])
    with t1:
        df = pd.concat([lead[lead["side"] == "pos"].head(5), lead[lead["side"] == "neg"].head(5)]).sort_values("C", ascending=False)
        plot(_lead_fig(df), "tc_lead1")
        pos, neg = lead[lead["side"] == "pos"]["C"].sum(), lead[lead["side"] == "neg"]["C"].sum()
        md(f'<div class="tc-row"><span>Tổng đóng góp tăng <b style="color:{pal()["up"]}">{fmt.num(pos, 2, True)}</b></span>'
           f'<span>Tổng đóng góp giảm <b style="color:{pal()["down"]}">{fmt.num(neg, 2, True)}</b></span></div>')
    with t2:
        l20 = outlook.cum_leaders(D["range"], sorted(D["range"]["trade_date"].unique()), 5).sort_values("C", ascending=False)
        plot(_lead_fig(l20), "tc_lead20")
        md(f'<div class="tc-note">Tổng điểm đóng góp cộng dồn {D["range"]["trade_date"].nunique()} phiên gần nhất.</div>')


# ── 4. Khối ngoại top mua/bán ròng ───────────────────────────────────────────
@safe_block("khối ngoại")
def w_foreign_top(D: Dict) -> None:
    v = D["stock"][D["stock"]["is_valid"]]
    title("Khối ngoại")
    t1, t2, t3 = st.tabs(["NN mua ròng", "NN bán ròng", "Theo nhóm"])
    for tab, df in ((t1, v[v["net_flow"] > 0].nlargest(10, "net_flow")), (t2, v[v["net_flow"] < 0].nsmallest(10, "net_flow"))):
        with tab:
            rows = [[str(i), _sym(r.symbol), _chg(r.net_flow, fmt.num(r.net_flow / 1e9, 2, True)), fmt.price(r.close),
                     _chg(r.ret, fmt.pct(r.ret * 100))] for i, r in enumerate(df.itertuples(), 1)]
            table(["#", "Mã", "Ròng (tỷ)", "Giá", "Thay đổi"], rows or [["", "Không có", "", "", ""]])
    with t3:
        from src.app.components.ui import soft_chip
        from src.app.theme import ABSORB_COLORS
        from src.finance.domestic import ABSORB_LABELS
        g = D["groups"]
        uni = g[g["group_type"] == "universe"].set_index("group_name")
        sec = g[g["group_type"] == "sector"]
        sec = sec.reindex(sec["net_flow"].abs().sort_values(ascending=False).index).head(6)
        rows = []
        for nm, label in (("FTSE", "Nhóm FTSE"), ("CONTROL", "Đối chứng"), ("VN30", "VN30")):
            if nm in uni.index:
                r = uni.loc[nm]
                rows.append([f"<b>{label}</b>", _chg(r["net_flow"], fmt.num(r["net_flow"] / 1e9, 1, True)),
                             fmt.num(r["nf"], 3, True), soft_chip(ABSORB_LABELS[r["absorb_state"]], ABSORB_COLORS[r["absorb_state"]])])
        for r in sec.itertuples():
            rows.append([esc(r.group_name), _chg(r.net_flow, fmt.num(r.net_flow / 1e9, 1, True)), fmt.num(r.nf, 3, True),
                         soft_chip(ABSORB_LABELS[r.absorb_state], ABSORB_COLORS[r.absorb_state])])
        table(["Nhóm / ngành", "Ròng (tỷ)", "nf", "Ngoại – nội"], rows, left=(0, 3))
        md('<div class="tc-note">nf = ròng / GTGD. Trạng thái chỉ gán khi |nf| ≥ 5% và |giá| ≥ 0,5%.</div>')


# ── 5. Diễn biến giao dịch khối ngoại ────────────────────────────────────────
@safe_block("diễn biến khối ngoại")
def w_foreign_flow(D: Dict) -> None:
    p = pal()
    h = D["hist"].tail(int(get("windows.tc_foreign", 15)))
    title("Diễn biến giao dịch khối ngoại", "HOSE · đơn vị tỷ đồng")
    t1, t2 = st.tabs(["Mua – bán – ròng", "Lũy kế 60 phiên"])
    with t1:
        fig = go.Figure()
        fig.add_bar(x=h["trade_date"], y=h["FB_total"] / 1e9, name="Giá trị mua", marker_color="#1E3A5F")
        fig.add_bar(x=h["trade_date"], y=-h["FS_total"] / 1e9, name="Giá trị bán", marker_color=p["down"])
        fig.add_scatter(x=h["trade_date"], y=h["NF_total"] / 1e9, name="Ròng", mode="lines+markers",
                        line=dict(color="#F59E0B", width=2, shape="spline"))
        _fig(fig, 300, dates=True, barmode="relative", showlegend=True, legend=dict(orientation="h", y=-0.18, x=0))
        plot(fig, "tc_ff")
        x = D["day"]
        md(f'<div class="tc-row"><span>Mua <b>{fmt.bn(x["FB_total"], 0, False)}</b> · Bán <b>{fmt.bn(x["FS_total"], 0, False)}</b></span>'
           f'<span>Giá trị ròng phiên {D["date"]:%d/%m/%Y}: <b style="color:{color_for(x["NF_total"], p)};font-size:16px">'
           f'{fmt.bn(x["NF_total"], 2)}</b></span></div>')
    with t2:
        h = D["hist"].tail(60)
        cum = (h["NF_total"].fillna(0) / 1e9).cumsum()
        fig = go.Figure()
        fig.add_bar(x=h["trade_date"], y=h["NF_total"] / 1e9, marker_color=[color_for(v, p) for v in h["NF_total"].fillna(0)],
                    name="Ròng phiên")
        fig.add_scatter(x=h["trade_date"], y=cum, name="Lũy kế", line=dict(color="#1E3A5F", width=2), yaxis="y2")
        _fig(fig, 300, dates=True, showlegend=True, legend=dict(orientation="h", y=-0.18, x=0),
             yaxis2=dict(overlaying="y", side="right", showgrid=False))
        plot(fig, "tc_ffc")


# ── 6. Thanh khoản ───────────────────────────────────────────────────────────
@safe_block("thanh khoản")
def w_liquidity(D: Dict) -> None:
    p = pal()
    h = D["hist"].tail(40)
    title("Thanh khoản thị trường", "GTGD khớp lệnh HOSE · tỷ đồng")
    tv = h["tv_total"] / 1e9
    ma = (D["hist"]["tv_total"] / 1e9).rolling(20).mean().tail(40)
    fig = go.Figure()
    fig.add_bar(x=h["trade_date"], y=tv, marker_color=[p["up"] if r >= 0 else p["down"] for r in h["r_vni_pct"].fillna(0)],
                opacity=.75, name="GTGD")
    fig.add_scatter(x=h["trade_date"], y=ma, name="TB 20 phiên", line=dict(color="#F59E0B", width=2))
    _fig(fig, 300, dates=True, showlegend=True, legend=dict(orientation="h", y=-0.18, x=0))
    plot(fig, "tc_liq")
    last, avg = tv.iloc[-1], ma.iloc[-1]
    md(f'<div class="tc-row"><span>Phiên này <b>{fmt.num(last, 0)} tỷ</b></span>'
       f'<span>So với TB20: <b style="color:{color_for(last - avg, p)}">{fmt.pct((last / avg - 1) * 100, 0)}</b></span></div>')


# ── 7. Độ rộng ───────────────────────────────────────────────────────────────
@safe_block("độ rộng")
def w_breadth(D: Dict) -> None:
    p = pal()
    h = D["hist"].tail(40)
    tot = (h["n_up"] + h["n_unch"] + h["n_down"]).replace(0, np.nan)
    title("Độ rộng thị trường", "Tỷ lệ số mã giảm / đứng / tăng · HOSE")
    fig = go.Figure()
    for col, name, c in (("n_down", "Giảm giá", p["down"]), ("n_unch", "Đứng giá", "#FACC15"), ("n_up", "Tăng giá", p["up"])):
        fig.add_scatter(x=h["trade_date"], y=h[col] / tot * 100, name=name, stackgroup="one", mode="lines",
                        line=dict(width=0.5, color=c), fillcolor=c, hovertemplate="%{y:.0f}%<extra>" + name + "</extra>")
    _fig(fig, 300, dates=True, showlegend=True, legend=dict(orientation="h", y=-0.18, x=0))
    fig.update_yaxes(range=[0, 100], ticksuffix="%")
    plot(fig, "tc_br")
    x = D["day"]
    md(f'<div class="tc-row"><span>Tỷ lệ mã tăng phiên này <b>{fmt.num(x["pct_up"], 0)}%</b></span>'
       f'<span>TB 20 phiên <b>{fmt.num(D["hist"]["pct_up"].tail(20).mean(), 0)}%</b></span></div>')


# ── 8. Ngành ─────────────────────────────────────────────────────────────────
@safe_block("ngành")
def w_sectors(D: Dict) -> None:
    p = pal()
    title("Biến động ngành", "Lợi suất theo vốn hóa")
    dates = sorted(D["range"]["trade_date"].unique())
    tabs = st.tabs(["1 phiên", "5 phiên", "20 phiên"])
    for tab, n in zip(tabs, (1, 5, 20)):
        with tab:
            s = outlook.sector_returns(D["range"], dates[-n:]).sort_values("ret_pct")
            fig = go.Figure(go.Bar(x=s["ret_pct"], y=s["sector"], orientation="h",
                                   marker_color=[color_for(v, p) for v in s["ret_pct"]],
                                   text=[fmt.pct(v, 1) for v in s["ret_pct"]], textposition="outside", cliponaxis=False,
                                   hovertemplate="%{y}: %{x:+.2f}%<extra></extra>"))
            _fig(fig, 340)
            fig.update_yaxes(tickfont=dict(size=11))
            span = float(s["ret_pct"].abs().max() or 1) * 1.35
            fig.update_xaxes(range=[-span, span])
            plot(fig, f"tc_sec{n}")


# ── 9. Bản đồ thị trường ─────────────────────────────────────────────────────
@safe_block("bản đồ thị trường")
def w_map(D: Dict) -> None:
    title("Bản đồ thị trường HOSE", "Diện tích theo giá trị giao dịch · màu theo % thay đổi giá · rê chuột để xem khối ngoại")
    v = D["stock"][D["stock"]["is_valid"]]
    secs = ["Tất cả các ngành"] + sorted(v["sector"].dropna().unique())
    c1, _ = st.columns([1, 3])
    with c1:
        sec = st.selectbox("Ngành", secs, key="tc_map_sec", label_visibility="collapsed")
    snap = D["stock"] if sec == secs[0] else D["stock"][D["stock"]["sector"] == sec]
    fig = charts.treemap(snap, pal())
    fig.update_layout(height=520)
    plot(fig, "tc_map")
