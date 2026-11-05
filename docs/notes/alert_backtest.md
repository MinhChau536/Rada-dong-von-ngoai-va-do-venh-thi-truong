# Chạy lại cảnh báo trên dữ liệu lịch sử (bước B8.4)

- Số phiên: **60**; mỗi phiên đánh giá 4 lần (10:00, 10:15, 11:00, 14:45).
- Số lượt kích hoạt thô: 888; số cảnh báo duy nhất/ngày trước lọc: 3.70.
- Bị chặn do trùng/cooldown: 627; bị chặn do giới hạn ngày: 52.
- Cảnh báo thị trường được giữ: trung bình **3.48/ngày**, tối đa 5/ngày (ngưỡng ≤ 5).

| Loại | Số lượng |
|---|---|
| wl_leader | 90 |
| wl_room | 52 |
| wl_foreign | 42 |
| wl_deviation | 16 |
| foreign_market | 7 |
| high_divergence | 2 |

_Tạo tự động bởi `src/analytics/alerts.py::backtest` – chạy lại khi đổi ngưỡng trong settings.yaml._