"""
Ảnh chụp CUỐI PHIÊN từ luồng NEO WebSocket (thuyết minh mục 6.2 – NEO thay thế khi SSI gián đoạn).

    python -m src.data.neo_eod                 # dựng cho phiên hôm nay
    python -m src.data.neo_eod --date 2026-11-09

Lấy tin stockInfo / marketInfo CUỐI CÙNG của mỗi mã / chỉ số trong phiên từ raw_stream_neo, chuẩn hóa đơn vị về
VND (NEO có thể trả giá theo nghìn đồng và giá trị theo triệu đồng – suy ra hệ số từ chính dữ liệu bằng đồng nhất
thức GTGD ≈ KL × giá), rồi ghi vào raw_daily_stock / raw_daily_index với source='NEO'. build_facts ưu tiên SSI,
nên NEO chỉ được dùng cho phiên/mã mà SSI thiếu – phiên đó được đánh dấu nguồn NEO trong kho.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from typing import Optional

import numpy as np
import pandas as pd

from src.common.logging import get_logger
from src.common.timeutil import today_vn
from src.data import database as db

log = get_logger(__name__)
PRICE_KEYS = ("refPrice", "ceilingPrice", "floorPrice", "openPrice", "highPrice", "lowPrice", "closePrice", "averagePrice")
VALUE_KEYS = ("totalTradingValue", "foreignBuyValue", "foreignSellValue", "foreignNetValue", "ptTotalTradedValue")
INDEX_MAP = {"VNINDEX": "VNINDEX", "VN30": "VN30", "HNXINDEX": "HNXINDEX", "HNX": "HNXINDEX",
             "UPCOMINDEX": "UPCOMINDEX", "HNXUPCOMINDEX": "UPCOMINDEX", "UPCOM": "UPCOMINDEX"}


def _f(x) -> float:
    try:
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return np.nan


def _pow10(x: float) -> float:
    return float(10 ** round(np.log10(x))) if x and np.isfinite(x) and x > 0 else 1.0


def unit_factors(recs: pd.DataFrame) -> tuple[float, float]:
    """(hệ số giá, hệ số giá trị) để quy về VND."""
    ref = recs["refPrice"].map(_f) if "refPrice" in recs else pd.Series(dtype=float)
    p_k = 1000.0 if ref.median() < 500 else 1.0                    # cổ phiếu HOSE không có giá < 500 đồng
    if {"totalTradingValue", "totalTradingVolume", "closePrice"} <= set(recs.columns):
        tv, vol, px = (recs[c].map(_f) for c in ("totalTradingValue", "totalTradingVolume", "closePrice"))
        ratio = (vol * px * p_k / tv).replace([np.inf, -np.inf], np.nan)
        v_k = _pow10(ratio[(vol > 0) & (tv > 0)].median())
    else:
        v_k = 1.0
    return p_k, v_k


def snapshot_to_raw(d: Optional[date] = None, path=None) -> dict:
    d = d or today_vn()
    raw = db.query_df("SELECT recv_ts, channel, symbol, payload FROM raw_stream_neo WHERE session_date = ? "
                      "AND channel IN ('stockInfo','marketInfo') ORDER BY recv_ts", [d], path=path)
    if raw.empty:
        log.info("NEO EOD %s: chưa có tin stockInfo/marketInfo", d)
        return {"date": str(d), "stocks": 0, "indexes": 0}
    now = datetime.now().replace(microsecond=0)
    out = {"date": str(d), "stocks": 0, "indexes": 0}

    st = raw[raw["channel"] == "stockInfo"]
    if not st.empty:
        # tin stockInfo là cập nhật từng phần → gộp lũy kế theo mã (giá trị khác NULL mới nhất)
        recs = pd.DataFrame([json.loads(p) for p in st["payload"]])
        recs["symbol"] = recs["symbol"].astype(str).str.upper()
        last = recs.groupby("symbol", sort=False).last()               # last() bỏ qua NULL theo từng cột
        last = last.reset_index()
        p_k, v_k = unit_factors(last)
        rows = []
        for r in last.to_dict("records"):
            payload = {k: v for k, v in r.items() if v is not None and not (isinstance(v, float) and np.isnan(v))}
            for k in PRICE_KEYS:
                if k in payload:
                    payload[k] = _f(payload[k]) * p_k
            for k in VALUE_KEYS:
                if k in payload:
                    payload[k] = _f(payload[k]) * v_k
            payload["tradingDate"] = d.strftime("%d/%m/%Y")
            payload["_unit_factors"] = {"price": p_k, "value": v_k}
            rows.append({"trade_date": d, "symbol": r["symbol"], "source": "NEO",
                         "payload": json.dumps(payload, ensure_ascii=False, default=str), "loaded_at": now})
        out["stocks"] = db.upsert("raw_daily_stock", pd.DataFrame(rows), path=path)
        out["unit_factors"] = {"price": p_k, "value": v_k}

    mi = raw[raw["channel"] == "marketInfo"]
    if not mi.empty:
        recs = pd.DataFrame([json.loads(p) for p in mi["payload"]])
        recs["index_code"] = recs["indexCode"].astype(str).str.upper().map(INDEX_MAP)
        recs = recs.dropna(subset=["index_code"])
        last = recs.groupby("index_code", sort=False).last().reset_index()
        rows = [{"trade_date": d, "index_code": r["index_code"], "source": "NEO",
                 "payload": json.dumps({**{k: v for k, v in r.items() if k != "index_code" and v is not None},
                                        "tradingDate": d.strftime("%d/%m/%Y")}, ensure_ascii=False, default=str),
                 "loaded_at": now} for r in last.to_dict("records")]
        out["indexes"] = db.upsert("raw_daily_index", pd.DataFrame(rows), path=path)
    log.info("NEO EOD: %s", out)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    a = ap.parse_args()
    db.init_schema()
    print(snapshot_to_raw(pd.Timestamp(a.date).date() if a.date else None))
