"""Ảnh biểu đồ PNG gửi qua bot Telegram (matplotlib, không cần trình duyệt): giá + MA20/MA50 + khối lượng + khối ngoại."""
from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from src.common.config import events  # noqa: E402
from src.data import database as db  # noqa: E402

TEAL, UP, DOWN, MA20, MA50, MUTED = "#0F766E", "#16A34A", "#DC2626", "#F59E0B", "#4F46E5", "#64748B"


def _style(ax) -> None:
    ax.grid(alpha=.25)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(labelsize=8, colors="#334155")


def stock_chart(symbol: str, sessions: int = 130) -> io.BytesIO:
    s = symbol.upper()
    h = db.query_df("SELECT trade_date, close, vol, net_flow FROM indicator_stock_daily WHERE symbol = ? ORDER BY trade_date", [s])
    if h.empty:
        raise ValueError(f"Không có dữ liệu {s}")
    h["trade_date"] = pd.to_datetime(h["trade_date"])
    h["ma20"], h["ma50"] = h["close"].rolling(20).mean(), h["close"].rolling(50).mean()
    h = h.tail(sessions)
    fig, (a1, a2, a3) = plt.subplots(3, 1, figsize=(9, 6.6), sharex=True, gridspec_kw={"height_ratios": [3, 1, 1.1]})
    a1.plot(h["trade_date"], h["close"], color=TEAL, lw=2, label="Giá đóng cửa (điều chỉnh)")
    a1.plot(h["trade_date"], h["ma20"], color=MA20, lw=1.2, label="MA20")
    a1.plot(h["trade_date"], h["ma50"], color=MA50, lw=1.2, label="MA50")
    a1.set_title(f"{s} · {len(h)} phiên gần nhất · nguồn SSI FastConnect V3", fontsize=11, loc="left", fontweight="bold")
    a1.legend(fontsize=8, frameon=False, loc="upper left")
    last = h.iloc[-1]
    a1.annotate(f"{last['close']:,.0f}".replace(",", "."), (last["trade_date"], last["close"]), xytext=(6, 0),
                textcoords="offset points", fontsize=9, color=TEAL, fontweight="bold", va="center")
    chg = h["close"].diff().fillna(0)
    a2.bar(h["trade_date"], h["vol"] / 1e6, color=[UP if c >= 0 else DOWN for c in chg], alpha=.6, width=1)
    a2.set_ylabel("KL (tr)", fontsize=8)
    a3.bar(h["trade_date"], h["net_flow"] / 1e9, color=[UP if v >= 0 else DOWN for v in h["net_flow"].fillna(0)], width=1)
    a3.plot(h["trade_date"], (h["net_flow"].fillna(0) / 1e9).rolling(10).mean(), color="#0F172A", lw=1, label="TB 10 phiên")
    a3.set_ylabel("NN ròng (tỷ)", fontsize=8)
    a3.legend(fontsize=7, frameon=False, loc="upper left")
    for ax in (a1, a2, a3):
        _style(ax)
    a3.xaxis.set_major_formatter(mdates.DateFormatter("%m/%Y"))
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130)
    plt.close(fig)
    buf.seek(0)
    return buf


def index_chart(code: str = "VNINDEX", sessions: int = 260) -> io.BytesIO:
    h = db.query_df("SELECT trade_date, value FROM fact_daily_index WHERE index_code = ? ORDER BY trade_date", [code])
    h["trade_date"] = pd.to_datetime(h["trade_date"])
    h["ma20"], h["ma50"] = h["value"].rolling(20).mean(), h["value"].rolling(50).mean()
    h = h.tail(sessions)
    d = db.query_df("SELECT trade_date, NF_total FROM indicator_daily ORDER BY trade_date")
    d["trade_date"] = pd.to_datetime(d["trade_date"])
    d = d[d["trade_date"] >= h["trade_date"].min()]
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9, 5.8), sharex=True, gridspec_kw={"height_ratios": [3, 1.1]})
    a1.plot(h["trade_date"], h["value"], color=TEAL, lw=2, label=code)
    a1.plot(h["trade_date"], h["ma20"], color=MA20, lw=1.1, label="MA20")
    a1.plot(h["trade_date"], h["ma50"], color=MA50, lw=1.1, label="MA50")
    for r in events().itertuples():
        if h["trade_date"].min() <= r.event_date <= h["trade_date"].max():
            a1.axvline(r.event_date, color="#F59E0B", ls="--", lw=1)
            a1.text(r.event_date, h["value"].max(), f" {r.event_id}", color="#B45309", fontsize=8, va="top")
    a1.set_title(f"{code} · 1 năm · mốc FTSE E1/E2/E3", fontsize=11, loc="left", fontweight="bold")
    a1.legend(fontsize=8, frameon=False, loc="upper left")
    a2.bar(d["trade_date"], d["NF_total"] / 1e9, color=[UP if v >= 0 else DOWN for v in d["NF_total"].fillna(0)], width=1)
    a2.set_ylabel("NN ròng HOSE (tỷ)", fontsize=8)
    for ax in (a1, a2):
        _style(ax)
    a2.xaxis.set_major_formatter(mdates.DateFormatter("%m/%Y"))
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130)
    plt.close(fig)
    buf.seek(0)
    return buf
