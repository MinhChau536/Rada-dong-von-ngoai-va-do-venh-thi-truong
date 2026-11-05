"""Kiểm thử Module B – (6), (7), (8), chuỗi & đảo chiều, mẫu số nf, trạng thái hấp thụ (B5.12)."""
import numpy as np
import pandas as pd
import pytest

from src.finance.domestic import absorb_state, absorb_states, absorption_rate, active_imbalance
from src.finance.foreign_flow import decide_denominator, market_flows, stock_flows
from src.finance.utils import streaks


def _df(n=80):
    rng = np.random.default_rng(1)
    dates = pd.bdate_range("2026-01-01", periods=n)
    rows = []
    for s in ("A", "B"):
        for d in dates:
            tv = 1e10
            nf = rng.normal(0, 0.1)
            rows.append({"trade_date": d, "symbol": s, "fb": tv * (0.2 + nf / 2), "fs": tv * (0.2 - nf / 2), "tv": tv,
                         "tv_pt": 0.0, "remain": 1e6, "room": 4e6, "is_valid": True})
    return pd.DataFrame(rows)


def test_nf_fpr_u_formulas():
    d = pd.DataFrame([{"trade_date": pd.Timestamp("2026-01-02"), "symbol": "A", "fb": 30.0, "fs": 10.0, "tv": 100.0,
                       "tv_pt": 0.0, "remain": 25.0, "room": 100.0}])
    s = stock_flows(d).iloc[0]
    assert s["net_flow"] == 20 and s["nf"] == pytest.approx(0.2) and s["FPR"] == pytest.approx(0.2)
    assert s["U"] == pytest.approx(0.75)
    s2 = stock_flows(d, "match_plus_deal").iloc[0]
    assert s2["nf"] == pytest.approx(0.2)


def test_division_by_zero_and_room_zero():
    d = pd.DataFrame([{"trade_date": pd.Timestamp("2026-01-02"), "symbol": "A", "fb": 0.0, "fs": 0.0, "tv": 0.0,
                       "tv_pt": 0.0, "remain": 0.0, "room": 0.0}])
    s = stock_flows(d).iloc[0]
    assert np.isnan(s["nf"]) and np.isnan(s["U"])


def test_nf_bounded():
    s = stock_flows(_df())
    assert s["nf"].between(-1, 1).all()


def test_hhi_hand_example():
    d = pd.DataFrame({"trade_date": pd.Timestamp("2026-01-02"), "symbol": ["A", "B", "C"], "net_flow": [30.0, -10.0, 0.0],
                      "fb": 1.0, "fs": 1.0, "tv": 10.0, "is_valid": True})
    m = market_flows(d).iloc[0]
    assert m["HHI"] == pytest.approx(0.75 ** 2 + 0.25 ** 2)
    assert m["NF_total"] == 20


def test_streak_and_reversal():
    sg = pd.Series([1, 2, 3, -1, -2, 5, 0, 1])
    assert streaks(sg).tolist() == [1, 2, 3, -1, -2, 1, 0, 1]
    d = pd.DataFrame({"trade_date": pd.bdate_range("2026-01-01", periods=6), "symbol": "A",
                      "fb": [5, 5, 5, 1, 1, 1.0], "fs": [1, 1, 1, 5, 5, 5.0], "tv": 10.0, "tv_pt": 0.0, "remain": 1.0, "room": 2.0})
    s = stock_flows(d)
    assert s["reversal"].tolist() == [False, False, False, True, False, False]


def test_denominator_decision():
    d = _df(10)
    assert decide_denominator(d)["chosen"] == "match"
    d2 = d.copy()
    d2["tv_pt"] = d2["tv"] * 0.5
    d2["fb"] = d2["tv"] * 1.2          # (FB+FS)/2 > TV ở phiên thỏa thuận lớn → gồm thỏa thuận
    d2["fs"] = d2["tv"] * 1.0
    assert decide_denominator(d2)["chosen"] == "match_plus_deal"


@pytest.mark.parametrize("nf,r,exp", [(-0.1, 0.01, "absorb"), (-0.1, -0.01, "joint_sell"), (0.1, 0.01, "joint_buy"),
                                      (0.1, -0.01, "domestic_take"), (0.04, 0.02, "neutral"), (-0.2, 0.004, "neutral"),
                                      (float("nan"), 0.01, "neutral")])
def test_absorb_state_table(nf, r, exp):
    assert absorb_state(nf, r, 0.05, 0.005) == exp
    assert absorb_states(pd.Series([nf]), pd.Series([r])).iloc[0] == exp


def test_absorption_rate_and_imbalance():
    assert absorption_rate(pd.Series(["absorb", "joint_sell", "absorb", "neutral"])) == pytest.approx(2 / 3)
    t = pd.DataFrame({"symbol": ["A", "A", "A"], "side": ["BU", "SD", "BU"], "vol": [300, 100, 100]})
    assert active_imbalance(t).iloc[0]["imbalance"] == pytest.approx((400 - 100) / 500)
