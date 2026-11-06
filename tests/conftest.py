"""Fixture dùng chung: kho DuckDB tạm với dữ liệu mẫu ngắn (không cần mạng, không cần khóa)."""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_IDS"):
    os.environ.pop(k, None)  # kiểm thử không bao giờ gửi tin thật


@pytest.fixture(scope="session")
def demo_db(tmp_path_factory):
    """Kho TẠM của pytest: dữ liệu giả lập 01/04–30/09/2025 (~125 phiên) chỉ để kiểm thử công thức, không dùng cho ứng dụng."""
    p = tmp_path_factory.mktemp("db") / "test.duckdb"
    cg = ROOT / "config" / "control_group.csv"
    backup = cg.read_bytes() if cg.exists() else None       # fixture không được ghi đè cấu hình thật
    os.environ["FFR_DB_PATH"] = str(p)
    try:
        from src.data import rebuild_all
        from tests.fixtures import synthetic_market
        synthetic_market.generate(end=date(2025, 9, 30), path=p, force=True)
        res = rebuild_all.main(path=p, robustness=False, backtest=True)
        yield p, res
    finally:
        os.environ.pop("FFR_DB_PATH", None)
        if backup is not None:
            cg.write_bytes(backup)
