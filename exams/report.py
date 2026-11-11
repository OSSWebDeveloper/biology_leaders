"""Natijalar hisoboti (PDF): baho taqsimoti, savollar bo'yicha to'g'ri javoblar soni, savollar qiyinligi
(Rasch) va o'quvchilar jadvali.

PyMuPDF bilan chiziladi (boshqa kutubxona kerak emas). Shrift tizimdan olinadi: o'zbek kirill harflari
(ғ, қ, ҳ) PyMuPDF ichki shriftida yo'q.
"""
import math
import os
import re

import pymupdf
from django.conf import settings
from django.utils import timezone

from .services import _is_blank, item_matrix, rasch_fit

PORTRAIT, LANDSCAPE = (595, 842), (842, 595)  # A4
BLACK, MUTED, GRID = (0, 0, 0), (0.4, 0.4, 0.4), (0.82, 0.82, 0.82)
ORANGE, BLUE = (1.0, 0.71, 0.38), (0.33, 0.55, 1.0)
NO_GRADE = 'NG'
GRADE_COLORS = {  # diagramma ustunlari; jadval qatori shu rangning och ko'rinishi
    'A+': (0.0, 0.39, 0.0), 'A': (0.24, 0.70, 0.44), 'B+': (0.12, 0.56, 1.0), 'B': (0.39, 0.58, 0.93),
    'C+': (1.0, 0.84, 0.0), 'C': (1.0, 0.98, 0.80), NO_GRADE: (0.86, 0.08, 0.24),
}

FONT_FILES = [  # (oddiy, qalin): birinchi topilgani ishlatiladi
    (settings.BASE_DIR / 'static/fonts/DejaVuSans.ttf', settings.BASE_DIR / 'static/fonts/DejaVuSans-Bold.ttf'),
    (r'C:\Windows\Fonts\arial.ttf', r'C:\Windows\Fonts\arialbd.ttf'),
    ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'),
    ('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
     '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf'),
]


def _fonts():
    for regular, bold in FONT_FILES:
        if os.path.exists(regular):
            return (pymupdf.Font(fontfile=str(regular)),
                    pymupdf.Font(fontfile=str(bold if os.path.exists(bold) else regular)))
    fallback = pymupdf.Font('cjk')
    return fallback, fallback


def _tint(color, strength=0.3):
    """Rangning och ko'rinishi (jadval qatori foni uchun)."""
    return tuple(1 - (1 - channel) * strength for channel in color)


class _Canvas:
    """Sahifaga matn va shakl chizish. Matn sahifa yopilganda yoziladi (shakllar ustida turadi)."""

    def __init__(self):
        self.doc = pymupdf.open()
        self.regular, self.bold = _fonts()
        self.page = None

    def new_page(self, size=PORTRAIT):
        self._flush()
        self.page = self.doc.new_page(width=size[0], height=size[1])
        self.shape = self.page.new_shape()  # shakllar sahifa yopilganda bir yo'la yoziladi: bittalab yozish sekin
        self.writers = {}

    def _flush(self):
        if self.page is not None:
            self.shape.commit()
            for color, writer in self.writers.items():
                writer.write_text(self.page, color=color)

    def clean(self, text, font):
        return ''.join(ch if font.has_glyph(ord(ch)) else '?' for ch in str(text))

    def width(self, text, size, bold=False):
        return (self.bold if bold else self.regular).text_length(text, fontsize=size)

    def fit(self, text, size, limit, bold=False):
        """Kenglikka sig'maydigan matnni «…» bilan qisqartiradi."""
        text = self.clean(text, self.bold if bold else self.regular)
        if self.width(text, size, bold) <= limit:
            return text
        while text and self.width(text + '…', size, bold) > limit:
            text = text[:-1]
        return text.rstrip() + '…'

    def text(self, x, y, text, size=10, bold=False, color=BLACK, align='left', underline=False):
        font = self.bold if bold else self.regular
        text = self.clean(text, font)
        if not text:
            return
        length = self.width(text, size, bold)
        if align != 'left':
            x -= length if align == 'right' else length / 2
        writer = self.writers.setdefault(color, pymupdf.TextWriter(self.page.rect))
        writer.append((x, y), text, font=font, fontsize=size)
        if underline:
            self.line(x, y + size * 0.16, x + length, y + size * 0.16, color, max(0.7, size * 0.07))

    def rect(self, x0, y0, x1, y1, fill, stroke=None, width=0.8):
        self.shape.draw_rect(pymupdf.Rect(x0, y0, x1, y1))
        self.shape.finish(color=stroke, fill=fill, width=width if stroke else 0)

    def line(self, x0, y0, x1, y1, color=BLACK, width=0.8, dashes=None):
        self.shape.draw_line((x0, y0), (x1, y1))
        self.shape.finish(color=color, width=width, dashes=dashes)

    def save(self):
        self._flush()
        self.page = None
        try:
            self.doc.subset_fonts()  # fayl kichrayadi; fontTools bo'lmasa shrift to'liq qoladi
        except Exception:
            pass
        return self.doc.tobytes(garbage=3, deflate=True)


def _grade(attempt):
    return attempt.grade or NO_GRADE


def _cover(canvas, exam, attempts):
    """1-sahifa: test ma'lumoti va baho taqsimoti."""
    canvas.new_page(PORTRAIT)
    canvas.text(297, 72, canvas.fit(exam.title, 19, 500, True), 19, bold=True, align='center')
    closed = timezone.localtime(exam.closes_at) if exam.closes_at else timezone.localtime()
    for index, line in enumerate((f'Test kodi: {exam.access_code}', f'Yakunlangan sana: {closed:%d/%m/%Y}',
                                  f'Qatnashchilar soni: {len(attempts)}')):
        canvas.text(50, 108 + index * 14, line, 11)
    canvas.text(50, 180, 'Baho taqsimoti', 15, bold=True, underline=True)
    counts = {grade: 0 for grade in GRADE_COLORS}
    for attempt in attempts:
        counts[_grade(attempt)] += 1
    base, height, slot, bar = 385.0, 160.0, 54.0, 31.0
    most = max(counts.values()) or 1
    for index, (grade, color) in enumerate(GRADE_COLORS.items()):
        center = 90 + slot * index
        size = max(2.5, height * counts[grade] / most) if counts[grade] else 0
        if size:
            canvas.rect(center - bar / 2, base - size, center + bar / 2, base, color, BLACK)
        canvas.text(center, base - size - 5, str(counts[grade]), 9.5, align='center')
        canvas.text(center, base + 13, grade, 9.5, bold=True, align='center')


def _split_label(label):
    """'36a' -> ('36', '-a'); '7' -> ('7', '')."""
    match = re.fullmatch(r'(\d+)([ab]?)', label)
    return (match.group(1), '-' + match.group(2) if match.group(2) else '') if match else (label, '')


def _item_axis(canvas, labels, left, right, y):
    """Savol raqamlari (ikki bandli savolda ostida -a/-b); har bir ustun markazini qaytaradi."""
    slot = (right - left) / max(1, len(labels))
    size = 7 if slot >= 12 else 6 if slot >= 9 else 5
    centers = []
    for index, label in enumerate(labels):
        center = left + slot * (index + 0.5)
        number, part = _split_label(label)
        canvas.text(center, y + size + 2, number, size, align='center')
        if part:
            canvas.text(center, y + 2 * size + 4, part, size, align='center')
        centers.append(center)
    return centers, slot, size


def _correct_counts(canvas, labels, counts):
    """2-sahifa: har bir savolga nechta o'quvchi to'g'ri javob bergani."""
    canvas.new_page(LANDSCAPE)
    canvas.text(421, 62, "Har bir savol bo'yicha to'g'ri javoblar soni", 16, bold=True, align='center')
    left, right, base, top = 70.0, 800.0, 470.0, 130.0
    centers, slot, size = _item_axis(canvas, labels, left, right, base)
    most = max(counts) if counts and max(counts) else 1
    bar = min(26.0, slot * 0.72)
    for center, count in zip(centers, counts):
        height = (base - top) * count / most
        if height > 0.4:
            canvas.rect(center - bar / 2, base - height, center + bar / 2, base, ORANGE, BLACK)
        canvas.text(center, base - height - 3, str(count), min(7, size + 0.5), align='center')
    canvas.line(left, base, right, base, BLACK, 1.2)


def _difficulty_chart(canvas, labels, fit, answered_count):
    """3-sahifa: Rasch modeli bo'yicha savollar qiyinligi. Namunadagidek musbat: oson, manfiy: qiyin."""
    canvas.new_page(LANDSCAPE)
    canvas.text(421, 62, 'Savollar qiyinchilik darajasi (manfiy/musbat)', 16, bold=True, align='center')
    if not fit:
        canvas.text(421, 250, "Bu testda Rasch modeli qo'llanmadi.", 12, align='center')
        canvas.text(421, 270, f"Javob bergan o'quvchilar {answered_count} ta: kamida 20 ta bo'lishi kerak, yoki javoblar "
                    "modelga yetarli ma'lumot bermadi.", 10, color=MUTED, align='center')
        canvas.text(421, 286, "Ball to'g'ri javoblar ulushidan hisoblandi: 75 × ulush.", 10, color=MUTED, align='center')
        return
    values = {label: -difficulty for label, difficulty in fit['difficulties'].items()}
    limit = max(0.5, math.ceil(max(abs(v) for v in values.values()) * 10) / 10)
    left, right, top, bottom = 78.0, 800.0, 135.0, 455.0
    middle, half = (top + bottom) / 2, (bottom - top) / 2
    centers, slot, size = _item_axis(canvas, labels, left, right, bottom)
    bar = min(26.0, slot * 0.72)
    for center in centers:
        canvas.line(center - slot / 2, top, center - slot / 2, bottom, GRID, 0.5, '[2 2] 0')
    canvas.line(left, top, left, bottom, BLACK, 0.8)
    for value, y in ((limit, top + 12), (0, middle), (-limit, bottom - 12)):
        canvas.text(left - 6, y + 3, f'{value:g}', 8, align='right')
    for center, label in zip(centers, labels):
        if label not in values:
            canvas.text(center, middle - 3, '×', size, color=MUTED, align='center')  # hamma bir xil yechgan
            continue
        value = values[label]
        end = middle - (half - 12) * value / limit  # chetda qiymat yozuvi uchun joy qoladi
        if abs(end - middle) > 0.4:
            canvas.rect(center - bar / 2, min(end, middle), center + bar / 2, max(end, middle), BLUE, BLACK)
        canvas.text(center, end - 3 if value >= 0 else end + size + 1, f'{value:.2f}', max(4.5, size - 1), align='center')
    canvas.line(left, middle, right, middle, BLACK, 1.2)
    canvas.text((left + right) / 2, bottom + 34, 'Savollar', 9.5, align='center')
    note = "Rasch modeli (logit). Musbat: savol oson, manfiy: savol qiyin."
    if any(label not in values for label in labels):
        note += " «×»: hamma bir xil yechgan savol, bahosi yo'q."
    canvas.text((left + right) / 2, bottom + 52, note, 8.5, color=MUTED, align='center')


COLUMNS = [('#', 30), ("O'quvchi", 185), ('T/J', 50), ('Z', 54), ('Ball', 62), ('Foiz', 62), ('Daraja', 54)]
TABLE_LEFT = (PORTRAIT[0] - sum(width for _, width in COLUMNS)) / 2
ROW_HEIGHT = 21.0


def _table_row(canvas, y, cells, fill, bold=False):
    right = TABLE_LEFT + sum(width for _, width in COLUMNS)
    canvas.rect(TABLE_LEFT, y, right, y + ROW_HEIGHT, fill, BLACK, 0.6)
    x = TABLE_LEFT
    for (_, width), cell in zip(COLUMNS, cells):
        if x > TABLE_LEFT:
            canvas.line(x, y, x, y + ROW_HEIGHT, BLACK, 0.6)
        canvas.text(x + width / 2, y + ROW_HEIGHT / 2 + 3.4, canvas.fit(cell, 9.5, width - 6, bold), 9.5,
                    bold=bold, align='center')
        x += width


def _results_table(canvas, attempts, z_scores):
    """4-sahifadan: o'quvchilar jadvali, qator rangi darajaga qarab."""
    canvas.new_page(PORTRAIT)
    canvas.text(50, 64, "O'quvchilar natijalari", 15, bold=True, underline=True)
    y = 86.0
    header = [title for title, _ in COLUMNS]
    _table_row(canvas, y, header, (1, 1, 1), bold=True)
    y += ROW_HEIGHT
    for index, attempt in enumerate(attempts, 1):
        if y + ROW_HEIGHT > PORTRAIT[1] - 46:
            canvas.new_page(PORTRAIT)
            y = 46.0
            _table_row(canvas, y, header, (1, 1, 1), bold=True)
            y += ROW_HEIGHT
        z = z_scores.get(attempt.pk)
        _table_row(canvas, y, [
            str(index), attempt.student.display_name, str(attempt.correct_items),
            f'{z:.2f}' if z is not None else '—', f'{attempt.score:.2f}', f'{attempt.percent:.1f}%', _grade(attempt),
        ], _tint(GRADE_COLORS[_grade(attempt)]))
        y += ROW_HEIGHT
    if settings.BOT_USERNAME:
        if y + 30 > PORTRAIT[1] - 30:
            canvas.new_page(PORTRAIT)
            y = 40.0
        canvas.text(TABLE_LEFT + sum(width for _, width in COLUMNS), y + 22,
                    f'@{settings.BOT_USERNAME} tizimi orqali tayyorlangan.', 8.5, color=MUTED, align='right')


def results_pdf(exam, attempts):
    """Natijalar hisoboti. attempts: ko'rsatiladigan urinishlar (ball bo'yicha tartiblangan). PDF baytlari."""
    # Tahlil ball hisoblangan ma'lumotning o'zidan: hamma yakunlangan urinishlar, Rasch uchun bo'sh bo'lmaganlari
    finished = list(exam.attempts.filter(finished_at__isnull=False).prefetch_related('answers'))
    answered = [a for a in finished if not _is_blank(a)]
    labels, rows = item_matrix(exam, finished)
    fit = rasch_fit(exam, answered)
    z_scores = {}
    if fit:
        thetas = fit['thetas']
        mean = sum(thetas) / len(thetas)
        deviation = math.sqrt(sum((t - mean) ** 2 for t in thetas) / len(thetas))
        if deviation > 1e-9:
            z_scores = {a.pk: (t - mean) / deviation for a, t in zip(answered, thetas)}

    canvas = _Canvas()
    _cover(canvas, exam, attempts)
    _correct_counts(canvas, labels, [sum(column) for column in zip(*rows)] if rows else [0] * len(labels))
    _difficulty_chart(canvas, labels, fit, len(answered))
    _results_table(canvas, attempts, z_scores)
    return canvas.save()
