"""
Kiểm thử vận hành (B5.10, B12.4) không cần mạng:
- Chuyển nguồn với đồng hồ giả: SSI lỗi 3 lần → NEO; im lặng > 120 giây → NEO; ổn định 5 phút → quay về SSI.
- SSI client: token, giãn cách ≥ 1,2 giây, thử lại 2–4–8 giây khi 'API calls quota exceeded', lỗi mạng, SSI trả rỗng.
- Nhật ký không chứa bí mật (mask_secrets).
"""
from datetime import datetime, timedelta

import pytest
import requests

from src.common.logging import mask_secrets


class Clock:
    def __init__(self):
        self.t = datetime(2026, 10, 1, 10, 0)

    def __call__(self):
        return self.t

    def advance(self, **kw):
        self.t += timedelta(**kw)


@pytest.fixture
def tmpdb(tmp_path, monkeypatch):
    p = tmp_path / "ops.duckdb"
    monkeypatch.setenv("FFR_DB_PATH", str(p))
    from src.data import database as db
    db.init_schema(p)
    return p


def test_failover_errors_and_recovery(tmpdb):
    from src.data import database as db
    from src.data.failover import FailoverController
    clk = Clock()
    fo = FailoverController(clock=clk, session_check=lambda t: True, path=tmpdb)
    fo.ssi_error("timeout")
    fo.ssi_error("timeout")
    assert fo.active == "SSI"
    fo.ssi_error("timeout")
    assert fo.active == "NEO"
    fo.ssi_ok()
    clk.advance(minutes=3)
    fo.ssi_ok()
    assert fo.active == "NEO"                 # chưa đủ 5 phút ổn định
    clk.advance(minutes=2, seconds=1)
    fo.ssi_ok()
    assert fo.active == "SSI"
    ev = db.query_df("SELECT * FROM source_events ORDER BY ts", path=tmpdb)
    assert ev["to_source"].tolist() == ["NEO", "SSI"]


def test_failover_silence(tmpdb):
    from src.data.failover import FailoverController
    clk = Clock()
    fo = FailoverController(clock=clk, session_check=lambda t: True, path=tmpdb)
    fo.ssi_ok()
    clk.advance(seconds=100)
    assert fo.tick() == "SSI"
    clk.advance(seconds=30)
    assert fo.tick() == "NEO"
    fo2 = FailoverController(clock=clk, session_check=lambda t: False, path=tmpdb)  # ngoài phiên: không chuyển
    clk.advance(hours=2)
    assert fo2.tick() == "SSI"


class FakeResp:
    def __init__(self, status=200, body=None):
        self.status_code, self._body = status, body or {}
        self.content = b"x"

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, gets):
        self.gets = list(gets)
        self.n_get = 0
        self.n_post = 0

    def post(self, url, json=None, timeout=None):
        self.n_post += 1
        return FakeResp(200, {"data": {"accessToken": "eyJabc.def.ghi"}, "status": 200})

    def get(self, url, params=None, timeout=None, headers=None):
        self.n_get += 1
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
    c = SSIClient("id_123456", "secret_abcdef", session=FakeSession(gets), sleep=sleep, clock=clock)
    return c, sleeps


def test_ssi_retry_backoff_on_quota(tmpdb):
    ok = FakeResp(200, {"status": 200, "data": [{"Symbol": "FPT"}], "totalRecord": 1})
    quota = FakeResp(200, {"status": 429, "message": "API calls quota exceeded"})
    c, sleeps = _client([quota, quota, ok], tmpdb)
    out = c.securities("HOSE")
    assert out == [{"Symbol": "FPT"}]
    assert [s for s in sleeps if s in (2, 4, 8)] == [2, 4]


def test_ssi_gives_up_after_retries_and_network_error(tmpdb):
    from src.ssi_api.ssi_client import SSIError
    err = requests.ConnectionError("mất mạng")
    c, sleeps = _client([err, err, err, err], tmpdb)
    with pytest.raises(SSIError):
        c.securities("HOSE")
    assert [s for s in sleeps if s in (2, 4, 8)] == [2, 4, 8]
    assert c.consecutive_failures == 1


def test_ssi_empty_day_and_throttle(tmpdb):
    empty = FakeResp(200, {"status": 200, "data": [], "totalRecord": 0})
    c, sleeps = _client([empty, empty], tmpdb)
    assert c.daily_stock_price(datetime(2026, 9, 2).date()) == []      # ngày nghỉ → rỗng, không lỗi
    c.daily_stock_price(datetime(2026, 9, 3).date())
    assert any(abs(s - 1.2) < 1e-9 for s in sleeps)                   # giãn cách 1,2 giây giữa hai lần gọi


def test_token_refresh_on_401(tmpdb):
    ok = FakeResp(200, {"status": 200, "data": [], "totalRecord": 0})
    c, _ = _client([FakeResp(401, {}), ok], tmpdb)
    c.securities()
    assert c.http.n_post == 2                                         # lấy token lần đầu + làm mới sau 401


def test_mask_secrets(monkeypatch):
    monkeypatch.setenv("SSI_CONSUMER_SECRET", "SuperSecret123")
    s = mask_secrets('consumerSecret="SuperSecret123" Authorization: Bearer eyJa.bcd.efg token=abc 123456789:AAAbbbcccdddeeefffggghhhiiijjjkkk')
    assert "SuperSecret123" not in s and "eyJa.bcd.efg" not in s and "AAAbbb" not in s


def test_demo_mode_ingest_no_network(demo_db):
    from src.data import database as db
    il = db.query_df("SELECT * FROM ingest_log", path=demo_db[0])
    assert il.empty                                                    # chế độ mẫu không gọi API thật
