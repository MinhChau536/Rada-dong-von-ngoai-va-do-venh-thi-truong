# Nhật ký luồng NEO WebSocket (bước B1.4b)

Thống kê tự động ở **Trang 7 – Chất lượng dữ liệu → "Luồng NEO WebSocket có lưu trữ"** (đọc bảng `raw_stream_neo`):
số tin mỗi phiên, giờ tin đầu/cuối, tổng phút mất kết nối (khoảng trống > 90 giây giữa hai tin marketInfo).

Tiêu chí đạt: **≥ 10 phiên**, mất kết nối **< 5 phút/phiên**.

| Phiên | Số tin | Mất kết nối (phút) | Ghi chú |
|---|---|---|---|
| (điền sau khi chạy `python -m src.data.recorder_neo`) | | | |

Kiểm tra kết nối 06/11/2026: WebSocket `wss://neoapi.vpbanks.com.vn/stock-stream/broker` đồng bộ 26 lược đồ Avro và nhận tin `marketSession` thật (HOSE, HNX, UPCOM, FU). Bộ ghi bắt đầu tích lũy dữ liệu từ phiên giao dịch kế tiếp (`python -m src.data.recorder_neo`).
