# Chạy lại cảnh báo trên dữ liệu lịch sử (bước B8.4)

- Số phiên: **60**; mỗi phiên đánh giá 4 lần (10:00, 10:15, 11:00, 14:45).
- Số lượt kích hoạt thô: 704; số cảnh báo duy nhất/ngày trước lọc: 2.93.
- Bị chặn do trùng/cooldown: 501; bị chặn do giới hạn ngày: 36.
- Cảnh báo thị trường được giữ: trung bình **2.78/ngày**, tối đa 5/ngày (ngưỡng ≤ 5).

| Loại | Số lượng |
|---|---|
| wl_leader | 49 |
| wl_room | 49 |
| wl_foreign | 38 |
| index_concentrated | 16 |
| wl_deviation | 11 |
| foreign_market | 3 |
| high_divergence | 1 |

_Tạo tự động bởi `src/analytics/alerts.py::backtest` – chạy lại khi đổi ngưỡng trong settings.yaml._

## Giá trị dự báo (B8.4b) – toàn bộ lịch sử

2713 phiên (2016-01-04 → 2026-11-13). Lợi suất VN-Index sau tín hiệu, nhân hướng tín hiệu (+1 khi chỉ số tăng / khối ngoại mua ròng). Lũy kế 5 phiên chồng lấp – p tham khảo.

| Quy tắc | Kỳ | n tín hiệu | TB sau tín hiệu (%) | TB phiên thường (%) | Tỷ lệ cùng hướng | p Welch | p MW |
|---|---|---|---|---|---|---|---|
| 1. Chỉ số do ít mã dẫn dắt | t+1 | 101 | 0.001 | 0.046 | 52.5% | 0.705 | 0.317 |
| 1. Chỉ số do ít mã dẫn dắt | t+1…t+5 | 100 | 0.059 | 0.216 | 55.0% | 0.545 | 0.420 |
| 2. Độ vênh cao (D ≥ P90 250 phiên) | t+1 | 290 | 0.271 | 0.017 | 65.9% | 0.002 | 0.000 |
| 2. Độ vênh cao (D ≥ P90 250 phiên) | t+1…t+5 | 282 | 0.705 | 0.148 | 67.0% | 0.004 | 0.000 |
| 2. Độ vênh cao (D ≥ P90 250 phiên) | ΔD phiên t+1 | 290 | -0.918 | – | 87.2% | – | 0.000 |
| 3. Khối ngoại toàn sàn bất thường (|z| ≥ 2) | t+1 | 141 | 0.113 | 0.043 | 56.0% | 0.553 | 0.779 |
| 3. Khối ngoại toàn sàn bất thường (|z| ≥ 2) | t+1…t+5 | 138 | 0.044 | 0.204 | 54.3% | 0.541 | 0.361 |
| 3a. Khối ngoại MUA ròng mạnh (z ≥ 2) | t+1 | 61 | 0.208 | 0.041 | 67.2% | 0.331 | 0.097 |
| 3a. Khối ngoại MUA ròng mạnh (z ≥ 2) | t+1…t+5 | 59 | 0.389 | 0.204 | 62.7% | 0.674 | 0.496 |
| 3b. Khối ngoại BÁN ròng mạnh (z ≤ −2) | t+1 | 80 | 0.041 | 0.047 | 47.5% | 0.969 | 0.063 |
| 3b. Khối ngoại BÁN ròng mạnh (z ≤ −2) | t+1…t+5 | 79 | -0.213 | 0.208 | 48.1% | 0.180 | 0.071 |

_Tạo tự động bởi `src/analytics/alerts.py::predictive`._
