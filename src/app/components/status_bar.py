"""Thanh trạng thái đầu mỗi trang (bước B4.4): phiên, giờ cập nhật, nguồn, kết nối, tỷ lệ đầy đủ, cảnh báo dữ liệu cũ."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.app import data_access as da
from src.app.components.ui import md, pal
from src.common.config import get
from src.common.fmt import frac_pct
from src.common.timeutil import in_session, now_vn


def source_state() -> dict:
    """Màu chấm trạng thái của nguồn duy nhất SSI FastConnect V3."""
    st_df = da.source_status()
    out = {}
    r = st_df[st_df["source"] == "SSI"] if not st_df.empty else st_df
    if r.empty:
        out["SSI"] = ("#94A3B8", "chưa kết nối", None)
    else:
        r = r.iloc[0]
        status = str(r["status"])
        color = {"ok": "#16A34A", "degraded": "#F59E0B", "error": "#DC2626"}.get(status, "#94A3B8")
        out["SSI"] = (color, status, r["last_ok"])
    return out


def active_source() -> str:
    return "SSI FastConnect V3"


def render(session_date=None) -> None:
    p = pal()
    d = da.daily()
    last = d["trade_date"].max() if not d.empty else None
    sdate = pd.Timestamp(session_date) if session_date is not None else last
    q = da.table("data_quality_log")
    comp = None
    if not q.empty and sdate is not None:
        c = q[(q["check_name"] == "completeness") & (pd.to_datetime(q["trade_date"]) == sdate)]
        comp = float(c["value"].iloc[0]) if not c.empty else None
    srcs = source_state()
    dots = " ".join(f'<span class="ffr-pill"><span class="ffr-dot" style="background:{c}"></span>{k}: {s}</span>'
                    for k, (c, s, _) in srcs.items())
    demo = ""
    sess = sdate.strftime("%d/%m/%Y") if sdate is not None else "—"
    md(f'<div class="ffr-status">{demo}<span class="ffr-pill">📅 Phiên {sess}</span>'
       f'<span class="ffr-pill">⏱ {now_vn():%H:%M:%S} (giờ VN)</span>'
       f'<span class="ffr-pill">Nguồn: {active_source()}</span>{dots}'
       f'<span class="ffr-pill">Đầy đủ: {frac_pct(comp, 1) if comp is not None else "—"}</span></div>')
    # Dữ liệu cũ > 5 phút trong phiên → cảnh báo vàng
    if in_session():
        ok = srcs.get("SSI", (None, None, None))[2]
        if ok is not None and pd.notna(ok):
            age = (now_vn().replace(tzinfo=None) - pd.Timestamp(ok)).total_seconds() / 60
            if age > float(get("alerts.stale_minutes", 5)):
                st.warning(f"⚠️ Dữ liệu cũ hơn {age:.0f} phút trong phiên – số liệu có thể chưa cập nhật.")
