"""Kiểm thử cảnh báo (B8.1, B8.2): từng quy tắc bằng dữ liệu giả, cooldown 30 phút, giới hạn 5/ngày, hệ thống không giới hạn."""
from datetime import datetime, timedelta

import pandas as pd

from src.analytics.alerts import dispatch, evaluate


def _day(**kw):
    base = {"trade_date": pd.Timestamp("2026-10-01"), "dI": 2.0, "CR5": 0.3, "session_type": "broad_up",
            "high_divergence": False, "z_NF_total": 0.5, "NF_total": -1e11, "r_vni_pct": 0.5, "median_ret_pct": 0.2,
            "D_pct250": 50}
    base.update(kw)
    return pd.Series(base)


LEAD = pd.DataFrame({"symbol": ["VIC", "VHM", "FPT"], "side": ["pos", "pos", "neg"], "rank": [1, 2, 1], "C": [3, 2, -1]})
FLOW = pd.DataFrame({"symbol": ["A", "B", "C"], "net_flow": [1e10, -2e10, 3e9]})


def _wl(**kw):
    r = {"symbol": "FPT", "is_valid": True, "pct60_nf": 50, "net_flow": 1e9, "streak": 2, "sd60_ER_M": 0.01, "ER_M": 0.0,
         "ret": 0.0, "C": -1.0, "U": 0.5}
    r.update(kw)
    return pd.DataFrame([r])


def rules(alerts):
    return sorted({a["rule_no"] for a in alerts})


def test_each_rule():
    assert 1 in rules(evaluate(_day(dI=8, CR5=0.7), LEAD, FLOW, None))
    assert 2 in rules(evaluate(_day(session_type="narrow_up", high_divergence=True), LEAD, FLOW, None))
    assert 3 in rules(evaluate(_day(z_NF_total=-2.5), LEAD, FLOW, None))
    assert 4 in rules(evaluate(_day(), LEAD.iloc[:0], FLOW, _wl(pct60_nf=97)))
    assert 5 in rules(evaluate(_day(), LEAD.iloc[:0], FLOW, _wl(ER_M=0.03, ret=0.03)))
    assert 6 in rules(evaluate(_day(), LEAD, FLOW, _wl()))
    assert 7 in rules(evaluate(_day(), LEAD.iloc[:0], FLOW, _wl(U=0.97)))
    assert 8 in rules(evaluate(_day(), LEAD, FLOW, None, {"source": "NEO", "since": "10:05"}))
    assert rules(evaluate(_day(), LEAD.iloc[:0], FLOW, _wl())) == []


def _hist():
    return pd.DataFrame(columns=["event_id", "ts", "alert_type", "symbol", "priority", "status"])


def test_cooldown_dedup():
    al = evaluate(_day(dI=8, CR5=0.7), LEAD, FLOW, None)
    t0 = datetime(2026, 10, 1, 10, 0)
    out1 = dispatch(al, t0, mode="backtest", history=_hist())
    h = pd.concat([_hist(), out1])
    out2 = dispatch(al, t0 + timedelta(minutes=10), mode="backtest", history=h)
    assert (out1["status"] == "simulated").all()
    assert (out2["status"] == "suppressed_duplicate").all()


def test_daily_limit_and_system_unlimited():
    al = []
    for i in range(8):
        al += evaluate(_day(), LEAD.iloc[:0], FLOW, _wl(symbol=f"S{i}", U=0.99))
    al += evaluate(_day(), LEAD, FLOW, None, {"source": "NEO", "since": "10:00"})
    out = dispatch(al, datetime(2026, 10, 1, 11, 0), mode="backtest", history=_hist())
    kept = out[out["status"] == "simulated"]
    assert (kept["priority"] != "system").sum() == 5
    assert (out["status"] == "suppressed_limit").sum() == 3
    assert (kept["priority"] == "system").sum() == 1


def test_backtest_average_within_limit(demo_db):
    bt = demo_db[1]["alerts_backtest"]
    assert bt["mean_market_per_day"] <= 5 and bt["max_market_per_day"] <= 5
