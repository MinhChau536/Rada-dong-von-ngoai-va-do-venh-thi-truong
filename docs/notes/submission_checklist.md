# Danh sách nộp bài & đối chiếu yêu cầu đề (bước B13.6, Phụ lục A thuyết minh)

## Tệp nộp
| Thành phần | Tên tệp | Trạng thái |
|---|---|---|
| Mã nguồn | `MSSV_HoTen_NEOAPI_FinTech.zip` (README, requirements, .env.example, src, tests, data_sample, docs, report; KHÔNG có .env, *.duckdb, logs) | ☐ |
| Báo cáo | `MSSV_HoTen_BaoCao.pdf` (8–12 trang, 10 phần) | ☐ |
| Video | `MSSV_HoTen_Demo.mp4` (5–7 phút, không lộ khóa/token/chat_id) | ☐ |

## Đối chiếu yêu cầu
| Yêu cầu đề | Đáp ứng trong mã | Trạng thái |
|---|---|---|
| Mục 2.1 API là cốt lõi | `src/ssi_api`, `src/neo_api`, `src/data/backfill.py`, `recorder_*` | Mã ✅ · chạy thật ☐ |
| Mục 2.2 Lớp logic tài chính | `src/finance`, `src/analytics` | ✅ |
| Mục 2.3 Sản phẩm chạy được | `streamlit run src/app/main.py` (chế độ mẫu), PDF, bot | ✅ |
| Mục 2.4 Kiểm chứng | đối chiếu độ rộng, ε, kiểm định, độ vững, 71 kiểm thử | ✅ · nguồn ngoài ☐ |
| Mục 4 ≥ 1 luồng WebSocket có lưu trữ | `recorder_neo.py` → `raw_stream_neo` | Mã ✅ · ≥ 10 phiên thật ☐ |
| Mục 4 ≥ 3 trường kinh tế | > 15 trường (`data_dictionary.yaml`) | ✅ |
| Mục 4 ≥ 5–10 phiên | ~400 phiên lịch sử (khi backfill thật) | ☐ |
| Mục 4 múi giờ Asia/Ho_Chi_Minh | `src/common/timeutil.py`, `logging.py` | ✅ |
| Mục 4 chất lượng dữ liệu | `build_facts.py`, `quality.py`, `data_quality_log` | ✅ |
| Mục 4 giới hạn tần suất | 1,2 s, thử lại 2–4–8 s; NEO ≤ 5 req/s | ✅ |
| Mục 4 tái lập | `rebuild_all.py --hash`, `test_reproducible_hash` | ✅ |
| Mục 4 an toàn | `.env`/`.gitignore`, `mask_secrets` | ✅ · tạo lại khóa ☐ |
| Mục 5 kiến trúc & sơ đồ riêng | README mục 2; báo cáo phần 3 | ✅ / ☐ |
| Mục 6 tên, mục tiêu, người dùng | `components/about.py` | ✅ |
| Mục 6 thời điểm cập nhật, kết nối | `components/status_bar.py` | ✅ |
| Mục 6 ≥ 3 chỉ số, ≥ 2 trực quan, bộ lọc | Trang 1–5 | ✅ |
| Mục 6 phân tích, cảnh báo, phương pháp | `narrative.py`, `alerts.py`, trang 8 | ✅ |
| Mục 6 không dữ liệu / mất kết nối / lỗi API | `components/states.py`, `safe_block` | ✅ |
| Mục 7 ngưỡng có cơ sở, không nhìn trước | `settings.yaml`, `test_no_lookahead.py` | ✅ |
| Mục 8 không giao dịch, miễn trừ | không có API đặt lệnh; câu miễn trừ trên 3 kênh | ✅ |
| Mục 9 cấu trúc mã, log, kiểm thử, README | cây thư mục theo mẫu đề | ✅ |
| Mục 12 báo cáo 10 phần | `report/README.md` (khung) | ☐ |
| Mục 13 liêm chính | README mục 7, trang 8 (mã kế thừa); nhận định không dùng mô hình ngôn ngữ | ✅ |

## Tự chấm (điền khi hoàn tất)
| Tiêu chí | Điểm tối đa | Tự đánh giá | Chỗ còn yếu |
|---|---|---|---|
| TC1 Giá trị cho người dùng | | | |
| TC2 Khai thác API & kỹ thuật dữ liệu | | | |
| TC3 Phương pháp tài chính | | | |
| TC4 Kỹ thuật | | | |
| TC5 Sản phẩm & trải nghiệm | | | |
| TC6 Kiểm thử & kiểm chứng | | | |
| TC7 Tài liệu & trình bày | | | |
