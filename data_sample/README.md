# Dữ liệu mẫu (bước B13.2)

Thư mục này chứa **dữ liệu thật** trích từ kho DuckDB sau khi tải qua API (SSI FastConnect Data / NEO API) –
không có dữ liệu sinh giả lập, không chứa khóa, token hay thông tin tài khoản.

```bash
python -m src.data.sample_data export     # (người làm đồ án) xuất 10 phiên gần nhất của các bảng raw_*
python -m src.data.sample_data load       # (người chấm) nạp vào data/ffr.duckdb rồi dựng lại toàn bộ chỉ báo
streamlit run src/app/main.py
```

| Tệp | Bảng | Nội dung |
|---|---|---|
| `raw_daily_stock.csv` | `raw_daily_stock` | JSON gốc DailyStockPrice (SSI) hoặc ảnh chụp cuối phiên stockInfo (NEO), cột `source` ghi nguồn |
| `raw_daily_index.csv` | `raw_daily_index` | JSON gốc DailyIndex (SSI) / marketInfo (NEO) |
| `raw_securities.csv` | `raw_securities` | SecuritiesDetails: loại CK, ListedShare |
| `raw_index_components.csv` | `raw_index_components` | Thành phần VN30 |

Với chỉ 10 phiên, các chỉ báo cần lịch sử dài (phân vị 250 phiên, beta 120 phiên, nghiên cứu sự kiện) sẽ hiện
trạng thái "chưa đủ dữ liệu" thay vì số liệu – đúng nguyên tắc không hiển thị kết quả gây hiểu nhầm.
