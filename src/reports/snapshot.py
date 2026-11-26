"""
Mẫu Market Snapshot (bước B9.1) – ảnh chụp TRONG PHIÊN: bìa, mục lục, tóm tắt thị trường, chỉ số & thanh khoản,
dẫn dắt, ngành, khối ngoại, biên dao động thống kê, watchlist. Dòng "số liệu trong phiên, chưa hoàn tất", giờ chụp, nguồn.
Tên tệp FFR_snapshot_yyyymmdd_hhmm.pdf.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from src.common.config import abs_path, get
from src.common.logging import get_logger
from src.common.timeutil import now_vn
from src.data import database as db
from src.reports import context
from src.reports.pdf_base import FFRPdf

log = get_logger(__name__)


def _out_path(kind: str, ts: datetime) -> Path:
    d = abs_path(get("paths.reports_dir", "reports_out"))
    d.mkdir(parents=True, exist_ok=True)
    stamp = ts.strftime("%Y%m%d_%H%M") if kind == "snapshot" else ts.strftime("%Y%m%d")
    return d / f"FFR_{kind}_{stamp}.pdf"


def save_pdf(pdf: FFRPdf, out: Path) -> Path:
    """Ghi PDF; nếu tệp cùng tên đang mở trong trình xem (Windows khóa tệp) thì lưu sang tên có hậu tố giờ phút giây."""
    try:
        pdf.output(str(out))
        return out
    except PermissionError:
        alt = out.with_name(f"{out.stem}_{now_vn():%H%M%S}{out.suffix}")
        log.warning("Tệp %s đang mở ở chương trình khác – lưu thành %s", out.name, alt.name)
        pdf.output(str(alt))
        return alt


def log_report(kind: str, date, path_: Optional[Path], status: str, note: str = "", db_path=None) -> None:
    db.append("reports_log", pd.DataFrame([{"created_at": now_vn().replace(tzinfo=None), "kind": kind,
                                             "trade_date": pd.Timestamp(date).date() if date is not None else None,
                                             "path": str(path_) if path_ else None, "status": status, "note": note}]), db_path)


WEEKDAYS = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]


def front_matter(pdf: FFRPdf, ctx: Dict, kind: str, stamp: str, contents: List[str], scope: str) -> None:
    """Trang bìa + trang mục lục (dùng chung cho hai mẫu báo cáo)."""
    from src.reports.sections import index_cards
    d = ctx["date"]
    from src.reports.chapters import session_conclusion
    pdf.cover(kind, f"Phiên {WEEKDAYS[d.weekday()]}, {d:%d/%m/%Y}", stamp, index_cards(ctx), contents,
              f"Nguồn dữ liệu: SSI FastConnect V3 (REST + WebSocket). {get('app.disclaimer')}", headline=session_conclusion(ctx))
    x = ctx["day"]
    pdf.toc_page([
        ("Phạm vi", scope),
        ("Nguồn dữ liệu", "SSI FastConnect V3 – securitiesSummary, indexSummary, OHLC, khối ngoại theo mã. Giờ Việt Nam."),
        ("Mẫu phân tích", f"{int(x['n_valid'])} cổ phiếu thường HOSE có giao dịch trong phiên; ngành theo phân loại của hệ thống."),
        ("Cách đọc", "Các nhận xét là phép so sánh số liệu (với phiên trước, trung bình 5/20 phiên, phân vị 250 phiên, nhóm "
                     "đối chứng). Màu xanh/đỏ chỉ dấu tăng/giảm, không phải tín hiệu mua/bán."),
        ("Lưu ý", get("app.disclaimer")),
    ], answers=ctx.get("answers", []))


def live_session() -> Optional[pd.Timestamp]:
    """Phiên hôm nay đang có số liệu tạm tính (bộ ghi WebSocket) – None nếu ngoài phiên hoặc đã có số chính thức."""
    from src.data import live
    m = live.meta()
    return pd.Timestamp(m["session_date"]) if m else None


def build(date=None, db_path=None) -> Optional[Path]:
    """Market Snapshot. Trong giờ giao dịch, nếu chọn phiên hôm nay (hoặc không chọn) → dựng từ số liệu TẠM TÍNH trong phiên
    (data/live.duckdb); bảng kiểm định, danh mục theo dõi vẫn đọc từ kho chính."""
    from src.reports import chapters as C
    ld = live_session() if db_path is None else None
    if ld is not None and (date is None or pd.Timestamp(date) == ld):
        from src.data import live
        from src.common.config import db_path as main_db
        ctx = context.build(ld, live.LIVE_DB, watch_path=db_path or main_db())
    else:
        ctx = context.build(date, db_path)
    if ctx is None:
        log_report("snapshot", date, None, "failed", "Không có dữ liệu", db_path)
        return None
    ts = now_vn().replace(tzinfo=None)
    pdf = FFRPdf("Market Snapshot", f"Chụp lúc {ts:%H:%M %d/%m/%Y} (giờ VN) · phiên {ctx['date']:%d/%m/%Y}",
                 "SỐ LIỆU TRONG PHIÊN, CHƯA HOÀN TẤT", ctx["is_demo"])
    chapters: List[Tuple[str, callable]] = [(t, (lambda k=k: C.render_one(pdf, ctx, k, db_path))) for t, k in C.CHAPTERS]
    front_matter(pdf, ctx, "Market Snapshot", f"Chụp lúc {ts:%H:%M} ngày {ts:%d/%m/%Y} (giờ Việt Nam)",
                 [c[0] for c in chapters], "Ảnh chụp thị trường trong phiên – số liệu có thể thay đổi đến khi đóng cửa.")
    for _, fn in chapters:
        fn()
    out = save_pdf(pdf, _out_path("snapshot", ts))
    log_report("snapshot", ctx["date"], out, "ok", "demo" if ctx["is_demo"] else "", db_path)
    log.info("Đã xuất %s", out.name)
    return out


if __name__ == "__main__":
    import sys
    print(build(sys.argv[1] if len(sys.argv) > 1 else None))
