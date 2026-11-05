# Kết quả xác minh API (bước B1.2) – cập nhật sau khi chạy `--samples` với khóa thật

| Câu hỏi | Có/Không | Bằng chứng (tệp JSON) |
|---|---|---|
| DailyStockPrice có trường khối ngoại theo ngày (ForeignBuyValTotal, ForeignSellValTotal)? | … | DailyStockPrice_HOSE.json |
| Trường khối ngoại là khớp lệnh hay gồm thỏa thuận? | Kết luận tự động ở `docs/notes/foreign_scope.md` (B2.5) | |
| SecuritiesDetails có ListedShare? | … | SecuritiesDetails_HOSE.json |
| DailyIndex có Advances/Declines/NoChanges/Ceilings/Floors? | … | DailyIndex_VNINDEX.json |

**Nếu khóa thuộc v3 và không có khối ngoại lịch sử** (thuyết minh mục 6.1): (i) đăng ký thêm quyền v2 để dùng DailyStockPrice; (ii) giới hạn phần khối ngoại lịch sử vào giai đoạn tự ghi từ streaming và ghi rõ trong báo cáo. Nghiên cứu sự kiện về lợi suất vẫn chạy được.
