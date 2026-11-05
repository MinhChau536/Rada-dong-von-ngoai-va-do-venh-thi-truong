"""
Bản tin & cảnh báo theo lịch (bước B10.3): 11:35 bản tin giữa phiên + Snapshot; 15:15 bản tin cuối phiên + Closing;
cảnh báo từ alerts.dispatch() (cooldown, giới hạn ngày); báo sự cố dữ liệu.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from src.analytics import alerts
from src.bot import messages as M
from src.bot.telegram_api import send_document, send_message
from src.common.logging import get_logger
from src.common.timeutil import now_vn
from src.reports import closing, context, snapshot

log = get_logger(__name__)


def midday_brief() -> Dict:
    ctx = context.build()
    txt = "🕦 Bản tin giữa phiên\n" + M.market(ctx)
    pdf = snapshot.build()
    ok = send_message(txt)
    if pdf:
        send_document(pdf, "Market Snapshot – số liệu trong phiên, chưa hoàn tất")
    return {"sent": ok, "pdf": str(pdf) if pdf else None}


def closing_brief() -> Dict:
    pdf, reason = closing.build()
    ctx = context.build()
    txt = "🔔 Bản tin cuối phiên\n" + M.market(ctx) + "\n\n" + M.foreign(ctx)
    if pdf is None:
        txt += f"\n\n⚠️ Chưa xuất Closing Report: {reason}"
    ok = send_message(txt)
    if pdf:
        send_document(pdf, "Closing Report")
    return {"sent": ok, "pdf": str(pdf) if pdf else None, "reason": reason}


def run_alerts(system: Optional[Dict] = None, now: Optional[datetime] = None) -> int:
    ctx = alerts.context_for(context.latest_date())
    if ctx is None:
        return 0
    al = alerts.evaluate(ctx["day"], ctx["leaders"], ctx["flow"], ctx["wl"], system)
    out = alerts.dispatch(al, (now or now_vn()).replace(tzinfo=None), mode="live", sender=send_message)
    return int((out["status"] == "sent").sum()) if not out.empty else 0


def data_incident(message: str) -> None:
    send_message(f"🛠 Sự cố dữ liệu: {message}")
