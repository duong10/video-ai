"""Hiệu ứng do AI tạo ảnh mô tả (hieu_ung.json) -> vị trí chính xác của từng khối trên ảnh.

AI tạo ảnh trả về, cho mỗi ảnh: các khối sẽ hiện ra (chữ trong khối, vùng ước lượng,
câu đọc làm mốc, kiểu hiệu ứng). Thứ tự, thời điểm và kiểu hiệu ứng lấy đúng theo đó.
Riêng tọa độ AI chỉ ước lượng được, nên được căn lại trên ảnh thật:
  - khối có chữ: tìm dòng chữ đó bằng OCR, rồi nới ra tới viền thẻ chứa nó;
  - khối không chữ (biểu tượng): lấy hình nổi bật nằm trong vùng ước lượng.
Không căn được thì dùng nguyên vùng AI ước lượng.

Có thêm make_prompt(): điền kịch bản vào mau_prompt_tao_anh.md để dán vào AI tạo ảnh.
"""

import json
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple

import numpy as np

import do_khoi
from do_khoi import Box, TextLine, union
from kich_ban import Script

EFFECTS = ("truot", "bat", "mo_dan", "nhip")
TEMPLATE = Path(__file__).resolve().parent / "mau_prompt_tao_anh.md"


class Element(NamedTuple):
    text: str  # chữ in trên khối ("" nếu là biểu tượng)
    desc: str
    region: Optional[Tuple[float, float, float, float]]  # [trái, trên, phải, dưới], 0-1
    trigger: str  # câu đọc làm mốc xuất hiện
    effect: str  # truot | bat | mo_dan | nhip


class SceneEffects(NamedTuple):
    number: int
    elements: List[Element]
    zoom_center: Optional[Tuple[float, float]]


class Placed(NamedTuple):
    box: Box
    element: Element
    how: str  # "chu" (căn theo chữ) | "vien" (căn theo viền hình) | "uoc_luong"


# ---- Đọc hieu_ung.json ----


def _json_objects(raw: str) -> List[dict]:
    """Mọi đối tượng JSON trong văn bản (chấp nhận dán nguyên câu trả lời của AI)."""
    try:
        data = json.loads(raw)
        return [data] if isinstance(data, dict) else [d for d in data if isinstance(d, dict)]
    except json.JSONDecodeError:
        pass
    decoder, out, i = json.JSONDecoder(), [], 0
    while (i := raw.find("{", i)) != -1:
        try:
            obj, end = decoder.raw_decode(raw, i)
        except json.JSONDecodeError:
            i += 1
            continue
        out.append(obj)
        i = end
    return out


def load(path: Path) -> Dict[int, SceneEffects]:
    scenes: Dict[int, SceneEffects] = {}
    for obj in _json_objects(path.read_text(encoding="utf-8")):
        for sc in obj.get("canh", [obj]):  # file tổng {"canh": [...]} hoặc từng cảnh
            if not isinstance(sc, dict) or "so" not in sc:
                continue
            elements = []
            for k in sc.get("khoi", []):
                effect = str(k.get("hieu_ung", "truot")).strip().lower()
                if effect not in EFFECTS:
                    print(f"  ! hieu_ung.json cảnh {sc['so']}: kiểu '{effect}' không có, dùng 'truot'")
                    effect = "truot"
                region = k.get("vung")
                if not (isinstance(region, list) and len(region) == 4 and region[0] < region[2] and region[1] < region[3]):
                    region = None
                elements.append(
                    Element(
                        unicodedata.normalize("NFC", str(k.get("chu", "")).strip()),
                        str(k.get("mo_ta", "")),
                        tuple(float(v) for v in region) if region else None,
                        unicodedata.normalize("NFC", str(k.get("hien_khi", "")).strip()),
                        effect,
                    )
                )
            center = sc.get("tam_zoom")
            center = tuple(float(v) for v in center) if isinstance(center, list) and len(center) == 2 else None
            # cùng một cảnh xuất hiện nhiều lần (từng ảnh rồi bản tổng): bản sau ghi đè
            scenes[int(sc["so"])] = SceneEffects(int(sc["so"]), elements, center)
    return scenes


# ---- Căn vị trí trên ảnh ----


def plain_words(text: str) -> List[str]:
    """Chữ thường, bỏ dấu (AI có thể vẽ sai dấu tiếng Việt), tách từ."""
    text = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+", text)


def _text_box(element: Element, lines: List[TextLine], region: Optional[Box]) -> Optional[Box]:
    """Vùng chữ của khối: các dòng OCR khớp với chữ của khối, gần vùng ước lượng nhất."""
    target = set(plain_words(element.text))
    matches = []
    for line in lines:
        words = plain_words(line.text)
        common = len(target & set(words))
        if words and common and common / len(words) >= 0.6:
            matches.append(line)
    if not matches:
        return None

    def dist(line: TextLine) -> float:
        if not region:
            return 0
        cx, cy = (line.box[0] + line.box[2]) / 2, (line.box[1] + line.box[3]) / 2
        rx, ry = (region[0] + region[2]) / 2, (region[1] + region[3]) / 2
        return abs(cx - rx) + abs(cy - ry)

    best = min(matches, key=dist)
    group = [best]
    # chữ dài xuống dòng: gom các dòng khớp ngay trên/dưới, cùng cột
    for line in sorted(matches, key=lambda t: abs(t.box[1] - best.box[1])):
        if line in group:
            continue
        g = union([t.box for t in group])
        line_h = best.box[3] - best.box[1]
        near = line.box[1] - g[3] < line_h * 1.2 and g[1] - line.box[3] < line_h * 1.2
        overlap_x = min(g[2], line.box[2]) - max(g[0], line.box[0]) > 0
        if near and overlap_x:
            group.append(line)
    return union([t.box for t in group])


def _area(b: Box) -> int:
    return max(b[2] - b[0], 0) * max(b[3] - b[1], 0)


def _overlap(a: Box, b: Box) -> int:
    return _area((max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])))


def _grow(b: Box, dx: int, dy: int, w: int, h: int) -> Box:
    return max(b[0] - dx, 0), max(b[1] - dy, 0), min(b[2] + dx, w), min(b[3] + dy, h)


def _local_parts(img: np.ndarray, area: Box) -> List[Box]:
    """Các hình trong một vùng nhỏ, so với màu nền ngay quanh vùng đó.

    Nền cục bộ lấy từ viền của vùng, nên dùng được cả khi khối nằm trên tấm nền khác
    màu trang (dòng trên tờ hợp đồng trắng, ô trong khung điện thoại...).
    """
    x0, y0, x1, y1 = area
    region = img[y0:y1, x0:x1].astype(np.int16)
    if region.shape[0] < 12 or region.shape[1] < 12:
        return []
    ring = np.concatenate(
        [region[:4].reshape(-1, 3), region[-4:].reshape(-1, 3), region[:, :4].reshape(-1, 3), region[:, -4:].reshape(-1, 3)]
    )
    bg = np.median(ring, axis=0)
    mask = np.abs(region - bg).max(axis=2) > 10
    mask[:3], mask[-3:], mask[:, :3], mask[:, -3:] = False, False, False, False
    parts = do_khoi.components(mask, close=(11, 7), min_h=8, min_area=150)
    return [(a + x0, b + y0, c + x0, d + y0) for a, b, c, d in parts]


def place(img: np.ndarray, elements: List[Element]) -> List[Placed]:
    h, w = img.shape[:2]
    lines = do_khoi.read_text(img)

    regions: List[Optional[Box]] = []
    for el in elements:
        if el.region:
            x0, y0, x1, y1 = el.region
            regions.append((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)))
        else:
            regions.append(None)
    texts = [_text_box(el, lines, r) if el.text and lines else None for el, r in zip(elements, regions)]

    placed = []
    for i, (el, region, text) in enumerate(zip(elements, regions, texts)):
        others = [t for j, t in enumerate(texts) if j != i and t]

        def free(part: Box) -> bool:  # không lấn sang chữ của khối khác
            return not any(_overlap(part, t) > 0.3 * _area(t) for t in others)

        box, how = None, "uoc_luong"
        if text:
            # thẻ/dòng chứa chữ: các hình cùng hàng với chữ, trong vùng quanh khối
            around = _grow(region, int(w * 0.03), int(h * 0.012), w, h) if region else _grow(text, 90, 30, w, h)
            around = (min(around[0], text[0] - 20), min(around[1], text[1] - 20), max(around[2], text[2] + 20), max(around[3], text[3] + 20))
            row = []
            for part in _local_parts(img, around):
                holds_text = do_khoi.contains(part, text)
                # hình bị mép vùng cắt ngang là của khối bên cạnh
                cut = part[0] <= around[0] + 4 or part[2] >= around[2] - 4 or part[1] <= around[1] + 4 or part[3] >= around[3] - 4
                same_row = min(part[3], text[3]) - max(part[1], text[1]) > 0.5 * min(part[3] - part[1], text[3] - text[1])
                if (holds_text or (same_row and not cut)) and free(part):
                    row.append(part)
            box = union([text] + row) if row else (text[0] - 14, text[1] - 10, text[2] + 14, text[3] + 10)
            how = "chu"
        elif region:
            # khối không chữ (biểu tượng): hình lớn nhất nằm trong vùng ước lượng
            pad_x, pad_y = max((region[2] - region[0]) // 4, 40), max((region[3] - region[1]) // 4, 40)
            around = _grow(region, pad_x, pad_y, w, h)
            near = [p for p in _local_parts(img, around) if free(p) and _area(p) < _area(around) * 0.9]
            near = [p for p in near if _overlap(p, region) > 0.3 * _area(p)]
            if near:
                box, how = max(near, key=lambda p: _overlap(p, region)), "vien"
            else:
                box = region
        if box is None:
            print(f"  ! Không tìm thấy khối '{el.text or el.desc}' trên ảnh (không có chữ khớp, không có 'vung'): bỏ qua")
            continue
        x0, y0, x1, y1 = box
        placed.append(Placed((max(x0, 0), max(y0, 4), min(x1, w), min(y1, h - 4)), el, how))
    return _separate(placed)


def _separate(placed: List[Placed]) -> List[Placed]:
    """Cắt phần chồng lấn giữa hai khung (thường do bóng đổ) tại điểm giữa.

    Khung chồng nhau thì khối hiện sau sẽ kéo theo mép của khối đã hiện trước.
    """
    boxes = [list(p.box) for p in placed]
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            ox = min(a[2], b[2]) - max(a[0], b[0])
            oy = min(a[3], b[3]) - max(a[1], b[1])
            if ox <= 0 or oy <= 0:
                continue
            if oy <= ox:  # chồng theo chiều dọc: khối trên / khối dưới
                top, bottom = (a, b) if a[1] <= b[1] else (b, a)
                mid = (max(a[1], b[1]) + min(a[3], b[3])) // 2
                top[3], bottom[1] = mid, mid
            else:  # chồng theo chiều ngang: khối trái / khối phải
                left, right = (a, b) if a[0] <= b[0] else (b, a)
                mid = (max(a[0], b[0]) + min(a[2], b[2])) // 2
                left[2], right[0] = mid, mid
    return [p._replace(box=tuple(b)) for p, b in zip(placed, boxes)]


# ---- Prompt cho AI tạo ảnh ----


def make_prompt(script: Script) -> str:
    def slug(text: str) -> str:
        return "_".join(plain_words(text))[:40]

    parts = [
        "## Cover image (scene 0)\n"
        f'- Save as: "00_anh_bia.png"\n'
        f'- Big title text on the image: "{script.cover_text or script.title}"\n'
        "- Static image, return \"khoi\": []"
    ]
    for sc in script.scenes:
        lines = [f"## Scene {sc.number} · {sc.title}"]
        if sc.frame_count > 1:
            names = ", ".join(f'"{sc.number:02d}{chr(97 + k)}_{slug(sc.title)}.png"' for k in range(sc.frame_count))
            lines.append(f"- {sc.frame_count} ảnh (fast cuts, one image per frame). Save as: {names}")
            for k, note in enumerate(sc.frame_notes):
                lines.append(f"  - Frame {k + 1}: {note}")
        else:
            lines.append(f'- Save as: "{sc.number:02d}_{slug(sc.title)}.png"')
        lines.append(f"- Picture (Vietnamese brief): {sc.image_note}")
        if sc.screen_lines:
            lines.append("- On-screen text (Vietnamese, write exactly):")
            lines += [f"  - {t}" for t in sc.screen_lines]
        lines.append(f'- Voice-over (Vietnamese, copy "hien_khi" from here): "{sc.narration}"')
        parts.append("\n".join(lines))
    template = TEMPLATE.read_text(encoding="utf-8")
    return template.replace("{{TIEU_DE}}", script.title).replace("{{CANH}}", "\n\n".join(parts))
