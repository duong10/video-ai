#!/usr/bin/env python3
"""Một lệnh từ kịch bản Word + ảnh từng cảnh ra video hoàn chỉnh (giọng đọc, phụ đề, nhạc nền).

Mỗi video là một thư mục trong du-an/ (chạy ./tao-video du-an/<tên> với tên mới để tạo sẵn khung):

  du-an/<tên>/
    assets/
      kich-ban/     đúng 1 file kịch bản .docx (bảng có cột "Cảnh / Thời gian", "Hình ảnh",
                    "Chữ trên màn hình", "Lời đọc"); ban-goc/ giữ bản trước khi ghi mốc thời gian
      anh/          ảnh từng cảnh, tên file có số cảnh:
                      "Cảnh 1 · Mở đầu.png" hoặc "01_mo_dau.png" hoặc "1.jpg"
                    cảnh nhiều khung ("Cắt nhanh 4 khung"): nhiều ảnh cùng số cảnh, xếp theo tên
                      "02a_...", "02b_..." hoặc "Cảnh 2 · Nỗi đau 1:4.png", "...2:4.png"
                    ảnh bìa (không bắt buộc): tên chứa "bìa" hoặc bắt đầu bằng "00"
      nhac/         nhạc nền .mp3/.m4a/.wav (không bắt buộc)
      hieu-ung/     prompt_tao_anh.md (gửi AI tạo ảnh) và hieu_ung.json (AI trả về)
      cau-hinh/     cau_hinh.toml: tự sinh, liệt kê đủ mọi cấu hình (giọng, tốc độ, cách đọc,
                    từng cảnh, chữ trên màn hình, phụ đề, nhạc...). Giá trị false = dùng mặc
                    định; muốn đổi thì thay false bằng giá trị mới (chú thích ghi cách dùng).
    output/         <tên>.mp4, giong-doc/ (giọng đọc, phụ đề, mốc thời gian), anh-kiem-tra/
  File để lẫn ở thư mục dự án hoặc trong assets/ được tự xếp vào đúng thư mục khi chạy.

Ảnh do AI tạo (khuyên dùng cho ảnh thiết kế có chữ):
  ./tao-video du-an/<tên> --tao-prompt
      -> assets/hieu-ung/prompt_tao_anh.md: dán vào ChatGPT/Gemini. AI vẽ từng ảnh và trả về
         JSON mô tả các khối sẽ hiện ra (chữ, vùng, câu đọc làm mốc, kiểu hiệu ứng).
         Lưu ảnh vào assets/anh/, lưu JSON tổng thành assets/hieu-ung/hieu_ung.json.
  Cảnh có trong hieu_ung.json dựng theo đúng mô tả đó; cảnh không có thì tự dò khối.

Chạy (từ thư mục Video_AI; "./tao-video" là cách gõ tắt của ".venv/bin/python san_xuat/tao_video.py"):
  ./tao-video du-an/<tên>                          # giọng đọc + video
  ./tao-video                                      # mọi dự án chưa có video
  ./tao-video du-an/<tên> --bo-qua-giong           # chỉ đổi ảnh: dùng lại giọng cũ
  ./tao-video du-an/<tên> --chi-giong              # chỉ tạo giọng đọc
  ./tao-video du-an/<tên> --snapshots 3 30 60      # xuất vài ảnh để xem nhanh
  ./tao-video du-an/<tên> --khong-nhac
"""

import argparse
import asyncio
import shutil
import sys
import time
from pathlib import Path

import cau_hinh
import du_an
from kich_ban import ROOT, check_images, find_docx, find_images, read_script

import tao_tu_docx

PROJECTS = ROOT / "du-an"
VOICE_PART = tao_tu_docx.MAIN_NAME  # "video_90s"


def show(path: Path) -> str:
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def scene_list(docx_path: Path) -> dict:
    """{"video_90s": [("1", "01_mo_dau"), ...], "quang_cao_30s": [...]} để sinh mục từng cảnh."""
    from docx import Document

    parts = tao_tu_docx.read_parts(Document(docx_path), "+10%", {})
    return {part.name: [(str(int(s.slug[:2])), s.slug) for s in part.scenes] for part in parts}


def find_music(folder: Path):
    files = sorted(f for f in folder.iterdir() if f.suffix.lower() in du_an.AUDIO_EXT)
    if len(files) > 1:
        print(f"  ! Có {len(files)} file nhạc, dùng {files[0].name}")
    return files[0] if files else None


def process(folder: Path, args) -> None:
    new = not folder.exists()
    p = du_an.prepare(folder)
    if new or not any(p.kich_ban.glob("*.docx")):
        print(f"\nĐã tạo khung dự án {show(p.root)}/. Bỏ vào:")
        print(f"  {show(p.kich_ban)}/   file kịch bản .docx")
        print(f"  {show(p.anh)}/        ảnh từng cảnh (hoặc chạy --tao-prompt để nhờ AI tạo ảnh)")
        print(f"  {show(p.nhac)}/       nhạc nền (không bắt buộc)")
        print(f"Cấu hình (giọng, tốc độ, phụ đề, nhạc...): {show(p.cau_hinh_file)}")
        print(f"rồi chạy lại: ./tao-video {show(p.root)}")
        return
    docx_path = find_docx(p.kich_ban)
    cau_hinh.ensure(p.cau_hinh_file, scene_list(docx_path))
    tuning = cau_hinh.settings(p.cau_hinh_file)
    video_opts = tuning["video"]

    print(f"\n######## {p.root.name}")
    script = read_script(docx_path)

    # 0. Prompt cho AI tạo ảnh (kèm yêu cầu trả về hieu_ung.json)
    if args.tao_prompt:
        import hieu_ung

        p.prompt.write_text(hieu_ung.make_prompt(script), encoding="utf-8")
        print(f"  Đã tạo {show(p.prompt)}: dán toàn bộ vào AI tạo ảnh (ChatGPT, Gemini...).")
        print(f"  Lưu ảnh vào {show(p.anh)}/, lưu JSON tổng AI trả về thành {show(p.hieu_ung_json)}")
        print("  rồi chạy lại không có --tao-prompt.")
        return

    images = find_images(p.anh)
    errors = check_images(script, images)
    if errors and not args.chi_giong:
        print("\nChưa dựng được video vì thiếu ảnh:")
        for e in errors:
            print(f"  - {e}")
        raise SystemExit(1)
    print(
        f"  {len(script.scenes)} cảnh, "
        f"{sum(len(v) for v in images.scenes.values())} ảnh cảnh"
        f"{', có ảnh bìa' if images.cover else ''}"
    )

    # 1. Giọng đọc
    voice_dir = p.giong_doc / VOICE_PART
    if args.bo_qua_giong and (voice_dir / "thoi_gian.json").exists():
        print("  Dùng lại giọng đọc đã tạo")
    else:
        backup = p.ban_goc / docx_path.name
        if not backup.exists():
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(docx_path, backup)
        asyncio.run(tao_tu_docx.process(docx_path, out_dir=p.giong_doc, tuning=tuning))
    if args.chi_giong:
        return

    # 2. Video
    import dung_video  # nạp moviepy chỉ khi cần dựng video

    import hieu_ung

    music = None if args.khong_nhac or not video_opts["nhac_nen"] else find_music(p.nhac)
    effects = hieu_ung.load(p.hieu_ung_json) if p.hieu_ung_json.exists() else {}
    if effects:
        print(f"  hieu_ung.json: mô tả hiệu ứng cho cảnh {', '.join(str(n) for n in sorted(effects) if n)}")
    video = dung_video.assemble(
        script,
        images,
        voice_dir,
        music=music,
        music_volume=video_opts["am_luong_nhac"],
        overlays_on=video_opts["chu_tren_man_hinh"],
        subtitles_on=video_opts["phu_de"],
        blocks_on=video_opts["hieu_ung_khoi"],
        effects=effects,
    )
    if args.snapshots is not None:
        p.kiem_tra.mkdir(parents=True, exist_ok=True)
        for t in args.snapshots:
            path = p.kiem_tra / f"snap_{t:06.2f}.png"
            video.save_frame(str(path), t=min(t, video.duration - 0.05))
            print(f"  {show(path)}")
        return
    started = time.time()
    dung_video.write(video, p.video)
    print(f"\nXong: {show(p.video)}  ({video.duration:.1f}s video, dựng mất {time.time() - started:.0f}s)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("thu_muc", nargs="*", type=Path, help="thư mục dự án; bỏ trống = mọi dự án trong du-an/ chưa có video")
    parser.add_argument("--bo-qua-giong", action="store_true", help="dùng lại giọng đọc đã tạo")
    parser.add_argument("--chi-giong", action="store_true", help="chỉ tạo giọng đọc, không dựng video")
    parser.add_argument("--khong-nhac", action="store_true", help="không dùng nhạc nền")
    parser.add_argument("--snapshots", type=float, nargs="*", help="chỉ lưu ảnh tại các giây này để kiểm tra")
    parser.add_argument(
        "--tao-prompt", action="store_true", help="tạo prompt_tao_anh.md để dán vào AI tạo ảnh (kèm mô tả hiệu ứng)"
    )
    args = parser.parse_args()

    folders = args.thu_muc
    if not folders:
        PROJECTS.mkdir(exist_ok=True)
        folders = [
            f for f in sorted(PROJECTS.iterdir())
            if f.is_dir() and du_an.is_project(f) and not du_an.paths(f).video.exists()
        ]
        if not folders:
            print(f"Không có dự án mới trong {PROJECTS.relative_to(ROOT)}/ (tạo dự án mới: ./tao-video du-an/<tên>)")
            return
    for folder in folders:
        process(folder, args)


if __name__ == "__main__":
    sys.exit(main())
