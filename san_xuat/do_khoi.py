"""Tự đo tọa độ các khối nội dung trong ảnh thiết kế sẵn chữ (thẻ, dòng, bước, biểu tượng).

Thay cho việc mở từng ảnh ra đo tay rồi ghi số vào code:
  1. Phân biệt ảnh thiết kế (nền trơn/chuyển màu, nhiều vùng phẳng) với ảnh chụp.
  2. Ước lượng màu nền từng hàng ở hai mép ảnh, đánh dấu pixel khác nền, gộp chữ
     gần nhau thành khối rồi lấy các vùng liền nhau. Khối lớn có nền một màu (tờ
     hợp đồng, bảng) được chia tiếp thành các dòng bên trong.
  3. Bỏ qua phần đứng yên: tiêu đề trên cùng, hình chạm mép ảnh, hình minh họa lớn.
  4. Đọc chữ trong từng khối bằng OCR có sẵn của macOS (Vision), để bước dựng video
     canh mỗi khối hiện ra đúng lúc giọng đọc nhắc tới.
"""

import tempfile
from pathlib import Path
from typing import List, NamedTuple, Tuple

import cv2
import numpy as np
from PIL import Image

Box = Tuple[int, int, int, int]  # x0, y0, x1, y1

HEADER_RATIO = 0.22  # khối nằm trong 22% chiều cao phía trên là tiêu đề, đứng yên
MAX_BLOCK_RATIO = 0.12  # khối to hơn 12% ảnh mà không phải tấm nền -> hình minh họa, đứng yên


class Block(NamedTuple):
    box: Box
    text: str
    pop: bool  # True: bật ra (biểu tượng nhỏ, gần vuông); False: trượt lên


class TextLine(NamedTuple):
    box: Box
    text: str


def is_graphic(img: np.ndarray) -> bool:
    """Ảnh thiết kế có nhiều vùng phẳng; ảnh chụp thì gần như chỗ nào cũng có vân."""
    gray = cv2.cvtColor(cv2.resize(img, (270, 480), interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2GRAY)
    grad = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0)) + np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1))
    return float((grad < 6).mean()) > 0.55


# ---- OCR ----


def read_text(img: np.ndarray) -> List[TextLine]:
    """Các dòng chữ trong ảnh kèm vị trí (pixel). Không có Vision (không phải macOS) thì trả về rỗng."""
    try:
        import Quartz
        import Vision
        from Foundation import NSURL
    except ImportError:
        return []
    h, w = img.shape[:2]
    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        Image.fromarray(img).save(tmp.name)
        src = Quartz.CGImageSourceCreateWithURL(NSURL.fileURLWithPath_(tmp.name), None)
        cg = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)
        req = Vision.VNRecognizeTextRequest.alloc().init()
        req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        req.setRecognitionLanguages_(["vi-VT", "en-US"])
        req.setUsesLanguageCorrection_(True)
        handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg, None)
        handler.performRequests_error_([req], None)
    lines = []
    for r in req.results() or []:
        b = r.boundingBox()  # tọa độ chuẩn hóa, gốc ở góc dưới bên trái
        x0, x1 = b.origin.x * w, (b.origin.x + b.size.width) * w
        y0, y1 = (1 - b.origin.y - b.size.height) * h, (1 - b.origin.y) * h
        lines.append(TextLine((int(x0), int(y0), int(x1), int(y1)), r.topCandidates_(1)[0].string()))
    return lines


# ---- Dò khối ----


def background_rows(img: np.ndarray, margin=24) -> np.ndarray:
    """Màu nền từng hàng: trung vị của hai dải sát mép trái/phải, làm mượn theo chiều dọc."""
    edges = np.concatenate([img[:, :margin], img[:, -margin:]], axis=1).astype(np.float32)
    bg = np.median(edges, axis=1)  # (H, 3)
    k = 41
    padded = np.pad(bg, ((k // 2, k // 2), (0, 0)), mode="edge")
    smooth = np.stack([np.convolve(padded[:, c], np.ones(k) / k, "valid") for c in range(3)], axis=1)
    return smooth


def components(mask: np.ndarray, close=(35, 15), min_h=14, min_area=900) -> List[Box]:
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, close)
    merged = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, kernel)
    n, _, stats, _ = cv2.connectedComponentsWithStats(merged, connectivity=8)
    boxes = []
    for x, y, w, h, area in stats[1:]:
        if h >= min_h and w * h >= min_area:
            boxes.append((int(x), int(y), int(x + w), int(y + h)))
    return boxes


def panel_children(img: np.ndarray, box: Box) -> List[Box]:
    """Khối lớn có nền một màu (tờ giấy, bảng): tìm các dòng/thẻ bên trong."""
    x0, y0, x1, y1 = box
    region = img[y0:y1, x0:x1].astype(np.int16)
    colors = region.reshape(-1, 3) // 8
    vals, counts = np.unique(colors, axis=0, return_counts=True)
    if counts.max() / colors.shape[0] < 0.5:
        return []  # không có màu nền chiếm ưu thế -> hình minh họa
    fill = vals[counts.argmax()] * 8 + 4
    inset = 14
    inner = np.abs(region - fill).max(axis=2) > 28
    inner[:inset], inner[-inset:], inner[:, :inset], inner[:, -inset:] = False, False, False, False
    kids = components(inner, close=(41, 9))
    kids = [(a + x0, b + y0, c + x0, d + y0) for a, b, c, d in kids]
    return kids if len(kids) >= 2 else []


def reading_order(boxes: List[Box]) -> List[Box]:
    """Trên xuống dưới; các khối cùng hàng (chồng nhau theo chiều dọc) thì trái sang phải."""
    rows: List[List[Box]] = []
    for b in sorted(boxes, key=lambda b: b[1]):
        if rows and b[1] < (rows[-1][0][1] + rows[-1][0][3]) / 2:
            rows[-1].append(b)
        else:
            rows.append([b])
    return [b for row in rows for b in sorted(row, key=lambda b: b[0])]


def contains(outer: Box, inner: Box, tol=6) -> bool:
    return (
        outer != inner
        and outer[0] - tol <= inner[0] and outer[1] - tol <= inner[1]
        and inner[2] <= outer[2] + tol and inner[3] <= outer[3] + tol
    )


def union(boxes: List[Box]) -> Box:
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def center_in(line: TextLine, box: Box, tol=4) -> bool:
    cx, cy = (line.box[0] + line.box[2]) / 2, (line.box[1] + line.box[3]) / 2
    return box[0] - tol <= cx <= box[2] + tol and box[1] - tol <= cy <= box[3] + tol


def is_header(box: Box, lines: List[TextLine], w: int, h: int) -> bool:
    """Tiêu đề: khối chữ căn giữa ở phía trên ảnh (kể cả dòng thứ hai của tiêu đề)."""
    x0, y0, x1, y1 = box
    cy = (y0 + y1) / 2
    if cy < h * HEADER_RATIO:
        return True
    centered = abs((x0 + x1) / 2 - w / 2) < w * 0.08
    has_text = any(center_in(t, box) for t in lines)
    return centered and has_text and cy < h * 0.27 and y1 - y0 < h * 0.09


def salient(img: np.ndarray, bg: np.ndarray, box: Box) -> bool:
    """Biểu tượng thật thì nổi bật hẳn khỏi nền; họa tiết trang trí mờ thì không."""
    x0, y0, x1, y1 = box
    diff = np.abs(img[y0:y1, x0:x1].astype(np.float32) - bg[y0:y1, None, :]).max(axis=2)
    return float(np.percentile(diff, 90)) > 70


def find_blocks(img: np.ndarray, with_text: bool = True) -> List[Block]:
    """Các khối sẽ lần lượt hiện ra, theo thứ tự đọc."""
    h, w = img.shape[:2]
    bg = background_rows(img)
    diff = np.abs(img.astype(np.float32) - bg[:, None, :]).max(axis=2)
    lines = read_text(img) if with_text else []

    candidates: List[Box] = []
    for box in components(diff > 12):
        x0, y0, x1, y1 = box
        if x0 <= 2 or y0 <= 2 or x1 >= w - 2 or y1 >= h - 2:
            continue  # chạm mép: nền trang trí, nhân vật... đứng yên
        if is_header(box, lines, w, h):
            continue
        area = (x1 - x0) * (y1 - y0)
        if area > w * h * MAX_BLOCK_RATIO * 0.5:
            kids = panel_children(img, box)
            if kids:
                candidates += kids
                continue
            if area > w * h * MAX_BLOCK_RATIO:
                continue  # hình minh họa lớn
        candidates.append(box)
    candidates = list(dict.fromkeys(candidates))

    # Khối chứa khối khác (do dò ở hai tầng): giữ các khối con, cộng thêm phần chữ
    # của khối cha chưa nằm trong khối con nào.
    leaves = []
    for box in candidates:
        kids = [k for k in candidates if contains(box, k)]
        if not kids:
            leaves.append(box)
            continue
        rest = [t.box for t in lines if center_in(t, box) and not any(center_in(t, k) for k in kids)]
        if rest:
            x0, y0, x1, y1 = union(rest)
            leaves.append((x0 - 10, y0 - 8, x1 + 10, y1 + 8))
    leaves = [b for b in dict.fromkeys(leaves) if not any(contains(o, b) for o in leaves)]

    kept = []
    for box in leaves:
        x0, y0, x1, y1 = box
        inside = sorted((t for t in lines if center_in(t, box)), key=lambda t: (round(t.box[1] / 25), t.box[0]))
        text = " ".join(t.text for t in inside)
        if sum(c.isalnum() for c in text) < 2:
            text = ""  # OCR đọc nhầm đường kẻ, dấu chấm thành chữ
        bw, bh = x1 - x0, y1 - y0
        if not text:
            # khối không có chữ: chỉ giữ biểu tượng gọn, nổi bật; đường kẻ, họa tiết,
            # hình minh họa thì đứng yên cùng nền
            if not (0.5 < bw / bh < 2 and bw * bh < w * h * 0.03 and salient(img, bg, box)):
                continue
        kept.append((box, text))
    return [Block(box, text, pop=not text) for box, text in merge_rows(kept)]


def merge_rows(items: List[Tuple[Box, str]]) -> List[Tuple[Box, str]]:
    """Gộp các khối cùng một hàng (chữ + dấu tích của một thẻ) để chúng hiện ra cùng lúc."""
    rows: List[List[Tuple[Box, str]]] = []
    for box, text in sorted(items, key=lambda it: it[0][1]):
        for row in rows:
            r = union([b for b, _ in row])
            overlap = min(r[3], box[3]) - max(r[1], box[1])
            if overlap >= 0.6 * min(r[3] - r[1], box[3] - box[1]):
                row.append((box, text))
                break
        else:
            rows.append([(box, text)])
    merged = []
    for row in rows:
        row.sort(key=lambda it: it[0][0])
        merged.append((union([b for b, _ in row]), " ".join(t for _, t in row if t)))
    return [(box, text) for box, text in sorted(merged, key=lambda it: (it[0][1], it[0][0]))]


def padded(box: Box, w: int = 1080, h: int = 1920, pad: int = 4) -> Box:
    """Khung nới rộng vài pixel để lấy trọn viền khử răng cưa của khối."""
    x0, y0, x1, y1 = box
    return max(x0 - pad, 0), max(y0 - pad, 2), min(x1 + pad, w), min(y1 + pad, h - 2)


def panels(img: np.ndarray, bg: np.ndarray) -> List[Tuple[Box, np.ndarray]]:
    """Các tấm nền lớn một màu đặt trên nền trang (tờ hợp đồng, màn hình điện thoại...)."""
    h, w = img.shape[:2]
    diff = np.abs(img.astype(np.float32) - bg[:, None, :]).max(axis=2)
    out = []
    for box in components(diff > 12):
        x0, y0, x1, y1 = box
        if (x1 - x0) * (y1 - y0) < w * h * 0.08:
            continue
        colors = img[y0:y1, x0:x1].reshape(-1, 3) // 8
        vals, counts = np.unique(colors, axis=0, return_counts=True)
        if counts.max() / colors.shape[0] >= 0.5:
            out.append((box, (vals[counts.argmax()] * 8 + 4).astype(np.float32)))
    return out


def erase(img: np.ndarray, boxes: List[Box]) -> np.ndarray:
    """Xóa các khối khỏi ảnh, tô lại bằng màu nền thật chứ không kéo màu từ khối bên cạnh.

    Khối nằm trong một tấm nền (tờ giấy, khung điện thoại) thì tô màu tấm nền đó; còn
    lại tô theo màu nền trang từng hàng (giữ nguyên dải chuyển màu).
    """
    out = img.copy()
    h, w = img.shape[:2]
    bg = background_rows(img)
    sheets = panels(img, bg)
    for box in boxes:
        x0, y0, x1, y1 = padded(box, w, h)
        inside = [
            (pb, color) for pb, color in sheets
            if pb[0] - 6 <= x0 and pb[1] - 6 <= y0 and x1 <= pb[2] + 6 and y1 <= pb[3] + 6
        ]
        if inside:
            _, color = min(inside, key=lambda it: (it[0][2] - it[0][0]) * (it[0][3] - it[0][1]))
            out[y0:y1, x0:x1] = color.astype(np.uint8)
        else:
            out[y0:y1, x0:x1] = bg[y0:y1, None, :].astype(np.uint8)
    return out


def debug_image(img: np.ndarray, blocks: List[Block], path: Path) -> None:
    """Vẽ khung các khối dò được lên ảnh để kiểm tra."""
    out = img.copy()
    for i, b in enumerate(blocks, 1):
        x0, y0, x1, y1 = b.box
        color = (229, 57, 53) if b.pop else (21, 94, 207)
        cv2.rectangle(out, (x0, y0), (x1, y1), color, 4)
        cv2.putText(out, str(i), (x0 + 6, y0 + 34), cv2.FONT_HERSHEY_SIMPLEX, 1.1, color, 3)
    Image.fromarray(out).save(path)
