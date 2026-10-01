#  Module Xử Lý PDF & AI Routing (AI-LMS)

Đây là phân hệ cốt lõi của dự án **AI-LMS (Micro-learning System)**, chịu trách nhiệm số hóa, làm sạch và trích xuất thông tin từ các tệp PDF giáo trình đa dạng (Text, Toán học, Sơ đồ, Bảng biểu), sau đó điều phối cho LLM để tự động sinh ra các bài giảng vi mô và câu hỏi trắc nghiệm chất lượng cao.

##  CÁC TÍNH NĂNG VÀ CẢI TIẾN VƯỢT TRỘI (MỚI NHẤT)

### 1. Trích xuất thông minh (Smart Extraction)
- **Đọc Đa Cột (Multi-column Layout):** Sử dụng sort=True của PyMuPDF để gom nhóm văn bản theo khối, giữ nguyên ngữ nghĩa của các bài báo khoa học 2 cột.
- **Lọc Nhiễu Theo Tọa Độ (Coordinate Filtering):** Tự động cắt bỏ 10% lề trên và 10% lề dưới của mọi trang, quét sạch Header, Footer, Watermark, và Số trang lặp lại.
- **Thuật toán Diệt Logo (Duplicate Image Hashing):** Quét dung lượng byte của hình ảnh. Bất kỳ Logo trường học hay icon trang trí nào lặp lại qua các trang đều bị đá văng khỏi pipeline để tiết kiệm 100% token ảnh vô ích.

### 2. Phân loại theo Ngữ nghĩa (Semantic Classifier)
- Hệ thống không còn đếm số lượng hình ảnh một cách cứng nhắc. Bất cứ ảnh nào sống sót qua "Lưới lọc rác" đều được đánh giá là Biểu đồ/Sơ đồ quan trọng.
- Phân loại tự động sang MIXED (Vừa chữ vừa ảnh) hoặc VISUAL_HEAVY (Trang thuần Slide) để gọi đúng Vision Model, không bao giờ bỏ sót Biểu đồ Venn hay Sơ đồ khối của sinh viên.

### 3. Điều phối AI (AI Routing & Prompt Engineering)
- **Đa ngôn ngữ tự động (Language Agnostic):** AI tự động nhận diện ngôn ngữ của PDF và sinh ra JSON (Summary & Quiz) bằng ĐÚNG NGÔN NGỮ ĐÓ (Không bị kẹt ở Tiếng Việt).
- **Khắc phục Hoang tưởng Toán học (Anti-Hallucination):** System Prompt chặn đứng thói quen tự giải toán sai của LLM. Đối với bài tập chưa giải, AI sẽ tự chuyển hướng sang hỏi về lý thuyết, cách đặt ẩn phụ, hoặc công thức.
- **Chống gãy cấu trúc JSON:** Cấm LLM sử dụng ký tự gạch chéo ngược (\) của LaTeX bên trong chuỗi JSON, đảm bảo Tỷ lệ Parse JSON thành công luôn đạt 100%.

### 4. Hệ thống Phòng thủ (Fault Tolerance)
- **Exponential Backoff:** Bảo vệ hệ thống khỏi lỗi Rate Limit (429) của Google Free Tier. Hệ thống sẽ bắt lỗi, tính toán thời gian bị phạt, cho luồng code "ngủ đông" (sleep) đúng số giây yêu cầu, và tự động gọi lại thay vì làm sập ứng dụng.
- **Quality Gate Retry:** Nếu LLM vô tình trả về JSON rác, AI Router tự động giảm độ khó (Giảm từ 5 câu xuống 3 câu) và thử lại để đảm bảo đầu ra luôn có dữ liệu.

---

## CẤU TRÚC THƯ MỤC

`	ext
Process-PDF/
├── src/
│   ├── extractors/
│   │   └── pdf_parser.py     # Cắt lề 10%, Đọc đa cột, Diệt Logo Hash
│   ├── core/
│   │   ├── classifier.py     # Phân loại Semantic (TEXT, MIXED, VISUAL)
│   │   ├── text_chunking.py  # LangChain Chunking (3000 chars, 300 overlap)
│   │   └── vision_cv.py      # Tiền xử lý ảnh OpenCV (Đo độ mờ, CLAHE)
│   └── ai_router.py          # LiteLLM, Exponential Backoff, Multi-language Prompt
├── dataset/                  # Chứa các file PDF mẫu để test
├── outputs/                  # Chứa kết quả JSON trả về
├── benchmark.py              # Script chạy test toàn bộ 5 file trong dataset
└── .env                      # Chứa GEMINI_API_KEY
`

## 🛠️ HƯỚNG DẪN CÀI ĐẶT VÀ SỬ DỤNG

### 1. Cài đặt thư viện (Requirements)
Cài đặt các dependency cần thiết (Nên sử dụng môi trường ảo venv):
`ash
pip install -r requirements.txt
`
*(Các thư viện chính bao gồm: PyMuPDF, opencv-python, numpy, langchain-text-splitters, litellm, python-dotenv)*

### 2. Cấu hình biến môi trường
Tạo một file .env ở thư mục gốc của project (cùng cấp với thư mục src/) và dán API Key của Google Gemini vào:
`env
GEMINI_API_KEY="AIzaSy...<API_KEY_CỦA_BẠN>"
`
*Lưu ý: Hệ thống hiện tại đang được tối ưu hóa cho mô hình gemini-3.5-flash-lite vì tốc độ cao và chi phí cực rẻ.*

### 3. Chạy hệ thống (Benchmark)
Để kiểm tra toàn bộ sức mạnh của pipeline trên các file PDF nằm trong thư mục dataset/, hãy chạy lệnh:
`ash
python benchmark.py
`
Kết quả sẽ được tự động xuất ra thư mục outputs/ với đuôi _result.json.

---

## 📊 KẾT QUẢ BENCHMARK (Tham khảo)
| Tên File (Đặc điểm) | Số trang | Thời gian xử lý | Tỷ lệ thành công (JSON Valid) |
| :--- | :---: | :---: | :---: |
| introduction.pdf (Văn bản thuần) | 26 | **~7s** | 100% |
| ds4sets.pdf (Sơ đồ, Bảng biểu) | 27 | **~6s** (Đã diệt 3 logo rác) | 100% |
| Ôn tập nguyên hàm tích phân.pdf (Toán học) | 8 | **~10-12s** | 100% |

*(Thời gian có thể dao động nhẹ tùy thuộc vào tình trạng Rate Limit của Google tại thời điểm gọi API, nhưng hệ thống luôn đảm bảo không bị crash nhờ Exponential Backoff).*
