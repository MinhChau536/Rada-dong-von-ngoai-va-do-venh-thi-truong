# Chạy lại cảnh báo trên dữ liệu lịch sử (bước B8.4)

- Số phiên: **50**; mỗi phiên đánh giá 4 lần (10:00, 10:15, 11:00, 14:45).
- Số lượt kích hoạt thô: 368; số cảnh báo duy nhất/ngày trước lọc: 1.84.
- Bị chặn do trùng/cooldown: 276; bị chặn do giới hạn ngày: 0.
- Cảnh báo thị trường được giữ: trung bình **1.84/ngày**, tối đa 4/ngày (ngưỡng ≤ 5).

| Loại | Số lượng |
|---|---|
| wl_leader | 52 |
| wl_foreign | 17 |
| index_concentrated | 16 |
| wl_deviation | 3 |
| foreign_market | 3 |
| high_divergence | 1 |

_Tạo tự động bởi `src/analytics/alerts.py::backtest` – chạy lại khi đổi ngưỡng trong settings.yaml._

## Giá trị dự báo (B8.4b) – toàn bộ lịch sử

2715 phiên (2016-01-04 → 2026-11-17). Lợi suất VN-Index sau tín hiệu, nhân hướng tín hiệu (+1 khi chỉ số tăng / khối ngoại mua ròng). Lũy kế 5 phiên chồng lấp – p tham khảo.

| Quy tắc | Kỳ | n tín hiệu | TB sau tín hiệu (%) | TB phiên thường (%) | Tỷ lệ cùng hướng | p Welch | p MW |
|---|---|---|---|---|---|---|---|
| 1. Chỉ số do ít mã dẫn dắt | t+1 | 101 | 0.001 | 0.046 | 52.5% | 0.706 | 0.318 |
| 1. Chỉ số do ít mã dẫn dắt | t+1…t+5 | 100 | 0.059 | 0.216 | 55.0% | 0.545 | 0.420 |
| 2. Độ vênh cao (D ≥ P90 250 phiên) | t+1 | 290 | 0.271 | 0.017 | 65.9% | 0.002 | 0.000 |
| 2. Độ vênh cao (D ≥ P90 250 phiên) | t+1…t+5 | 283 | 0.699 | 0.149 | 66.8% | 0.004 | 0.000 |
| 2. Độ vênh cao (D ≥ P90 250 phiên) | ΔD phiên t+1 | 290 | -0.918 | – | 87.2% | – | 0.000 |
| 3. Khối ngoại toàn sàn bất thường (|z| ≥ 2) | t+1 | 141 | 0.113 | 0.043 | 56.0% | 0.552 | 0.782 |
| 3. Khối ngoại toàn sàn bất thường (|z| ≥ 2) | t+1…t+5 | 138 | 0.044 | 0.204 | 54.3% | 0.541 | 0.361 |
| 3a. Khối ngoại MUA ròng mạnh (z ≥ 2) | t+1 | 61 | 0.208 | 0.040 | 67.2% | 0.330 | 0.096 |
| 3a. Khối ngoại MUA ròng mạnh (z ≥ 2) | t+1…t+5 | 59 | 0.389 | 0.204 | 62.7% | 0.674 | 0.496 |
| 3b. Khối ngoại BÁN ròng mạnh (z ≤ −2) | t+1 | 80 | 0.041 | 0.047 | 47.5% | 0.970 | 0.063 |
| 3b. Khối ngoại BÁN ròng mạnh (z ≤ −2) | t+1…t+5 | 79 | -0.213 | 0.208 | 48.1% | 0.180 | 0.071 |

_Tạo tự động bởi `src/analytics/alerts.py::predictive`._
