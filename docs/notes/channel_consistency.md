# Đồng nhất ba kênh (bước B12.5)

Cùng phiên 05/11/2026: 10 con số lấy từ `src/reports/context.py::key_numbers` (nguồn chung của PDF và Telegram),
giao diện đọc cùng bảng `indicator_daily` và cùng hàm định dạng `src/common/fmt.py`. Kiểm thử tự động: `tests/test_pipeline.py::test_three_channels_consistent`.

| Chỉ tiêu | Giá trị | Có trong tin /market |
|---|---|---|
| VN-Index | 1.630,41 | ✅ |
| ΔVN-Index | -21,08 | ✅ |
| r_VNI | -1,28% | ✅ |
| Trung vị | -1,37% | ✅ |
| D | +0,09 | ✅ |
| CR5 | 29% | ✅ |
| AD | -0,62 | ✅ |
| NF HOSE | -1.438 tỷ | — (hiển thị ở /leaders hoặc /foreign) |
| HHI | 0,038 | — (hiển thị ở /leaders hoặc /foreign) |
| ε | -0,15 | — (hiển thị ở /leaders hoặc /foreign) |

Bằng chứng ảnh chụp (dashboard, PDF, Telegram cùng thời điểm) – sinh viên bổ sung khi chạy dữ liệu thật.

_Số liệu trên là DỮ LIỆU MẪU tổng hợp._