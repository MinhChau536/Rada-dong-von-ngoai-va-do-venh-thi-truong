"""
Cơ chế chuyển nguồn SSI ↔ NEO (bước B1.5, mục 6.2).

- SSI lỗi 3 lần liên tiếp HOẶC luồng streaming im lặng > 120 giây trong phiên → chuyển NEO, gắn source='NEO'.
- SSI ổn định liên tục 5 phút → quay lại SSI.
- Mỗi lần chuyển ghi bảng source_events; trạng thái nguồn ghi source_status (giao diện, PDF, Telegram đọc lại).
Đồng hồ được truyền vào (clock) để kiểm thử giả lập không cần chờ thật.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from src.common.config import get
from src.common.logging import get_logger
from src.common.timeutil import in_session, now_vn
from src.data import database as db

log = get_logger(__name__)


class FailoverController:
    def __init__(self, clock: Callable[[], datetime] = lambda: now_vn().replace(tzinfo=None),
                 session_check: Callable[[datetime], bool] = in_session, path: Optional[Path] = None,
                 on_switch: Optional[Callable[[str, str, str], None]] = None):
        self.clock = clock
        self.session_check = session_check
        self.path = path
        self.on_switch = on_switch
        self.active = "SSI"
        self.fail_count = 0
        self.last_ssi_msg: Optional[datetime] = clock()
        self.ssi_ok_since: Optional[datetime] = None
        self.max_fail = int(get("failover.ssi_fail_count", 3))
        self.silence = timedelta(seconds=int(get("failover.silence_sec", 120)))
        self.stable = timedelta(minutes=int(get("failover.recover_stable_min", 5)))

    def _switch(self, to: str, reason: str) -> None:
        frm, self.active = self.active, to
        ts = self.clock()
        db.append("source_events", pd.DataFrame([{"ts": ts, "from_source": frm, "to_source": to, "reason": reason}]), self.path)
        db.set_source_status("SSI", "ok" if to == "SSI" else "error", reason, ok=(to == "SSI"), path=self.path)
        log.warning("Chuyển nguồn %s → %s: %s", frm, to, reason)
        if self.on_switch:
            self.on_switch(frm, to, reason)

    def ssi_error(self, msg: str = "") -> None:
        self.fail_count += 1
        self.ssi_ok_since = None
        if self.active == "SSI" and self.fail_count >= self.max_fail:
            self._switch("NEO", f"SSI lỗi {self.fail_count} lần liên tiếp: {msg}"[:200])

    def ssi_ok(self) -> None:
        now = self.clock()
        self.fail_count = 0
        self.last_ssi_msg = now
        if self.ssi_ok_since is None:
            self.ssi_ok_since = now
        if self.active == "NEO" and now - self.ssi_ok_since >= self.stable:
            self._switch("SSI", f"SSI ổn định {int(self.stable.total_seconds() // 60)} phút")

    def tick(self) -> str:
        """Gọi định kỳ: phát hiện luồng SSI im lặng trong phiên."""
        now = self.clock()
        if self.active == "SSI" and self.session_check(now) and self.last_ssi_msg is not None \
                and now - self.last_ssi_msg > self.silence:
            self.ssi_ok_since = None
            self._switch("NEO", f"Luồng SSI im lặng {int((now - self.last_ssi_msg).total_seconds())} giây trong phiên")
        return self.active

    @property
    def source_label(self) -> str:
        return self.active
