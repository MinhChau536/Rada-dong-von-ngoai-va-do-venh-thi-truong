"""
Tầng đọc dữ liệu cho giao diện – mọi trang đọc từ indicator_* (cùng nguồn với PDF và Telegram).
Có st.cache_data(ttl=60) để chuyển trang < 2 giây; nút "Làm mới" gọi clear_cache().
"""
from __future__ import annotations

from typing import List, Optional

import pandas as pd
import streamlit as st

from src.data import database as db

TTL = 60


def _q(sql: str, params: Optional[list] = None) -> pd.DataFrame:
    df = db.query_df(sql, params or [])
    for c in df.columns:
        if c in ("trade_date", "event_date", "session_date", "as_of"):
            df[c] = pd.to_datetime(df[c])
    return df


@st.cache_data(ttl=TTL, show_spinner=False)
def ready() -> bool:
    return db.table_exists("indicator_daily") and not _q("SELECT 1 FROM indicator_daily LIMIT 1").empty


@st.cache_data(ttl=TTL, show_spinner=False)
def daily() -> pd.DataFrame:
    return _q("SELECT * FROM indicator_daily ORDER BY trade_date")


@st.cache_data(ttl=TTL, show_spinner=False)
def sessions() -> List[pd.Timestamp]:
    return list(daily()["trade_date"])


@st.cache_data(ttl=TTL, show_spinner=False)
def index_hist(code: str) -> pd.DataFrame:
    return _q("SELECT * FROM fact_daily_index WHERE index_code = ? ORDER BY trade_date", [code])


@st.cache_data(ttl=TTL, show_spinner=False)
def stock_day(date) -> pd.DataFrame:
    return _q("SELECT * FROM indicator_stock_daily WHERE trade_date = ?", [pd.Timestamp(date)])


@st.cache_data(ttl=TTL, show_spinner=False)
def stock_hist(symbol: str) -> pd.DataFrame:
    return _q("SELECT * FROM indicator_stock_daily WHERE symbol = ? ORDER BY trade_date", [symbol.upper()])


@st.cache_data(ttl=TTL, show_spinner=False)
def sparks(date, n: int = 30) -> pd.DataFrame:
    """Chuỗi giá đóng cửa n phiên gần nhất của mọi mã (cho sparkline)."""
    d = pd.Timestamp(date)
    df = _q("SELECT symbol, trade_date, close FROM indicator_stock_daily WHERE trade_date <= ? "
            "AND trade_date >= ? ORDER BY trade_date", [d, d - pd.Timedelta(days=int(n * 1.6) + 10)])
    return df


@st.cache_data(ttl=TTL, show_spinner=False)
def stock_range(start, end) -> pd.DataFrame:
    return _q("SELECT * FROM indicator_stock_daily WHERE trade_date BETWEEN ? AND ?", [pd.Timestamp(start), pd.Timestamp(end)])


@st.cache_data(ttl=TTL, show_spinner=False)
def leaders(date) -> pd.DataFrame:
    return _q("SELECT * FROM leaders_daily WHERE trade_date = ? ORDER BY side, rank", [pd.Timestamp(date)])


@st.cache_data(ttl=TTL, show_spinner=False)
def groups(date=None, group_type: Optional[str] = None) -> pd.DataFrame:
    sql, p = "SELECT * FROM indicator_group_daily WHERE 1=1", []
    if date is not None:
        sql += " AND trade_date = ?"
        p.append(pd.Timestamp(date))
    if group_type:
        sql += " AND group_type = ?"
        p.append(group_type)
    return _q(sql + " ORDER BY trade_date", p)


@st.cache_data(ttl=TTL, show_spinner=False)
def table(name: str) -> pd.DataFrame:
    if not db.table_exists(name):
        return pd.DataFrame()
    return _q(f"SELECT * FROM {name}")


@st.cache_data(ttl=TTL, show_spinner=False)
def universe(name: str) -> List[str]:
    return _q("SELECT symbol FROM dim_universe WHERE universe = ?", [name])["symbol"].tolist()


@st.cache_data(ttl=TTL, show_spinner=False)
def symbols() -> List[str]:
    return _q("SELECT DISTINCT symbol FROM indicator_stock_daily ORDER BY symbol")["symbol"].tolist()


@st.cache_data(ttl=15, show_spinner=False)
def source_status() -> pd.DataFrame:
    return _q("SELECT * FROM source_status")


@st.cache_data(ttl=15, show_spinner=False)
def neo_stream_stats() -> pd.DataFrame:
    return _q("""SELECT session_date, source, COUNT(*) AS n_msg, MIN(recv_ts) AS first_ts, MAX(recv_ts) AS last_ts,
                        COUNT(DISTINCT channel) AS n_channels
                 FROM raw_stream_neo GROUP BY 1, 2 ORDER BY 1""")


@st.cache_data(ttl=15, show_spinner=False)
def neo_gaps() -> pd.DataFrame:
    """Tổng thời gian mất kết nối (khoảng trống > 90 giây giữa 2 tin marketInfo liên tiếp) theo phiên."""
    df = _q("SELECT session_date, recv_ts FROM raw_stream_neo WHERE channel = 'marketInfo' ORDER BY recv_ts")
    if df.empty:
        return df
    df["recv_ts"] = pd.to_datetime(df["recv_ts"])
    out = []
    for d, g in df.groupby("session_date"):
        dt = g["recv_ts"].diff().dt.total_seconds().fillna(0)
        dt = dt[(dt > 90) & (dt < 3600)]  # bỏ nghỉ trưa
        out.append({"session_date": d, "gap_minutes": float((dt - 60).clip(lower=0).sum() / 60), "n_gaps": int(len(dt))})
    return pd.DataFrame(out)


def clear_cache() -> None:
    st.cache_data.clear()
