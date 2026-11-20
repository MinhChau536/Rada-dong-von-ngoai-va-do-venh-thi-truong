# FTSE Flow Radar 3.2

**Radar dòng vốn ngoại và độ vênh thị trường chứng khoán Việt Nam trong giai đoạn nâng hạng FTSE** – ứng dụng web Streamlit, báo cáo PDF và bot Telegram, dữ liệu thật từ **SSI FastConnect V3** (REST + WebSocket).

Đồ án cá nhân cuối kỳ · Học phần *Gói phần mềm ứng dụng cho tài chính 1* · Trường ĐH Kinh tế – Luật (ĐHQG-HCM) · Sinh viên: Lê Ngọc Minh Châu.

> 🎓 **Đề tài nghiên cứu học thuật – không mang tính chất khuyến nghị đầu tư.** Hệ thống chỉ đọc dữ liệu thị trường, **không đặt, sửa hay hủy lệnh**. Lời nhắc này xuất hiện trên mọi trang web, mọi trang PDF và mọi tin nhắn bot.

## Mục lục

1. [Tóm tắt](#1-tóm-tắt)
2. [Vấn đề và người dùng](#2-vấn-đề-và-người-dùng)
3. [Kiến trúc sản phẩm](#3-kiến-trúc-sản-phẩm)
4. [Cài đặt](#4-cài-đặt)
5. [Cấu hình](#5-cấu-hình)
6. [Chạy chương trình](#6-chạy-chương-trình)
7. [Dữ liệu SSI FastConnect V3](#7-dữ-liệu-ssi-fastconnect-v3)
8. [Cấu trúc dữ liệu (kho DuckDB)](#8-cấu-trúc-dữ-liệu-kho-duckdb)
9. [Phương pháp tài chính](#9-phương-pháp-tài-chính)
10. [Giao diện sản phẩm](#10-giao-diện-sản-phẩm)
11. [Báo cáo PDF và bot Telegram](#11-báo-cáo-pdf-và-bot-telegram)
12. [Kiểm thử và kiểm chứng](#12-kiểm-thử-và-kiểm-chứng)
13. [Bảo mật và sử dụng có trách nhiệm](#13-bảo-mật-và-sử-dụng-có-trách-nhiệm)
14. [Giới hạn đã biết](#14-giới-hạn-đã-biết)
15. [Cấu trúc thư mục](#15-cấu-trúc-thư-mục)
16. [Xử lý sự cố](#16-xử-lý-sự-cố)

---

## 1. Tóm tắt

| | |
|---|---|
| **Vấn đề** | VN-Index thường biến động khác hẳn số đông cổ phiếu vì một nhóm nhỏ mã vốn hóa lớn chi phối; trong giai đoạn nâng hạng FTSE (công bố 08/10/2025, hiệu lực 21/09/2026), dòng vốn ngoại lại đổ vào/rút khỏi chính nhóm này. Nhà đầu tư nhìn chỉ số dễ đánh giá sai trạng thái thị trường và danh mục của mình. |
| **Người dùng** | Nhà đầu tư cá nhân, chuyên viên phân tích, sinh viên tài chính |
| **Giải pháp** | Đo **độ vênh** giữa chỉ số và cổ phiếu điển hình, **ai dẫn dắt** chỉ số, **khối ngoại có đứng sau** biến động không, tác động lên **danh mục theo dõi**; nghiên cứu sự kiện FTSE; chẩn đoán kỹ thuật; cảnh báo tự động |
| **Dữ liệu** | SSI FastConnect V3: 7 endpoint REST + 4 kênh WebSocket; 2.717 phiên HOSE từ 04/01/2016, 492 mã; luồng trong phiên lưu vào bảng `raw_stream` |
| **Phương pháp** | Đóng góp điểm, độ vênh D, CR5, HHI, z-score, phân vị trượt; nghiên cứu sự kiện (CAR/CAAR, BMP, Kolari–Pynnönen), DiD, OLS Newey–West, hiệu chỉnh Holm; RSI, MACD, MA, cấu trúc đỉnh–đáy; biên dao động EWMA |
| **Sản phẩm** | Web 10 trang · báo cáo PDF (Closing Report, Market Snapshot) · bot Telegram có cảnh báo tự động 2 phút/lần |

---

## 2. Vấn đề và người dùng

**Bối cảnh.** VN-Index là chỉ số vốn hóa: vài mã lớn (họ Vingroup, ngân hàng) có thể kéo chỉ số tăng/giảm mạnh trong khi phần lớn cổ phiếu đi ngược chiều. Giai đoạn nâng hạng FTSE làm câu hỏi này nóng hơn vì dòng vốn ngoại tập trung vào 27 mã được chọn.

**Khó khăn hiện tại.** Bảng giá và ứng dụng công ty chứng khoán cho biết chỉ số tăng/giảm bao nhiêu nhưng không trả lời: (1) chỉ số có đại diện cho số đông không; (2) mã nào tạo ra biến động; (3) khối ngoại có đứng sau không; (4) danh mục của tôi bị ảnh hưởng ra sao.

**Câu hỏi nghiên cứu và nơi trả lời**

| Câu hỏi | Chỉ báo | Trang web |
|---|---|---|
| RQ1 – Chỉ số có lan tỏa tới số đông cổ phiếu? Bao nhiêu mã tạo phần lớn biến động? | D, AD, IQR, loại phiên, đóng góp C, CR5, ε | Tổng quan · Dẫn dắt & độ vênh |
| RQ2 – Dòng vốn ngoại tập trung ở đâu, có cùng chiều giá không? | NF, nf, FPR, HHI, z60, chiều giá – ngoại | Ra-đa khối ngoại |
| RQ3 – Quanh các mốc FTSE, nhóm 27 mã có lợi suất bất thường so với nhóm đối chứng? | AR, CAR, CAAR, DiD | Nâng hạng FTSE |
| RQ4 – Các mã trong danh mục theo dõi phản ứng thế nào? | ERᴹ, β Dimson, phơi nhiễm với nhóm dẫn dắt | Watchlist Impact |
| RQ5 – Cấu trúc thị trường có thay đổi sau công bố FTSE? | Kiểm định H4 (OLS HAC, Holm), hồi quy gộp D | Nâng hạng FTSE · Chẩn đoán thị trường |

**Giá trị kỳ vọng.** Một câu trả lời bằng số liệu cho mỗi phiên, cập nhật theo phút trong giờ giao dịch, đồng bộ giữa web – PDF – Telegram.

---

## 3. Kiến trúc sản phẩm

```
SSI FastConnect V3 ──► Thu thập ──────────► Chuẩn hóa / Lưu trữ ─► Logic tài chính ─► Phân tích / Mô hình ─► Giao diện ─► Người dùng
 REST  /api/v3/data/*   src/ssi_api/         DuckDB data/ffr.duckdb   src/finance/        src/analytics/          src/app/ (web)
 WS    stream/ws/v3     src/data/backfill    raw_* → fact_* → dim_*   breadth             pipeline (indicator_*)  src/reports/ (PDF)
                        src/data/updater     src/data/build_facts     contribution        event_study, did        src/bot/ (Telegram)
                        src/data/recorder_ssi  src/data/quality       foreign_flow        stats_tests, technical
                        src/data/live (phiên tạm tính)                sectors (ICB)       alerts, watchlist_impact
```

| Lớp | Nhiệm vụ | Mô-đun |
|---|---|---|
| Thu thập | Gọi REST theo lô có giới hạn tần suất, thử lại; ghi luồng WebSocket cả sàn HOSE | `src/ssi_api/ssi_client.py`, `src/data/backfill.py`, `src/data/recorder_ssi.py` |
| Chuẩn hóa / lưu trữ | Lưu JSON gốc (`raw_*`), tách cột theo từ điển dữ liệu, quy đổi thang giá, khử trùng lặp, kiểm tra chất lượng | `src/data/build_facts.py`, `src/data/quality.py`, `config/data_dictionary.yaml` |
| Logic tài chính | Độ rộng, đóng góp điểm, dòng vốn ngoại, phân ngành ICB | `src/finance/` |
| Phân tích | Chỉ báo hằng ngày, nghiên cứu sự kiện, DiD, kiểm định, chẩn đoán kỹ thuật, cảnh báo | `src/analytics/` |
| Giao diện | Web Streamlit, báo cáo PDF, bot Telegram – cùng đọc một kho chỉ báo | `src/app/`, `src/reports/`, `src/bot/` |

**Lựa chọn công nghệ.** Python 3.12; **DuckDB** (kho phân tích một tệp, truy vấn cột nhanh, không cần máy chủ); **Streamlit + Plotly** (giao diện tương tác nhanh); **fpdf2 + matplotlib** (PDF không cần trình duyệt); **python-telegram-bot**; **ssi-sdk** (SDK WebSocket chính thức của SSI, tự kết nối lại).

---

## 4. Cài đặt

Yêu cầu: **Windows 10/11, Python 3.12, Git** (Linux/macOS chạy được, thay lệnh kích hoạt môi trường).

```powershell
git clone https://github.com/MinhChau536/Rada-dong-von-ngoai-va-do-venh-thi-truong.git
cd Rada-dong-von-ngoai-va-do-venh-thi-truong
python -m venv .venv
.venv\Scripts\activate                  # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env                  # Linux/macOS: cp .env.example .env
```

Thư viện chính: `streamlit`, `plotly`, `pandas`, `numpy`, `duckdb`, `scipy`, `statsmodels`, `linearmodels`, `fpdf2`, `matplotlib`, `python-telegram-bot`, `ssi-sdk`, `requests`, `pyyaml`.

Lần chạy đầu, kho `data/ffr.duckdb` được **tự dựng từ `data/snapshot/`** (Parquet đi kèm mã nguồn, ~30 giây) nên xem được ngay cả khi chưa có khóa SSI.

> Lỗi *"running scripts is disabled"* khi kích hoạt `.venv`: chạy một lần `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

---

## 5. Cấu hình

### 5.1. Biến môi trường `.env` (không đẩy lên GitHub)

| Biến | Ý nghĩa | Bắt buộc |
|---|---|---|
| `SSI_API_KEY`, `SSI_API_SECRET` | Khóa SSI FastConnect V3 – tạo tại [developers.ssi.com.vn](https://developers.ssi.com.vn) › Quản lý API Key, nhóm quyền Market Data (không cần Private Key, không cần OTP) | Để tải dữ liệu mới |
| `SSI_BASE_URL`, `SSI_STREAM_URL` | Mặc định `https://api.ssi.com.vn`, `wss://stream.ssi.com.vn/ws/v3` | Không |
| `TELEGRAM_BOT_TOKEN` | Token bot riêng, tạo bằng @BotFather (`/newbot`) | Để chạy bot |
| `TELEGRAM_CHAT_IDS` | chat_id được phép, cách nhau bằng dấu phẩy (lấy bằng @userinfobot). **Để trống = bot không trả lời ai** | Để chạy bot |
| `LOG_LEVEL` | `INFO` (mặc định) / `DEBUG` | Không |

### 5.2. Tệp cấu hình trong `config/`

| Tệp | Nội dung |
|---|---|
| `settings.yaml` | Mọi tham số: lịch phiên, giới hạn tần suất SSI, cửa sổ phân vị, λ EWMA, ngưỡng cảnh báo, độ nhạy, đường dẫn. Trang *Phương pháp & giới hạn* đọc trực tiếp tệp này |
| `data_dictionary.yaml` | Ánh xạ trường JSON của SSI → cột chuẩn, kiểu, đơn vị |
| `ftse_universe.csv` | 27 mã FTSE theo công bố chính thức 21/08/2026 (cột `source_url`) |
| `events.csv` | Các mốc E1, E2, L1, L2, E3 (cột `source_url`) |
| `stock_groups.csv` | Định nghĩa họ cổ phiếu (Vingroup, Masan…) do đề tài đặt; **ngành lấy theo mã ICB của SSI** |
| `control_group.csv` | Nhóm đối chứng ghép theo vốn hóa – thanh khoản (sinh tự động) |

---

## 6. Chạy chương trình

### 6.1. Một lệnh: web + bot

```powershell
python run.py              # thêm --no-bot nếu chỉ cần web, --port 8502 để đổi cổng
```

`run.py` làm theo thứ tự:

1. **Cập nhật dữ liệu trước**: trong giờ giao dịch bật bộ ghi luồng SSI và chờ phiên tạm tính đầu tiên; ngoài giờ tải phiên đã đóng cửa còn thiếu rồi tính lại chỉ báo.
2. Chạy **bot Telegram** ở nền (nếu `.env` có token).
3. Mở **web** tại `http://localhost:8501` – đường link chỉ hiện khi số liệu đã mới. Dừng bằng `Ctrl + C`.

### 6.2. Lệnh riêng

| Việc | Lệnh |
|---|---|
| Chỉ web | `streamlit run src/app/main.py` |
| Chỉ bot Telegram | `python -m src.bot.bot` |
| Tải phiên mới từ SSI + tính lại | `python -m src.data.updater` |
| Ghi luồng WebSocket (tự dừng 15:05) / ghi thử 60 giây | `python -m src.data.recorder_ssi` / `python -m src.data.recorder_ssi --seconds 60` |
| Dựng lại toàn bộ từ dữ liệu gốc | `python -m src.data.rebuild_all` |
| Xuất PDF | `python -m src.reports.closing` · `python -m src.reports.snapshot` |
| Xuất / nạp gói dữ liệu Parquet | `python -m tools.snapshot export` · `python -m tools.snapshot restore --force` |
| Kiểm thử | `python -m pytest` |

### 6.3. Tự động hằng ngày (không cần mở web)

```powershell
python tools/schedule_windows.py          # đăng ký tác vụ Windows "FTSE Flow Radar - SSI"
python tools/schedule_windows.py --status # xem lần chạy gần nhất / kế tiếp
python tools/schedule_windows.py --remove # gỡ
```

| Giờ (thứ 2 – thứ 6) | Việc hệ thống làm | Web / PDF / bot hiển thị |
|---|---|---|
| 08:50 | Bộ ghi luồng khởi động (Task Scheduler; hoặc khi mở web/bot) | Phiên gần nhất |
| **09:00 – 15:00** | Ghi WebSocket cả sàn HOSE; **2 phút/lần** dựng phiên tạm tính và chạy lại chuỗi chỉ báo | ● TRỰC TIẾP, trễ ~2–3 phút, web tự làm mới |
| 11:35 | Bản tin giữa phiên + Market Snapshot qua Telegram | |
| **15:05 – 15:15** | Chốt phiên từ luồng (giá sau ATC, khối ngoại cả phiên), tính lại toàn bộ chỉ báo và kiểm định | ● ĐÓNG CỬA TẠM TÍNH |
| 15:15 | Chẩn đoán phiên + Closing Report qua Telegram | |
| Khi SSI công bố số cuối ngày | Hỏi REST 90 giây/lần (tới 18:30), tải và **thay bản tạm tính** bằng số chính thức | Số liệu chính thức |

Máy tắt nhiều ngày: lần chạy sau tự lấp mọi phiên còn thiếu qua REST. Luồng WebSocket không tải bù được.

---

## 7. Dữ liệu SSI FastConnect V3

Nguồn dữ liệu thị trường **duy nhất** là SSI FastConnect V3. **Không dùng dữ liệu giả lập**; kho trống thì app chỉ mở trang Kết nối dữ liệu. Thông tin tham chiếu ngoài API (danh sách 27 mã và mốc FTSE) có ghi nguồn trong cấu hình.

### 7.1. Endpoint và luồng sử dụng

| Nhóm | Endpoint / kênh | Trường chính khai thác | Tần suất |
|---|---|---|---|
| Xác thực | `POST /api/v3/auth/token` | JWT (làm mới trước hạn 60 giây) | Theo hạn token |
| Danh mục | `GET /api/v3/data/securitiesByBoard` | `symbol`, `stockType`, `listedShare`, `icbCode`, `icbName` | 1 lần/lần cập nhật |
| Giá tham chiếu | `GET /api/v3/data/masterdata` | `refPrice`, `ceiling`, `floor`, `board` | Mỗi phiên |
| Tổng hợp mã | `GET /api/v3/data/securitiesSummary` | `open/high/low/close`, `totalMatch`, `totalMatchValue`, `totalDeal*`, `totalForeignBuy/Sell(Value)`, `remainForeignRoom`, `totalForeignRoom` | Mỗi phiên (sau đóng cửa) |
| Tổng hợp chỉ số | `GET /api/v3/data/indexSummary` | `indexValue`, `indexChange(%)`, số mã tăng/giảm/đứng/trần/sàn, KL, GTGD | Mỗi phiên |
| Nến | `GET /api/v3/data/ohlc` (1d, 5m, 1m) | OHLCV | 1d hằng ngày; 1m khi bot quét/khi bổ sung mã thiếu |
| Danh sách chỉ số | `GET /api/v3/data/indexList` | mã chỉ số | Khi cần |
| WebSocket | `trade` cả sàn HOSE · `room` từng mã HOSE · `indexsummary` (VNINDEX, VN30, HNX, UPCOM) · `trade.index` | giá khớp, KL lũy kế, giá TB; KL/GT ngoại mua–bán lũy kế, room; điểm chỉ số, số mã tăng/giảm | Thời gian thực, 09:00–15:05 |

### 7.2. Giới hạn tần suất và lỗi kết nối

- REST: tối thiểu **0,06 giây giữa hai yêu cầu** (máy chủ báo giới hạn 20 yêu cầu/giây), phân trang 1.000 dòng, timeout 60 giây, **thử lại 3 lần** với chờ 2 – 4 – 8 giây; lỗi 401/403 báo rõ nguyên nhân khóa; mọi lời gọi ghi vào bảng `ingest_log`.
- Dữ liệu thời gian thực dùng **WebSocket** thay cho gọi REST liên tục. SDK tự kết nối lại; luồng im lặng > 120 giây trong phiên → trạng thái nguồn chuyển `degraded`, ghi `source_events` và báo qua Telegram; bộ ghi chết giữa phiên được bot/web bật lại.
- Khóa `data/.update.lock` và `data/.recorder.lock` bảo đảm không có hai lần cập nhật hay hai bộ ghi chạy chồng nhau.

### 7.3. Xử lý chất lượng dữ liệu

| Tình huống | Cách xử lý |
|---|---|
| Giá trị thiếu | SSI trả `null` cho khối ngoại/thỏa thuận khi không có giao dịch → 0 nếu mã có khớp lệnh; phiên SSI bỏ trống khối ngoại toàn sàn → giữ NULL và tự tải lại ở lần sau; room mang giá trị phiên trước |
| Dữ liệu lặp | Khóa chính `(trade_date, symbol, source)`; khử trùng theo nguồn ưu tiên (`SSI` REST > `SSI-WS` luồng) |
| Lỗi kiểu / đơn vị | Chuỗi số có dấu phân cách được chuẩn hóa; giá 0 → NULL; phiên SSI trả giá trị theo triệu đồng được quy đổi; giá đã điều chỉnh quyền được quy về cùng thang với tham chiếu |
| Mất kết nối / đến muộn | Thử lại có giãn cách; điểm dừng (`checkpoints`) để tải tiếp; số liệu cuối ngày đến muộn được thay thế khi có |
| Thông điệp bất thường | Lợi suất ngoài biên độ ±7% được ghi nhật ký; tin heartbeat/xác nhận đăng ký bị bỏ qua |
| Múi giờ | Mọi dấu thời gian lưu và hiển thị theo **giờ Việt Nam (Asia/Ho_Chi_Minh, UTC+7)** |

Kết quả kiểm tra ghi trong bảng `data_quality_log` (độ đầy đủ, đối chiếu số mã tăng/giảm với SSI, sai số tái lập chỉ số ε) và hiển thị ở trang *Kiểm chứng & dữ liệu*.

---

## 8. Cấu trúc dữ liệu (kho DuckDB)

`raw_*` → `fact_*` / `dim_*` → `indicator_*` → kết quả nghiên cứu. Định nghĩa đầy đủ: `src/data/schema.sql`, `config/data_dictionary.yaml`.

| Tầng | Bảng | Khóa | Nội dung |
|---|---|---|---|
| Gốc | `raw_daily_stock`, `raw_daily_index`, `raw_securities`, `raw_index_components`, `raw_intraday` | ngày, mã, nguồn | JSON nguyên văn SSI trả về (truy vết được mọi con số) |
| Gốc | `raw_stream` | thời điểm nhận, kênh, mã | Tin WebSocket (chỉ số, VN30, watchlist) |
| Chuẩn hóa | `fact_daily_stock` | ngày, mã | ref, trần, sàn, OHLC, KL, GTGD, khớp/thỏa thuận, ngoại mua/bán (KL, GT), room |
| Chuẩn hóa | `fact_daily_index`, `fact_intraday` | ngày/thời điểm, mã | Điểm chỉ số, số mã tăng/giảm, nến 5 phút |
| Danh mục | `dim_securities`, `dim_universe`, `dim_events` | mã / sự kiện | Số CP niêm yết, nhóm FTSE / đối chứng / VN30, các mốc |
| Chỉ báo | `indicator_stock_daily` | ngày, mã | lợi suất, tỷ trọng w, đóng góp C, NF, nf, z, ERᴹ, MA20, trạng thái giá – ngoại |
| Chỉ báo | `indicator_daily` | ngày | D, CR5, AD, IQR, loại phiên, NF toàn sàn, HHI, FPR, phân vị 20/60/250 phiên |
| Chỉ báo | `indicator_group_daily`, `leaders_daily` | ngày, nhóm | Ngành, họ, FTSE, đối chứng; top mã dẫn dắt |
| Kết quả | `event_aar`, `event_results`, `did_coefs`, `stats_results`, `robustness_results` | | Nghiên cứu sự kiện, DiD, kiểm định |
| Vận hành | `alert_log`, `reports_log`, `ingest_log`, `data_quality_log`, `source_status`, `checkpoints` | | Nhật ký cảnh báo, báo cáo, gọi API, chất lượng |
| Trong phiên | `data/live.duckdb` (`live_meta` + các bảng chỉ báo) | | Phiên tạm tính dựng lại mỗi 2 phút |

---

## 9. Phương pháp tài chính

Công thức đầy đủ (1)–(17) trên trang *Phương pháp & giới hạn* và Phụ lục PDF.

| Phần | Chỉ báo / mô hình | Cách tính | Vì sao chọn |
|---|---|---|---|
| Lan tỏa | Độ vênh **D** | r VN-Index − trung vị lợi suất cổ phiếu | Trung vị đại diện cổ phiếu điển hình, không bị mã lớn chi phối |
| Dẫn dắt | Đóng góp **C**, **CR5**, ε | C = I(t−1)·w·r; CR5 = Σ\|C\| top 5 / Σ\|C\|; ε = ΔI − ΣC | Biết chính xác mã nào tạo ra bao nhiêu điểm; ε kiểm tra độ chính xác |
| Dẫn dắt | HHI tỷ trọng | Σw², 1/HHI = số mã hiệu dụng | Kiểm soát việc tỷ trọng chỉ số tự phình to |
| Khối ngoại | NF, nf, FPR, HHI, z60 | Mua − bán; NF/GTGD; (mua+bán)/2GTGD; z theo 60 phiên trước | Chuẩn hóa để so sánh giữa mã và giữa phiên |
| Khối ngoại | Chiều giá – ngoại | Dấu NF × dấu giá khi \|nf\| ≥ 5%, \|r\| ≥ 0,5% | Nhận diện khối ngoại đứng sau hay ngược chiều giá |
| FTSE | CAR/CAAR, BMP, Kolari–Pynnönen, Welch | Mô hình thị trường, cửa sổ ước lượng [−130; −11]; FTSE − đối chứng | Chuẩn mực nghiên cứu sự kiện, chịu được tương quan chéo |
| FTSE | DiD, H4 | Hiệu ứng cố định mã và phiên; OLS Newey–West 5 trễ; p hiệu chỉnh Holm | Tách tác động giai đoạn khỏi xu hướng chung |
| Kỹ thuật | MA20/50/200, Dow, RSI(14), MACD(12,26,9), khối lượng xác nhận | Chuẩn kỹ thuật phổ biến | Mô tả xu hướng, động lượng, độ tin cậy của biến động giá |
| Biên dao động | EWMA hiệu chỉnh đuôi dày | σ EWMA λ = 0,94; biên I·exp(±k·σ·√h), k = phân vị sai số quá khứ | Biên có bao phủ thực tế kiểm chứng được |
| Watchlist | ERᴹ, β Dimson | r − trung vị thị trường; hồi quy có trễ ±1 | β Dimson khắc phục giao dịch không đồng bộ |
| Cảnh báo | 8 quy tắc ngưỡng | Ngưỡng từ phân vị lịch sử (CR5, D), \|z\| ≥ 2, room ≥ 95%… | Ngưỡng có cơ sở thống kê, không đặt tùy ý |

**Không nhìn trước**: phân vị, z-score, biên EWMA và backtest chỉ dùng dữ liệu tới phiên t−1. Khuyến nghị chỉ ở **cấp thị trường**, suy ra từ bảng trạng thái chỉ báo theo quy tắc cố định – không chọn cổ phiếu, không định giá doanh nghiệp.

---

## 10. Giao diện sản phẩm

| Nhóm | Trang | Nội dung chính |
|---|---|---|
| **Diễn biến thị trường** | Tổng quan thị trường | 4 thẻ chỉ số, chất lượng xu hướng + kết luận phiên, nến + MA + mốc FTSE, thanh khoản, độ rộng, ngành, bản đồ nhiệt, Top 10, cổ phiếu nổi bật (GTGD ≥ 10 tỷ), hiệu suất, watchlist |
| | Dẫn dắt & độ vênh | Thác nước đóng góp theo mã/ngành, bảng chi tiết, họ cổ phiếu, chuỗi D có dải phân vị, CR5, HHI tỷ trọng |
| | Ra-đa khối ngoại | NF, z60, HHI, FPR, xếp hạng mua/bán ròng/room, khối ngoại theo ngành và nhóm, chuỗi lũy kế |
| **Phân tích chuyên sâu** | Nâng hạng FTSE | Dòng thời gian mốc, 27 mã, lợi suất lũy kế các nhóm, CAAR/CAFF, DiD, bảng kiểm định đầy đủ, cân bằng nhóm đối chứng |
| | Chẩn đoán thị trường | Kết luận + khuyến nghị cấp thị trường, phân tích kỹ thuật (bảng + biểu đồ giá/RSI/MACD), cấu trúc dòng vốn, kịch bản hỗ trợ/kháng cự, chẩn đoán phiên 5 bước, kết luận nghiên cứu FTSE |
| **Danh mục & tiện ích** | Watchlist Impact | Thêm/bớt mã, tab riêng từng mã, phản ứng so với thị trường, phơi nhiễm |
| | Báo cáo PDF | Xuất Closing Report / Market Snapshot, danh sách báo cáo đã sinh |
| | Bot Telegram | Giới thiệu bot, luồng hoạt động, tin mẫu dựng từ dữ liệu thật, cơ chế cảnh báo, gửi thử |
| **Hệ thống** | Kiểm chứng & dữ liệu | Backtest cảnh báo và biên dao động, chất lượng dữ liệu, luồng WebSocket đã ghi, kết nối SSI |
| | Phương pháp & giới hạn | Công thức (1)–(17), tham số từ `settings.yaml`, kết quả kiểm định, giới hạn |

**Đáp ứng yêu cầu giao diện của đề:** tên sản phẩm, mục tiêu và người dùng ở đầu mỗi trang · **thanh trạng thái** gồm giờ cập nhật, nguồn, trạng thái kết nối SSI, độ đầy đủ, nhãn TRỰC TIẾP / ĐÓNG CỬA TẠM TÍNH · nhiều chỉ số tổng hợp (D, CR5, NF, HHI…) · biểu đồ nến, thác nước, bản đồ nhiệt, phân phối, chuỗi thời gian, bảng xếp hạng · bộ chọn phiên, mã, kỳ, nhóm · khu vực phân tích, cảnh báo, giải thích · trang phương pháp và giới hạn · trạng thái không có dữ liệu / mất kết nối / lỗi API được hiển thị rõ, mỗi khối lỗi độc lập không làm treo trang.

---

## 11. Báo cáo PDF và bot Telegram

**Báo cáo PDF** (`src/reports/`, lưu tại `reports_out/`): *Closing Report* (sau phiên, có kiểm tra chất lượng) và *Market Snapshot* (trong phiên).
Bố cục: bìa + kết luận phiên · mục lục + tóm tắt điều hành (3 câu trả lời) · 1. Tổng quan thị trường · 2. Dẫn dắt và độ vênh · 3. Dòng vốn ngoại · 4. Bối cảnh nâng hạng FTSE · 5. Chẩn đoán thị trường · 6. Tác động lên watchlist · 7. Kết luận, hàm ý và khuyến nghị · 8. Phụ lục phương pháp và chất lượng dữ liệu. Mỗi chương bắt đầu trang mới, mở đầu bằng một câu kết luận sinh từ số liệu.

**Bot Telegram** (`src/bot/`):

| Chức năng | Mô tả |
|---|---|
| Tra cứu bằng nút | Menu: Thị trường, Dẫn dắt, Khối ngoại, Triển vọng, Chẩn đoán phiên, Watchlist, PDF, Cảnh báo; gõ mã (vd. `FPT`) ra thẻ phân tích; `/intra FPT` biểu đồ trong phiên |
| Cảnh báo tự động | Quét 2 phút/lần trong phiên: VN-Index vượt ±1%/±2%, biến động 15 phút, vượt biên EWMA 95%, cắt MA50, khối ngoại vượt 2σ, độ rộng lệch ≥ 4 lần; mã watchlist vượt ngưỡng %, trần/sàn, khối lượng đột biến, phá đỉnh/đáy 20 phiên. Độ nhạy Thấp/Vừa/Cao (`/alerts`), nút "Cơ chế cảnh báo" giải thích ngưỡng |
| Bản tin | 11:35 giữa phiên, 15:15 cuối phiên kèm PDF, tín hiệu xu hướng sau phiên |
| An toàn | Chỉ trả lời `TELEGRAM_CHAT_IDS`; mỗi tín hiệu tối đa 1 lần/ngày; chặn bấm lặp |

---

## 12. Kiểm thử và kiểm chứng

**Kiểm thử tự động** (`tests/`, chạy `python -m pytest`, dùng kho tạm và dữ liệu mẫu trong `tests/fixtures`, không cần mạng):

| Nhóm | Tệp |
|---|---|
| Công thức tài chính (độ rộng, đóng góp điểm, ε, khối ngoại) | `test_breadth.py`, `test_contribution.py`, `test_foreign.py` |
| Không nhìn trước (phân vị, z, walk-forward) | `test_no_lookahead.py`, `test_outlook.py` |
| Nghiên cứu sự kiện, kiểm định, watchlist | `test_event_study.py`, `test_stats_watchlist.py` |
| Chuỗi xử lý và sửa lỗi dữ liệu lịch sử | `test_pipeline.py`, `test_history_fixes.py` |
| Cảnh báo, chống trùng, giới hạn | `test_alerts.py` |
| Gọi API (phiên HTTP giả: lỗi 429/5xx, hết hạn token), cập nhật, khóa | `test_operations.py`, `test_updater.py` |
| PDF, tin nhắn Telegram (HTML hợp lệ), cấu trúc trang web | `test_portfolio.py` |

**Kiểm chứng kết quả** (trang *Kiểm chứng & dữ liệu*): tái lập VN-Index từ đóng góp từng mã (ε hằng ngày); đối chiếu số mã tăng/giảm với `indexSummary` của SSI; backtest cảnh báo (chống trùng, giá trị thông tin, có hiệu chỉnh Holm); bao phủ thực tế của biên dao động; bảng độ vững của kết quả FTSE qua nhiều biến thể (`docs/robustness_table.csv`). Tham số không chỉnh theo kết quả.

---

## 13. Bảo mật và sử dụng có trách nhiệm

- Khóa SSI và token Telegram chỉ nằm trong `.env` (đã `.gitignore`); `.env.example` để trống; nhật ký che khóa bí mật.
- **Không đặt lệnh**: hệ thống chỉ dùng API dữ liệu thị trường, không dùng chức năng tài khoản hay giao dịch.
- Tôn trọng giới hạn tần suất SSI; dữ liệu thời gian thực qua WebSocket.
- Mọi nhận định là mô tả thống kê; khuyến nghị chỉ ở cấp thị trường, kèm lời nhắc **không phải khuyến nghị đầu tư**.
- Không nên dùng sản phẩm để: ra quyết định mua/bán từng mã, giao dịch tần suất cao, hay coi tương quan là quan hệ nhân quả.

---

## 14. Giới hạn đã biết

- Vốn hóa xấp xỉ bằng số cổ phiếu niêm yết (chưa trừ cổ phiếu quỹ, free-float) → đóng góp C là xấp xỉ, sai số đo bằng ε (trung vị ~0,34 điểm).
- Chỉ tách được khối ngoại; ròng khối nội = − ròng khối ngoại, không tách tổ chức / cá nhân trong nước.
- Tương quan cùng phiên không phải nhân quả; nghiên cứu sự kiện mẫu nhỏ (27 mã), giai đoạn sau hiệu lực FTSE còn ngắn và trùng các biến động vĩ mô.
- Nhóm FTSE có vốn hóa lớn hơn nhóm đối chứng (kiểm tra cân bằng chưa đạt hoàn toàn).
- Chỉ báo kỹ thuật mô tả trạng thái, không dự báo hướng đi.
- Phiên tạm tính từ WebSocket chỉ đầy đủ khi bộ ghi chạy từ đầu phiên; máy tắt trong giờ giao dịch thì mất phần luồng đó (bản REST chính thức vẫn được tải sau).
- SSI FastConnect không cung cấp định giá (P/E, P/B) hay số liệu vĩ mô nên hệ thống không dùng.
- Số mã tăng/giảm có thể lệch vài mã so với SSI vì SSI đếm cả CCQ/ETF.

---

## 15. Cấu trúc thư mục

```
├── run.py                 khởi động một lệnh: cập nhật dữ liệu → bot → web
├── requirements.txt · .env.example · pytest.ini
├── config/                settings.yaml · data_dictionary.yaml · ftse_universe.csv · events.csv · stock_groups.csv · control_group.csv
├── src/
│   ├── ssi_api/           ssi_client.py (REST, giới hạn tần suất, thử lại) · base_provider.py
│   ├── data/              backfill · updater · autoupdate · recorder_ssi · live · build_facts · quality · rebuild_all · database · schema.sql
│   ├── finance/           breadth · contribution · foreign_flow · domestic · sectors (ICB)
│   ├── analytics/         pipeline · event_study · did · stats_tests · technical · diagnosis · outlook · alerts · watchlist_impact · narrative
│   ├── app/               main.py · views/ (các trang) · components/ (thẻ, biểu đồ, giao diện)
│   ├── reports/           closing · snapshot · chapters · charts · pdf_base · context
│   ├── bot/               bot · messages · monitor (cảnh báo tự động) · jobs · intraday
│   └── common/            config · fmt · timeutil · logging
├── tools/                 schedule_windows.py · snapshot.py
├── tests/                 kiểm thử tự động + fixtures
├── data/                  ffr.duckdb (không đẩy git) · snapshot/ (Parquet đi kèm)
├── docs/                  api_samples/ (JSON mẫu SSI) · notes/ · robustness_table.csv
├── reports_out/           PDF đã xuất
└── logs/                  app.log · job_recorder.log · job_autoupdate.log
```

---

## 16. Xử lý sự cố

| Hiện tượng | Cách xử lý |
|---|---|
| `running scripts is disabled` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| Web báo "Chưa có phiên tạm tính" trong giờ giao dịch | Chờ 1–2 phút; xem `logs/job_recorder.log`; kiểm tra khóa SSI trên trang Kiểm chứng & dữ liệu › Kết nối |
| Dữ liệu chưa có phiên hôm nay sau giờ đóng cửa | SSI công bố số cuối ngày muộn; hệ thống tự tải khi có. Tải ngay: `python -m src.data.updater` |
| SSI trả 401/403 | Khóa sai hoặc chưa được cấp quyền Market Data |
| Bot không trả lời | Thêm chat_id vào `TELEGRAM_CHAT_IDS`; lỗi *Conflict* = đang có tiến trình bot khác dùng cùng token |
| "Đang có tiến trình cập nhật khác" | Một lần cập nhật đang chạy; khóa quá 3 giờ tự gỡ |
| Closing Report không xuất | Xem lý do trên trang Báo cáo PDF (chưa có dữ liệu phiên hoặc kiểm tra chất lượng chưa đạt) |

---

Dữ liệu thị trường thuộc SSI, chỉ dùng cho mục đích học thuật theo điều khoản của nhà cung cấp. Font Be Vietnam Pro theo SIL Open Font License (`assets/fonts/OFL.txt`).

*Đề tài nghiên cứu học thuật – không mang tính chất khuyến nghị đầu tư.*
