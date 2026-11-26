"""
FTSE Flow Radar – điểm vào ứng dụng Streamlit.

    streamlit run src/app/main.py

Ứng dụng chỉ đọc dữ liệu thật tải từ SSI FastConnect V3. Khi kho chỉ báo còn trống, chỉ mở trang
"Kết nối dữ liệu" (chẩn đoán API, IP cần đăng ký, nút tải dữ liệu) và trang "Phương pháp & giới hạn".
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Streamlit Cloud kéo code mới sau mỗi git push nhưng giữ module cũ trong bộ nhớ → lỗi import hàm mới (vd. session_label).
# Khi bất kỳ tệp .py trong src/ đổi, bỏ toàn bộ module src.* đã nạp để lần chạy này nạp lại bản mới.
_SRC_SIG = max((f.stat().st_mtime for f in (ROOT / "src").rglob("*.py")), default=0.0)
if getattr(sys, "_ffr_src_sig", _SRC_SIG) != _SRC_SIG:
    for _m in [m for m in sys.modules if m == "src" or m.startswith("src.")]:
        sys.modules.pop(_m, None)
sys._ffr_src_sig = _SRC_SIG

import pandas as pd
import streamlit as st  # noqa: E402

from src.app import data_access as da  # noqa: E402
from src.app.theme import css, register_plotly  # noqa: E402
from src.common.config import get  # noqa: E402

from src.common.logo import png_path  # noqa: E402

st.set_page_config(page_title=f"{get('app.name')}", page_icon=str(png_path()), layout="wide", initial_sidebar_state="expanded")
from src.app.components.banners import background_css, banner_css, load_prefs, normalize  # noqa: E402

_prefs = load_prefs()                                   # giao diện đã chọn lần trước (data/ui_prefs.json)
st.session_state.setdefault("theme", _prefs.get("theme", "light"))
st.session_state.setdefault("bg_choice", normalize(_prefs.get("background")))   # mặc định: Đêm sao tương tác
st.session_state.setdefault("bg_overlay", float(_prefs.get("overlay", 0.82)))
st.session_state.setdefault("bg_fx", False)  # B4.3: tắt hiệu ứng nền động, không còn tùy chọn bật

from src.app.views import (p_chan_doan, p_kiem_chung, p0_ket_noi, p1_tong_quan, p2_dan_dat, p3_khoi_ngoai, p4_su_kien, p5_watchlist,  # noqa: E402
                           p6_bao_cao, p7_chat_luong, p8_phuong_phap, p9_telegram, p10_backtest)

PAGES = {
    "Diễn biến thị trường": [                 # tổng quan → chẩn đoán → hai góc chi tiết: dẫn dắt, khối ngoại
        st.Page(p1_tong_quan.render, title="Tổng quan thị trường", icon=":material/dashboard:", url_path="tong-quan", default=True),
        st.Page(p_chan_doan.render, title="Chẩn đoán thị trường", icon=":material/insights:", url_path="chan-doan"),
        st.Page(p2_dan_dat.render, title="Dẫn dắt & độ vênh", icon=":material/stacked_bar_chart:", url_path="dan-dat"),
        st.Page(p3_khoi_ngoai.render, title="Ra-đa khối ngoại", icon=":material/radar:", url_path="khoi-ngoai"),
    ],
    "Danh mục & tiện ích": [
        st.Page(p5_watchlist.render, title="Watchlist Impact", icon=":material/visibility:", url_path="watchlist"),
        st.Page(p6_bao_cao.render, title="Báo cáo PDF", icon=":material/description:", url_path="bao-cao"),
        st.Page(p9_telegram.render, title="Bot Telegram", icon=":material/send:", url_path="telegram"),
    ],
    "Nghiên cứu & hệ thống": [               # FTSE là bối cảnh nghiên cứu, không phải trục chính của sản phẩm
        st.Page(p4_su_kien.render, title="Nghiên cứu: nâng hạng FTSE", icon=":material/event:", url_path="su-kien-ftse"),
        st.Page(p_kiem_chung.render, title="Kiểm chứng & dữ liệu", icon=":material/fact_check:", url_path="kiem-chung"),
        st.Page(p8_phuong_phap.render, title="Phương pháp & giới hạn", icon=":material/menu_book:", url_path="phuong-phap"),
    ],
}
if not da.ready():
    # Kho chỉ báo trống: vẫn hiện đủ menu, mỗi trang phân tích hiện nội dung sẽ có + lối tới "Kết nối dữ liệu";
    # trang Kết nối dữ liệu là trang mặc định. KHÔNG sinh dữ liệu giả.
    from src.app.components.states import page_waiting

    def _waiting(pg):
        path = pg.url_path or "tong-quan"                      # trang mặc định cũ trả url_path rỗng

        def _render(title=pg.title, url=path):
            page_waiting(title, url)
        _render.__name__ = f"waiting_{path.replace('-', '_')}"
        return st.Page(_render, title=pg.title, icon=pg.icon, url_path=path)

    keep = {"phuong-phap"}
    PAGES = {g: [pg if pg.url_path in keep else _waiting(pg) for pg in grp]
             for g, grp in PAGES.items()}
    PAGES["Nghiên cứu & hệ thống"].insert(0, st.Page(p0_ket_noi.render, title="Kết nối dữ liệu", icon=":material/cable:",
                                        url_path="ket-noi", default=True))
st.session_state["_pages"] = {pg.url_path: pg for grp in PAGES.values() for pg in grp}

nav = st.navigation(PAGES, position="hidden")
from src.app.components import sidebar  # noqa: E402

sidebar.render(PAGES, nav)                              # thanh bên đặt theme/nền TRƯỚC khi chèn CSS
mode = st.session_state["theme"]
register_plotly(mode)
st.markdown(css(mode), unsafe_allow_html=True)
st.markdown("<style>" + banner_css(mode == "dark")
            + background_css(st.session_state["bg_choice"], mode == "dark", st.session_state["bg_overlay"],
                             nav.url_path or "tong-quan") + "</style>",
            unsafe_allow_html=True)
from src.app.components import starfield  # noqa: E402
from src.app.components.banners import STARS  # noqa: E402

starfield.inject(normalize(st.session_state["bg_choice"]) == STARS and mode == "dark", True)  # sao chỉ ở chế độ Tối
if st.session_state.pop("sb_search_go", False) and nav.url_path != "watchlist" and "watchlist" in st.session_state["_pages"]:
    st.switch_page(st.session_state["_pages"]["watchlist"])
from src.app.components.ui import md  # noqa: E402

# ── Tự cập nhật phiên mới: khi khởi động app và kiểm tra lại mỗi 30 phút (tiến trình nền, src/data/autoupdate.py) ──
@st.cache_resource(ttl=1800, show_spinner=False)
def _autoupdate() -> dict:
    from src.data import autoupdate
    autoupdate.start_recorder_if_session()          # trong giờ giao dịch: tự ghi luồng WebSocket SSI V3
    return autoupdate.start_if_behind()


def _autoupdate_notice() -> None:
    from src.data import autoupdate
    au = _autoupdate()
    if au.get("state") == "started":
        code = autoupdate.finished(au)
        if code is None:
            md(f'<div class="ffr-note">🔄 <span>'
               f'<b>Đang tự tải phiên mới từ SSI</b> (kho tới {au.get("from")}, cần tới {au.get("to")}) – chạy nền, '
               f'trang vẫn dùng được; bấm <b>Làm mới</b> sau 1–3 phút để xem số liệu mới.</span></div>')
        elif not au.get("_done"):
            au["_done"] = True
            da.clear_cache()
            st.toast("Đã cập nhật dữ liệu phiên mới từ SSI" if code == 0 else
                     "Tự cập nhật chưa thành công – xem logs/job_autoupdate.log", icon="✅" if code == 0 else "⚠️")
    elif au.get("state") == "running":
        md('<div class="ffr-note">🔄 <span>'
           'Một tiến trình khác đang cập nhật dữ liệu (bộ lập lịch hoặc nút trên trang Kết nối dữ liệu).</span></div>')



md('<div class="ffr-acad">🎓 <span><b>Đề tài nghiên cứu học thuật</b> – số liệu và nhận định chỉ phục vụ học tập, nghiên cứu; '
   '<b>không mang tính chất khuyến nghị đầu tư</b>.</span></div>')   # nhắc trên MỌI trang
from src.common.config import public_mode  # noqa: E402
if public_mode():
    _last = da.sessions()[-1] if da.ready() and da.sessions() else None
    from tools import snapshot as _snap
    try:
        _st = (_snap.STAMP.read_text(encoding="utf-8") if _snap.STAMP.exists() else "-") + " / disk " + _snap.stamp()
    except Exception as _e:  # noqa: BLE001
        _st = repr(_e)
    md(f'<div class="ffr-note" data-stamp="{_st}">🌐 <span><b>Bản công khai chỉ xem</b> · dữ liệu SSI FastConnect tới phiên '
       f'<b>{_last:%d/%m/%Y}</b> · tự cập nhật sau khi SSI công bố số liệu cuối ngày.</span></div>' if _last is not None else
       '<div class="ffr-note">🌐 <span><b>Bản công khai (chỉ xem)</b></span></div>')
else:
    _autoupdate_notice()


# ── Trong giờ giao dịch: tự làm mới khi bộ ghi dựng xong phiên tạm tính mới (≈ 2 phút/lần, src/data/live.py) ──
@st.fragment(run_every=20)
def _live_watch() -> None:
    from src.common.timeutil import in_session
    if not in_session() and not st.session_state.get("_live_v"):
        return
    v = da._lv()
    old = st.session_state.get("_live_v")
    st.session_state["_live_v"] = v
    if old is None or v == old:
        return
    prev_last = st.session_state.get("_live_last")
    da.clear_cache()
    new_last = da.sessions()[-1] if da.sessions() else None
    st.session_state["_live_last"] = new_last
    if prev_last is not None:                    # ô chọn phiên đang ở phiên mới nhất → chuyển sang phiên mới
        for k, val in list(st.session_state.items()):
            if isinstance(val, pd.Timestamp) and val == prev_last and k != "_live_last":
                del st.session_state[k]
    st.rerun(scope="app")


if "_live_last" not in st.session_state:
    st.session_state["_live_last"] = da.sessions()[-1] if da.ready() and da.sessions() else None
_live_watch()
nav.run()
