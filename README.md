# FTSE Flow Radar 3.2

**Phân tích độ vênh chỉ số, cổ phiếu dẫn dắt và dòng vốn ngoại trên HOSE trong giai đoạn nâng hạng FTSE – web Streamlit, báo cáo PDF và bot Telegram, dữ liệu thật từ SSI FastConnect V3.**

Đồ án cá nhân cuối kỳ – *Gói phần mềm ứng dụng cho tài chính 1*, Trường ĐH Kinh tế – Luật (ĐHQG-HCM). Sinh viên: Lê Ngọc Minh Châu.

> 🎓 **Đề tài nghiên cứu học thuật, không mang tính chất khuyến nghị đầu tư.** Hệ thống chỉ đọc dữ liệu, không đặt lệnh.

---

## 1. Chạy nhanh (web + bot)

Yêu cầu: Windows 10/11, Python 3.12, Git.

```powershell
git clone https://github.com/MinhChau536/Rada-dong-von-ngoai-va-do-venh-thi-truong.git
cd Rada-dong-von-ngoai-va-do-venh-thi-truong
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env          # rồi điền khóa vào .env (xem bảng dưới)
python run.py                   # cập nhật dữ liệu → chạy bot (nếu có token) → mở web http://localhost:8501
```

`run.py` **cập nhật dữ liệu trước rồi mới mở web**: trong giờ giao dịch nó bật bộ ghi luồng SSI và chờ số liệu trong phiên đầu tiên; ngoài giờ nó tải phiên đã đóng cửa còn thiếu. Khi đường link hiện ra là số liệu đã mới. Dừng: `Ctrl + C`.

| Biến trong `.env` | Ý nghĩa |
|---|---|
| `SSI_API_KEY`, `SSI_API_SECRET` | Khóa SSI FastConnect V3 – tạo tại [developers.ssi.com.vn](https://developers.ssi.com.vn) › Quản lý API Key (nhóm Market Data, không cần OTP) |
| `TELEGRAM_BOT_TOKEN` | Token bot riêng của bạn – tạo bằng @BotFather (`/newbot`) |
| `TELEGRAM_CHAT_IDS` | chat_id được phép dùng bot, cách nhau bằng dấu phẩy (gửi `/start` cho @userinfobot để biết chat_id). Để trống = bot không trả lời ai |

`.env` nằm trong `.gitignore`, không đẩy lên GitHub. Không có khóa SSI vẫn xem được dữ liệu đi kèm (`data/snapshot/`, tự dựng kho ở lần chạy đầu).

**Chạy riêng từng phần**

| Việc | Lệnh |
|---|---|
| Chỉ web | `streamlit run src/app/main.py` |
| Chỉ bot Telegram | `python -m src.bot.bot` |
| Tải phiên mới + tính lại chỉ báo | `python -m src.data.updater` |
| Dựng lại toàn bộ từ dữ liệu gốc | `python -m src.data.rebuild_all` |
| Xuất PDF | `python -m src.reports.closing` · `python -m src.reports.snapshot` |
| Kiểm thử | `python -m pytest` |
| **Bật lịch tự động hằng ngày** (Task Scheduler) | `python tools/schedule_windows.py` (`--status`, `--remove`) |

> Lỗi *"running scripts is disabled"* khi kích hoạt `.venv`: chạy `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

---

## 2. Dữ liệu cập nhật theo giờ

Nguồn duy nhất là **SSI FastConnect V3**: REST (`securitiesSummary`, `masterdata`, `indexSummary`, `ohlc`, `securities`) và WebSocket V3. Không có dữ liệu giả lập.

| Giờ (thứ 2 – thứ 6) | Web / PDF / bot hiển thị | Nguồn |
|---|---|---|
| 08:50 | Bộ ghi luồng tự khởi động (Task Scheduler, hoặc khi mở web/bot) | – |
| **09:00 – 15:00** | Phiên tạm tính, **cập nhật ~2 phút/lần**, nhãn ● TRỰC TIẾP, web tự làm mới | WebSocket (khớp lệnh cả sàn HOSE, room/khối ngoại, tổng hợp chỉ số) |
| **15:05 – 15:15** | Chốt phiên bằng giá sau ATC, tính lại toàn bộ chỉ báo – **đủ kết quả trước 15:15**, nhãn ● ĐÓNG CỬA TẠM TÍNH | WebSocket (nguồn `SSI-WS`) |
| Khi SSI công bố số cuối ngày | Tự tải và thay bản tạm tính bằng số liệu chính thức | REST (nguồn `SSI`, ưu tiên cao hơn) |
| Ngoài giờ | Giá đóng cửa phiên gần nhất | Kho DuckDB |

Máy tắt nhiều ngày vẫn đủ dữ liệu: lần chạy sau tự lấp mọi phiên thiếu. Luồng WebSocket thì không tải bù được – cần máy bật trong giờ giao dịch.

Kho `data/ffr.duckdb`: `raw_*` (JSON gốc SSI) → `fact_*` → `indicator_*` → `stats_results`, `alert_*`. Ngành theo mã **ICB do SSI trả về**; danh sách 27 mã FTSE và các mốc sự kiện lấy từ thông báo của FTSE Russell (ghi nguồn trong `config/ftse_universe.csv`, `config/events.csv`). Tham số phân tích: `config/settings.yaml`.

---

## 3. Ứng dụng web

| Nhóm | Trang | Nội dung chính |
|---|---|---|
| **Diễn biến thị trường** | Tổng quan thị trường | 4 chỉ số, chất lượng xu hướng + kết luận phiên, nến + MA + mốc FTSE, thanh khoản, độ rộng, ngành, bản đồ nhiệt, cổ phiếu nổi bật, watchlist |
| | Dẫn dắt & độ vênh | Đóng góp điểm theo mã/ngành/họ, độ vênh D có dải phân vị, CR5, chỉ số loại trừ họ Vingroup |
| | Ra-đa khối ngoại | NF, z60, HHI, FPR, xếp hạng mua/bán ròng, lũy kế theo nhóm, chiều giá – ngoại |
| **Phân tích chuyên sâu** | Nâng hạng FTSE | Mốc sự kiện, 27 mã chính thức, CAAR FTSE vs đối chứng, DiD, kiểm định đầy đủ (BMP, Kolari–Pynnönen, Welch, Holm) |
| | Chẩn đoán thị trường | Kết luận + khuyến nghị cấp thị trường, phân tích kỹ thuật (MA, Dow, RSI, MACD, khối lượng), cấu trúc dòng vốn, kịch bản hỗ trợ/kháng cự, chẩn đoán phiên 5 bước |
| **Danh mục & tiện ích** | Watchlist Impact · Báo cáo PDF · Bot Telegram | Phản ứng từng mã so với thị trường, xuất PDF, giới thiệu bot + tin mẫu |
| **Hệ thống** | Kiểm chứng & dữ liệu · Phương pháp & giới hạn | Backtest cảnh báo và biên dao động, chất lượng dữ liệu, kết nối SSI; công thức (1)–(17), tham số, giới hạn |

**Báo cáo PDF** (Closing Report cuối phiên, Market Snapshot trong phiên): bìa · mục lục + tóm tắt điều hành · 1. Tổng quan thị trường · 2. Dẫn dắt và độ vênh · 3. Dòng vốn ngoại · 4. Bối cảnh nâng hạng FTSE · 5. Chẩn đoán thị trường · 6. Tác động lên watchlist · 7. Kết luận, hàm ý và khuyến nghị · 8. Phụ lục phương pháp.

**Bot Telegram**: menu nút bấm (Thị trường, Dẫn dắt, Khối ngoại, Chẩn đoán phiên, Watchlist, PDF…), gõ mã để xem thẻ phân tích, cảnh báo tự động 2 phút/lần trong phiên (`/alerts` để cài độ nhạy, nút "Cơ chế cảnh báo" giải thích ngưỡng), bản tin 11:35 và 15:15.

---

## 4. Cấu trúc thư mục

```
run.py                  khởi động một lệnh: cập nhật dữ liệu → bot → web
config/                 settings.yaml · data_dictionary.yaml · ftse_universe.csv · events.csv · stock_groups.csv
src/ssi_api/            SSI FastConnect V3 REST (giới hạn tần suất, thử lại)
src/data/               backfill · updater · recorder_ssi (WebSocket) · live (phiên tạm tính) · build_facts · quality
src/finance/            độ rộng, đóng góp điểm, dòng vốn ngoại, ngành ICB
src/analytics/          pipeline chỉ báo · event_study · did · stats_tests · technical · diagnosis · alerts · watchlist
src/app/                web Streamlit (views/, components/)
src/reports/            PDF (fpdf2 + matplotlib)
src/bot/                bot Telegram, cảnh báo tự động
tools/                  schedule_windows.py · snapshot.py
tests/                  kiểm thử tự động (pytest)
data/snapshot/          dữ liệu SSI đã tải (Parquet) để chạy ngay khi clone
```

---

## 5. Giới hạn

- Vốn hóa xấp xỉ bằng số cổ phiếu niêm yết (chưa trừ cổ phiếu quỹ, free-float); sai số tái lập chỉ số đo hằng ngày bằng ε.
- Chỉ tách được khối ngoại; ròng khối nội = − ròng khối ngoại.
- Tương quan cùng phiên không phải nhân quả; nghiên cứu sự kiện mẫu nhỏ (27 mã), giai đoạn sau hiệu lực còn ngắn.
- Chỉ báo kỹ thuật mô tả trạng thái, không dự báo hướng đi; khuyến nghị chỉ ở cấp thị trường theo quy tắc cố định.
- Phiên tạm tính từ WebSocket chỉ đầy đủ khi bộ ghi chạy từ đầu phiên; bản REST chính thức luôn thay thế sau đó.
- SSI FastConnect không cung cấp định giá (P/E, P/B) hay số liệu vĩ mô nên hệ thống không dùng.

## 6. Xử lý sự cố

| Hiện tượng | Cách xử lý |
|---|---|
| Web báo "Chưa có phiên tạm tính" trong giờ giao dịch | Chờ 1–2 phút; kiểm tra `logs/job_recorder.log` |
| Bot không trả lời | Thêm chat_id vào `TELEGRAM_CHAT_IDS`; báo *Conflict* = đang có bot khác dùng cùng token |
| "Đang có tiến trình cập nhật khác" | Một lần cập nhật đang chạy; khóa quá 3 giờ tự gỡ |
| Closing Report không xuất | Xem lý do trên trang Báo cáo PDF (chưa có dữ liệu phiên hoặc kiểm tra chất lượng chưa đạt) |

Dữ liệu thị trường thuộc SSI, chỉ dùng cho mục đích học thuật. Font Be Vietnam Pro theo SIL Open Font License.
