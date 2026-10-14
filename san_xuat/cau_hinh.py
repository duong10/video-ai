"""File cấu hình dự án: assets/cau-hinh/cau_hinh.toml.

File được sinh tự động, liệt kê ĐỦ mọi cấu hình. Giá trị false = chưa tùy chỉnh, chương trình
dùng mặc định (ghi trong chú thích từng dòng). Người dùng chỉ việc thay false bằng giá trị mới.

- Tạo dự án mới: sinh phần cấu hình chung.
- Khi đã có kịch bản: bổ sung mục cho từng cảnh (video_90s, quang_cao_30s), giữ nguyên các
  giá trị người dùng đã sửa.
- Dự án cũ có tinh_chinh.toml: chuyển giá trị sang cau_hinh.toml, file cũ đổi tên thành
  tinh_chinh.toml.cu.
"""

import tomllib
from pathlib import Path
from typing import Dict, List, Optional, Tuple

FILE_NAME = "cau_hinh.toml"
PARTS = {"video_90s": "video chính", "quang_cao_30s": "bản rút gọn quảng cáo"}
SCENE_KEYS = [
    ("toc_do", 'tốc độ đọc riêng cảnh này, ví dụ "+15%". Mặc định: tốc độ chung'),
    ("nghi_truoc", "giây nghỉ trước cảnh, ví dụ 0.6. Mặc định: 0.3 với cảnh đầu, 0.8 với cảnh khác"),
    ("nghi_giua_cau", "giây nghỉ giữa các câu trong cảnh, ví dụ 0.3. Mặc định: 0.35"),
]

# (mục, khóa, chú thích) - chú thích nêu mặc định và ví dụ giá trị
GENERAL = [
    ("giong_doc", "giong", 'giọng đọc. Mặc định: theo dòng "Thời lượng" trong kịch bản, không có thì "vi-VN-NamMinhNeural". Giọng nữ: "vi-VN-HoaiMyNeural"'),
    ("giong_doc", "toc_do", 'tốc độ đọc chung, ví dụ "+15%" hoặc "-5%". Mặc định: theo kịch bản, không có thì "+10%"'),
    ("video", "chu_tren_man_hinh", 'vẽ chữ theo cột "Chữ trên màn hình". Mặc định: tự động (ảnh chụp thì vẽ, ảnh thiết kế đã có chữ thì không). "bat" = luôn vẽ, "tat" = không vẽ'),
    ("video", "tat_hieu_ung_khoi", "true = tắt hiệu ứng tự dò khối trên ảnh thiết kế (không ảnh hưởng hieu_ung.json)"),
    ("video", "tat_phu_de", "true = không hiện phụ đề"),
    ("video", "tat_nhac_nen", "true = không dùng nhạc nền dù có file trong assets/nhac/"),
    ("video", "am_luong_nhac", "âm lượng nhạc nền khi có lời đọc, từ 0 đến 1, ví dụ 0.05. Mặc định: 0.07"),
]

HEADER = """\
# CẤU HÌNH DỰ ÁN VIDEO
# false = chưa tùy chỉnh, chương trình dùng giá trị mặc định ghi trong chú thích.
# Muốn đổi: thay false bằng giá trị mới (chữ để trong ngoặc kép), lưu file rồi chạy lại
#   ./tao-video du-an/<tên>
# Đổi phần [giong_doc], [cach_doc] hoặc từng cảnh thì giọng đọc được tạo lại, nên đừng thêm
# --bo-qua-giong. Chỉ đổi phần [video] thì thêm --bo-qua-giong cho nhanh.
"""


def load(path: Path) -> dict:
    return tomllib.loads(path.read_text("utf-8")) if path.exists() else {}


def _fmt(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def render(raw: dict, parts: Optional[Dict[str, List[Tuple[str, str]]]] = None) -> str:
    """Nội dung file: mọi khóa, giá trị người dùng đã đặt giữ nguyên, còn lại là false.

    parts: {"video_90s": [("1", "01_mo_dau"), ...], ...} lấy từ kịch bản.
    """
    lines = [HEADER]
    for section in ("giong_doc", "video"):
        if section == "video":
            lines.append("")
        lines.append(f"[{section}]")
        for sec, key, note in GENERAL:
            if sec == section:
                value = raw.get(section, {}).get(key, False)
                lines.append(f"{key} = {_fmt(value)}  # {note}")
        if section == "giong_doc":
            lines += [
                "",
                "[cach_doc]",
                '# Cách đọc riêng: chữ trên phụ đề = cách giọng đọc. Có sẵn "G-Car" = "Gi Ca" và số điện',
                "# thoại được đọc theo cụm. Thêm từng dòng dạng:",
                '# "8Car" = "Tám Ca"',
            ]
            for word, said in raw.get("cach_doc", {}).items():
                lines.append(f"{_fmt(word)} = {_fmt(said)}")

    parts = parts or {}
    for part, label in PARTS.items():
        scenes = {num: slug for num, slug in parts.get(part, [])}
        for num in raw.get(part, {}):  # giữ các mục người dùng đã có
            scenes.setdefault(str(num), "")
        if not scenes:
            continue
        lines += ["", f"# ---- Từng cảnh của {label} ({part}) ----"]
        for num in sorted(scenes, key=lambda n: int(n) if str(n).isdigit() else 0):
            values = raw.get(part, {}).get(num, {})
            title = f"  # {scenes[num]}" if scenes[num] else ""
            lines.append(f"[{part}.{num}]{title}")
            for key, note in SCENE_KEYS:
                lines.append(f"{key} = {_fmt(values.get(key, False))}  # {note}")
    if not parts:
        lines += [
            "",
            "# Các mục cho từng cảnh ([video_90s.1], [video_90s.2]...) được thêm tự động",
            "# khi đã có file kịch bản trong assets/kich-ban/.",
        ]
    return "\n".join(lines) + "\n"


def _from_legacy(old: dict) -> dict:
    """tinh_chinh.toml (bản cũ) -> giá trị theo cau_hinh.toml."""
    raw: dict = {"giong_doc": {}, "video": {}}
    for key in ("giong", "toc_do"):
        if old.get(key):
            raw["giong_doc"][key] = old[key]
    if old.get("cach_doc"):
        raw["cach_doc"] = dict(old["cach_doc"])
    for part in PARTS:
        if old.get(part):
            raw[part] = {str(k): dict(v) for k, v in old[part].items()}
    video = old.get("video", {})
    text = video.get("chu_tren_man_hinh", "tu_dong")
    if text is True:
        raw["video"]["chu_tren_man_hinh"] = "bat"
    elif text is False:
        raw["video"]["chu_tren_man_hinh"] = "tat"
    if video.get("hieu_ung_khoi") is False:
        raw["video"]["tat_hieu_ung_khoi"] = True
    if video.get("phu_de") is False:
        raw["video"]["tat_phu_de"] = True
    if "am_luong_nhac" in video:
        raw["video"]["am_luong_nhac"] = video["am_luong_nhac"]
    return raw


def ensure(path: Path, parts: Optional[Dict[str, List[Tuple[str, str]]]] = None) -> None:
    """Sinh file nếu chưa có; bổ sung mục từng cảnh nếu kịch bản có cảnh chưa liệt kê."""
    legacy = path.parent / "tinh_chinh.toml"
    if not path.exists() and legacy.exists():
        raw = _from_legacy(load(legacy))
        legacy.rename(legacy.with_name("tinh_chinh.toml.cu"))
        print(f"  Chuyển tinh_chinh.toml sang {FILE_NAME} (bản cũ đổi tên thành tinh_chinh.toml.cu)")
    elif path.exists():
        raw = load(path)
        missing = [
            (part, num) for part, scenes in (parts or {}).items() for num, _ in scenes
            if num not in raw.get(part, {})
        ]
        if not missing:
            return
    else:
        raw = {}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(raw, parts), encoding="utf-8")


def settings(path: Path) -> dict:
    """Đọc cau_hinh.toml, bỏ các giá trị false (= dùng mặc định).

    Trả về dạng các bước tạo giọng và dựng video dùng:
      {"giong", "toc_do", "cach_doc", "video_90s": {"1": {...}}, "quang_cao_30s": {...},
       "video": {"chu_tren_man_hinh": None|True|False, "hieu_ung_khoi", "phu_de",
                 "nhac_nen", "am_luong_nhac"}}
    """
    raw = load(path)
    out: dict = {}
    voice = raw.get("giong_doc", {})
    for key in ("giong", "toc_do"):
        if voice.get(key) not in (False, None, ""):
            out[key] = str(voice[key])
    out["cach_doc"] = {str(k): str(v) for k, v in raw.get("cach_doc", {}).items() if v not in (False, None, "")}
    for part in PARTS:
        scenes = {}
        for num, opts in raw.get(part, {}).items():
            chosen = {k: v for k, v in opts.items() if v is not False}
            if chosen:
                scenes[str(num)] = chosen
        out[part] = scenes

    video = raw.get("video", {})
    text = video.get("chu_tren_man_hinh", False)
    if text in (False, "tu_dong"):
        text_on = None
    elif text in (True, "bat"):
        text_on = True
    elif text == "tat":
        text_on = False
    else:
        print(f'  ! {FILE_NAME}: chu_tren_man_hinh = {_fmt(text)} không hợp lệ (dùng false, "bat" hoặc "tat"): dùng tự động')
        text_on = None
    volume = video.get("am_luong_nhac", False)
    out["video"] = {
        "chu_tren_man_hinh": text_on,
        "hieu_ung_khoi": not video.get("tat_hieu_ung_khoi", False),
        "phu_de": not video.get("tat_phu_de", False),
        "nhac_nen": not video.get("tat_nhac_nen", False),
        "am_luong_nhac": 0.07 if volume is False else float(volume),
    }
    return out
