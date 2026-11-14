"""
Bản tin & cảnh báo theo lịch (bước B10.3): 11:35 bản tin giữa phiên + Snapshot; 15:15 bản tin cuối phiên + Closing;
cảnh báo từ alerts.dispatch() (cooldown, giới hạn ngày); báo sự cố dữ liệu.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

import pandas as pd
from src.analytics import alerts
from src.bot import messages as M
from src.bot.telegram_api import send_document, send_message
from src.common.logging import get_logger
from src.common.timeutil import now_vn
from src.reports import closing, context, snapshot
from src.data import database as db

log = get_logger(__name__)


def midday_brief() -> Dict:
    ctx = context.build()
    txt, kb = M.market(ctx, with_buttons=True)
    pdf = snapshot.build()
    ok = send_message("🕦 <b>BẢN TIN GIỮA PHIÊN</b>\n\n" + txt, html=True, keyboard=kb)
    if pdf:
        send_document(pdf, "Market Snapshot – số liệu trong phiên, chưa hoàn tất")
    return {"sent": ok, "pdf": str(pdf) if pdf else None}


def closing_brief() -> Dict:
    from html import escape
    pdf, reason = closing.build()
    ctx = context.build()
    txt, kb = M.market(ctx, with_buttons=True)
    ok = send_message("🔔 <b>BẢN TIN CUỐI PHIÊN</b>\n\n" + txt, html=True, keyboard=kb)
    send_message(M.foreign(ctx) + "\n\n" + M.outlook(ctx), html=True, keyboard=M.MENU)
    if pdf is None:
        send_message(f"⚠️ Chưa xuất Closing Report: {escape(reason)}", html=True)
    else:
        send_document(pdf, "Closing Report")
    return {"sent": ok, "pdf": str(pdf) if pdf else None, "reason": reason}


def run_alerts(system: Optional[Dict] = None, now: Optional[datetime] = None) -> int:
    ctx = alerts.context_for(context.latest_date())
    if ctx is None:
        return 0
    if system is None:                                       # trạng thái nguồn SSI do bộ ghi/backfill cập nhật
        st = db.query_df("SELECT status, message, last_error FROM source_status WHERE source = 'SSI'")
        if not st.empty and st["status"].iloc[0] in ("error", "degraded"):
            le = st["last_error"].iloc[0]
            system = {"status": st["status"].iloc[0], "message": st["message"].iloc[0],
                      "since": "?" if le is None or pd.isna(le) else f"{pd.Timestamp(le):%H:%M}"}
    al = alerts.evaluate(ctx["day"], ctx["leaders"], ctx["flow"], ctx["wl"], system)
    out = alerts.dispatch(al, (now or now_vn()).replace(tzinfo=None), mode="live", sender=send_message)
    return int((out["status"] == "sent").sum()) if not out.empty else 0


def data_incident(message: str) -> None:
    send_message(f"🛠 Sự cố dữ liệu: {message}")
