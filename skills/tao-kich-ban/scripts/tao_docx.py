#!/usr/bin/env python3
"""Tạo file kịch bản Word (.docx) đúng mẫu của Video_AI từ file JSON, rồi kiểm tra lại.

Chạy bằng Python của Video_AI (đã có python-docx):

    /Users/duongca/WorkSpace/Video_AI/.venv/bin/python tao_docx.py <kich_ban.json> <file.docx>
    ... tao_docx.py --kiem-tra <file.docx>      # chỉ kiểm tra một file có sẵn

Sau khi ghi, file được đọc lại bằng chính code của Video_AI (kich_ban.read_script và
tao_tu_docx.read_parts), nên đã qua bước này thì ./tao-video đọc được.

Định dạng JSON: xem mau/vi_du_lich_dat_xe.json cạnh thư mục scripts/.
Không có mốc thời gian nào trong file: chương trình tự ghi mốc thật sau khi tạo giọng đọc.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Emu, Pt, RGBColor

VIDEO_AI = Path(os.environ.get("VIDEO_AI", "/Users/duongca/WorkSpace/Video_AI"))

FONT = "Arial"
BLUE = RGBColor(0x1F, 0x4E, 0x79)
GRAY = RGBColor(0x7F, 0x7F, 0x7F)
HEADER_FILL = "DCE6F1"
STRIPE_FILL = "F7F9FC"
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"
MAIN_WIDTHS = [952500, 2349500, 2095500, 3854450]  # Cảnh / Hình ảnh / Chữ / Lời đọc
AD_WIDTHS = [1397000, 7854950]

# Độ dài lời đọc (số tiếng), đo từ kịch bản mẫu: bản chính 282 tiếng đọc trong 87,6 giây,
# bản rút gọn 50 tiếng trong 19,4 giây (giọng NamMinh, khoảng +10%).
MAIN_SYLLABLES = (250, 310)
AD_SYLLABLES = (40, 60)


# ---- Ghi file Word ----


def style_run(run, size=10, bold=None, italic=None, color=None):
    run.font.name = FONT
    run._r.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), FONT)
    run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    if color is not None:
        run.font.color.rgb = color
    return run


def shade(cell, fill):
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    cell._tc.get_or_add_tcPr().append(shd)


def write_lines(cell, lines, size=9.5, **fmt):
    """Mỗi dòng một paragraph trong ô (paragraph đầu của ô đã có sẵn)."""
    for i, line in enumerate(lines):
        para = cell.paragraphs[0] if i == 0 else cell.add_paragraph()
        para.paragraph_format.space_after = Pt(2)
        style_run(para.add_run(line), size=size, **fmt)


def quoted(text):
    return f"“{text.strip()}”"


def make_table(doc, headers, widths):
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.autofit = False
    for cell, text, width in zip(table.rows[0].cells, headers, widths):
        cell.width = Emu(width)
        shade(cell, HEADER_FILL)
        write_lines(cell, [text], size=10, bold=True)
    return table


def add_row(table, widths, stripe):
    cells = table.add_row().cells
    for cell, width in zip(cells, widths):
        cell.width = Emu(width)
        if stripe:
            shade(cell, STRIPE_FILL)
    return cells


def heading(doc, text):
    para = doc.add_paragraph(style="Heading 1")
    style_run(para.add_run(text), size=14, bold=True, color=BLUE)


def labeled(doc, label, value, style=None):
    para = doc.add_paragraph(style=style)
    style_run(para.add_run(f"{label}: "), bold=True)
    style_run(para.add_run(value))
    return para


def image_lines(hinh_anh):
    lines = [hinh_anh["mo_ta"]] if hinh_anh.get("mo_ta") else []
    lines += [f"{CIRCLED[i]} {k}" for i, k in enumerate(hinh_anh.get("khung", []))]
    return lines


def build(data, out: Path):
    doc = Document()
    sec = doc.sections[0]
    sec.orientation = WD_ORIENT.LANDSCAPE
    sec.page_width, sec.page_height = Emu(10692130), Emu(7560310)
    sec.left_margin = sec.right_margin = Emu(720090)
    sec.top_margin = sec.bottom_margin = Emu(635000)

    para = doc.add_paragraph()
    style_run(para.add_run("KỊCH BẢN VIDEO"), bold=True, color=GRAY)
    para = doc.add_paragraph(style="Title")
    style_run(para.add_run(data["tieu_de"]), size=20, bold=True, color=BLUE)

    labeled(doc, "Nguồn", data["nguon"])
    labeled(doc, "Định dạng", data.get("dinh_dang", "Video dọc 9:16 cho TikTok, Reels, YouTube Shorts"))
    # Phần sau nhãn "Thời lượng:" được ./tao-video ghi đè bằng thời lượng thật.
    labeled(
        doc,
        "Thời lượng",
        f"tự điền sau khi tạo giọng đọc – giọng {data.get('giong', 'vi-VN-NamMinhNeural')}, "
        f"tốc độ {data.get('toc_do', '+10%')}",
    )
    labeled(doc, "Giọng đọc", data["giong_doc"])
    labeled(doc, "Nhân vật", data["nhan_vat"])

    heading(doc, "Kịch bản chi tiết (mốc thời gian theo giọng đọc)")
    table = make_table(doc, ["Cảnh / Thời gian", "Hình ảnh", "Chữ trên màn hình", "Lời đọc"], MAIN_WIDTHS)
    for n, scene in enumerate(data["canh"], 1):
        cells = add_row(table, MAIN_WIDTHS, stripe=n % 2 == 0)
        # Chỉ ghi "số. tên cảnh"; dòng mốc giờ bên dưới do chương trình tự thêm.
        write_lines(cells[0], [f"{n}. {scene['ten']}"], bold=True, color=BLUE)
        write_lines(cells[1], image_lines(scene["hinh_anh"]))
        write_lines(cells[2], scene["chu"], bold=True)
        write_lines(cells[3], [quoted(scene["loi_doc"])], italic=True)

    if data.get("rut_gon"):
        heading(doc, "Bản rút gọn (dùng để chạy quảng cáo)")
        table = make_table(doc, ["Thời gian", "Lời đọc"], AD_WIDTHS)
        for n, text in enumerate(data["rut_gon"], 1):
            cells = add_row(table, AD_WIDTHS, stripe=n % 2 == 0)
            write_lines(cells[1], [quoted(text)], italic=True)

    heading(doc, "Chú thích bài đăng (caption)")
    for line in data["caption"]:
        style_run(doc.add_paragraph().add_run(line))
    style_run(doc.add_paragraph().add_run(data["hashtag"]), color=BLUE)

    heading(doc, "Gợi ý sản xuất")
    for item in data["goi_y"]:
        labeled(doc, item["nhan"], item["noi_dung"], style="List Bullet")

    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)


# ---- Kiểm tra ----


def syllables(text):
    return len(re.findall(r"[0-9A-Za-zÀ-ỹđĐ]+(?:[.,][0-9]+)*", text))


def check_data(data):
    """Lỗi về nội dung, phát hiện trước khi ghi file."""
    errors, warnings = [], []
    scenes = data.get("canh", [])
    if not 6 <= len(scenes) <= 10:
        warnings.append(f"Có {len(scenes)} cảnh; mẫu chuẩn là 8 (khoảng 6–10)")
    for n, scene in enumerate(scenes, 1):
        tag = f"Cảnh {n} ({scene.get('ten', '?')})"
        text = scene.get("loi_doc", "")
        if not text.strip():
            errors.append(f"{tag}: thiếu lời đọc")
        if re.search(r"[“”\"]", text):
            errors.append(f"{tag}: lời đọc không được chứa dấu ngoặc kép (dùng ‘…’ nếu cần)")
        if re.search(r"\d+[:.,]\d+\s*(?:–|-)\s*\d+[:.,]\d+|\d+(?:[.,]\d+)?\s*giây", scene.get("ten", "")):
            errors.append(f"{tag}: tên cảnh không được ghi mốc thời gian")
        hinh = scene.get("hinh_anh", {})
        frames = hinh.get("khung", [])
        m = re.search(r"(\d+)\s*khung", hinh.get("mo_ta", ""))
        if m and int(m.group(1)) != len(frames):
            errors.append(f"{tag}: ghi {m.group(1)} khung nhưng liệt kê {len(frames)} ý ①②…")
        if len(frames) > len(CIRCLED):
            errors.append(f"{tag}: tối đa {len(CIRCLED)} khung")
        if not scene.get("chu"):
            errors.append(f"{tag}: thiếu chữ trên màn hình")
    if scenes and not re.search(r"hotline|\d{3,4}[. ]\d{3,4}[. ]\d{3}|dùng thử",
                                " ".join(scenes[-1].get("chu", [])).lower()):
        warnings.append("Cảnh cuối không có hotline hoặc “Dùng thử”: video sẽ không có bảng kêu gọi hành động")
    if not any(g.get("nhan", "").lower().startswith("ảnh bìa") and "“" in g.get("noi_dung", "")
               for g in data.get("goi_y", [])):
        errors.append("Gợi ý sản xuất thiếu mục “Ảnh bìa” có chữ to trong ngoặc kép “…”")

    main = sum(syllables(s.get("loi_doc", "")) for s in scenes)
    ad = sum(syllables(t) for t in data.get("rut_gon", []))
    if not MAIN_SYLLABLES[0] <= main <= MAIN_SYLLABLES[1]:
        warnings.append(f"Lời đọc bản chính {main} tiếng (nên {MAIN_SYLLABLES[0]}–{MAIN_SYLLABLES[1]})")
    if data.get("rut_gon") and not AD_SYLLABLES[0] <= ad <= AD_SYLLABLES[1]:
        warnings.append(f"Lời đọc bản rút gọn {ad} tiếng (nên {AD_SYLLABLES[0]}–{AD_SYLLABLES[1]})")
    return errors, warnings, main, ad


def check_docx(path: Path):
    """Đọc lại file bằng code của Video_AI: trả về (số cảnh chính, số dòng rút gọn, ảnh bìa)."""
    sys.path.insert(0, str(VIDEO_AI / "san_xuat"))
    import kich_ban
    import tao_tu_docx

    script = kich_ban.read_script(path)
    parts = tao_tu_docx.read_parts(Document(path), "+10%", {})
    counts = {p.name: len(p.scenes) for p in parts}
    return script, counts


def report(path: Path, data=None):
    script, counts = check_docx(path)
    print(f"Đã kiểm tra bằng code Video_AI: {path}")
    print(f"  Tiêu đề: {script.title}")
    print(f"  Ảnh bìa: {script.cover_text or '(không có)'}")
    for sc in script.scenes:
        frames = f", {sc.frame_count} khung" if sc.frame_count > 1 else ""
        print(f"  {sc.number}. {sc.title}{frames}")
    print(f"  Bảng chính: {counts.get('video_90s', 0)} cảnh có lời đọc;"
          f" bản rút gọn: {counts.get('quang_cao_30s', 0)} dòng")
    if data is not None and len(script.scenes) != len(data["canh"]):
        raise SystemExit("Số cảnh đọc lại khác số cảnh trong JSON")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("json", nargs="?", help="file kịch bản JSON")
    parser.add_argument("docx", help="file .docx cần ghi (hoặc cần kiểm tra khi dùng --kiem-tra)")
    parser.add_argument("--kiem-tra", action="store_true", help="chỉ kiểm tra file .docx có sẵn")
    args = parser.parse_args()

    out = Path(args.docx).resolve()
    if args.kiem_tra:
        report(out)
        return

    data = json.loads(Path(args.json).read_text("utf-8"))
    errors, warnings, main_count, ad_count = check_data(data)
    for w in warnings:
        print(f"  ! {w}")
    if errors:
        print("Chưa ghi file vì kịch bản còn lỗi:", *[f"  ✗ {e}" for e in errors], sep="\n")
        sys.exit(1)
    build(data, out)
    print(f"Lời đọc: bản chính {main_count} tiếng, bản rút gọn {ad_count} tiếng")
    report(out, data)


if __name__ == "__main__":
    main()
