# Dữ liệu mẫu (bước B13.2)

⚠️ **Dữ liệu tổng hợp** do `src/data/demo_data.py` sinh (seed cố định) – KHÔNG phải số liệu thị trường thật, không chứa thông tin tài khoản.

- Ứng dụng chạy không cần khóa với `DEMO_DATA=true` (mặc định): lần đầu tự sinh ~400 phiên vào `data/ffr.duckdb`.
- Các tệp CSV ở đây là 10 phiên cuối của các bảng chính để xem nhanh cấu trúc:

| Tệp | Bảng |
|---|---|
| `raw_daily_index_VNINDEX_sample.csv` | `raw_daily_index` – JSON gốc theo tên trường SSI v2 |
| `fact_daily_stock_10sessions.csv` | `fact_daily_stock` – bảng chuẩn mã × phiên |
| `fact_daily_index_10sessions.csv` | `fact_daily_index` |
| `indicator_daily_10sessions.csv` | `indicator_daily` – D, AD, IQR, CR5, ε, NF, HHI, z, loại phiên, phân vị |
| `leaders_daily_10sessions.csv` | `leaders_daily` – top 5 đóng góp dương/âm |
