"""Giá trong phiên theo từng phút – gọi thẳng SSI FastConnect V3 (endpoint ohlc, timeFrame 1m) lúc người dùng bấm nút.

• fetch(): phiên hôm nay nếu đang/đã giao dịch, ngược lại phiên gần nhất có dữ liệu; đệm 60 giây/mã để không gọi API dồn dập.
• summary(): mở cửa, cao/thấp (kèm giờ), giá cuối, VWAP, KL/GTGD, so với tham chiếu.
• chart(): ảnh PNG nến 1 phút + VWAP + đường tham chiếu + khối lượng.
Chỉ đọc dữ liệu thật; không ghi vào kho.
"""
from __future__ import annotations

import io
import time
from datetime import date, datetime, timedelta
from typing import Dict, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from src.common.timeutil import now_vn  # noqa: E402
from src.data import database as db  # noqa: E402

UP, DOWN, REF, VWAP, TEAL = "#16A34A", "#DC2626", "#F59E0B", "#4F46E5", "#0F766E"
_CACHE: Dict[Tuple[str, date], Tuple[float, pd.DataFrame]] = {}
_CLIENT = None


def _client():
    global _CLIENT
    if _CLIENT is None:
        from src.ssi_api.ssi_client import SSIClient
        _CLIENT = SSIClient()
    return _CLIENT


def in_session(now: Optional[datetime] = None) -> bool:
    n = now or now_vn()
    return n.weekday() < 5 and (9, 0) <= (n.hour, n.minute) <= (15, 5)


def _bars(symbol: str, d: date) -> pd.DataFrame:
    key = (symbol, d)
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < 60:
        return hit[1]
    rows = _client().ohlc(symbol, "1m", d, d)
    df = pd.DataFrame(rows)
    if not df.empty:
        df["ts"] = pd.to_datetime(df["tradingDate"], format="%Y/%m/%d %H:%M:%S", errors="coerce")
        for c in ("open", "high", "low", "close", "volume", "value"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.dropna(subset=["ts", "close"]).sort_values("ts").reset_index(drop=True)
    _CACHE[key] = (time.time(), df)
    return df


def fetch(symbol: str) -> Tuple[pd.DataFrame, Optional[date]]:
    """(nến 1 phút, ngày giao dịch). Thử hôm nay, rồi lùi tối đa 7 ngày tới phiên có dữ liệu."""
    s = symbol.upper().strip()
    d = now_vn().date()
    for _ in range(8):
        if d.weekday() < 5:
            df = _bars(s, d)
            if not df.empty:
                return df, d
        d -= timedelta(days=1)
    return pd.DataFrame(), None


def reference(symbol: str, d: date) -> Tuple[Optional[float], str]:
    """Giá tham chiếu: từ kho nếu đã có phiên d, ngược lại giá đóng cửa phiên trước (≈ tham chiếu)."""
    r = db.query_df("SELECT ref FROM fact_daily_stock WHERE symbol = ? AND trade_date = ?", [symbol, d])
    if not r.empty and pd.notna(r["ref"].iat[0]) and r["ref"].iat[0] > 0:
        return float(r["ref"].iat[0]), "TC"
    r = db.query_df("SELECT close FROM fact_daily_stock WHERE symbol = ? AND trade_date < ? AND close > 0 "
                    "ORDER BY trade_date DESC LIMIT 1", [symbol, d])
    return (float(r["close"].iat[0]), "TC≈") if not r.empty else (None, "TC")


def summary(df: pd.DataFrame, ref: Optional[float]) -> Dict:
    vol = df["volume"].fillna(0)
    val = df["value"].fillna(0)
    hi_i, lo_i = df["high"].idxmax(), df["low"].idxmin()
    last = float(df["close"].iloc[-1])
    vwap = float(val.sum() / vol.sum()) if vol.sum() > 0 else np.nan
    out = {"open": float(df["open"].iloc[0]), "high": float(df.loc[hi_i, "high"]), "high_t": df.loc[hi_i, "ts"],
           "low": float(df.loc[lo_i, "low"]), "low_t": df.loc[lo_i, "ts"], "last": last, "last_t": df["ts"].iloc[-1],
           "vwap": vwap, "vol": float(vol.sum()), "value": float(val.sum()), "bars": len(df), "ref": ref,
           "chg": (last - ref) if ref else np.nan, "pct": (last / ref - 1) * 100 if ref else np.nan}
    # khối lượng theo buổi: sáng (≤ 11:30) / chiều
    am = df["ts"].dt.hour * 60 + df["ts"].dt.minute <= 11 * 60 + 30
    out["vol_am"], out["vol_pm"] = float(vol[am].sum()), float(vol[~am].sum())
    return out


def chart(df: pd.DataFrame, symbol: str, d: date, ref: Optional[float]) -> io.BytesIO:
    """Nến 1 phút trên trục thứ tự nến (bỏ khoảng nghỉ trưa 11:30–13:00), VWAP, tham chiếu, khối lượng."""
    from matplotlib.ticker import FuncFormatter
    x = np.arange(len(df))
    up = (df["close"] >= df["open"]).to_numpy()
    col = np.where(up, UP, DOWN)
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9.5, 6.2), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    a1.vlines(x, df["low"], df["high"], color=col, lw=.8)
    body = np.maximum((df["close"] - df["open"]).abs().to_numpy(), df["close"].to_numpy() * 0.0003)   # nến đứng giá vẫn hiện
    a1.bar(x, body, 0.7, bottom=df[["open", "close"]].min(axis=1), color=col, edgecolor=col, lw=.3)
    cum_v = df["volume"].fillna(0).cumsum().replace(0, np.nan)
    a1.plot(x, df["value"].fillna(0).cumsum() / cum_v, color=VWAP, lw=1.4, label="VWAP (giá bình quân)")
    lo, hi = float(df["low"].min()), float(df["high"].max())
    if ref:
        a1.axhline(ref, color=REF, ls="--", lw=1.1, label=f"Tham chiếu {ref:,.0f}".replace(",", "."))
        lo, hi = min(lo, ref), max(hi, ref)
    pad = max((hi - lo) * 0.08, hi * 0.002)
    a1.set_ylim(lo - pad, hi + pad)
    last = float(df["close"].iloc[-1])
    a1.annotate(f" {last:,.0f}".replace(",", "."), (x[-1], last), xytext=(4, 0), textcoords="offset points",
                fontsize=9.5, fontweight="bold", va="center", color=UP if not ref or last >= ref else DOWN,
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=.8))
    mins = (df["ts"].dt.hour * 60 + df["ts"].dt.minute).to_numpy()
    pm = np.where(mins >= 13 * 60)[0]
    for ax in (a1, a2):
        if len(pm) and pm[0] > 0:                             # ranh giới phiên sáng / chiều
            ax.axvline(pm[0] - 0.5, color="#94A3B8", lw=1, ls=":")
    if len(pm) and pm[0] > 0:
        a1.text(pm[0] - 0.5, hi + pad * 0.5, " nghỉ trưa ", fontsize=7.5, color="#64748B", ha="center", va="center",
                bbox=dict(fc="white", ec="none", alpha=.85))
    a1.set_title(f"{symbol} · nến 1 phút · phiên {d:%d/%m/%Y} · cập nhật {df['ts'].iloc[-1]:%H:%M} · SSI FastConnect V3",
                 fontsize=10.5, loc="left", fontweight="bold")
    a1.legend(fontsize=8, frameon=False, loc="upper left")
    a1.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}".replace(",", ".")))
    a2.bar(x, df["volume"] / 1e3, 0.8, color=col, alpha=.75)
    a2.set_ylabel("KL (nghìn cp)", fontsize=8)
    # nhãn giờ tại các mốc tròn 30 phút
    ticks = [i for i, m in enumerate(mins) if m % 30 == 0 and (i == 0 or mins[i - 1] != m)]
    a2.set_xticks(ticks)
    a2.set_xticklabels([df["ts"].iloc[i].strftime("%H:%M") for i in ticks])
    a2.set_xlim(-1, len(df) + max(4, len(df) * 0.06))
    for ax in (a1, a2):
        ax.grid(alpha=.25)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.tick_params(labelsize=8, colors="#334155")
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130)
    plt.close(fig)
    buf.seek(0)
    return buf
