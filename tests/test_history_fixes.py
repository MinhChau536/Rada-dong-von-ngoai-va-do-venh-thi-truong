"""Kiểm thử các sửa lỗi khi mở rộng lịch sử về 2016 (giá điều chỉnh phiên cũ, sàn niêm yết theo ngày, mã hủy niêm yết,
BMP điều chỉnh tương quan chéo, H1a giới hạn nhóm trước mốc, backtest dự báo)."""
import numpy as np
import pandas as pd
import pytest

from src.analytics.event_study import car_tests, mean_cross_corr
from src.finance.breadth import add_validity


def test_enrich_stock_old_session_without_price_change():
    from src.ssi_api.ssi_client import enrich_stock
    # FPT 15/06/2018 (phản hồi thật): priceChange = null, pct = −0,20; close đã điều chỉnh 12 867,378
    r = enrich_stock({"close": "12867.378", "priceChange": None, "priceChangePercentage": "-0.20"},
                     {"refPrice": 40700, "ceiling": 43500, "floor": 37900, "board": "HOSE"})
    assert float(r["close"]) / r["refPrice"] - 1 == pytest.approx(-0.002, abs=1e-6)
    assert r["floor"] < float(r["close"]) < r["ceiling"] and r["board"] == "HOSE"
    # chưa điều chỉnh + pct làm tròn → k = 1 đúng, trần khớp tuyệt đối
    r2 = enrich_stock({"close": "53900", "priceChange": None, "priceChangePercentage": "6.94"},
                      {"refPrice": 50400, "ceiling": 53900, "floor": 46900, "board": "HOSE"})
    assert r2["adjFactor"] == 1.0 and float(r2["close"]) >= r2["ceiling"]


def test_enrich_stock_small_cumulative_factor():
    from src.ssi_api.ssi_client import enrich_stock
    # HPG 15/06/2017 (phản hồi thật): close điều chỉnh 5 130,536, ref gốc 31 700, pct +2,20 → k ≈ 0,158 (< 0,2 cũ)
    r = enrich_stock({"close": "5130.536", "priceChange": None, "priceChangePercentage": "2.20"},
                     {"refPrice": 31700, "ceiling": 33850, "floor": 29450, "board": "HOSE"})
    assert 0.15 < r["adjFactor"] < 0.17
    assert float(r["close"]) / r["refPrice"] - 1 == pytest.approx(0.022, abs=1e-6)
    assert r["floor"] < float(r["close"]) < r["ceiling"]


def test_reenrich_repairs_stored_payload():
    from src.ssi_api.ssi_client import reenrich_stock
    # payload lưu bằng bản cũ: adjFactor = 1, refPrice còn ở thang giá gốc
    old = {"symbol": "HPG", "close": "5130.536", "priceChange": None, "priceChangePercentage": "2.20",
           "board": "HOSE", "ceiling": 33850.0, "floor": 29450.0, "refPrice": 31700.0, "adjFactor": 1.0}
    r = reenrich_stock(old)
    assert float(r["close"]) / r["refPrice"] - 1 == pytest.approx(0.022, abs=1e-6)
    # payload đã đúng → tính lại không đổi (bất biến)
    ok = {"symbol": "HPG", "close": "19899.782", "priceChange": "350", "priceChangePercentage": "1.33", "board": "HOSE",
          "ceiling": 20978.462, "floor": 18300.36, "refPrice": 19639.411, "adjFactor": 0.74391708}
    r2 = reenrich_stock(ok)
    assert r2["refPrice"] == pytest.approx(ok["refPrice"], abs=0.01) and r2["adjFactor"] == pytest.approx(ok["adjFactor"])
    assert r2["ceiling"] == pytest.approx(ok["ceiling"], abs=0.01)


def test_fill_ref_from_prev_close_when_no_change_fields():
    from src.data.build_facts import fill_ref_from_prev_close
    # ROS 13–14/06/2017 (phản hồi thật): không có priceChange/%; ref gốc 112 700 → 120 500, close đã điều chỉnh
    df = pd.DataFrame({"symbol": "ROS", "trade_date": ["2017-06-13", "2017-06-14"], "_no_chg": [True, True],
                       "ref": [112700.0, 120500.0], "ceiling": [120500.0, 128900.0], "floor": [104900.0, 112100.0],
                       "close": [91285.14, 84921.695]})
    assert fill_ref_from_prev_close(df) == 1                   # phiên đầu không có phiên trước → giữ nguyên
    row = df.iloc[1]
    assert row["ref"] == pytest.approx(91285.14)
    assert row["close"] / row["ref"] - 1 == pytest.approx(84921.695 / 91285.14 - 1)
    assert row["floor"] == pytest.approx(row["close"], abs=0.01)   # ROS giảm sàn phiên 14/06/2017
    assert row["close"] < row["ceiling"]


def test_off_board_sessions_excluded_from_hose_universe():
    d = pd.DataFrame({"trade_date": "2024-03-01", "symbol": ["AAA", "VTP", "BBB"], "ref": [10000.0] * 3,
                      "close": [10100.0, 11500.0, 9900.0], "ceiling": [10700.0, np.nan, 10700.0],
                      "floor": [9300.0, np.nan, 9300.0], "tv": [1e9] * 3, "board": ["HOSE", "UPCOM", None]})
    v = add_validity(d)
    assert list(v["is_valid"]) == [True, False, True]        # mã đang ở UPCOM bị loại; thiếu sàn → giữ theo mã
    assert not add_validity(d, board=None)["is_valid"].eq(False).any()


def test_value_reported_in_million_vnd_is_rescaled():
    from src.data.build_facts import fix_value_units
    # VNM 13/09/2018 (phản hồi thật): totalMatch 655 170 cp, totalMatchValue 86 474 (triệu đồng)
    df = pd.DataFrame({"vol": [655170.0, 1342390.0], "tv": [86474.0, 179606770000.0],
                       "fb_vol": [0.0, 1.0], "fb": [0.0, 1.0e5]})
    assert fix_value_units(df) == 1
    assert df["tv"].iloc[0] == pytest.approx(86_474e6) and df["tv"].iloc[1] == pytest.approx(179_606_770_000)


def test_zero_close_is_not_valid():
    # SSI V3 trả close = 0 ở một số phiên 01/2020 → không được tính là r = −100%
    d = pd.DataFrame({"trade_date": "2020-01-10", "symbol": ["AGF", "BBB"], "ref": [4210.0, 10000.0],
                      "close": [0.0, 10100.0], "ceiling": [4500.0, 10700.0], "floor": [3920.0, 9300.0],
                      "tv": [1e8, 1e9]})
    assert list(add_validity(d)["is_valid"]) == [False, True]


def test_ceiling_tolerance_on_adjusted_scale():
    d = pd.DataFrame({"trade_date": "2018-01-02", "symbol": ["AAA"], "ref": [10000.0], "close": [10699.0],
                      "ceiling": [10700.5], "floor": [9300.0], "tv": [1e9]})
    assert bool(add_validity(d)["is_ceiling"].iat[0])        # lệch 0,014% do làm tròn → vẫn là trần


def test_estimate_shares_from_room():
    from src.data.build_facts import estimate_shares_from_room
    df = pd.DataFrame({"symbol": ["VCB", "VCB", "FLC"], "room_api": [300.0, 330.0, 49.0],
                       "listed_share": [1000.0, 1100.0, np.nan]})
    est = estimate_shares_from_room(df)
    assert est.iloc[0] == pytest.approx(1000) and est.iloc[1] == pytest.approx(1100)   # giới hạn 30% của chính mã
    assert est.iloc[2] == pytest.approx(100)                                             # mã hủy niêm yết: 49%


def test_kolari_pynnonen_shrinks_bmp_under_cross_correlation():
    rng = np.random.default_rng(1)
    idx = pd.RangeIndex(120)
    common = rng.normal(0, 1, 120)
    res = [{"symbol": f"S{i}", "resid": pd.Series(0.7 * common + 0.7 * rng.normal(0, 1, 120), index=idx)} for i in range(20)]
    rbar = mean_cross_corr(res)
    assert 0.3 < rbar < 0.7
    cars = rng.normal(0.01, 0.01, 20)
    out = {t["test"]: t for t in car_tests(cars, cars / 0.01, np.full(20, 0.5), 200, rbar)}
    assert abs(out["BMP điều chỉnh Kolari–Pynnönen"]["statistic"]) < abs(out["BMP"]["statistic"])
    assert out["BMP điều chỉnh Kolari–Pynnönen"]["p_value"] > out["BMP"]["p_value"]


def test_h1a_limits_pre_period():
    from src.analytics.stats_tests import h1a
    dates = pd.bdate_range("2025-01-01", "2026-11-06")
    day = pd.DataFrame({"trade_date": dates, "session_type": "broad_up", "D": np.linspace(-1, 1, len(dates))})
    n_post = int((dates >= "2026-09-21").sum())
    assert h1a(day, pre_sessions=100)[0]["n"] == 100 + n_post
    assert h1a(day, pre_sessions=0)[0]["n"] == len(dates)


def test_predictive_backtest_runs(demo_db):
    from src.analytics import alerts
    p, _ = demo_db
    out = alerts.predictive(path=p, write_note=False)
    assert not out.empty and {"rule", "horizon", "n_signal"} <= set(out.columns)
