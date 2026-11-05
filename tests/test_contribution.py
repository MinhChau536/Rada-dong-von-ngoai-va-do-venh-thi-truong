"""Kiểm thử phân rã đóng góp (4), (5): ΣC = ΔI khi chỉ số tính đúng từ cùng số cổ phiếu; CR5; nhóm loại trừ."""
import numpy as np
import pandas as pd
import pytest

from src.finance.contribution import contributions, group_contrib, leaders


def _setup():
    dt = pd.Timestamp("2026-01-05")
    shares = np.array([100, 200, 300, 50, 80, 60], dtype=float)
    ref = np.array([10, 20, 5, 40, 30, 15], dtype=float)
    ret = np.array([0.02, -0.01, 0.03, 0.0, -0.05, 0.07])
    close = ref * (1 + ret)
    st = pd.DataFrame({"trade_date": dt, "symbol": list("ABCDEF"), "ref": ref, "ret": ret, "is_valid": True,
                       "listed_share": shares, "close": close})
    i_prev = 1000.0
    i_now = i_prev * (shares * close).sum() / (shares * ref).sum()
    idx = pd.DataFrame({"value": [i_now], "prev_value": [i_prev]}, index=[dt])
    return st, idx, i_prev, i_now


def test_sum_C_equals_dI_hand_example():
    st, idx, i_prev, i_now = _setup()
    s, day, meta = contributions(st, idx)
    w_a = 100 * 10 / (100 * 10 + 200 * 20 + 300 * 5 + 50 * 40 + 80 * 30 + 60 * 15)
    assert s.loc[s.symbol == "A", "C"].iloc[0] == pytest.approx(i_prev * w_a * 0.02)
    assert day["sumC"].iloc[0] == pytest.approx(i_now - i_prev)
    assert abs(day["eps"].iloc[0]) < 1e-9
    assert meta["scale_k"] == 1.0


def test_cr5_and_leaders():
    st, idx, *_ = _setup()
    s, day, _ = contributions(st, idx)
    absC = s["C"].abs().sort_values(ascending=False)
    assert day["CR5"].iloc[0] == pytest.approx(absC.head(5).sum() / absC.sum())
    lead = leaders(s, day, n=2)
    assert set(lead["side"]) == {"pos", "neg"}
    assert (lead.groupby("side").size() <= 2).all()
    top_pos = lead[(lead.side == "pos") & (lead["rank"] == 1)]["symbol"].iloc[0]
    assert top_pos == s.loc[s["C"].idxmax(), "symbol"]


def test_index_ex_group():
    st, idx, i_prev, i_now = _setup()
    s, day, _ = contributions(st, idx)
    g = group_contrib(s, pd.Series({"A": "G1", "B": "G1"}), "family", day)
    row = g.iloc[0]
    assert row["index_ex_group"] == pytest.approx(i_prev + day["sumC"].iloc[0] - row["C"])


def test_invalid_and_zero_weights():
    st, idx, *_ = _setup()
    st.loc[0, "is_valid"] = False
    st.loc[1, "listed_share"] = np.nan
    s, day, _ = contributions(st, idx)
    assert s.loc[0, "w"] == 0 and s.loc[1, "w"] == 0
    assert s["w"].sum() == pytest.approx(1.0)


def test_scale_k_applied_when_eps_large():
    st, idx, i_prev, i_now = _setup()
    rows = []
    for k in range(10):                 # 10 phiên, chỉ số thật biến động gấp 1,5 lần ΣC → ε lớn → hiệu chỉnh k ≈ 1,5
        t = st.copy()
        t["trade_date"] = pd.Timestamp("2026-01-05") + pd.Timedelta(days=k)
        rows.append(t)
    st10 = pd.concat(rows)
    dI = (i_now - i_prev) * 1.5
    idx10 = pd.DataFrame({"value": i_prev + dI, "prev_value": i_prev}, index=sorted(st10["trade_date"].unique()))
    s, day, meta = contributions(st10, idx10)
    assert meta["scale_k"] == pytest.approx(1.5, rel=1e-6)
    assert day["eps"].abs().max() < 1e-6
