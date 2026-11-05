"""
Hàm dùng chung cho chỉ báo (bước B2.7).

Nguyên tắc KHÔNG NHÌN TRƯỚC: mọi ngưỡng lịch sử (phân vị, z-score) của phiên t chỉ dùng
dữ liệu trong cửa sổ [t−k, t−1]. Thay đổi giá trị phiên t không làm đổi ngưỡng của phiên t.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


def winsorize(s: pd.Series, lower: float = 0.01, upper: float = 0.99) -> pd.Series:
    """Cắt giá trị ngoại lệ ở phân vị lower/upper (trên một mặt cắt)."""
    x = pd.to_numeric(s, errors="coerce")
    if x.notna().sum() < 3:
        return x
    lo, hi = x.quantile(lower), x.quantile(upper)
    return x.clip(lo, hi)


def winsorize_by(df: pd.DataFrame, col: str, by: str = "trade_date", lower: float = 0.01, upper: float = 0.99) -> pd.Series:
    """Cắt theo TỪNG PHIÊN (mục 8.1)."""
    return df.groupby(by, group_keys=False)[col].apply(lambda s: winsorize(s, lower, upper))


def rolling_pct_rank(s: pd.Series, window: int, min_periods: Optional[int] = None) -> pd.Series:
    """
    Phân vị (0–100) của giá trị phiên t so với `window` phiên TRƯỚC đó [t−window, t−1].
    Đếm số quan sát quá khứ nhỏ hơn x_t (+½ số bằng), chia cho số quan sát hợp lệ.
    """
    x = pd.to_numeric(s, errors="coerce").to_numpy(dtype=float)
    n = len(x)
    mp = min_periods if min_periods is not None else max(5, window // 4)
    out = np.full(n, np.nan)
    for t in range(n):
        if np.isnan(x[t]):
            continue
        past = x[max(0, t - window):t]
        past = past[~np.isnan(past)]
        if len(past) < mp:
            continue
        out[t] = ((past < x[t]).sum() + 0.5 * (past == x[t]).sum()) / len(past) * 100
    return pd.Series(out, index=s.index)


def rolling_z(s: pd.Series, window: int, min_periods: Optional[int] = None) -> pd.Series:
    """z_t = (x_t − mean[t−window, t−1]) / sd[t−window, t−1] – công thức (8)."""
    x = pd.to_numeric(s, errors="coerce")
    mp = min_periods if min_periods is not None else max(10, window // 3)
    past = x.shift(1)
    mu = past.rolling(window, min_periods=mp).mean()
    sd = past.rolling(window, min_periods=mp).std(ddof=1)
    return (x - mu) / sd.replace(0, np.nan)


def rolling_past_quantile(s: pd.Series, window: int, q: float, min_periods: Optional[int] = None) -> pd.Series:
    """Ngưỡng phân vị q của cửa sổ [t−window, t−1] – dùng cho cờ 'độ vênh cao'."""
    x = pd.to_numeric(s, errors="coerce").shift(1)
    mp = min_periods if min_periods is not None else max(20, window // 5)
    return x.rolling(window, min_periods=mp).quantile(q)


def safe_div(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where((b == 0) | np.isnan(b), np.nan, a / b)
    return out


def streaks(sign: pd.Series) -> pd.Series:
    """Độ dài chuỗi cùng dấu liên tiếp tính đến phiên t (dương: mua ròng, âm: bán ròng, 0 nếu dấu 0/NaN)."""
    sg = np.sign(pd.to_numeric(sign, errors="coerce").fillna(0)).astype(int).to_numpy()
    out = np.zeros(len(sg), dtype=int)
    for i, v in enumerate(sg):
        if v == 0:
            out[i] = 0
        elif i > 0 and np.sign(out[i - 1]) == v:
            out[i] = out[i - 1] + v
        else:
            out[i] = v
    return pd.Series(out, index=sign.index)
