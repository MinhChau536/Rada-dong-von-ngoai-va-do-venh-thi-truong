"""
SSI FastConnect Data – REST phiên bản 2 (bước B1.1). NGUỒN DỮ LIỆU CHÍNH.

Đối chiếu đặc tả guide.ssi.com.vn/ssi-products/fastconnect-data/api-specs và SDK chính thức ssi-fc-data 2.2.2:
  • POST api/v2/Market/AccessToken  {consumerID, consumerSecret} → data.accessToken (JWT có trường exp).
  • GET  api/v2/Market/{Securities|SecuritiesDetails|IndexComponents|IndexList|DailyOhlc|IntradayOhlc|
         DailyIndex|DailyStockPrice}, header "Authorization: Bearer <token>", ngày dd/mm/yyyy.
  • pageIndex 1–10, pageSize ∈ {10, 20, 50, 100, 1000}. status trả 200 hoặc "Success". Giá trị số dạng chuỗi.
  • KHÔNG dùng Private Key (chỉ để ký lệnh giao dịch – đồ án không đặt lệnh).

Vận hành: giãn cách ≥ 1,2 giây giữa hai lần gọi; thử lại 3 lần, chờ 2–4–8 giây khi lỗi mạng/5xx/"quota exceeded";
tự làm mới token trước khi hết hạn hoặc khi nhận 401. Mọi lần gọi ghi ingest_log; không ghi token ra log.

    python -m src.ssi_api.ssi_client            # kiểm tra kết nối: lấy token + đếm số mã HOSE
    python -m src.ssi_api.ssi_client --samples  # B1.2: lưu JSON gốc mỗi hàm vào docs/api_samples/
"""
from __future__ import annotations

import argparse
import base64
import json
import threading
import time
from datetime import date, timedelta
from typing import Any, Dict, Iterator, List, Optional

import requests

from src.common.config import abs_path, env, get
from src.common.logging import get_logger
from src.common.timeutil import fmt_ssi_date, today_vn
from src.data import database as db
from src.ssi_api.base_provider import BaseProvider

log = get_logger(__name__)
OK_STATUS = {"200", "success"}


class SSIError(RuntimeError):
    pass


def _ci(d: Dict, *names, default=None):
    """Lấy giá trị theo tên trường không phân biệt hoa/thường (tài liệu SSI viết không thống nhất)."""
    low = {str(k).lower(): v for k, v in d.items()}
    for n in names:
        if n.lower() in low:
            return low[n.lower()]
    return default


def _jwt_exp(token: str) -> Optional[float]:
    try:
        part = token.split(".")[1]
        part += "=" * (-len(part) % 4)
        return float(json.loads(base64.urlsafe_b64decode(part))["exp"])
    except Exception:
        return None


class SSIClient(BaseProvider):
    ENDPOINTS = {
        "token": "api/v2/Market/AccessToken",
        "securities": "api/v2/Market/Securities",
        "securities_details": "api/v2/Market/SecuritiesDetails",
        "index_components": "api/v2/Market/IndexComponents",
        "index_list": "api/v2/Market/IndexList",
        "daily_ohlc": "api/v2/Market/DailyOhlc",
        "intraday_ohlc": "api/v2/Market/IntradayOhlc",
        "daily_index": "api/v2/Market/DailyIndex",
        "daily_stock_price": "api/v2/Market/DailyStockPrice",
    }

    def __init__(self, consumer_id: Optional[str] = None, consumer_secret: Optional[str] = None,
                 session: Optional[requests.Session] = None, sleep=time.sleep, clock=time.monotonic):
        self.base = get("ssi.base_url", "https://fc-data.ssi.com.vn/")
        self.cid = consumer_id or env("SSI_CONSUMER_ID")
        self.secret = consumer_secret or env("SSI_CONSUMER_SECRET")
        self.http = session or requests.Session()
        if hasattr(self.http, "headers"):
            self.http.headers.update({"Content-Type": "application/json", "Accept": "application/json"})
        self.min_interval = float(get("ssi.min_interval_sec", 1.2))
        self.backoff = list(get("ssi.backoff_sec", [2, 4, 8]))
        self.retries = int(get("ssi.retries", 3))
        self.timeout = float(get("ssi.timeout_sec", 30))
        self.page_size = int(get("ssi.page_size", 1000))
        self._token: Optional[str] = None
        self._token_exp: float = 0.0
        self._last_call = -1e9
        self._lock = threading.Lock()
        self._sleep, self._clock = sleep, clock
        self.consecutive_failures = 0

    @property
    def name(self) -> str:
        return "SSI"

    @property
    def is_available(self) -> bool:
        return bool(self.cid and self.secret and not str(self.cid).startswith("your_"))

    # ── xác thực ──────────────────────────────────────────────────────────────
    def get_token(self, force: bool = False) -> str:
        if self._token and not force and self._clock() < self._token_exp:
            return self._token
        if not self.is_available:
            raise SSIError("Thiếu SSI_CONSUMER_ID / SSI_CONSUMER_SECRET trong tệp .env")
        self._throttle()
        r = self.http.post(self.base + self.ENDPOINTS["token"],
                           json={"consumerID": self.cid, "consumerSecret": self.secret}, timeout=self.timeout)
        try:
            body = r.json()
        except ValueError:
            raise SSIError(f"AccessToken trả về không phải JSON (HTTP {r.status_code})")
        tok = (_ci(body, "data") or {}).get("accessToken") if isinstance(_ci(body, "data"), dict) else None
        if not tok:
            raise SSIError(f"Không lấy được access token: {_ci(body, 'message', default=r.status_code)} – "
                           "kiểm tra ConsumerID/ConsumerSecret và IP đã đăng ký trên iBoard")
        self._token = tok
        exp = _jwt_exp(tok)
        ttl = (exp - time.time()) if exp else 8 * 3600
        self._token_exp = self._clock() + max(60.0, ttl - 3600)       # làm mới trước hạn 1 giờ (như SDK chính thức)
        log.info("Đã lấy access token SSI (hết hạn sau ~%.1f giờ)", ttl / 3600)
        return tok

    # ── gọi API ───────────────────────────────────────────────────────────────
    def _throttle(self) -> None:
        with self._lock:
            wait = self.min_interval - (self._clock() - self._last_call)
            if wait > 0:
                self._sleep(wait)
            self._last_call = self._clock()

    def _request(self, endpoint: str, params: Dict[str, Any]) -> Dict:
        url = self.base + self.ENDPOINTS[endpoint]
        last_exc: Optional[Exception] = None
        t0 = time.time()
        for attempt in range(1, self.retries + 2):
            try:
                tok = self.get_token()
                self._throttle()
                r = self.http.get(url, params=params, timeout=self.timeout, headers={"Authorization": f"Bearer {tok}"})
                if r.status_code == 401:
                    self.get_token(force=True)
                    raise SSIError("401 – token hết hạn, đã làm mới")
                try:
                    body = r.json()
                except ValueError:
                    raise SSIError(f"HTTP {r.status_code} – phản hồi không phải JSON")
                msg = str(_ci(body, "message", default=""))
                status = str(_ci(body, "status", default="")).lower()
                if "quota" in msg.lower() or r.status_code == 429 or status == "429":
                    raise SSIError(f"API calls quota exceeded ({msg})")
                if r.status_code >= 500:
                    raise SSIError(f"HTTP {r.status_code}")
                if status not in OK_STATUS:
                    if r.status_code in (400, 403, 404):          # lỗi tham số/quyền – thử lại không giúp gì
                        db.log_ingest("SSI", endpoint, "error", 0, attempt, (time.time() - t0) * 1000, msg)
                        raise SSIError(f"{endpoint}: {msg or r.status_code}")
                    raise SSIError(f"{endpoint}: status={status} {msg}")
                data = _ci(body, "data")
                n = len(data) if isinstance(data, list) else (1 if data else 0)
                db.log_ingest("SSI", endpoint, "ok", n, attempt, (time.time() - t0) * 1000)
                self.consecutive_failures = 0
                return body
            except SSIError as exc:
                if str(exc).startswith(f"{endpoint}:") and "status=" not in str(exc):
                    self.consecutive_failures += 1
                    raise
                last_exc = exc
            except (requests.RequestException, ValueError) as exc:
                last_exc = exc
            wait = self.backoff[min(attempt - 1, len(self.backoff) - 1)]
            log.warning("SSI %s lỗi lần %d: %s", endpoint, attempt, last_exc)
            if attempt <= self.retries:
                self._sleep(wait)
        self.consecutive_failures += 1
        db.log_ingest("SSI", endpoint, "error", 0, self.retries + 1, (time.time() - t0) * 1000, str(last_exc))
        raise SSIError(f"{endpoint} thất bại sau {self.retries + 1} lần: {last_exc}")

    def _paged(self, endpoint: str, params: Dict[str, Any]) -> Iterator[Dict]:
        size = self.page_size
        for page in range(1, 11):                      # SSI giới hạn pageIndex 1–10
            body = self._request(endpoint, {**params, "pageIndex": page, "pageSize": size})
            data = _ci(body, "data") or []
            if isinstance(data, dict):
                data = [data]
            yield from data
            total = int(_ci(body, "totalRecord", default=0) or 0)
            if len(data) < size or page * size >= total:
                return
        log.warning("%s: đạt giới hạn 10 trang – thu hẹp khoảng ngày để không mất dữ liệu", endpoint)

    # ── hàm dữ liệu ───────────────────────────────────────────────────────────
    def daily_stock_price(self, d: date, market: str = "HOSE", symbol: str = "") -> List[Dict]:
        s = fmt_ssi_date(d)
        return list(self._paged("daily_stock_price", {"symbol": symbol, "fromDate": s, "toDate": s, "market": market}))

    def daily_index(self, index_id: str, start: date, end: date) -> List[Dict]:
        return list(self._paged("daily_index", {"indexId": index_id, "fromDate": fmt_ssi_date(start),
                                                "toDate": fmt_ssi_date(end)}))

    def daily_ohlc(self, symbol: str, start: date, end: date) -> List[Dict]:
        return list(self._paged("daily_ohlc", {"symbol": symbol, "fromDate": fmt_ssi_date(start),
                                               "toDate": fmt_ssi_date(end), "ascending": "true"}))

    def intraday_ohlc(self, symbol: str, start: date, end: date, resolution: int = 1) -> List[Dict]:
        # SDK chính thức dùng "resolution"; bảng đặc tả viết "resollution" → gửi cả hai cho chắc
        return list(self._paged("intraday_ohlc", {"symbol": symbol, "fromDate": fmt_ssi_date(start),
                                                  "toDate": fmt_ssi_date(end), "ascending": "true",
                                                  "resolution": resolution, "resollution": resolution}))

    def securities(self, market: str = "HOSE") -> List[Dict]:
        return list(self._paged("securities", {"market": market}))

    def securities_details(self, market: str = "HOSE", symbol: str = "") -> List[Dict]:
        """Danh sách đã làm phẳng: mỗi phần tử có Symbol, SecType, Exchange, ListedShare…"""
        out = []
        for item in self._paged("securities_details", {"market": market, "symbol": symbol}):
            rep = _ci(item, "RepeatedInfo", "repeatedinfoList")
            out.extend(rep if isinstance(rep, list) else [item])
        return out

    def index_components(self, index_code: str = "VN30") -> List[str]:
        syms = []
        for item in self._paged("index_components", {"indexCode": index_code}):
            for c in _ci(item, "IndexComponent", default=[]) or []:
                syms.append(_ci(c, "StockSymbol", "Symbol"))
        return [s for s in syms if s]

    def index_list(self, exchange: str = "HOSE") -> List[Dict]:
        return list(self._paged("index_list", {"exchange": exchange}))


def save_samples(client: Optional[SSIClient] = None, d: Optional[date] = None) -> Dict[str, str]:
    """B1.2 – gọi thử MỘT ngày cho từng hàm, lưu JSON gốc vào docs/api_samples/."""
    c = client or SSIClient()
    d = d or (today_vn() - timedelta(days=1))
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    out_dir = abs_path("docs/api_samples")
    out_dir.mkdir(parents=True, exist_ok=True)
    calls = {
        "DailyStockPrice_HOSE": lambda: c.daily_stock_price(d)[:5],
        "DailyIndex_VNINDEX": lambda: c.daily_index("VNINDEX", d, d),
        "DailyOhlc_VNINDEX": lambda: c.daily_ohlc("VNINDEX", d, d),
        "DailyOhlc_FPT": lambda: c.daily_ohlc("FPT", d, d),
        "IntradayOhlc_FPT": lambda: c.intraday_ohlc("FPT", d, d)[:10],
        "SecuritiesDetails_FPT": lambda: c.securities_details("HOSE", "FPT"),
        "IndexComponents_VN30": lambda: c.index_components("VN30"),
        "IndexList_HOSE": lambda: c.index_list("HOSE"),
        "IndexList_HNX": lambda: c.index_list("HNX"),
    }
    res = {}
    for name, fn in calls.items():
        try:
            data = fn()
            (out_dir / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            res[name] = f"ok ({len(data)} bản ghi)"
        except Exception as exc:  # noqa: BLE001
            res[name] = f"lỗi: {exc}"
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", action="store_true", help="Lưu JSON mẫu vào docs/api_samples (B1.2)")
    a = ap.parse_args()
    db.init_schema()
    if a.samples:
        for k, v in save_samples().items():
            print(f"{k}: {v}")
    else:
        c = SSIClient()
        if not c.is_available:
            raise SystemExit("Chưa có SSI_CONSUMER_ID / SSI_CONSUMER_SECRET trong .env")
        c.get_token()
        print("Kết nối SSI thành công. Số mã HOSE:", len(c.securities("HOSE")))
