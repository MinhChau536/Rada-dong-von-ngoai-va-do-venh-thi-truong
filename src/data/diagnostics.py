"""
Chẩn đoán kết nối nguồn dữ liệu (dùng chung cho trang "Kết nối dữ liệu", trang 7 và dòng lệnh).

    python -m src.data.diagnostics

Mỗi phép kiểm tra trả {ok, detail, hint}. Không bao giờ in khóa/token; chỉ in thông điệp lỗi của máy chủ.
"""
from __future__ import annotations

import time
from typing import Dict

import requests

from src.common.config import neo_configured, ssi_configured
from src.common.logging import get_logger

log = get_logger(__name__)


def public_ip() -> str:
    for url in ("https://api.ipify.org", "https://ifconfig.me/ip"):
        try:
            return requests.get(url, timeout=6).text.strip()
        except requests.RequestException:
            continue
    return "không xác định"


def check_ssi() -> Dict:
    if not ssi_configured():
        return {"ok": False, "detail": "Chưa có SSI_CONSUMER_ID / SSI_CONSUMER_SECRET trong .env",
                "hint": "Lấy tại iBoard › Dịch vụ API (chỉ cần API Key + API Secret, không cần Private Key)."}
    from src.ssi_api.ssi_client import SSIClient
    try:
        c = SSIClient()
        c.get_token(force=True)
        return {"ok": True, "detail": "Lấy access token thành công", "hint": ""}
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        hint = ("SSI từ chối kết nối: kiểm tra (1) IP máy này đã được đăng ký trên iBoard › Dịch vụ API, "
                "(2) ConsumerID/ConsumerSecret chép đúng từng ký tự (dễ nhầm 1/l/I, 0/O), "
                "(3) khóa thuộc dịch vụ FastConnect DATA và đang ở trạng thái Hoạt động.")
        return {"ok": False, "detail": msg, "hint": hint}


def check_neo_rest() -> Dict:
    if not neo_configured():
        return {"ok": False, "detail": "Chưa có NEO_USERNAME / NEO_PASSWORD trong .env", "hint": ""}
    from src.neo_api.neo_client import NEOClient
    c = NEOClient()
    try:
        c.auth(force=True)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detail": f"Đăng nhập thất bại: {exc}", "hint": "Kiểm tra tài khoản NEO trong .env."}
    try:
        rows = c.market_index_detail("VNINDEX")
        return {"ok": True, "detail": f"Đăng nhập + marketIndexDetail OK ({len(rows)} bản ghi)", "hint": ""}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detail": f"Đăng nhập OK nhưng REST bị chặn: {exc}",
                "hint": "NEO kiểm soát IP: đăng ký IP máy này tại cổng NEO API của VPBankS."}


def check_neo_ws(seconds: float = 8) -> Dict:
    from src.neo_api.neo_client import NEOClient
    import websocket

    c = NEOClient()
    t0 = time.time()
    try:
        ws = websocket.create_connection(c.ws_url, timeout=15)
        try:
            c._sync(ws)
            n_schema = len(c._schemas)
            ws.settimeout(seconds)
            import json
            ws.send(json.dumps({"type": "sub", "channel": "marketSession", "listId": ["HOSE"]}))
            got = 0
            try:
                while time.time() - t0 < seconds and got < 3:
                    if c.decode(ws.recv()) is not None:
                        got += 1
            except Exception:  # noqa: BLE001 – hết giờ chờ là bình thường ngoài phiên
                pass
        finally:
            ws.close()
        return {"ok": True, "detail": f"Kết nối + đồng bộ {n_schema} lược đồ Avro OK, nhận {got} tin marketSession",
                "hint": "Ngoài giờ giao dịch máy chủ không đẩy giá – bộ ghi sẽ có dữ liệu từ 9:00 phiên kế tiếp."}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detail": str(exc), "hint": "Kiểm tra mạng / tường lửa tới neoapi.vpbanks.com.vn:443."}


def run_all() -> Dict[str, Dict]:
    return {"SSI REST": check_ssi(), "NEO REST": check_neo_rest(), "NEO WebSocket": check_neo_ws()}


if __name__ == "__main__":
    from src.data import database as db

    db.init_schema()
    print("IP công khai của máy:", public_ip())
    for k, v in run_all().items():
        print(f"[{'OK ' if v['ok'] else 'LỖI'}] {k}: {v['detail']}")
        if v["hint"] and not v["ok"]:
            print("      →", v["hint"])
