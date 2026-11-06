"""Kiểm thử Module A – công thức (1), (2), (3) và phân loại phiên (B3.9) bằng ví dụ tính tay."""
import numpy as np
import pandas as pd
import pytest

from src.finance.breadth import add_validity, breadth_check, breadth_summary, classify_session, daily_breadth


def _stock(rows):
    return pd.DataFrame(rows, columns=["trade_date", "symbol", "ref", "close", "ceiling", "floor", "tv"])


def test_return_formula_and_validity():
    d = _stock([("2026-01-02", "AAA", 10000, 10500, 10700, 9300, 1e9),
                ("2026-01-02", "BBB", 20000, 20000, 21400, 18600, 0),       # không khớp lệnh → loại khỏi Ω
                ("2026-01-02", "CCC", 0, 5000, 0, 0, 1e9),                  # P_ref = 0 → loại
                ("2026-01-02", "DDD", 10000, 10700, 10700, 9300, 2e9),      # kịch trần
                ("2026-01-02", "CFPT2401", 1000, 1100, 1500, 500, 1e9),     # chứng quyền → loại
                ("2026-01-02", "FUEVFVND", 30000, 30500, 32100, 27900, 1e9)])  # chứng chỉ quỹ ETF → loại
    v = add_validity(d)
    assert v.loc[0, "ret"] == pytest.approx(0.05)
    assert list(v["is_valid"]) == [True, False, False, True, False, False]
    assert bool(v.loc[3, "is_ceiling"]) and not bool(v.loc[0, "is_ceiling"])
    assert np.isnan(v.loc[2, "ret"])                                       # chia cho 0 → NaN, không lỗi
    # SecType từ API được ưu tiên hơn quy ước mã ("ST" theo đặc tả, "S" theo phản hồi mẫu SSI)
    v2 = add_validity(d, sec_type=pd.Series({"AAA": "S", "DDD": "E"}))
    assert list(v2["is_valid"])[:4] == [True, False, False, False]


def test_D_AD_IQR_hand_example():
    # 5 mã: lợi suất 3%, 1%, 0%, −1%, −2% → trung vị 0%; VN-Index +1,5% → D = 1,5 đ.%
    rets = [0.03, 0.01, 0.0, -0.01, -0.02]
    d = pd.DataFrame({"trade_date": pd.Timestamp("2026-01-02"), "symbol": list("ABCDE"), "ret": rets,
                      "is_valid": True, "is_ceiling": False, "is_floor": False, "tv": 1e9})
    out = daily_breadth(d, pd.Series({pd.Timestamp("2026-01-02"): 0.015})).iloc[0]
    assert out["median_ret_pct"] == pytest.approx(0.0)
    assert out["D"] == pytest.approx(1.5)
    assert out["AD"] == pytest.approx((2 - 2) / 5)
    assert out["IQR_pct"] == pytest.approx((0.01 - (-0.01)) * 100)
    assert out["session_type"] == "narrow_up"         # chỉ số tăng nhưng AD không dương
    assert int(out["n_unch"]) == 1


@pytest.mark.parametrize("r,ad,exp", [(0.5, 0.3, "broad_up"), (0.5, 0.0, "narrow_up"), (-0.5, 0.0, "narrow_down"),
                                      (-0.5, -0.2, "broad_down"), (0.05, 0.9, "flat"), (-0.09, -0.9, "flat"),
                                      (float("nan"), 0.1, "flat")])
def test_classify_session(r, ad, exp):
    assert classify_session(r, ad, 0.1) == exp


def test_single_stock_and_breadth_summary_empty():
    d = pd.DataFrame({"trade_date": pd.Timestamp("2026-01-02"), "symbol": ["A"], "ret": [0.02], "is_valid": True,
                      "is_ceiling": False, "is_floor": False, "tv": 1.0})
    out = daily_breadth(d, pd.Series({pd.Timestamp("2026-01-02"): 0.02})).iloc[0]
    assert out["D"] == pytest.approx(0.0) and out["AD"] == 1.0
    assert breadth_summary(pd.DataFrame())["available"] is False


def test_breadth_check_diff():
    mine = pd.DataFrame({"n_up": [10], "n_down": [5], "n_unch": [2]}, index=[pd.Timestamp("2026-01-02")])
    ssi = pd.DataFrame({"trade_date": [pd.Timestamp("2026-01-02")], "advances": [11], "declines": [5], "no_changes": [2]})
    r = breadth_check(mine, ssi).iloc[0]
    assert r["diff_up"] == -1 and r["max_abs_diff"] == 1
