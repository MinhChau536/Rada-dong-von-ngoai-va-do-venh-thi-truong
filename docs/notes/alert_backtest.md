# Chạy lại cảnh báo trên dữ liệu lịch sử (bước B8.4)

- Số phiên: **60**; mỗi phiên đánh giá 4 lần (10:00, 10:15, 11:00, 14:45).
- Số lượt kích hoạt thô: 660; số cảnh báo duy nhất/ngày trước lọc: 2.75.
- Bị chặn do trùng/cooldown: 180; bị chặn do giới hạn ngày: 420.
- Cảnh báo thị trường được giữ: trung bình **1.00/ngày**, tối đa 1/ngày (ngưỡng ≤ 1).

| Loại | Số lượng |
|---|---|
| wl_foreign | 22 |
| wl_leader | 22 |
| index_concentrated | 13 |
| wl_deviation | 2 |
| foreign_market | 1 |

_Tạo tự động bởi `src/analytics/alerts.py::backtest` – chạy lại khi đổi ngưỡng trong settings.yaml._

## Giá trị dự báo (B8.4b) – toàn bộ lịch sử

2720 phiên (2016-01-04 → 2026-11-25). Lợi suất VN-Index sau tín hiệu, nhân hướng tín hiệu (+1 khi chỉ số tăng / khối ngoại mua ròng). Lũy kế 5 phiên chồng lấp – p tham khảo.

| Quy tắc | Kỳ | n tín hiệu | TB sau tín hiệu (%) | TB phiên thường (%) | Tỷ lệ cùng hướng | p Welch | p MW |
|---|---|---|---|---|---|---|---|
| 1. Chỉ số do ít mã dẫn dắt | t+1 | 103 | 0.007 | 0.049 | 52.4% | 0.715 | 0.332 |
| 1. Chỉ số do ít mã dẫn dắt | t+1…t+5 | 102 | 0.046 | 0.215 | 54.9% | 0.509 | 0.367 |
| 2. Độ vênh cao (D ≥ P90 250 phiên) | t+1 | 292 | 0.286 | 0.018 | 66.4% | 0.001 | 0.000 |
| 2. Độ vênh cao (D ≥ P90 250 phiên) | t+1…t+5 | 287 | 0.674 | 0.149 | 66.2% | 0.006 | 0.000 |
| 2. Độ vênh cao (D ≥ P90 250 phiên) | ΔD phiên t+1 | 292 | -0.939 | – | 87.3% | – | 0.000 |
| 3. Khối ngoại toàn sàn bất thường (|z| ≥ 2) | t+1 | 141 | 0.134 | 0.046 | 56.0% | 0.461 | 0.966 |
| 3. Khối ngoại toàn sàn bất thường (|z| ≥ 2) | t+1…t+5 | 138 | 0.065 | 0.203 | 55.1% | 0.598 | 0.431 |
| 3a. Khối ngoại MUA ròng mạnh (z ≥ 2) | t+1 | 61 | 0.223 | 0.043 | 67.2% | 0.297 | 0.071 |
| 3a. Khối ngoại MUA ròng mạnh (z ≥ 2) | t+1…t+5 | 59 | 0.404 | 0.203 | 64.4% | 0.645 | 0.447 |
| 3b. Khối ngoại BÁN ròng mạnh (z ≤ −2) | t+1 | 80 | 0.066 | 0.050 | 47.5% | 0.924 | 0.096 |
| 3b. Khối ngoại BÁN ròng mạnh (z ≤ −2) | t+1…t+5 | 79 | -0.188 | 0.208 | 48.1% | 0.207 | 0.088 |

_Tạo tự động bởi `src/analytics/alerts.py::predictive`._
