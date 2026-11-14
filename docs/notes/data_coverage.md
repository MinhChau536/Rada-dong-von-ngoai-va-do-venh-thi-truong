# Độ phủ dữ liệu và độ dài mẫu cho nghiên cứu trước/sau nâng hạng FTSE

Kiểm tra trên kho `data/ffr.duckdb` (SSI FastConnect V3), cập nhật 14/11/2026.

## 1. Phạm vi

| Hạng mục | Từ | Đến | Số phiên / ghi chú |
|---|---|---|---|
| Cổ phiếu HOSE ngày (giá điều chỉnh, KL, GTGD, khối ngoại, room) | 04/01/2016 | 09/11/2026 | 2.710 phiên, 490 mã (284 mã hợp lệ/phiên năm 2016 → ~372 năm 2026) |
| VN-Index, VN30, HNX-Index, UPCoM-Index | 04/01/2016 | 09/11/2026 | VN-Index 2.687 phiên – **SSI thiếu 23 phiên** (chủ yếu cuối tháng 2016–2018, cả indexSummary lẫn nến ngày) |
| Khối ngoại theo mã | 04/01/2016 | 09/11/2026 | có ở mọi phiên |
| Nến 5 phút (31 mã) | 05/10/2026 | 09/11/2026 | 26 phiên – chỉ đủ cho β nội ngày watchlist |
| Luồng WebSocket (`raw_stream`) | — | — | **trống** |

Khoảng trống lịch giao dịch > 5 ngày đều là nghỉ Tết / 30-4 (16 lần) – không thiếu phiên. 23 phiên thiếu VN-Index được để
trống (không nội suy); lợi suất chỉ số của phiên kế tiếp dùng ΔI chính thức của SSI thay vì gộp hai phiên.

## 2. Ba giai đoạn so sánh

| Giai đoạn | Từ | Đến | Số phiên |
|---|---|---|---|
| Trước công bố (cơ sở chính = 250 phiên cuối) | 04/01/2016 | 07/10/2025 | 2.438 (cơ sở: 07/10/2024 → 07/10/2025) |
| Công bố E1 → trước hiệu lực | 08/10/2025 | 18/09/2026 | 235 |
| Sau ngày hiệu lực | 21/09/2026 | 09/11/2026 | **36** |

Nhóm FTSE (27 mã) và đối chứng (27 mã) đều có đủ dữ liệu ở cả ba giai đoạn (235 và 36 phiên hợp lệ mỗi mã). Mã ngắn lịch sử
nhất: BSR, GEE (từ 2024), SHB (2021) – vẫn đủ cửa sổ ước lượng [−130; −11] cho mọi mốc.

## 3. Đủ chưa? – theo công suất thống kê (MDE 80%, α = 5%)

* **Trước vs. sau công bố (E1)**: đủ. 250 vs 235 phiên → phát hiện được thay đổi cỡ 0,04 ở CR5, 0,016 ở FPR, 11 điểm %
  ở tỷ lệ phiên thiếu lan tỏa.
* **Trước vs. sau hiệu lực**: **chưa đủ để kết luận chắc chắn**. 36 phiên → MDE lớn gấp ~2 lần (CR5 0,07; FPR 0,036; tỷ lệ
  phiên thiếu lan tỏa 17,5 điểm %). Chỉ các thay đổi lớn mới phát hiện được; kết quả là **sơ bộ**. Nên chờ ≥ 60 phiên
  (khoảng giữa tháng 12/2026) và lý tưởng là ≥ 120 phiên (khoảng 03/2027) rồi chạy lại `rebuild_all`.
* **Nghiên cứu sự kiện quanh E1, E2, E3** (cửa sổ tới [0; +20]): đủ cho cả ba mốc.
* **DiD quanh E3** (±60 phiên): hiện chỉ có +36 phiên sau mốc → các tuần +6, +7 dựa trên rất ít quan sát.

## 4. Lựa chọn cơ sở và độ vững (H4)

Cơ sở chính = 250 phiên ngay trước E1 vì giai đoạn 2016–2023 khác hẳn về quy mô thanh khoản, biên độ (COVID 2020,
bùng nổ 2021) và chất lượng dữ liệu (ε 2016–2018 ≈ 0,5 điểm). Độ vững với cơ sở dài từ 02/01/2019:

* Giữ nguyên dấu và ý nghĩa: **CR5 tăng**, **FPR tăng**, **tỷ lệ phiên thiếu lan tỏa tăng** (cả hai giai đoạn).
* Đổi kết luận: ln GTGD và IQR – khác biệt chủ yếu do xu hướng dài hạn (thanh khoản tăng mạnh từ 2019, biên dao động
  2019–2021 rộng hơn), không phải do nâng hạng → **không dùng cơ sở dài cho hai chỉ báo này**.
* nf toàn sàn âm hơn so với cơ sở dài (khối ngoại bán ròng mạnh hơn trung bình 2019–2025) nhưng không khác 250 phiên trước.

## 5. Các lỗi dữ liệu đã sửa (14/11/2026)

1. Hệ số điều chỉnh quyền < 0,2 bị bỏ qua (HPG, MBB… 2016–2019) → ref ở thang giá gốc, r ≈ −84%.
2. ~42 nghìn dòng 2016–2019 thiếu priceChange và % → ref điều chỉnh = close điều chỉnh phiên trước.
3. close = 0 (01/2020) → coi là thiếu.
4. GTGD theo triệu đồng ở 13/09/2018 và 25/04/2019 → nhân 10^6.
5. Lợi suất VN-Index phiên sau 23 phiên thiếu chỉ số → dùng ΔI chính thức.

Sau sửa: trung vị |ε| = 0,34 điểm (2019+: 0,21–0,42), 615 quan sát vượt biên độ (từ 25.805).

## 6. Còn hạn chế

* Danh sách FTSE (`config/ftse_universe.csv`) vẫn `verified=false` – cần đối chiếu thông báo FTSE Russell.
* Giai đoạn sau hiệu lực ngắn; các mốc trùng biến động vĩ mô → mô tả, không khẳng định nhân quả.
* Chưa ghi luồng WebSocket → chưa đối chiếu luồng ↔ REST.
