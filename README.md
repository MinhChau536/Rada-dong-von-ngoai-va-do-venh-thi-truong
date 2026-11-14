# FTSE Flow Radar 3.2

**Hệ thống phân tích độ vênh, cổ phiếu dẫn dắt và dòng vốn ngoại trên thị trường chứng khoán Việt Nam trong giai đoạn nâng hạng FTSE, tích hợp tác động lên danh mục theo dõi, báo cáo PDF và cảnh báo Telegram.**

Đồ án cá nhân cuối kỳ – học phần *Gói phần mềm ứng dụng cho tài chính 1*, Trường ĐH Kinh tế – Luật (ĐHQG-HCM).
Sinh viên: Lê Ngọc Minh Châu.

> ⚖️ Công cụ phân tích học thuật, **không phải khuyến nghị đầu tư**. Hệ thống chỉ đọc dữ liệu, không đặt lệnh, không quản trị danh mục, không khẳng định quan hệ nhân quả.

---

## 1. Sản phẩm trả lời câu hỏi gì

| Câu hỏi | Chỉ báo | Trang |
|---|---|---|
| RQ1 – Sức tăng/giảm của VN-Index có lan tỏa đến số đông không? Bao nhiêu mã tạo ra phần lớn biến động? | D, AD, IQR, loại phiên, C, CR5, ε | 1, 2 |
| RQ2 – Dòng vốn ngoại tập trung vào đâu, có đi cùng giá không, khối nội phản ứng ra sao? | NF, nf, FPR, HHI, z, chuỗi, trạng thái hấp thụ | 1, 3 |
| RQ3 – Quanh các mốc FTSE (E1 08/10/2025, E2 08/04/2026, E3 18/09/2026) nhóm vào rổ có bất thường so với đối chứng? | AR, CAR, CAAR, AFF, AVol, DiD | 4 |
| RQ5 – Cấu trúc thị trường thay đổi thế nào qua ba giai đoạn (250 phiên trước E1 / E1 → hiệu lực / sau hiệu lực)? Mẫu đã đủ dài chưa? | H4: D, CR5, IQR, \|r\|, ln TV, FPR, nf, HHI, tỷ lệ phiên thiếu lan tỏa – OLS Newey–West + MDE | 8, PDF · `docs/notes/data_coverage.md` |
| RQ4 – Các mã trong watchlist phản ứng thế nào? | ER^I, ER^M, β Dimson, β nội ngày, phản ứng theo loại phiên | 5 |

Ba kênh phân phối – **dashboard Streamlit 8 trang**, **báo cáo PDF** (Snapshot, Closing) và **bot Telegram** – đọc chung một kho chỉ báo (`indicator_*`) và một bộ định dạng số (`src/common/fmt.py`), nên con số luôn trùng khớp.

## 2. Kiến trúc

```
 SSI FastConnect V3 – NGUỒN DUY NHẤT (developers.ssi.com.vn)
 REST https://api.ssi.com.vn/api/v3/data/*        WebSocket wss://stream.ssi.com.vn/ws/v3
 securitiesSummary · masterdata · indexSummary     indexsummary · trade.index · trade · room
 ohlc (1d, 5m) · securitiesByBoard                 (SDK chính thức ssi-sdk)
              │                                                       │
              ▼                                                       ▼
 Thu thập: src/ssi_api/ssi_client.py · src/data/backfill.py · src/data/recorder_ssi.py
 (token apiKey/apiSecret, ≤ 20 yêu cầu/giây, thử lại 2–4–8 s, tái kết nối, ánh xạ trường theo data_dictionary.yaml)
              │
              ▼
 Kho DuckDB: raw_* (JSON gốc) → fact_daily_stock, fact_daily_index, fact_intraday, dim_* → data_quality_log
              │
              ▼
 Tầng chỉ báo: indicator_daily · indicator_stock_daily · indicator_group_daily · leaders_daily · indicator_intraday
              │
   ┌──────────┼──────────────┬───────────────────┐
   ▼          ▼              ▼                   ▼
 A·Độ vênh  B·Dòng vốn    C·Sự kiện FTSE     D·Watchlist Impact      + Cảnh báo (8 quy tắc) + Nhận định (khuôn câu)
   └──────────┴──────────────┴───────────────────┘
              ▼
 Dashboard Streamlit (8 trang) · Báo cáo PDF (fpdf2) · Bot Telegram (lệnh, bản tin 11:35/15:15, cảnh báo)
```

## 3. Cài đặt

```bash
git clone https://github.com/MinhChau536/Rada-dong-von-ngoai-va-do-venh-thi-truong.git
cd Rada-dong-von-ngoai-va-do-venh-thi-truong
python -m venv .venv && .venv\Scripts\activate        # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env                                  # rồi điền khóa thật nếu có (cp trên Linux/macOS)
```

Yêu cầu Python 3.12. Ứng dụng **chỉ dùng dữ liệu thật** tải qua API – không có chế độ dữ liệu giả lập.

### Cấu hình `.env`

| Biến | Ý nghĩa |
|---|---|
| `SSI_API_KEY`, `SSI_API_SECRET` | Khóa **SSI FastConnect V3** tạo tại Developer Portal (developers.ssi.com.vn › Quản lý API Key), nhóm quyền Market Data / stream DATA. **Không cần Private Key, không cần OTP.** |
| `SSI_BASE_URL`, `SSI_STREAM_URL` | Mặc định `https://api.ssi.com.vn` và `wss://stream.ssi.com.vn/ws/v3` |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_IDS` | Bot từ @BotFather; danh sách chat_id được phép (phân tách dấu phẩy) |

`.env` nằm trong `.gitignore`; kho mã chỉ chứa `.env.example` với giá trị giả. Nhật ký đi qua `mask_secrets` nên không ghi token, API Secret.

## 4. Cách chạy

### 4.1. Kiểm tra khóa API

```bash
python -m src.data.diagnostics      # lấy token + gọi thử securitiesSummary (REST) + mở WebSocket V3
python -m src.ssi_api.ssi_client    # in số mã HOSE
```

### 4.2. Tải dữ liệu thật và chạy

```bash
python -m src.ssi_api.ssi_client --samples   # B1.2: gọi thử 1 ngày mỗi hàm, lưu JSON gốc vào docs/api_samples/
python -m src.data.backfill                  # B1.8–B1.11: tải từ history.start_date (01/01/2016) đến phiên gần nhất (lần đầu lâu, có điểm dừng)
python -m src.data.rebuild_all               # raw → fact → chỉ báo → sự kiện, DiD, kiểm định → watchlist → chạy lại cảnh báo
streamlit run src/app/main.py

python -m src.data.recorder_ssi              # B1.4b/B5.9: ghi luồng WebSocket SSI V3 mỗi phiên 8:55–15:05 vào raw_stream
python -m src.data.recorder_ssi --seconds 60 # ghi thử 60 giây
python -m src.bot.bot                        # B10: bot Telegram (/market /leaders /foreign /watch /report /status)
```

### 4.2a. Cập nhật dữ liệu mới liên tục

```bash
python -m src.data.updater --status          # dữ liệu đang tới phiên nào, có thiếu phiên không
python -m src.data.updater                   # TẢI BÙ mọi phiên thiếu (từ điểm dừng) + dựng lại chỉ báo, kiểm định, triển vọng
python -m src.data.scheduler                 # chạy liên tục: tải bù khi khởi động · 8:55 bộ ghi · 11:35 Snapshot ·
                                             # 15:05 cập nhật (lỗi → thử lại mỗi 30') · 15:15 Closing + Telegram · 22:00 dự phòng
powershell -ExecutionPolicy Bypass -File tools\install_windows_task.ps1   # đăng ký chạy nền khi đăng nhập Windows
powershell -ExecutionPolicy Bypass -File tools\install_windows_task.ps1 -Uninstall
```

Máy tắt nhiều ngày vẫn đủ dữ liệu: lần chạy kế tiếp tự lấp các phiên còn thiếu. Ngày lễ không xuất báo cáo cũ.
Hai tiến trình không thể cập nhật chồng nhau (khóa `data/.update.lock`). Trạng thái: `logs/last_update.json`,
trang **Kết nối dữ liệu** (nút *Cập nhật dữ liệu mới*).

Khi kho chỉ báo còn trống, ứng dụng chỉ mở trang **Kết nối dữ liệu** (chẩn đoán API SSI, nút chạy nền
các tác vụ trên) và trang **Phương pháp & giới hạn** – không bao giờ hiển thị số liệu giả.

### 4.2b. Người chấm không có khóa

`data_sample/` chứa 10 phiên **dữ liệu thật** trích từ kho (`python -m src.data.sample_data export`).
Nạp và chạy: `python -m src.data.sample_data load && streamlit run src/app/main.py`.

### 4.3. Kiểm thử

```bash
python -m pytest                             # kiểm thử công thức trên kho TẠM (bộ dữ liệu kiểm thử chỉ nằm trong tests/fixtures), không cần mạng/khóa
python tools/make_test_summary.py            # docs/test_summary.csv + độ phủ (finance + analytics ≈ 83%)
python -m src.data.rebuild_all --hash        # CHỈ in mã băm kết quả hiện có trong kho (không dựng lại); chạy rebuild_all hai lần rồi so hash để kiểm tra tái lập (B12.3)
```

## 5. Cấu trúc thư mục

```
├── README.md · requirements.txt · .env.example · pytest.ini
├── config/            settings.yaml (MỌI tham số, ngưỡng) · data_dictionary.yaml · events.csv · ftse_universe.csv
│                      · stock_groups.csv · control_group.csv (sinh tự động, B6.1)
├── src/
│   ├── common/        config.py · logging.py (mask_secrets) · timeutil.py · fmt.py (định dạng số dùng chung 3 kênh)
│   ├── ssi_api/       ssi_client.py (FastConnect V3 REST: token, giãn cách, thử lại, phân trang, chuẩn hóa giá điều chỉnh)
│   ├── data/          schema.sql · database.py · backfill.py · recorder_ssi.py (WebSocket V3)
│   │                  build_facts.py · quality.py · diagnostics.py · sample_data.py · scheduler.py · rebuild_all.py
│   ├── finance/       breadth.py (1–3) · contribution.py (4–5) · foreign_flow.py (6–8) · domestic.py · utils.py
│   ├── analytics/     pipeline.py · event_study.py (9–10) · did.py (11) · stats_tests.py · watchlist_impact.py (12–13)
│   │                  alerts.py · narrative.py · health.py · news.py
│   ├── app/           main.py · theme.py · data_access.py · components/ · views/ (8 trang + Kết nối dữ liệu)
│   ├── reports/       context.py · pdf_base.py · snapshot.py · closing.py
│   └── bot/           bot.py · messages.py · jobs.py · telegram_api.py
├── tests/             kiểm thử công thức, không nhìn trước, sự kiện, cảnh báo, vận hành, tích hợp
├── tools/             make_test_summary.py
├── data_sample/       10 phiên dữ liệu THẬT (bảng raw_*) xuất từ kho – sample_data.py export/load
├── docs/              api_samples/ · notes/ · test_summary.csv · robustness_table.csv
├── report/            khung báo cáo cuối kỳ 10 phần
└── assets/fonts/      Be Vietnam Pro (giấy phép OFL)
```

## 6. Tám trang của ứng dụng

| Nhóm | Trang | Nội dung chính |
|---|---|---|
| Thị trường | 1. Tổng quan | Thanh trạng thái · giới thiệu · 4 thẻ chỉ số · chất lượng xu hướng (MỚI) · dải watchlist · nến + mốc FTSE + sức khỏe · mã dẫn dắt (MỚI) · độ rộng có trần/sàn · bản đồ nhiệt & ngành · dòng vốn khối ngoại (MỚI) · cổ phiếu nổi bật · so sánh hiệu suất |
| | 2. Dẫn dắt & độ vênh | Thác nước C theo mã/ngành · chuỗi D với dải phân vị 10–90 · chỉ số loại trừ họ cổ phiếu · phân phối CR5 · lịch loại phiên |
| Dòng vốn | 3. Ra-đa khối ngoại | Xếp hạng NF, nf, z, chuỗi, U, hấp thụ · HHI · dòng vốn theo nhóm FTSE/VN30/đối chứng/ngành · tỷ lệ hấp thụ |
| | 4. Sự kiện FTSE | CAAR, CAFF hai nhóm có dải tin cậy · bảng kiểm định (t, BMP, dấu tổng quát, Welch, Mann–Whitney, Holm) · DiD + đồ thị hệ số tuần |
| Cá nhân | 5. Watchlist Impact | Quản lý 5–10 mã · hồ sơ phản ứng · hiệu suất chuẩn hóa · phản ứng theo loại phiên · tin liên quan (nguồn ngoài) |
| | 6. Báo cáo & Telegram | Xuất Snapshot/Closing · tải PDF · cấu hình cảnh báo · nhật ký cảnh báo |
| Hệ thống | 7. Chất lượng dữ liệu | Trạng thái nguồn SSI · nhật ký sự cố · độ đầy đủ · ε · đối chiếu độ rộng · luồng WebSocket SSI · đối chiếu luồng ↔ REST · xuất CSV |
| | 8. Phương pháp & giới hạn | Công thức (1)–(13) · tham số đọc trực tiếp settings.yaml · kết quả kiểm định · độ vững · giới hạn · mã kế thừa |

## 7. Mã kế thừa từ đồ án giữa kỳ

Nguồn: kho [`web_phantichchungkhoan`](https://github.com/MinhChau536/web_phantichchungkhoan). Phần kế thừa được ghi nguồn ở đầu tệp và liệt kê tại trang 8.

| Thành phần giữa kỳ | Vị trí bản 3.2 | Mức tái sử dụng |
|---|---|---|
| `data/providers/base_provider.py` | `src/ssi_api/base_provider.py` | Giữ khuôn |
| `data/database.py` | `src/data/database.py` | Ý tưởng, viết lại theo lược đồ mới |
| `core/thi_truong_danh_muc.py` (breadth_stats, sector_performance, index_card, period_returns, market_health, rsi, WatchlistService) | `src/finance/breadth.py`, `src/analytics/health.py`, `src/analytics/watchlist_impact.py` | Giữ logic, đổi nguồn, đổi trọng số |
| `giao_dien/thi_truong.py` (render, _index_chart, _treemap, _sector_bars, _gauge, _breadth_block, _movers_table, _spark, _returns_table) | `src/app/views/p1_tong_quan.py`, `src/app/components/` | Giữ thứ tự khối & khung, đổi bảng màu |
| `_pal()` rải rác, `assets/styles/main_style.py` | `src/app/theme.py` | Viết lại – một nguồn màu cho CSS, Plotly, PDF |
| `reports/pdf_generator.py`, `reports/cover.py`, `assets/fonts/` | `src/reports/`, `assets/fonts/` | Giữ khung & font |
| `core/tin_tuc.py` | `src/analytics/news.py` | Rút gọn (Google News RSS), nhãn nguồn ngoài |
| `components/background_fx.py` | — | Tắt (B4.3) |

**Phần viết mới**: toàn bộ tầng SSI FastConnect V3 (REST + WebSocket), lược đồ & chuỗi xử lý, Module A–D, nghiên cứu sự kiện & DiD, kiểm định, cảnh báo, nhận định, 7 trang mới, 2 mẫu PDF, bot, kiểm thử.

## 8. Trạng thái so với hướng dẫn từng bước (CSV v3)

| Nhóm bước | Trạng thái |
|---|---|
| B0.3–B0.6 khung dự án, bí mật, tham số tập trung | ✅ Hoàn thành |
| B0.1–B0.2 tạo khóa SSI FastConnect V3 | ✅ API Key/Secret tạo trên Developer Portal, kết nối REST + WebSocket thành công |
| B1.1, B1.4, B1.7–B1.12 kết nối, lược đồ, backfill, nhật ký | ✅ Chạy với khóa thật SSI V3; kiểm thử bằng phiên HTTP giả |
| B1.2–B1.3 xác minh API, từ điển dữ liệu | ✅ Tên trường V3 đối chiếu với phản hồi thật (`verified: true`) |
| B1.4b, B5.9 bộ ghi WebSocket SSI V3 | ✅ Đã ghi thử luồng thật · ⏳ cần ≥ 10 phiên ghi |
| B1.6 events, ftse_universe, stock_groups | ✅ Có tệp · ⏳ **danh sách FTSE là DỰ KIẾN (`verified=false`) – phải đối chiếu thông báo FTSE Russell** |
| B2–B3, B5, B6, B7, B8 chất lượng, Module A–D, cảnh báo | ✅ Hoàn thành, có kiểm thử |
| B4, B9, B10, B11 giao diện 8 trang, PDF, bot, trang hệ thống | ✅ Hoàn thành · PDF có tóm tắt điều hành, tổng quan thị trường (sức khỏe, độ rộng mở rộng, hiệu suất kỳ, ngành, cổ phiếu nổi bật), diễn biến 5/20 phiên, triển vọng thống kê (`src/analytics/outlook.py`) và bối cảnh nâng hạng (H4) |
| B12.1–B12.5, B12.8 kiểm thử | ✅ 92 kiểm thử qua, độ phủ ≈ 83% |
| B12.6 đối chiếu nguồn ngoài, B12.7 luồng ↔ REST trên dữ liệu thật | ⏳ cần các phiên có ghi luồng (mẫu ghi chú ở `docs/notes/`) |
| B13.1–B13.2 README, dữ liệu mẫu | ✅ |
| B13.3–B13.7 báo cáo, video, rà soát bảo mật, nộp bài, chuẩn bị bảo vệ | 📝 Khung & ghi chú sẵn trong `report/`, `docs/notes/` – sinh viên hoàn thiện trên dữ liệu thật |

## 9. Giới hạn

- Vốn hóa xấp xỉ bằng số cổ phiếu niêm yết (chưa điều chỉnh cổ phiếu quỹ, free-float) → C là xấp xỉ; chất lượng đo bằng ε hằng ngày (mục tiêu trung vị |ε| < 0,5 điểm, có hệ số hiệu chỉnh k).
- Chỉ tách được khối ngoại; mua ròng khối nội = − bán ròng khối ngoại nên không dựng chỉ số "dòng tiền nội" riêng.
- Tương quan không phải nhân quả; nghiên cứu sự kiện có mẫu nhỏ (~27 mã) và các mốc trùng biến động vĩ mô.
- Giá lịch sử của SSI V3 (`securitiesSummary`) đã điều chỉnh quyền; giá tham chiếu/trần/sàn (`masterdata`, giá gốc) được quy về cùng thang bằng hệ số k = close / (ref gốc + priceChange), nên lợi suất ngày khớp % thay đổi chính thức. Phiên cũ không có priceChange dùng priceChangePercentage; ~42 nghìn dòng (chủ yếu 2016–2019) thiếu cả hai → ref điều chỉnh = close điều chỉnh phiên trước của chính mã. Sau xử lý, trung vị |ε| toàn kỳ 2016–2026 ≈ 0,35 điểm, nhưng 2016–2018 còn ≈ 0,5–0,56 điểm (nên ưu tiên 2019+ cho các phép đo dựa trên C).
- `securitiesSummary` có khối ngoại mua/bán theo mã cho cả lịch sử (đã kiểm tra từ 04/2025).

## 10. Giấy phép dữ liệu

Dữ liệu thị trường thuộc SSI, chỉ dùng cho mục đích học thuật theo điều khoản của nhà cung cấp; kho mã không phân phối dữ liệu thật. Font Be Vietnam Pro theo SIL Open Font License (`assets/fonts/OFL.txt`).
