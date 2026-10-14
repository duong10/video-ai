"""Dựng video dọc 9:16 từ kịch bản Word, ảnh từng cảnh và giọng đọc đã tạo.

Mọi thứ tự suy ra từ kịch bản, không cần viết code riêng cho từng video:
  - Ảnh nền zoom chậm. Cảnh nhiều khung ("Cắt nhanh 4 khung") được cắt ngay trước
    câu đọc tương ứng, kiểu TikTok.
  - Cột "Chữ trên màn hình":
      “câu trong ngoặc kép”/dòng chữ thường đầu tiên -> tiêu đề trên cùng
      dòng bắt đầu bằng biểu tượng (✅ 🚗 ❌ ...)     -> thẻ trắng có biểu tượng
      các dòng chữ thường sau đó                       -> thẻ trắng
      "A · B · C → D"                                  -> các nhãn bật ra lần lượt
      "A → B → C"                                      -> các bước đánh số
      "Khung cuối: chữ đỏ “X”"                         -> con dấu đỏ X ở khung cuối
      "Từng ... hiện theo khung hình"                  -> mỗi khung một dòng chữ,
                                                          lấy từ các ý ① ② ở cột Hình ảnh
    Thẻ/nhãn hiện đúng lúc giọng đọc nhắc tới (so khớp từ với lời đọc).
  - Ảnh thiết kế đã có sẵn chữ (nền trơn, nhận ra tự động): không vẽ thêm chữ mà tự
    dò các khối trong ảnh (thẻ, dòng, bước, biểu tượng - xem do_khoi.py), xóa khỏi nền
    rồi cho từng khối trượt lên/bật ra đúng lúc giọng đọc nhắc tới chữ trong khối.
  - Cảnh cuối có hotline hoặc "Dùng thử" -> bảng kêu gọi hành động, nút nhịp đập.
  - Ảnh bìa (nếu có) hiện ở câu đầu, kèm chữ to lấy từ dòng "Ảnh bìa: ... “CHỮ”".
  - Phụ đề theo từng câu, nhạc nền tự hạ nhỏ khi có lời.
"""

import json
import re
import unicodedata
from pathlib import Path
from typing import Callable, List, NamedTuple, Optional, Sequence, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from moviepy import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    VideoClip,
    afx,
    vfx,
)

import do_khoi
import hieu_ung
from kich_ban import Images, Script, ScriptScene, is_cta

W, H = 1080, 1920
FPS = 30

FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_EMOJI = "/System/Library/Fonts/Apple Color Emoji.ttc"

BLUE = (21, 94, 207)
NAVY = (15, 23, 42)
ORANGE = (255, 136, 0)
RED = (229, 57, 53)
GREEN = (34, 160, 90)
WHITE = (255, 255, 255)
GRAY = (90, 100, 115)

TOP = 150  # mép trên vùng chữ
BOTTOM = 1500  # chữ/thẻ không xuống quá đây (phía dưới dành cho phụ đề)
SUB_CENTER_Y = 1690
SUB_FONT_SIZE = 50
SUB_MAX_CHARS = 42

TRANSITION = {"fade": 0.4, "push": 0.4}

# Từ quá phổ biến, bỏ qua khi so khớp chữ trên màn hình với lời đọc.
STOP_WORDS = set(
    "và là có của cho các một những được với thì mà để đã từ đến trên trong ngay "
    "theo khi này đó nào bạn rồi cũng còn hay hoặc".split()
)


# --------------------------------------------------------------------------- #
# Mốc thời gian của giọng đọc
# --------------------------------------------------------------------------- #


class Sentence(NamedTuple):
    start: float  # lúc bắt đầu nói
    end: float  # lúc nói xong
    text: str
    scene: str  # slug cảnh


class SceneTime(NamedTuple):
    slug: str
    start: float
    end: float
    sentences: List[Sentence]


def load_timing(path: Path) -> Tuple[List[SceneTime], float]:
    data = json.loads(path.read_text(encoding="utf-8"))
    sentences = [Sentence(c["bat_dau"], c["ket_thuc"], c["chu"], c["canh"]) for c in data["cau"]]
    scenes = [
        SceneTime(c["slug"], c["bat_dau"], c["ket_thuc"], [s for s in sentences if s.scene == c["slug"]])
        for c in data["canh"]
    ]
    return scenes, data["tong"]


def words_of(text: str) -> List[Tuple[str, int]]:
    text = unicodedata.normalize("NFC", text).lower()
    return [(m.group(), m.start()) for m in re.finditer(r"\w+", text)]


class Speech:
    """Lời đọc của một cảnh, tách thành từng từ kèm thời điểm (ước lượng) được nói."""

    def __init__(self, sentences: Sequence[Sentence]):
        self.words: List[str] = []
        self.times: List[float] = []
        for s in sentences:
            for word, pos in words_of(s.text):
                self.words.append(word)
                self.times.append(s.start + (s.end - s.start) * pos / max(len(s.text), 1))

    def find(self, phrase: str, after: int = 0) -> Optional[Tuple[int, float]]:
        """Vị trí đầu tiên lời đọc nói tới ``phrase`` (khớp nhiều từ nhất)."""
        target = {w for w, _ in words_of(phrase) if w not in STOP_WORDS and not w.isdigit()}
        target = target or {w for w, _ in words_of(phrase)}
        if not target:
            return None
        best = None
        span = len(target) + 3
        for i in range(after, len(self.words)):
            if self.words[i] not in target:
                continue
            score = len(target & set(self.words[i : i + span]))
            if best is None or score > best[0]:
                best = (score, i)
        need = 1 if len(target) <= 2 else 2
        if best and best[0] >= need:
            return best[1], self.times[best[1]]
        return None

    def schedule(self, phrases: Sequence[str], t_from: float, t_to: float) -> List[float]:
        """Thời điểm nhắc tới từng ý, theo đúng thứ tự; ý nào không khớp thì chia đều."""
        found: List[Optional[float]] = []
        after = 0
        for p in phrases:
            hit = self.find(p, after)
            if hit:
                after = hit[0] + 1
            found.append(hit[1] if hit else None)
        # điền các ý không khớp: chia đều giữa hai ý đã biết gần nhất
        known = [(-1, t_from)] + [(i, t) for i, t in enumerate(found) if t is not None]
        known.append((len(found), t_to))
        out = list(found)
        for (i0, t0), (i1, t1) in zip(known, known[1:]):
            for k in range(i0 + 1, i1):
                out[k] = t0 + (t1 - t0) * (k - i0) / (i1 - i0)
        return [float(t) for t in out]  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Ảnh và chữ
# --------------------------------------------------------------------------- #


def load(path: Path) -> np.ndarray:
    """Đọc ảnh, phóng/cắt cho phủ kín khung 1080x1920 (giữ phần giữa)."""
    img = np.asarray(Image.open(path).convert("RGB"))
    h, w = img.shape[:2]
    s = max(W / w, H / h)
    img = cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
    y0 = (img.shape[0] - H) // 2
    x0 = (img.shape[1] - W) // 2
    return np.ascontiguousarray(img[y0 : y0 + H, x0 : x0 + W])


def blurred(img: np.ndarray, darken=0.55) -> np.ndarray:
    return (cv2.GaussianBlur(img, (0, 0), 22) * darken).astype(np.uint8)


def top_shade(img: np.ndarray, height=760, strength=0.55) -> np.ndarray:
    """Phủ dải tối mờ dần ở phía trên để chữ trắng dễ đọc trên nền sáng."""
    height = int(min(max(height, 300), H))
    out = img.astype(float)
    k = np.linspace(strength, 0, height)[:, None, None]
    out[:height] *= 1 - k
    return out.astype(np.uint8)


def font(size, bold=True):
    return ImageFont.truetype(FONT_BOLD if bold else FONT, int(size))


def emoji(ch: str, size: int):
    """Biểu tượng emoji màu (Apple Color Emoji chỉ vẽ ở cỡ 160 rồi thu nhỏ)."""
    try:
        f = ImageFont.truetype(FONT_EMOJI, 160)
        im = Image.new("RGBA", (260, 260), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((10, 10), ch, font=f, embedded_color=True)
        box = im.getbbox()
        if not box:
            return None
        return im.crop(box).resize((size, size), Image.LANCZOS)
    except OSError:
        return None


def wrap(text: str, f, max_w: float) -> List[str]:
    lines, cur = [], ""
    for word in text.split():
        test = f"{cur} {word}".strip()
        if f.getlength(test) > max_w and cur:
            lines.append(cur)
            cur = word
        else:
            cur = test
    return lines + [cur]


def text_box(text, size, color=WHITE, bg=None, pad=(36, 22), radius=28, max_w=920, bold=True):
    """Khối chữ căn giữa, có hoặc không có nền bo góc. Trả về mảng RGBA."""
    f = font(size, bold)
    lines = wrap(text, f, max_w)
    line_h = int(size * 1.28)
    tw = int(max(f.getlength(line) for line in lines))
    w, h = tw + 2 * pad[0], line_h * len(lines) + 2 * pad[1]
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if bg is not None:
        d.rounded_rectangle((0, 0, w - 1, h - 1), radius, fill=bg)
    for i, line in enumerate(lines):
        x = (w - f.getlength(line)) / 2
        y = pad[1] + i * line_h + (line_h - size) // 2 - 3
        if bg is None:  # chữ nằm thẳng trên ảnh: thêm viền tối cho dễ đọc
            d.text((x, y), line, font=f, fill=color, stroke_width=4, stroke_fill=(0, 0, 0, 160))
        else:
            d.text((x, y), line, font=f, fill=color)
    return np.asarray(img)


def card(text, icon=None, number=None, w=900, scale=1.0, accent=BLUE):
    """Thẻ trắng: biểu tượng (hoặc số thứ tự) tròn bên trái, chữ bên phải.

    "Xe: biển số, dòng xe" -> dòng đậm "Xe" và dòng mô tả "biển số, dòng xe".
    """
    title, detail = text, None
    m = re.match(r"([^:]{1,24}):\s+(.+)", text)
    if m and not re.search(r"\d{3}", m.group(2)[:4]):
        title, detail = m.group(1), m.group(2)

    s = scale
    pad = int(24 * s)
    has_badge = bool(icon or number)
    badge = int(76 * s)
    tx = pad + (badge + int(24 * s) if has_badge else int(14 * s))
    max_w = w - tx - pad
    f_title = font(42 * s)
    f_detail = font(32 * s, bold=False)
    title_lines = wrap(title, f_title, max_w)[:2]
    detail_lines = wrap(detail, f_detail, max_w)[:2] if detail else []
    lh_title, lh_detail = int(42 * s * 1.22), int(32 * s * 1.3)
    content_h = len(title_lines) * lh_title + len(detail_lines) * lh_detail
    h = max(int(104 * s), content_h + 2 * int(22 * s))

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), int(30 * s), fill=(255, 255, 255, 245))
    cy = h // 2
    if has_badge:
        d.ellipse((pad, cy - badge // 2, pad + badge, cy + badge // 2), fill=(*accent, 38))
        icon_img = emoji(icon, int(50 * s)) if icon else None
        if icon_img:
            img.alpha_composite(icon_img, (pad + (badge - icon_img.width) // 2, cy - icon_img.height // 2))
        else:
            label = str(number) if number else icon
            f = font(40 * s)
            d.text(
                (pad + (badge - f.getlength(label)) / 2, cy - 40 * s * 0.6),
                label,
                font=f,
                fill=(*accent, 255),
            )
    y = (h - content_h) // 2
    for line in title_lines:
        d.text((tx, y + (lh_title - 42 * s) / 2 - 2), line, font=f_title, fill=NAVY)
        y += lh_title
    for line in detail_lines:
        d.text((tx, y + (lh_detail - 32 * s) / 2 - 2), line, font=f_detail, fill=GRAY)
        y += lh_detail
    return np.asarray(img)


def pill(text, size, fg=WHITE, bg=RED, pad=(30, 14)):
    return text_box(text, size, fg, bg=(*bg, 255), pad=pad, radius=200)


def stamp(text, size=120, color=RED, angle=-8):
    """Con dấu chữ đỏ có viền, nghiêng nhẹ."""
    f = font(size)
    while size > 60 and f.getlength(text) > 820:
        size -= 6
        f = font(size)
    tw = int(f.getlength(text))
    w, h = tw + 80, size + 70
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(
        (4, 4, w - 5, h - 5), 26, fill=(255, 255, 255, 230), outline=(*color, 255), width=10
    )
    d.text((40, 30), text, font=f, fill=(*color, 255))
    return np.asarray(img.rotate(angle, expand=True, resample=Image.BICUBIC))


# --------------------------------------------------------------------------- #
# Chuyển động
# --------------------------------------------------------------------------- #


def ease_out(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def ease_in_out(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return 3 * x * x - 2 * x * x * x


def slide_in(rgba, x, y, start, scene_dur, dur=0.35, dy=40):
    """Lớp RGBA trượt lên và hiện dần tại ``start`` (giây, tính trong cảnh). x="center" để căn giữa."""
    x = (W - rgba.shape[1]) // 2 if x == "center" else x
    start = min(max(start, 0.0), max(scene_dur - 0.05, 0.0))
    clip = (
        ImageClip(rgba)
        .with_start(start)
        .with_duration(max(scene_dur - start, 0.01))
        .with_effects([vfx.CrossFadeIn(dur)])
    )
    return clip.with_position(lambda t: (x, y + dy * (1 - ease_out(t / dur))))


def sprite(rgba, center, start, duration, scale_fn):
    """Lớp RGBA phóng to/thu nhỏ quanh ``center`` theo ``scale_fn(t)``."""
    rgb = np.ascontiguousarray(rgba[..., :3])
    alpha = np.ascontiguousarray(rgba[..., 3].astype(np.float32) / 255)
    h, w = alpha.shape
    cw, ch = int(w * 1.3) // 2 * 2, int(h * 1.3) // 2 * 2

    def place(src, t):
        s = max(scale_fn(t), 0.01)
        sw, sh = max(1, round(w * s)), max(1, round(h * s))
        scaled = cv2.resize(src, (sw, sh), interpolation=cv2.INTER_LINEAR)
        canvas = np.zeros((ch, cw) + src.shape[2:], src.dtype)
        x, y = (cw - sw) // 2, (ch - sh) // 2
        sx, sy = max(0, -x), max(0, -y)
        x, y = max(0, x), max(0, y)
        part = scaled[sy : sy + ch - y, sx : sx + cw - x]
        canvas[y : y + part.shape[0], x : x + part.shape[1]] = part
        return canvas

    duration = max(duration, 0.01)
    clip = VideoClip(lambda t: place(rgb, t), duration=duration)
    mask = VideoClip(lambda t: place(alpha, t), is_mask=True, duration=duration)
    cx, cy = center
    return clip.with_mask(mask).with_start(max(start, 0.0)).with_position((cx - cw // 2, cy - ch // 2))


def pop_scale(dur=0.45, peak=1.15):
    def f(t):
        x = t / dur
        if x >= 1:
            return 1.0
        if x < 0.6:
            return peak * ease_out(x / 0.6)
        return peak + (1 - peak) * ease_in_out((x - 0.6) / 0.4)

    return f


def pop_in(rgba, center, start, end):
    """Bật ra tại ``start`` và giữ tới ``end`` (giây, tính trong cảnh)."""
    start = max(start, 0.0)
    return sprite(rgba, center, start, end - start, pop_scale())


def ken_burns(z0=1.0, z1=1.06, dur=1.0):
    return lambda t: z0 + (z1 - z0) * ease_in_out(t / dur)


def punch(dur, start_zoom=1.12, settle=0.35, drift=0.04):
    """Cắt nhanh kiểu TikTok: hình bật từ hơi to về bình thường, rồi trôi rất chậm."""

    def f(t):
        if t < settle:
            return start_zoom + (1 - start_zoom) * ease_out(t / settle)
        return 1 + drift * (t - settle) / max(dur - settle, 0.01)

    return f


def zoomed(frame: np.ndarray, s: float, center) -> np.ndarray:
    if s <= 1.0005:
        return frame
    cx, cy = center
    vw, vh = W / s, H / s
    x0 = min(max(cx - vw / 2, 0), W - vw)
    y0 = min(max(cy - vh / 2, 0), H - vh)
    m = np.float32([[s, 0, -x0 * s], [0, s, -y0 * s]])
    return cv2.warpAffine(frame, m, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


class Frame(NamedTuple):
    image: np.ndarray
    start: float  # giây, tính trong cảnh
    end: float
    zoom: Callable[[float], float]


def scene_clip(frames: List[Frame], dur: float, overlays=(), center=(W // 2, H // 2), zoom_all=False):
    """Nền gồm một hoặc nhiều khung ảnh (cắt thẳng), chữ/thẻ phủ lên trên.

    Chữ tự vẽ thì không zoom theo nền. Khối cắt ra từ chính ảnh (``zoom_all``) thì
    phải zoom cùng nền, nếu không sẽ lệch khỏi chỗ trống đã xóa.
    """

    def make(t):
        for fr in frames:
            if t < fr.end or fr is frames[-1]:
                return zoomed(fr.image, 1.0 if zoom_all else fr.zoom(t - fr.start), center)

    bg = VideoClip(make, duration=dur)
    if not overlays:
        return bg if not zoom_all else bg.transform(lambda gf, t: zoomed(gf(t), frames[0].zoom(t), center))
    comp = CompositeVideoClip([bg, *overlays], size=(W, H), use_bgclip=True).with_duration(dur)
    # Bọc lại thành VideoClip thường: gắn CrossFadeIn thẳng lên CompositeVideoClip
    # làm MoviePy lỗi ('VideoClip' object has no attribute 'precomputed').
    if zoom_all:
        return VideoClip(lambda t: zoomed(comp.get_frame(t), frames[0].zoom(t), center), duration=dur)
    return VideoClip(comp.get_frame, duration=dur)


def reveal(img: np.ndarray, base: np.ndarray, box, effect: str, start: float, dur: float):
    """Lớp phủ cho một khối cắt từ ảnh gốc, hiện ra trên nền đã xóa khối.

    effect: "truot" trượt lên | "bat" bật ra | "mo_dan" hiện dần | "nhip" bật ra rồi nhịp đập.
    """
    x0, y0, x1, y1 = do_khoi.padded(box)
    crop = img[y0:y1, x0:x1]
    # chỉ những pixel khác nền đã xóa mới hiện ra, nên không lộ mép khung chữ nhật
    diff = np.abs(crop.astype(int) - base[y0:y1, x0:x1].astype(int)).max(axis=2)
    alpha = cv2.GaussianBlur(np.clip(diff / 10.0, 0, 1).astype(np.float32), (0, 0), 1.5)
    alpha = cv2.dilate(alpha, np.ones((3, 3), np.uint8))
    rgba = np.dstack([crop, (alpha * 255).astype(np.uint8)])
    center = ((x0 + x1) // 2, (y0 + y1) // 2)
    if effect == "bat":
        return [pop_in(rgba, center, start, dur)]
    if effect == "mo_dan":
        clip = ImageClip(rgba).with_start(start).with_duration(max(dur - start, 0.01))
        return [clip.with_effects([vfx.CrossFadeIn(0.6)]).with_position((x0, y0))]
    if effect == "nhip":
        settle = min(start + 0.45, dur - 0.05)
        return [
            pop_in(rgba, center, start, settle),
            sprite(rgba, center, settle, dur - settle, lambda t: 1 + 0.06 * np.sin(np.pi * t / 0.8) ** 2),
        ]
    return [slide_in(rgba, x0, y0, start, dur, dy=36)]


def timed_layers(img, boxes, effects, phrases, speech: "Speech", sentences, t0: float, dur: float):
    """Xóa các khối khỏi ảnh rồi cho hiện lại lần lượt, đúng lúc lời đọc nhắc tới ``phrases``."""
    base = do_khoi.erase(img, boxes)
    speech_end = (sentences[-1].end if sentences else t0 + dur) - 0.3
    times = speech.schedule(phrases, t0 + 0.3, max(speech_end, t0 + 0.6))
    layers, prev = [], 0.0
    for box, effect, t in zip(boxes, effects, times):
        start = min(max(t - t0 - 0.12, prev + 0.15, 0.15), dur - 0.3)
        prev = start
        layers += reveal(img, base, box, effect, start, dur)
    return base, layers


def block_layers(img: np.ndarray, speech: "Speech", sentences, t0: float, dur: float):
    """Tự dò các khối trong ảnh thiết kế, xóa khỏi nền và cho hiện lại theo lời đọc.

    Trả về (ảnh nền đã xóa khối, các lớp phủ). Không dò được khối nào thì (ảnh gốc, []).
    """
    blocks = do_khoi.find_blocks(img)
    if not blocks:
        return img, []
    return timed_layers(
        img,
        [b.box for b in blocks],
        ["bat" if b.pop else "truot" for b in blocks],
        [b.text for b in blocks],
        speech,
        sentences,
        t0,
        dur,
    )


def manifest_layers(img: np.ndarray, effects: "hieu_ung.SceneEffects", label: str, speech: "Speech", sentences, t0, dur):
    """Các khối theo hieu_ung.json: thứ tự, câu mốc, kiểu hiệu ứng do AI tạo ảnh chỉ định."""
    placed = hieu_ung.place(img, effects.elements)
    if not placed:
        return img, []
    how = [p.how for p in placed]
    print(
        f"  {label}: {len(placed)} khối theo hieu_ung.json "
        f"(căn theo chữ {how.count('chu')}, theo viền {how.count('vien')}, vùng ước lượng {how.count('uoc_luong')})"
    )
    return timed_layers(
        img,
        [p.box for p in placed],
        [p.element.effect for p in placed],
        [p.element.trigger or p.element.text for p in placed],
        speech,
        sentences,
        t0,
        dur,
    )


# --------------------------------------------------------------------------- #
# Chữ trên màn hình -> các lớp phủ
# --------------------------------------------------------------------------- #


def strip_quotes(text: str) -> Tuple[str, bool]:
    t = text.strip()
    if len(t) > 1 and t[0] in "“\"" and t[-1] in "”\"":
        return t[1:-1].strip(), True
    return t, False


def leading_icon(text: str) -> Tuple[Optional[str], str]:
    """Tách biểu tượng ở đầu dòng: "✅ Công nợ rõ ràng" -> ("✅", "Công nợ rõ ràng")."""
    i = 0
    while i < len(text) and (
        unicodedata.category(text[i]) in ("So", "Sk", "Mn", "Cf") or text[i] in "️‍"
    ):
        i += 1
    if i == 0:
        return None, text
    return text[:i], text[i:].strip()


class Item(NamedTuple):
    kind: str  # "headline" | "card" | "chips" | "steps" | "stamp"
    text: str
    icon: Optional[str] = None
    parts: Tuple[str, ...] = ()
    result: Optional[str] = None  # "A · B → Kết quả"
    quoted: bool = False
    frame: Optional[int] = None  # stamp: khung số mấy (0 = đầu, -1 = cuối)


def parse_screen(lines: List[str]) -> Tuple[List[Item], bool]:
    """Phân loại các dòng chữ trên màn hình. Trả về (các mục, có_chữ_theo_khung)."""
    items: List[Item] = []
    per_frame = False
    for raw in lines:
        low = raw.lower()
        if "theo khung hình" in low or low.startswith("từng "):
            per_frame = True
            continue
        m = re.match(r"khung\s+(cuối|đầu|\d+)\s*:", low)
        if m:
            quote = re.findall(r"“([^”]+)”", raw) or re.findall(r'"([^"]+)"', raw)
            if quote:
                where = m.group(1)
                frame = -1 if where == "cuối" else 0 if where == "đầu" else int(where) - 1
                items.append(Item("stamp", quote[-1], frame=frame))
            continue
        text, quoted = strip_quotes(raw)
        icon, rest = leading_icon(text)
        if icon:
            items.append(Item("card", rest, icon=icon))
        elif "·" in text:
            result = None
            if "→" in text:
                text, result = (p.strip() for p in text.rsplit("→", 1))
            parts = tuple(p.strip() for p in text.split("·") if p.strip())
            items.append(Item("chips", text, parts=parts, result=result))
        elif text.count("→") >= 2:
            parts = tuple(p.strip() for p in text.split("→") if p.strip())
            items.append(Item("steps", text, parts=parts))
        elif not any(i.kind == "headline" for i in items):
            items.append(Item("headline", text, quoted=quoted))
        else:
            items.append(Item("card", text))

    # Dòng chữ thường đầu tiên chỉ là tiêu đề khi nằm trong ngoặc kép, có số thứ tự
    # ("01. ..."), đứng một mình hoặc đi kèm thẻ biểu tượng/nhãn/các bước. Nếu mọi
    # dòng đều là chữ thường ngang hàng nhau thì tất cả là thẻ.
    head = next((i for i in items if i.kind == "headline"), None)
    if head and not head.quoted and not re.match(r"\d+\.", head.text):
        others = [i for i in items if i is not head and i.kind != "stamp"]
        if others and all(i.kind == "card" and not i.icon for i in others):
            items = [i._replace(kind="card") if i is head else i for i in items]
    return items, per_frame


def chip_rows(chips: List[np.ndarray], max_w=960, gap=18):
    """Xếp các nhãn thành hàng, căn giữa. Trả về [(x, y_offset)] và tổng chiều cao."""
    rows, cur, cur_w = [], [], 0
    for i, c in enumerate(chips):
        w = c.shape[1]
        if cur and cur_w + gap + w > max_w:
            rows.append(cur)
            cur, cur_w = [], 0
        cur_w += (gap if cur else 0) + w
        cur.append(i)
    if cur:
        rows.append(cur)
    pos = [None] * len(chips)
    y = 0
    for row in rows:
        total = sum(chips[i].shape[1] for i in row) + gap * (len(row) - 1)
        x = (W - total) // 2
        row_h = max(chips[i].shape[0] for i in row)
        for i in row:
            pos[i] = (x, y + (row_h - chips[i].shape[0]) // 2)
            x += chips[i].shape[1] + gap
        y += row_h + gap
    return pos, y - gap


def layout(items: List[Item], speech: Speech, t0: float, dur: float, scale: float):
    """Đặt các mục lên màn hình từ trên xuống. Trả về (lớp phủ, mép dưới nội dung)."""
    layers = []
    y = TOP
    speech_from = t0 + 0.3
    speech_to = t0 + max(dur * 0.75, 0.6)
    # Các thẻ đơn lẻ được hẹn giờ chung để giữ đúng thứ tự xuất hiện.
    singles = [i for i in items if i.kind == "card"]
    single_times = iter(speech.schedule([i.text for i in singles], speech_from, speech_to))

    for item in items:
        if item.kind == "headline":
            bg = (*NAVY, 225) if item.quoted else (*BLUE, 235)
            box = text_box(item.text, 58 * scale, WHITE, bg=bg)
            layers.append(slide_in(box, "center", y, 0.25, dur))
            y += box.shape[0] + int(30 * scale)
        elif item.kind == "card":
            c = card(item.text, icon=item.icon, scale=scale)
            t = next(single_times) - t0 - 0.15
            layers.append(slide_in(c, "center", y, t, dur))
            y += c.shape[0] + int(20 * scale)
        elif item.kind == "steps":
            times = speech.schedule(item.parts, speech_from, speech_to)
            if all(abs(b - a) < 0.2 for a, b in zip(times, times[1:])):
                times = [t0 + 0.3 + 0.45 * k for k in range(len(item.parts))]
            for k, (part, t) in enumerate(zip(item.parts, times), 1):
                c = card(part, number=k, scale=scale * 0.92)
                layers.append(slide_in(c, "center", y, t - t0 - 0.1, dur))
                y += c.shape[0] + int(16 * scale)
        elif item.kind == "chips":
            chips = [pill(p, 46 * scale, fg=NAVY, bg=WHITE, pad=(34, 18)) for p in item.parts]
            times = speech.schedule(item.parts, speech_from, speech_to)
            pos, height = chip_rows(chips)
            for c, (x, dy), t in zip(chips, pos, times):
                center = (x + c.shape[1] // 2, y + dy + c.shape[0] // 2)
                layers.append(pop_in(c, center, t - t0, dur))
            y += height + int(26 * scale)
            if item.result:
                done = pill("→ " + item.result, 50 * scale, bg=GREEN, pad=(40, 20))
                hit = speech.find(item.result)
                t = hit[1] if hit and hit[1] > times[-1] else times[-1] + 0.8
                layers.append(pop_in(done, (W // 2, y + done.shape[0] // 2), t - t0, dur))
                y += done.shape[0] + int(26 * scale)
    return layers, y


# --------------------------------------------------------------------------- #
# Các cảnh
# --------------------------------------------------------------------------- #


class Entry(NamedTuple):
    clip: VideoClip
    start: float
    end: float
    transition: str  # vào cảnh này bằng "cut" | "fade" | "push"


def frame_cuts(sc: ScriptScene, st: SceneTime, start: float, count: int, speech: Speech) -> List[float]:
    """Thời điểm đổi khung (tuyệt đối), ngay trước câu đọc tương ứng."""
    sentence_starts = [s.start for s in st.sentences]
    # Mỗi câu một khung: đổi hình đúng đầu từng câu.
    if len(sentence_starts) == count:
        return [s - 0.25 for s in sentence_starts[1:]]

    cuts = []
    after = 0
    for k in range(1, count):
        target = start + (st.end - start) * k / count
        hit = None
        if len(sc.frame_notes) == count:  # khớp ý ① ② ③ với lời đọc
            hit = speech.find(sc.frame_notes[k], after)
        if hit:
            after = hit[0] + 1
            # đổi hình ở đầu câu CHỨA từ khớp (không phải đầu câu gần nhất,
            # vì từ khớp nằm cuối câu sẽ kéo hình sang câu sau)
            t = max((s for s in sentence_starts if s <= hit[1]), default=hit[1]) - 0.25
        else:
            near = min(sentence_starts, key=lambda s: abs(s - target), default=target)
            t = near - 0.25 if abs(near - target) < 2.5 else target
        prev = cuts[-1] if cuts else start
        if t - prev < 0.8:
            t = prev + (st.end - prev) / (count - k + 1)
        cuts.append(t)
    return cuts


def cta_layers(sc: ScriptScene, speech: Speech, t0: float, dur: float):
    """Bảng kêu gọi hành động: thương hiệu, mô tả, hotline và nút bấm nhịp đập."""
    brand, lines, phone, button_text = None, [], None, None
    for raw in sc.screen_lines:
        text, _ = strip_quotes(raw)
        low = text.lower()
        m = re.search(r"(0\d{2,3}[. ]?\d{3,4}[. ]?\d{3,4})", text)
        if m and ("hotline" in low or len(text) < 30):
            phone = m.group(1)
        elif "dùng thử" in low and len(text) < 40:
            button_text = text.upper()
        elif brand is None and re.match(r"[^:]{1,20}:\s", text):
            brand, desc = text.split(":", 1)
            lines.append(desc.strip())
        else:
            lines.append(text)

    pw = 920
    blocks = []  # (văn bản, cỡ chữ, màu, đậm)
    if brand:
        blocks.append((brand.strip(), 130, BLUE, True))
    for line in lines:
        blocks.append((line, 44, NAVY, True))
    if phone:
        blocks.append(("Hotline", 40, GRAY, False))
        blocks.append((phone, 92, BLUE, True))

    rendered = []
    for text, size, color, bold in blocks:
        f = font(size, bold)
        while size > 60 and f.getlength(text) > pw - 80:
            size -= 6
            f = font(size, bold)
        for line in wrap(text, f, pw - 80):
            rendered.append((line, f, size, color))
    ph = 50 + sum(int(s * 1.3) for _, _, s, _ in rendered) + 40
    panel = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    p = ImageDraw.Draw(panel)
    p.rounded_rectangle((0, 0, pw - 1, ph - 1), 44, fill=(255, 255, 255, 248))
    y = 50
    for line, f, size, color in rendered:
        p.text(((pw - f.getlength(line)) / 2, y), line, font=f, fill=color)
        y += int(size * 1.3)

    top = 330
    layers = [slide_in(np.asarray(panel), "center", top, 0.3, dur, dy=60)]
    if button_text:
        button = text_box(button_text, 58, WHITE, bg=(*ORANGE, 255), pad=(60, 30), radius=200)
        cy = top + ph + 60 + button.shape[0] // 2
        hit = speech.find(button_text)
        go = min(max(hit[1] - t0 if hit else dur * 0.5, 0.8), dur - 0.5)
        layers.append(pop_in(button, (W // 2, cy), 0.6, go))
        layers.append(
            sprite(button, (W // 2, cy), go, dur - go, lambda t: 1 + 0.06 * np.sin(np.pi * t / 0.8) ** 2)
        )
    return layers


def build_entries(
    script: Script,
    images: Images,
    scenes: List[SceneTime],
    overlays_on: Optional[bool],
    blocks_on: bool = True,
    effects: Optional[dict] = None,
) -> List[Entry]:
    """``overlays_on``: True/False ép bật/tắt chữ tự vẽ; None = tự động (ảnh thiết kế
    đã có chữ thì không vẽ thêm). ``blocks_on``: tự dò khối trong ảnh thiết kế để làm hiệu ứng.
    ``effects``: {số cảnh: SceneEffects} đọc từ hieu_ung.json; cảnh có mô tả thì theo đúng mô tả."""
    effects = effects or {}
    entries: List[Entry] = []
    for idx, (sc, st) in enumerate(zip(script.scenes, scenes)):
        speech = Speech(st.sentences)
        paths = images.scenes.get(sc.number, [])
        start, end = st.start, st.end
        last = idx == len(script.scenes) - 1
        transition = "cut" if idx == 0 else "fade" if last else "push"

        # Ảnh bìa: hiện trong câu đầu tiên của video.
        if idx == 0 and images.cover:
            if len(st.sentences) >= 2 and st.sentences[1].start - start > 1.2:
                cut = st.sentences[1].start - 0.2
            else:
                cut = start + min(1.8, (end - start) * 0.4)
            cover = load(images.cover)
            layers = []
            cover_text_on = overlays_on if overlays_on is not None else not do_khoi.is_graphic(cover)
            if cover_text_on and script.cover_text:
                big = text_box(script.cover_text.upper(), 96, WHITE, max_w=900)
                cover = top_shade(cover, 900, 0.65)
                layers.append(pop_in(big, (W // 2, 330), 0.05, cut - start))
            d = cut - start
            entries.append(
                Entry(scene_clip([Frame(cover, 0, d, ken_burns(dur=d))], d, layers, (540, 700)), start, cut, "cut")
            )
            start, transition = cut, "cut"

        dur = end - start

        # Các khung ảnh của cảnh (cảnh kêu gọi cuối không có ảnh: lấy ảnh cảnh trước làm mờ)
        if paths:
            imgs = [load(p) for p in paths]
        else:
            imgs = [blurred(load(images.scenes[script.scenes[idx - 1].number][-1]), darken=1.0)]
        graphic = bool(paths) and do_khoi.is_graphic(imgs[0])
        text_on = overlays_on if overlays_on is not None else not graphic
        items, per_frame = parse_screen(sc.screen_lines) if text_on else ([], False)
        cta = text_on and last and is_cta(sc)

        # hieu_ung.json có mô tả cảnh này: các khối hiện ra theo đúng mô tả của AI tạo ảnh.
        fx = effects.get(sc.number)
        if fx and fx.elements and paths and len(imgs) == 1:
            label = f"Cảnh {sc.number}"
            base, layers = manifest_layers(imgs[0], fx, label, speech, st.sentences, start, dur)
            center = (int(fx.zoom_center[0] * W), int(fx.zoom_center[1] * H)) if fx.zoom_center else (W // 2, H // 2)
            frames = [Frame(base, 0, dur, ken_burns(1.0, 1.03 if layers else 1.06, dur))]
            entries.append(Entry(scene_clip(frames, dur, layers, center, zoom_all=True), start, end, transition))
            continue

        # Ảnh thiết kế, một khung: các khối trong ảnh lần lượt hiện ra theo lời đọc.
        if graphic and blocks_on and len(imgs) == 1 and not text_on:
            base, layers = block_layers(imgs[0], speech, st.sentences, start, dur)
            frames = [Frame(base, 0, dur, ken_burns(1.0, 1.03 if layers else 1.06, dur))]
            entries.append(Entry(scene_clip(frames, dur, layers, zoom_all=True), start, end, transition))
            continue
        if len(imgs) > 1:
            cuts = [start] + frame_cuts(sc, st, start, len(imgs), speech) + [end]
            frames = [
                Frame(img, a - start, b - start, punch(b - a))
                for img, a, b in zip(imgs, cuts, cuts[1:])
            ]
        else:
            cuts = [start, end]
            zoom_to = 1.04 if cta else 1.06 if items else 1.1
            frames = [Frame(imgs[0], 0, dur, ken_burns(1.0, zoom_to, dur))]

        layers = []
        bottom = 0
        if cta:
            frames = [fr._replace(image=(fr.image * 0.6).astype(np.uint8)) for fr in frames]
            layers = cta_layers(sc, speech, start, dur)
        elif items or per_frame:
            for scale in (1.0, 0.9, 0.8, 0.7):
                layers, bottom = layout(
                    [i for i in items if i.kind != "stamp"], speech, start, dur, scale
                )
                if bottom <= BOTTOM:
                    break
            # Chữ riêng cho từng khung: "NỖI ĐAU 1/4" + ý ① ② ở cột Hình ảnh
            if per_frame and len(frames) > 1:
                y = bottom if bottom > TOP else TOP
                for k, fr in enumerate(frames):
                    tag = pill(f"{sc.title.upper()} {k + 1}/{len(frames)}", 34)
                    layers.append(pop_in(tag, (W // 2, y + tag.shape[0] // 2), fr.start + 0.05, fr.end))
                    if k < len(sc.frame_notes):
                        note = text_box(sc.frame_notes[k], 52, WHITE, bg=(*NAVY, 225))
                        layers.append(
                            slide_in(note, "center", y + tag.shape[0] + 24, fr.start + 0.15, fr.end)
                        )
                        bottom = max(bottom, y + tag.shape[0] + 24 + note.shape[0])
            # Con dấu đỏ ở khung chỉ định
            for item in (i for i in items if i.kind == "stamp"):
                fr = frames[item.frame if -len(frames) <= item.frame < len(frames) else -1]
                hit = speech.find(item.text)
                t = hit[1] - start if hit and fr.start <= hit[1] - start < fr.end else fr.start + (fr.end - fr.start) * 0.4
                layers.append(pop_in(stamp(item.text), (W // 2, max(bottom + 200, 820)), t, fr.end))
            if bottom:
                frames = [fr._replace(image=top_shade(fr.image, bottom + 160)) for fr in frames]

        center = (560, 1250) if layers else (W // 2, H // 2)
        entries.append(Entry(scene_clip(frames, dur, layers, center), start, end, transition))
    return entries


# --------------------------------------------------------------------------- #
# Phụ đề và âm thanh
# --------------------------------------------------------------------------- #


class Cue(NamedTuple):
    start: float
    end: float
    text: str


def split_caption(cue: Cue) -> List[Cue]:
    """Tách câu dài thành các khung ngắn (tại dấu phẩy/hai chấm), chia thời gian theo độ dài."""
    parts = re.split(r"(?<=[,:])\s+", cue.text)
    chunks, cur = [], ""
    for p in parts:
        if cur and len(cur) + 1 + len(p) > SUB_MAX_CHARS:
            chunks.append(cur)
            cur = p
        else:
            cur = f"{cur} {p}".strip()
    chunks.append(cur)
    total = sum(len(c) for c in chunks)
    out, t = [], cue.start
    for c in chunks:
        dt = (cue.end - cue.start) * len(c) / total
        out.append(Cue(t, t + dt, c))
        t += dt
    return out


def build_subtitles(scenes: List[SceneTime]):
    clips = []
    for st in scenes:
        for i, s in enumerate(st.sentences):
            # giữ phụ đề qua khoảng nghỉ ngắn tới câu sau; câu cuối cảnh tắt khi chuyển cảnh
            nxt = st.sentences[i + 1].start if i + 1 < len(st.sentences) else st.end
            end = nxt if nxt - s.end < 1.2 else s.end + 0.3
            for part in split_caption(Cue(s.start, min(end, st.end), s.text)):
                arr = text_box(part.text, SUB_FONT_SIZE, WHITE, bg=(*NAVY, 215), pad=(34, 20), radius=26, max_w=900)
                clips.append(
                    ImageClip(arr)
                    .with_start(part.start)
                    .with_duration(part.end - part.start)
                    .with_position(("center", SUB_CENTER_Y - arr.shape[0] // 2))
                )
    return clips


def ducking_envelope(scenes: List[SceneTime], total: float, low, boost=2.2, ramp=0.3):
    """Âm lượng nhạc theo thời gian: ``low`` khi có lời, ``low * boost`` khi nghỉ chuyển cảnh."""
    spans = []
    for s in (s for st in scenes for s in st.sentences):
        if spans and s.start - spans[-1][1] < 0.6:
            spans[-1][1] = s.end
        else:
            spans.append([s.start, s.end])
    rate = 100
    t = np.arange(0, total + 1, 1 / rate)
    env = np.full_like(t, low * boost)
    for start, end in spans:
        env[(t >= start - ramp / 2) & (t <= end)] = low
    n = int(ramp * rate)
    env = np.convolve(np.pad(env, n, mode="edge"), np.ones(n) / n, "same")[n:-n]
    return lambda tt: np.interp(np.atleast_1d(tt), t, env)


def _extend(clip, dur):
    """Giữ khung hình cuối của cảnh trong khoảng chồng lên cảnh sau."""
    last = clip.duration - 1e-3
    return clip.time_transform(lambda t: min(t, last), keep_duration=False).with_duration(dur)


def assemble(
    script: Script,
    images: Images,
    voice_dir: Path,
    music: Optional[Path] = None,
    music_volume: float = 0.07,
    overlays_on: Optional[bool] = None,
    subtitles_on: bool = True,
    blocks_on: bool = True,
    effects: Optional[dict] = None,
):
    scenes, total = load_timing(voice_dir / "thoi_gian.json")
    if len(scenes) != len(script.scenes):
        raise SystemExit(
            f"Giọng đọc có {len(scenes)} cảnh nhưng kịch bản có {len(script.scenes)} cảnh: "
            "tạo lại giọng đọc (bỏ --bo-qua-giong)"
        )
    entries = build_entries(script, images, scenes, overlays_on, blocks_on, effects)

    layers = []
    for i, e in enumerate(entries):
        # kéo dài cảnh trước để cảnh sau phủ lên trong lúc chuyển cảnh
        nxt = entries[i + 1].transition if i + 1 < len(entries) else "cut"
        overlap = TRANSITION.get(nxt, 0)
        dur = e.end - e.start + overlap
        clip = e.clip.with_duration(dur) if overlap == 0 else _extend(e.clip, dur)
        if e.transition == "fade":
            clip = clip.with_effects([vfx.CrossFadeIn(TRANSITION["fade"])])
        elif e.transition == "push":
            d = TRANSITION["push"]
            clip = clip.with_position(lambda t, d=d: (int(W * (1 - ease_out(t / d))), 0))
        layers.append(clip.with_start(e.start))

    if subtitles_on:
        layers += build_subtitles(scenes)
    video = CompositeVideoClip(layers, size=(W, H)).with_duration(total)

    voice = AudioFileClip(str(voice_dir / f"{voice_dir.name}.mp3"))
    audio = voice
    if music:
        gain = ducking_envelope(scenes, total, music_volume)
        bgm = (
            AudioFileClip(str(music))
            .with_effects([afx.AudioLoop(duration=total)])
            .with_duration(total)
            .transform(lambda get_frame, t: get_frame(t) * gain(t)[:, None])
            .with_effects([afx.AudioFadeIn(1.0), afx.AudioFadeOut(2.5)])
        )
        audio = CompositeAudioClip([bgm, voice])
    return video.with_audio(audio.with_duration(total))


def write(video, out: Path) -> None:
    """Ghi ra file tạm rồi mới đổi tên: dừng giữa chừng thì video cũ vẫn còn nguyên."""
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + ".dang-dung.mp4")
    video.write_videofile(
        str(tmp),
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        audio_bitrate="192k",
        preset="medium",
        threads=8,
        pixel_format="yuv420p",
        ffmpeg_params=["-crf", "20", "-movflags", "+faststart"],
    )
    tmp.replace(out)
