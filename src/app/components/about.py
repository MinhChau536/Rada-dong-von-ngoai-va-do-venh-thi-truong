"""Khối giới thiệu sản phẩm (bước B4.4b): tên, mục tiêu, người dùng, miễn trừ – đúng mục 6 của đề."""
from __future__ import annotations

from src.app.components.ui import md
from src.common.config import get

GOAL = ("đo mức lan tỏa của VN-Index, mã dẫn dắt và dòng vốn ngoại trong giai đoạn nâng hạng FTSE, "
        "và tác động lên danh mục theo dõi")
USERS = "nhà đầu tư cá nhân, chuyên viên phân tích, sinh viên tài chính"


def render_intro() -> None:
    md(f'<div class="ffr-intro"><span><b>{get("app.name")}</b> · {GOAL} · dành cho {USERS}.</span>'
       f'<span>⚖️ {get("app.disclaimer")}</span></div>')


def render_full() -> None:
    md(f"""<div class="ffr-card"><div class="ffr-lbl">Giới thiệu sản phẩm</div>
    <div style="font-size:20px;font-weight:800;margin:4px 0">{get("app.name")} {get("app.version")}</div>
    <p><b>Mục tiêu:</b> {GOAL}.</p><p><b>Người dùng:</b> {USERS}.</p>
    <p><b>Dữ liệu:</b> SSI FastConnect Data (nguồn chính, lịch sử & thời gian thực) và VPBankS NEO API
    (luồng WebSocket ghi song song, đối chiếu chéo, dự phòng).</p>
    <p><b>Không làm:</b> đặt lệnh, quản trị danh mục, khuyến nghị mua bán, kết luận nhân quả.</p>
    <p style="color:#B45309"><b>⚖️ {get("app.disclaimer")}</b></p></div>""")
