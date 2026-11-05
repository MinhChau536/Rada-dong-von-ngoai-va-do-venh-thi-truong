"""Thanh trạng thái đầu mỗi trang (bước B4.4): phiên, giờ cập nhật, nguồn, kết nối, tỷ lệ đầy đủ, cảnh báo dữ liệu cũ."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.app import data_access as da
from src.app.components.ui import md, pal
from src.common.config import get, is_demo
from src.common.fmt import frac_pct
from src.common.timeutil import in_session, now_vn


def source_state() -> dict:
    """Nguồn đang dùng & màu chấm trạng thái cho SSI và NEO."""
    st_df = da.source_status()
    out = {}
    for src in ("SSI", "NEO"):
        r = st_df[st_df["source"] == src]
        if r.empty:
            out[src] = ("#94A3B8", "chưa kết nối", None)
            continue
        r = r.iloc[0]
        status = str(r["status"])
        color = {"ok": "#16A34A", "demo": "#F59E0B", "degraded": "#F59E0B", "error": "#DC2626"}.get(status, "#94A3B8")
        out[src] = (color, status, r["last_ok"])
    return out


def active_source() -> str:
    ev = da.table("source_events")
    if not ev.empty:
        last = ev.sort_values("ts").iloc[-1]
        if last["to_source"] == "NEO":
            return "NEO (dự phòng)"
    return "Dữ liệu mẫu" if is_demo() else "SSI FastConnect"


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
    demo = '<span class="ffr-pill ffr-demo">⚠ DỮ LIỆU MẪU tổng hợp – không phải số liệu thị trường thật</span>' if is_demo() else ""
    sess = sdate.strftime("%d/%m/%Y") if sdate is not None else "—"
    md(f'<div class="ffr-status">{demo}<span class="ffr-pill">📅 Phiên {sess}</span>'
       f'<span class="ffr-pill">⏱ {now_vn():%H:%M:%S} (giờ VN)</span>'
       f'<span class="ffr-pill">Nguồn: {active_source()}</span>{dots}'
       f'<span class="ffr-pill">Đầy đủ: {frac_pct(comp, 1) if comp is not None else "—"}</span></div>')
    # Dữ liệu cũ > 5 phút trong phiên → cảnh báo vàng (không áp dụng cho dữ liệu mẫu)
    if not is_demo() and in_session():
        ok = srcs.get("SSI", (None, None, None))[2]
        if ok is not None and pd.notna(ok):
            age = (now_vn().replace(tzinfo=None) - pd.Timestamp(ok)).total_seconds() / 60
            if age > float(get("alerts.stale_minutes", 5)):
                st.warning(f"⚠️ Dữ liệu cũ hơn {age:.0f} phút trong phiên – số liệu có thể chưa cập nhật.")
