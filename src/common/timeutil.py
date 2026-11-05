"""Tiện ích thời gian – mọi mốc chuẩn hóa theo Asia/Ho_Chi_Minh (mục 4 của đề)."""
from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pandas as pd

from src.common.config import get

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def now_vn() -> datetime:
    return datetime.now(VN_TZ)


def today_vn() -> date:
    return now_vn().date()


def _t(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def in_session(ts: datetime | None = None) -> bool:
    """Đang trong giờ giao dịch (thứ 2–6, 9:00–15:00 giờ VN; không xét ngày lễ)."""
    ts = ts or now_vn()
    if ts.weekday() >= 5:
        return False
    return _t(get("session.open", "09:00")) <= ts.time() <= _t(get("session.close", "15:00"))


def in_recorder_window(ts: datetime | None = None) -> bool:
    ts = ts or now_vn()
    if ts.weekday() >= 5:
        return False
    return _t(get("session.recorder_start", "08:55")) <= ts.time() <= _t(get("session.recorder_end", "15:05"))


def parse_ssi_date(s) -> pd.Timestamp:
    """SSI trả TradingDate dạng 'dd/mm/yyyy'."""
    return pd.to_datetime(s, format="%d/%m/%Y", errors="coerce")


def fmt_ssi_date(d) -> str:
    return pd.Timestamp(d).strftime("%d/%m/%Y")


def fmt_vn_date(d) -> str:
    return "—" if d is None or pd.isna(d) else pd.Timestamp(d).strftime("%d/%m/%Y")
