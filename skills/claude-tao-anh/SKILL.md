---
name: claude-tao-anh
description: Tạo file prompt_tao_anh.md từ kịch bản video (.docx) để gửi cho AI tạo ảnh (ChatGPT, Gemini). Prompt yêu cầu AI vẽ ảnh infographic cho từng cảnh và, khi tạo xong toàn bộ ảnh, trả về một file tổng hợp hieu_ung.json mô tả các khối hiệu ứng để luồng ./tao-video dựng video có animation. Dùng khi người dùng gọi /claude-tao-anh hoặc muốn có prompt tạo ảnh kèm hiệu ứng cho một kịch bản.
argument-hint: "[du-an/<tên> | đường dẫn file .docx]"
---

# Tạo prompt ảnh kèm hiệu ứng cho video

Đầu vào của người dùng: $ARGUMENTS

Luồng dựng video nằm ở `/Users/duongca/WorkSpace/Video_AI` (lệnh `./tao-video`). Mỗi video là
một thư mục `du-an/<tên>/`, tài nguyên nằm trong `assets/`, mỗi loại một thư mục:
`assets/kich-ban/` (đúng 1 file `.docx`), `assets/anh/` (ảnh), `assets/nhac/` (nhạc nền),
`assets/hieu-ung/` (`prompt_tao_anh.md`, `hieu_ung.json`), `assets/cau-hinh/` (`cau_hinh.toml`).

- Đầu vào là thư mục dự án: dùng thư mục đó.
- Đầu vào là file `.docx` nằm ngoài `du-an/`: hỏi người dùng tên dự án, chạy
  `./tao-video du-an/<tên>` để tạo khung thư mục, rồi chép file vào `du-an/<tên>/assets/kich-ban/`
  (không di chuyển file gốc).
- Đầu vào trống: liệt kê các thư mục trong `du-an/` chưa có `assets/hieu-ung/hieu_ung.json` và hỏi
  người dùng chọn.

## Bước 1. Tạo bản prompt gốc bằng code

```bash
cd /Users/duongca/WorkSpace/Video_AI && ./tao-video du-an/<tên> --tao-prompt
```

Lệnh này (tự xếp các file để lẫn vào đúng thư mục trong `assets/`) ghi
`du-an/<tên>/assets/hieu-ung/prompt_tao_anh.md` theo mẫu `san_xuat/mau_prompt_tao_anh.md`:
phong cách hình, quy tắc bố cục, định dạng JSON, tên file ảnh cần lưu, lời đọc từng cảnh.
KHÔNG tự đặt lại tên file ảnh: tên do code sinh ra là tên mà bước dựng video sẽ tìm.

## Bước 2. Lên trước các khối hiệu ứng cho từng cảnh

Đọc file vừa tạo. Với MỖI cảnh một ảnh (không phải ảnh bìa, không phải cảnh "N ảnh" cắt nhanh),
thêm vào cuối phần của cảnh đó một mục:

````
- Animated elements (draw exactly these, return this JSON with "vung" filled in):
```json
{"so": 6, "anh": "<tên file của cảnh>", "tam_zoom": [0.5, 0.6], "khoi": [
  {"chu": "Ngoại thất", "mo_ta": "white card with green check icon", "vung": null, "hien_khi": "Ngoại thất", "hieu_ung": "truot"},
  {"chu": "", "mo_ta": "green shield with white check mark", "vung": null, "hien_khi": "kiểm soát được", "hieu_ung": "bat"}
]}
```
````

Cách chọn khối:
1. Lấy từ cột "Chữ trên màn hình": mỗi mục danh sách, mỗi bước, mỗi nhãn là MỘT khối riêng.
   Dòng tiêu đề (trong ngoặc kép, hoặc dạng "01. ...") là phần tĩnh, KHÔNG đưa vào khối.
   Dòng hướng dẫn kiểu "Từng ... hiện theo khung hình", "Khung cuối: ..." không phải chữ in lên ảnh.
2. Thêm 1–2 biểu tượng quan trọng lấy từ cột "Hình ảnh" (dấu hỏi, khiên, cảnh báo...) với
   `"chu": ""` và kiểu `bat`.
3. Tối đa 7 khối mỗi cảnh. Cảnh chỉ có tiêu đề và một hình minh họa thì để `"khoi": []`.
4. `chu`: viết đúng từng chữ tiếng Việt có dấu, ngắn gọn (tối đa khoảng 8 từ).
5. `hien_khi`: 2–6 từ LIÊN TIẾP chép NGUYÊN VĂN từ lời đọc của chính cảnh đó, đúng chỗ nhắc tới
   khối. Kiểm tra lại bằng cách tìm cụm đó trong lời đọc; không tìm thấy thì chọn cụm khác.
   Các khối xếp theo đúng thứ tự xuất hiện trong lời đọc.
   Lời đọc không nhắc riêng từng khối (ví dụ câu tóm tắt) thì rải các cụm liên tiếp của câu
   cho các khối lần lượt hiện đều.
6. `hieu_ung`: `truot` cho thẻ, dòng, bước, chữ; `bat` cho biểu tượng, con dấu, huy hiệu;
   `mo_dan` cho hình lớn; `nhip` chỉ cho nút kêu gọi cuối video ("Dùng thử miễn phí").
7. `vung`: để `null` (AI tạo ảnh sẽ điền). `tam_zoom`: điểm camera zoom tới, thường là giữa
   cụm khối.

Đồng thời viết thêm cho mỗi cảnh một dòng `- Picture (English): ...` mô tả cụ thể bằng tiếng Anh
hình cần vẽ (nhân vật, đồ vật, bố cục; khối nằm ở đâu so với tiêu đề và hình minh họa), dựa
trên dòng "Picture (Vietnamese brief)". Giữ nguyên dòng tiếng Việt.

## Bước 3. Kiểm tra trước khi giao

- Mọi `hien_khi` đều có trong lời đọc của đúng cảnh đó (so khớp nguyên văn, kể cả dấu).
- Mọi khối JSON hợp lệ (không chú thích, không dấu phẩy thừa).
- Phần "Final deliverable" ở đầu file còn nguyên: AI phải trả về MỘT file `hieu_ung.json` tổng
  hợp sau khi tạo xong toàn bộ ảnh.

## Định dạng trả lời cho người dùng (tiếng Việt)

1. Đường dẫn file đã tạo: `du-an/<tên>/assets/hieu-ung/prompt_tao_anh.md`, kèm số cảnh và tổng số khối hiệu ứng.
2. Hướng dẫn ngắn:
   - Mở ChatGPT hoặc Gemini (cần công cụ vừa tạo ảnh vừa trả được chữ/file; Midjourney không
     trả được JSON), dán toàn bộ nội dung file. Nếu AI dừng giữa chừng, nhắn "tiếp tục".
   - Tải từng ảnh, lưu vào `du-an/<tên>/assets/anh/` đúng tên AI ghi.
   - Khi AI gửi file tổng hợp, lưu thành `du-an/<tên>/assets/hieu-ung/hieu_ung.json` (dán nguyên câu trả lời
     vào file cũng được, code tự lấy phần JSON).
   - Dựng video: `./tao-video du-an/<tên>`.
3. Nhắc: nếu AI vẽ sai dấu tiếng Việt, code vẫn so khớp được (bỏ qua dấu), nhưng nên yêu cầu
   AI vẽ lại ảnh đó vì chữ sai sẽ hiện trong video.
