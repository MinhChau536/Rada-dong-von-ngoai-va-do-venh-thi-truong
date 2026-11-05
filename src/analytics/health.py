"""
Sức khỏe thị trường 0–100 và hiệu suất theo kỳ.
Kế thừa ms.market_health, ms.rsi, ms.period_returns của core/thi_truong_danh_muc.py (giữa kỳ) – sửa trọng số theo
mục 11.4: xu hướng 30%, động lượng 15%, hiệu suất 20 phiên 15%, độ rộng 25%, độ vênh 15% (= 100 − phân vị D).
Điểm theo quy tắc, chỉ để tham khảo – không phải dự báo hay khuyến nghị.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from src.common.config import get


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    out[(loss == 0) & (gain > 0)] = 100.0
    out[(loss == 0) & (gain == 0)] = 50.0
    return out


def period_returns(s: pd.Series) -> Dict[str, Optional[float]]:
    """Hiệu suất 1T, 1Th, 3Th, 6Th, YTD, 1N (%) – s: giá đóng cửa có index ngày. Lợi suất kỳ = P_t/P_{t−k} − 1."""
    out: Dict[str, Optional[float]] = {k: None for k in ("1T", "1Th", "3Th", "6Th", "YTD", "1N")}
    s = s.dropna().astype(float)
    if len(s) < 2:
        return out
    s.index = pd.to_datetime(s.index)
    last_dt, last = s.index[-1], float(s.iloc[-1])

    def since(dt):
        base = s[s.index <= dt]
        return None if base.empty or not base.iloc[-1] else (last / float(base.iloc[-1]) - 1) * 100

    out["1T"] = since(last_dt - pd.Timedelta(days=7))
    out["1Th"] = since(last_dt - pd.Timedelta(days=30))
    out["3Th"] = since(last_dt - pd.Timedelta(days=91))
    out["6Th"] = since(last_dt - pd.Timedelta(days=182))
    out["YTD"] = since(pd.Timestamp(year=last_dt.year, month=1, day=1) - pd.Timedelta(days=1))
    out["1N"] = since(last_dt - pd.Timedelta(days=365)) if s.index[0] <= last_dt - pd.Timedelta(days=360) else None
    return out


def market_health(index_close: pd.Series, pct_up: Optional[float], pct_above_ma20: Optional[float],
                  d_pct250: Optional[float]) -> Dict[str, Any]:
    W = get("health_weights", {})
    comps: Dict[str, Dict[str, Any]] = {}
    c = index_close.dropna().astype(float).reset_index(drop=True)
    if len(c) >= 30:
        last = float(c.iloc[-1])
        mas = {n: float(c.tail(n).mean()) for n in (20, 50, 200) if len(c) >= n}
        comps["trend"] = {"label": "Xu hướng", "weight": W.get("trend", 30),
                          "score": float(np.mean([100.0 if last > m else 0.0 for m in mas.values()])),
                          "detail": " · ".join(f"{'▲' if last > m else '▼'}MA{n}" for n, m in mas.items())}
        r = float(rsi(c, int(get("windows.rsi_period", 14))).iloc[-1])
        if not math.isnan(r):
            comps["momentum"] = {"label": "Động lượng", "weight": W.get("momentum", 15),
                                 "score": float(np.clip((r - 30) / 40 * 100, 0, 100)),
                                 "detail": f"RSI14 = {r:.1f}".replace(".", ",")}
        if len(c) > 20:
            r20 = (last / float(c.iloc[-21]) - 1) * 100
            comps["perf"] = {"label": "Hiệu suất 20 phiên", "weight": W.get("perf20", 15),
                             "score": float(np.clip(50 + r20 * 6, 0, 100)), "detail": f"{r20:+.2f}%".replace(".", ",")}
    if pct_up is not None and not pd.isna(pct_up):
        pm = pct_above_ma20 if pct_above_ma20 is not None and not pd.isna(pct_above_ma20) else pct_up
        comps["breadth"] = {"label": "Độ rộng", "weight": W.get("breadth", 25), "score": float((pct_up + pm) / 2),
                            "detail": f"{pct_up:.0f}% mã tăng · {pm:.0f}% trên MA20"}
    if d_pct250 is not None and not pd.isna(d_pct250):
        comps["divergence"] = {"label": "Độ vênh", "weight": W.get("divergence", 15), "score": float(100 - d_pct250),
                               "detail": f"phân vị D {d_pct250:.0f}%"}
    valid = [v for v in comps.values() if v.get("score") is not None]
    if not valid:
        return {"available": False, "components": comps}
    score = sum(v["score"] * v["weight"] for v in valid) / sum(v["weight"] for v in valid)
    L = get("health_labels", {"positive": 70, "caution": 40})
    label = "Tích cực" if score >= L["positive"] else "Thận trọng" if score >= L["caution"] else "Tiêu cực"
    return {"available": True, "score": float(score), "label": label, "components": comps,
            "weights_sum": sum(v["weight"] for v in comps.values())}
