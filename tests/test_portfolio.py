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
    assert len(btn) == 8 and all(len(b["callback_data"].encode()) <= 64 for b in btn)
    assert keyboard_json(None) is None
