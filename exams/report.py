"""Natijalar hisoboti (PDF): o'quvchilar jadvali, Rasch diagrammasi va savollar bo'yicha o'zlashtirish.

PyMuPDF bilan chiziladi (boshqa kutubxona kerak emas). Shrift tizimdan olinadi: o'zbek kirill harflari
(ғ, қ, ҳ) PyMuPDF ichki shriftida yo'q.
"""
import math
import os

import pymupdf
from django.conf import settings
from django.utils import timezone

from .services import _is_blank, item_matrix, rasch_fit

WIDTH, HEIGHT = 595, 842  # A4
LEFT, RIGHT, TOP, BOTTOM = 40, 555, 46, 800
INK, MUTED, LINE = (0.1, 0.12, 0.16), (0.42, 0.45, 0.5), (0.82, 0.84, 0.87)
ACCENT, SOFT, ZEBRA = (0.16, 0.39, 0.82), (0.86, 0.91, 0.98), (0.965, 0.97, 0.98)
GOOD, MID, BAD = (0.18, 0.62, 0.36), (0.9, 0.62, 0.12), (0.84, 0.27, 0.25)

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


class _Canvas:
    """Sahifaga matn va shakl chizish. Matn sahifa yopilganda yoziladi (shakllar ustida turadi)."""

    def __init__(self, footer):
        self.doc = pymupdf.open()
        self.regular, self.bold = _fonts()
        self.footer = footer
        self.page = None
        self.new_page()

    def new_page(self):
        self._flush()
        self.page = self.doc.new_page(width=WIDTH, height=HEIGHT)
        self.writers = {}

    def _flush(self):
        if self.page is None:
            return
        self.text(LEFT, HEIGHT - 24, self.footer, 7.5, color=MUTED)
        self.text(RIGHT, HEIGHT - 24, str(self.page.number + 1), 7.5, color=MUTED, align='right')
        for color, writer in self.writers.items():
            writer.write_text(self.page, color=color)

    def clean(self, text, font):
        return ''.join(ch if font.has_glyph(ord(ch)) else '?' for ch in str(text))

    def width(self, text, size, bold=False):
        return (self.bold if bold else self.regular).text_length(text, fontsize=size)

    def fit(self, text, size, limit, bold=False):
        """Kenglikka sig'maydigan matnni «…» bilan qisqartiradi."""
        font = self.bold if bold else self.regular
        text = self.clean(text, font)
        if self.width(text, size, bold) <= limit:
            return text
        while text and self.width(text + '…', size, bold) > limit:
            text = text[:-1]
        return text.rstrip() + '…'

    def text(self, x, y, text, size=9.5, bold=False, color=INK, align='left'):
        font = self.bold if bold else self.regular
        text = self.clean(text, font)
        if not text:
            return
        if align != 'left':
            length = self.width(text, size, bold)
            x -= length if align == 'right' else length / 2
        writer = self.writers.setdefault(color, pymupdf.TextWriter(self.page.rect))
        writer.append((x, y), text, font=font, fontsize=size)

    def paragraph(self, x, y, text, size=9, limit=RIGHT - LEFT, color=MUTED, leading=1.4):
        """So'zma-so'z ko'chiriladigan matn; keyingi qatorning y ini qaytaradi."""
        line = ''
        for word in str(text).split():
            candidate = f'{line} {word}'.strip()
            if line and self.width(candidate, size) > limit:
                self.text(x, y, line, size, color=color)
                y += size * leading
                line = word
            else:
                line = candidate
        if line:
            self.text(x, y, line, size, color=color)
            y += size * leading
        return y

    def rect(self, x0, y0, x1, y1, fill, stroke=None):
        self.page.draw_rect(pymupdf.Rect(x0, y0, x1, y1), color=stroke, fill=fill, width=0.5 if stroke else 0)

    def line(self, x0, y0, x1, y1, color=LINE, width=0.6):
        self.page.draw_line((x0, y0), (x1, y1), color=color, width=width)

    def save(self):
        self._flush()
        self.page = None
        try:
            self.doc.subset_fonts()  # fayl kichrayadi; fontTools bo'lmasa shrift to'liq qoladi
        except Exception:
            pass
        return self.doc.tobytes(garbage=3, deflate=True)


def _number(value):
    return f'{value:g}'


COLUMNS = [  # (sarlavha, x, tekislash)
    ('№', LEFT + 8, 'left'), ('F.I.Sh.', LEFT + 38, 'left'), ("To'g'ri", 368, 'center'),
    ('Foiz', 424, 'center'), ('Ball', 476, 'center'), ('Daraja', 528, 'center'),
]
ROW = 16.5


def _table_header(canvas, y):
    canvas.rect(LEFT, y, RIGHT, y + ROW + 2, SOFT)
    for title, x, align in COLUMNS:
        canvas.text(x, y + 12.5, title, 9, bold=True, color=ACCENT, align=align)
    return y + ROW + 2


def _results_table(canvas, y, attempts):
    y = _table_header(canvas, y)
    for index, attempt in enumerate(attempts, 1):
        if y + ROW > BOTTOM:
            canvas.new_page()
            y = _table_header(canvas, TOP)
        if index % 2 == 0:
            canvas.rect(LEFT, y, RIGHT, y + ROW, ZEBRA)
        base = y + 11.8
        name_limit = COLUMNS[2][1] - 30 - COLUMNS[1][1]
        canvas.text(COLUMNS[0][1], base, str(index), 9, color=MUTED)
        canvas.text(COLUMNS[1][1], base, canvas.fit(attempt.student.display_name, 9.5, name_limit), 9.5)
        canvas.text(COLUMNS[2][1], base, f'{attempt.correct_items}/{attempt.total_items}', 9.5, align='center')
        canvas.text(COLUMNS[3][1], base, f'{_number(attempt.percent)}%', 9.5, color=MUTED, align='center')
        canvas.text(COLUMNS[4][1], base, _number(attempt.score), 9.5, bold=True, align='center')
        canvas.text(COLUMNS[5][1], base, attempt.grade or '—', 9.5, bold=bool(attempt.grade),
                    color=ACCENT if attempt.grade else MUTED, align='center')
        y += ROW
    canvas.line(LEFT, y, RIGHT, y)
    return y


MAP_LIMIT = 6.0  # logit: bundan chetdagi qiymatlar diagramma chetiga yopishtiriladi
MAP_BIN = 0.5


def _wright_map(canvas, y, fit, excluded):
    """Rasch diagrammasi: chapda o'quvchilar qobiliyati taqsimoti, o'ngda savollar qiyinligi, bitta shkalada."""
    thetas = [max(-MAP_LIMIT, min(MAP_LIMIT, t)) for t in fit['thetas']]
    items = {label: max(-MAP_LIMIT, min(MAP_LIMIT, b)) for label, b in fit['difficulties'].items()}
    low = math.floor(min(thetas + list(items.values())))
    high = math.ceil(max(thetas + list(items.values())))
    if high - low < 2:
        low, high = low - 1, high + 1
    bins = int((high - low) / MAP_BIN)
    top, height = y + 30, min(330.0, bins * 20.0)
    step = height / bins
    axis, scale_x = 300, LEFT + 18

    def bin_of(value):
        return min(bins - 1, max(0, int((value - low) / MAP_BIN)))

    persons = [0] * bins
    for theta in thetas:
        persons[bin_of(theta)] += 1
    labels = [[] for _ in range(bins)]
    for label, difficulty in sorted(items.items(), key=lambda kv: (len(kv[0]), kv[0])):
        labels[bin_of(difficulty)].append(label)

    canvas.text(axis - 10, y + 12, "O'quvchilar (qobiliyat)", 9.5, bold=True, align='right')
    canvas.text(axis + 10, y + 12, 'Savollar (qiyinlik)', 9.5, bold=True)
    canvas.text(scale_x, y + 12, 'logit', 7.5, color=MUTED, align='center')
    canvas.text(axis - 10, y + 23, 'kuchliroq  ↑', 7.5, color=MUTED, align='right')
    canvas.text(axis + 10, y + 23, '↑  qiyinroq', 7.5, color=MUTED)
    for logit in range(low, high + 1):
        line_y = top + height - (logit - low) / (high - low) * height
        canvas.line(LEFT + 30, line_y, RIGHT, line_y, LINE, 0.4)
        canvas.text(scale_x, line_y + 2.6, f'{logit:+d}' if logit else '0', 8, color=MUTED, align='center')
    canvas.line(axis, top, axis, top + height, INK, 0.9)

    most = max(persons)
    bar_room = axis - 10 - (LEFT + 62)
    for index in range(bins):
        bin_top = top + height - (index + 1) * step
        if persons[index]:
            length = max(3.0, bar_room * persons[index] / most)
            canvas.rect(axis - 4 - length, bin_top + 1.5, axis - 4, bin_top + step - 1.5, ACCENT)
            canvas.text(axis - 8 - length, bin_top + step / 2 + 2.8, str(persons[index]), 8, color=INK, align='right')
        if labels[index]:
            size, room = 8.5, RIGHT - axis - 12
            text = '   '.join(labels[index])
            while size > 5.5 and canvas.width(text, size, True) > room:
                size -= 0.5
            canvas.text(axis + 10, bin_top + step / 2 + size * 0.34, canvas.fit(text, size, room, True), size,
                        bold=True, color=BAD if low + (index + 0.5) * MAP_BIN > 0 else GOOD)
    y = top + height + 18
    y = canvas.paragraph(LEFT, y, "O'quvchi va savol bitta shkalada turadi. O'quvchi o'zi bilan bir balandlikdagi savolni "
                         "taxminan 50% ehtimol bilan yechadi: undan pastdagi savollar unga oson, yuqoridagilari qiyin. "
                         "Chapdagi ustun shu darajadagi o'quvchilar sonini ko'rsatadi; o'ngdagi raqamlar savol raqamlari "
                         "(qizil: o'rtachadan qiyin, yashil: oson).")
    if excluded:
        y = canvas.paragraph(LEFT, y + 2, 'Diagrammaga kirmagan savollar (hamma bir xil yechgan): ' + ', '.join(excluded) + '.')
    return y


def _item_bars(canvas, y, labels, shares):
    """Har bir savol (band) bo'yicha to'g'ri javob berganlar ulushi."""
    canvas.text(LEFT, y + 12, "Savollar bo'yicha to'g'ri javoblar ulushi", 11, bold=True)
    top, height = y + 34, 120.0
    left = LEFT + 30
    for percent in (0, 50, 100):
        line_y = top + height - height * percent / 100
        canvas.line(left, line_y, RIGHT, line_y, LINE, 0.4)
        canvas.text(left - 5, line_y + 2.6, f'{percent}%', 7.5, color=MUTED, align='right')
    slot = (RIGHT - left) / max(1, len(labels))
    bar = min(20.0, slot * 0.72)
    size = 7.5 if slot >= 12 else 6 if slot >= 9 else 5
    for index, (label, share) in enumerate(zip(labels, shares)):
        center = left + slot * (index + 0.5)
        bar_height = height * share
        color = BAD if share < 0.35 else MID if share < 0.7 else GOOD
        if bar_height > 0.3:
            canvas.rect(center - bar / 2, top + height - bar_height, center + bar / 2, top + height, color)
        if slot >= 9:
            canvas.text(center, top + height - bar_height - 3, str(round(share * 100)), size, color=MUTED, align='center')
        canvas.text(center, top + height + size + 3, label, size, bold=True, align='center')
    canvas.text(left, top + height + 28, "Qizil: 35% dan kam o'quvchi yechgan, sariq: 35–70%, yashil: 70% dan ko'p.", 8, color=MUTED)
    return top + height + 40


def results_pdf(exam, attempts):
    """Natijalar hisoboti. attempts: ko'rsatiladigan urinishlar (ball bo'yicha tartiblangan). PDF baytlari."""
    canvas = _Canvas(f'{exam.title} · natijalar')
    canvas.text(LEFT, TOP + 14, canvas.fit(exam.title, 17, RIGHT - LEFT, True), 17, bold=True)
    when = ''
    if exam.opens_at and exam.closes_at:
        when = f'{timezone.localtime(exam.opens_at):%d.%m.%Y %H:%M} – {timezone.localtime(exam.closes_at):%H:%M} · '
    canvas.text(LEFT, TOP + 32, f'{when}{exam.duration_min} daqiqa · natijalar', 10, color=MUTED)

    own = sum(1 for a in attempts if a.finished_at < a.deadline)
    average = sum(a.score for a in attempts) / len(attempts) if attempts else 0
    boxes = [('Qatnashdi', str(len(attempts))), ("O'zi topshirdi", str(own)),
             ('Vaqt tugab yakunlandi', str(len(attempts) - own)), ("O'rtacha ball", f'{average:.1f}')]
    box_width = (RIGHT - LEFT - 3 * 8) / 4
    for index, (caption, value) in enumerate(boxes):
        x = LEFT + index * (box_width + 8)
        canvas.rect(x, TOP + 46, x + box_width, TOP + 90, ZEBRA, LINE)
        canvas.text(x + 10, TOP + 68, value, 16, bold=True)
        canvas.text(x + 10, TOP + 82, caption, 8, color=MUTED)
    grades = {}
    for attempt in attempts:
        grades[attempt.grade or 'darajasiz'] = grades.get(attempt.grade or 'darajasiz', 0) + 1
    order = ['A+', 'A', 'B+', 'B', 'C+', 'C', 'darajasiz']
    canvas.text(LEFT, TOP + 108, 'Darajalar:  ' + '   '.join(f'{g}: {grades[g]}' for g in order if g in grades),
                9.5, color=INK)
    _results_table(canvas, TOP + 120, attempts)

    # Rasch va savollar tahlili: ball hisoblangan o'sha ma'lumot (hamma yakunlangan, bo'sh bo'lmagan urinishlar)
    finished = list(exam.attempts.filter(finished_at__isnull=False).prefetch_related('answers'))
    answered = [a for a in finished if not _is_blank(a)]
    labels, rows = item_matrix(exam, finished)
    fit = rasch_fit(exam, answered)
    canvas.new_page()
    canvas.text(LEFT, TOP + 14, 'Rasch modeli diagrammasi', 17, bold=True)
    y = TOP + 34
    if fit:
        excluded = [label for label in labels if label not in fit['difficulties']]
        y = canvas.paragraph(LEFT, y, f"Ball Rasch modeli bilan hisoblandi: {len(answered)} o'quvchining javoblaridan "
                             "savollar qiyinligi va o'quvchilar qobiliyati birga baholandi, so'ng 75 ballik shkalaga "
                             "o'tkazildi (T = 50 + 10·Z).", 9.5)
        y = _wright_map(canvas, y + 6, fit, excluded)
    else:
        y = canvas.paragraph(LEFT, y, "Bu testda Rasch modeli qo'llanmadi (javob bergan o'quvchilar "
                             f"{len(answered)} ta: kamida 20 ta bo'lishi kerak, yoki javoblar modelga yetarli ma'lumot "
                             "bermadi). Ball to'g'ri javoblar ulushidan hisoblandi: 75 × ulush.", 9.5)
    if labels and finished:
        shares = [sum(column) / len(finished) for column in zip(*rows)]
        if y + 200 > BOTTOM:
            canvas.new_page()
            y = TOP
        _item_bars(canvas, y + 14, labels, shares)
    return canvas.save()
