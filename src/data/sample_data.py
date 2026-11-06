"""
Bộ dữ liệu mẫu THẬT cho người chấm (bước B13.2) – trích từ kho đã tải qua API, không sinh dữ liệu giả.

    python -m src.data.sample_data export            # xuất N phiên gần nhất của bảng raw_* ra data_sample/
    python -m src.data.sample_data load              # nạp data_sample/ vào kho rồi chạy rebuild_all

Chỉ xuất bảng raw (phản hồi JSON gốc của SSI/NEO) + danh mục chứng khoán; không chứa khóa, token hay dữ liệu tài khoản.
Kết quả phụ thuộc lịch sử ngắn (phân vị 250 phiên, nghiên cứu sự kiện) sẽ hiển thị "chưa đủ dữ liệu" – đúng như thiết kế.
"""
from __future__ import annotations

import argparse

import pandas as pd

from src.common.config import abs_path, get
from src.common.logging import get_logger
from src.data import database as db

log = get_logger(__name__)
TABLES = {"raw_daily_stock": "trade_date", "raw_daily_index": "trade_date", "raw_securities": None,
          "raw_index_components": None}


def export(n_sessions: int | None = None) -> dict:
    n = int(n_sessions or get("sample.sessions", 10))
    out_dir = abs_path("data_sample")
    out_dir.mkdir(exist_ok=True)
    dates = db.query_df("SELECT DISTINCT trade_date FROM raw_daily_stock ORDER BY trade_date DESC LIMIT ?", [n])
    if dates.empty:
        raise SystemExit("raw_daily_stock trống – tải dữ liệu thật trước (python -m src.data.backfill).")
    start = pd.to_datetime(dates["trade_date"]).min().date()
    res = {}
    for t, dcol in TABLES.items():
        sql = f"SELECT * FROM {t}" + (f" WHERE {dcol} >= ?" if dcol else "")
        df = db.query_df(sql, [start] if dcol else [])
        df.to_csv(out_dir / f"{t}.csv", index=False, encoding="utf-8")
        res[t] = len(df)
    log.info("Đã xuất dữ liệu mẫu thật từ %s: %s", start, res)
    return res


def load(rebuild: bool = True) -> dict:
    db.init_schema()
    res = {}
    for t in TABLES:
        p = abs_path("data_sample") / f"{t}.csv"
        if p.exists():
            df = pd.read_csv(p, dtype=str, keep_default_na=False)
            for c in ("trade_date", "as_of"):
                if c in df:
                    df[c] = pd.to_datetime(df[c]).dt.date
            if "loaded_at" in df:
                df["loaded_at"] = pd.to_datetime(df["loaded_at"])
            res[t] = db.upsert(t, df)
    if rebuild:
        from src.data import rebuild_all
        rebuild_all.main(robustness=False, backtest=False)
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["export", "load"])
    ap.add_argument("--sessions", type=int)
    a = ap.parse_args()
    print(export(a.sessions) if a.action == "export" else load())
