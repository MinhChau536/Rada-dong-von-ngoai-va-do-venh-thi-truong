"""
Nội dung tin nhắn bot – sinh từ CÙNG ngữ cảnh src/reports/context.py với PDF (số liệu khớp giao diện, bước B12.5).
Mọi tin kết thúc bằng câu miễn trừ. Không có lệnh nào liên quan đặt lệnh.
"""
from __future__ import annotations

from typing import Dict, Optional

import pandas as pd

from src.analytics import watchlist_impact as wi
from src.common import fmt
from src.common.config import get
from src.data import database as db
from src.finance.breadth import session_type_label
from src.reports import context

HELP = ("FTSE Flow Radar – lệnh tra cứu:\n"
        "/market – tóm tắt thị trường\n/leaders – 5 mã đóng góp dương & âm lớn nhất\n"
        "/foreign – khối ngoại: tổng ròng, top mã, HHI, nhóm FTSE\n/watch [mã] – hồ sơ watchlist (hoặc 1 mã)\n"
        "/report – gửi PDF gần nhất\n/status – nguồn dữ liệu, thời điểm, độ đầy đủ\n/help – trợ giúp")


def _demo_tag(ctx: Dict) -> str:
    return "⚠️ DỮ LIỆU MẪU TỔNG HỢP\n" if ctx.get("is_demo") else ""


def market(ctx: Optional[Dict] = None) -> str:
    ctx = ctx or context.build()
    if not ctx:
        return "Chưa có dữ liệu phiên."
    k = context.key_numbers(ctx)
    x = ctx["day"]
    return (f"{_demo_tag(ctx)}📊 Thị trường phiên {ctx['date']:%d/%m/%Y}\n"
            f"VN-Index {k['VN-Index']} ({k['ΔVN-Index']} điểm, {k['r_VNI']})\n"
            f"Trung vị cổ phiếu HOSE: {k['Trung vị']} · D = {k['D']} đ.% · CR5 = {k['CR5']}\n"
            f"Loại phiên: {session_type_label(x['session_type'])} · AD = {k['AD']}\n\n{ctx['summary']}")


def leaders(ctx: Optional[Dict] = None) -> str:
    ctx = ctx or context.build()
    if not ctx:
        return "Chưa có dữ liệu phiên."
    lead = ctx["leaders"]
    pos = "\n".join(f"  {r.symbol}: {fmt.num(r.C, 2, True)} điểm" for r in lead[lead["side"] == "pos"].head(5).itertuples())
    neg = "\n".join(f"  {r.symbol}: {fmt.num(r.C, 2, True)} điểm" for r in lead[lead["side"] == "neg"].head(5).itertuples())
    k = context.key_numbers(ctx)
    return (f"{_demo_tag(ctx)}🏁 Mã dẫn dắt VN-Index {ctx['date']:%d/%m/%Y} (ΔI = {k['ΔVN-Index']}, ε = {k['ε']})\n"
            f"Kéo lên:\n{pos}\nKéo xuống:\n{neg}\nCR5 = {k['CR5']}")


def foreign(ctx: Optional[Dict] = None) -> str:
    ctx = ctx or context.build()
    if not ctx:
        return "Chưa có dữ liệu phiên."
    g = ctx["groups"]
    ftse = g[(g["group_type"] == "universe") & (g["group_name"] == "FTSE")]
    f = f"\nNhóm FTSE: {fmt.bn(ftse['net_flow'].iloc[0])} (nf {fmt.num(ftse['nf'].iloc[0], 3, True)})" if not ftse.empty else ""
    return f"{_demo_tag(ctx)}🌏 Khối ngoại {ctx['date']:%d/%m/%Y}\n{ctx['foreign']}{f}"


def watch(symbol: Optional[str] = None, ctx: Optional[Dict] = None) -> str:
    ctx = ctx or context.build()
    if not ctx:
        return "Chưa có dữ liệu phiên."
    pf = ctx["watch"]
    if symbol:
        s = symbol.upper().strip()
        if pf is None or s not in set(pf["symbol"]):
            hist = db.query_df("SELECT * FROM indicator_stock_daily WHERE symbol = ? AND trade_date <= ?", [s, ctx["date"]])
            if hist.empty:
                return f"{s}: không có dữ liệu (mã không thuộc HOSE hoặc tạm ngừng)."
            pf = wi.compute(pd.concat([hist, ctx["stock"]]).drop_duplicates(["trade_date", "symbol"]), ctx["hist"],
                            None, [s], ctx["date"])["profile"]
        pf = pf[pf["symbol"] == s]
    lines = [r.sentence for r in pf.itertuples()] if pf is not None else []
    return f"{_demo_tag(ctx)}👁 Watchlist {ctx['date']:%d/%m/%Y}\n" + "\n".join(f"• {x}" for x in lines)


def status() -> str:
    st = db.query_df("SELECT * FROM source_status")
    q = db.query_df("SELECT trade_date, value FROM data_quality_log WHERE check_name = 'completeness' "
                    "ORDER BY trade_date DESC LIMIT 1")
    ev = db.query_df("SELECT * FROM source_events ORDER BY ts DESC LIMIT 1")
    src = "NEO (dự phòng)" if not ev.empty and ev["to_source"].iloc[0] == "NEO" else "SSI"
    lines = [f"🛰 Nguồn đang dùng: {src}"]
    for r in st.itertuples():
        lines.append(f"{r.source}: {r.status} · cập nhật {pd.Timestamp(r.updated_at):%H:%M %d/%m}")
    if not q.empty:
        lines.append(f"Độ đầy đủ phiên {pd.Timestamp(q['trade_date'].iloc[0]):%d/%m/%Y}: {fmt.frac_pct(q['value'].iloc[0], 1)}")
    return "\n".join(lines)


def latest_report() -> Optional[str]:
    r = db.query_df("SELECT path FROM reports_log WHERE status = 'ok' AND path IS NOT NULL ORDER BY created_at DESC LIMIT 1")
    return None if r.empty else str(r["path"].iloc[0])
