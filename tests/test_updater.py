"""Kiểm thử cơ chế cập nhật liên tục: khóa chống chạy chồng, khung giờ tác vụ của bộ lập lịch."""
import os
import time

import pytest

from src.data import scheduler, updater


def test_update_lock_blocks_second_run(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "LOCK", tmp_path / ".update.lock")
    with updater.update_lock():
        assert updater.LOCK.exists()
        with pytest.raises(updater.Busy):
            with updater.update_lock():
                pass
    assert not updater.LOCK.exists()                       # luôn gỡ khóa khi xong


def test_stale_lock_is_removed(tmp_path, monkeypatch):
    lock = tmp_path / ".update.lock"
    lock.write_text("pid=1 start=cũ", encoding="utf-8")
    old = time.time() - updater.STALE_LOCK_SEC - 60
    os.utime(lock, (old, old))
    monkeypatch.setattr(updater, "LOCK", lock)
    with updater.update_lock():                           # khóa treo > 3 giờ được gỡ, không chặn
        pass


def test_scheduler_jobs_have_windows_and_retries():
    js = {j.name: j for j in scheduler.jobs()}
    assert {"recorder", "midday", "update", "closing", "update_late"} <= set(js)
    assert "quality" not in js                             # đã nằm trong update (rebuild_all)
    for j in js.values():
        assert j.start <= j.until
    assert js["update"].retry_min > 0 and js["closing"].retry_min > 0
    assert js["midday"].until <= "13:00" and js["recorder"].until <= "15:05"


def test_foreign_gap_session_kept_missing_not_zero():
    import numpy as np
    import pandas as pd
    from src.data.build_facts import foreign_gap_sessions
    from src.finance.foreign_flow import market_flows
    n = 60
    df = pd.DataFrame({"trade_date": ["2026-11-11"] * n + ["2026-11-12"] * n, "symbol": [f"S{i}" for i in range(n)] * 2,
                       "close": 10000.0, "fb": [1e9] * n + [np.nan] * n, "fs": [5e8] * n + [np.nan] * n})
    assert foreign_gap_sessions(df) == ["2026-11-12"]       # 12/11/2026: SSI trả null khối ngoại cho mọi mã
    st = df.assign(is_valid=True, tv=1e10, net_flow=df["fb"] - df["fs"])
    mf = market_flows(st)
    assert mf.loc["2026-11-11", "NF_total"] == pytest.approx(60 * 5e8)
    assert np.isnan(mf.loc["2026-11-12", "NF_total"])       # thiếu → NaN, không phải 0


def test_closing_waits_for_today_session(monkeypatch):
    monkeypatch.setattr(scheduler, "_has_session_today", lambda: False)
    with pytest.raises(scheduler.NotReady):
        scheduler.task_closing()
    assert scheduler.run_job(scheduler.Job("closing", "15:15", "21:00", 30)) is False   # → thử lại, không đánh dấu xong
