---
name: tao-kich-ban
description: Chuyển một bài viết (URL, file hoặc nội dung dán vào) thành kịch bản video dọc 9:16 dạng Word (.docx) theo đúng mẫu của Video_AI — bảng 4 cột "Cảnh / Thời gian · Hình ảnh · Chữ trên màn hình · Lời đọc", bản rút gọn quảng cáo, caption, gợi ý sản xuất — không ghi mốc thời gian ước tính. File tạo ra dùng thẳng cho ./tao-video và /claude-tao-anh. Dùng khi người dùng gọi /tao-kich-ban, hoặc muốn viết kịch bản video TikTok/Reels/Shorts từ một bài viết.
argument-hint: "[URL bài viết | đường dẫn file | du-an/<tên>]"
---

# Viết kịch bản video từ bài viết

Đầu vào của người dùng: $ARGUMENTS

Thư mục skill (chứa `scripts/tao_docx.py` và `mau/vi_du_lich_dat_xe.json`) là thư mục của file
SKILL.md này. Luồng dựng video nằm ở `/Users/duongca/WorkSpace/Video_AI`.

- URL: đọc bài bằng WebFetch (lấy toàn văn, không tóm tắt).
- File (.docx, .pdf, .md, .txt): đọc file.
- Nội dung dán trong tin nhắn: dùng nguyên văn.
- Trống: hỏi người dùng bài viết nguồn.

Hỏi tên dự án (gợi ý một tên ngắn không dấu, ví dụ `lich-dat-xe`) nếu người dùng chưa nêu.

## Bước 1. Đọc bài và rút ý

Trước khi viết, ghi ra (chỉ để dùng nội bộ, không đưa vào file):
1. Đối tượng xem là ai, "nỗi đau" cụ thể của họ mà bài nhắc tới.
2. Ý cốt lõi của bài: danh sách tiêu chí, các bước, các nhóm thông tin… (thường thành cảnh 4).
3. Tính năng/giải pháp sản phẩm được bài nêu (thường thành cảnh 5, 6).
4. Lợi ích, câu kêu gọi, hotline.

Chỉ dùng thông tin có trong bài. Không thêm số liệu, tính năng, cam kết mà bài không nói.
Thông tin thương hiệu mặc định (khi bài không ghi khác): G-Car, phần mềm quản lý cho thuê xe,
hotline 098.1855.854, có dùng thử miễn phí.

## Bước 2. Viết kịch bản theo khung 8 cảnh

Mạch chuẩn (lấy từ mẫu `mau/vi_du_lich_dat_xe.json` — đọc file này trước khi viết để bắt đúng
giọng văn và độ dài):

| # | Tên cảnh (đổi cho hợp bài) | Vai trò | Lời đọc |
|---|---|---|---|
| 1 | Mở đầu | Câu hỏi/tình huống chạm đúng nỗi đau trong 3 giây đầu | 1 câu hỏi |
| 2 | Nỗi đau | 3–4 nỗi đau cụ thể, cắt nhanh nhiều khung | 3–4 câu ngắn, nhịp nhanh |
| 3 | Chuyển ý | "Vấn đề không nằm ở bạn…", đặt câu hỏi dẫn vào nội dung chính | 2 câu |
| 4 | Nội dung chính của bài (vd. "5 nhóm thông tin") | Kiến thức/tiêu chí cốt lõi, mỗi ý một thẻ | Đọc lần lượt từng ý |
| 5 | Giải pháp G-Car | Tính năng phần mềm giải quyết đúng các nỗi đau ở cảnh 2 | 3–4 câu |
| 6 | Xử lý phát sinh | Các tình huống khó, phần mềm giúp thấy ngay | 1 câu hỏi + 1 câu đáp |
| 7 | Lợi ích | 3–4 lợi ích ngắn | Câu ngắn, dứt khoát |
| 8 | Kêu gọi hành động | Xóa rào cản + dùng thử + hotline | Kết bằng "Dùng thử … gọi <hotline>!" |

Được thêm/bớt cảnh khi bài cần (6–10 cảnh), nhưng giữ mạch: mở đầu → nỗi đau → chuyển ý →
nội dung chính → giải pháp → lợi ích → kêu gọi. Cảnh cuối luôn là kêu gọi hành động.

### Quy tắc từng cột

**Cảnh / Thời gian** — chỉ tên cảnh (code tự đánh số `1.`, `2.`…). **Không ghi mốc thời gian
hay số giây ở bất cứ đâu**: `./tao-video` tự ghi mốc thật vào cột này và dòng "Thời lượng"
sau khi tạo giọng đọc.

**Hình ảnh** — mô tả cụ thể để vẽ được: nhân vật, hành động, đồ vật, cảm xúc.
- Cảnh cần nhiều ảnh cắt nhanh: `mo_ta` ghi đúng `Cắt nhanh N khung:` và `khung` có đúng N ý
  (code đếm "N khung" để biết cần N ảnh).
- Một ảnh gồm nhiều phần (vd. quay màn hình nhiều bước): `mo_ta` ghi `Quay màn hình …:` (KHÔNG
  có chữ "khung") rồi liệt kê ý trong `khung`.
- Cảnh màn hình phần mềm: mô tả đúng màn hình/tính năng bài nêu.

**Chữ trên màn hình** — mỗi phần tử một dòng, in đậm.
- Tiêu đề/câu nói của nhân vật đặt trong ngoặc kép “…”.
- Danh sách: mỗi ý một dòng, tối đa khoảng 8 từ; có thể mở đầu bằng emoji (🚗 👤 ⏰ 💰 📋 ✅).
- Mỗi ý trên màn hình phải được NHẮC TỚI trong lời đọc của chính cảnh đó, theo đúng thứ tự
  (bước /claude-tao-anh cần chép cụm từ trong lời đọc để canh lúc chữ hiện).
- Dòng hướng dẫn dựng (không in lên ảnh) như "Từng nỗi đau hiện theo khung hình",
  "Khung cuối: chữ đỏ “TRÙNG LỊCH!”" được phép.
- Cảnh cuối phải có `Hotline: …` và `Dùng thử miễn phí` (để video dựng bảng kêu gọi hành động).

**Lời đọc** — văn nói, gần gũi, xưng "bạn"; câu ngắn.
- Không chứa dấu ngoặc kép (code lấy lời đọc là phần nằm trong “…” của ô).
- Tên thương hiệu viết bình thường ("G-Car"); số điện thoại viết dạng 098.1855.854 — code đọc
  đúng. Từ viết tắt/tên riêng khó đọc khác: liệt kê cho người dùng ở bước báo cáo.
- Tổng độ dài bản chính khoảng 250–310 tiếng (≈ 80–95 giây). Mẫu: 282 tiếng.

### Các phần khác

- `tieu_de`: tiêu đề gây chú ý, dạng "Câu hỏi nỗi đau? Lời thúc giục!".
- `nguon`: `Bài viết “<tiêu đề bài>” – <tên miền>`.
- `giong_doc`: tính cách giọng + nhịp từng phần; ghi cách đọc tên riêng nếu có (“G-Car” đọc là “Gi Ca”).
- `nhan_vat`: 1–2 nhân vật xuyên suốt (người dẫn chuyện + người phụ).
- `giong` / `toc_do`: mặc định `vi-VN-NamMinhNeural`, `+10%` (giọng nữ: `vi-VN-HoaiMyNeural`).
- `rut_gon`: đúng 3 câu cho bản quảng cáo — câu móc nỗi đau / giải pháp / kêu gọi + hotline;
  tổng 40–60 tiếng. Chỉ ghi lời đọc, không ghi thời gian.
- `caption`: 3 dòng mở đầu bằng emoji (📅 nỗi đau · 👉 giải pháp · 📞 hotline, dùng thử).
- `hashtag`: 5–7 hashtag không dấu, gồm `#GCar`.
- `goi_y`: các mục "Nhạc nền", "Phụ đề", gợi ý quay/che dữ liệu cho cảnh màn hình phần mềm, và
  BẮT BUỘC mục `"nhan": "Ảnh bìa"` có chữ to trong ngoặc kép, vd.
  `Chủ xe ôm đầu giữa đống sổ sách, kèm chữ to “HẾT CẢNH TRÙNG LỊCH XE”.`

## Bước 3. Ghi JSON và tạo file Word

1. Ghi kịch bản ra JSON đúng cấu trúc file mẫu `mau/vi_du_lich_dat_xe.json` vào thư mục tạm
   (scratchpad), tên `kich_ban.json`.
2. Tạo file Word vào dự án (thư mục chưa có thì tạo; `kich-ban/` chỉ được có đúng 1 file .docx —
   nếu đã có file khác, hỏi người dùng trước khi ghi):

```bash
/Users/duongca/WorkSpace/Video_AI/.venv/bin/python <thư mục skill>/scripts/tao_docx.py \
  <scratchpad>/kich_ban.json \
  /Users/duongca/WorkSpace/Video_AI/du-an/<tên>/assets/kich-ban/Kich-ban-video-<tên>.docx
```

Script kiểm tra nội dung trước khi ghi, rồi đọc lại file bằng chính code của Video_AI.
- Dòng `✗` là lỗi, file chưa được ghi: sửa JSON và chạy lại.
- Dòng `!` là cảnh báo (số cảnh, độ dài lời đọc, thiếu kêu gọi hành động): sửa trừ khi có lý
  do rõ ràng, và nêu lý do trong báo cáo.

## Bước 4. Tự rà trước khi giao

- Mọi thông tin trong lời đọc và chữ trên màn hình đều có trong bài nguồn.
- Mỗi dòng "Chữ trên màn hình" (trừ tiêu đề và dòng hướng dẫn) có cụm từ tương ứng trong lời
  đọc cùng cảnh.
- Nỗi đau ở cảnh 2 được giải quyết ở cảnh 5–7.
- Không có mốc thời gian, số giây ước tính ở bất kỳ đâu.

## Định dạng trả lời cho người dùng (tiếng Việt)

1. Đường dẫn file `.docx`, số cảnh, số tiếng lời đọc (bản chính / rút gọn), danh sách tên cảnh.
2. Tóm tắt 2–3 dòng mạch kịch bản (móc mở đầu là gì, nội dung chính là gì).
3. Từ có thể bị đọc sai (nếu có), gợi ý thêm vào mục `[cach_doc]` của
   `du-an/<tên>/assets/cau-hinh/cau_hinh.toml`, vd. `"8Car" = "Tám Ca"`.
4. Bước tiếp theo: `/claude-tao-anh du-an/<tên>` để tạo prompt vẽ ảnh, rồi `./tao-video du-an/<tên>`.
