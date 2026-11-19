# FTSE Flow Radar 3.2

**Hệ thống phân tích độ vênh, cổ phiếu dẫn dắt và dòng vốn ngoại trên thị trường chứng khoán Việt Nam trong giai đoạn nâng hạng FTSE, kèm tác động lên danh mục theo dõi, báo cáo PDF và bot Telegram.**

Đồ án cá nhân cuối kỳ, học phần *Gói phần mềm ứng dụng cho tài chính 1*, Trường ĐH Kinh tế – Luật (ĐHQG-HCM).
Sinh viên: Lê Ngọc Minh Châu.

> 🎓 **Đề tài nghiên cứu học thuật, không mang tính chất khuyến nghị đầu tư.** Hệ thống chỉ đọc dữ liệu, không đặt lệnh và không khẳng định quan hệ nhân quả. Lời nhắc này xuất hiện trên mọi trang của ứng dụng, mọi trang PDF và mọi tin nhắn bot.

---

## Mục lục

1. [Dự án trả lời câu hỏi gì](#1-dự-án-trả-lời-câu-hỏi-gì)
2. [Chạy nhanh](#2-chạy-nhanh)
3. [Cài đặt chi tiết](#3-cài-đặt-chi-tiết)
4. [Các lệnh vận hành](#4-các-lệnh-vận-hành)
5. [Dữ liệu và cập nhật tự động](#5-dữ-liệu-và-cập-nhật-tự-động)
6. [Ứng dụng web](#6-ứng-dụng-web)
7. [Báo cáo PDF](#7-báo-cáo-pdf)
8. [Bot Telegram](#8-bot-telegram)
9. [Kết quả kiểm chứng (backtest)](#9-kết-quả-kiểm-chứng-backtest)
10. [Kiến trúc và cấu trúc thư mục](#10-kiến-trúc-và-cấu-trúc-thư-mục)
11. [Kiểm thử](#11-kiểm-thử)
12. [Giới hạn](#12-giới-hạn)
13. [Mã kế thừa từ đồ án giữa kỳ](#13-mã-kế-thừa-từ-đồ-án-giữa-kỳ)
14. [Xử lý sự cố thường gặp](#14-xử-lý-sự-cố-thường-gặp)
15. [Giấy phép](#15-giấy-phép)

---

## 1. Dự án trả lời câu hỏi gì

| Câu hỏi nghiên cứu | Chỉ báo chính | Trang web |
|---|---|---|
| **RQ1** – VN-Index tăng/giảm có lan tỏa đến số đông cổ phiếu không? Bao nhiêu mã tạo ra phần lớn biến động? | Độ vênh D, AD, IQR, loại phiên, đóng góp điểm C, CR5, sai số tái lập ε | Tổng quan · Dẫn dắt & độ vênh |
| **RQ2** – Dòng vốn ngoại tập trung vào đâu, có đi cùng giá không, khối nội phản ứng ra sao? | NF, nf, FPR, HHI, z60, chuỗi mua/bán, trạng thái ngoại – nội | Tổng quan · Ra-đa khối ngoại |
| **RQ3** – Quanh các mốc FTSE (E1 08/10/2025, E2 08/04/2026, E3 18/09/2026), nhóm vào rổ có bất thường so với nhóm đối chứng không? | AR, CAR, CAAR, AFF, AVol, DiD | Sự kiện FTSE |
| **RQ4** – Các mã trong watchlist phản ứng thế nào? | ER so với chỉ số và trung vị, β Dimson, phản ứng theo loại phiên (kiểm định trên ER), mức phơi nhiễm với nhóm dẫn dắt | Watchlist Impact |
| **RQ5** – Cấu trúc thị trường thay đổi thế nào qua ba giai đoạn (250 phiên trước E1 / E1 → hiệu lực / sau hiệu lực)? | Kiểm định H4: OLS Newey–West, p hiệu chỉnh Holm, MDE | Phương pháp · PDF |

Ba kênh **web, PDF và Telegram** cùng đọc một kho chỉ báo (`indicator_*`) và một bộ định dạng số (`src/common/fmt.py`), nên con số luôn khớp nhau giữa các kênh.

---

## 2. Chạy nhanh

Yêu cầu: **Windows 10/11 · Python 3.12 · Git**. Không cần khóa SSI để xem dữ liệu đã có.

```powershell
git clone https://github.com/MinhChau536/Rada-dong-von-ngoai-va-do-venh-thi-truong.git
cd Rada-dong-von-ngoai-va-do-venh-thi-truong
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run src/app/main.py
```

Trình duyệt tự mở `http://localhost:8501`.

- **Lần chạy đầu tiên**, kho `data/ffr.duckdb` được dựng tự động từ `data/snapshot/` (Parquet, khoảng 15–30 giây). Dữ liệu thật đi kèm gồm 04/01/2016 → 13/11/2026, khoảng 2.700 phiên và 490 mã HOSE.
- **Nếu có khóa SSI** trong `.env`, app tự tải thêm các phiên mới khi khởi động (xem [mục 5](#5-dữ-liệu-và-cập-nhật-tự-động)).
- Dừng app: nhấn `Ctrl + C` trong terminal.

> Gặp lỗi *"running scripts is disabled"* khi kích hoạt `.venv`: chạy một lần `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` rồi kích hoạt lại.

---

## 3. Cài đặt chi tiết

### 3.1. Môi trường

```powershell
python --version                 # cần 3.12.x
python -m venv .venv
.venv\Scripts\activate           # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

Thư viện chính: `streamlit`, `pandas`, `duckdb`, `plotly`, `scipy`, `statsmodels`, `linearmodels`, `fpdf2`, `matplotlib`, `python-telegram-bot`, `ssi-sdk` (SDK chính thức SSI FastConnect V3).

### 3.2. Tệp cấu hình `.env`

Ứng dụng đọc `.env`. Nếu chưa có `.env`, ứng dụng dùng `.env.example` đi kèm mã nguồn. Muốn dùng khóa riêng, sao chép `.env.example` thành `.env` rồi điền:

| Biến | Ý nghĩa | Bắt buộc? |
|---|---|---|
| `SSI_API_KEY`, `SSI_API_SECRET` | Khóa **SSI FastConnect V3** tạo tại [developers.ssi.com.vn](https://developers.ssi.com.vn) › Quản lý API Key, nhóm quyền Market Data. Không cần Private Key, không cần OTP. | Chỉ khi muốn tải phiên mới |
| `SSI_BASE_URL`, `SSI_STREAM_URL` | Mặc định `https://api.ssi.com.vn` và `wss://stream.ssi.com.vn/ws/v3` | Không |
| `TELEGRAM_BOT_TOKEN` | Token bot từ @BotFather. `.env.example` có sẵn token bot @FTSERadar_bot của tác giả. | Chỉ khi chạy bot |
| `TELEGRAM_CHAT_IDS` | Danh sách chat_id được phép, cách nhau bằng dấu phẩy | Chỉ khi chạy bot |
| `LOG_LEVEL` | Mức nhật ký, mặc định `INFO` | Không |

`.env` nằm trong `.gitignore` và không bao giờ được đẩy lên GitHub. Nhật ký đi qua `mask_secrets` nên không ghi token hay API Secret.

### 3.3. Tham số phân tích

Mọi ngưỡng và tham số nằm tập trung trong **`config/settings.yaml`**, ví dụ: ngưỡng cảnh báo, lịch chạy, lambda EWMA, chi phí giao dịch dùng trong backtest. Trang **Phương pháp & giới hạn** đọc trực tiếp tệp này nên luôn hiện đúng giá trị đang dùng.

---

## 4. Các lệnh vận hành

Mọi lệnh chạy ở thư mục gốc dự án, sau khi đã `.venv\Scripts\activate`.

### Lệnh thường dùng

| Mục đích | Lệnh |
|---|---|
| **Mở ứng dụng web** | `streamlit run src/app/main.py` |
| **Chạy bot Telegram** (mở terminal riêng) | `python -m src.bot.bot` |
| **Chạy nền cả ngày** (tự cập nhật, ghi luồng, gửi báo cáo) | `python -m src.data.scheduler` |
| Xem kho đang có dữ liệu tới phiên nào | `python -m src.data.updater --status` |
| Tải bù phiên thiếu + dựng lại chỉ báo ngay | `python -m src.data.updater` |
| Chạy kiểm thử | `python -m pytest` |

### Kiểm tra kết nối SSI

```powershell
python -m src.data.diagnostics      # lấy token + gọi thử REST securitiesSummary + mở WebSocket V3
python -m src.ssi_api.ssi_client    # in số mã HOSE
```

### Tải và dựng dữ liệu từ đầu

```powershell
python -m src.data.backfill         # tải từ 01/01/2016 đến phiên gần nhất (lần đầu lâu, có điểm dừng)
python -m src.data.rebuild_all      # raw → fact → chỉ báo → sự kiện, DiD, kiểm định → watchlist → cảnh báo
```

### Bộ ghi luồng WebSocket SSI V3

```powershell
python -m src.data.recorder_ssi               # ghi trong khung 08:55–15:05 vào bảng raw_stream
python -m src.data.recorder_ssi --seconds 60  # ghi thử 60 giây (bỏ qua khung giờ)
```

### Ảnh chụp dữ liệu (snapshot) đi kèm mã nguồn

```powershell
python -m tools.snapshot restore    # dựng lại data/ffr.duckdb từ data/snapshot (app tự làm khi thiếu kho)
python -m tools.snapshot export     # tác giả cập nhật ảnh chụp trước khi đẩy lên GitHub
```

### Chạy nền khi đăng nhập Windows

```powershell
powershell -ExecutionPolicy Bypass -File tools\install_windows_task.ps1              # đăng ký
powershell -ExecutionPolicy Bypass -File tools\install_windows_task.ps1 -Uninstall   # gỡ
```

---

## 5. Dữ liệu và cập nhật tự động

**Nguồn duy nhất:** SSI FastConnect V3, gồm REST `securitiesSummary`, `masterdata`, `indexSummary`, `ohlc` (ngày và trong phiên) và WebSocket V3. Ứng dụng **chỉ dùng dữ liệu thật**, không có chế độ giả lập. Khi kho trống, ứng dụng chỉ mở trang *Kết nối dữ liệu* và *Phương pháp & giới hạn*, không vẽ số liệu giả.

### Cập nhật tự động

| Khi nào | Việc gì xảy ra |
|---|---|
| **Mở app web hoặc bot** | Nếu kho thiếu phiên đã đóng cửa gần nhất, app tự chạy `src.data.updater` ở **tiến trình nền**. Trong lúc đó app vẫn dùng được, đầu trang hiện dòng 🔄. Khi app đang mở, cứ **30 phút** kiểm tra lại một lần. |
| **Mở app/bot trong giờ giao dịch** (08:55–15:05, thứ Hai – thứ Sáu) | Tự bật bộ ghi luồng WebSocket SSI V3 tới hết phiên, mỗi ngày một lần |
| **Bộ lập lịch** `src.data.scheduler` | Tải bù khi khởi động · 08:55 bộ ghi · 11:35 Market Snapshot · 15:05 cập nhật (lỗi thì thử lại mỗi 30 phút) · 15:15 Closing Report + Telegram · 22:00 lượt dự phòng |

- Máy tắt nhiều ngày vẫn đủ dữ liệu, vì lần chạy kế tiếp tự lấp mọi phiên còn thiếu.
- Phiên mà SSI chưa công bố khối ngoại được tải lại ở các lần sau cho tới khi có số liệu.
- Tệp khóa `data/.update.lock` bảo đảm không bao giờ có hai lần cập nhật chồng nhau, kể cả khi app, bot và bộ lập lịch cùng chạy.
- Lần dựng lại toàn bộ đầu tiên mất khoảng 15–20 phút. Nhật ký nằm ở `logs/job_autoupdate.log` và `logs/last_update.json`.

### Kho dữ liệu (DuckDB)

`raw_*` (JSON gốc) → `fact_daily_stock`, `fact_daily_index`, `fact_intraday`, `dim_*` → `indicator_daily`, `indicator_stock_daily`, `indicator_group_daily`, `leaders_daily`, `indicator_intraday` → `data_quality_log`, `stats_results`, `alert_*`, `reports_log`.

### Chất lượng dữ liệu (đo trên toàn kỳ)

| Kiểm tra | Kết quả |
|---|---|
| Độ đầy đủ các trường chính | **99,85%**, chỉ 3 phiên dưới mục tiêu 98% |
| Tái lập VN-Index từ đóng góp từng mã (ε) | Trung vị **0,34 điểm**, mục tiêu ≤ 0,5 |
| Số mã tăng/giảm khớp SSI (lệch ≤ 2 mã) | 73% số phiên có đối chiếu. Phần lệch chủ yếu do SSI đếm cả CCQ/ETF, khác rổ cổ phiếu thường của dự án |

---

## 6. Ứng dụng web

Giao diện dạng **lưới thẻ** (kiểu các cổng thông tin chứng khoán): mỗi thẻ có tiêu đề và thanh tab. Có chế độ Sáng/Tối và hình nền tùy chọn trong mục **Giao diện** ở thanh bên. Ô **Tra cứu mã** ở thanh bên mở hồ sơ mã trong Watchlist Impact.

| Nhóm | Trang | Nội dung chính |
|---|---|---|
| **Thị trường** | Tổng quan thị trường | 4 thẻ chỉ số HOSE (VN-Index), VN30, HNX, UPCoM · chất lượng xu hướng và kết luận phiên · Top 10 cổ phiếu (tăng/giảm/GTGD/KL đột biến, lọc GTGD ≥ 10 tỷ) · nhóm dẫn dắt · nến + MA + mốc FTSE · khối ngoại mua/bán ròng, diễn biến mua – bán – ròng · thanh khoản · độ rộng · biến động ngành · bản đồ thị trường theo ngành · cổ phiếu nổi bật · so sánh hiệu suất · danh mục theo dõi (cuối trang). Mọi bảng hiển thị sẵn, không cần mở rộng |
| | Chẩn đoán thị trường | Phiên hôm nay qua 5 bước (lan tỏa · ai tạo biến động · khối ngoại có đứng sau không · phần còn lại của thị trường · watchlist) · % biến động có ngoại cùng chiều · đóng góp điểm của 27 mã FTSE · 7 câu hỏi nghiên cứu giai đoạn FTSE · hồi quy gộp giải thích độ vênh (HAC) |
| | Dẫn dắt & độ vênh | Thác nước đóng góp theo mã/ngành · bảng đóng góp chi tiết top 15 · đóng góp theo họ cổ phiếu và ngành · chuỗi D có dải phân vị · thống kê độ vênh 5/20/60/250 phiên · chỉ số loại trừ một họ cổ phiếu · phân phối CR5 · loại phiên · mã xuất hiện nhiều nhất trong Top 5 |
| **Dòng vốn** | Ra-đa khối ngoại | Chỉ số NF, z60, HHI, FPR · top mua/bán ròng · diễn biến mua – bán – ròng · nhận định theo quy tắc · bảng xếp hạng (mua ròng, bán ròng, \|z\|, room) · khối ngoại theo ngành · lũy kế theo nhóm 1/5/20/60 phiên · chuỗi mua/bán ròng · HHI và NF lũy kế · dòng vốn theo nhóm · trạng thái hấp thụ của khối nội |
| | Sự kiện FTSE | Dòng thời gian các mốc (E1–E3, L1–L2) có giải thích · danh sách 27 mã chính thức theo quy mô · lợi suất lũy kế các nhóm từ E1 · CAAR, CAFF (FTSE, nhóm All-World, nhóm All-Cap, đối chứng) · bảng tóm tắt có kết luận · bảng kiểm định đầy đủ (t, BMP, Kolari–Pynnönen, dấu, Welch, Mann–Whitney, Holm) · DiD và hệ số theo tuần · nhóm đối chứng và kiểm tra cân bằng |
| **Danh mục & tiện ích** | Watchlist Impact | Quản lý danh mục · hồ sơ phản ứng từng mã · mức phơi nhiễm (trong nhóm dẫn dắt, họ Vingroup, β, tỷ lệ thua khi độ vênh cao) · **tab riêng từng mã**: thông tin doanh nghiệp (vốn hóa, cổ phiếu niêm yết, tỷ trọng VN-Index, room ngoại, thanh khoản), giá 250 phiên, khối ngoại 60 phiên |
| | Báo cáo PDF | Xuất Market Snapshot / Closing Report · danh sách báo cáo đã sinh, tải về |
| | Bot Telegram | Trạng thái bot · xem trước tin nhắn kèm nút bấm · gửi thử · danh sách lệnh · nhật ký cảnh báo |
| **Hệ thống** | Kiểm chứng & dữ liệu | Ba tab: **Backtest** (chống trùng cảnh báo · giá trị dự báo · biên dao động · giá trị kinh tế) · **Chất lượng** (độ đầy đủ, ε, đối chiếu độ rộng, luồng WebSocket, nhật ký lỗi, xuất CSV) · **Kết nối** SSI |
| | Phương pháp & giới hạn | Công thức (1)–(13) · tham số từ `settings.yaml` · kết quả kiểm định · giới hạn · mã kế thừa |
| | Kết nối dữ liệu | Kiểm tra SSI REST + WebSocket · các nút chạy nền: cập nhật, tải lịch sử, ghi luồng, dựng lại chỉ báo |

---

## 7. Báo cáo PDF

Hai mẫu báo cáo dùng chung bố cục: **trang bìa** (logo, 4 chỉ số, danh sách nội dung) → **mục lục** có số trang và liên kết → các chương → phụ lục. Mỗi trang có dải *"Đề tài nghiên cứu học thuật – không mang tính chất khuyến nghị đầu tư"*. Báo cáo có khoảng 15 biểu đồ, vẽ bằng matplotlib nên không cần trình duyệt.

| | **Market Snapshot** | **Closing Report** |
|---|---|---|
| Thời điểm | Trong phiên, lịch tự động 11:35 | Sau đóng cửa, lịch tự động 15:15 |
| Số liệu | Tạm thời, ghi rõ "chưa hoàn tất" | Cuối phiên, **chỉ xuất khi qua kiểm tra chất lượng** (đầy đủ ≥ 98%, độ rộng khớp SSI, \|ε\| ≤ 5 điểm) |
| Tên tệp | `FFR_snapshot_yyyymmdd_hhmm.pdf` | `FFR_closing_yyyymmdd.pdf` (mỗi phiên một tệp) |
| Độ dài | Khoảng 14 trang | Khoảng 14 trang, có thêm bảng kiểm định H4 và Watchlist đầy đủ |

**Bố cục:** bìa (kèm kết luận phiên) · mục lục + tóm tắt điều hành gồm 3 câu trả lời của phiên · 1. Chẩn đoán phiên · 2. Dòng vốn ngoại · 3. Bối cảnh nâng hạng FTSE (CAAR, câu hỏi nghiên cứu, hồi quy gộp) · 4. Tác động lên watchlist · 5. Kết luận và hàm ý (điều kiện theo ngưỡng MA20/MA50/EWMA, không chấm điểm) · 6. Thị trường chung · 7. Phụ lục phương pháp.

Mọi nhận xét trong báo cáo là phép so sánh có số cụ thể, không dùng tính từ đánh giá cảm tính. Nếu SSI chưa công bố khối ngoại cho một phiên, Closing vẫn xuất được, có ghi chú và để trống các mục khối ngoại. Tệp được lưu vào `reports_out/`.

---

## 8. Bot Telegram

```powershell
python -m src.bot.bot
```

Bot chỉ trả lời các chat_id có trong `TELEGRAM_CHAT_IDS`. Muốn bot trả lời bạn: gửi `/start` cho bot, lấy chat_id của mình (ví dụ qua @userinfobot), rồi thêm vào `.env`. Telegram chỉ cho **một tiến trình** chạy với một token; nếu có tiến trình khác đang chạy, bot báo lỗi *Conflict*.

| Lệnh | Chức năng |
|---|---|
| `/menu`, `/help` | Menu chính dạng nút bấm, hướng dẫn |
| `/market` · `/leaders` · `/foreign` · `/outlook` | Tổng quan · mã dẫn dắt · khối ngoại · triển vọng thống kê 5 và 20 phiên |
| `/stock FPT` · `/sector FPT` · `/chart FPT` · `/intra FPT` | Thẻ phân tích mã · ngành của mã · biểu đồ ngày · giá từng phút trong phiên |
| `/watch` · `/add FPT` · `/remove FPT` | Danh mục theo dõi |
| `/diag` | Chẩn đoán phiên: 3 câu trả lời và hàm ý |
| `/alerts` | Cảnh báo tự động: bật/tắt, chọn loại, độ nhạy |
| `/report` · `/status` | PDF gần nhất · tình trạng dữ liệu |
| `/legend` | Giải thích ký hiệu 🟢🔴🟡⚪ và thuật ngữ (NN ròng, CR5, D, z60, HHI…) |

Có thể gõ thẳng mã cổ phiếu (ví dụ `FPT`) để mở thẻ phân tích. Khi khởi động, bot cũng tự cập nhật phiên mới và tự bật bộ ghi luồng trong giờ giao dịch.

---

## 9. Kết quả kiểm chứng (backtest)

Mọi kiểm chứng **chỉ dùng dữ liệu quá khứ tại mỗi thời điểm** (không nhìn trước), và đều xem lại được trên trang **Backtest**. Tham số **không** được chỉnh theo kết quả.

### 9.1. Biên dao động VN-Index (2019 → 2026, khoảng 1.950 phiên)

σ được ước lượng bằng EWMA (λ = 0,94). Hệ số biên k là phân vị thực nghiệm của sai số các dự báo **đã biết kết quả**, dùng để hiệu chỉnh đuôi dày thay cho z = 1 / 1,645 của phân phối chuẩn.

| Kỳ hạn | Bao phủ biên 68% | Bao phủ biên 90% |
|---|---|---|
| 5 phiên | 68,8% | 90,9% |
| 20 phiên | 69,5% | 89,8% |

Trước khi hiệu chỉnh, biên 20 phiên chỉ bao phủ 83%.

### 9.2. Danh mục watchlist (walk-forward, 60 tháng ngoài mẫu, 07/2021 → 11/2026)

Tái cân bằng mỗi tháng chỉ bằng dữ liệu trước đó, **đã trừ chi phí 0,25%** trên doanh số tái cân bằng.

| | Lợi suất năm | Sụt giảm tối đa |
|---|---|---|
| Danh mục (đồng tỷ trọng) | 3,0% | −24% |
| Danh mục (theo khẩu vị) | 3,2% | −28% |
| VN-Index | 3,9% | −40% |

Lợi suất gần bằng thị trường nhưng **sụt giảm tối đa thấp hơn rõ rệt**.

### 9.3. Giá trị dự báo và giá trị kinh tế của tín hiệu cảnh báo (2016 → 2026)

- Sau hiệu chỉnh Holm cho 10 kiểm định, chỉ quy tắc **"Độ vênh cao"** có ý nghĩa thống kê (p Holm ≈ 0,02).
- Mô phỏng giao dịch theo tín hiệu này (mua, giữ 5 phiên, không bán khống, chi phí khứ hồi 0,4%): **1,3%/năm**, so với **9,7%/năm** khi mua và nắm giữ VN-Index. Giai đoạn 2021–2026 lỗ −3%/năm.

**Kết luận:** dữ liệu và chỉ báo mô tả đúng thị trường, biên rủi ro được hiệu chỉnh tốt, nhưng tín hiệu **không tạo lợi nhuận vượt thị trường sau chi phí**. Kết quả này phù hợp với giả thuyết thị trường hiệu quả dạng yếu. Hệ thống là công cụ mô tả và giám sát, không phải chiến lược giao dịch.

---

## 10. Kiến trúc và cấu trúc thư mục

```
 SSI FastConnect V3 – NGUỒN DUY NHẤT
 REST  https://api.ssi.com.vn/api/v3/data/*        WebSocket  wss://stream.ssi.com.vn/ws/v3
              │                                                │
              ▼                                                ▼
 Thu thập: ssi_client.py · backfill.py · updater.py · autoupdate.py · recorder_ssi.py
 (token, ≤ 20 yêu cầu/giây, thử lại 2–4–8 s, tái kết nối, khóa cập nhật)
              │
              ▼
 DuckDB: raw_* → fact_* / dim_* → indicator_* → data_quality_log, stats_results, alert_*
              │
   ┌──────────┼──────────────┬──────────────────┬───────────────────┐
   ▼          ▼              ▼                  ▼                   ▼
 Độ vênh   Dòng vốn ngoại  Sự kiện FTSE    Watchlist & danh mục   Cảnh báo · nhận định · triển vọng
   └──────────┴──────────────┴──────────────────┴───────────────────┘
              ▼
 Web Streamlit · Báo cáo PDF (fpdf2 + matplotlib) · Bot Telegram
```

```
├── README.md · requirements.txt · .env.example · pytest.ini
├── config/        settings.yaml (mọi tham số) · data_dictionary.yaml · events.csv · ftse_universe.csv
│                  · stock_groups.csv · control_group.csv
├── src/
│   ├── common/    config.py · logging.py · timeutil.py · fmt.py (định dạng số chung 3 kênh) · logo.py
│   ├── ssi_api/   ssi_client.py (REST V3) · base_provider.py
│   ├── data/      database.py · schema.sql · backfill.py · updater.py · autoupdate.py · scheduler.py
│   │              recorder_ssi.py · build_facts.py · quality.py · rebuild_all.py · diagnostics.py · sample_data.py
│   ├── finance/   breadth.py · contribution.py · foreign_flow.py · domestic.py · utils.py
│   ├── analytics/ pipeline.py · event_study.py · did.py · stats_tests.py · watchlist_impact.py · diagnosis.py
│   │              outlook.py · alerts.py · narrative.py · health.py
│   ├── app/       main.py · theme.py · data_access.py
│   │              components/ (widgets.py – thẻ dùng chung · charts.py · sidebar.py · ui.py · banners.py …)
│   │              views/ (các trang web)
│   ├── reports/   context.py · sections.py (các chương) · charts.py (biểu đồ PDF) · pdf_base.py · snapshot.py · closing.py
│   └── bot/       bot.py · messages.py · jobs.py · monitor.py · charts.py · intraday.py · telegram_api.py · runtime.py
├── tests/         kiểm thử công thức, không nhìn trước, sự kiện, cảnh báo, danh mục, vận hành, tích hợp
├── tools/         snapshot.py · make_test_summary.py · install_windows_task.ps1
├── data/snapshot/ ảnh chụp kho dữ liệu thật (Parquet nén, mỗi tệp < 50 MB)
├── data_sample/   10 phiên dữ liệu thật dạng raw_* (sample_data.py export/load)
├── docs/          api_samples/ · notes/ · test_summary.csv · robustness_table.csv
├── report/        khung báo cáo cuối kỳ
└── assets/        fonts/ (Be Vietnam Pro, OFL) · logo/ (logo ứng dụng PNG + SVG)
```

---

## 11. Kiểm thử

```powershell
python -m pytest                       # 116 kiểm thử, khoảng 1,5 phút, không cần mạng hay khóa
python tools/make_test_summary.py      # docs/test_summary.csv + độ phủ (finance + analytics ≈ 83%)
python -m src.data.rebuild_all --hash  # in mã băm kết quả để kiểm tra tính tái lập
```

Kiểm thử chạy trên kho **tạm**; bộ dữ liệu kiểm thử chỉ nằm trong `tests/fixtures`. Các nhóm kiểm thử: công thức (1)–(13), không nhìn trước (phân vị, z, walk-forward), nghiên cứu sự kiện và DiD, cảnh báo và chống trùng, tối ưu danh mục, báo cáo PDF, tin nhắn bot, bộ lập lịch và cập nhật.

---

## 12. Giới hạn

- **Vốn hóa xấp xỉ** bằng số cổ phiếu niêm yết, chưa điều chỉnh cổ phiếu quỹ và free-float, nên đóng góp C là xấp xỉ. Chất lượng được đo hằng ngày bằng ε: trung vị toàn kỳ khoảng 0,34 điểm, giai đoạn 2016–2018 khoảng 0,5 điểm, nên ưu tiên dữ liệu từ 2019 cho các phép đo dựa trên C.
- **Chỉ tách được khối ngoại**: mua ròng khối nội = − bán ròng khối ngoại, nên không có chỉ số "dòng tiền nội" riêng.
- **Tương quan không phải nhân quả.** Nghiên cứu sự kiện có mẫu nhỏ (khoảng 27 mã), giai đoạn sau hiệu lực FTSE còn ngắn, và các mốc trùng với biến động vĩ mô.
- **Danh sách nhóm FTSE** trong `config/ftse_universe.csv` là **dự kiến** (`verified=false`), cần đối chiếu với thông báo chính thức của FTSE Russell.
- **Giá lịch sử** của SSI V3 đã điều chỉnh quyền; giá tham chiếu/trần/sàn được quy về cùng thang bằng hệ số k = close / (ref gốc + priceChange).
- **Luồng WebSocket** chỉ có dữ liệu cho các phiên mà bộ ghi chạy trong giờ giao dịch.
- **Backtest** không tính trượt giá và thanh khoản thực tế. Lợi suất kỳ vọng ước lượng từ lịch sử có sai số lớn.
- **Dữ liệu đi kèm** trong `data/snapshot/` dừng ở phiên được xuất gần nhất; cần khóa SSI để tải các phiên mới hơn.

---

## 13. Mã kế thừa từ đồ án giữa kỳ

Nguồn: kho [`web_phantichchungkhoan`](https://github.com/MinhChau536/web_phantichchungkhoan). Phần kế thừa được ghi nguồn ở đầu tệp và liệt kê tại trang *Phương pháp & giới hạn*.

| Thành phần giữa kỳ | Vị trí bản 3.2 | Mức tái sử dụng |
|---|---|---|
| `data/providers/base_provider.py` | `src/ssi_api/base_provider.py` | Giữ khuôn |
| `data/database.py` | `src/data/database.py` | Ý tưởng, viết lại theo lược đồ mới |
| `core/thi_truong_danh_muc.py` | `src/finance/breadth.py`, `src/analytics/health.py`, `src/analytics/watchlist_impact.py` | Giữ logic, đổi nguồn và trọng số |
| `giao_dien/thi_truong.py` | `src/app/views/p1_tong_quan.py`, `src/app/components/` | Giữ ý tưởng khối, làm lại bố cục lưới thẻ |
| `_pal()`, `assets/styles/main_style.py` | `src/app/theme.py` | Viết lại – một nguồn màu cho CSS, Plotly, PDF |
| `reports/pdf_generator.py`, `reports/cover.py`, `assets/fonts/` | `src/reports/`, `assets/fonts/` | Giữ font, làm lại bố cục |

**Phần viết mới:** tầng SSI FastConnect V3 (REST + WebSocket), cập nhật tự động, lược đồ và chuỗi xử lý, các module độ vênh, dòng vốn, sự kiện FTSE, DiD, kiểm định, chẩn đoán phiên, cảnh báo, nhận định, triển vọng thống kê, backtest, các trang web mới, hai mẫu PDF, bot Telegram, kiểm thử.

---

## 14. Xử lý sự cố thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| `running scripts is disabled` khi kích hoạt `.venv` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| App báo "Dữ liệu cũ hơn … phút" | Bình thường ngoài giờ giao dịch hoặc ngày nghỉ. Có khóa SSI thì app tự tải phiên mới; muốn tải ngay thì chạy `python -m src.data.updater` |
| Sửa mã nhưng giao diện không đổi | Tắt app (`Ctrl + C`) rồi chạy lại `streamlit run src/app/main.py` |
| Trang Báo cáo PDF báo lỗi trùng `key` sau khi khôi phục snapshot | Đã sửa trong bản này – cập nhật mã mới nhất (`git pull`) |
| `Closing Report` không xuất | Xem lý do hiện trên trang Báo cáo PDF (kiểm tra chất lượng chưa đạt hoặc chưa có dữ liệu phiên) |
| Không ghi được PDF vì tệp đang mở | Tệp được tự lưu sang tên có hậu tố giờ phút giây |
| Bot báo *Conflict* | Đang có tiến trình bot khác dùng cùng token; tắt tiến trình đó |
| Bot không trả lời | Thêm chat_id của bạn vào `TELEGRAM_CHAT_IDS` trong `.env` |
| SSI trả lỗi 429 | Vượt giới hạn tần suất; hệ thống tự chờ và thử lại |
| "Đang có tiến trình cập nhật khác" | Một lần cập nhật đang chạy (app, bot hoặc bộ lập lịch); chờ xong. Khóa quá 3 giờ được tự gỡ |

---

## 15. Giấy phép

Dữ liệu thị trường thuộc SSI, chỉ dùng cho mục đích học thuật theo điều khoản của nhà cung cấp. Font Be Vietnam Pro theo SIL Open Font License (`assets/fonts/OFL.txt`).

*Đề tài nghiên cứu học thuật – không mang tính chất khuyến nghị đầu tư.*
