#!/usr/bin/env python3
"""Giao diện web để tạo video, thay cho việc gõ lệnh và sửa file bằng tay.

  ./giao-dien                 mở http://127.0.0.1:8765 trên trình duyệt
  ./giao-dien --cong 9000     dùng cổng khác
  ./giao-dien --khong-mo      không tự mở trình duyệt

Chỉ chạy trên máy này (127.0.0.1). Giao diện làm đúng những việc của luồng dòng lệnh:
  - Tải kịch bản, ảnh từng cảnh, nhạc nền, hieu_ung.json vào du-an/<tên>/assets/
    (ảnh thả vào ô của một cảnh được tự đặt tên có số cảnh).
  - Sửa cau_hinh.toml: giọng đọc, tốc độ, cách đọc riêng, các tùy chọn video.
  - Tạo video / chỉ tạo giọng / chụp ảnh xem thử bằng cách chạy san_xuat/tao_video.py,
    nên kết quả giống hệt chạy ./tao-video. Mỗi lúc chỉ chạy một việc.
File bị xóa trên giao diện được chuyển vào assets/thung-rac/, không mất hẳn.
"""

import argparse
import asyncio
import codecs
import contextlib
import glob
import io
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

from docx import Document
from PIL import Image

import cau_hinh
import du_an
import hieu_ung
from kich_ban import ROOT, check_images, find_images, is_cta, nfc, read_script, scene_of
from tao_video import PROJECTS, VOICE_PART, scene_list

import giong_doc

WEB = Path(__file__).resolve().parent / "web"
TAO_VIDEO = Path(__file__).resolve().parent / "tao_video.py"
VOICES = {"vi-VN-NamMinhNeural": "Nam Minh (nam)", "vi-VN-HoaiMyNeural": "Hoài My (nữ)"}
SAMPLE_TEXT = "Xin chào, đây là giọng đọc thử cho video của bạn."
# Đánh dấu giọng đọc đã cũ (đổi kịch bản, giọng, tốc độ, cách đọc): lần chạy sau phải tạo lại.
STALE = ".can_tao_lai"
NAME_RE = re.compile(r"^[\w][\w .-]{0,79}$")

print_lock = threading.Lock()


class UserError(Exception):
    """Lỗi do thao tác của người dùng, trả về kèm thông báo dễ hiểu."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# ---- Dự án ----


def project_dir(name: str) -> Path:
    name = nfc(urllib.parse.unquote(name)).strip()
    if not NAME_RE.match(name) or name in (".", ".."):
        raise UserError("Tên dự án chỉ gồm chữ, số, dấu gạch và khoảng trắng")
    return PROJECTS / name


def existing(name: str) -> du_an.DuAn:
    folder = project_dir(name)
    if not folder.is_dir():
        raise UserError(f"Không có dự án {folder.name}", 404)
    return du_an.paths(folder)


def the_docx(p: du_an.DuAn) -> Optional[Path]:
    files = [f for f in p.kich_ban.glob("*.docx") if not f.name.startswith("~$")]
    return files[0] if len(files) == 1 else None


def script_title(p: du_an.DuAn) -> Optional[str]:
    docx = the_docx(p)
    if not docx:
        return None
    try:
        return read_script(docx).title
    except (SystemExit, Exception):
        return None


def created_at(folder: Path) -> float:
    st = folder.stat()
    return getattr(st, "st_birthtime", st.st_ctime)  # macOS có ngày tạo thật, nơi khác dùng ctime


def folder_size(folder: Path) -> int:
    return sum(f.stat().st_size for f in folder.rglob("*") if f.is_file())


def list_projects() -> list:
    """Các dự án, mới tạo nằm trên cùng."""
    PROJECTS.mkdir(exist_ok=True)
    folders = [f for f in PROJECTS.iterdir() if f.is_dir() and not f.name.startswith(".")]
    out = []
    for f in sorted(folders, key=created_at, reverse=True):
        p = du_an.paths(f)
        has_docx = bool(the_docx(p)) or du_an.is_project(f)
        status = "co_video" if p.video.exists() else "chuan_bi" if has_docx else "trong"
        out.append({
            "ten": f.name,
            "tieu_de": script_title(p),
            "trang_thai": status,
            "tao_luc": created_at(f),
            "dung_luong": folder_size(f),
        })
    return out


def delete_project(name: str) -> dict:
    """Chuyển cả thư mục dự án vào Thùng rác của máy (khôi phục được), không xóa hẳn.

    Không ghi được vào Thùng rác (máy không phải macOS, hoặc bị chặn quyền) thì chuyển vào
    du-an/.thung-rac/.
    """
    p = existing(name)
    job.check_free(p.root.name)
    for trash in (Path.home() / ".Trash", PROJECTS / ".thung-rac"):
        try:
            trash.mkdir(exist_ok=True)
            dst = unique(trash / p.root.name)
            shutil.move(str(p.root), str(dst))
        except OSError:
            continue
        where = "Thùng rác" if trash.name == ".Trash" else f"du-an/.thung-rac/{dst.name}"
        return {"noi_chuyen": where}
    raise UserError("Không chuyển được dự án vào Thùng rác", 500)


def voice_defaults(docx: Path) -> dict:
    """Giọng và tốc độ mặc định lấy từ dòng "Thời lượng" của kịch bản, như tao_tu_docx."""
    header = "\n".join(par.text for par in Document(docx).paragraphs[:15])
    voice = re.search(r"\b([a-z]{2}-[A-Z]{2}-\w+Neural)\b", header)
    rate = re.search(r"tốc độ ([+-]\d+%)", header)
    return {
        "giong": voice.group(1) if voice else giong_doc.DEFAULT_VOICE,
        "toc_do": rate.group(1) if rate else giong_doc.DEFAULT_RATE,
    }


def rel(p: du_an.DuAn, path: Path) -> str:
    return path.relative_to(p.root).as_posix()


def file_info(p: du_an.DuAn, path: Path) -> dict:
    st = path.stat()
    return {"ten": path.name, "duong_dan": rel(p, path), "v": int(st.st_mtime), "co": st.st_size}


def newest_input(p: du_an.DuAn) -> float:
    skip = {"ban-goc", "thung-rac"}
    times = [
        f.stat().st_mtime
        for f in (p.root / "assets").rglob("*")
        if f.is_file() and not f.name.startswith(".") and not skip & set(f.relative_to(p.root).parts)
    ]
    return max(times, default=0)


def project_state(name: str) -> dict:
    p = existing(name)
    if not job.busy(p.root.name):
        with print_lock, contextlib.redirect_stdout(io.StringIO()):
            du_an.prepare(p.root)

    state: dict = {"ten": p.root.name, "duong_dan": f"du-an/{p.root.name}", "giong_co_san": VOICES}
    docx = the_docx(p)
    docx_count = len([f for f in p.kich_ban.glob("*.docx") if not f.name.startswith("~$")])
    script, parts, script_error = None, {}, None
    if docx:
        try:
            script = read_script(docx)
            parts = scene_list(docx)
        except SystemExit as e:
            script_error = str(e)
        except Exception as e:  # noqa: BLE001 - file Word hỏng, báo lại cho người dùng
            script_error = f"Không đọc được {docx.name}: {e}"
    elif docx_count > 1:
        script_error = f"Thư mục kịch bản có {docx_count} file .docx, cần đúng 1 file"

    durations = {}
    timing = {}
    for part in ("video_90s", "quang_cao_30s"):
        f = p.giong_doc / part / "thoi_gian.json"
        if f.exists():
            data = json.loads(f.read_text("utf-8"))
            durations[part] = data.get("tong")
            timing[part] = data.get("canh", [])

    state["kich_ban"] = {
        "tep": file_info(p, docx) if docx else None,
        "loi": script_error,
        "tieu_de": script.title if script else None,
        "chu_anh_bia": script.cover_text if script else None,
        "phan": {k: len(v) for k, v in parts.items()},
        "thoi_luong": durations,
        "ban_goc": bool(docx and (p.ban_goc / docx.name).exists()),
    }

    # Ảnh: mỗi cảnh có số ô = số khung trong kịch bản (hoặc số ảnh đang có nếu nhiều hơn)
    images = find_images(p.anh)
    scenes, errors, warnings = [], [], []
    if script:
        for sc in script.scenes:
            files = images.scenes.get(sc.number, [])
            scenes.append({
                "so": sc.number,
                "ten": sc.title,
                "mo_ta": sc.image_note,
                "so_khung": sc.frame_count,
                "y_khung": sc.frame_notes,
                "o": max(sc.frame_count, len(files), 1),
                "anh": [file_info(p, f) for f in files],
                "khong_bat_buoc": sc is script.scenes[-1] and is_cta(sc) and len(script.scenes) > 1,
            })
        with print_lock, contextlib.redirect_stdout(io.StringIO()) as out:
            errors = check_images(script, images)
        warnings = [line.strip().lstrip("! ").strip() for line in out.getvalue().splitlines() if line.strip()]
    state["anh"] = {
        "bia": file_info(p, images.cover) if images.cover else None,
        "canh": scenes,
        "chua_ro": [file_info(p, f) for f in images.unknown],
        "ngoai_kich_ban": [
            file_info(p, f) for n, fs in images.scenes.items()
            if script and n not in {sc.number for sc in script.scenes} for f in fs
        ],
        "loi": errors,
        "canh_bao": warnings,
    }

    music = sorted(f for f in p.nhac.iterdir() if f.suffix.lower() in du_an.AUDIO_EXT) if p.nhac.exists() else []
    state["nhac"] = [file_info(p, f) for f in music]

    effects = {"tep": None, "canh": [], "loi": None, "co_prompt": p.prompt.exists()}
    if p.hieu_ung_json.exists():
        effects["tep"] = file_info(p, p.hieu_ung_json)
        try:
            with print_lock, contextlib.redirect_stdout(io.StringIO()):
                effects["canh"] = sorted(n for n in hieu_ung.load(p.hieu_ung_json) if n)
        except Exception as e:  # noqa: BLE001
            effects["loi"] = f"Không đọc được hieu_ung.json: {e}"
    state["hieu_ung"] = effects

    raw = cau_hinh.load(p.cau_hinh_file)
    state["cau_hinh"] = {
        "giong_doc": raw.get("giong_doc", {}),
        "cach_doc": raw.get("cach_doc", {}),
        "video": raw.get("video", {}),
        "mac_dinh": {
            **(voice_defaults(docx) if docx and not script_error else
               {"giong": giong_doc.DEFAULT_VOICE, "toc_do": giong_doc.DEFAULT_RATE}),
            "cach_doc": giong_doc.DEFAULT_PRONUNCIATIONS,
            "am_luong_nhac": 0.07,
        },
    }

    voice_dir = p.giong_doc / VOICE_PART
    voice_ok = (voice_dir / "thoi_gian.json").exists()
    voice_mp3 = voice_dir / f"{VOICE_PART}.mp3"
    state["giong"] = {
        "da_tao": voice_ok,
        "cu": voice_ok and (p.giong_doc / STALE).exists(),
        "tep": file_info(p, voice_mp3) if voice_mp3.exists() else None,
        "canh": timing.get(VOICE_PART, []),
    }

    video = None
    if p.video.exists():
        video = file_info(p, p.video)
        video["moi"] = p.video.stat().st_mtime >= newest_input(p) and not state["giong"]["cu"]
    state["video"] = video
    snaps = sorted(p.kiem_tra.glob("snap_*.png")) if p.kiem_tra.exists() else []
    state["anh_thu"] = [file_info(p, f) for f in snaps]

    image_count = sum(len(s["anh"]) for s in scenes) + (1 if images.cover else 0)
    state["buoc"] = {
        "kich_ban": bool(script),
        "anh": bool(script) and not errors,
        "giong": voice_ok and not state["giong"]["cu"],
        "video": bool(video and video["moi"]),
    }
    state["so_anh"] = image_count
    return state


# ---- Thay đổi tài nguyên ----


def to_trash(p: du_an.DuAn, path: Path) -> None:
    trash = p.root / "assets" / "thung-rac"
    trash.mkdir(parents=True, exist_ok=True)
    dst = trash / path.name
    n = 2
    while dst.exists():
        dst = trash / f"{path.stem}-{n}{path.suffix}"
        n += 1
    shutil.move(str(path), str(dst))


def mark_voice_stale(p: du_an.DuAn) -> None:
    if (p.giong_doc / VOICE_PART).exists():
        (p.giong_doc / STALE).write_text("", encoding="utf-8")


def safe_name(name: str) -> str:
    name = nfc(Path(urllib.parse.unquote(name)).name).strip()
    if not name or name.startswith((".", "~$")):
        raise UserError("Tên file không hợp lệ")
    return name


def unique(path: Path) -> Path:
    n = 2
    out = path
    while out.exists():
        out = path.with_name(f"{path.stem}-{n}{path.suffix}")
        n += 1
    return out


def scene_file_name(number: int, letter: str, title: str, ext: str) -> str:
    """Tên ảnh cho một cảnh, theo cùng kiểu prompt tạo ảnh dùng ("02b_noi_lo.png")."""
    slug = "_".join(hieu_ung.plain_words(title))[:40]
    name = f"{number:02d}{letter}_{slug}{ext}" if slug else f"{number:02d}{letter}{ext}"
    return name if scene_of(Path(name)) == number else f"{number:02d}{letter}{ext}"


def save_image(p: du_an.DuAn, name: str, data: bytes, scene: Optional[int], frame: Optional[int]) -> str:
    ext = Path(name).suffix.lower()
    if ext not in du_an.IMAGE_EXT:
        raise UserError("Ảnh cần là .png, .jpg, .jpeg hoặc .webp")
    p.anh.mkdir(parents=True, exist_ok=True)
    images = find_images(p.anh)
    if scene is None:
        target = p.anh / name
        if target.exists():
            to_trash(p, target)
    elif scene == 0:
        if images.cover:
            to_trash(p, images.cover)
        target = unique(p.anh / f"00_anh_bia{ext}")
    else:
        docx = the_docx(p)
        sc = next((s for s in read_script(docx).scenes if s.number == scene), None) if docx else None
        title = sc.title if sc else ""
        multi = bool(sc and sc.frame_count > 1)
        files = images.scenes.get(scene, [])
        if frame is not None and frame < len(files):
            old = files[frame]  # thay ảnh của khung này, giữ tên để không đổi thứ tự khung
            to_trash(p, old)
            target = old.with_suffix(ext)
        elif files and not multi and frame in (None, 0):
            to_trash(p, files[0])
            target = p.anh / scene_file_name(scene, "", title, ext)
        else:
            letter = chr(97 + len(files)) if multi or files else ""
            target = unique(p.anh / scene_file_name(scene, letter, title, ext))
    target.write_bytes(data)
    return target.name


def upload(name: str, kind: str, filename: str, data: bytes, query: dict) -> dict:
    p = existing(name)
    job.check_free(p.root.name)
    filename = safe_name(filename)
    ext = Path(filename).suffix.lower()
    if kind == "kich-ban":
        if ext != ".docx":
            raise UserError("Kịch bản cần là file Word .docx")
        p.kich_ban.mkdir(parents=True, exist_ok=True)
        for old in p.kich_ban.glob("*.docx"):
            to_trash(p, old)
        if (p.ban_goc / filename).exists():
            to_trash(p, p.ban_goc / filename)  # bản gốc cũ không còn đúng với file mới
        target = p.kich_ban / filename
        target.write_bytes(data)
        try:
            read_script(target)
            cau_hinh.ensure(p.cau_hinh_file, scene_list(target))
        except SystemExit as e:
            raise UserError(f"Đã lưu nhưng chưa đọc được kịch bản: {e}")
        mark_voice_stale(p)
        return {"ten": filename}
    if kind == "anh":
        scene = query.get("canh")
        frame = query.get("khung")
        saved = save_image(
            p, filename, data,
            int(scene) if scene not in (None, "") else None,
            int(frame) if frame not in (None, "") else None,
        )
        return {"ten": saved}
    if kind == "nhac":
        if ext not in du_an.AUDIO_EXT:
            raise UserError("Nhạc nền cần là .mp3, .m4a, .wav hoặc .aac")
        p.nhac.mkdir(parents=True, exist_ok=True)
        for old in p.nhac.iterdir():  # chương trình chỉ dùng một file nhạc
            if old.is_file() and old.suffix.lower() in du_an.AUDIO_EXT:
                to_trash(p, old)
        (p.nhac / filename).write_bytes(data)
        return {"ten": filename}
    if kind == "hieu-ung":
        return save_effects(p, data.decode("utf-8", errors="replace"))
    raise UserError("Loại tài nguyên không đúng")


def save_effects(p: du_an.DuAn, text: str) -> dict:
    tmp = p.hieu_ung / ".kiem_tra.json"
    p.hieu_ung.mkdir(parents=True, exist_ok=True)
    tmp.write_text(text, encoding="utf-8")
    try:
        with print_lock, contextlib.redirect_stdout(io.StringIO()):
            scenes = sorted(n for n in hieu_ung.load(tmp) if n)
    except Exception as e:  # noqa: BLE001
        tmp.unlink()
        raise UserError(f"Nội dung không phải JSON hiệu ứng hợp lệ: {e}")
    if not scenes:
        tmp.unlink()
        raise UserError('Không thấy cảnh nào (mỗi cảnh cần có "so" và "khoi")')
    tmp.replace(p.hieu_ung_json)
    return {"canh": scenes}


def delete(name: str, kind: str, filename: str) -> None:
    p = existing(name)
    job.check_free(p.root.name)
    folder = {"anh": p.anh, "nhac": p.nhac, "hieu-ung": p.hieu_ung, "anh-thu": p.kiem_tra}.get(kind)
    if folder is None:
        raise UserError("Loại tài nguyên không đúng")
    path = folder / safe_name(filename)
    if not path.is_file():
        raise UserError("Không thấy file", 404)
    if kind == "anh-thu":
        path.unlink()
    else:
        to_trash(p, path)


def assign(name: str, filename: str, scene: int) -> dict:
    """Đổi tên ảnh chưa nhận ra cảnh để nó thuộc về cảnh `scene` (0 = ảnh bìa)."""
    p = existing(name)
    job.check_free(p.root.name)
    src = p.anh / safe_name(filename)
    if not src.is_file():
        raise UserError("Không thấy ảnh", 404)
    data = src.read_bytes()
    src.unlink()
    return {"ten": save_image(p, src.name, data, scene, None)}


def save_config(name: str, body: dict) -> None:
    p = existing(name)
    job.check_free(p.root.name)
    raw = cau_hinh.load(p.cau_hinh_file)
    old_voice = (raw.get("giong_doc", {}), raw.get("cach_doc", {}))

    voice = body.get("giong_doc", {})
    giong = voice.get("giong") or False
    toc_do = voice.get("toc_do") or False
    if giong and not re.match(r"^[a-z]{2}-[A-Z]{2}-\w+Neural$", giong):
        raise UserError("Tên giọng đọc không đúng")
    if toc_do and not re.match(r"^[+-]\d{1,3}%$", toc_do):
        raise UserError('Tốc độ cần dạng "+10%" hoặc "-5%"')
    raw["giong_doc"] = {"giong": giong, "toc_do": toc_do}

    pron = {}
    for word, said in body.get("cach_doc", {}).items():
        word, said = str(word).strip(), str(said).strip()
        if word and said:
            pron[word] = said
    raw["cach_doc"] = pron

    v = body.get("video", {})
    text = v.get("chu_tren_man_hinh") or False
    if text not in (False, "bat", "tat"):
        raise UserError("Chữ trên màn hình chỉ nhận tự động, bật hoặc tắt")
    volume = v.get("am_luong_nhac", False)
    if volume is not False:
        volume = float(volume)
        if not 0 <= volume <= 1:
            raise UserError("Âm lượng nhạc từ 0 đến 1")
    raw["video"] = {
        "chu_tren_man_hinh": text,
        "tat_hieu_ung_khoi": bool(v.get("tat_hieu_ung_khoi")),
        "tat_phu_de": bool(v.get("tat_phu_de")),
        "tat_nhac_nen": bool(v.get("tat_nhac_nen")),
        "am_luong_nhac": volume,
    }
    docx = the_docx(p)
    parts = None
    if docx:
        with contextlib.suppress(SystemExit, Exception):
            parts = scene_list(docx)
    p.cau_hinh.mkdir(parents=True, exist_ok=True)
    p.cau_hinh_file.write_text(cau_hinh.render(raw, parts), encoding="utf-8")
    if (raw["giong_doc"], raw["cach_doc"]) != (
        {k: old_voice[0].get(k, False) for k in ("giong", "toc_do")}, old_voice[1]
    ):
        mark_voice_stale(p)


def make_prompt(name: str) -> str:
    p = existing(name)
    docx = the_docx(p)
    if not docx:
        raise UserError("Cần có kịch bản trước khi tạo prompt")
    text = hieu_ung.make_prompt(read_script(docx))
    p.hieu_ung.mkdir(parents=True, exist_ok=True)
    p.prompt.write_text(text, encoding="utf-8")
    return text


def sample_voice(query: dict) -> bytes:
    """Đọc thử 1-2 câu đầu kịch bản (hoặc câu mẫu) bằng giọng, tốc độ đang chọn."""
    voice = query.get("giong") or giong_doc.DEFAULT_VOICE
    rate = query.get("toc_do") or giong_doc.DEFAULT_RATE
    if not re.match(r"^[a-z]{2}-[A-Z]{2}-\w+Neural$", voice) or not re.match(r"^[+-]\d{1,3}%$", rate):
        raise UserError("Giọng hoặc tốc độ không đúng")
    text, pron = SAMPLE_TEXT, dict(giong_doc.DEFAULT_PRONUNCIATIONS)
    if query.get("du_an"):
        p = existing(query["du_an"])
        pron.update(cau_hinh.settings(p.cau_hinh_file)["cach_doc"])
        docx = the_docx(p)
        with contextlib.suppress(SystemExit, Exception):
            first = read_script(docx).scenes[0].narration if docx else ""
            sentences = giong_doc.split_sentences(first)
            if sentences:
                text = " ".join(sentences[:2])
    try:
        clip = asyncio.run(giong_doc.synthesize(text, voice, rate, pron, asyncio.Semaphore(1), retries=2))
    except RuntimeError as e:
        raise UserError(f"Máy chủ giọng đọc không trả lời, kiểm tra mạng rồi thử lại ({e.__cause__ or e})", 502)
    return clip.audio


# ---- Chạy tao_video.py ----


class Job:
    """Một lần chạy tao_video.py; đọc dần kết quả in ra để giao diện hiển thị."""

    PROGRESS_RE = re.compile(r"^\s*([^:|]{1,40}):\s*(\d{1,3})%\|")

    def __init__(self):
        self.lock = threading.Lock()
        self.proc: Optional[subprocess.Popen] = None
        self.project = ""
        self.mode = ""
        self.lines: list = []
        self.progress: Optional[float] = None
        self.phase = ""
        self.started = 0.0
        self.ended = 0.0
        self.returncode: Optional[int] = None
        self.cancelled = False
        self.reuse_voice = False

    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def busy(self, project: str) -> bool:
        return self.running() and self.project == project

    def check_free(self, project: str) -> None:
        if self.busy(project):
            raise UserError("Dự án đang chạy, đợi xong hoặc bấm Dừng rồi thao tác lại", 409)

    def start(self, project: str, body: dict) -> None:
        p = existing(project)
        mode = body.get("che_do")
        if mode not in ("video", "giong", "anh-thu"):
            raise UserError("Chế độ chạy không đúng")
        with self.lock:
            if self.running():
                raise UserError(f"Đang chạy dự án {self.project}, đợi xong rồi chạy tiếp", 409)
            args = [sys.executable, "-u", str(TAO_VIDEO), str(p.root)]
            notes = []
            stale = (p.giong_doc / STALE).exists()
            reuse = mode != "giong" and bool(body.get("dung_lai_giong"))
            if reuse and stale:
                reuse = False
                notes.append("Kịch bản hoặc cài đặt giọng đã đổi: tạo lại giọng đọc.")
            if mode == "giong":
                args.append("--chi-giong")
            elif reuse:
                args.append("--bo-qua-giong")
            if mode == "anh-thu":
                seconds = [float(s) for s in body.get("giay", [])] or [3, 30, 60]
                args += ["--snapshots", *(f"{s:g}" for s in seconds)]
                if p.kiem_tra.exists():
                    for old in p.kiem_tra.glob("snap_*.png"):
                        old.unlink()
            env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
            self.proc = subprocess.Popen(
                args, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                start_new_session=True,
            )
            self.project, self.mode, self.reuse_voice = p.root.name, mode, reuse
            self.lines = notes + ["$ ./tao-video " + " ".join(a if " " not in a else f'"{a}"' for a in [f"du-an/{p.root.name}", *args[4:]])]
            self.progress, self.phase, self.returncode, self.cancelled = None, "Đang chạy", None, False
            self.started, self.ended = time.time(), 0.0
        threading.Thread(target=self._read, args=(self.proc, p), daemon=True).start()

    def _add(self, text: str, final: bool) -> None:
        text = text.rstrip()
        m = self.PROGRESS_RE.match(text)
        if m:  # thanh tiến độ của moviepy (tqdm): cập nhật %, không ghi thành dòng
            label = m.group(1).strip()
            self.phase = {"frame_index": "Dựng hình", "chunk": "Ghép âm thanh"}.get(label, label)
            self.progress = int(m.group(2)) / 100
            return
        if final and (text or (self.lines and self.lines[-1])):
            self.lines.append(text)

    def _read(self, proc: subprocess.Popen, p: du_an.DuAn) -> None:
        buf = ""
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        assert proc.stdout
        while True:
            chunk = proc.stdout.read1(4096)
            if not chunk:
                break
            buf += decoder.decode(chunk)
            while True:
                m = re.search(r"[\r\n]", buf)
                if not m:
                    break
                piece, sep, buf = buf[: m.start()], buf[m.start()], buf[m.end():]
                with self.lock:
                    self._add(piece, final=sep == "\n")
        proc.wait()
        with self.lock:
            if buf:
                self._add(buf, final=True)
            self.returncode = proc.returncode
            self.ended = time.time()
            if self.cancelled:
                self.lines.append("Đã dừng.")
                partial = p.video.with_name(p.video.stem + ".dang-dung.mp4")
                partial.unlink(missing_ok=True)
                for tmp in ROOT.glob(glob.escape(partial.stem) + "TEMP_MPY_*"):  # âm thanh tạm của moviepy
                    tmp.unlink(missing_ok=True)
            elif proc.returncode == 0:
                self.progress = 1.0
                if self.mode in ("video", "giong") and not self.reuse_voice:
                    (p.giong_doc / STALE).unlink(missing_ok=True)

    def cancel(self) -> None:
        with self.lock:
            if not self.running():
                return
            self.cancelled = True
            assert self.proc
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self.proc.pid, signal.SIGTERM)

    def snapshot(self, since: int) -> dict:
        with self.lock:
            running = self.running()
            return {
                "dang_chay": running,
                "du_an": self.project,
                "che_do": self.mode,
                "dong": self.lines[since:],
                "tong_dong": len(self.lines),
                "tien_do": self.progress,
                "giai_doan": self.phase,
                "bat_dau": self.started,
                "ket_thuc": self.ended,
                "ma_thoat": self.returncode,
                "da_dung": self.cancelled,
            }


job = Job()


# ---- HTTP ----


thumb_cache: dict = {}


def thumbnail(path: Path, width: int) -> bytes:
    key = (path, path.stat().st_mtime, width)
    if key not in thumb_cache:
        with Image.open(path) as im:
            im = im.convert("RGB")
            im.thumbnail((width, width * 4))
            out = io.BytesIO()
            im.save(out, "JPEG", quality=82)
        if len(thumb_cache) > 400:
            thumb_cache.clear()
        thumb_cache[key] = out.getvalue()
    return thumb_cache[key]


MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
    ".mp4": "video/mp4", ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".wav": "audio/wav",
    ".aac": "audio/aac", ".json": "application/json", ".md": "text/markdown; charset=utf-8",
    ".srt": "text/plain; charset=utf-8", ".txt": "text/plain; charset=utf-8",
    ".html": "text/html; charset=utf-8", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "VideoAI"

    def log_message(self, fmt, *args):  # chỉ in lỗi, không in từng yêu cầu
        if args and str(args[1])[:1] in "45":
            sys.stderr.write("  ! %s %s\n" % (self.command, self.path))

    # -- trả lời --

    def send_json(self, data, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_bytes(self, data: bytes, mime: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def send_file(self, path: Path, download: bool = False) -> None:
        size = path.stat().st_size
        mime = MIME.get(path.suffix.lower(), "application/octet-stream")
        start, end = 0, size - 1
        rng = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        if rng and size:
            if rng.group(1):
                start = int(rng.group(1))
                end = int(rng.group(2)) if rng.group(2) else size - 1
            else:
                start = max(0, size - int(rng.group(2) or 0))
            end = min(end, size - 1)
            if start > end:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Cache-Control", "no-cache")
        if download:
            self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + urllib.parse.quote(path.name))
        self.end_headers()
        with path.open("rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(1 << 20, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                left -= len(chunk)

    def body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def json_body(self) -> dict:
        raw = self.body()
        return json.loads(raw.decode("utf-8")) if raw else {}

    # -- định tuyến --

    def route(self, method: str) -> None:
        url = urllib.parse.urlsplit(self.path)
        parts = [urllib.parse.unquote(s) for s in url.path.split("/") if s]
        query = {k: v[-1] for k, v in urllib.parse.parse_qs(url.query).items()}
        try:
            self.dispatch(method, parts, query)
        except UserError as e:
            self.send_json({"loi": str(e)}, e.status)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:  # noqa: BLE001 - báo lỗi lên giao diện thay vì treo
            import traceback

            traceback.print_exc()
            self.send_json({"loi": f"Lỗi: {e}"}, 500)

    def dispatch(self, method: str, parts: list, query: dict) -> None:
        if method == "GET" and not parts:
            return self.send_file(WEB / "index.html")
        if parts[:1] == ["tep"] and len(parts) >= 3 and method == "GET":
            return self.serve_project_file(parts[1], parts[2:], query)
        if parts[:1] != ["api"]:
            raise UserError("Không có trang này", 404)
        api = parts[1:]

        if api == ["du-an"]:
            if method == "GET":
                return self.send_json(list_projects())
            if method == "POST":
                folder = project_dir(self.json_body().get("ten", ""))
                if folder.exists():
                    raise UserError(f"Đã có dự án {folder.name}")
                du_an.prepare(folder)
                return self.send_json({"ten": folder.name})
        if api == ["cong-viec"] and method == "GET":
            return self.send_json(job.snapshot(int(query.get("tu", 0))))
        if api == ["cong-viec", "dung"] and method == "POST":
            job.cancel()
            return self.send_json({})
        if api == ["nghe-thu"] and method == "GET":
            return self.send_bytes(sample_voice(query), "audio/mpeg")

        if len(api) >= 2 and api[0] == "du-an":
            name, action = api[1], api[2] if len(api) > 2 else ""
            if action == "xoa-du-an" and method == "POST":
                return self.send_json(delete_project(name))
            if action == "" and method == "GET":
                return self.send_json(project_state(name))
            if action == "tai-len" and method == "POST":
                result = upload(name, query.get("loai", ""), query.get("ten", ""), self.body(), query)
                return self.send_json(result)
            if action == "xoa" and method == "POST":
                b = self.json_body()
                delete(name, b.get("loai", ""), b.get("ten", ""))
                return self.send_json({})
            if action == "gan-canh" and method == "POST":
                b = self.json_body()
                return self.send_json(assign(name, b.get("ten", ""), int(b.get("canh", -1))))
            if action == "hieu-ung" and method == "POST":
                p = existing(name)
                job.check_free(p.root.name)
                return self.send_json(save_effects(p, self.body().decode("utf-8", errors="replace")))
            if action == "tao-prompt" and method == "POST":
                return self.send_json({"noi_dung": make_prompt(name)})
            if action == "prompt" and method == "GET":
                p = existing(name)
                text = p.prompt.read_text("utf-8") if p.prompt.exists() else ""
                return self.send_json({"noi_dung": text})
            if action == "cau-hinh" and method == "PUT":
                save_config(name, self.json_body())
                return self.send_json({})
            if action == "chay" and method == "POST":
                job.start(name, self.json_body())
                return self.send_json({})
        raise UserError("Không có yêu cầu này", 404)

    def serve_project_file(self, name: str, rest: list, query: dict) -> None:
        p = existing(name)
        path = (p.root / Path(*rest)).resolve()
        if not path.is_relative_to(p.root) or not path.is_file():
            raise UserError("Không thấy file", 404)
        width = query.get("rong")
        if width and path.suffix.lower() in du_an.IMAGE_EXT:
            return self.send_bytes(thumbnail(path, max(64, min(1080, int(width)))), "image/jpeg")
        self.send_file(path, download=query.get("tai") == "1")

    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def do_PUT(self):
        self.route("PUT")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cong", type=int, default=8765, help="cổng (mặc định 8765)")
    parser.add_argument("--khong-mo", action="store_true", help="không tự mở trình duyệt")
    args = parser.parse_args()

    server = None
    for port in range(args.cong, args.cong + 20):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    if server is None:
        raise SystemExit(f"Không mở được cổng {args.cong}-{args.cong + 19}")
    server.daemon_threads = True
    url = f"http://127.0.0.1:{server.server_address[1]}"
    print(f"Giao diện tạo video: {url}   (Ctrl+C để tắt)", flush=True)
    if not args.khong_mo:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nĐã tắt.")
    finally:
        job.cancel()


if __name__ == "__main__":
    main()
