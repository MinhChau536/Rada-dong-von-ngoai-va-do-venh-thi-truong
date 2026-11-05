# Chuẩn bị bảo vệ (bước B13.7) – 10 câu hỏi

1. **Vì sao dùng trung vị cho D?** Lợi suất HOSE bị chặn ±7% và đuôi dày; trung vị đại diện "cổ phiếu điển hình", không bị vài mã trần/sàn kéo lệch. Độ vững: thay bằng trung bình đồng trọng số (bảng robustness).
2. **Công thức C và sai số ε?** C_i = I_{t−1}·w_i·r_i với w theo S_i·P_ref (vốn hóa đầu phiên, giá đã điều chỉnh quyền). ε = ΔI − ΣC đo phần xấp xỉ do S niêm yết ≠ S tính chỉ số (cổ phiếu quỹ, free-float). Mục tiêu trung vị |ε| < 0,5 điểm; nếu không đạt, hiệu chỉnh k bằng hồi quy ΔI trên ΣC không hệ số chặn.
3. **Vì sao không dùng ròng khối nội như chỉ số độc lập?** Mỗi giao dịch có bên mua và bán → ròng khối nội = −ròng khối ngoại, không thêm thông tin. Thay bằng FPR, trạng thái hấp thụ, lô lẻ, mua/bán chủ động.
4. **Chọn ngưỡng cảnh báo thế nào?** Phân vị lịch sử (D ≥ P90 của 250 phiên; nf ≥ P95/≤ P5 của 60 phiên; |z| ≥ 2) và quy tắc nghiệp vụ (|ΔI| ≥ 5 điểm & CR5 ≥ 60%, U ≥ 95%). Chạy lại 60 phiên: trung bình ≤ 5 cảnh báo/ngày.
5. **Tránh nhìn trước thế nào?** Mọi phân vị/z của phiên t chỉ dùng [t−k, t−1] (`shift(1)`); tham số sự kiện ước lượng trên [−130; −11]. Kiểm thử `test_no_lookahead.py` phá hủy dữ liệu tương lai và kiểm tra kết quả không đổi.
6. **BMP khác t thường ở đâu?** BMP chuẩn hóa AR của từng mã bằng σ cửa sổ ước lượng (có hiệu chỉnh sai số dự báo) rồi kiểm định t trên SCAR → vững khi phương sai tăng quanh sự kiện.
7. **DiD giả định gì?** Xu hướng song song: không có sự kiện thì chênh lệch FTSE − đối chứng không đổi. Kiểm tra bằng hệ số theo tuần trước sự kiện ≈ 0; sai số cụm theo mã, hiệu ứng cố định mã và phiên.
8. **NEO đóng vai trò gì?** Luồng WebSocket ghi song song mỗi phiên (đáp ứng chuẩn "≥ 1 luồng WebSocket có lưu trữ"), đối chiếu chéo với SSI, và nguồn dự phòng.
9. **Cơ chế chuyển nguồn?** SSI lỗi 3 lần liên tiếp hoặc streaming im lặng > 120 giây trong phiên → NEO, gắn source='NEO', ghi source_events, báo Telegram; SSI ổn định 5 phút → quay lại. Kiểm thử bằng đồng hồ giả.
10. **Mã nào kế thừa, mã nào viết mới?** Xem README mục 7 và trang 8: kế thừa khung giao diện/biểu đồ/PDF/watchlist; viết mới tầng SSI–NEO, lược đồ, Module A–D, sự kiện, kiểm định, cảnh báo, bot, kiểm thử.
