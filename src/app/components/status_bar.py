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


@st.cache_data(ttl=120, show_spinner=False)
def _ssi_today() -> bool:
    """SSI đã phát dữ liệu phiên hôm nay chưa (kiểm tra 2 phút/lần)."""
    try:
        from src.data import live
        return live.ssi_has_today()
    except Exception:  # noqa: BLE001
        return True


def active_source() -> str:
    return "SSI FastConnect V3"


def render(session_date=None, show_session: bool = True) -> None:
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
    sess_pill = f'<span class="ffr-pill">📅 Phiên {sess}</span>' if show_session else ""
    li = da.live_info()
    is_live = li is not None and sdate is not None and sdate == pd.Timestamp(li["session_date"])
    if is_live:
        tick = str(li.get("last_tick") or "")[-8:-3]
        live_pill = (f'<span class="ffr-pill" style="border-color:#DC2626;color:#F87171"><b>● TRỰC TIẾP</b>&nbsp;'
                     f'số liệu tới {tick or "—"} · dựng lúc {pd.Timestamp(li["built_at"]):%H:%M:%S} · '
                     f'{int(li["n_traded"])}/{int(li["n_symbols"])} mã có khớp lệnh</span>')
        comp_pill = '<span class="ffr-pill">Phiên tạm tính – chốt số liệu chính thức sau 15:05</span>'
    elif sdate is not None and "SSI-WS" in da.session_sources(sdate):
        live_pill = ('<span class="ffr-pill" style="border-color:#D97706;color:#F59E0B"><b>● ĐÓNG CỬA TẠM TÍNH</b>&nbsp;'
                     'giá chốt ATC từ luồng WebSocket SSI · tự thay bằng số liệu REST chính thức khi SSI công bố</span>')
        comp_pill = ""
    else:
        live_pill = ""
        comp_pill = f'<span class="ffr-pill">Đầy đủ: {frac_pct(comp, 1) if comp is not None else "—"}</span>'
    md(f'<div class="ffr-status">{demo}{sess_pill}{live_pill}'
       f'<span class="ffr-pill">⏱ {now_vn():%H:%M:%S} (giờ VN)</span>'
       f'<span class="ffr-pill">Nguồn: {active_source()}</span>{dots}'
       f'{comp_pill}</div>')
    if in_session() and li is not None:
        age = (now_vn().replace(tzinfo=None) - pd.Timestamp(li["built_at"])).total_seconds() / 60
        if age > float(get("alerts.stale_minutes", 5)):
            st.warning(f"⚠️ Phiên tạm tính dựng cách đây {age:.0f} phút – bộ ghi WebSocket có thể đã dừng.")
        elif not is_live:
            st.info("Đang xem một phiên cũ. Chọn phiên hôm nay ở ô bên trái để xem số liệu trực tiếp.")
        return
    if in_session():
        from src.common.config import public_mode
        if public_mode():                        # bản công khai không chạy bộ ghi – chỉ có dữ liệu đã đẩy lên
            return
        if not _ssi_today():
            st.info("ℹ️ SSI FastConnect chưa phát dữ liệu phiên hôm nay (masterdata và nến 1 phút đều trống – ngày nghỉ "
                    "hoặc SSI gián đoạn). Đang hiển thị phiên gần nhất; bộ ghi vẫn chạy nền và trang tự làm mới khi SSI có số liệu.")
            return
        st.info("⏳ Chưa có phiên tạm tính của hôm nay – bộ ghi WebSocket SSI đang dựng số liệu "
                "(lần đầu khoảng 30–60 giây). Trang tự làm mới khi có số liệu; trong lúc chờ đang hiển thị phiên gần nhất.")
        return
    # Dữ liệu cũ > 5 phút trong phiên → cảnh báo vàng
    if in_session():
        ok = srcs.get("SSI", (None, None, None))[2]
        if ok is not None and pd.notna(ok):
            age = (now_vn().replace(tzinfo=None) - pd.Timestamp(ok)).total_seconds() / 60
            if age > float(get("alerts.stale_minutes", 5)):
                st.warning(f"⚠️ Dữ liệu cũ hơn {age:.0f} phút trong phiên – số liệu có thể chưa cập nhật.")
