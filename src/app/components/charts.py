"""
Biểu đồ Plotly dùng chung. Kế thừa _index_chart, _treemap, _sector_bars, _gauge, line_comparison_chart của bản
giữa kỳ (đổi sang template 'ffr' của theme.py), thêm biểu đồ mới cho Module A–C.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src.app.theme import SESSION_COLORS, color_for, register_plotly
from src.finance.breadth import SESSION_TYPES


def _lay(fig: go.Figure, p: Dict, height: int, **kw) -> go.Figure:
    fig.update_layout(template=register_plotly("dark" if p["dark"] else "light"), height=height, **kw)
    fig.update_xaxes(automargin=True)
    fig.update_yaxes(automargin=True)
    return fig


def index_chart(df: pd.DataFrame, name: str, kind: str, p: Dict, events: Optional[pd.DataFrame] = None,
                height: int = 460) -> go.Figure:
    d = df.copy()
    d["MA20"] = d["value"].rolling(20).mean()
    d["MA50"] = d["value"].rolling(50).mean()
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.77, 0.23], vertical_spacing=0.02)
    x = d["trade_date"]
    op = d["open"].fillna(d["value"])
    if kind == "Nến":
        fig.add_trace(go.Candlestick(x=x, open=op, high=d["high"].fillna(d["value"]), low=d["low"].fillna(d["value"]),
                                     close=d["value"], name=name, increasing_line_color=p["up"],
                                     decreasing_line_color=p["down"], increasing_fillcolor=p["up"],
                                     decreasing_fillcolor=p["down"]), 1, 1)
    else:
        fig.add_trace(go.Scatter(x=x, y=d["value"], name=name, line=dict(color=p["accent"], width=2)), 1, 1)
    for ma, c in (("MA20", p["ma20"]), ("MA50", p["ma50"])):
        fig.add_trace(go.Scatter(x=x, y=d[ma], name=ma, line=dict(color=c, width=1.3)), 1, 1)
    vc = [p["up"] if c >= o else p["down"] for c, o in zip(d["value"], op)]
    fig.add_trace(go.Bar(x=x, y=d["vol"], marker_color=vc, opacity=.5, name="Khối lượng", showlegend=False), 2, 1)
    last = float(d["value"].iloc[-1])
    fig.add_hline(y=last, line=dict(color=p["accent"], width=1, dash="dot"), row=1, col=1,
                  annotation_text=f" {last:,.2f}".replace(",", "§").replace(".", ",").replace("§", "."),
                  annotation_position="right", annotation_font=dict(color=p["accent"], size=11))
    if events is not None:
        for e in events.itertuples():
            ed = pd.Timestamp(e.event_date)
            if x.min() <= ed <= x.max():
                fig.add_vline(x=ed, line=dict(color=p["teal"], width=1.3, dash="dash"))
                fig.add_annotation(x=ed, y=1.0, yref="paper", text=f"{e.event_id} {ed:%d/%m}", showarrow=False,
                                   font=dict(size=10, color="#fff"), bgcolor=p["teal"], borderpad=2)
    _lay(fig, p, height, hovermode="x unified", xaxis_rangeslider_visible=False, margin=dict(l=8, r=60, t=36, b=8))
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])], showgrid=False)
    fig.update_yaxes(tickformat=",.0f", row=1, col=1)
    fig.update_yaxes(tickformat=".2s", row=2, col=1)
    return fig


def gauge(score: float, p: Dict) -> go.Figure:
    col = p["up"] if score >= 70 else p["ref"] if score >= 40 else p["down"]
    fig = go.Figure(go.Indicator(mode="gauge+number", value=score,
                                 number=dict(font=dict(size=38, color=p["text"]), valueformat=".0f"),
                                 gauge=dict(axis=dict(range=[0, 100], tickwidth=0, tickfont=dict(size=10, color=p["muted"])),
                                            bar=dict(color=col, thickness=.28), bgcolor="rgba(0,0,0,0)", borderwidth=0,
                                            steps=[dict(range=[0, 40], color="rgba(220,38,38,.12)"),
                                                   dict(range=[40, 70], color="rgba(217,119,6,.12)"),
                                                   dict(range=[70, 100], color="rgba(22,163,74,.14)")])))
    return _lay(fig, p, 185, margin=dict(l=28, r=28, t=12, b=0))


def diverging_bars(labels: List[str], values: List[float], p: Dict, height: int = 330, fmt: str = "{:+.1f}",
                   title: str = "") -> go.Figure:
    order = np.argsort(values)
    lab = [labels[i] for i in order]
    val = [values[i] for i in order]
    fig = go.Figure(go.Bar(x=val, y=lab, orientation="h", marker_color=[color_for(v, p) for v in val],
                           text=[fmt.format(v).replace(".", ",") for v in val], textposition="outside", cliponaxis=False,
                           hovertemplate="<b>%{y}</b>: %{x:.2f}<extra></extra>"))
    span = max(abs(min(val + [0])), abs(max(val + [0]))) * 1.35 + 1e-9
    _lay(fig, p, height, showlegend=False, title=dict(text=title, font=dict(size=13)), margin=dict(l=8, r=30, t=30 if title else 8, b=8))
    fig.update_xaxes(range=[-span, span], zeroline=True, zerolinecolor=p["muted"])
    fig.update_yaxes(showgrid=False, type="category")
    return fig


def treemap(snap: pd.DataFrame, p: Dict) -> go.Figure:
    d = snap[snap["is_valid"]].copy()
    d["size"] = (d["tv"] / 1e9).clip(lower=0.05)
    d["ret_pct"] = d["ret"] * 100
    d["nf_bn"] = d["net_flow"] / 1e9
    fig = px.treemap(d, path=[px.Constant("HOSE"), "sector", "symbol"], values="size", color="ret_pct",
                     color_continuous_scale=[[0, "#B91C1C"], [.35, "#F87171"], [.5, "#E5E7EB" if not p["dark"] else "#334155"],
                                             [.65, "#4ADE80"], [1, "#15803D"]],
                     range_color=[-2.5, 2.5], color_continuous_midpoint=0,
                     custom_data=["ret_pct", "close", "size", "nf_bn"])
    big = d["nf_bn"].abs() >= d["nf_bn"].abs().quantile(.9)
    widths = [3 if b else 1 for b in big]
    fig.update_traces(texttemplate="<b>%{label}</b><br>%{customdata[0]:+.2f}%", textposition="middle center",
                      hovertemplate="<b>%{label}</b><br>%{customdata[0]:+.2f}%<br>Giá %{customdata[1]:,.0f}"
                                    "<br>GTGD %{customdata[2]:,.1f} tỷ<br>NN ròng %{customdata[3]:+,.1f} tỷ<extra></extra>",
                      marker=dict(line=dict(width=1.2, color=p["card"])), root_color="rgba(0,0,0,0)", tiling=dict(pad=2))
    _lay(fig, p, 450, margin=dict(l=0, r=0, t=4, b=0), coloraxis_colorbar=dict(title="%", thickness=10, len=.8))
    return fig


def sector_bars(df: pd.DataFrame, col: str, p: Dict, suffix: str = "%") -> go.Figure:
    d = df.dropna(subset=[col]).sort_values(col)
    fig = go.Figure(go.Bar(x=d[col], y=d["group_name"], orientation="h", marker_color=[color_for(v, p) for v in d[col]],
                           text=[f"{v:+.2f}{suffix}".replace(".", ",") for v in d[col]], textposition="outside",
                           cliponaxis=False))
    lo, hi = min(0.0, float(d[col].min() if len(d) else 0)), max(0.0, float(d[col].max() if len(d) else 0))
    pad = (hi - lo) * .35 + .3
    _lay(fig, p, max(300, 28 * len(d) + 50), showlegend=False, margin=dict(l=8, r=50, t=6, b=8))
    fig.update_xaxes(range=[lo - pad, hi + pad], zeroline=True, zerolinecolor=p["muted"])
    fig.update_yaxes(showgrid=False)
    return fig


def line_comparison(series: Dict[str, pd.Series], p: Dict, height: int = 330) -> go.Figure:
    fig = go.Figure()
    colors = [p["accent"], "#4F46E5", "#F59E0B", "#DB2777"]
    for i, (name, s) in enumerate(series.items()):
        s = s.dropna()
        if s.empty:
            continue
        fig.add_trace(go.Scatter(x=s.index, y=s / s.iloc[0] * 100, name=name, line=dict(width=2, color=colors[i % 4])))
    fig.add_hline(y=100, line=dict(color=p["muted"], width=1, dash="dot"))
    return _lay(fig, p, height, hovermode="x unified")


def waterfall(names: List[str], values: List[float], p: Dict, height: int = 380, total_label: str = "ΔVN-Index") -> go.Figure:
    fig = go.Figure(go.Waterfall(x=names + [total_label], y=values + [sum(values)],
                                 measure=["relative"] * len(values) + ["total"],
                                 increasing=dict(marker=dict(color=p["up"])), decreasing=dict(marker=dict(color=p["down"])),
                                 totals=dict(marker=dict(color=p["accent"])), connector=dict(line=dict(color=p["border"])),
                                 text=[f"{v:+.2f}".replace(".", ",") for v in values + [sum(values)]], textposition="outside"))
    return _lay(fig, p, height, showlegend=False)


def d_series(day: pd.DataFrame, p: Dict, height: int = 330) -> go.Figure:
    d = day.copy()
    lo = d["D"].shift(1).rolling(250, min_periods=40).quantile(.1)
    hi = d["D"].shift(1).rolling(250, min_periods=40).quantile(.9)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d["trade_date"], y=hi, line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=d["trade_date"], y=lo, fill="tonexty", fillcolor="rgba(20,184,166,.12)", line=dict(width=0),
                             name="Dải phân vị 10–90 (250 phiên trước)"))
    fig.add_trace(go.Scatter(x=d["trade_date"], y=d["D"], name="D (điểm %)", line=dict(color=p["accent"], width=1.4)))
    hd = d[d["high_divergence"].astype(bool)]
    fig.add_trace(go.Scatter(x=hd["trade_date"], y=hd["D"], mode="markers", name="Độ vênh cao",
                             marker=dict(color=p["down"], size=6)))
    fig.add_hline(y=0, line=dict(color=p["muted"], width=1))
    return _lay(fig, p, height, hovermode="x unified")


def hist(values: pd.Series, p: Dict, title: str, vline: Optional[float] = None, height: int = 300, nbins: int = 30) -> go.Figure:
    fig = go.Figure(go.Histogram(x=values.dropna(), nbinsx=nbins, marker_color=p["accent"], opacity=.85))
    if vline is not None:
        fig.add_vline(x=vline, line=dict(color=p["down"], dash="dash"))
    return _lay(fig, p, height, title=dict(text=title, font=dict(size=13)), showlegend=False, bargap=.05)


def session_calendar(day: pd.DataFrame, p: Dict, height: int = 260) -> go.Figure:
    d = day.copy()
    d["dt"] = pd.to_datetime(d["trade_date"])
    d["week"] = d["dt"].dt.to_period("W").dt.start_time
    d["dow"] = d["dt"].dt.dayofweek
    codes = list(SESSION_TYPES)
    d["code"] = d["session_type"].map({c: i for i, c in enumerate(codes)})
    z = d.pivot_table(index="dow", columns="week", values="code", aggfunc="first")
    txt = d.pivot_table(index="dow", columns="week", values="session_type", aggfunc="first").replace(SESSION_TYPES)
    n = len(codes)
    scale = []
    for i, c in enumerate(codes):
        scale += [[i / n, SESSION_COLORS[c]], [(i + 1) / n, SESSION_COLORS[c]]]
    fig = go.Figure(go.Heatmap(z=z.values, x=z.columns, y=["T2", "T3", "T4", "T5", "T6"][:len(z.index)],
                               text=txt.values, hovertemplate="%{x|%d/%m/%Y} %{y}: %{text}<extra></extra>",
                               colorscale=scale, zmin=-.5, zmax=n - .5, showscale=False, xgap=2, ygap=2))
    return _lay(fig, p, height, margin=dict(l=8, r=8, t=8, b=8))


def caar_chart(aar: pd.DataFrame, p: Dict, col: str = "CAAR", title: str = "", height: int = 340) -> go.Figure:
    fig = go.Figure()
    for g, c in (("FTSE", p["accent"]), ("CONTROL", "#94A3B8")):
        d = aar[aar["group"] == g].sort_values("tau")
        if d.empty:
            continue
        name = "Nhóm FTSE" if g == "FTSE" else "Nhóm đối chứng"
        fig.add_trace(go.Scatter(x=d["tau"], y=d[f"{col}_hi"] * 100 if col == "CAAR" else d[f"{col}_hi"],
                                 line=dict(width=0), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=d["tau"], y=d[f"{col}_lo"] * 100 if col == "CAAR" else d[f"{col}_lo"], fill="tonexty",
                                 fillcolor=f"rgba({','.join(str(int(c.lstrip('#')[i:i+2], 16)) for i in (0, 2, 4))},.14)",
                                 line=dict(width=0), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=d["tau"], y=d[col] * 100 if col == "CAAR" else d[col], name=name,
                                 line=dict(color=c, width=2.2)))
    fig.add_vline(x=0, line=dict(color=p["teal"], dash="dash"))
    fig.add_hline(y=0, line=dict(color=p["muted"], width=1))
    _lay(fig, p, height, title=dict(text=title, font=dict(size=13)), hovermode="x unified")
    fig.update_xaxes(title="Ngày sự kiện τ (phiên)")
    return fig


def did_coef_chart(c: pd.DataFrame, p: Dict, outcome: str, height: int = 320) -> go.Figure:
    d = c[c["outcome"] == outcome].sort_values("week")
    fig = go.Figure(go.Scatter(x=d["week"], y=d["coef"], mode="markers+lines", line=dict(color=p["accent"]),
                               error_y=dict(type="data", symmetric=False, array=d["ci_hi"] - d["coef"],
                                            arrayminus=d["coef"] - d["ci_lo"], color=p["muted"]), name=outcome))
    fig.add_hline(y=0, line=dict(color=p["muted"]))
    fig.add_vline(x=-0.5, line=dict(color=p["teal"], dash="dash"))
    _lay(fig, p, height, showlegend=False, title=dict(text=f"Hệ số FTSE × tuần tương đối – {outcome}", font=dict(size=13)))
    fig.update_xaxes(title="Tuần so với E3 (tuần −1 là gốc)")
    return fig


def line(df: pd.DataFrame, x: str, ys: Dict[str, str], p: Dict, height: int = 300, title: str = "") -> go.Figure:
    fig = go.Figure()
    colors = [p["accent"], "#4F46E5", "#F59E0B", "#DB2777", "#94A3B8"]
    for i, (col, name) in enumerate(ys.items()):
        fig.add_trace(go.Scatter(x=df[x], y=df[col], name=name, line=dict(color=colors[i % 5], width=1.8)))
    return _lay(fig, p, height, hovermode="x unified", title=dict(text=title, font=dict(size=13)))
