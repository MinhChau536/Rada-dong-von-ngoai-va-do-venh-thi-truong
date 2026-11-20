"""
Chẩn đoán kết nối SSI FastConnect V3 (dùng chung cho trang "Kết nối dữ liệu", trang 7 và dòng lệnh).

    python -m src.data.diagnostics

Mỗi phép kiểm tra trả {ok, detail, hint}. Không bao giờ in khóa/token; chỉ in thông điệp lỗi của máy chủ.
"""
from __future__ import annotations

import time
from datetime import timedelta
from typing import Dict

import requests

from src.common.config import env, ssi_base_url, ssi_configured, ssi_stream_url
from src.common.logging import get_logger
from src.common.timeutil import today_vn

log = get_logger(__name__)
KEY_HINT = ("Tạo API Key + API Secret tại SSI Developer Portal (developers.ssi.com.vn) › Quản lý API Key, "
            "nhóm quyền Market Data / stream DATA; điền SSI_API_KEY, SSI_API_SECRET vào .env (không cần Private Key/OTP).")


def public_ip() -> str:
    """Không gọi dịch vụ ngoài SSI: IP được phép xem/đăng ký trong SSI Developer Portal › Quản lý API Key."""
    return "xem trong SSI Developer Portal › Quản lý API Key"


def check_ssi() -> Dict:
    """Lấy token + gọi thử securitiesSummary FPT 7 ngày gần nhất (có khối ngoại)."""
    if not ssi_configured():
        return {"ok": False, "detail": "Chưa có SSI_API_KEY / SSI_API_SECRET trong .env", "hint": KEY_HINT}
    from src.ssi_api.ssi_client import SSIClient
    try:
        c = SSIClient()
        c.get_token(force=True)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detail": str(exc),
                "hint": "SSI từ chối bộ khóa: kiểm tra (1) dán bằng nút copy, không gõ tay (dễ nhầm 1/l/I, 0/O), "
                        "(2) khóa đang ở trạng thái Hoạt động trên Developer Portal, (3) khóa môi trường Production "
                        "(UAT và Production tách riêng)."}
    try:
        rows = c.securities_summary("FPT", today_vn() - timedelta(days=7), today_vn())
        fx = sum(1 for r in rows if r.get("totalForeignBuyValue") not in (None, ""))
        return {"ok": True, "detail": f"Token OK · securitiesSummary FPT: {len(rows)} phiên ({fx} có số liệu khối ngoại)",
                "hint": ""}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detail": f"Token OK nhưng gọi dữ liệu lỗi: {exc}",
                "hint": "Khóa có thể chưa được cấp nhóm quyền Market Data (data:*) – kiểm tra tab Nhóm quyền."}


def check_ssi_ws(seconds: float = 8) -> Dict:
    """Mở WebSocket V3, đăng ký indexsummary.VNINDEX và đếm tin nhận được trong vài giây."""
    if not ssi_configured():
        return {"ok": False, "detail": "Chưa có SSI_API_KEY / SSI_API_SECRET trong .env", "hint": KEY_HINT}
    try:
        from ssi_sdk import Auth, Config, Stream  # type: ignore
    except ImportError:
        return {"ok": False, "detail": "Chưa cài SDK ssi-sdk", "hint": "pip install -r requirements.txt"}
    got = []
    try:
        cfg = Config(api_key=env("SSI_API_KEY"), api_secret=env("SSI_API_SECRET"), api_url=ssi_base_url(),
                     streaming_url=ssi_stream_url(), log_level="WARNING")
        with Auth(cfg) as auth:
            auth.authenticate()
            with Stream(auth) as stream:
                s = stream.streaming
                s.on_data = lambda m: got.append(m) if not isinstance(m, dict) else None
                s.connect()
                s.subscribe_index_summary(["VNINDEX"])
                s.subscribe_index_trade(["VNINDEX"])
                t0 = time.time()
                while time.time() - t0 < seconds and len(got) < 3:
                    time.sleep(0.5)
                s.disconnect()
        return {"ok": True, "detail": f"Kết nối {ssi_stream_url()} OK, nhận {len(got)} tin VNINDEX trong {seconds:.0f} giây",
                "hint": "Ngoài giờ giao dịch máy chủ ít/không đẩy tin – bộ ghi sẽ có dữ liệu từ 9:00 phiên kế tiếp."}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detail": str(exc), "hint": "Kiểm tra mạng / tường lửa tới stream.ssi.com.vn:443."}


def run_all() -> Dict[str, Dict]:
    return {"SSI REST (FastConnect V3)": check_ssi(), "SSI WebSocket (V3)": check_ssi_ws()}


if __name__ == "__main__":
    from src.data import database as db

    db.init_schema()
    print("IP công khai của máy:", public_ip())
    for k, v in run_all().items():
        print(f"[{'OK ' if v['ok'] else 'LỖI'}] {k}: {v['detail']}")
        if v["hint"] and not v["ok"]:
            print("      →", v["hint"])
