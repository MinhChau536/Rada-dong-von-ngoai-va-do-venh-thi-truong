# Khung báo cáo cuối kỳ (bước B13.3) – 8–12 trang A4, 10 phần theo mục 12 của đề

> Mọi số liệu trích từ `stats_results`, `indicator_*`, `docs/test_summary.csv` (không gõ tay). **Chỉ viết báo cáo trên dữ liệu SSI thật** – kết quả hiện có trong kho mẫu là dữ liệu tổng hợp để trình diễn.

| Phần | Trang | Nội dung | Nguồn số liệu |
|---|---|---|---|
| 1. Tóm tắt điều hành | 0,5 | Vấn đề (chỉ số xanh – cổ phiếu đỏ; dòng vốn ngoại sau nâng hạng), người dùng, giải pháp, dữ liệu SSI/NEO, 3–4 kết quả có số | stats_results |
| 2. Vấn đề & nhu cầu người dùng | 1 | Bối cảnh FTSE (E1, E2, E3), VN-Index nửa đầu 2026 với/không Vingroup | indicator_group_daily (VINGROUP) |
| 3. Thiết kế sản phẩm | 1 | Sơ đồ kiến trúc riêng (README mục 2), nhiệm vụ từng lớp, lý do chọn Streamlit, DuckDB | — |
| 4. Dữ liệu | 1,5 | Bảng endpoint/luồng (SSI v2, NEO WS), tần suất, lưu trữ raw→fact, làm sạch, chuyển nguồn | docs/notes/api_check.md, trang 7 |
| 5. Phương pháp tài chính | 2 | Công thức (1)–(13), cơ sở ngưỡng, thiết kế sự kiện & kiểm định | trang 8, settings.yaml |
| 6. Triển khai sản phẩm | 1,5 | Ảnh 8 trang, PDF, Telegram; xử lý lỗi & trạng thái dữ liệu | docs/screens/ |
| 7. Kiểm thử & kết quả | 2 | Bảng tổng hợp kiểm thử; kết quả RQ1–RQ4 (bảng, CAAR, Fama–MacBeth) | docs/test_summary.csv, stats_results |
| 8. Hạn chế & sử dụng có trách nhiệm | 0,5 | Xấp xỉ vốn hóa, không tách tổ chức nội, không nhân quả, mẫu nhỏ, bảo mật | trang 8 |
| 9–10. Hướng phát triển & kết luận | 0,5 | Basis VN30F, đợt FTSE 2027, điều chỉnh free-float | — |
| Phụ lục | — | Từ điển dữ liệu, công thức, kiểm thử đầy đủ, cài đặt, mã kế thừa, tuyên bố sử dụng công cụ AI | config/data_dictionary.yaml, README |

**Tuyên bố sử dụng công cụ AI (phụ lục):** mã nguồn của bản 3.2 được xây dựng với sự hỗ trợ của trợ lý lập trình AI (Claude Code) theo thuyết minh và hướng dẫn từng bước của sinh viên; sinh viên chịu trách nhiệm kiểm tra, chạy với dữ liệu thật và giải thích được mã khi bảo vệ (đề mục 13).
