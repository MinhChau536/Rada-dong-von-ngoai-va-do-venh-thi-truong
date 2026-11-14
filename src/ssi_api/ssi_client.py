"""
SSI FastConnect V3 – REST (bước B1.1). NGUỒN DỮ LIỆU DUY NHẤT.

Đối chiếu Developer Portal developers.ssi.com.vn và SDK chính thức `ssi-sdk` 3.3.x (ssi_sdk/constant.py):
  • POST {base}/api/v3/auth/token  {apiKey, apiSecret}  → accessToken (JWT), expiresAt (epoch giây).
    Dữ liệu thị trường KHÔNG cần OTP, KHÔNG cần Private Key (chỉ dùng để ký lệnh – đồ án không đặt lệnh).
  • GET  {base}/api/v3/data/…  header "Authorization: Bearer <token>":
        securitiesSummary  symbol|index, from, to (yyyy/mm/dd), pageIndex, pageSize → giá, KL/GT khớp, thỏa thuận,
                           KHỐI NGOẠI mua/bán (KL + GT), room còn lại / tổng room
        masterdata         from, to → giá tham chiếu / trần / sàn của mọi mã theo ngày
        indexSummary       index, tradingDate → điểm, % thay đổi, số mã tăng/giảm/đứng/trần/sàn, KL/GT
        ohlc               symbol, timeFrame (1m 3m 5m 15m 1h 1d), from, to (yyyy/mm/dd HH:MM:SS)
        securitiesByBoard  board|index|symbol → danh mục (listedShare, stockType, icbName…)
        indexList          board → danh sách chỉ số
  • Kết quả rỗng: HTTP 200 kèm {"code": 204, "msg": "No Content"}. Lỗi: {"code", "msg"}. Giá trị số dạng chuỗi.
  • Máy chủ giới hạn 20 yêu cầu/giây (X-RateLimit-Limit); 429 kèm Retry-After.

Vận hành: giãn cách ≥ 0,06 giây giữa hai lần gọi (an toàn với nhiều luồng); thử lại 3 lần, chờ 2–4–8 giây khi lỗi
mạng/5xx/429; tự lấy lại token trước khi hết hạn hoặc khi nhận 401. Mọi lần gọi ghi ingest_log; không ghi khóa/token ra log.

    python -m src.ssi_api.ssi_client            # kiểm tra kết nối: lấy token + đếm số mã HOSE
    python -m src.ssi_api.ssi_client --samples  # B1.2: lưu JSON gốc mỗi hàm vào docs/api_samples/
"""
from __future__ import annotations

import argparse
import json
import threading
import time
from datetime import date, timedelta
from typing import Any, Dict, Iterator, List, Optional

import requests

from src.common.config import abs_path, env, get, ssi_base_url
from src.common.logging import get_logger
from src.common.timeutil import fmt_v3_date, today_vn
from src.data import database as db
from src.ssi_api.base_provider import BaseProvider

log = get_logger(__name__)
OK_CODES = {200, 204}
K_MIN, K_MAX = 0.005, 5.0      # khoảng hợp lệ của hệ số điều chỉnh quyền tích lũy (giá điều chỉnh / giá gốc)


class SSIError(RuntimeError):
    pass


class SSIAuthError(SSIError):
    """Khóa sai / bị thu hồi / thiếu quyền – thử lại không giúp gì."""


def _f(v: Any) -> Optional[float]:
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _code(body: Any) -> Optional[int]:
    if isinstance(body, dict) and body.get("code") is not None:
        try:
            return int(body["code"])
        except (TypeError, ValueError):
            return None
    return None


def _msg(body: Any) -> str:
    if isinstance(body, dict):
        return str(body.get("msg") or body.get("message") or "")
    return ""


def rows_of(body: Any) -> List[Dict]:
    """Danh sách bản ghi của một phản hồi: mảng trần, hoặc {"data": [...]}; {"code": 204} → []."""
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        if _code(body) == 204:
            return []
        data = body.get("data")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
    return []


# ── Chuẩn hóa bản ghi (thuần, kiểm thử được) ────────────────────────────────────
def enrich_stock(row: Dict, master: Optional[Dict] = None) -> Dict:
    """
    Bổ sung refPrice / ceiling / floor vào bản ghi securitiesSummary (endpoint này không trả 3 trường đó).

    Giá lịch sử của securitiesSummary là giá ĐÃ ĐIỀU CHỈNH quyền (cổ tức, thưởng), còn masterdata và priceChange là
    giá gốc của ngày đó. Hệ số điều chỉnh k = close / (refPrice_gốc + priceChange) đưa tham chiếu/trần/sàn về cùng
    thang với close, nhờ đó r = close / ref − 1 đúng bằng % thay đổi chính thức của sở. Phiên chưa điều chỉnh: k = 1.
    """
    r = dict(row)
    close, chg, pct = _f(row.get("close")), _f(row.get("priceChange")), _f(row.get("priceChangePercentage"))
    ref_raw = _f((master or {}).get("refPrice"))
    if master and master.get("board"):
        r["board"] = str(master["board"]).upper()           # sàn niêm yết CỦA NGÀY ĐÓ (mã chuyển sàn UPCOM/HNX → HOSE)
    adj = 1.0
    k = None
    if ref_raw and close and close > 0:
        if chg is not None and ref_raw + chg > 0:
            k = close / (ref_raw + chg)
        elif pct is not None and pct > -100:
            # Phiên cũ (trước ~2024) SSI V3 trả priceChange = null, chỉ có priceChangePercentage (làm tròn 2 số lẻ):
            # giá đóng cửa gốc = ref_gốc × (1 + pct) → k = close_điều_chỉnh / close_gốc.
            k = close / (ref_raw * (1 + pct / 100))
            if abs(k - 1) < 2e-4:                           # sai số làm tròn của pct, phiên không điều chỉnh
                k = 1.0
    if k is not None:
        # Mã chia nhiều cổ tức cổ phiếu/thưởng có hệ số tích lũy rất nhỏ (HPG 2017: k ≈ 0,16) – không chặn ở 0,2.
        adj = k if K_MIN < k < K_MAX else 1.0
    ref = None
    if ref_raw:
        ref = ref_raw * adj
        for key in ("ceiling", "floor"):
            v = _f((master or {}).get(key))
            r[key] = None if v is None else round(v * adj, 3)
    elif close and pct is not None and pct > -100:
        ref = close / (1 + pct / 100)
    r["refPrice"] = None if ref is None else round(ref, 3)
    r["adjFactor"] = round(adj, 8)
    return r


def reenrich_stock(stored: Dict) -> Dict:
    """Tính lại phần quy đổi thang giá cho payload ĐÃ LƯU trong raw_daily_stock (không cần gọi lại API).

    Payload lưu = securitiesSummary + refPrice/ceiling/floor đã nhân adjFactor → khôi phục giá gốc masterdata
    bằng cách chia lại cho adjFactor rồi chạy enrich_stock với logic hiện hành (sửa được các phiên tải bằng bản cũ).
    """
    adj = _f(stored.get("adjFactor"))
    if not adj or adj <= 0 or _f(stored.get("refPrice")) is None:
        return dict(stored)
    master = {"refPrice": _f(stored.get("refPrice")) / adj}
    for key in ("ceiling", "floor"):
        v = _f(stored.get(key))
        master[key] = None if v is None else v / adj
    if stored.get("board"):
        master["board"] = stored["board"]
    row = {k: v for k, v in stored.items() if k not in ("refPrice", "ceiling", "floor", "adjFactor")}
    return enrich_stock(row, master)


def enrich_index(row: Dict, ohlc: Optional[Dict] = None) -> Dict:
    """Ghép open/high/low (nến 1d) vào indexSummary; sửa indexChange khi lệch với indexChangePercentage
    (một số phiên cũ máy chủ trả indexChange nhân 100, ví dụ −8799 thay vì −87,99)."""
    r = dict(row)
    val, pct, chg = _f(row.get("indexValue")), _f(row.get("indexChangePercentage")), _f(row.get("indexChange"))
    if val and pct is not None and pct > -100:
        expect = val - val / (1 + pct / 100)
        if chg is None or abs(chg - expect) > max(0.05, abs(expect) * 0.02):
            r["indexChange"] = f"{expect:.2f}"
    for k in ("open", "high", "low", "close"):
        if ohlc and ohlc.get(k) is not None:
            r[k] = ohlc[k]
    return r


class SSIClient(BaseProvider):
    ENDPOINTS = {
        "token": "/api/v3/auth/token",
        "ohlc": "/api/v3/data/ohlc",
        "masterdata": "/api/v3/data/masterdata",
        "index_list": "/api/v3/data/indexList",
        "index_summary": "/api/v3/data/indexSummary",
        "securities_by_board": "/api/v3/data/securitiesByBoard",
        "securities_summary": "/api/v3/data/securitiesSummary",
    }

    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None,
                 session: Optional[requests.Session] = None, sleep=time.sleep, clock=time.monotonic):
        self.base = ssi_base_url()
        self.key = api_key or env("SSI_API_KEY")
        self.secret = api_secret or env("SSI_API_SECRET")
        self.http = session or requests.Session()
        if hasattr(self.http, "headers"):
            self.http.headers.update({"Content-Type": "application/json", "Accept": "application/json",
                                      "User-Agent": "FTSE-Flow-Radar/3.2 (python-requests)"})
        self.min_interval = float(get("ssi.min_interval_sec", 0.06))
        self.backoff = list(get("ssi.backoff_sec", [2, 4, 8]))
        self.retries = int(get("ssi.retries", 3))
        self.timeout = float(get("ssi.timeout_sec", 60))
        self.page_size = int(get("ssi.page_size", 1000))
        self._token: Optional[str] = None
        self._token_exp: float = 0.0
        self._last_call = -1e9
        self._lock = threading.Lock()
        self._auth_lock = threading.Lock()
        self._sleep, self._clock = sleep, clock
        self.consecutive_failures = 0

    @property
    def name(self) -> str:
        return "SSI"

    @property
    def is_available(self) -> bool:
        return bool(self.key and self.secret and not str(self.key).startswith("your_"))

    # ── xác thực ──────────────────────────────────────────────────────────────
    def get_token(self, force: bool = False) -> str:
        with self._auth_lock:
            if self._token and not force and self._clock() < self._token_exp:
                return self._token
            if not self.is_available:
                raise SSIAuthError("Thiếu SSI_API_KEY / SSI_API_SECRET trong tệp .env")
            self._throttle()
            try:
                r = self.http.post(self.base + self.ENDPOINTS["token"],
                                   json={"apiKey": self.key, "apiSecret": self.secret}, timeout=self.timeout)
            except requests.RequestException as exc:
                raise SSIError(f"Không kết nối được {self.base}: {exc}") from exc
            try:
                body = r.json()
            except ValueError:
                raise SSIError(f"auth/token trả về không phải JSON (HTTP {r.status_code})")
            payload = body.get("data") if isinstance(body, dict) and isinstance(body.get("data"), dict) else body
            tok = payload.get("accessToken") if isinstance(payload, dict) else None
            if r.status_code >= 400 or not tok:
                raise SSIAuthError(f"Không lấy được access token (HTTP {r.status_code} {_code(body) or ''} "
                                   f"{_msg(body)}) – kiểm tra SSI_API_KEY / SSI_API_SECRET và quyền Market Data "
                                   "của khóa trên Developer Portal")
            exp = _f(payload.get("expiresAt")) or 0
            if exp > 1e12:                                  # mili-giây → giây
                exp /= 1000
            ttl = (exp - time.time()) if exp else 900
            self._token = tok
            self._token_exp = self._clock() + max(30.0, ttl - 60)     # làm mới sớm 60 giây
            log.info("Đã lấy access token SSI V3 (hết hạn sau ~%.0f phút)", ttl / 60)
            return tok

    # ── gọi API ───────────────────────────────────────────────────────────────
    def _throttle(self) -> None:
        with self._lock:
            wait = self.min_interval - (self._clock() - self._last_call)
            if wait > 0:
                self._sleep(wait)
            self._last_call = self._clock()

    def _request(self, endpoint: str, params: Dict[str, Any]) -> Any:
        url = self.base + self.ENDPOINTS[endpoint]
        last_exc: Optional[Exception] = None
        t0 = time.time()
        for attempt in range(1, self.retries + 2):
            wait = None
            try:
                tok = self.get_token()
                self._throttle()
                r = self.http.get(url, params=params, timeout=self.timeout, headers={"Authorization": f"Bearer {tok}"})
                try:
                    body = r.json()
                except ValueError:
                    body = None
                code = _code(body)
                if r.status_code == 401 or code == 401:
                    self.get_token(force=True)
                    raise SSIError("401 – token hết hạn hoặc bị thay thế, đã lấy token mới")
                if r.status_code == 429 or code == 429:
                    ra = _f(getattr(r, "headers", {}).get("Retry-After"))
                    wait = ra if ra and ra <= 30 else None
                    raise SSIError(f"429 – vượt giới hạn tần suất ({_msg(body)})")
                if r.status_code >= 500:
                    raise SSIError(f"HTTP {r.status_code} {_msg(body)}")
                if body is None:
                    raise SSIError(f"HTTP {r.status_code} – phản hồi không phải JSON")
                if r.status_code == 403 or code == 403:
                    db.log_ingest("SSI", endpoint, "error", 0, attempt, (time.time() - t0) * 1000, _msg(body))
                    self.consecutive_failures += 1
                    raise SSIAuthError(f"{endpoint}: 403 – khóa chưa được cấp quyền dữ liệu này ({_msg(body)})")
                if r.status_code >= 400 or (code is not None and code not in OK_CODES and code >= 400):
                    db.log_ingest("SSI", endpoint, "error", 0, attempt, (time.time() - t0) * 1000, _msg(body))
                    self.consecutive_failures += 1
                    raise SSIAuthError(f"{endpoint}: HTTP {r.status_code} [{code}] {_msg(body)}")
                n = len(rows_of(body))
                db.log_ingest("SSI", endpoint, "ok", n, attempt, (time.time() - t0) * 1000)
                self.consecutive_failures = 0
                return body
            except SSIAuthError:
                raise
            except SSIError as exc:
                last_exc = exc
            except (requests.RequestException, ValueError) as exc:
                last_exc = exc
            wait = wait if wait is not None else self.backoff[min(attempt - 1, len(self.backoff) - 1)]
            log.warning("SSI %s lỗi lần %d: %s", endpoint, attempt, last_exc)
            if attempt <= self.retries:
                self._sleep(wait)
        self.consecutive_failures += 1
        db.log_ingest("SSI", endpoint, "error", 0, self.retries + 1, (time.time() - t0) * 1000, str(last_exc))
        raise SSIError(f"{endpoint} thất bại sau {self.retries + 1} lần: {last_exc}")

    def _paged(self, endpoint: str, params: Dict[str, Any]) -> Iterator[Dict]:
        """Lặp pageIndex đến khi hết (pagesCount nếu có, nếu không dừng ở trang ngắn hơn pageSize)."""
        size = self.page_size
        page = 1
        while True:
            body = self._request(endpoint, {**params, "pageIndex": page, "pageSize": size})
            data = rows_of(body)
            yield from data
            pages = None
            if isinstance(body, dict):
                pages = body.get("pagesCount") or body.get("pageCount")
            if not data or (pages is not None and page >= int(pages)) or (pages is None and len(data) < size):
                return
            page += 1
            if page > 500:
                log.warning("%s: quá 500 trang – dừng để tránh lặp vô hạn", endpoint)
                return

    # ── hàm dữ liệu ───────────────────────────────────────────────────────────
    def securities(self, board: str = "HOSE") -> List[Dict]:
        """Danh mục chứng khoán của sàn: symbol, stockType (Stock/ETF/CW…), listedShare, icbName…"""
        return rows_of(self._request("securities_by_board", {"board": board}))

    def index_components(self, index_code: str = "VN30") -> List[str]:
        rows = rows_of(self._request("securities_by_board", {"index": index_code}))
        return [str(r.get("symbol")).strip().upper() for r in rows if r.get("symbol")]

    def index_list(self, board: str = "HOSE") -> List[Dict]:
        return rows_of(self._request("index_list", {"board": board}))

    def index_summary(self, index_code: str, d: Optional[date] = None) -> List[Dict]:
        p = {"index": index_code}
        if d is not None:
            p["tradingDate"] = fmt_v3_date(d)
        return rows_of(self._request("index_summary", p))

    def securities_summary(self, symbol: str, start: date, end: date) -> List[Dict]:
        """Tổng hợp phiên của một mã trong khoảng ngày (mới → cũ). ~400 phiên/lần gọi với pageSize 1000."""
        return list(self._paged("securities_summary", {"symbol": symbol, "from": fmt_v3_date(start),
                                                       "to": fmt_v3_date(end)}))

    def master_data(self, start: date, end: date) -> List[Dict]:
        """Giá tham chiếu/trần/sàn mọi mã (mọi sàn) theo ngày."""
        return list(self._paged("masterdata", {"from": fmt_v3_date(start), "to": fmt_v3_date(end)}))

    def ohlc(self, symbol: str, timeframe: str, start: date, end: date) -> List[Dict]:
        """Nến OHLCV (timeFrame 1m/3m/5m/15m/1h/1d) – trả theo thứ tự cũ → mới."""
        rows = list(self._paged("ohlc", {"symbol": symbol, "timeFrame": timeframe,
                                         "from": f"{fmt_v3_date(start)} 00:00:00", "to": f"{fmt_v3_date(end)} 23:59:59"}))
        return sorted(rows, key=lambda r: str(r.get("tradingDate", "")))


def save_samples(client: Optional[SSIClient] = None, d: Optional[date] = None) -> Dict[str, str]:
    """B1.2 – gọi thử MỘT ngày cho từng hàm, lưu JSON gốc vào docs/api_samples/."""
    c = client or SSIClient()
    d = d or (today_vn() - timedelta(days=1))
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    out_dir = abs_path("docs/api_samples")
    out_dir.mkdir(parents=True, exist_ok=True)
    calls = {
        "securitiesSummary_FPT": lambda: c.securities_summary("FPT", d, d),
        "masterdata_FPT": lambda: [r for r in c.master_data(d, d) if r.get("symbol") == "FPT"],
        "indexSummary_VNINDEX": lambda: c.index_summary("VNINDEX", d),
        "ohlc_1d_VNINDEX": lambda: c.ohlc("VNINDEX", "1d", d, d),
        "ohlc_5m_FPT": lambda: c.ohlc("FPT", "5m", d, d)[:10],
        "securitiesByBoard_VN30": lambda: c.securities("HOSE")[:3] + [{"VN30": c.index_components("VN30")}],
        "indexList_HOSE": lambda: c.index_list("HOSE"),
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
            raise SystemExit("Chưa có SSI_API_KEY / SSI_API_SECRET trong .env")
        c.get_token()
        hose = c.securities("HOSE")
        print("Kết nối SSI FastConnect V3 thành công. Số mã HOSE:", len(hose),
              "· cổ phiếu:", sum(1 for r in hose if str(r.get("stockType", "")).lower() == "stock"))
