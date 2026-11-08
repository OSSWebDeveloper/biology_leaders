"""Rasch (1PL) modeli: savol qiyinligi va o'quvchi qobiliyati shu testni yechganlarning javoblaridan birga baholanadi.

Usul: JML (joint maximum likelihood). Hamma o'quvchi bir xil yechgan savol (hamma to'g'ri yoki hamma xato)
qiyinlik haqida ma'lumot bermaydi va hisobga olinmaydi. Hamma savolni to'g'ri yoki hammasini xato yechgan
o'quvchining bahosi cheksizga ketmasligi uchun xom ball 0,3 ga suriladi.

Ball: qobiliyat standartlashtiriladi va T = 50 + 10·Z ga o'tkaziladi, 0–75 oralig'ida cheklanadi.
"""
import math

SCALE_MAX = 75
EXTREME_SHIFT = 0.3
MAX_STEP = 1.0


def _p(theta, b):
    x = theta - b
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def _person_theta(row, b, theta=0.0):
    """Savol qiyinliklari ma'lum bo'lganda bitta o'quvchi qobiliyati (Nyuton usuli)."""
    length = len(b)
    raw = min(max(sum(row), EXTREME_SHIFT), length - EXTREME_SHIFT)
    for _ in range(100):
        probs = [_p(theta, bi) for bi in b]
        info = sum(p * (1 - p) for p in probs)
        if info < 1e-12:
            break
        step = max(-MAX_STEP, min(MAX_STEP, (raw - sum(probs)) / info))
        theta += step
        if abs(step) < 1e-6:
            break
    return theta


def estimate(responses, iterations=300):
    """responses: o'quvchilar ro'yxati, har biri 0/1 qatori. Qaytaradi: (thetalar, qiyinliklar yoki None)."""
    if not responses or not responses[0]:
        return [0.0] * len(responses), None
    columns = list(zip(*responses))
    n = len(responses)
    kept = [i for i, col in enumerate(columns) if 0 < sum(col) < n]
    if not kept:
        return [0.0] * n, None
    matrix = [[row[i] for i in kept] for row in responses]
    length = len(kept)
    raw = [sum(row) for row in matrix]
    # Qiyinlikni faqat chegaraviy bo'lmagan o'quvchilar baholaydi
    middle = [k for k, r in enumerate(raw) if 0 < r < length]
    if not middle:
        return [0.0] * n, None

    sums = [sum(matrix[k][i] for k in middle) for i in range(length)]
    b = [math.log((len(middle) - s + EXTREME_SHIFT) / (s + EXTREME_SHIFT)) for s in sums]
    theta = {k: math.log(raw[k] / (length - raw[k])) for k in middle}
    for _ in range(iterations):
        biggest = 0.0
        for i in range(length):
            probs = [_p(theta[k], b[i]) for k in middle]
            info = sum(p * (1 - p) for p in probs)
            if info < 1e-12:
                continue
            step = max(-MAX_STEP, min(MAX_STEP, (sum(probs) - sums[i]) / info))
            b[i] += step
            biggest = max(biggest, abs(step))
        mean = sum(b) / length
        b = [bi - mean for bi in b]
        for k in middle:
            new = _person_theta(matrix[k], b, theta[k])
            biggest = max(biggest, abs(new - theta[k]))
            theta[k] = new
        if biggest < 1e-5:
            break
    if length > 1:  # JML siljishini kamaytirish
        b = [bi * (length - 1) / length for bi in b]
    thetas = [_person_theta(row, b) for row in matrix]
    return thetas, b


def t_scores(thetas):
    """Qobiliyatni T = 50 + 10·Z ballga o'tkazadi (0–75)."""
    if not thetas:
        return []
    mean = sum(thetas) / len(thetas)
    sd = math.sqrt(sum((t - mean) ** 2 for t in thetas) / len(thetas))
    scores = []
    for t in thetas:
        z = (t - mean) / sd if sd > 1e-9 else 0.0
        scores.append(round(min(SCALE_MAX, max(0.0, 50 + 10 * z)), 1))
    return scores
