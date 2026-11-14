"""Kiểm thử triển vọng thống kê (src/analytics/outlook.py) và so sánh giai đoạn H4 (stats_tests.h4)."""
import numpy as np
import pandas as pd
import pytest

from src.analytics import outlook, stats_tests


def _gbm(n=1500, sigma=0.01, seed=3):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2019-01-02", periods=n)
    return pd.Series(1000 * np.exp(np.cumsum(rng.normal(0, sigma, n))), index=idx)


def test_vol_range_coverage_near_nominal_for_gaussian_returns():
    c = _gbm()
    vr = outlook.vol_range(c, (5, 20), start="2019-01-02")
    assert vr[5]["lo90"] < c.iloc[-1] < vr[5]["hi90"]
    assert vr[5]["lo68"] > vr[5]["lo90"] and vr[20]["hi90"] > vr[5]["hi90"]
    assert vr[5]["sigma_d"] == pytest.approx(0.01, rel=0.35)
    assert 0.85 <= vr[5]["coverage90"] <= 0.95                 # lợi suất chuẩn → bao phủ ≈ 90%


def test_analog_probabilities_use_only_completed_windows():
    c = _gbm(800)
    nf = pd.Series(np.random.default_rng(1).normal(0, 1, len(c)), index=c.index)
    a = outlook.analog_probabilities(c, nf, (5, 20), start="2019-01-02", min_n=10)
    assert a["available"]
    for h in (5, 20):
        r = a["horizons"][h]
        assert r["n_base"] <= len(c) - h - 49                   # cần MA50 và đủ h phiên phía sau
        assert 0 <= r["p_up"] <= 1 and r["p10"] <= r["median"] <= r["p90"]
    # thay đổi giá SAU phiên cuối không được ảnh hưởng (không nhìn trước)
    c2 = pd.concat([c, pd.Series([c.iloc[-1] * 2], index=[c.index[-1] + pd.offsets.BDay()])])
    nf2 = nf.reindex(c2.index).fillna(0)
    b = outlook.analog_probabilities(c2.iloc[:-1], nf2.iloc[:-1], (5,), start="2019-01-02", min_n=10)
    assert b["horizons"][5]["p_up"] == a["horizons"][5]["p_up"]


def test_recap_counts_sessions_and_flows():
    d = pd.bdate_range("2026-10-01", periods=30)
    hist = pd.DataFrame({"trade_date": d, "vni": np.linspace(1000, 1029, 30), "r_vni_pct": 0.1,
                         "NF_total": [1e9] * 25 + [-1e9] * 5, "tv_total": 1e13, "pct_up": 50.0, "D": 0.1, "CR5": 0.4,
                         "session_type": "broad_up"})
    rc = outlook.recap(hist)
    assert rc[5]["vni_chg"] == pytest.approx(5.0) and rc[5]["up_sessions"] == 5
    assert rc[5]["nf_cum"] == pytest.approx(-5e9) and rc[20]["nf_buy_days"] == 15
    assert rc["tv_ratio"] == pytest.approx(1.0)


def test_h4_detects_level_shift_after_announcement():
    d = pd.bdate_range("2024-06-03", "2026-11-09")
    rng = np.random.default_rng(5)
    post = d >= "2025-10-08"
    day = pd.DataFrame({"trade_date": d, "D": rng.normal(0, 1, len(d)),
                        "CR5": 0.35 + 0.10 * post + rng.normal(0, 0.05, len(d)), "IQR_pct": 1.6, "r_vni_pct": rng.normal(0, 1, len(d)),
                        "tv_total": 2e13, "FPR_total": 0.13, "nf_total_ratio": 0.0, "HHI": 0.05, "session_type": "broad_up"})
    rows = pd.DataFrame(stats_tests.h4(day))
    cr5 = rows[(rows["metric"].str.startswith("CR5")) & rows["test"].str.startswith("OLS")].set_index("window")
    assert cr5.loc["E1 → hiệu lực", "estimate"] == pytest.approx(0.10, abs=0.02)
    assert cr5.loc["E1 → hiệu lực", "p_value"] < 1e-6
    dd = rows[(rows["metric"].str.startswith("D ")) & rows["test"].str.startswith("OLS")]
    assert (dd["p_value"] > 0.01).all()                         # không có dịch chuyển giả
    assert rows["note"].str.contains("MDE").any()
    ps = stats_tests.period_summary(day)
    assert set(ps["period"]) == {"Cơ sở trước E1", "E1 → hiệu lực", "Sau hiệu lực"}
    assert ps[ps["period"] == "Cơ sở trước E1"]["n"].max() == 250
