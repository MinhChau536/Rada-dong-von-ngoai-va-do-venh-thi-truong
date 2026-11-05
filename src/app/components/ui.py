"""Thành phần giao diện dùng chung (kế thừa _md, _section, _spark của giao_dien/thi_truong.py giữa kỳ, đổi bảng màu)."""
from __future__ import annotations

import html
import itertools
from typing import Iterable, List, Optional, Sequence

import pandas as pd
import streamlit as st

from src.app.theme import color_for, palette

_uid = itertools.count()


def mode() -> str:
    return st.session_state.get("theme", "light")


def pal():
    return palette(mode())


def md(s: str) -> None:
    """Gộp một dòng để Markdown không hiểu nhầm phần thụt lề là khối code."""
    st.markdown(" ".join(line.strip() for line in s.splitlines()), unsafe_allow_html=True)


def esc(s) -> str:
    return html.escape(str(s))


def section(title: str, sub: str = "", new: bool = False) -> None:
    badge = ' <span class="ffr-new">MỚI</span>' if new else ""
    md(f'<div class="ffr-sec"><h3>{title}{badge}</h3><span>{sub}</span></div>')


def header(title: str, sub: str, pills: Sequence[str] = ()) -> None:
    ph = "".join(f'<span class="ffr-pill">{p}</span>' for p in pills)
    md(f'<div class="ffr-head"><div><div class="ffr-title">{title}</div><div class="ffr-sub">{sub}</div></div>'
       f'<div>{ph}</div></div>')


def spark(values: Iterable, color: str, w: int = 170, h: int = 40, fill: bool = True) -> str:
    vals = [float(v) for v in values if v is not None and not pd.isna(v)]
    if len(vals) < 2:
        return f'<svg width="100%" height="{h}"></svg>'
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    step = w / (len(vals) - 1)
    pts = [(i * step, h - 3 - (v - lo) / rng * (h - 6)) for i, v in enumerate(vals)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    gid = f"g{next(_uid)}"
    area = f'<path d="M0,{h} L{line.replace(" ", " L")} L{w},{h} Z" fill="url(#{gid})"/>' if fill else ""
    return (f'<svg width="100%" height="{h}" viewBox="0 0 {w} {h}" preserveAspectRatio="none">'
            f'<defs><linearGradient id="{gid}" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stop-color="{color}" '
            f'stop-opacity=".28"/><stop offset="100%" stop-color="{color}" stop-opacity="0"/></linearGradient></defs>'
            f'{area}<polyline points="{line}" fill="none" stroke="{color}" stroke-width="1.7" stroke-linejoin="round" '
            f'vector-effect="non-scaling-stroke"/></svg>')


def chip(text: str, bg: str, fg: str = "#ffffff") -> str:
    return f'<span class="ffr-chip" style="background:{bg};color:{fg}">{esc(text)}</span>'


def tint(hex_color: str, alpha: float = .14) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def soft_chip(text: str, color: str) -> str:
    return f'<span class="ffr-chip" style="background:{tint(color)};color:{color}">{esc(text)}</span>'


def kpi(label: str, value: str, color: Optional[str] = None, sub: str = "", title: str = "") -> str:
    c = color or pal()["text"]
    s = f'<div style="font-size:11.5px;color:{pal()["muted"]};margin-top:2px">{sub}</div>' if sub else ""
    return f'<div class="ffr-kpi" title="{esc(title)}"><small>{label}</small><b style="color:{c}">{value}</b>{s}</div>'


def kpi_row(items: List[str]) -> None:
    cols = st.columns(len(items))
    for c, h in zip(cols, items):
        with c:
            md(h)


def table_html(headers: List[str], rows: List[List[str]], left: Sequence[int] = (0, 1)) -> str:
    th = "".join(f'<th class="{"l" if i in left else ""}">{h}</th>' for i, h in enumerate(headers))
    body = "".join("<tr>" + "".join(f'<td class="{"l" if i in left else ""}">{c}</td>' for i, c in enumerate(r)) + "</tr>"
                   for r in rows)
    return f'<div class="ffr-card" style="padding:6px 8px;overflow-x:auto"><table class="ffr-t"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


def colored(v, text: str) -> str:
    return f'<span style="color:{color_for(v, pal())};font-weight:700">{text}</span>'


def plot(fig, key: Optional[str] = None) -> None:
    st.plotly_chart(fig, width="stretch", theme=None, config={"displayModeBar": False}, key=key)
