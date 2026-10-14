---
name: photorealistic
description: Viết prompt sinh ảnh GIỐNG ẢNH CHỤP THẬT (photorealistic, không hoạt hình) cho cảnh trong kịch bản video hoặc bài đăng ngành cho thuê xe ô tô tự lái tại Việt Nam (thương hiệu G-Car). Dùng khi người dùng gọi /photorealistic, hoặc muốn tạo prompt ảnh giống thật cho một cảnh, một danh sách cảnh hay cả kịch bản video.
argument-hint: "[mô tả cảnh | danh sách cảnh | đường dẫn file kịch bản]"
---

# Tạo prompt sinh ảnh giống thật (photorealistic)

Đầu vào của người dùng: $ARGUMENTS

Nếu đầu vào là đường dẫn file (.docx, .md, .txt), hãy đọc file đó và viết prompt cho từng cảnh.
Nếu đầu vào trống, dùng kịch bản hoặc cảnh gần nhất trong cuộc trò chuyện. Nếu không có, hỏi người dùng muốn tạo ảnh cho cảnh nào.

## Mục tiêu
Khi người dùng mô tả một cảnh, hoặc đưa một cảnh trong kịch bản video, hãy viết prompt sinh ảnh
ra kết quả GIỐNG ẢNH CHỤP THẬT, không phải hoạt hình hay minh họa.
Bối cảnh mặc định: ngành cho thuê xe ô tô tự lái tại Việt Nam, thương hiệu G-Car.

## Quy tắc bắt buộc
1. Luôn viết prompt bằng TIẾNG ANH. Giải thích cho người dùng bằng tiếng Việt.
2. Mô tả như một BỨC ẢNH CHỤP: người thật, đồ vật thật, ánh sáng, máy ảnh, ống kính.
   KHÔNG dùng các từ: illustration, character, icon, cartoon, vector, flat, cute.
3. Biến ý trừu tượng thành hành động cụ thể, nhìn thấy được.
   - Sai: "người đặt khác người lái", "≠", "nỗi lo"
   - Đúng: "two different young men stand at the desk, the one in green reaching for the car key
     while the car owner looks at a booking on his phone, puzzled"
4. KHÔNG yêu cầu AI vẽ chữ, logo, biểu tượng hay số trên ảnh (AI làm hỏng dấu tiếng Việt).
   Chữ và logo G-Car sẽ được chèn sau bằng CapCut hoặc Canva. Thay vào đó, chừa khoảng trống cho chữ.
5. Màn hình điện thoại hoặc laptop chỉ mô tả chung ("a booking app on screen", "a calendar
   interface"), không ghi chữ cụ thể.
6. Người trong ảnh là người Việt Nam, bối cảnh Việt Nam (Hà Nội hoặc TP.HCM),
   biển số xe để mờ hoặc không nhìn rõ.
7. Mỗi prompt chỉ có MỘT khoảnh khắc, tối đa 3 người, hành động rõ ràng.

## Cấu trúc prompt (theo đúng thứ tự)
[1. Loại ảnh] + [2. Chủ thể và hành động] + [3. Cảm xúc và biểu cảm] + [4. Bối cảnh]
+ [5. Ánh sáng] + [6. Máy ảnh và bố cục] + [7. Đoạn phong cách cố định]

## Nhân vật cố định (dùng lại đúng từng chữ để các ảnh đồng nhất)
- CAR_OWNER: "a Vietnamese man in his late 30s, short neat black hair, clean-shaven,
  light blue button-up shirt with rolled sleeves, khaki trousers, brown leather belt"
- STAFF: "a young Vietnamese woman in her mid 20s, shoulder-length black hair,
  white blouse, name badge"
- CUSTOMER: mô tả riêng theo cảnh, khác màu áo với CAR_OWNER để dễ phân biệt.

## Bối cảnh cố định
- OFFICE: "a bright modern car rental office in Hanoi, wooden key board with rows of car keys
  on the wall, wooden desk with a laptop and a tray of car keys, potted green plants,
  large glass door showing white and dark SUVs parked outside on a sunny tree-lined street"
- PARKING: "an outdoor car rental parking lot in Hanoi, row of clean white and dark SUVs and
  sedans, trees and low-rise buildings in the background"

## Đoạn phong cách cố định (luôn gắn vào cuối prompt)
Photorealistic editorial photograph, shot on a full-frame DSLR, 35mm lens, f/2.8,
natural daylight, soft realistic shadows, shallow depth of field, true-to-life skin texture
and pores, natural hand anatomy, candid authentic moment, clean warm color grading,
high detail, sharp focus on the main subject

## Tỷ lệ khung hình
- Video TikTok, Reels, Shorts (mặc định): 9:16, thêm "vertical composition, empty space at the
  top third for text overlay"
- Bài đăng Facebook hoặc website: 16:9 hoặc 3:2, thêm "horizontal composition, empty space on
  one side for text overlay"

## Negative prompt (luôn đưa kèm)
cartoon, illustration, anime, 3D render, CGI, vector, flat design, drawing, painting,
plastic skin, doll face, distorted hands, extra fingers, deformed face, cross-eyed,
text, letters, words, watermark, logo, signature, readable license plate, blurry, oversaturated

## Định dạng trả lời
Với mỗi ảnh, trả về:
1. **Tên cảnh** (tiếng Việt)
2. **Prompt** (tiếng Anh, trong khối code, đã thay hết CAR_OWNER, OFFICE... bằng mô tả đầy đủ)
3. **Negative prompt** (trong khối code; khi có nhiều cảnh, chỉ in một lần ở cuối)
4. **Chữ chèn sau** (tiếng Việt: dòng chữ cần thêm khi dựng video)
5. Nếu dùng Midjourney: thêm `--ar 9:16 --style raw --v 7` vào cuối prompt.

Cuối câu trả lời, nhắc người dùng: nếu công cụ tạo ảnh cho tải ảnh tham chiếu (ChatGPT, Gemini,
Midjourney `--cref`), hãy tải kèm ảnh chủ xe mẫu để nhân vật đồng nhất giữa các ảnh.

## Ví dụ
**Đầu vào:** "Nỗi lo 2/5: Người đặt một người, người lái một người"

**Prompt:**
```
Photorealistic photo of a tense moment at a car rental desk. A Vietnamese man in his late 30s,
short neat black hair, clean-shaven, light blue button-up shirt with rolled sleeves, khaki
trousers, stands behind a wooden desk holding a car key in one hand and a smartphone showing a
booking app in the other, looking puzzled and cautious. In front of the desk stand two different
young Vietnamese men: one in an orange hoodie gesturing that he made the booking, and one in a
green t-shirt, navy cap and round glasses reaching out for the car key. A bright modern car
rental office in Hanoi, wooden key board with rows of car keys on the wall, potted green plants,
large glass door showing white and dark SUVs parked outside on a sunny tree-lined street.
Soft natural window light from the side. Medium shot at eye level, vertical composition, empty
space at the top third for text overlay. Photorealistic editorial photograph, shot on a
full-frame DSLR, 35mm lens, f/2.8, natural daylight, soft realistic shadows, shallow depth of
field, true-to-life skin texture and pores, natural hand anatomy, candid authentic moment,
clean warm color grading, high detail, sharp focus on the main subject
```
**Chữ chèn sau:** "NỖI LO 2/5" · "Người đặt một người, người lái một người"
