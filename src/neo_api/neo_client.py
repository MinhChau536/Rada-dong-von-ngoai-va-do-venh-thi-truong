"""
VPBankS NEO API (bước B1.4) – REST + WebSocket stock-stream.

Đối chiếu bộ SDK Python của VPBankS (NeoInvestSDK 0.2.5, cấu hình môi trường thật) và kiểm thử kết nối ngày 06/11/2026:

REST
  • Xác thực:  POST {auth_base_url}/auth/token  {"username","password"}  → data.access_token (hạn 28 800 giây),
                data.refresh_token.  auth_base_url = https://external.vpbanks.com.vn
  • Dữ liệu:   GET  {base_url}/stock/stockDetail?symbols&marketCode&pageNo&pageSize
               GET  {base_url}/market/marketIndexDetail?indexCode&marketCode
               GET  {base_url}/market/marketStatus?marketCode ;  /stock/stockList ; /market/indexList …
               base_url = https://neoapi.vpbanks.com.vn/neo-api ; header Authorization: Bearer <JWT>.
  • Hệ thống kiểm soát IP: nếu IP chưa đăng ký, REST trả 401 "Invalid role or IP address" (NEOINP000401).

WebSocket  wss://neoapi.vpbanks.com.vn/stock-stream/broker  (không cần JWT)
  1. Gửi {"type":"sync","data":"<sha1 lược đồ đã lưu hoặc rỗng>"}.
  2. Máy chủ trả bytes: byte đầu = 101 (SCHEMA_ID_SYNC). Nếu phần còn lại = b"\\x00" → lược đồ đã khớp;
     nếu không → base64(zlib(JSON {schema_id: avro_schema})). Lưu lược đồ, gửi lại sync với sha1 mới,
     máy chủ xác nhận b"\\x65\\x00".
  3. Đăng ký: {"type":"sub","channel":"stockInfo|marketInfo|marketSession|marketData","listId":[...]}.
  4. Mỗi tin là bytes: byte đầu = schema_id, phần còn lại mã hóa Avro nhị phân.
     schema 2 = marketInfo, 3 = stockInfo, 1 = marketData, 26 = marketSession, 10 = marketVolume.
Giới hạn 5 yêu cầu/giây cho REST; dữ liệu thời gian thực đi qua WebSocket (đúng mục 4 của đề).
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import threading
import time
import zlib
from typing import Dict, Iterator, List, Optional

import requests

from src.common.config import abs_path, env, field_map, get
from src.common.logging import get_logger
from src.data import database as db
from src.ssi_api.base_provider import BaseProvider

log = get_logger(__name__)

SCHEMA_ID_SYNC = 101
SYNC_SUCCESS = b"\x00"
SCHEMA_CHANNEL = {1: "marketData", 2: "marketInfo", 3: "stockInfo", 10: "marketVolume", 23: "fuTopNPrice",
                  26: "marketSession"}
HEADERS = {"User-Agent": "NeoAPI-PythonSDK", "x-device": "NeoAPI-PythonSDK", "x-devicetype": "edge"}


class NEOError(RuntimeError):
    pass


class NEOClient(BaseProvider):
    def __init__(self, username: Optional[str] = None, password: Optional[str] = None,
                 session: Optional[requests.Session] = None, sleep=time.sleep):
        self.base = get("neo.base_url", "https://neoapi.vpbanks.com.vn/neo-api").rstrip("/")
        self.auth_base = get("neo.auth_base_url", "https://external.vpbanks.com.vn").rstrip("/")
        self.ws_url = get("neo.ws_url", "wss://neoapi.vpbanks.com.vn/stock-stream/broker")
        self.user = username or env("NEO_USERNAME")
        self.pwd = password or env("NEO_PASSWORD")
        self.http = session or requests.Session()
        if hasattr(self.http, "headers"):
            self.http.headers.update(HEADERS)
        self.min_interval = 1.0 / float(get("neo.max_rps", 5))
        self.timeout = float(get("neo.timeout_sec", 20))
        self._last = 0.0
        self._lock = threading.Lock()
        self._sleep = sleep
        self.jwt: Optional[str] = None
        self.jwt_exp = 0.0
        self._schemas: Dict[int, object] = {}
        self._schema_file = abs_path(get("neo.schema_cache", "data/neo_schemas.bin"))

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

    # ── REST ──────────────────────────────────────────────────────────────────
    def auth(self, force: bool = False) -> str:
        if self.jwt and not force and time.monotonic() < self.jwt_exp:
            return self.jwt
        if not self.is_available:
            raise NEOError("Thiếu NEO_USERNAME / NEO_PASSWORD trong .env")
        self._throttle()
        r = self.http.post(f"{self.auth_base}/auth/token", json={"username": self.user, "password": self.pwd},
                           timeout=self.timeout)
        try:
            body = r.json()
        except ValueError:
            raise NEOError(f"NEO auth: phản hồi không phải JSON (HTTP {r.status_code})")
        data = body.get("data") or {}
        tok = data.get("access_token") if isinstance(data, dict) else None
        if r.status_code != 200 or not tok:
            raise NEOError(f"NEO auth thất bại: HTTP {r.status_code} – {body.get('message', '')}")
        ttl = float(data.get("expires_in") or 28800)
        self.jwt, self.jwt_exp = tok, time.monotonic() + max(60.0, ttl - 600)
        log.info("Đã lấy JWT NEO (hạn ~%.1f giờ)", ttl / 3600)
        return tok

    def _get(self, path: str, params: Dict) -> Dict:
        t0 = time.time()
        for attempt in (1, 2):
            self._throttle()
            r = self.http.get(f"{self.base}{path}", params={k: v for k, v in params.items() if v is not None},
                              headers={"Authorization": f"Bearer {self.auth(force=attempt == 2)}"}, timeout=self.timeout)
            try:
                body = r.json()
            except ValueError:
                body = {}
            if r.status_code == 401 and "IP" in str(body.get("errors", "")):
                msg = f"401 {body.get('errors')} – đăng ký IP máy chạy bộ ghi trên cổng NEO API"
                db.log_ingest("NEO", path, "error", 0, attempt, (time.time() - t0) * 1000, msg)
                raise NEOError(msg)
            if r.status_code == 401 and attempt == 1:
                continue                                   # token hết hạn → làm mới và thử lại
            if r.status_code >= 400:
                msg = f"HTTP {r.status_code} – {body.get('message', '')} {body.get('errors', '')}".strip()
                db.log_ingest("NEO", path, "error", 0, attempt, (time.time() - t0) * 1000, msg)
                raise NEOError(f"{path}: {msg}")
            data = body.get("data")
            n = len(data) if isinstance(data, list) else len((data or {}).get("content") or []) if isinstance(data, dict) else 0
            db.log_ingest("NEO", path, "ok", n, attempt, (time.time() - t0) * 1000)
            return body
        raise NEOError(f"{path}: 401 sau khi làm mới token")

    @staticmethod
    def _rows(body: Dict) -> List[Dict]:
        data = body.get("data") or []
        if isinstance(data, dict):
            data = data.get("content") or data.get("items") or data.get("data") or [data]
        return list(data)

    def stock_detail(self, market_code: str = "HOSE", symbols: Optional[str] = None) -> List[Dict]:
        size, out = int(get("neo.page_size", 1000)), []
        for page in range(1, 50):
            rows = self._rows(self._get("/stock/stockDetail", {"symbols": symbols, "marketCode": market_code,
                                                                "pageNo": page, "pageSize": size}))
            out.extend(rows)
            if len(rows) < size:
                break
        return out

    def market_index_detail(self, index_code: str = "ALL", market_code: str = "") -> List[Dict]:
        return self._rows(self._get("/market/marketIndexDetail", {"indexCode": index_code, "marketCode": market_code}))

    def market_status(self, market_code: str = "ALL") -> List[Dict]:
        return self._rows(self._get("/market/marketStatus", {"marketCode": market_code}))

    @staticmethod
    def to_common(records: List[Dict], table: str = "daily_stock") -> List[Dict]:
        """Ánh xạ tên trường NEO → lược đồ chung theo data_dictionary.yaml."""
        fmap = field_map(table, "neo")
        return [{fmap.get(str(k).lower(), k): v for k, v in r.items()} for r in records]

    # ── WebSocket (Avro) ──────────────────────────────────────────────────────
    def _load_schemas(self, blob: bytes) -> None:
        import avro.schema  # thư viện avro (Apache)

        parsed = json.loads(zlib.decompress(base64.b64decode(blob)).decode("utf-8"))
        self._schemas = {int(k): avro.schema.parse(json.dumps(v)) for k, v in parsed.items()}

    def _sync(self, ws) -> None:
        cached = self._schema_file.read_bytes() if self._schema_file.exists() else b""
        ws.send(json.dumps({"type": "sync", "data": hashlib.sha1(cached).hexdigest() if cached else ""}))
        msg = ws.recv()
        if not isinstance(msg, bytes) or not msg or msg[0] != SCHEMA_ID_SYNC:
            raise NEOError(f"NEO WS: không nhận được phản hồi đồng bộ lược đồ ({msg!r:.80})")
        body = msg[1:]
        if body == SYNC_SUCCESS and cached:
            self._load_schemas(cached)
            return
        self._load_schemas(body)
        self._schema_file.parent.mkdir(parents=True, exist_ok=True)
        self._schema_file.write_bytes(body)
        ws.send(json.dumps({"type": "sync", "data": hashlib.sha1(body).hexdigest()}))
        ok = ws.recv()
        if ok != bytes([SCHEMA_ID_SYNC]) + SYNC_SUCCESS:
            raise NEOError("NEO WS: máy chủ không xác nhận lược đồ")
        log.info("Đồng bộ %d lược đồ Avro NEO", len(self._schemas))

    def decode(self, msg: bytes) -> Optional[Dict]:
        import avro.io

        if not isinstance(msg, bytes) or not msg or msg[0] not in self._schemas:
            return None
        rec = avro.io.DatumReader(self._schemas[msg[0]]).read(avro.io.BinaryDecoder(io.BytesIO(msg[1:])))
        if isinstance(rec, dict):
            rec = dict(rec)
            rec["_channel"] = SCHEMA_CHANNEL.get(msg[0], f"schema_{msg[0]}")
        return rec

    def ws_messages(self, subscriptions: List[Dict], recv_timeout: float = 120) -> Iterator[Dict]:
        """Kết nối, đồng bộ lược đồ, đăng ký kênh; sinh từng tin đã giải mã. Ném lỗi khi mất kết nối để bộ ghi nối lại."""
        import websocket  # websocket-client

        ws = websocket.create_connection(self.ws_url, timeout=30, header=[f"{k}: {v}" for k, v in HEADERS.items()])
        try:
            self._sync(ws)
            ws.settimeout(recv_timeout)
            for sub in subscriptions:
                ws.send(json.dumps(sub))
            while True:
                rec = self.decode(ws.recv())
                if rec is not None:
                    yield rec
        finally:
            try:
                ws.close()
            except Exception:  # noqa: BLE001
                pass


def default_subscriptions(symbols: List[str], indexes: Optional[List[str]] = None) -> List[Dict]:
    """Tin đăng ký theo định dạng SDK VPBankS: {type:'sub', channel, listId}."""
    idx = indexes or ["VNINDEX", "VN30", "HNXINDEX", "UPCOMINDEX"]
    subs = [{"type": "sub", "channel": "marketInfo", "listId": idx},
            {"type": "sub", "channel": "marketSession", "listId": ["HOSE", "HNX", "UPCOM"]}]
    syms = sorted(set(s for s in symbols if s))
    for i in range(0, len(syms), 100):                 # chia lô 100 mã/tin đăng ký
        subs.append({"type": "sub", "channel": "stockInfo", "listId": syms[i:i + 100]})
    return subs
