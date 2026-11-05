"""
Mẫu Market Snapshot (bước B9.1) – 3 trang: (1) trạng thái + thẻ + nhận định; (2) dẫn dắt + độ rộng + khối ngoại;
(3) watchlist. Dòng "số liệu trong phiên, chưa hoàn tất", giờ chụp, nguồn. Tên tệp FFR_snapshot_yyyymmdd_hhmm.pdf.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from src.common import fmt
from src.common.config import abs_path, get
from src.common.logging import get_logger
from src.common.timeutil import now_vn
from src.data import database as db
from src.finance.breadth import session_type_label
from src.finance.domestic import ABSORB_LABELS
from src.reports import context
from src.reports.pdf_base import FFRPdf

log = get_logger(__name__)


def _clr(v) -> str:
    return "up" if v is not None and v > 0 else "down" if v is not None and v < 0 else "ref"


def page_market(pdf: FFRPdf, ctx: Dict) -> None:
    x = ctx["day"]
    idx = ctx["index"].set_index("index_code")
    names = [("VNINDEX", "VN-Index"), ("VN30", "VN30"), ("HNXINDEX", "HNX-Index"), ("UPCOMINDEX", "UPCoM-Index")]
    pdf.h2(f"Trạng thái phiên {ctx['date']:%d/%m/%Y}")
    pdf.cards([(n, fmt.num(idx.loc[c, "value"]) if c in idx.index else "—",
                f"{fmt.num(idx.loc[c, 'change'], 2, True)} ({fmt.pct(idx.loc[c, 'ratio_change'])})" if c in idx.index else "",
                _clr(idx.loc[c, "change"]) if c in idx.index else None) for c, n in names])
    pdf.cards([
        ("Trung vị cổ phiếu HOSE", fmt.pct(x["median_ret_pct"]), f"{int(x['n_valid'])} mã · IQR {fmt.num(x['IQR_pct'], 1)}%", _clr(x["median_ret_pct"])),
        ("Độ vênh D", fmt.num(x["D"], 2, True, " đ.%"), f"phân vị 250 phiên: {fmt.num(x['D_pct250'], 0)}%", "accent"),
        ("Top 5 đóng góp CR5", fmt.frac_pct(x["CR5"], 0), f"ε = {fmt.num(x['eps'], 2, True)} điểm", None),
        ("Loại phiên", session_type_label(x["session_type"]), f"AD = {fmt.num(x['AD'], 2, True)}", None),
    ])
    pdf.h2("Nhận định theo quy tắc")
    pdf.para(ctx["summary"])
    pdf.para(ctx["foreign"])
    pdf.para(get("app.bot_disclaimer"), 8, "I")


def page_leaders(pdf: FFRPdf, ctx: Dict) -> None:
    x, lead = ctx["day"], ctx["leaders"]
    pdf.h2(f"Mã dẫn dắt VN-Index · ΔI = {fmt.num(x['dI'], 2, True)} điểm")
    both = pd.concat([lead[lead["side"] == "pos"].head(5), lead[lead["side"] == "neg"].head(5)]).sort_values("C", ascending=False)
    y0 = pdf.get_y()
    pdf.hbars(both["symbol"].tolist(), both["C"].tolist(), fmt_fn=lambda v: fmt.num(v, 2, True))
    y1 = pdf.get_y()
    pdf.set_xy(118, y0)
    g = ctx["groups"]
    fam = g[g["group_type"] == "family"].sort_values("C", ascending=False)
    rows = [[r.group_name, fmt.num(r.C, 2, True), fmt.pct(r.index_ex_group_ret_pct)] for r in fam.itertuples()]
    pdf.set_left_margin(118)
    pdf.table(["Họ cổ phiếu", "Đóng góp (đ)", "VNI loại trừ"], rows, [30, 24, 24])
    pdf.set_left_margin(14)
    pdf.set_y(max(y1, pdf.get_y()) + 2)
    pdf.h2("Độ rộng thị trường HOSE")
    pdf.cards([("Tăng", f"{int(x['n_up'])}", f"trong đó trần {int(x['n_ceiling'])}", "up"),
               ("Đứng giá", f"{int(x['n_unch'])}", "", "ref"),
               ("Giảm", f"{int(x['n_down'])}", f"trong đó sàn {int(x['n_floor'])}", "down"),
               ("Tỷ lệ mã tăng", fmt.num(x["pct_up"], 0, False, "%"), f"AD = {fmt.num(x['AD'], 2, True)}", None)])
    pdf.h2(f"Khối ngoại · ròng {fmt.bn(x['NF_total'])} · HHI {fmt.num(x['HHI'], 3)}")
    top = pd.concat([ctx["top_buy"], ctx["top_sell"]]).sort_values("net_flow", ascending=False)
    pdf.hbars(top["symbol"].tolist(), (top["net_flow"] / 1e9).tolist(), fmt_fn=lambda v: fmt.num(v, 0, True, " tỷ"))


def page_watch(pdf: FFRPdf, ctx: Dict, full: bool = False) -> None:
    pf = ctx["watch"]
    pdf.h2("Danh mục theo dõi – Watchlist Impact")
    if pf is None or pf.empty:
        pdf.para("Danh mục trống.")
        return
    rows = []
    for r in pf.itertuples():
        if not r.has_data:
            rows.append([r.symbol] + ["—"] * (8 if full else 6))
            continue
        base = [r.symbol, fmt.price(r.close), fmt.pct(r.ret * 100), fmt.num(r.ER_M * 100, 2, True),
                fmt.num(r.C, 2, True) if r.C is not None else "—", fmt.bn(r.net_flow, 1), ABSORB_LABELS.get(r.absorb_state, "")]
        if full:
            base += [fmt.num(r.pct60_nf, 0), fmt.num(r.beta_dimson, 2)]
        rows.append(base)
    heads = ["Mã", "Giá", "%", "ER^M (đ.%)", "Đóng góp", "NN ròng", "Hấp thụ"] + (["Phân vị nf", "β Dimson"] if full else [])
    widths = [16, 20, 18, 22, 20, 24, 36] + ([20, 20] if full else [])
    pdf.table(heads, rows, widths)
    for r in pf.itertuples():
        pdf.para("• " + r.sentence, 8.5)


def _out_path(kind: str, ts: datetime) -> Path:
    d = abs_path(get("paths.reports_dir", "reports_out"))
    d.mkdir(parents=True, exist_ok=True)
    stamp = ts.strftime("%Y%m%d_%H%M") if kind == "snapshot" else ts.strftime("%Y%m%d")
    return d / f"FFR_{kind}_{stamp}.pdf"


def log_report(kind: str, date, path_: Optional[Path], status: str, note: str = "", db_path=None) -> None:
    db.append("reports_log", pd.DataFrame([{"created_at": now_vn().replace(tzinfo=None), "kind": kind,
                                             "trade_date": pd.Timestamp(date).date() if date is not None else None,
                                             "path": str(path_) if path_ else None, "status": status, "note": note}]), db_path)


def build(date=None, db_path=None) -> Optional[Path]:
    ctx = context.build(date, db_path)
    if ctx is None:
        log_report("snapshot", date, None, "failed", "Không có dữ liệu", db_path)
        return None
    ts = now_vn().replace(tzinfo=None)
    pdf = FFRPdf("Market Snapshot", f"Chụp lúc {ts:%H:%M %d/%m/%Y} (giờ VN) · phiên {ctx['date']:%d/%m/%Y}",
                 "SỐ LIỆU TRONG PHIÊN, CHƯA HOÀN TẤT", ctx["is_demo"])
    pdf.add_page()
    page_market(pdf, ctx)
    pdf.add_page()
    page_leaders(pdf, ctx)
    pdf.add_page()
    page_watch(pdf, ctx)
    out = _out_path("snapshot", ts)
    pdf.output(str(out))
    log_report("snapshot", ctx["date"], out, "ok", "demo" if ctx["is_demo"] else "", db_path)
    log.info("Đã xuất %s", out.name)
    return out
