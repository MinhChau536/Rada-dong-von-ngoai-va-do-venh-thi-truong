"""Trang 8 – Phương pháp & giới hạn (bước B11.2): công thức (1)–(17), nguồn, tham số đọc TRỰC TIẾP từ settings.yaml,
kết quả kiểm định & kiểm thử, độ vững, giới hạn, mã kế thừa."""
from __future__ import annotations

import pandas as pd
import streamlit as st
import yaml

from src.app import data_access as da
from src.app.components import about, status_bar
from src.app.components.ui import esc, header, md, section, table_html
from src.common import fmt
from src.common.config import CONFIG_DIR, ROOT, load_settings

FORMULAS = [
    ("(1) Lợi suất phiên", r"r_{i,t} = \frac{P^{c}_{i,t}}{P^{ref}_{i,t}} - 1"),
    ("(2) Điểm vênh", r"D_t = r_{VNI,t} - \operatorname{median}_{i\in\Omega_t}(r_{i,t})"),
    ("(3) Độ rộng, phân tán", r"AD_t = \frac{N^+_t - N^-_t}{N^+_t+N^-_t+N^0_t},\quad IQR_t = Q_{75}(r_{\cdot,t}) - Q_{25}(r_{\cdot,t})"),
    ("(4) Đóng góp điểm", r"w_{i,t} = \frac{S_i P^{ref}_{i,t}}{\sum_j S_j P^{ref}_{j,t}},\quad C_{i,t} = I_{t-1}\, w_{i,t}\, r_{i,t}"),
    ("(5) Sai số tái lập, CR5", r"\varepsilon_t = (I_t - I_{t-1}) - \sum_i C_{i,t},\quad CR5_t = \frac{\sum_{i\in Top5}|C_{i,t}|}{\sum_i |C_{i,t}|}"),
    ("(6) Dòng vốn ngoại", r"NF = FB - FS,\quad nf = \frac{NF}{TV},\quad FPR = \frac{FB+FS}{2\,TV}"),
    ("(7) Tập trung, room", r"HHI_t = \sum_i\Big(\frac{|NF_{i,t}|}{\sum_j|NF_{j,t}|}\Big)^2,\quad U_{i,t} = 1-\frac{Remain_{i,t}}{Room_{i,t}}"),
    ("(8) Bất thường (không nhìn trước)", r"z_{i,t} = \frac{nf_{i,t} - \overline{nf}_{i,[t-60,t-1]}}{s_{i,[t-60,t-1]}}"),
    ("(9) Nghiên cứu sự kiện", r"AR_{i,\tau} = r_{i,\tau} - (\hat\alpha_i + \hat\beta_i r_{m,\tau}),\ CAR_i = \sum_{\tau_1}^{\tau_2} AR_{i,\tau},\ CAAR = \tfrac1N\sum_i CAR_i"),
    ("(10) Dòng vốn & thanh khoản bất thường", r"AFF_{i,\tau} = nf_{i,\tau} - \overline{nf}_{i,est},\quad AVol_{i,\tau} = \ln TV_{i,\tau} - \overline{\ln TV}_{i,est}"),
    ("(11) Chênh lệch kép", r"y_{i,t} = \mu_i + \lambda_t + \delta\,(FTSE_i\times Post_t) + \varepsilon_{i,t}"),
    ("(12) Lợi suất vượt trội", r"ER^I_{i,t} = r_{i,t}-r_{VNI,t},\quad ER^M_{i,t} = r_{i,t} - \operatorname{median}_j(r_{j,t})"),
    ("(13) Beta Dimson", r"r_{i,t} = a_i + \sum_{k=-1}^{1} b_{i,k} r_{VNI,t+k} + u_{i,t},\quad \beta^D_i = \sum_k \hat b_{i,k}"),
    ("(14) RSI(14) – động lượng", r"RSI_t = 100 - \frac{100}{1+RS_t},\quad RS_t = \frac{\overline{U}_t}{\overline{D}_t},\ "
                                  r"\overline{X}_t = \tfrac{13}{14}\overline{X}_{t-1} + \tfrac{1}{14}X_t"),
    ("(15) MACD(12, 26, 9)", r"MACD_t = EMA_{12}(I)_t - EMA_{26}(I)_t,\quad Sig_t = EMA_9(MACD)_t,\quad H_t = MACD_t - Sig_t"),
    ("(16) Cấu trúc đỉnh – đáy (Dow)", r"\text{tăng} \Leftrightarrow \max_{[t-19,t]} I > \max_{[t-39,t-20]} I \ \wedge\ "
                                        r"\min_{[t-19,t]} I > \min_{[t-39,t-20]} I"),
    ("(17) Khối lượng xác nhận", r"V^{*}_t = TV_t / \overline{TV}_{20},\quad \text{xác nhận} \Leftrightarrow "
                                 r"\operatorname{sign}(r_t)\ \text{và}\ V^{*}_t \ge 1"),
]

INHERITED = [
    ("data/providers/base_provider.py", "src/ssi_api/base_provider.py", "Giữ khuôn lớp cơ sở"),
    ("data/database.py", "src/data/database.py", "Ý tưởng kho DuckDB, viết lại theo lược đồ mới"),
    ("core/thi_truong_danh_muc.py: breadth_stats, sector_performance, index_card, period_returns, market_health, rsi",
     "src/finance/breadth.py, src/analytics/health.py", "Giữ logic, đổi nguồn, đổi trọng số sức khỏe"),
    ("giao_dien/thi_truong.py: _index_chart, _treemap, _sector_bars, _gauge, _breadth_block, _movers_table, _spark, render()",
     "src/app/components/charts.py, ui.py, pages/p1_tong_quan.py", "Giữ bố cục & thứ tự khối, đổi bảng màu"),
    ("_pal() rải rác", "src/app/theme.py", "Gom thành một nguồn màu cho CSS, Plotly, PDF"),
    ("reports/pdf_generator.py, reports/cover.py, assets/fonts/", "src/reports/*, assets/fonts/", "Giữ khung & font Be Vietnam Pro"),
    ("WatchlistService", "src/analytics/watchlist_impact.py", "Giữ quản lý danh sách, thêm hồ sơ phản ứng"),
    ("tests/fakes.py", "tests/test_operations.py", "Ý tưởng kiểm thử không cần mạng (phiên HTTP giả)"),
    ("components/background_fx.py", "—", "Tắt (B4.3) – giao diện tĩnh"),
]


def render() -> None:
    header("Phương pháp & giới hạn", "Công thức, tham số, kết quả kiểm định, độ vững và những điều KHÔNG kết luận")
    status_bar.render()
    about.render_full()
    section("Công thức (1)–(17)")
    c1, c2 = st.columns(2)
    for i, (t, f) in enumerate(FORMULAS):
        with (c1 if i % 2 == 0 else c2):
            st.markdown(f"**{t}**")
            st.latex(f)
    st.caption("Ω_t: cổ phiếu thường HOSE, P_ref > 0, có khớp lệnh (loại mã tạm ngừng, CCQ, chứng quyền). Trung vị dùng thay "
               "trung bình vì lợi suất bị chặn biên độ ±7% và có đuôi dày. Biến liên tục cắt 1%/99% theo phiên cho hồi quy; "
               "thống kê mô tả dùng số chưa cắt.")
    section("Tham số chính (đọc trực tiếp config/settings.yaml)", "Đổi tham số trong tệp → trang tự cập nhật sau khi Làm mới")
    from src.common.config import get
    params = [
        ("Dữ liệu", "Tỷ lệ đầy đủ mục tiêu", get("cleaning.completeness_target"), "Phiên dưới mức này không xuất Closing Report"),
        ("Dữ liệu", "Lệch độ rộng tối đa so với SSI (mã)", get("cleaning.breadth_tolerance"), "Đối chiếu số mã tăng/giảm/đứng"),
        ("Đóng góp điểm", "Trung vị |ε| mục tiêu (điểm)", get("contribution.eps_median_target"), "Sai số tái lập VN-Index"),
        ("Khối ngoại", "Ngưỡng |nf| / |giá| gán trạng thái", f"{get('foreign.absorb_nf_min')} / {get('foreign.absorb_ret_min')}",
         "Dưới ngưỡng → trung tính"),
        ("Cảnh báo", "Quy tắc 1: |ΔI| (điểm) và CR5", f"{get('alerts.dI_min')} và {get('alerts.cr5_min')}", "Chỉ số do ít mã dẫn dắt"),
        ("Cảnh báo", "Quy tắc 2: D ≥ phân vị", get("alerts.div_pct"), "Độ vênh cao so với 250 phiên"),
        ("Cảnh báo", "Quy tắc 3: |z| tổng NF ≥", get("alerts.z_total_nf"), "Khối ngoại bất thường"),
        ("Cảnh báo", "Tối đa cảnh báo thị trường/ngày · chống trùng (phút)",
         f"{get('alerts.max_market_per_day')} · {get('alerts.cooldown_min')}", "Ưu tiên mức cao trước"),
        ("Sự kiện FTSE", "Cửa sổ CAR", str(get("events.car_windows")), "Ngày sự kiện τ"),
        ("Sự kiện FTSE", "Số lần bootstrap · trễ Newey–West", f"{get('events.bootstrap_reps')} · {get('events.nw_lags')}", ""),
        ("Giai đoạn", "Ngày công bố E1 · ngày hiệu lực", f"{get('periods.announce')} · {get('periods.effective')}", "H4 so với 250 phiên trước E1"),
        ("Biên dao động", "λ EWMA", get("outlook.ewma_lambda"), "RiskMetrics; hệ số biên hiệu chỉnh đuôi dày"),
    ]
    md(table_html(["Nhóm", "Tham số", "Giá trị", "Ý nghĩa"], [[a, b, esc(str(c)), d] for a, b, c, d in params], left=(0, 1, 2, 3)))
    with st.expander("Xem toàn bộ tệp settings.yaml"):
        st.code(yaml.safe_dump(load_settings(), allow_unicode=True, sort_keys=False), language="yaml")
    section("Kết quả kiểm định giả thuyết", "p gốc và p hiệu chỉnh Holm theo họ kiểm định cùng giả thuyết")
    stats = da.table("stats_results")
    if not stats.empty:
        hyp = st.multiselect("Giả thuyết", sorted(stats["hypothesis"].unique()), default=["H1a", "H1b", "H2a", "H2b", "H2c"],
                             key="p8_h")
        s = stats[stats["hypothesis"].isin(hyp) & (stats["variant"] == "base")]
        md(table_html(["Giả thuyết", "Chỉ tiêu", "Nhóm", "Kiểm định", "Ước lượng", "Thống kê", "p", "p Holm", "N", "Ghi chú"],
                      [[r.hypothesis, r.metric, r.group, r.test, fmt.num(r.estimate, 4, True), fmt.num(r.statistic, 2, True),
                        fmt.num(r.p_value, 4), fmt.num(r.p_holm, 4), str(int(r.n)) if pd.notna(r.n) else "—", r.note or ""]
                       for r in s.itertuples()], left=(0, 1, 2, 3, 9)))
    section("Kiểm tra độ vững (B6.13)", "Kết quả coi là vững nếu giữ dấu và mức ý nghĩa ở phần lớn biến thể")
    rb = da.table("robustness_results")
    if not rb.empty:
        md(table_html(["Biến thể", "Mốc", "Nhóm", "Kiểm định", "Ước lượng", "p", "Có ý nghĩa 5%"],
                      [[r.variant, r.event_id, r.group, r.test, fmt.num(r.estimate, 4, True), fmt.num(r.p_value, 4),
                        "✅" if r.sig_5pct else "—"] for r in rb.itertuples()], left=(0, 1, 2, 3)))
    section("Kết quả kiểm thử tự động")
    ts = ROOT / "docs" / "test_summary.csv"
    if ts.exists():
        st.dataframe(pd.read_csv(ts), width="stretch")
    else:
        st.caption("Chạy `python -m pytest` rồi `python tools/make_test_summary.py` để sinh docs/test_summary.csv.")
    section("Giới hạn và những điều không kết luận")
    md("""<div class="ffr-insight">
    • Vốn hóa xấp xỉ bằng số cổ phiếu niêm yết, chưa điều chỉnh cổ phiếu quỹ và tỷ lệ tự do chuyển nhượng → đóng góp C là
      xấp xỉ, chất lượng đo bằng ε hằng ngày.<br>
    • Dữ liệu chỉ tách được khối ngoại; không tách tổ chức trong nước và cá nhân. Mua ròng khối nội = − bán ròng khối ngoại.<br>
    • Tương quan cùng phiên giữa dòng vốn ngoại và lợi suất không phải quan hệ nhân quả hay khả năng dự báo.<br>
    • Khác biệt trước/sau 21/9/2026 không quy hoàn toàn cho nâng hạng (lãi suất, tỷ giá, kết quả kinh doanh đồng thời).<br>
    • Nghiên cứu sự kiện ~25–30 mã nhóm xử lý → độ mạnh thống kê hạn chế; giai đoạn sau hiệu lực còn ngắn.<br>
    • Danh sách FTSE trong cấu hình phải đối chiếu thông báo chính thức (≥ 2 nguồn) trước khi diễn giải.<br>
    • Chỉ báo kỹ thuật (công thức 14–17) mô tả trạng thái giá – khối lượng, không dự báo hướng đi.<br>
    • Khuyến nghị trên trang Chẩn đoán thị trường và trong báo cáo chỉ ở cấp THỊ TRƯỜNG, suy ra từ chỉ báo theo quy tắc cố định
      (MA20/MA50, ≥ 55% / ≤ 40% mã tăng, CR5 phân vị ≥ 80, |z khối ngoại 5 phiên| ≥ 1, σ ≥ 1,5% / ≤ 0,8%); không chọn cổ phiếu.<br>
    • Ngành của cổ phiếu theo mã ICB do SSI trả về (danh mục chứng khoán SSI), gộp nhóm theo tiền tố mã ICB (src/finance/sectors.py).
      Định giá (P/E, P/B) và số liệu vĩ mô không có trong SSI FastConnect nên không được dùng.<br>
    • Thông tin tham chiếu ngoài API, có ghi nguồn: danh sách 27 mã và các mốc sự kiện FTSE Russell (config/ftse_universe.csv,
      config/events.csv – cột source_url); định nghĩa họ cổ phiếu (Vingroup…) do đề tài đặt.<br>
    • Mọi số liệu thị trường tải từ SSI FastConnect V3 (REST + WebSocket). Giá lịch sử của SSI đã điều chỉnh quyền; giá tham chiếu/trần/sàn được quy về cùng thang nên lợi suất ngày khớp % thay đổi chính thức.
    </div>""")
    section("Mã kế thừa từ đồ án giữa kỳ", "Kho web_phantichchungkhoan – ghi nguồn theo yêu cầu liêm chính học thuật")
    md(table_html(["Thành phần giữa kỳ", "Vị trí trong bản 3.2", "Cách dùng"], [list(x) for x in INHERITED], left=(0, 1, 2)))
