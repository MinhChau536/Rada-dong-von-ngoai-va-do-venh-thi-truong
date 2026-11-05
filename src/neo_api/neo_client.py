"""
VPBankS NEO API – nguồn phụ (bước B1.4).

REST: POST /auth/token → JWT; GET /stock/stockDetail (phân trang pageSize 1000, đọc đến trang cuối).
WebSocket: ws://neoapi.vpbanks.com.vn/stock-stream/broker – gửi {action:'auth', data: JWT}, rồi đăng ký kênh
marketInfo, marketSession, stockInfo. Giới hạn 5 yêu cầu/giây; ưu tiên WebSocket thay vì gọi REST lặp lại.

Đường dẫn & định dạng tin đăng ký lấy từ settings.yaml và PHẢI đối chiếu NeoAPI Docs (neoinvest.vpbanks.com.vn/
neo-openapi) khi có quyền – các giá trị mặc định ở đây theo mô tả trong thuyết minh mục 6.2.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Dict, Iterator, List, Optional

import requests

from src.common.config import env, field_map, get
from src.common.logging import get_logger
from src.data import database as db
from src.ssi_api.base_provider import BaseProvider

log = get_logger(__name__)


class NEOClient(BaseProvider):
    def __init__(self, username: Optional[str] = None, password: Optional[str] = None,
                 session: Optional[requests.Session] = None, sleep=time.sleep):
        self.base = get("neo.base_url").rstrip("/")
        self.ws_url = get("neo.ws_url")
        self.user = username or env("NEO_USERNAME")
        self.pwd = password or env("NEO_PASSWORD")
        self.http = session or requests.Session()
        self.min_interval = 1.0 / float(get("neo.max_rps", 5))
        self._last = 0.0
        self._lock = threading.Lock()
        self._sleep = sleep
        self.jwt: Optional[str] = None
        self.jwt_time = 0.0

    @property
    def name(self) -> str:
        return "NEO"

    @property
    def is_available(self) -> bool:
        return bool(self.user and self.pwd and not str(self.user).startswith("your_"))

    def _throttle(self):
        with self._lock:
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                self._sleep(wait)
            self._last = time.monotonic()

    def auth(self, force: bool = False) -> str:
        if self.jwt and not force and time.monotonic() - self.jwt_time < 3000:
            return self.jwt
        self._throttle()
        r = self.http.post(f"{self.base}/auth/token", json={"username": self.user, "password": self.pwd}, timeout=20)
        body = r.json() if r.content else {}
        tok = body.get("token") or (body.get("data") or {}).get("token") or body.get("accessToken")
        if not tok:
            raise RuntimeError(f"NEO auth thất bại: HTTP {r.status_code}")
        self.jwt, self.jwt_time = tok, time.monotonic()
        return tok

    def stock_detail(self, exchange: str = "HOSE") -> List[Dict]:
        size, page, out = int(get("neo.page_size", 1000)), 1, []
        t0 = time.time()
        while True:
            self._throttle()
            r = self.http.get(f"{self.base}/stock/stockDetail", params={"exchange": exchange, "pageNo": page, "pageSize": size},
                              headers={"Authorization": f"Bearer {self.auth()}"}, timeout=20)
            if r.status_code == 401:
                self.auth(force=True)
                continue
            body = r.json() if r.content else {}
            data = body.get("data") or body.get("content") or []
            if isinstance(data, dict):
                data = data.get("content") or data.get("items") or []
            out.extend(data)
            if len(data) < size:
                break
            page += 1
        db.log_ingest("NEO", "stockDetail", "ok", len(out), 1, (time.time() - t0) * 1000)
        return out

    @staticmethod
    def to_common(records: List[Dict], table: str = "daily_stock") -> List[Dict]:
        """Ánh xạ tên trường NEO → lược đồ chung theo data_dictionary.yaml."""
        fmap = field_map(table, "neo")
        return [{fmap.get(k, k): v for k, v in r.items()} for r in records]

    # ── WebSocket ─────────────────────────────────────────────────────────────
    def ws_messages(self, subscriptions: List[Dict]) -> Iterator[Dict]:
        """Kết nối, xác thực, đăng ký kênh; sinh từng tin (dict). Ném lỗi khi mất kết nối để bộ ghi tự nối lại."""
        import websocket  # websocket-client

        ws = websocket.create_connection(self.ws_url, timeout=30)
        try:
            ws.send(json.dumps({"action": "auth", "data": self.auth()}))
            for sub in subscriptions:
                ws.send(json.dumps(sub))
            while True:
                raw = ws.recv()
                if not raw:
                    continue
                try:
                    yield json.loads(raw)
                except ValueError:
                    yield {"raw": raw}
        finally:
            ws.close()


def default_subscriptions(watch: List[str], vn30: List[str]) -> List[Dict]:
    """Định dạng tin đăng ký (cần đối chiếu NeoAPI Docs)."""
    return [{"action": "subscribe", "channel": "marketInfo", "data": ["VNINDEX", "VN30"]},
            {"action": "subscribe", "channel": "marketSession", "data": ["HOSE"]},
            {"action": "subscribe", "channel": "stockInfo", "data": sorted(set(vn30 + watch))}]
