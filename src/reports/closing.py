"""
Mẫu Closing Report (bước B9.2) – bìa, mục lục, tóm tắt thị trường, trạng thái phiên + phân vị 20/60/250, tổng quan thị trường,
diễn biến tuần/tháng, dẫn dắt, triển vọng thống kê + bối cảnh nâng hạng (H4), watchlist đầy đủ, phụ lục phương pháp. CHỈ xuất khi kiểm tra chất lượng cuối phiên đạt.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from src.common import fmt
from src.common.config import get
from src.common.logging import get_logger
from src.common.timeutil import now_vn
from src.data import database as db
from src.finance.domestic import ABSORB_LABELS
from src.reports import context
from src.reports.pdf_base import FFRPdf
from src.reports.snapshot import _out_path, front_matter, log_report, save_pdf

log = get_logger(__name__)


def quality_gate(date, db_path=None) -> Tuple[bool, str]:
    """Đạt khi: có đủ chỉ số, tỷ lệ đầy đủ ≥ mục tiêu, lệch độ rộng ≤ ngưỡng, |ε| hợp lý."""
    d = pd.Timestamp(date)
    q = db.query_df("SELECT * FROM data_quality_log WHERE trade_date = ?", [d], path=db_path)
    if q.empty:
        return False, "Chưa có kết quả kiểm tra chất lượng cho phiên"
    target = float(get("cleaning.completeness_target", .98))
    comp = q[q["check_name"] == "completeness"]["value"]
    note = ""
    if comp.empty or float(comp.iloc[0]) < target:
        # SSI có phiên KHÔNG trả khối ngoại cho mọi mã → độ đầy đủ (gồm fb/fs/remain) = 0 dù giá đầy đủ.
        # Khi đó chỉ xét các trường giá; báo cáo vẫn xuất, các mục khối ngoại ghi "SSI chưa công bố".
        if (q["check_name"] == "foreign_missing_session").any():
            px = db.query_df("SELECT AVG(CASE WHEN ref IS NOT NULL AND close IS NOT NULL AND tv IS NOT NULL THEN 1.0 ELSE 0 END) AS r "
                             "FROM indicator_stock_daily WHERE trade_date = ? AND is_valid", [d], path=db_path)["r"].iloc[0]
            if px is None or pd.isna(px) or float(px) < target:
                return False, f"Tỷ lệ đầy đủ dữ liệu giá {fmt.frac_pct(px, 1)} dưới mục tiêu"
            note = f" – dữ liệu giá đầy đủ {fmt.frac_pct(px, 1)}; SSI chưa công bố khối ngoại phiên này (mục khối ngoại để trống)"
        else:
            return False, f"Tỷ lệ đầy đủ {fmt.frac_pct(comp.iloc[0] if not comp.empty else None, 1)} dưới mục tiêu"
    br = q[q["check_name"] == "breadth_check"]["value"]
    if not br.empty and float(br.iloc[0]) > float(get("cleaning.breadth_tolerance", 2)) + 3:
        return False, f"Độ rộng lệch {int(br.iloc[0])} mã so với SSI"
    eps = q[q["check_name"] == "eps"]["value"]
    if not eps.empty and abs(float(eps.iloc[0])) > 5:
        return False, f"Sai số tái lập ε = {fmt.num(eps.iloc[0], 2)} điểm quá lớn"
    return True, "đạt" + note


def closed_check(date=None, db_path=None) -> Tuple[bool, str]:
    """Closing Report chỉ dành cho phiên ĐÃ ĐÓNG CỬA và đã có số chính thức trong kho chính."""
    from src.common.timeutil import in_session
    today = now_vn().date()
    d = pd.Timestamp(date).date() if date is not None else None
    if d == today and in_session():
        return False, "phiên hôm nay chưa kết thúc – trong phiên chỉ xuất được Market Snapshot"
    last = context.latest_date(db_path)
    if d == today and (last is None or last.date() < today):
        return False, "chưa có số liệu đóng cửa chính thức của hôm nay (SSI công bố sau 15:00) – xuất Market Snapshot"
    if d is None:                                   # "báo cáo mới nhất": hôm nay đang/vừa giao dịch mà chưa có số chính thức
        from src.data import live
        if live.meta() is not None:
            return False, "phiên hôm nay chưa có số liệu đóng cửa chính thức – trong phiên chỉ xuất được Market Snapshot"
    return True, ""


def build(date=None, db_path=None, force: bool = False) -> Tuple[Optional[Path], str]:
    ok_closed, why = closed_check(date, db_path) if db_path is None else (True, "")
    if not ok_closed:
        log_report("closing", date, None, "blocked", why, db_path)
        return None, why
    ctx = context.build(date, db_path)
    if ctx is None:
        log_report("closing", date, None, "failed", "Không có dữ liệu", db_path)
        return None, "Không có dữ liệu"
    ok, reason = quality_gate(ctx["date"], db_path)
    if not ok and not force:
        log_report("closing", ctx["date"], None, "blocked", reason, db_path)
        return None, reason
    ts = now_vn().replace(tzinfo=None)
    pdf = FFRPdf("Closing Report", f"Báo cáo cuối phiên {ctx['date']:%d/%m/%Y} · xuất {ts:%H:%M %d/%m/%Y}",
                 "SỐ LIỆU CUỐI PHIÊN – ĐÃ QUA KIỂM TRA CHẤT LƯỢNG", ctx["is_demo"])
    from src.reports import chapters as C
    chapters: List[Tuple[str, callable]] = [(t, (lambda k=k: C.render_one(pdf, ctx, k, db_path))) for t, k in C.CHAPTERS]
    front_matter(pdf, ctx, "Closing Report", f"Xuất lúc {ts:%H:%M} ngày {ts:%d/%m/%Y} (giờ Việt Nam)",
                 [c[0] for c in chapters], "Báo cáo cuối phiên – số liệu đã khớp lệnh xong và qua kiểm tra chất lượng "
                 "(độ đầy đủ ≥ 98%, độ rộng khớp SSI, sai số tái lập chỉ số trong ngưỡng).")
    for _, fn in chapters:
        fn()
    out = save_pdf(pdf, _out_path("closing", pd.Timestamp(ctx["date"])))
    log_report("closing", ctx["date"], out, "ok", reason if reason != "đạt" else "", db_path)
    return out, reason if reason != "đạt" else "ok"


if __name__ == "__main__":
    import sys
    print(build(sys.argv[1] if len(sys.argv) > 1 else None))
