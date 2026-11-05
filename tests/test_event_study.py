"""Kiểm thử Module C – AR/CAR/BMP phát hiện hiệu ứng cài sẵn; không có hiệu ứng → không bác bỏ; ghép đối chứng."""
import numpy as np
import pandas as pd
import pytest

from src.analytics.event_study import EventStudy, _window_sum, bootstrap_ci, car_tests


def make_panel(effect: float = 0.03, n_sym: int = 30, n_days: int = 200, seed: int = 0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-01-01", periods=n_days)
    m = rng.normal(0.0003, 0.01, n_days)
    pos = 160
    rows = []
    for i in range(n_sym):
        a, b = rng.normal(0, 0.0005), rng.uniform(0.6, 1.4)
        r = a + b * m + rng.normal(0, 0.012, n_days)
        r[pos] += effect
        nf = rng.normal(0, 0.05, n_days)
        nf[pos] += effect * 5
        for k, d in enumerate(dates):
            rows.append({"trade_date": d, "symbol": f"S{i}", "ret": r[k], "nf": nf[k], "tv": 1e9 * np.exp(rng.normal(0, .2)),
                         "w": 0.001, "C": 0.0, "is_valid": True, "is_ceiling": False, "is_floor": False})
    st = pd.DataFrame(rows)
    vni = 1000 * np.cumprod(1 + m)
    prev = np.r_[1000, vni[:-1]]
    day = pd.DataFrame({"trade_date": dates, "vni": vni, "prev_value": prev, "dI": vni - prev})
    return st, day, pos


def _cars(res, w):
    L = w[1] - w[0] + 1
    return (np.array([_window_sum(r, "ar", w) for r in res]), np.array([_window_sum(r, "sar", w) / np.sqrt(L) for r in res]),
            np.array([r["p_pos"] for r in res]))


def test_detects_planted_effect():
    st, day, pos = make_panel(effect=0.03)
    es = EventStudy(st, day)
    res = es.run_group([f"S{i}" for i in range(30)], day["trade_date"].iloc[pos])
    assert len(res) == 30
    car, scar, pp = _cars(res, (-1, 1))
    assert car.mean() == pytest.approx(0.03, abs=0.01)
    tests = {t["test"]: t for t in car_tests(car, scar, pp, 500)}
    assert tests["BMP"]["p_value"] < 0.01 and tests["t cắt ngang"]["p_value"] < 0.01
    assert tests["Dấu tổng quát"]["p_value"] < 0.05


def test_no_effect_not_rejected():
    st, day, pos = make_panel(effect=0.0, seed=3)
    res = EventStudy(st, day).run_group([f"S{i}" for i in range(30)], day["trade_date"].iloc[pos])
    car, scar, pp = _cars(res, (-1, 1))
    tests = {t["test"]: t for t in car_tests(car, scar, pp, 500)}
    assert tests["BMP"]["p_value"] > 0.01


def test_market_adjusted_and_beta_recovered():
    st, day, pos = make_panel(effect=0.0)
    r = EventStudy(st, day).run_symbol("S0", pos)
    assert 0.4 < r["beta"] < 1.6 and r["n_est"] >= 100
    r2 = EventStudy(st, day, model="market_adj").run_symbol("S0", pos)
    assert r2["alpha"] == 0 and r2["beta"] == 1


def test_bootstrap_ci_contains_mean():
    x = np.random.default_rng(0).normal(1, 1, 200)
    lo, hi = bootstrap_ci(x, 1000)
    assert lo < x.mean() < hi


def test_control_matching_without_replacement(demo_db):
    from src.common.config import control_group
    cg = control_group()
    assert len(cg) > 0
    assert cg["control_symbol"].is_unique                       # không hoàn lại
    assert not set(cg["control_symbol"]) & set(cg["ftse_symbol"])
