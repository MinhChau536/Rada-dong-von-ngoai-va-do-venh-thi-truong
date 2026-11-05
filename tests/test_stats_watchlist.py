"""Kiểm thử hàm thống kê (Holm, Newey–West, hoán vị khối, Dunn) và Module D (ER, beta Dimson)."""
import numpy as np
import pandas as pd
import pytest

from src.analytics.stats_tests import block_permutation_diff, holm, nw_mean_test
from src.analytics.watchlist_impact import beta_dimson, beta_ols, dunn


def test_holm_matches_definition():
    df = pd.DataFrame({"hypothesis": "H", "test": "t", "group": "g", "metric": "m", "model": "", "variant": "base",
                       "p_value": [0.01, 0.04, 0.03]})
    out = holm(df)
    # Holm: sắp tăng 0.01, 0.03, 0.04 → ×3, ×2, ×1 với đơn điệu → 0.03, 0.06, 0.06
    assert out["p_holm"].tolist() == pytest.approx([0.03, 0.06, 0.06])


def test_nw_mean_test():
    rho = pd.Series(np.random.default_rng(0).normal(0.3, 0.1, 200))
    r = nw_mean_test(rho, 5)
    assert r["mean"] == pytest.approx(0.3, abs=0.03) and r["p"] < 1e-6


def test_block_permutation_detects_shift():
    x = np.r_[np.zeros(100), np.ones(40)]
    assert block_permutation_diff(x, 100, 5, 500) < 0.01
    y = np.random.default_rng(1).integers(0, 2, 140).astype(float)
    assert block_permutation_diff(y, 100, 5, 500) > 0.01


def test_dunn_runs():
    g = {"a": np.arange(20.0), "b": np.arange(20.0) + 30, "c": np.arange(20.0)}
    res = dunn(g)
    ab = [r for r in res if {r["a"], r["b"]} == {"a", "b"}][0]
    ac = [r for r in res if {r["a"], r["b"]} == {"a", "c"}][0]
    assert ab["p_holm"] < 0.01 and ac["p"] > 0.5


def test_beta_dimson_sums_lags():
    rng = np.random.default_rng(0)
    m = pd.Series(rng.normal(0, 0.01, 300))
    r = 0.5 * m + 0.4 * m.shift(1).fillna(0) + rng.normal(0, 0.002, 300)   # cổ phiếu phản ứng trễ
    bd = beta_dimson(r, m, 120, 100)
    assert bd == pytest.approx(0.9, abs=0.1)
    assert beta_ols(r.tail(120), m.tail(120)) < bd                         # beta OLS bị chệch xuống (Dimson 1979)


def test_watchlist_profile_from_db(demo_db):
    from src.data import database as db
    pf = db.query_df("SELECT * FROM indicator_watchlist", path=demo_db[0])
    assert len(pf) >= 5
    r = pf[pf["has_data"]].iloc[0]
    st = db.query_df("SELECT ret, ER_I, ER_M FROM indicator_stock_daily WHERE symbol = ? AND trade_date = ?",
                     [r["symbol"], r["trade_date"]], path=demo_db[0]).iloc[0]
    assert r["ER_I"] == pytest.approx(st["ER_I"]) and r["ER_M"] == pytest.approx(st["ER_M"])
    assert pf.loc[pf["has_data"], "sentence"].str.contains("điểm VN-Index").all()


def test_market_health_weights_and_labels():
    from src.analytics.health import market_health, period_returns
    up = pd.Series(np.linspace(100, 130, 250))
    h = market_health(up, 80, 75, 10)
    assert h["weights_sum"] == 100 and h["label"] == "Tích cực"
    assert h["components"]["divergence"]["score"] == pytest.approx(90)     # điểm độ vênh = 100 − phân vị D
    down = pd.Series(np.linspace(130, 100, 250))
    assert market_health(down, 10, 10, 95)["label"] == "Tiêu cực"
    s = pd.Series([100.0, 110.0], index=pd.to_datetime(["2026-01-02", "2026-02-02"]))
    assert period_returns(s)["1Th"] == pytest.approx(10.0)
