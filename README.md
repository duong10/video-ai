# Video AI

Tạo video dọc 9:16 (TikTok, Reels, Shorts) từ **một kịch bản Word** và **ảnh từng cảnh**.
Chương trình tự làm phần còn lại:

- **Giọng đọc AI** tiếng Việt (Microsoft Edge TTS), đọc đúng lời trong kịch bản.
- **Ghi lại mốc thời gian thật** của từng cảnh vào file Word.
- **Dựng video**:
  - ảnh zoom chậm, cảnh nhiều khung thì cắt nhanh;
  - chữ và khối nội dung hiện ra đúng lúc giọng đọc nhắc tới;
  - có phụ đề và nhạc nền (nhạc tự hạ nhỏ khi có lời).
- **Prompt cho AI vẽ ảnh** (ChatGPT, Gemini), kèm file mô tả hiệu ứng chuyển động.

Có hai cách dùng: **giao diện web** (`./giao-dien`) hoặc **dòng lệnh** (`./tao-video`). Cả hai
cho ra cùng một kết quả. Chạy được trên **macOS** và **Windows**.

---

## Cấu trúc repo

```
video-ai/
├── giao-dien              mở giao diện web (macOS)
├── giao-dien.cmd          mở giao diện web (Windows)
├── tao-video              tạo video bằng dòng lệnh (macOS)
├── tao-video.cmd          tạo video bằng dòng lệnh (Windows)
├── requirements.txt       thư viện cần cài
├── san_xuat/              code của dự án
│   ├── tao_video.py         luồng chính: kịch bản + ảnh -> giọng đọc -> video
│   ├── tao_tu_docx.py       đọc kịch bản Word, tạo giọng, ghi mốc thời gian vào file Word
│   ├── giong_doc.py         gọi Edge TTS, cách đọc riêng, ghép câu
│   ├── dung_video.py        dựng video (moviepy)
│   ├── do_khoi.py           tự dò các khối chữ trên ảnh thiết kế
│   ├── hieu_ung.py          đọc hieu_ung.json, tạo prompt cho AI vẽ ảnh
│   ├── cau_hinh.py          file cấu hình của từng dự án
│   ├── du_an.py             cấu trúc thư mục một dự án
│   ├── giao_dien.py         server của giao diện web
│   └── web/index.html       trang giao diện
├── skills/                prompt/skill cho AI tạo ảnh (xem mục "Tạo ảnh bằng AI")
├── ui-mau/                ảnh thiết kế mẫu của giao diện
├── edge-tts/              submodule: fork của rany2/edge-tts (thư viện giọng đọc)
├── moviepy/               submodule: fork của Zulko/moviepy (thư viện dựng video)
└── du-an/                 các dự án video (KHÔNG đưa lên git)
```

- `edge-tts/` và `moviepy/` là **submodule**, mỗi thư mục là một repo riêng (fork của bạn).
  Hai repo này **chỉ chứa code thư viện**, không chứa dự án video.
- `du-an/` và `.venv/` nằm trong `.gitignore`: ảnh, giọng đọc, video rất nặng và chỉ giữ trên máy.

---

## Cài đặt (một lần cho mỗi máy)

Cần có mạng khi dùng, vì giọng đọc được tạo trên máy chủ của Microsoft. Python 3.13 không cần
cài riêng: `uv` tự tải về.

### macOS

1. Cài [uv](https://docs.astral.sh/uv/) (công cụ quản lý Python) bằng Terminal:
   ```sh
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
   Máy chưa có `git` thì chạy `xcode-select --install`.
2. Tải code và cài thư viện:
   ```sh
   git clone --recurse-submodules https://github.com/duong10/video-ai.git
   cd video-ai
   uv venv --python 3.13 .venv
   uv pip install --python .venv/bin/python -r requirements.txt
   ```
3. Chạy thử: `./giao-dien`

### Windows (10 / 11)

1. Cài **Git for Windows** tại [git-scm.com/download/win](https://git-scm.com/download/win).
   Cứ bấm Next, giữ các lựa chọn mặc định.
2. Mở **PowerShell** (bấm Start, gõ `PowerShell`) rồi cài **uv**:
   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```
   Cài xong thì **đóng PowerShell và mở lại**, để máy nhận lệnh `uv`.
3. Tải code và cài thư viện. Có thể đặt thư mục ở đâu cũng được, ví dụ trong `Documents`:
   ```powershell
   cd $HOME\Documents
   git clone --recurse-submodules https://github.com/duong10/video-ai.git
   cd video-ai
   uv venv --python 3.13 .venv
   uv pip install --python .venv\Scripts\python.exe -r requirements.txt
   ```
4. Chạy thử: `.\giao-dien.cmd`

**Khác biệt khi dùng Windows:**

| macOS | Windows |
|---|---|
| `./giao-dien` | `.\giao-dien.cmd` |
| `./tao-video du-an/<tên>` | `.\tao-video.cmd du-an\<tên>` |
| `.venv/bin/python` | `.venv\Scripts\python.exe` |

Mọi lệnh trong README viết theo kiểu macOS. Trên Windows, đổi theo bảng trên.

- **Tên file ảnh không được chứa dấu `:`** (Windows không cho phép). Với cảnh nhiều khung, đặt tên
  kiểu `02a_….png`, `02b_….png`, hoặc thả ảnh vào ô trên giao diện để tên được đặt tự động.
- **Hiệu ứng khối chữ**: trên macOS, chương trình dùng OCR có sẵn của máy để đọc chữ trong ảnh
  thiết kế, nhờ đó từng khối hiện ra đúng lúc giọng đọc nhắc tới. Windows không có OCR này nên
  các khối được chia đều theo thời gian cảnh. Muốn khớp chính xác trên Windows thì dùng
  `hieu_ung.json` do AI trả về (xem mục "Tạo ảnh bằng AI").
- **Xoá dự án** trên giao diện: macOS chuyển vào Thùng rác của máy; Windows chuyển vào
  `du-an\.thung-rac\`, muốn giải phóng dung lượng thì tự xoá thư mục đó.
- Font chữ dùng Arial và Segoe UI Emoji, có sẵn trên Windows.

### Lỡ clone thiếu submodule

Nếu thư mục `edge-tts/` hoặc `moviepy/` trống (do quên `--recurse-submodules`), chạy:

```sh
git submodule update --init --recursive
```

---

## Người dùng cần cung cấp gì

Mỗi video là một **dự án** = một thư mục trong `du-an/`:

```
du-an/<tên>/
  assets/
    kich-ban/     1 file kịch bản .docx           BẮT BUỘC
    anh/          ảnh từng cảnh + ảnh bìa          BẮT BUỘC (ảnh bìa không bắt buộc)
    nhac/         1 file nhạc nền                  không bắt buộc
    hieu-ung/     hieu_ung.json do AI trả về      không bắt buộc
    cau-hinh/     cau_hinh.toml                   tự sinh, sửa nếu muốn
  output/         kết quả, chương trình tự tạo
```

Bỏ file lẫn lộn vào thẳng thư mục dự án cũng được, chương trình tự xếp vào đúng chỗ.

### 1. Kịch bản Word (.docx), bắt buộc

Một **bảng chính** với các cột:

| Cột | Nội dung |
|---|---|
| **Cảnh / Thời gian** | Dòng đầu là số + tên cảnh: `1. Mở đầu`, `2. Những nỗi lo`… Dòng sau là mốc giờ, có thể để trống: chương trình tự điền. |
| **Hình ảnh** | Mô tả hình. Cảnh nhiều ảnh thì ghi `Cắt nhanh 5 khung: ① … ② …`. |
| **Chữ trên màn hình** | Chữ hiện trên video (tiêu đề, danh sách, nhãn…). |
| **Lời đọc** | Lời của giọng đọc, đặt **trong ngoặc kép “…”**. Ghi chú ngoài ngoặc kép sẽ bị bỏ qua. |

Không bắt buộc:

- Dòng `Ảnh bìa: … “CHỮ TO”`: chữ to hiện trên ảnh bìa ở đầu video.
- Dòng `Thời lượng: … giọng vi-VN-NamMinhNeural, tốc độ +10%`: chọn giọng và tốc độ mặc định.
- Bảng **"Bản rút gọn"** (có cột `Thời gian` và `Lời đọc`): chương trình tạo thêm giọng đọc
  `quang_cao_30s` để làm quảng cáo. Bản rút gọn chỉ có giọng đọc, không dựng video.

### 2. Ảnh từng cảnh, bắt buộc

- Ảnh dọc 9:16 (khuyên dùng 1080×1920), định dạng `.png`, `.jpg`, `.jpeg` hoặc `.webp`.
- **Tên file phải có số cảnh** để chương trình biết ảnh thuộc cảnh nào:
  - `01_mo_dau.png`, `3.jpg`, `Cảnh 4 · Việc 1.png`;
  - cảnh nhiều khung: `02a_….png`, `02b_….png`… (macOS còn nhận `Cảnh 2 · Nỗi lo 1:5.png`,
    nhưng Windows không cho dùng dấu `:` trong tên file);
  - ảnh bìa: tên có chữ `bìa`, hoặc bắt đầu bằng `00` (ví dụ `00_anh_bia.png`).
- Trên giao diện chỉ cần **thả ảnh vào đúng ô của cảnh**, tên file được đặt tự động.
- Cảnh cuối là cảnh kêu gọi hành động (có hotline hoặc chữ "Dùng thử") thì có thể để
  trống ảnh. Khi đó video dùng ảnh cảnh trước làm mờ làm nền.

### 3. Nhạc nền, không bắt buộc

Một file `.mp3`, `.m4a`, `.wav` hoặc `.aac`. Nhạc tự hạ nhỏ khi có lời đọc.

### 4. hieu_ung.json, không bắt buộc

Là file mô tả hiệu ứng chuyển động của từng ảnh, do AI vẽ ảnh trả về (xem mục "Tạo ảnh bằng
AI"). Cảnh nào có trong file này thì dựng đúng theo mô tả. Cảnh không có thì chương trình tự dò
các khối chữ trên ảnh.

---

## Các bước tạo video

### Cách 1: Giao diện web (khuyên dùng)

```sh
./giao-dien                 # mở http://127.0.0.1:8765 trên trình duyệt (Windows: .\giao-dien.cmd)
./giao-dien --cong 9000     # dùng cổng khác
./giao-dien --khong-mo      # không tự mở trình duyệt
```

1. **Tạo dự án**: bấm `＋ Dự án mới` ở thanh bên trái.
2. **Kịch bản**: kéo thả file `.docx` vào ô Kịch bản. Giao diện báo số cảnh, hoặc báo lỗi nếu
   bảng sai mẫu.
3. **Ảnh**: thả ảnh vào ô của từng cảnh. Ô thiếu ảnh hiện màu đỏ.
   - Chưa có ảnh: bấm **✨ Tạo prompt cho AI vẽ ảnh**, sao chép rồi dán vào ChatGPT/Gemini.
   - AI trả về JSON hiệu ứng thì dán vào ô **Hiệu ứng (AI)**.
4. **Nhạc nền** (tuỳ chọn): thả file nhạc vào ô Nhạc nền.
5. **Cài đặt** (tự lưu):
   - giọng đọc nam/nữ và tốc độ; bấm **▶ Nghe thử** để nghe 1–2 câu đầu kịch bản;
   - cách đọc riêng, ví dụ chữ `8Car` thì đọc là `Tám Ca`;
   - chữ trên màn hình, phụ đề, nhạc nền, âm lượng nhạc.
6. **Tạo video**: bấm **▶ Tạo video**.
   - Lần đầu, chương trình tạo giọng đọc (khoảng 15–60 giây) rồi dựng video (khoảng 30 giây).
   - Nhật ký và thanh tiến độ hiện ở cột phải. Muốn huỷ thì bấm **■ Dừng**.
   - Xong thì xem video ngay trong khung điện thoại, bấm thanh thời gian để nhảy tới từng
     cảnh, và bấm **⬇ Tải** để tải video về.

Các nút khác:

- **Dùng lại giọng đọc đã tạo**: bỏ qua bước tạo giọng, dùng khi chỉ đổi ảnh hoặc tuỳ chọn
  video. Ô này tự tắt khi bạn đổi kịch bản, giọng, tốc độ hoặc cách đọc.
- **🎙️ Chỉ tạo giọng**: tạo giọng đọc, không dựng video.
- **📸 Xem thử ảnh**: chụp vài khung hình tại các giây bạn chọn để xem nhanh, không cần dựng
  cả video.
- **Xoá dự án**: rê chuột vào dự án ở thanh trái rồi bấm 🗑, hoặc bấm link cạnh đường dẫn
  dự án. Dự án được chuyển vào Thùng rác của máy (Windows: `du-an\.thung-rac\`), có thể lấy lại.
- File xoá trên giao diện (ảnh, nhạc…) được chuyển vào `assets/thung-rac/` của dự án.

**Tắt giao diện**: bấm `Ctrl + C` trong cửa sổ Terminal/PowerShell đang chạy. Nếu đã đóng cửa sổ
đó mà giao diện vẫn chạy ngầm:

- macOS: `pkill -f giao_dien.py`
- Windows (PowerShell):
  ```powershell
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object CommandLine -like '*giao_dien.py*' | ForEach-Object { Stop-Process -Id $_.ProcessId }
  ```

- Đóng tab trình duyệt **không** tắt giao diện.
- Tắt giao diện khi đang dựng video thì việc dựng bị dừng. Video cũ vẫn giữ nguyên.

### Cách 2: Dòng lệnh

Windows: thay `./tao-video du-an/<tên>` bằng `.\tao-video.cmd du-an\<tên>`.

```sh
./tao-video du-an/<tên>                      # lần đầu với tên mới: tạo sẵn khung thư mục
./tao-video du-an/<tên>                      # có đủ kịch bản + ảnh: tạo giọng + dựng video
./tao-video                                  # mọi dự án trong du-an/ chưa có video
./tao-video du-an/<tên> --tao-prompt         # tạo prompt cho AI vẽ ảnh
./tao-video du-an/<tên> --bo-qua-giong       # dùng lại giọng cũ (chỉ đổi ảnh / tuỳ chọn video)
./tao-video du-an/<tên> --chi-giong          # chỉ tạo giọng đọc
./tao-video du-an/<tên> --snapshots 3 30 60  # chỉ chụp khung hình tại các giây này
./tao-video du-an/<tên> --khong-nhac         # không dùng nhạc nền
```

### Cấu hình dự án: `assets/cau-hinh/cau_hinh.toml`

File này tự sinh và liệt kê **đủ mọi tuỳ chọn**, mỗi dòng có chú thích. Giá trị `false` nghĩa là
dùng mặc định. Giao diện web sửa file này giúp bạn; nếu dùng dòng lệnh thì sửa tay.

| Mục | Ý nghĩa | Mặc định |
|---|---|---|
| `[giong_doc] giong` | `vi-VN-NamMinhNeural` (nam) hoặc `vi-VN-HoaiMyNeural` (nữ) | theo dòng "Thời lượng", không có thì giọng nam |
| `[giong_doc] toc_do` | ví dụ `"+15%"`, `"-5%"` | `"+10%"` |
| `[cach_doc]` | `"8Car" = "Tám Ca"`: phụ đề hiện bên trái, giọng đọc bên phải | có sẵn `"G-Car" = "Gi Ca"`; số điện thoại tự đọc theo cụm |
| `[video] chu_tren_man_hinh` | `"bat"` luôn vẽ chữ, `"tat"` không vẽ | tự động: ảnh chụp thì vẽ, ảnh thiết kế đã có chữ thì không |
| `[video] tat_hieu_ung_khoi` | `true` = tắt hiệu ứng tự dò khối | bật |
| `[video] tat_phu_de` | `true` = không hiện phụ đề | có phụ đề |
| `[video] tat_nhac_nen` | `true` = không dùng nhạc nền | dùng nếu có file |
| `[video] am_luong_nhac` | 0 đến 1 | `0.07` |
| `[video_90s.N]` | riêng cảnh N: `toc_do`, `nghi_truoc`, `nghi_giua_cau` (giây) | tốc độ chung; nghỉ trước cảnh 0.8s (cảnh đầu 0.3s), giữa các câu 0.35s |

Đổi phần giọng đọc (giọng, tốc độ, cách đọc, từng cảnh) thì phải **tạo lại giọng**. Chỉ đổi phần
`[video]` thì dùng lại giọng cũ cho nhanh.

### Kết quả

```
du-an/<tên>/output/
  <tên>.mp4                video hoàn chỉnh
  giong-doc/video_90s/     giọng đọc (.mp3), phụ đề (.srt), bảng mốc thời gian từng cảnh
  giong-doc/quang_cao_30s/ giọng đọc bản rút gọn (nếu kịch bản có)
  anh-kiem-tra/            ảnh chụp thử (Xem thử ảnh / --snapshots)
```

File kịch bản `.docx` được ghi lại mốc thời gian thật và dòng "Thời lượng". Bản gốc trước khi
sửa được giữ trong `assets/kich-ban/ban-goc/`.

---

## Tạo ảnh bằng AI

1. Tạo prompt: bấm **✨ Tạo prompt cho AI vẽ ảnh** trên giao diện, hoặc chạy
   `./tao-video du-an/<tên> --tao-prompt`. Prompt được lưu vào `assets/hieu-ung/prompt_tao_anh.md`.
2. Dán toàn bộ prompt vào ChatGPT hoặc Gemini. AI vẽ từng ảnh và đặt sẵn tên file theo số cảnh.
3. Lưu ảnh vào dự án (thả vào giao diện, hoặc chép vào `assets/anh/`).
4. AI trả về JSON tổng hợp: dán vào ô **Hiệu ứng (AI)**, hoặc lưu thành
   `assets/hieu-ung/hieu_ung.json`.

Thư mục `skills/` có sẵn các skill:

| Skill | Dùng ở đâu | Tác dụng |
|---|---|---|
| `chatgpt-gemini-tao-anh` | Đưa vào ChatGPT (GPT tuỳ chỉnh) hoặc Gemini (Gem) làm hướng dẫn | Vẽ đủ ảnh cho kịch bản và trả về `hieu_ung.json` |
| `claude-tao-anh` | Claude Code: chép vào `~/.claude/skills/`, gọi `/claude-tao-anh` | Tạo `prompt_tao_anh.md` từ kịch bản |
| `photorealistic` | Claude Code: chép vào `~/.claude/skills/`, gọi `/photorealistic` | Viết prompt ảnh giống ảnh chụp thật (không hoạt hình) |

---

## Cập nhật code

### Lấy code mới của repo này (máy khác đã push lên)

```sh
git pull
git submodule update --init --recursive     # đưa edge-tts, moviepy về đúng bản repo đang dùng
uv pip install --python .venv/bin/python -r requirements.txt   # nếu requirements.txt có thay đổi
# Windows: uv pip install --python .venv\Scripts\python.exe -r requirements.txt
```

Giao diện đang chạy thì phải tắt (`Ctrl + C`) rồi bật lại `./giao-dien` để nạp code mới.

### Lưu thay đổi của bạn lên GitHub

```sh
git add -A
git commit -m "Mô tả thay đổi"
git push
```

### Cập nhật thư viện edge-tts / moviepy từ repo gốc

Hai thư viện đi theo chuỗi: **repo gốc** (`upstream`) → **fork của bạn** (`origin`) → **repo này**
(ghi nhận commit đang dùng). Ví dụ edge-tts ra bản `7.3.2`:

```sh
cd edge-tts
git fetch upstream --tags
git merge 7.3.2                 # hoặc: git merge upstream/master
git push origin master          # cập nhật fork trên GitHub

cd ..
git add edge-tts
git commit -m "Cập nhật edge-tts lên 7.3.2"
git push
```

moviepy làm giống hệt, đổi `edge-tts` thành `moviepy` và dùng tag của moviepy.

- Merge báo xung đột ở `src/edge_tts/constants.py` thì giữ dòng
  `DEFAULT_VOICE = "vi-VN-HoaiMyNeural"`, các dòng còn lại lấy theo bản mới.
- Sau khi cập nhật, chạy thử `./tao-video du-an/<tên> --chi-giong` cho chắc.
- Không cần cài lại: thư viện được cài kiểu `-e` (liên kết thẳng tới thư mục), code mới có tác
  dụng ngay. Chỉ cần cài lại khi bản mới thêm thư viện phụ (`setup.py` thay đổi).
- Nếu clone fork mới hoặc remote `upstream` chưa có, thêm bằng lệnh:
  `git -C edge-tts remote add upstream https://github.com/rany2/edge-tts.git`
  (moviepy: `https://github.com/Zulko/moviepy.git`).

### Sửa code thư viện (trong submodule)

```sh
cd moviepy                      # hoặc edge-tts
git checkout master             # submodule thường ở trạng thái "detached HEAD", chuyển về nhánh trước khi sửa
# ... sửa code ...
git commit -am "Mô tả" && git push origin master
cd .. && git add moviepy && git commit -m "Dùng bản moviepy mới" && git push
```

---

## Xử lý sự cố

| Hiện tượng | Cách xử lý |
|---|---|
| `RuntimeError: Không đọc được câu: …`, kèm lỗi 403 từ `speech.platform.bing.com` | Microsoft đổi cách xác thực, bản edge-tts đã cũ: cập nhật edge-tts theo mục trên. Nếu không phải lỗi 403 thì kiểm tra mạng. |
| "Chưa dựng được video vì thiếu ảnh" | Thêm ảnh cho các cảnh được liệt kê; tên file cần có số cảnh. |
| "Không biết ảnh … thuộc cảnh nào" | Đổi tên file cho có số cảnh, hoặc chọn cảnh cho ảnh trên giao diện. |
| "cần đúng 1 file kịch bản .docx" | Trong `assets/kich-ban/` chỉ để một file `.docx`. |
| Giao diện báo cổng đang bận | Chương trình tự chuyển sang cổng kế tiếp; xem địa chỉ in ra trong Terminal. |
| Sửa code nhưng giao diện không đổi | Tắt giao diện (`Ctrl + C`), bật lại `./giao-dien` rồi tải lại trang. |
| Thư mục `edge-tts/` hoặc `moviepy/` trống | `git submodule update --init --recursive` |
| Windows: gõ `uv` hoặc `git` báo "is not recognized" | Đóng PowerShell, mở lại sau khi cài. Vẫn lỗi thì cài lại uv/Git. |
| Windows: chạy `.\giao-dien` không được | Gõ đủ đuôi `.cmd`: `.\giao-dien.cmd`, và chạy ngay trong thư mục `video-ai`. |
