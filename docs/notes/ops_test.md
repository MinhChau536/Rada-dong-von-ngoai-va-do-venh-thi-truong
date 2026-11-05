# Kiểm thử vận hành (bước B12.4)

Tự động trong `tests/test_operations.py` (không cần mạng – HTTP và đồng hồ giả):

| Kịch bản | Kiểm thử | Kết quả mong đợi |
|---|---|---|
| Mất mạng | `test_ssi_gives_up_after_retries_and_network_error` | Thử lại 3 lần (chờ 2–4–8 s), ném SSIError, không treo |
| Token hết hạn | `test_token_refresh_on_401` | Lấy lại token, gọi tiếp |
| Vượt hạn mức | `test_ssi_retry_backoff_on_quota` | Chờ 2 s, 4 s rồi thành công |
| SSI trả rỗng | `test_ssi_empty_day_and_throttle` | Trả danh sách rỗng (ngày nghỉ), giãn cách 1,2 s |
| SSI lỗi 3 lần → NEO → quay lại | `test_failover_errors_and_recovery` | source_events ghi đúng 2 sự kiện |
| Luồng im lặng > 120 s | `test_failover_silence` | Chuyển NEO trong phiên; ngoài phiên không chuyển |
| Giao diện khi lỗi | `safe_block` + `states.py` | Khối lỗi hiện cảnh báo, trang không dừng; không hiện số cũ như số mới |
| Cả hai nguồn lỗi | Trang 7 + thanh trạng thái | Chấm đỏ, cảnh báo dữ liệu cũ > 5 phút; Closing Report bị chặn bởi `quality_gate` |
