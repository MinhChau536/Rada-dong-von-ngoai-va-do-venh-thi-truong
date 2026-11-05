# Mẫu phản hồi API (bước B1.2)

Chạy sau khi có khóa SSI thật trong `.env`:

```bash
python -m src.ssi_api.ssi_client --samples
```

Lệnh gọi thử MỘT ngày cho DailyStockPrice (HOSE), DailyIndex (VNINDEX), DailyOhlc, IntradayOhlc, SecuritiesDetails, IndexComponents (VN30) và lưu JSON gốc vào thư mục này. Sau đó:

1. Đối chiếu tên trường với `config/data_dictionary.yaml`, đổi `verified: true` cho trường đã khớp.
2. Trả lời trong `docs/notes/api_check.md`: có trường khối ngoại theo ngày không; khớp lệnh hay gồm thỏa thuận; có ListedShare không.

⚠️ Kiểm tra JSON không chứa token trước khi commit (phản hồi dữ liệu thị trường không chứa thông tin tài khoản).
