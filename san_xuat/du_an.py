"""Cấu trúc thư mục của một dự án video.

du-an/<tên>/
  assets/                      tài nguyên đầu vào, mỗi loại một thư mục
    kich-ban/                  file kịch bản .docx (đúng 1 file)
      ban-goc/                 bản gốc trước khi được ghi mốc thời gian
    anh/                       ảnh từng cảnh + ảnh bìa
    nhac/                      nhạc nền (không bắt buộc)
    hieu-ung/                  prompt_tao_anh.md gửi AI tạo ảnh, hieu_ung.json AI trả về
    cau-hinh/                  cau_hinh.toml: mọi cấu hình, tự sinh, giá trị false = mặc định
  output/                      kết quả, do chương trình tạo
    <tên>.mp4                  video hoàn chỉnh
    giong-doc/                 giọng đọc, phụ đề, mốc thời gian (video_90s/, quang_cao_30s/)
    anh-kiem-tra/              ảnh chụp thử khi chạy --snapshots

File để lẫn ở thư mục dự án hoặc ngay trong assets/ được tự xếp vào đúng chỗ.
"""

import shutil
from pathlib import Path
from typing import NamedTuple

import cau_hinh

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
AUDIO_EXT = {".mp3", ".m4a", ".wav", ".aac"}
VOICE_NAMES = {"video_90s", "quang_cao_30s"}


class DuAn(NamedTuple):
    root: Path
    kich_ban: Path
    ban_goc: Path
    anh: Path
    nhac: Path
    hieu_ung: Path
    cau_hinh: Path
    output: Path
    giong_doc: Path
    kiem_tra: Path

    @property
    def cau_hinh_file(self) -> Path:
        return self.cau_hinh / "cau_hinh.toml"

    @property
    def hieu_ung_json(self) -> Path:
        return self.hieu_ung / "hieu_ung.json"

    @property
    def prompt(self) -> Path:
        return self.hieu_ung / "prompt_tao_anh.md"

    @property
    def video(self) -> Path:
        return self.output / f"{self.root.name}.mp4"


def paths(folder: Path) -> DuAn:
    root = folder.resolve()
    assets = root / "assets"
    out = root / "output"
    return DuAn(
        root,
        assets / "kich-ban",
        assets / "kich-ban" / "ban-goc",
        assets / "anh",
        assets / "nhac",
        assets / "hieu-ung",
        assets / "cau-hinh",
        out,
        out / "giong-doc",
        out / "anh-kiem-tra",
    )


def is_project(folder: Path) -> bool:
    return any(folder.glob("*.docx")) or any((folder / "assets" / "kich-ban").glob("*.docx"))


def _target(p: DuAn, f: Path):
    """Thư mục đúng của một file để lẫn, hoặc None nếu không nhận ra."""
    name, ext = f.name.lower(), f.suffix.lower()
    if f.name.startswith(("~$", ".")):
        return None
    if ext == ".docx":
        return p.kich_ban
    if ext in IMAGE_EXT:
        return p.anh
    if ext in AUDIO_EXT:
        # giọng đọc cũ để lẫn (video_90s.mp3...) không phải nhạc nền: để nguyên
        return None if f.stem.lower() in VOICE_NAMES else p.nhac
    if name in ("hieu_ung.json", "prompt_tao_anh.md"):
        return p.hieu_ung
    if ext == ".toml":
        return p.cau_hinh
    return None


def _move(src: Path, dst_dir: Path, root: Path) -> None:
    dst = dst_dir / src.name
    if dst.exists():
        print(f"  ! Không chuyển {src.relative_to(root)}: đã có {dst.relative_to(root)}")
        return
    dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    print(f"  Chuyển {src.relative_to(root)} -> {dst.relative_to(root)}")


def prepare(folder: Path) -> DuAn:
    """Tạo khung thư mục và xếp các file để lẫn vào đúng chỗ."""
    p = paths(folder)
    for loose_dir in (p.root, p.root / "assets"):
        if not loose_dir.is_dir():
            continue
        for f in sorted(loose_dir.iterdir()):
            if f.is_file() and (dst := _target(p, f)):
                _move(f, dst, p.root)
    # bố cục cũ: ban-goc/ ở thư mục dự án; giọng đọc và ảnh chụp thử nằm thẳng trong output/
    old_backup = p.root / "ban-goc"
    if old_backup.is_dir():
        for f in sorted(old_backup.iterdir()):
            _move(f, p.ban_goc, p.root)
        if not any(old_backup.iterdir()):
            old_backup.rmdir()
    if p.output.is_dir():
        for part in ("video_90s", "quang_cao_30s"):
            if (p.output / part).is_dir():
                _move(p.output / part, p.giong_doc, p.root)
        for snap in sorted(p.output.glob("snap_*.png")):
            _move(snap, p.kiem_tra, p.root)
    for d in (p.kich_ban, p.anh, p.nhac, p.hieu_ung, p.cau_hinh):
        d.mkdir(parents=True, exist_ok=True)
    cau_hinh.ensure(p.cau_hinh_file)
    return p
