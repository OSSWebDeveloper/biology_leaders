"""PDF testni savollarga bo'lib, har bir savolni rasm qilib kesadi.

Formulalar PDF matn qatlamida buzilib chiqadi, shu sabab savol asl ko'rinishida rasm bo'lib
saqlanadi. Raqamlar ketma-ketlik bo'yicha izlanadi (1, 2, 3 ...), shuning uchun formula ichidagi
tasodifiy sonlar savol boshi deb olinmaydi. Sahifa sarlavhasi, pastki yozuvlar va takrorlanuvchi
suv belgisi matnlari kesimga ta'sir qilmaydi.
"""
import io
import re
from collections import Counter
from dataclasses import dataclass, field

import pymupdf as fitz
from PIL import Image

DPI = 170
BLOCK_SIZE = 3  # moslashtirish bloki: 33, 34, 35
_NUMBER = re.compile(r'^(\d{1,2})(?:[.)]|-savol:?|-misol\.?)(?!\d)')
_MATCH_BLOCK = re.compile(r'^\W*Topshiriqlar\b')
_KEY_PAGE = re.compile(r'^(JAVOBLAR|KALITLAR)\b')
_OPEN_PART = re.compile(r'^a\)')
_CHOICE = re.compile(r'^A\)')


class PdfImportError(Exception):
    pass


@dataclass
class Slice:
    number: int
    kind: str
    png: bytes
    extra_numbers: list = field(default_factory=list)  # bir rasmni bo'lishadigan savollar (33-35)


@dataclass
class ImportResult:
    slices: list
    mcq_key: dict


@dataclass
class _Start:
    line: object
    is_block: bool = False
    numbers: list = field(default_factory=list)


@dataclass
class _Line:
    page: int
    x0: float
    x1: float
    y0: float
    y1: float
    text: str


def _page_lines(page):
    lines = []
    for block in page.get_text('dict')['blocks']:
        if block['type'] != 0:
            continue
        for line in block['lines']:
            if line['dir'] != (1.0, 0.0):
                continue
            text = ''.join(span['text'] for span in line['spans']).strip()
            if text:
                lines.append(_Line(page.number, line['bbox'][0], line['bbox'][2], line['bbox'][1], line['bbox'][3], text))
    lines.sort(key=lambda l: (round(l.y0 / 3), l.x0))
    return lines


def _signature(text):
    return re.sub(r'\d+', '#', text)


def _analyze(doc):
    """Har sahifa uchun tana qatorlari va yuqori/pastki chegaralarni topadi."""
    all_lines = [_page_lines(page) for page in doc]
    seen = Counter()
    for lines in all_lines:
        for sig in {(_signature(l.text), round(l.y0 / 4)) for l in lines}:
            seen[sig] += 1
    threshold = max(3, len(doc) * 0.4)
    bodies, bounds = [], []
    for page, lines in zip(doc, all_lines):
        height = page.rect.height
        counts = Counter(l.text for l in lines)
        top, bottom, body = 0.0, height, []
        for line in lines:
            if counts[line.text] >= 5 and len(line.text) >= 6:  # takrorlanuvchi suv belgisi
                continue
            # '5-savol:' har sahifada bir joyda tursa ham sarlavha emas
            repeated = (seen[(_signature(line.text), round(line.y0 / 4))] >= threshold
                        and not _NUMBER.match(line.text))
            if repeated and line.y1 < height * 0.15:
                top = max(top, line.y1)
            elif (repeated or line.text.isdigit()) and line.y0 > height * 0.85:
                bottom = min(bottom, line.y0)
            else:
                body.append(line)
        # chegaradan chiqqan qatorlarni olib tashlaymiz
        bodies.append([l for l in body if l.y0 >= top - 1 and l.y1 <= bottom + 1])
        bounds.append((top, bottom))
    return bodies, bounds


def _is_faint(drawing):
    """Och rangli yoki shaffof chizma: suv belgisi, kontent hisoblanmaydi."""
    if min(drawing.get('fill_opacity') or 1, drawing.get('stroke_opacity') or 1) < 0.5:
        return True
    colors = [c for c in (drawing.get('fill'), drawing.get('color')) if c]
    return bool(colors) and all(min(c) > 0.75 for c in colors)


def _content_extent(page, y0, y1, lines):
    """[y0, y1] oralig'ida kontent qayerda tugaydi: (pastki, o'ng chegara). Bo'sh joy kesiladi."""
    bottom, right = y0, 0.0
    for line in lines:
        if line.page == page.number and y0 - 1 <= line.y0 < y1:
            bottom = max(bottom, line.y1)
            right = max(right, line.x1)
    page_area = page.rect.width * page.rect.height
    for info in page.get_image_info():
        x0, top, x1, end = info['bbox']
        if (x1 - x0) * (end - top) > page_area * 0.25:  # katta fon/suv belgisi
            continue
        if top < y1 and end > y0:
            bottom = max(bottom, min(end, y1))
            right = max(right, x1)
    for drawing in page.get_drawings():
        rect = drawing['rect']
        if rect.height > page.rect.height * 0.5 or _is_faint(drawing):
            continue
        # sahifa pastidagi ajratuvchi chiziq kontent emas
        if rect.height < 3 and rect.width > page.rect.width * 0.6 and rect.y0 > page.rect.height * 0.85:
            continue
        if rect.y0 < y1 and rect.y1 > y0:
            bottom = max(bottom, min(rect.y1, y1))
            right = max(right, rect.x1)
    return min(bottom + 6, y1), min(right + 6, page.rect.width)


def _render(doc, segments):
    """Bo'laklarni (sahifa, y0, y1) rasmga aylantirib, bittaga tikadi."""
    zoom = DPI / 72
    images = []
    for page_no, x0, x1, y0, y1 in segments:
        if y1 - y0 < 4:
            continue
        clip = fitz.Rect(x0, y0, x1, y1)
        pix = doc[page_no].get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip, alpha=False)
        images.append(Image.frombytes('RGB', (pix.width, pix.height), pix.samples))
    if not images:
        raise PdfImportError("Savol kesimi bo'sh chiqdi")
    width = max(i.width for i in images)
    canvas = Image.new('RGB', (width, sum(i.height for i in images)), 'white')
    y = 0
    for image in images:
        canvas.paste(image, (0, y))
        y += image.height
    buf = io.BytesIO()
    canvas.quantize(colors=96, dither=Image.Dither.NONE).save(buf, 'PNG', optimize=True)
    return buf.getvalue()


def parse_mcq_key(lines):
    """Kalit jadvali matnidan {raqam: harf} ni oladi: qatorlar '1', 'C', '8', 'D', ..."""
    key = {}
    for current, following in zip(lines, lines[1:]):
        if current.isdigit() and 1 <= int(current) <= 60 and re.fullmatch('[A-F]', following):
            key[int(current)] = following
    return key


def slice_pdf(data):
    """PDF baytlaridan savol kesimlari va (bo'lsa) yopiq savollar kalitini qaytaradi."""
    try:
        doc = fitz.open(stream=data, filetype='pdf')
    except Exception as exc:
        raise PdfImportError("PDF faylni ochib bo'lmadi") from exc
    if doc.is_encrypted:
        raise PdfImportError('PDF parol bilan himoyalangan')
    bodies, bounds = _analyze(doc)
    flat = [line for body in bodies for line in body]
    if not flat:
        raise PdfImportError("PDF da matn qatlami yo'q (skaner qilingan). Savollarni qo'lda kiriting.")
    # muqova sahifasi chetroqdan boshlanishi mumkin, shuning uchun u hisobga olinmaydi
    left = min(l.x0 for l in (flat if len(doc) < 3 else [l for l in flat if l.page > 0]))
    margin = max(0, left - 5)

    # 1) Savol boshlarini ketma-ketlik bo'yicha topamiz
    starts = []
    expected = 1
    key_line = None
    for line in flat:
        if _KEY_PAGE.match(line.text):
            key_line = line
            break
        block = starts[-1] if starts and starts[-1].is_block and len(starts[-1].numbers) < BLOCK_SIZE else None
        if _MATCH_BLOCK.match(line.text) and expected > 1 and block is None:
            starts.append(_Start(line, is_block=True))
            continue
        match = _NUMBER.match(line.text)
        if not match or int(match.group(1)) != expected:
            continue
        if block is not None:  # blok ichidagi raqam jadval ustunida bo'lishi mumkin
            block.numbers.append(expected)
            expected += 1
        elif line.x0 <= left + 12:
            starts.append(_Start(line, numbers=[expected]))
            expected += 1
    starts = [s for s in starts if s.numbers]
    if not starts:
        raise PdfImportError("PDF dan savol raqamlari topilmadi. Savollarni qo'lda kiriting.")

    # 2) Kesib chiqamiz
    last_page = key_line.page - 1 if key_line else len(doc) - 1
    slices = []
    for index, start in enumerate(starts):
        line = start.line
        next_line = starts[index + 1].line if index + 1 < len(starts) else None
        stop_page = next_line.page if next_line else last_page
        segments = []
        for page_no in range(line.page, stop_page + 1):
            top, bottom = bounds[page_no]
            y0 = max(line.y0 - 5 if page_no == line.page else top + 2, top)
            y1 = next_line.y0 - 5 if next_line and page_no == next_line.page else bottom - 2
            if y1 <= y0:
                continue
            end, right = _content_extent(doc[page_no], y0, y1, flat)
            if end - y0 >= 8:
                segments.append((page_no, margin, right, y0, end))
        scope = [l.text for l in flat if _in_segments(l, segments)]
        kind = 'matching' if start.is_block else _detect_kind(scope)
        slices.append(Slice(start.numbers[0], kind, _render(doc, segments), start.numbers[1:]))

    key = parse_mcq_key([l.text for l in flat if l.page >= key_line.page]) if key_line else {}
    doc.close()
    return ImportResult(slices, key)


def _in_segments(line, segments):
    return any(line.page == s[0] and s[3] - 1 <= line.y0 < s[4] for s in segments)


def _detect_kind(lines):
    if any(_OPEN_PART.match(t) for t in lines) and not any(_CHOICE.match(t) for t in lines):
        return 'open'
    return 'mcq'
