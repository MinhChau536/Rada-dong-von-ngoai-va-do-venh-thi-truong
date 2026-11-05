"""
Mẫu Closing Report (bước B9.2) – như Snapshot + phân vị 20/60/250, dòng vốn FTSE vs đối chứng, hấp thụ, bảng
watchlist đầy đủ, phụ lục phương pháp & giới hạn. CHỈ xuất khi kiểm tra chất lượng cuối phiên đạt.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd

from src.common import fmt
from src.common.config import get
from src.common.logging import get_logger
from src.common.timeutil import now_vn
from src.data import database as db
from src.finance.domestic import ABSORB_LABELS
from src.reports import context
from src.reports.pdf_base import FFRPdf
from src.reports.snapshot import _out_path, log_report, page_leaders, page_market, page_watch

log = get_logger(__name__)


def quality_gate(date, db_path=None) -> Tuple[bool, str]:
    """Đạt khi: có đủ chỉ số, tỷ lệ đầy đủ ≥ mục tiêu, lệch độ rộng ≤ ngưỡng, |ε| hợp lý."""
    d = pd.Timestamp(date)
    q = db.query_df("SELECT * FROM data_quality_log WHERE trade_date = ?", [d], path=db_path)
    if q.empty:
        return False, "Chưa có kết quả kiểm tra chất lượng cho phiên"
    comp = q[q["check_name"] == "completeness"]["value"]
    if comp.empty or float(comp.iloc[0]) < float(get("cleaning.completeness_target", .98)):
        return False, f"Tỷ lệ đầy đủ {fmt.frac_pct(comp.iloc[0] if not comp.empty else None, 1)} dưới mục tiêu"
    br = q[q["check_name"] == "breadth_check"]["value"]
    if not br.empty and float(br.iloc[0]) > float(get("cleaning.breadth_tolerance", 2)) + 3:
        return False, f"Độ rộng lệch {int(br.iloc[0])} mã so với SSI"
    eps = q[q["check_name"] == "eps"]["value"]
    if not eps.empty and abs(float(eps.iloc[0])) > 5:
        return False, f"Sai số tái lập ε = {fmt.num(eps.iloc[0], 2)} điểm quá lớn"
    return True, "đạt"


def page_history(pdf: FFRPdf, ctx: Dict) -> None:
    x = ctx["day"]
    pdf.h2("So với lịch sử (phân vị, chỉ dùng dữ liệu trước phiên)")
    rows = []
    for m, lbl in (("D", "Độ vênh D"), ("CR5", "CR5"), ("IQR_pct", "IQR"), ("AD", "AD"), ("NF_total", "NF HOSE"), ("HHI", "HHI")):
        rows.append([lbl, fmt.num(x[m] / 1e9 if m == "NF_total" else x[m], 3 if m != "NF_total" else 0, True)]
                    + [fmt.num(x.get(f"{m}_pct{w}"), 0, False, "%") for w in (20, 60, 250)])
    pdf.table(["Chỉ báo", "Hôm nay", "Phân vị 20", "Phân vị 60", "Phân vị 250"], rows, [40, 32, 30, 30, 30])
    g = ctx["groups"]
    uni = g[g["group_type"] == "universe"]
    pdf.h2("Dòng vốn theo nhóm FTSE và đối chứng")
    pdf.table(["Nhóm", "Số mã", "NF", "nf", "FPR", "Trạng thái"],
              [[r.group_name, str(int(r.n)), fmt.bn(r.net_flow), fmt.num(r.nf, 3, True), fmt.frac_pct(r.FPR, 1),
                ABSORB_LABELS.get(r.absorb_state, "")] for r in uni.itertuples()], [30, 18, 30, 24, 24, 40])
    st = ctx["stock"][ctx["stock"]["is_valid"]]
    cnt = st["absorb_state"].value_counts()
    pdf.para("Trạng thái hấp thụ toàn sàn: " + "; ".join(f"{ABSORB_LABELS[k]} {int(cnt.get(k, 0))} mã" for k in ABSORB_LABELS) + ".", 8.5)


def page_method(pdf: FFRPdf) -> None:
    pdf.h2("Phụ lục – Phương pháp và giới hạn")
    for t in [
        "(1) r = P_c / P_ref − 1 · (2) D = r_VNI − trung vị r_i trên Ω (cổ phiếu thường HOSE, P_ref > 0, có khớp lệnh).",
        "(3) AD = (N⁺ − N⁻)/N; IQR = Q75 − Q25 · (4) C_i = I_(t−1) · w_i · r_i, w_i theo vốn hóa đầu phiên S_i·P_ref.",
        "(5) ε = ΔI − ΣC; CR5 = Σ|C| top 5 / Σ|C| · (6) NF = FB − FS; nf = NF/TV; FPR = (FB+FS)/(2TV).",
        "(7) HHI = Σ(|NF_i|/Σ|NF|)²; U = 1 − Remain/Room · (8) z theo 60 phiên trước (không nhìn trước).",
        "Giới hạn: vốn hóa xấp xỉ bằng số CP niêm yết (chưa điều chỉnh CP quỹ, free-float); chỉ tách được khối ngoại; "
        "tương quan không phải nhân quả; nghiên cứu sự kiện có mẫu nhỏ.",
        get("app.disclaimer")]:
        pdf.para(t, 8.5)


def build(date=None, db_path=None, force: bool = False) -> Tuple[Optional[Path], str]:
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
    pdf.add_page()
    page_market(pdf, ctx)
    page_history(pdf, ctx)
    pdf.add_page()
    page_leaders(pdf, ctx)
    pdf.add_page()
    page_watch(pdf, ctx, full=True)
    page_method(pdf)
    out = _out_path("closing", pd.Timestamp(ctx["date"]))
    pdf.output(str(out))
    log_report("closing", ctx["date"], out, "ok", "demo" if ctx["is_demo"] else "", db_path)
    return out, "ok"
