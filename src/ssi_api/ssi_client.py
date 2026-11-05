"""
SSI FastConnect Data – REST phiên bản 2 (bước B1.1).

- Lấy access token bằng ConsumerID/ConsumerSecret (KHÔNG dùng Private Key – chỉ dùng cho ký lệnh giao dịch).
- Tự làm mới token khi hết hạn hoặc nhận 401.
- Giãn cách ≥ 1,2 giây giữa hai lần gọi; thử lại 3 lần với thời gian chờ 2–4–8 giây khi lỗi mạng
  hoặc thông báo "API calls quota exceeded".
- Mọi lần gọi ghi ingest_log (nguồn, endpoint, trạng thái, số lần thử, thời gian) – không ghi token.

Endpoint theo tài liệu FastConnect Data v2 (guide.ssi.com.vn); tên trường thực tế được đối chiếu ở bước B1.2
(lưu JSON mẫu trong docs/api_samples/ bằng `python -m src.ssi_api.ssi_client --samples`).
"""
from __future__ import annotations

import argparse
import json
import threading
import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterator, List, Optional

import requests

from src.common.config import abs_path, env, get
from src.common.logging import get_logger
from src.common.timeutil import fmt_ssi_date
from src.data import database as db
from src.ssi_api.base_provider import BaseProvider

log = get_logger(__name__)


class SSIError(RuntimeError):
    pass


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
        self.min_interval = float(get("ssi.min_interval_sec", 1.2))
        self.backoff = list(get("ssi.backoff_sec", [2, 4, 8]))
        self.retries = int(get("ssi.retries", 3))
        self.timeout = float(get("ssi.timeout_sec", 30))
        self._token: Optional[str] = None
        self._token_exp: float = 0.0
        self._last_call = 0.0
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
            raise SSIError("Thiếu SSI_CONSUMER_ID / SSI_CONSUMER_SECRET trong .env")
        self._throttle()
        r = self.http.post(self.base + self.ENDPOINTS["token"],
                           json={"consumerID": self.cid, "consumerSecret": self.secret}, timeout=self.timeout)
        body = r.json() if r.content else {}
        tok = (body.get("data") or {}).get("accessToken")
        if not tok:
            raise SSIError(f"Không lấy được access token: {body.get('message', r.status_code)}")
        self._token = tok
        self._token_exp = self._clock() + 7 * 3600          # token SSI ~8 giờ; làm mới sớm
        log.info("Đã lấy access token SSI")
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
                self._throttle()
                r = self.http.get(url, params=params, timeout=self.timeout,
                                  headers={"Authorization": f"Bearer {self.get_token()}"})
                if r.status_code == 401:
                    self.get_token(force=True)
                    raise SSIError("401 – token hết hạn, đã làm mới")
                body = r.json() if r.content else {}
                msg = str(body.get("message", ""))
                if "quota" in msg.lower() or r.status_code == 429:
                    raise SSIError(f"API calls quota exceeded ({r.status_code})")
                if r.status_code >= 500:
                    raise SSIError(f"HTTP {r.status_code}")
                status = str(body.get("status", ""))
                if status not in ("200", "Success", "success") and r.status_code != 200:
                    raise SSIError(f"{r.status_code} {msg}")
                n = len(body.get("data") or []) if isinstance(body.get("data"), list) else 1
                db.log_ingest("SSI", endpoint, "ok", n, attempt, (time.time() - t0) * 1000)
                self.consecutive_failures = 0
                return body
            except (requests.RequestException, SSIError, ValueError) as exc:
                last_exc = exc
                wait = self.backoff[min(attempt - 1, len(self.backoff) - 1)]
                log.warning("SSI %s lỗi lần %d: %s – chờ %ss", endpoint, attempt, exc, wait)
                if attempt <= self.retries:
                    self._sleep(wait)
        self.consecutive_failures += 1
        db.log_ingest("SSI", endpoint, "error", 0, self.retries + 1, (time.time() - t0) * 1000, str(last_exc))
        raise SSIError(f"{endpoint} thất bại sau {self.retries + 1} lần: {last_exc}")

    def _paged(self, endpoint: str, params: Dict[str, Any]) -> Iterator[Dict]:
        size = int(get("ssi.page_size", 1000))
        page = 1
        while True:
            body = self._request(endpoint, {**params, "pageIndex": page, "pageSize": size})
            data = body.get("data") or []
            yield from data
            total = int(body.get("totalRecord") or 0)
            if len(data) < size or page * size >= total:
                break
            page += 1

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
        return list(self._paged("intraday_ohlc", {"symbol": symbol, "fromDate": fmt_ssi_date(start),
                                                  "toDate": fmt_ssi_date(end), "ascending": "true",
                                                  "resollution": resolution}))   # chính tả theo tài liệu SSI

    def securities(self, market: str = "HOSE") -> List[Dict]:
        return list(self._paged("securities", {"market": market}))

    def securities_details(self, market: str = "HOSE", symbol: str = "") -> List[Dict]:
        """Trả danh sách đã làm phẳng: Symbol, SecType, Exchange, ListedShare…"""
        out = []
        for item in self._paged("securities_details", {"market": market, "symbol": symbol}):
            for rep in item.get("RepeatedInfo", [item]) if isinstance(item, dict) else []:
                out.append(rep)
        return out

    def index_components(self, index_code: str = "VN30") -> List[str]:
        syms = []
        for item in self._paged("index_components", {"indexCode": index_code}):
            for c in item.get("IndexComponent", []) or []:
                syms.append(c.get("StockSymbol") or c.get("Symbol"))
        return [s for s in syms if s]


def save_samples(client: Optional[SSIClient] = None, d: Optional[date] = None) -> Dict[str, str]:
    """B1.2 – gọi thử MỘT ngày cho từng hàm, lưu JSON gốc vào docs/api_samples/."""
    c = client or SSIClient()
    d = d or (date.today() - timedelta(days=1))
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    out_dir = abs_path("docs/api_samples")
    out_dir.mkdir(parents=True, exist_ok=True)
    calls = {
        "DailyStockPrice_HOSE": lambda: c.daily_stock_price(d)[:5],
        "DailyIndex_VNINDEX": lambda: c.daily_index("VNINDEX", d, d),
        "DailyOhlc_FPT": lambda: c.daily_ohlc("FPT", d, d),
        "IntradayOhlc_FPT": lambda: c.intraday_ohlc("FPT", d, d)[:10],
        "SecuritiesDetails_HOSE": lambda: c.securities_details("HOSE", "FPT"),
        "IndexComponents_VN30": lambda: c.index_components("VN30"),
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
    if a.samples:
        for k, v in save_samples().items():
            print(f"{k}: {v}")
    else:
        c = SSIClient()
        print("SSI khả dụng:", c.is_available)
        if c.is_available:
            print("Số mã HOSE:", len(c.securities("HOSE")))
