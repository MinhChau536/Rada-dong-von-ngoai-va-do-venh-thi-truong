"""
Tầng đọc dữ liệu cho giao diện – mọi trang đọc từ indicator_* (cùng nguồn với PDF và Telegram).
Có st.cache_data(ttl=60) để chuyển trang < 2 giây; nút "Làm mới" gọi clear_cache().

Trong giờ giao dịch, phiên HÔM NAY lấy từ kho phụ data/live.duckdb (phiên tạm tính, dựng lại mỗi ~2 phút từ luồng
WebSocket SSI – src/data/live.py) và được ghép vào sau dữ liệu lịch sử. Khóa cache gồm thời điểm dựng phiên tạm tính
nên mỗi lần dựng mới, trang đọc số liệu mới ngay.
"""
from __future__ import annotations

from typing import List, Optional

import pandas as pd
import streamlit as st

from src.data import database as db

TTL = 60


def _q(sql: str, params: Optional[list] = None, path=None) -> pd.DataFrame:
    df = db.query_df(sql, params or [], path=path)
    for c in df.columns:
        if c in ("trade_date", "event_date", "session_date", "as_of"):
            df[c] = pd.to_datetime(df[c])
    return df


# ── phiên tạm tính trong giờ giao dịch ────────────────────────────────────────
@st.cache_data(ttl=15, show_spinner=False)
def live_info() -> Optional[dict]:
    """Thông tin phiên tạm tính còn hiệu lực (None nếu ngoài phiên / kho chính đã có phiên hôm nay)."""
    from src.data import live
    try:
        return live.meta()
    except Exception:  # noqa: BLE001
        return None


def session_progress(session_date) -> Optional[float]:
    """Phiên `session_date` đang là phiên tạm tính trong giờ → tỷ lệ thời gian giao dịch đã qua (0–1) tại lần dựng
    gần nhất (9:00–11:30 và 13:00–15:00 = 270 phút). Ngoài phiên / đã có số đóng cửa → None."""
    li = live_info()
    if not li or session_date is None or pd.Timestamp(li["session_date"]) != pd.Timestamp(session_date):
        return None
    t = pd.Timestamp(li["built_at"])
    m = t.hour * 60 + t.minute
    done = max(0, min(m, 11 * 60 + 30) - 9 * 60) + max(0, min(m, 15 * 60) - 13 * 60)
    frac = done / 270
    return None if frac >= 0.995 else max(frac, 0.02)


def _lv() -> str:
    """Phiên bản dữ liệu tạm tính – dùng làm khóa cache."""
    li = live_info()
    return str(li["built_at"]) if li else ""


def _live_date() -> Optional[pd.Timestamp]:
    li = live_info()
    return pd.Timestamp(li["session_date"]) if li else None


def _lq(sql: str, params: Optional[list] = None) -> pd.DataFrame:
    from src.data import live
    try:
        return _q(sql, params, path=live.LIVE_DB)
    except Exception:  # noqa: BLE001 – tệp đang được thay bằng bản mới
        return pd.DataFrame()


def _cat(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    if b is None or b.empty:
        return a
    if a.empty:
        return b
    return pd.concat([a, b[[c for c in b.columns if c in a.columns]]], ignore_index=True)


@st.cache_data(ttl=TTL, show_spinner=False)
def ready() -> bool:
    return db.table_exists("indicator_daily") and not _q("SELECT 1 FROM indicator_daily LIMIT 1").empty


@st.cache_data(ttl=TTL, show_spinner=False)
def session_sources(date=None) -> dict:
    """Số mã theo nguồn (SSI) của một phiên (mặc định phiên mới nhất) trong fact_daily_stock."""
    if not db.table_exists("fact_daily_stock"):
        return {}
    if date is None:
        df = _q("SELECT source, COUNT(*) AS n FROM fact_daily_stock WHERE trade_date = "
                "(SELECT MAX(trade_date) FROM fact_daily_stock) GROUP BY 1")
    else:
        df = _q("SELECT source, COUNT(*) AS n FROM fact_daily_stock WHERE trade_date = ? GROUP BY 1", [pd.Timestamp(date)])
    return dict(zip(df["source"], df["n"].astype(int))) if not df.empty else {}


@st.cache_data(ttl=TTL, show_spinner=False)
def raw_counts() -> dict:
    """Số bản ghi tầng raw theo bảng và nguồn – trang Kết nối dữ liệu."""
    out = {}
    for t in ("raw_daily_stock", "raw_daily_index", "raw_securities", "raw_intraday", "raw_stream"):
        if db.table_exists(t):
            df = _q(f"SELECT source, COUNT(*) AS n FROM {t} GROUP BY 1")
            out[t] = dict(zip(df["source"], df["n"].astype(int))) if not df.empty else {}
    return out


def daily() -> pd.DataFrame:
    return _daily(_lv())


@st.cache_data(ttl=TTL, show_spinner=False)
def _daily(v: str) -> pd.DataFrame:
    d = _q("SELECT * FROM indicator_daily ORDER BY trade_date")
    ld = _live_date()
    return _cat(d, _lq("SELECT * FROM indicator_daily WHERE trade_date = ?", [ld])) if ld is not None else d


def sessions() -> List[pd.Timestamp]:
    return list(daily()["trade_date"])


def index_hist(code: str) -> pd.DataFrame:
    return _index_hist(code, _lv())


@st.cache_data(ttl=TTL, show_spinner=False)
def _index_hist(code: str, v: str) -> pd.DataFrame:
    d = _q("SELECT * FROM fact_daily_index WHERE index_code = ? ORDER BY trade_date", [code])
    ld = _live_date()
    return _cat(d, _lq("SELECT * FROM fact_daily_index WHERE index_code = ? AND trade_date = ?", [code, ld])) \
        if ld is not None else d


def stock_day(date) -> pd.DataFrame:
    return _stock_day(pd.Timestamp(date), _lv())


@st.cache_data(ttl=TTL, show_spinner=False)
def _stock_day(date, v: str) -> pd.DataFrame:
    if _live_date() is not None and pd.Timestamp(date) == _live_date():
        return _lq("SELECT * FROM indicator_stock_daily WHERE trade_date = ?", [pd.Timestamp(date)])
    return _q("SELECT * FROM indicator_stock_daily WHERE trade_date = ?", [pd.Timestamp(date)])


def stock_hist(symbol: str) -> pd.DataFrame:
    return _stock_hist(symbol.upper(), _lv())


@st.cache_data(ttl=TTL, show_spinner=False)
def _stock_hist(symbol: str, v: str) -> pd.DataFrame:
    d = _q("SELECT * FROM indicator_stock_daily WHERE symbol = ? ORDER BY trade_date", [symbol])
    ld = _live_date()
    return _cat(d, _lq("SELECT * FROM indicator_stock_daily WHERE symbol = ? AND trade_date = ?", [symbol, ld])) \
        if ld is not None else d


def sparks(date, n: int = 30) -> pd.DataFrame:
    """Chuỗi giá đóng cửa n phiên gần nhất của mọi mã (cho sparkline)."""
    return _sparks(pd.Timestamp(date), n, _lv())


@st.cache_data(ttl=TTL, show_spinner=False)
def _sparks(d, n: int, v: str) -> pd.DataFrame:
    df = _q("SELECT symbol, trade_date, close FROM indicator_stock_daily WHERE trade_date <= ? "
            "AND trade_date >= ? ORDER BY trade_date", [d, d - pd.Timedelta(days=int(n * 1.6) + 10)])
    ld = _live_date()
    if ld is not None and d >= ld:
        df = _cat(df, _lq("SELECT symbol, trade_date, close FROM indicator_stock_daily WHERE trade_date = ?", [ld]))
    return df


def stock_range(start, end) -> pd.DataFrame:
    return _stock_range(pd.Timestamp(start), pd.Timestamp(end), _lv())


@st.cache_data(ttl=TTL, show_spinner=False)
def _stock_range(start, end, v: str) -> pd.DataFrame:
    df = _q("SELECT * FROM indicator_stock_daily WHERE trade_date BETWEEN ? AND ?", [start, end])
    ld = _live_date()
    if ld is not None and start <= ld <= end:
        df = _cat(df, _lq("SELECT * FROM indicator_stock_daily WHERE trade_date = ?", [ld]))
    return df


def leaders(date) -> pd.DataFrame:
    return _leaders(pd.Timestamp(date), _lv())


@st.cache_data(ttl=TTL, show_spinner=False)
def _leaders(date, v: str) -> pd.DataFrame:
    q = "SELECT * FROM leaders_daily WHERE trade_date = ? ORDER BY side, rank"
    return _lq(q, [date]) if _live_date() is not None and date == _live_date() else _q(q, [date])


def groups(date=None, group_type: Optional[str] = None) -> pd.DataFrame:
    return _groups(pd.Timestamp(date) if date is not None else None, group_type, _lv())


@st.cache_data(ttl=TTL, show_spinner=False)
def _groups(date, group_type: Optional[str], v: str) -> pd.DataFrame:
    ld = _live_date()
    if ld is not None and date is not None and date == ld:
        sql, p = "SELECT * FROM indicator_group_daily WHERE trade_date = ?", [date]
        if group_type:
            sql += " AND group_type = ?"
            p.append(group_type)
        return _lq(sql, p)
    sql, p = "SELECT * FROM indicator_group_daily WHERE 1=1", []
    if date is not None:
        sql += " AND trade_date = ?"
        p.append(date)
    if group_type:
        sql += " AND group_type = ?"
        p.append(group_type)
    df = _q(sql + " ORDER BY trade_date", p)
    if ld is not None and date is None:
        lsql, lp = "SELECT * FROM indicator_group_daily WHERE trade_date = ?", [ld]
        if group_type:
            lsql += " AND group_type = ?"
            lp.append(group_type)
        df = _cat(df, _lq(lsql, lp))
    return df


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
def stream_stats() -> pd.DataFrame:
    """Thống kê luồng WebSocket SSI V3 đã lưu theo phiên."""
    if not db.table_exists("raw_stream"):
        return pd.DataFrame()
    return _q("""SELECT session_date, source, COUNT(*) AS n_msg, MIN(recv_ts) AS first_ts, MAX(recv_ts) AS last_ts,
                        COUNT(DISTINCT channel) AS n_channels
                 FROM raw_stream GROUP BY 1, 2 ORDER BY 1""")


@st.cache_data(ttl=15, show_spinner=False)
def stream_gaps() -> pd.DataFrame:
    """Tổng thời gian mất kết nối (khoảng trống > 90 giây giữa 2 tin indexsummary.VNINDEX liên tiếp) theo phiên."""
    if not db.table_exists("raw_stream"):
        return pd.DataFrame()
    df = _q("SELECT session_date, recv_ts FROM raw_stream WHERE channel = 'indexsummary' AND symbol = 'VNINDEX' "
            "ORDER BY recv_ts")
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
