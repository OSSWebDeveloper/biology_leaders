"""Javobni tekshirish va baholash.

grade_attempt javoblarni tekshiradi va to'g'ri bandlar ulushini hisoblaydi. Yakuniy ball keyin
services.rasch_rescore da Rasch modeli bilan, shu testni yechgan hamma bilan birga hisoblanadi.
"""
import math
import re

SCALE_MAX = 75
# (chegara, daraja): rasmiy jadval, ball 75 lik shkalada
# A+ — 70 dan yuqori (70 ning o'zi A)
GRADES = [(65, 'A'), (60, 'B+'), (55, 'B'), (50, 'C+'), (46, 'C')]
MAX_INPUT_LEN = 64
_TOLERANCE = 1e-6
_ALTERNATIVES = re.compile(r'\s+or\s+|\|', re.IGNORECASE)


def grade_for(score):
    if score > 70:
        return 'A+'
    for bound, grade in GRADES:
        if score >= bound:
            return grade
    return ''


class _ParseError(Exception):
    pass


_TOKEN = re.compile(r'\d+(?:\.\d+)?|sqrt|pi|[+\-*/^()√π]')


def _tokenize(text):
    pos, tokens = 0, []
    while pos < len(text):
        match = _TOKEN.match(text, pos)
        if not match:
            raise _ParseError
        tokens.append(match.group())
        pos = match.end()
    return tokens


class _Parser:
    """Kichik ifoda tahlilchisi: 2√5, 16/3, 8π, 2√3+1, -1/16, (1+√5)/2. eval ishlatilmaydi."""

    def __init__(self, tokens):
        self.tokens, self.i = tokens, 0

    def peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def take(self):
        self.i += 1
        return self.tokens[self.i - 1]

    def parse(self):
        value = self.expr()
        if self.peek() is not None:
            raise _ParseError
        return value

    def expr(self):
        value = self.term()
        while self.peek() in ('+', '-'):
            value = value + self.term() if self.take() == '+' else value - self.term()
        return value

    def term(self):
        value = self.unary()
        while True:
            tok = self.peek()
            if tok in ('*', '/'):
                self.take()
                right = self.unary()
                if tok == '/' and right == 0:
                    raise _ParseError
                value = value * right if tok == '*' else value / right
            elif tok is not None and (tok[0].isdigit() or tok in ('√', 'π', 'pi', 'sqrt', '(')):
                value *= self.unary()  # yashirin ko'paytirish: 2√5, 3π, 2(1+√3)
            else:
                return value

    def unary(self):
        if self.peek() == '-':
            self.take()
            return -self.unary()
        if self.peek() == '+':
            self.take()
            return self.unary()
        return self.power()

    def power(self):
        base = self.atom()
        if self.peek() == '^':
            self.take()
            return base ** self.unary()
        return base

    def atom(self):
        tok = self.peek()
        if tok is None:
            raise _ParseError
        self.take()
        if tok in ('√', 'sqrt'):
            inner = self.atom()
            if inner < 0:
                raise _ParseError
            return math.sqrt(inner)
        if tok in ('π', 'pi'):
            return math.pi
        if tok == '(':
            value = self.expr()
            if self.peek() != ')':
                raise _ParseError
            self.take()
            return value
        if tok[0].isdigit():
            return float(tok)
        raise _ParseError


_APOSTROPHES = "'‘’ʻʼ`"
# Birlik harf bilan boshlanadi: «3,5» dagi «.5» birlik emas (aks holda 3,5 = 3 bo'lib qoladi)
_UNIT = re.compile(r'[a-z%' + _APOSTROPHES + r'°][a-z%' + _APOSTROPHES + r'°.]*\d?$')


def _clean(text):
    text = str(text).strip().lower()
    for src, dst in (('−', '-'), ('–', '-'), ('—', '-'), ('×', '*'), ('·', '*'), ('⋅', '*'),
                     (',', '.'), ('÷', '/'), ('²', '^2'), ('³', '^3')):
        text = text.replace(src, dst)
    return re.sub(r'\s+', '', text)


def _split_unit(cleaned):
    """(son qismi, birlik): '20sm' -> ('20', 'sm'), '2n' -> ('2', 'n')."""
    if cleaned.endswith(('pi', 'sqrt')):
        return cleaned, ''
    match = _UNIT.search(cleaned)
    if not match:
        return cleaned, ''
    return cleaned[:match.start()], match.group()


def parse_value(text):
    """Javobni songa aylantiradi; ifoda emas bo'lsa None."""
    text = _clean(text)
    if not text or len(text) > MAX_INPUT_LEN:
        return None
    if ':' in text:
        return None  # nisbat (9:3:3:1, 1:2:1) matn sifatida solishtiriladi
    text, _ = _split_unit(text)
    try:
        value = _Parser(_tokenize(text)).parse()
    except (_ParseError, OverflowError, ZeroDivisionError, ValueError, TypeError, RecursionError):
        return None
    return value if isinstance(value, float) and math.isfinite(value) else None


def answers_match(given, key):
    """O'quvchi javobi kalitga mosmi. Kalitda to'g'ri javoblar soni cheklanmagan: 'or' yoki '|' bilan."""
    if not str(given).strip():
        return False
    given_value = parse_value(given)
    for option in _ALTERNATIVES.split(str(key)):
        if not option.strip():
            continue
        key_value = parse_value(option)
        if given_value is not None and key_value is not None:
            # Birlik yozilmasa ham bo'ladi (20 = 20 sm), lekin har xil birlik har xil javob: 2c ≠ 2n
            given_unit, key_unit = _split_unit(_clean(given))[1], _split_unit(_clean(option))[1]
            if given_unit and key_unit and given_unit != key_unit:
                continue
            if abs(given_value - key_value) <= _TOLERANCE * max(1.0, abs(key_value)):
                return True
        elif _clean(given) == _clean(option):
            return True
    return False


def grade_attempt(attempt):
    """Urinishni qayta hisoblaydi (kalit o'zgarganda ham chaqiriladi)."""
    exam = attempt.exam
    answers = {a.question_id: a for a in attempt.answers.all()}
    earned = possible = 0.0
    correct_items = total_items = 0
    changed = []
    for question in exam.questions.all():
        if not question.has_key():
            continue
        weight = exam.weight_for(question.kind)
        items = question.max_items
        possible += weight * items
        total_items += items
        answer = answers.get(question.pk)
        if not answer:
            continue
        if question.kind == question.Kind.OPEN:
            answer.correct_a = answers_match(answer.value_a, question.answer_a)
            answer.correct_b = question.two_parts and answers_match(answer.value_b, question.answer_b)
        else:
            answer.correct_a = bool(answer.choice) and answer.choice == question.correct
            answer.correct_b = False
        hits = int(answer.correct_a) + int(answer.correct_b)
        correct_items += hits
        earned += weight * hits
        changed.append(answer)
    if changed:
        type(changed[0]).objects.bulk_update(changed, ['correct_a', 'correct_b'])
    attempt.correct_items = correct_items
    attempt.total_items = total_items
    attempt.percent = round(100 * earned / possible, 1) if possible else 0
    attempt.score = round(SCALE_MAX * earned / possible, 1) if possible else 0
    attempt.grade = grade_for(attempt.score)
    attempt.save(update_fields=['correct_items', 'total_items', 'percent', 'score', 'grade'])
    return attempt
