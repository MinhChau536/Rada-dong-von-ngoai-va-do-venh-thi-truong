"""
Kiểm tra chất lượng dữ liệu (bước B2.4, B2.5, B2.6, B3.5) – ghi data_quality_log và ghi chú docs/notes.

- completeness   : tỷ lệ cặp (phiên, mã hợp lệ) có đủ trường chính (mục tiêu ≥ 98%)
- breadth_check  : số mã tăng/giảm/đứng tự đếm − Advances/Declines/NoChanges của SSI (≤ 2 mã ở ≥ 95% phiên)
- return_bounds  : |r| > 7% (ngoài biên độ HOSE)
- eps            : sai số tái lập chỉ số ε_t (trung vị |ε| < 0,5 điểm)
- foreign_scope  : trường khối ngoại là khớp lệnh hay gồm thỏa thuận
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

from src.common.config import abs_path, get
from src.common.logging import get_logger
from src.data import database as db
from src.finance.breadth import breadth_check

log = get_logger(__name__)
KEY_FIELDS = ["ref", "close", "tv", "fb", "fs", "remain"]
CHECKS = ("completeness", "breadth_check", "return_bounds", "eps", "foreign_scope")


def run(path: Optional[Path] = None, write_notes: bool = True) -> Dict:
    st = db.query_df("SELECT * FROM indicator_stock_daily", path=path)
    day = db.query_df("SELECT * FROM indicator_daily ORDER BY trade_date", path=path)
    idx = db.query_df("SELECT * FROM fact_daily_index WHERE index_code = 'VNINDEX'", path=path)
    meta = db.query_df("SELECT * FROM pipeline_meta", path=path)
    if st.empty or day.empty:
        return {}
    db.execute("DELETE FROM data_quality_log WHERE check_name IN ({})".format(",".join(f"'{c}'" for c in CHECKS)), path=path)
    rows = []
    v = st[st["is_valid"]]
    full = v[KEY_FIELDS].notna().all(axis=1)
    comp = full.groupby(v["trade_date"]).mean()
    for d, x in comp.items():
        rows.append({"trade_date": d, "check_name": "completeness", "metric": "ratio", "value": x,
                     "status": "ok" if x >= get("cleaning.completeness_target", .98) else "warn", "detail": ""})
    overall = float(full.mean())
    maxr = float(get("cleaning.max_abs_return", .07)) + 0.001
    oob = v[v["ret"].abs() > maxr]
    for r in oob.itertuples():
        rows.append({"trade_date": r.trade_date, "check_name": "return_bounds", "metric": r.symbol, "value": r.ret,
                     "status": "warn", "detail": "|r| vượt biên độ 7% (kiểm tra ngày đầu niêm yết/điều chỉnh)"})
    day_i = day.set_index("trade_date")
    idx_i = idx.copy()
    bc = breadth_check(day_i[["n_up", "n_down", "n_unch"]], idx_i)
    tol = int(get("cleaning.breadth_tolerance", 2))
    for d, r in bc.iterrows():
        rows.append({"trade_date": d, "check_name": "breadth_check", "metric": "max_abs_diff", "value": r["max_abs_diff"],
                     "status": "ok" if r["max_abs_diff"] <= tol else "warn",
                     "detail": f"tăng {int(r['diff_up']):+d}, giảm {int(r['diff_down']):+d}, đứng {int(r['diff_unch']):+d}"
                               + ("" if r["max_abs_diff"] <= tol else " – kiểm tra CCQ/ETF, mã mới niêm yết")})
    breadth_ok = float((bc["max_abs_diff"] <= tol).mean()) if len(bc) else np.nan
    for d, e in day_i["eps"].items():
        rows.append({"trade_date": d, "check_name": "eps", "metric": "eps_points", "value": e,
                     "status": "ok" if abs(e) < 1.5 else "warn", "detail": ""})
    eps_med = float(day_i["eps"].abs().median())
    m = meta.iloc[0] if not meta.empty else {}
    rows.append({"trade_date": None, "check_name": "foreign_scope", "metric": "share_exceed_bigdeal",
                 "value": m.get("share_exceed_bigdeal", np.nan), "status": "info",
                 "detail": f"mẫu số nf = {m.get('denominator', '?')}"})
    db.log_quality(rows, path)
    summary = {"completeness": overall, "breadth_ok_share": breadth_ok, "eps_median": eps_med,
               "eps_median_raw": float(m.get("eps_median_raw", np.nan)), "scale_k": float(m.get("scale_k", 1.0)),
               "n_out_of_bounds": int(len(oob)), "denominator": m.get("denominator", "match"),
               "foreign_includes_deal": bool(m.get("foreign_includes_deal", False)),
               "n_sessions": int(day["trade_date"].nunique()), "n_symbols": int(st["symbol"].nunique())}
    if write_notes:
        _notes(summary, m)
    log.info("Chất lượng: đầy đủ %.2f%%, độ rộng khớp %.1f%% phiên, trung vị |ε| = %.3f",
             overall * 100, breadth_ok * 100, eps_med)
    return summary


def _notes(s: Dict, m) -> None:
    p = abs_path("docs/notes/foreign_scope.md")
    p.write_text("\n".join([
        "# Phạm vi trường khối ngoại (bước B2.5)", "",
        "Phép thử: so (FB + FS)/2 với giá trị khớp lệnh TV trên các mã–phiên có giao dịch thỏa thuận lớn "
        "(TV_pt > 20% TV). Nếu nửa tổng giao dịch khối ngoại vượt TV ở nhiều quan sát → trường gồm cả thỏa thuận.", "",
        f"- Số quan sát có thỏa thuận lớn: {int(m.get('n_bigdeal', 0))}",
        f"- Tỷ lệ quan sát (FB+FS)/2 > TV trong nhóm này: {float(m.get('share_exceed_bigdeal', 0)):.2%}",
        f"- **Kết luận: trường khối ngoại {'GỒM thỏa thuận' if s['foreign_includes_deal'] else 'chỉ KHỚP LỆNH'}; "
        f"mẫu số nf chốt = `{s['denominator']}`.**", "",
        "_Tự sinh bởi src/data/quality.py. Với dữ liệu mẫu (DEMO_DATA) kết luận phản ánh cách sinh dữ liệu, "
        "phải chạy lại trên dữ liệu SSI thật._"]), encoding="utf-8")
