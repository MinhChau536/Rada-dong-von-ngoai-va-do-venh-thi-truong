# Rà soát bảo mật (bước B13.5)

Lệnh kiểm tra (chạy trước khi nộp):

```bash
git log -p | grep -iE "consumer_?secret|consumerid|password|bot[0-9]{8,}:|eyJ[a-zA-Z0-9_-]{10,}\." 
git ls-files | grep -E "^\.env$|\.duckdb$|\.log$"
```

Kết quả lần rà soát khi khởi tạo kho (05/11/2026): không có tệp `.env`, `*.duckdb`, `logs/` trong kho; `.env.example` chỉ chứa giá trị giả;
`src/common/logging.py::mask_secrets` che token/JWT/mật khẩu trong nhật ký (kiểm thử `test_mask_secrets`).

Còn lại sinh viên tự kiểm tra: ảnh chụp màn hình, video trình diễn (không lộ khóa, token, chat_id).
