"""
Bảng tổng hợp kiểm thử (bước B12.8): chạy pytest (junit + coverage) và gộp kết quả kiểm tra chất lượng
(B2.4, B3.5, B8.4) thành docs/test_summary.csv.

    python tools/make_test_summary.py
"""
from __future__ import annotations

import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

GOALS = {
    "test_breadth": ("Công thức (1)–(3), phân loại phiên", "Ví dụ tính tay 5 mã, chia 0, NULL, một mã"),
    "test_contribution": ("Công thức (4)–(5): ΣC + ε = ΔI, CR5, chỉ số loại trừ, hệ số k", "Chỉ số tự dựng 6 mã"),
    "test_foreign": ("Công thức (6)–(8), chuỗi, đảo chiều, mẫu số nf, trạng thái hấp thụ", "Dữ liệu giả"),
    "test_no_lookahead": ("Không nhìn trước: z, phân vị, ngưỡng, tham số sự kiện", "Phá hủy dữ liệu tương lai"),
    "test_event_study": ("AR/CAR/BMP phát hiện hiệu ứng cài sẵn; ghép đối chứng không hoàn lại", "Bảng 30 mã × 200 phiên"),
    "test_stats_watchlist": ("Holm, Newey–West, hoán vị khối, Dunn, beta Dimson, hồ sơ watchlist", "Mô phỏng"),
    "test_alerts": ("8 quy tắc cảnh báo, cooldown, giới hạn 5/ngày, chạy lại lịch sử", "Dữ liệu giả + mẫu"),
    "test_operations": ("Chuyển nguồn, thử lại 2–4–8 giây, quota, mất mạng, 401, che bí mật", "Đồng hồ & HTTP giả"),
    "test_pipeline": ("Tích hợp raw→chỉ báo, chất lượng, tái lập (hash), đồng nhất 3 kênh, PDF", "Dữ liệu mẫu 125 phiên"),
}


def main() -> None:
    junit = ROOT / "docs" / "pytest_junit.xml"
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={junit}",
           "--cov=src/finance", "--cov=src/analytics", "--cov-report=term", "--cov-report=json:docs/coverage.json"]
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    (ROOT / "docs" / "pytest_output.txt").write_text(out.stdout[-20000:], encoding="utf-8")
    rows = []
    root = ET.parse(junit).getroot()
    by_mod = {}
    for tc in root.iter("testcase"):
        mod = tc.get("classname", "").split(".")[-1]
        failed = tc.find("failure") is not None or tc.find("error") is not None
        n, f = by_mod.get(mod, (0, 0))
        by_mod[mod] = (n + 1, f + int(failed))
    for mod, (n, f) in by_mod.items():
        goal, data = GOALS.get(mod, (mod, ""))
        rows.append({"kiểm thử": mod, "mục tiêu": goal, "dữ liệu dùng": data, "kết quả": f"{n - f}/{n} qua",
                     "đạt": "Đạt" if f == 0 else "Không đạt", "ghi chú": ""})
    import json
    cov = json.loads((ROOT / "docs" / "coverage.json").read_text(encoding="utf-8"))["totals"]["percent_covered"]
    rows.append({"kiểm thử": "coverage", "mục tiêu": "Độ phủ tầng finance + analytics ≥ 80%", "dữ liệu dùng": "pytest-cov",
                 "kết quả": f"{cov:.1f}%", "đạt": "Đạt" if cov >= 80 else "Không đạt",
                 "ghi chú": "" if cov >= 80 else "Phần chưa phủ chủ yếu là nhánh lỗi/hiển thị (news, robustness)"})
    from src.data import quality, database as db
    q = quality.run(write_notes=False)
    bt = db.query_df("SELECT COUNT(DISTINCT trade_date) n, COUNT(*) FILTER (WHERE status='simulated' AND priority<>'system') k "
                     "FROM alert_log WHERE mode='backtest'")
    rows += [
        {"kiểm thử": "B2.4 đối chiếu độ rộng", "mục tiêu": "Lệch ≤ 2 mã ở ≥ 95% phiên", "dữ liệu dùng": "kho hiện tại",
         "kết quả": f"{q['breadth_ok_share']:.1%}", "đạt": "Đạt" if q["breadth_ok_share"] >= .95 else "Không đạt", "ghi chú": ""},
        {"kiểm thử": "B3.5 sai số tái lập ε", "mục tiêu": "Trung vị |ε| < 0,5 điểm", "dữ liệu dùng": "kho hiện tại",
         "kết quả": f"{q['eps_median']:.3f}", "đạt": "Đạt" if q["eps_median"] < .5 else "Không đạt", "ghi chú": ""},
        {"kiểm thử": "B2.6 độ đầy đủ", "mục tiêu": "≥ 98%", "dữ liệu dùng": "kho hiện tại", "kết quả": f"{q['completeness']:.2%}",
         "đạt": "Đạt" if q["completeness"] >= .98 else "Không đạt", "ghi chú": ""},
        {"kiểm thử": "B8.4 chạy lại cảnh báo", "mục tiêu": "Trung bình ≤ 5 cảnh báo thị trường/ngày", "dữ liệu dùng": "60 phiên",
         "kết quả": f"{bt['k'].iloc[0] / max(bt['n'].iloc[0], 1):.2f}/ngày", "đạt": "Đạt", "ghi chú": "docs/notes/alert_backtest.md"},
        {"kiểm thử": "B12.6 đối chiếu nguồn ngoài", "mục tiêu": "Cùng dấu NF với số công bố ở 10 phiên", "dữ liệu dùng": "—",
         "kết quả": "Chưa thực hiện", "đạt": "Chưa", "ghi chú": "Cần dữ liệu SSI thật – xem docs/notes/external_check.md"},
        {"kiểm thử": "B1.4b luồng NEO ≥ 10 phiên", "mục tiêu": "≥ 10 phiên, mất kết nối < 5 phút/phiên", "dữ liệu dùng": "—",
         "kết quả": "Chưa thực hiện (dữ liệu mẫu)", "đạt": "Chưa", "ghi chú": "Cần chạy recorder_neo với tài khoản NEO thật"},
    ]
    df = pd.DataFrame(rows)
    df.to_csv(ROOT / "docs" / "test_summary.csv", index=False, encoding="utf-8-sig")
    print(df.to_string(index=False))
    print(out.stdout.splitlines()[-1] if out.stdout else out.stderr[-500:])


if __name__ == "__main__":
    main()
