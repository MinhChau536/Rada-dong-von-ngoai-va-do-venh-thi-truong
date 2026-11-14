"""
Kiểm thử vận hành (B5.10, B12.4) không cần mạng:
- SSI FastConnect V3 client: token {apiKey, apiSecret}, giãn cách giữa hai lần gọi, thử lại 2–4–8 giây khi 429,
  lỗi mạng, {"code": 204} (rỗng), làm mới token sau 401, phân trang theo pagesCount.
- Chuẩn hóa bản ghi: giá tham chiếu/trần/sàn quy về thang giá đã điều chỉnh; sửa indexChange lệch.
- Bộ ghi WebSocket: tin SDK → dòng raw_stream; bỏ xác nhận subscribe.
- Nhật ký không chứa bí mật (mask_secrets).
"""
from datetime import datetime

import pytest
import requests

from src.common.logging import mask_secrets


@pytest.fixture
def tmpdb(tmp_path, monkeypatch):
    p = tmp_path / "ops.duckdb"
    monkeypatch.setenv("FFR_DB_PATH", str(p))
    from src.data import database as db
    db.init_schema(p)
    return p


class FakeResp:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code, self._body = status, body if body is not None else {}
        self.headers = headers or {}
        self.content = b"x"

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, gets):
        self.gets = list(gets)
        self.n_get = 0
        self.n_post = 0
        self.posted = []
        self.params = []

    def post(self, url, json=None, timeout=None):
        self.n_post += 1
        self.posted.append((url, json))
        return FakeResp(200, {"tokenType": "Bearer", "accessToken": "eyJabc.def.ghi", "expiresAt": 4102444800})

    def get(self, url, params=None, timeout=None, headers=None):
        self.n_get += 1
        self.params.append((url, params))
        g = self.gets.pop(0)
        if isinstance(g, Exception):
            raise g
        return g


def _client(gets, tmpdb):
    from src.ssi_api.ssi_client import SSIClient
    sleeps = []
    t = [0.0]

    def clock():
        return t[0]

    def sleep(s):
        sleeps.append(s)
        t[0] += s
    c = SSIClient("key_123456", "secret_abcdef", session=FakeSession(gets), sleep=sleep, clock=clock)
    return c, sleeps


def test_ssi_v3_auth_body_and_endpoint(tmpdb):
    c, _ = _client([FakeResp(200, [{"symbol": "FPT", "stockType": "Stock"}])], tmpdb)
    assert c.securities("HOSE") == [{"symbol": "FPT", "stockType": "Stock"}]
    url, body = c.http.posted[0]
    assert url.endswith("/api/v3/auth/token") and body == {"apiKey": "key_123456", "apiSecret": "secret_abcdef"}
    gurl, params = c.http.params[0]
    assert gurl.endswith("/api/v3/data/securitiesByBoard") and params == {"board": "HOSE"}


def test_ssi_retry_backoff_on_429(tmpdb):
    ok = FakeResp(200, [{"symbol": "FPT"}])
    quota = FakeResp(429, {"code": 429, "msg": "Too Many Requests"})
    c, sleeps = _client([quota, quota, ok], tmpdb)
    assert c.securities("HOSE") == [{"symbol": "FPT"}]
    assert [s for s in sleeps if s in (2, 4, 8)] == [2, 4]


def test_ssi_gives_up_after_retries_and_network_error(tmpdb):
    from src.ssi_api.ssi_client import SSIError
    err = requests.ConnectionError("mất mạng")
    c, sleeps = _client([err, err, err, err], tmpdb)
    with pytest.raises(SSIError):
        c.securities("HOSE")
    assert [s for s in sleeps if s in (2, 4, 8)] == [2, 4, 8]
    assert c.consecutive_failures == 1


def test_ssi_no_content_and_throttle(tmpdb):
    empty = FakeResp(200, {"code": 204, "msg": "No Content"})
    c, sleeps = _client([empty, empty], tmpdb)
    assert c.index_summary("VNINDEX", datetime(2026, 11, 8).date()) == []      # ngày nghỉ → rỗng, không lỗi
    c.index_summary("VNINDEX", datetime(2026, 11, 7).date())
    assert c.http.params[0][1] == {"index": "VNINDEX", "tradingDate": "2026/11/08"}
    assert any(abs(s - c.min_interval) < 1e-9 for s in sleeps)              # giãn cách giữa hai lần gọi


def test_ssi_paging_by_pages_count(tmpdb):
    p1 = FakeResp(200, {"code": 200, "pagesCount": 2, "data": [{"symbol": "A"}]})
    p2 = FakeResp(200, {"code": 200, "pagesCount": 2, "data": [{"symbol": "B"}]})
    c, _ = _client([p1, p2], tmpdb)
    rows = c.master_data(datetime(2026, 11, 2).date(), datetime(2026, 11, 6).date())
    assert [r["symbol"] for r in rows] == ["A", "B"]
    assert [p["pageIndex"] for _, p in c.http.params] == [1, 2]
    assert c.http.params[0][1]["from"] == "2026/11/02"


def test_token_refresh_on_401(tmpdb):
    ok = FakeResp(200, [])
    c, _ = _client([FakeResp(401, {"code": 401101, "msg": "expired"}), ok], tmpdb)
    c.securities()
    assert c.http.n_post == 2                                         # lấy token lần đầu + làm mới sau 401


def test_auth_error_not_retried(tmpdb):
    from src.ssi_api.ssi_client import SSIAuthError
    c, sleeps = _client([FakeResp(403, {"code": 403, "msg": "scope"})], tmpdb)
    with pytest.raises(SSIAuthError):
        c.securities()
    assert not [s for s in sleeps if s in (2, 4, 8)]


def test_enrich_stock_adjusted_history():
    from src.ssi_api.ssi_client import enrich_stock
    # FPT 03/04/2025 (số thật từ API): giá đã điều chỉnh 86 851,316; giá gốc tham chiếu 122 000, priceChange −8 500
    row = {"close": "86851.316", "priceChange": "-8500", "priceChangePercentage": "-6.97"}
    r = enrich_stock(row, {"refPrice": 122000, "ceiling": 130500, "floor": 113500})
    assert abs(float(r["close"]) / r["refPrice"] - 1 - (-8500 / 122000)) < 1e-6
    assert r["floor"] <= float(r["close"]) <= r["ceiling"]
    # phiên chưa điều chỉnh: k = 1, giữ nguyên giá gốc
    r2 = enrich_stock({"close": "50800", "priceChange": "-2100", "priceChangePercentage": "-3.97"},
                      {"refPrice": 52900, "ceiling": 56600, "floor": 49200})
    assert (r2["refPrice"], r2["ceiling"], r2["floor"], r2["adjFactor"]) == (52900, 56600, 49200, 1.0)
    # thiếu masterdata → suy từ % thay đổi
    r3 = enrich_stock({"close": "104", "priceChange": "4", "priceChangePercentage": "4"})
    assert abs(r3["refPrice"] - 100) < 1e-9


def test_enrich_stock_ceiling_exact():
    from src.ssi_api.ssi_client import enrich_stock
    r = enrich_stock({"close": "53900", "priceChange": "3500", "priceChangePercentage": "6.94"},
                     {"refPrice": 50400, "ceiling": 53900, "floor": 46900})
    assert float(r["close"]) >= r["ceiling"]


def test_enrich_index_fixes_scaled_change():
    from src.ssi_api.ssi_client import enrich_index
    r = enrich_index({"indexValue": "1229.84", "indexChange": "-8799", "indexChangePercentage": "-6.677"},
                     {"open": "1300", "high": "1310", "low": "1220"})
    assert abs(float(r["indexChange"]) + 88.0) < 0.1 and r["open"] == "1300"
    ok = enrich_index({"indexValue": "1725.36", "indexChange": "-15.37", "indexChangePercentage": "-0.88"})
    assert ok["indexChange"] == "-15.37"


def test_stream_row_from_sdk_message():
    from dataclasses import dataclass
    from src.data.recorder_ssi import to_row

    @dataclass
    class ForeignRoomMessage:
        symbol: str = "VNM"
        buy_value: int = 15551870000

    r = to_row(ForeignRoomMessage(), datetime(2026, 11, 9, 13, 11))
    assert r["channel"] == "room" and r["symbol"] == "VNM" and "15551870000" in r["payload"]
    assert to_row({"method": "subscribe", "status": "ok"}) is None


def test_mask_secrets(monkeypatch):
    monkeypatch.setenv("SSI_API_SECRET", "SuperSecret123")
    s = mask_secrets('apiSecret="SuperSecret123" Authorization: Bearer eyJa.bcd.efg token=abc 123456789:AAAbbbcccdddeeefffggghhhiiijjjkkk')
    assert "SuperSecret123" not in s and "eyJa.bcd.efg" not in s and "AAAbbb" not in s


def test_demo_mode_ingest_no_network(demo_db):
    from src.data import database as db
    il = db.query_df("SELECT * FROM ingest_log", path=demo_db[0])
    assert il.empty                                                    # bộ dữ liệu kiểm thử không gọi API thật
