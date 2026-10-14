"""Phần dùng chung để tạo giọng đọc cho kịch bản video bằng Edge TTS.

Từng câu được đọc riêng rồi ghép lại với khoảng nghỉ chủ động (ngắn giữa các câu,
dài hơn khi chuyển cảnh), nên timeline đi theo tốc độ đọc thực tế. Kết quả gồm MP3
tổng, MP3 từng cảnh, SRT, bảng mốc thời gian từng cảnh để đặt hình ảnh và
thoi_gian.json (mốc từng cảnh, từng câu) cho bước dựng video tự động.
"""

import asyncio
import json
import re
from datetime import timedelta
from pathlib import Path
from typing import Dict, List, NamedTuple, Tuple, Union

import aiohttp
import edge_tts
from edge_tts.srt_composer import Subtitle, compose

DEFAULT_VOICE = "vi-VN-NamMinhNeural"
DEFAULT_RATE = "+10%"

# Khoảng nghỉ (giây)
LEAD_IN = 0.3  # đầu video
SENTENCE_PAUSE = 0.35  # giữa các câu trong cùng một cảnh
QUESTION_PAUSE = 0.55  # sau câu hỏi, để người xem kịp "nghĩ"
SCENE_PAUSE = 0.8  # khi chuyển cảnh
TAIL = 0.8  # cuối video

# Edge TTS trả về MP3 24 kHz, 48 kbps CBR, mono: mỗi frame 144 byte = 24 ms.
FRAME_BYTES = 144
FRAME_SEC = 0.024
# Frame MPEG-2 Layer III rỗng (side info toàn 0) -> giải mã ra im lặng.
SILENT_FRAME = b"\xff\xf3\x64\xc0" + bytes(FRAME_BYTES - 4)
SPEECH_GAIN = 145  # global gain tối thiểu của frame có tiếng nói

# Số câu gửi lên server cùng lúc; gửi quá nhiều dễ bị từ chối kết nối.
MAX_PARALLEL = 8

# Cách đọc riêng mặc định: giọng đọc dùng bản bên phải, phụ đề vẫn hiện bản bên trái.
DEFAULT_PRONUNCIATIONS = {
    "G-Car": "Gi Ca",  # đọc kiểu tiếng Anh "G Car"
}

DIGITS = "không một hai ba bốn năm sáu bảy tám chín".split()
# Số điện thoại Việt Nam viết theo cụm, ví dụ 098.1855.854 hoặc 0981 855 854.
PHONE_RE = re.compile(r"\b0\d{2,3}(?:[. ]\d{3,4}){2}\b")


class Scene(NamedTuple):
    """Một cảnh trong kịch bản. Lời đọc được tự tách thành từng câu."""

    slug: str
    text: str
    rate: str = DEFAULT_RATE
    pause_before: float = SCENE_PAUSE
    sentence_pause: float = SENTENCE_PAUSE


class SceneTime(NamedTuple):
    scene: Scene
    start: float
    end: float


class Clip(NamedTuple):
    """Một câu đã đọc xong, đã cắt khoảng lặng thừa hai đầu."""

    audio: bytes
    cues: List[Tuple[float, float, str]]  # (bắt đầu, kết thúc, chữ) tính bằng giây


def split_sentences(text: str) -> List[str]:
    """Tách lời đọc thành từng câu; không tách ở dấu chấm trong số điện thoại."""
    return [s for s in re.split(r"(?<=[.?!])\s+", text.strip()) if s]


def spoken_phone(phone: str) -> str:
    """Đọc số điện thoại theo từng cụm cho rõ: 098.1855.854 -> "không chín tám, ..."."""
    groups = re.split(r"[. ]", phone)
    return ", ".join(" ".join(DIGITS[int(d)] for d in g) for g in groups)


def pronunciation_map(text: str, pronunciations: Dict[str, str]) -> Dict[str, str]:
    """Các cặp (chữ viết -> cách đọc) áp dụng cho câu này."""
    mapping = {phone: spoken_phone(phone) for phone in PHONE_RE.findall(text)}
    mapping.update({k: v for k, v in pronunciations.items() if k in text})
    return mapping


def frame_gain(audio: Union[bytes, bytearray], index: int) -> int:
    """Đọc global_gain của frame MP3 thứ index (MPEG-2, mono, không CRC)."""
    side = int.from_bytes(audio[index * FRAME_BYTES + 4 : index * FRAME_BYTES + 13], "big")
    # side info 72 bit: main_data_begin 8, private 1, part2_3_length 12, big_values 9, global_gain 8
    return (side >> (72 - 9 - 12 - 9 - 8)) & 0xFF


async def synthesize(
    text: str,
    voice: str,
    rate: str,
    pronunciations: Dict[str, str],
    limit: asyncio.Semaphore,
    retries: int = 6,
) -> Clip:
    """Gọi _synthesize, thử lại khi server Microsoft hoặc mạng chập chờn."""
    for attempt in range(1, retries + 1):
        try:
            async with limit:
                return await _synthesize(text, voice, rate, pronunciations)
        except (
            edge_tts.exceptions.EdgeTTSException,
            aiohttp.ClientError,
            asyncio.TimeoutError,
        ) as exc:
            if attempt == retries:
                raise RuntimeError(f"Không đọc được câu: {text!r}") from exc
            await asyncio.sleep(2 * attempt)
    raise AssertionError("unreachable")


async def _synthesize(
    text: str, voice: str, rate: str, pronunciations: Dict[str, str]
) -> Clip:
    """Đọc một câu và lấy kèm mốc thời gian."""
    mapping = pronunciation_map(text, pronunciations)
    spoken = text
    for written, said in mapping.items():
        spoken = spoken.replace(written, said)
    communicate = edge_tts.Communicate(spoken, voice, rate=rate, boundary="SentenceBoundary")
    audio = bytearray()
    cues = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio += chunk["data"]
        elif chunk["type"] == "SentenceBoundary":
            start = chunk["offset"] / 1e7
            end = (chunk["offset"] + chunk["duration"]) / 1e7
            cue_text = chunk["text"]
            for written, said in mapping.items():
                cue_text = cue_text.replace(said, written)
            cues.append((start, end, cue_text))
    if len(audio) % FRAME_BYTES:
        raise RuntimeError("Audio không phải MP3 CBR 48 kbps như mong đợi")

    # Cắt khoảng lặng thừa Edge thêm ở đầu/cuối (mốc SentenceBoundary tính cả
    # khoảng lặng cuối nên không dùng được). Frame có tiếng nói có global gain
    # khoảng 145-185, frame lặng chỉ khoảng 120-135.
    gains = [frame_gain(audio, i) for i in range(len(audio) // FRAME_BYTES)]
    loud = [i for i, g in enumerate(gains) if SPEECH_GAIN <= g < 210]
    first = max(0, loud[0] - 2) if loud else 0
    last = min(len(gains), loud[-1] + 5) if loud else len(gains)
    shift = first * FRAME_SEC
    end = (last - first) * FRAME_SEC
    cues = [(max(0.0, s - shift), min(end, e - shift), t) for s, e, t in cues]
    return Clip(bytes(audio[first * FRAME_BYTES : last * FRAME_BYTES]), cues)


def fmt(seconds: float) -> str:
    minutes, sec = divmod(seconds, 60)
    return f"{int(minutes)}:{sec:05.2f}"


async def build(
    out: Path,
    scenes: List[Scene],
    voice: str = DEFAULT_VOICE,
    pronunciations: Dict[str, str] = DEFAULT_PRONUNCIATIONS,
) -> Tuple[List[SceneTime], float]:
    """Tạo MP3 tổng, MP3 từng cảnh, SRT và bảng mốc thời gian trong thư mục out.

    Trả về mốc thời gian thực tế của từng cảnh và tổng thời lượng (giây).
    """
    name = out.name
    scene_dir = out / "tung_canh"
    scene_dir.mkdir(parents=True, exist_ok=True)
    for old in scene_dir.glob("*.mp3"):
        old.unlink()

    # Đọc song song tất cả các câu cho nhanh.
    sentences = [split_sentences(s.text) for s in scenes]
    limit = asyncio.Semaphore(MAX_PARALLEL)
    clips = await asyncio.gather(
        *(
            synthesize(text, voice, scene.rate, pronunciations, limit)
            for scene, group in zip(scenes, sentences)
            for text in group
        )
    )
    clip_iter = iter(clips)

    timeline = bytearray()
    subtitles: List[Subtitle] = []

    def silence(seconds: float) -> None:
        nonlocal timeline
        timeline += SILENT_FRAME * round(seconds / FRAME_SEC)

    def pos() -> float:
        return len(timeline) // FRAME_BYTES * FRAME_SEC

    # Mỗi cảnh bắt đầu từ khoảng nghỉ trước nó, để hình ảnh chuyển cảnh trước lời.
    scene_bounds = []
    spoken = []  # mốc thật của từng câu, cho bước dựng video
    for scene, group in zip(scenes, sentences):
        scene_start = len(timeline)
        silence(scene.pause_before)
        for i, text in enumerate(group):
            if i:
                prev = group[i - 1]
                silence(QUESTION_PAUSE if prev.endswith("?") else scene.sentence_pause)
            clip = next(clip_iter)
            offset = pos()
            timeline += clip.audio
            spoken.append(
                {
                    "canh": scene.slug,
                    "bat_dau": round(offset, 3),
                    "ket_thuc": round(pos(), 3),
                    "chu": text,
                }
            )
            for cue_start, cue_end, cue_text in clip.cues:
                subtitles.append(
                    Subtitle(
                        index=len(subtitles) + 1,
                        start=timedelta(seconds=offset + cue_start),
                        end=timedelta(seconds=offset + cue_end),
                        content=cue_text,
                    )
                )
        scene_bounds.append((scene, scene_start))
    silence(TAIL)

    times = []
    report = [f"{'Cảnh':<38}{'Bắt đầu':>9}{'Kết thúc':>10}{'Dài':>8}{'Tốc độ':>9}"]
    for i, (scene, start) in enumerate(scene_bounds):
        stop = scene_bounds[i + 1][1] if i + 1 < len(scene_bounds) else len(timeline)
        (scene_dir / f"{scene.slug}.mp3").write_bytes(timeline[start:stop])
        t0 = start // FRAME_BYTES * FRAME_SEC
        t1 = stop // FRAME_BYTES * FRAME_SEC
        times.append(SceneTime(scene, t0, t1))
        report.append(
            f"{scene.slug:<38}{fmt(t0):>9}{fmt(t1):>10}{t1 - t0:>7.2f}s{scene.rate:>9}"
        )

    # Giữ phụ đề trên màn hình qua khoảng nghỉ cho tới câu tiếp theo, tránh nhấp nháy.
    for prev, cur in zip(subtitles, subtitles[1:]):
        if cur.start - prev.end < timedelta(seconds=1.2):
            prev.end = cur.start

    total = pos()
    (out / f"{name}.mp3").write_bytes(timeline)
    (out / f"{name}.srt").write_text(compose(subtitles), encoding="utf-8")
    report.append(f"\nTổng thời lượng: {total:.2f}s - giọng {voice}")
    (out / "bang_thoi_gian.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    timing = {
        "giong": voice,
        "tong": round(total, 3),
        "canh": [
            {"slug": t.scene.slug, "bat_dau": round(t.start, 3), "ket_thuc": round(t.end, 3)}
            for t in times
        ],
        "cau": spoken,
    }
    (out / "thoi_gian.json").write_text(
        json.dumps(timing, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return times, total
