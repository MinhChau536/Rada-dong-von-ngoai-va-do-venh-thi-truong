"""B12.2 – Không nhìn trước: thay đổi dữ liệu phiên t và sau t không làm đổi ngưỡng/z/phân vị dùng cho phiên t."""
import numpy as np
import pandas as pd
import pytest

from src.finance.utils import rolling_past_quantile, rolling_pct_rank, rolling_z, winsorize


@pytest.fixture
def series():
    rng = np.random.default_rng(42)
    return pd.Series(rng.normal(size=300))


def test_z_ignores_future(series):
    t = 200
    z1 = rolling_z(series, 60).iloc[t]
    s2 = series.copy()
    s2.iloc[t + 1:] = 1e6                       # phá hủy tương lai
    assert rolling_z(s2, 60).iloc[t] == pytest.approx(z1)


def test_threshold_ignores_current_value(series):
    t = 260
    thr1 = rolling_past_quantile(series, 250, 0.9).iloc[t]
    s2 = series.copy()
    s2.iloc[t] = 999                            # đổi giá trị phiên t → ngưỡng của phiên t không đổi
    assert rolling_past_quantile(s2, 250, 0.9).iloc[t] == pytest.approx(thr1)


def test_pct_rank_uses_only_past(series):
    t = 150
    p1 = rolling_pct_rank(series, 60).iloc[t]
    s2 = series.copy()
    s2.iloc[t + 1:] = -1e6
    assert rolling_pct_rank(s2, 60).iloc[t] == pytest.approx(p1)
    past = series.iloc[t - 60:t]
    assert p1 == pytest.approx(((past < series.iloc[t]).sum() + 0.5 * (past == series.iloc[t]).sum()) / 60 * 100)


def test_z_hand_value():
    s = pd.Series([1.0, 2, 3, 4, 5, 10])
    z = rolling_z(s, 5, min_periods=5).iloc[5]
    past = s.iloc[:5]
    assert z == pytest.approx((10 - past.mean()) / past.std(ddof=1))


def test_event_params_ignore_post_event():
    """Tham số α, β ước lượng trên [−130; −11] không phụ thuộc lợi suất trong cửa sổ sự kiện."""
    from tests.test_event_study import make_panel
    from src.analytics.event_study import EventStudy
    st, day, pos = make_panel(effect=0.0)
    r1 = EventStudy(st, day).run_symbol("S0", pos)
    st2 = st.copy()
    dates = np.sort(st2["trade_date"].unique())
    st2.loc[st2["trade_date"] >= dates[pos - 5], "ret"] += 0.5
    r2 = EventStudy(st2, day).run_symbol("S0", pos)
    assert r1["beta"] == pytest.approx(r2["beta"]) and r1["alpha"] == pytest.approx(r2["alpha"])


def test_winsorize():
    s = pd.Series(list(range(100)) + [10_000])
    w = winsorize(s, 0.01, 0.99)
    assert w.max() < 10_000 and w.min() >= 0
