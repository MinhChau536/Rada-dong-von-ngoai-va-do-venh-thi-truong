"""Kiểm thử tối ưu danh mục (src/analytics/portfolio.py), watchlist không tự khôi phục mặc định, bố cục tin nhắn bot."""
import numpy as np
import pandas as pd
import pytest

from src.analytics import portfolio as P


def _rets(n=400, seed=7):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-01-01", periods=n)
    common = rng.normal(0, 0.008, n)
    sig = {"AAA": 0.010, "BBB": 0.015, "CCC": 0.025, "DDD": 0.020}
    return pd.DataFrame({k: common + rng.normal(0.0004, s, n) for k, s in sig.items()}, index=idx)


def test_ledoit_wolf_is_symmetric_positive_definite():
    c = P.ledoit_wolf(_rets().to_numpy())
    assert np.allclose(c, c.T) and np.linalg.eigvalsh(c).min() > 0


@pytest.mark.parametrize("method", list(P.METHODS))
def test_weights_valid_long_only_capped(method):
    est = P.estimate(_rets())
    w = P.optimize(est, method, max_w=0.4, target_vol=0.2)
    assert w.sum() == pytest.approx(1, abs=1e-6) and (w >= -1e-9).all() and (w <= 0.4 + 1e-6).all()


def test_min_var_has_lowest_vol_and_target_respects_vol():
    est = P.estimate(_rets())
    vols = {k: P.vol(P.optimize(est, k, 1.0, 0.18), est["cov"]) for k in P.METHODS}
    assert vols["min_var"] <= min(vols.values()) + 1e-6
    assert vols["target"] <= 0.18 + 1e-3 or vols["target"] == pytest.approx(vols["min_var"], abs=1e-6)


def test_risk_parity_equalises_risk_contribution():
    r = _rets()
    est = P.estimate(r)
    w = P.optimize(est, "risk_parity")
    rc = P.metrics(w, r, est)["risk_contrib"]
    assert rc.max() - rc.min() < 0.02
    assert w[0] > w[2]                                          # mã ít biến động nhận tỷ trọng lớn hơn


def test_allocate_shares_rounds_to_lots():
    al = P.allocate_shares(pd.Series({"AAA": 0.5, "BBB": 0.5}), pd.Series({"AAA": 25000.0, "BBB": 51000.0}), 100e6)
    assert (al["shares"] % 100 == 0).all() and al["value"].sum() <= 100e6
    assert al.set_index("symbol").loc["AAA", "shares"] == 2000


def test_suggestions_flag_correlated_pair_and_vol_above_target():
    r = _rets()
    r["EEE"] = r["DDD"] + np.random.default_rng(1).normal(0, 0.002, len(r))
    est = P.estimate(r)
    w = P.optimize(est, "equal")
    m = P.metrics(w, r, est)
    out = P.suggestions(r, w, m, P.Profile("Thận trọng", 0.05, 0.25, 0.9, ""), pd.DataFrame())
    assert any("DDD và EEE" in s for s in out) and any("vượt mục tiêu" in s for s in out)


def test_watchlist_can_be_emptied_and_defaults_do_not_return(demo_db):
    from src.analytics import watchlist_impact as wi
    p, _ = demo_db
    wi.ensure_default(p)
    before = wi.get_watchlist(p)
    assert before
    try:
        wi.clear(p)
        wi.ensure_default(p)                                    # mở lại trang → KHÔNG nạp lại mặc định
        assert wi.get_watchlist(p) == []
        wi.add("FPT", path=p)
        assert wi.get_watchlist(p) == ["FPT"]
    finally:                                                    # kho kiểm thử dùng chung → trả lại danh mục cũ
        wi.clear(p)
        for s in before:
            wi.add(s, path=p)


def test_keyboard_json_limits_callback_data():
    import json
    from src.bot.telegram_api import keyboard_json
    from src.bot import messages as M
    mk = json.loads(keyboard_json(M.MENU))
    btn = [b for row in mk["inline_keyboard"] for b in row]
    assert len(btn) == 10 and all(len(b["callback_data"].encode()) <= 64 for b in btn)
    assert keyboard_json(None) is None


def test_bot_runtime_pid_detection(tmp_path, monkeypatch):
    import os
    from src.bot import runtime
    monkeypatch.setattr(runtime, "PID_FILE", tmp_path / ".bot.pid")
    assert runtime.bot_process() is None
    runtime.write_pid()
    assert runtime.bot_process()["pid"] == os.getpid()          # tiến trình hiện tại đang sống
    runtime.clear_pid()
    assert runtime.bot_process() is None
    assert runtime.pid_alive(0) is False


def test_report_telegram_and_verification_pages():
    """Báo cáo, Telegram là trang riêng; Backtest + Chất lượng + Kết nối gộp thành trang Kiểm chứng & dữ liệu."""
    from pathlib import Path
    src = Path("src/app/main.py").read_text(encoding="utf-8")
    for slug in ('url_path="bao-cao"', 'url_path="telegram"', 'url_path="kiem-chung"', 'url_path="chan-doan"'):
        assert slug in src
    merged = Path("src/app/views/p_kiem_chung.py").read_text(encoding="utf-8")
    assert "p10_backtest.render(embedded=True)" in merged and "p7_chat_luong.render(embedded=True)" in merged
    from src.app.components.banners import ART, TITLE_TO_SLUG
    assert TITLE_TO_SLUG["Bot Telegram"] in ART and TITLE_TO_SLUG["Kiểm chứng & dữ liệu"] in ART


def test_stock_and_sector_cards_are_valid_telegram_html(demo_db):
    """Lỗi cũ: '(< 95%)' không escape → Telegram 'Can't parse entities' (BadRequest)."""
    import re
    from src.bot import messages as M
    from src.data import database as db
    from src.reports import context
    p, _ = demo_db
    ctx = context.build(path=p)
    sym = db.query_df("SELECT symbol FROM indicator_stock_daily WHERE sector IS NOT NULL ORDER BY tv DESC LIMIT 1", path=p)["symbol"].iat[0]
    allowed = re.compile(r"</?(b|i|code|u|s|pre)>")
    for fn in (M.stock_card, M.sector_card):
        text, kb = fn(sym, ctx)
        assert not [t for t in re.findall(r"<[^>]*>?", text) if not allowed.fullmatch(t)], fn.__name__
        assert len(text) < 4000 and all(len(c.encode()) <= 64 for row in kb for _, c in row)
    text, kb = M.stock_card(sym, ctx)
    assert "ĐÁNH GIÁ TỔNG QUÁT" in text and any(c == f"intra:{sym}" for row in kb for _, c in row)


def test_intraday_summary_and_chart():
    import pandas as pd
    from src.bot import intraday
    ts = pd.date_range("2026-11-13 09:15", periods=60, freq="1min").append(pd.date_range("2026-11-13 13:00", periods=60, freq="1min"))
    px = pd.Series(range(120), dtype=float) * 10 + 10000
    df = pd.DataFrame({"ts": ts, "open": px, "high": px + 20, "low": px - 20, "close": px + 5, "volume": 1000.0})
    df["value"] = df["close"] * df["volume"]
    sm = intraday.summary(df, 10000.0)
    assert sm["last"] == 11195 and sm["vol_am"] == sm["vol_pm"] == 60000 and sm["high_t"].hour == 13
    assert intraday.chart(df, "AAA", pd.Timestamp("2026-11-13").date(), 10000.0).getbuffer().nbytes > 10000


def _bars(closes, start="2026-11-13 09:15", vol=1000.0):
    import pandas as pd
    ts = pd.date_range(start, periods=len(closes), freq="1min")
    c = pd.Series(closes, dtype=float)
    return pd.DataFrame({"ts": ts, "open": c, "high": c, "low": c, "close": c, "volume": vol, "value": c * vol})


def test_market_rules_thresholds_band_ma50_and_foreign():
    from src.bot import monitor as mo
    lv = mo.LEVELS["Vừa"]
    df = _bars([1000.0] * 30 + [985.0] * 5 + [978.0])                     # -2,2% và rơi mạnh trong 15 phút
    base = {"ref": 1000.0, "prev_close": 1000.0, "sigma": 1.0, "ma50_prev": 990.0, "nf_sd": 300e9}
    keys = [k for k, _ in mo.market_rules(df, base, lv, {"nf": -800e9, "up": 40, "dn": 300})]
    assert {"vni:dn:1.0", "vni:dn:2.0", "vniband:dn", "vnima50:dn", "vninf:dn", "vnibreadth:giảm"} <= set(keys)
    assert any(k.startswith("vni15:") for k in keys)
    calm = mo.market_rules(_bars([1000.0, 1001.0, 1002.0]), base, lv, {"nf": 10e9, "up": 150, "dn": 140})
    assert calm == []


def test_stock_rules_ceiling_volume_and_breakout():
    from datetime import datetime
    from src.bot import monitor as mo
    df = _bars([20000.0] * 10 + [21400.0], vol=50000.0)                    # +7% trần, KL 550k
    hits = dict(mo.stock_rules("AAA", df, {"ref": 20000.0, "hi20": 21000.0, "lo20": 18000.0, "vol20": 300000.0},
                               mo.LEVELS["Vừa"], datetime(2026, 11, 13, 10, 0)))
    assert {"AAA:up:3.0", "AAA:up:5.0", "AAA:ceil", "AAA:vol", "AAA:hi20"} <= set(hits)


def test_alert_prefs_and_dedup(tmp_path, monkeypatch):
    import json
    from src.bot import monitor as mo
    monkeypatch.setattr(mo, "STORE", tmp_path / "a.json")
    assert mo.prefs("1") == {"on": True, "types": {"market": True, "watch": True, "trend": True}, "level": "Vừa"}
    mo.set_pref("1", type="watch")
    mo.set_pref("1", level="Cao")
    assert mo.prefs("1")["types"]["watch"] is False and mo.prefs("1")["level"] == "Cao"
    assert mo._targets("watch", ["1"]) == [] and mo._targets("market", ["1"]) == ["1"]
    assert mo._claim(["x", "y"], "2026-11-13") == ["x", "y"] and mo._claim(["x", "z"], "2026-11-13") == ["z"]
    assert mo._claim(["x"], "2026-11-14") == ["x"]                         # ngày mới → gửi lại được
    text, kb = mo.settings_view("1")
    assert "CẢNH BÁO TỰ ĐỘNG" in text and all(len(c.encode()) <= 64 for row in kb for _, c in row)
    assert json.loads((tmp_path / "a.json").read_text(encoding="utf-8"))["chats"]["1"]["level"] == "Cao"
