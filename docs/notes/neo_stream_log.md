# Nhật ký luồng NEO WebSocket (bước B1.4b)

Thống kê tự động ở **Trang 7 – Chất lượng dữ liệu → "Luồng NEO WebSocket có lưu trữ"** (đọc bảng `raw_stream_neo`):
số tin mỗi phiên, giờ tin đầu/cuối, tổng phút mất kết nối (khoảng trống > 90 giây giữa hai tin marketInfo).

Tiêu chí đạt: **≥ 10 phiên**, mất kết nối **< 5 phút/phiên**.

| Phiên | Số tin | Mất kết nối (phút) | Ghi chú |
|---|---|---|---|
| (điền sau khi chạy `python -m src.data.recorder_neo` với tài khoản NEO thật) | | | |

Trạng thái hiện tại: kho đang chứa 10 phiên luồng NEO **mẫu** (`source = DEMO_NEO`) để trình diễn giao diện – không tính là bằng chứng ghi thật.
