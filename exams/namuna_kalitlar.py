"""Namuna testlar: manba PDF va yozma javoblar kaliti (PDF kalit jadvalidan ko'chirilgan).

Yopiq savollar kaliti PDF ichidan avtomatik o'qiladi. Yozma javoblar formula bo'lgani uchun qo'lda.
key=None: PDF da kalit yo'q, test qoralama bo'lib qoladi.
"""

NAMUNALAR = [
    {
        'file': 'MS_04.10.2026_2-smena.pdf',
        'title': 'Matematika — 04.10.2026, 2-smena',
        'key': {
            36: ('57', '6'), 37: ('4π/3', '2'), 38: ('-1', '-9'), 39: ('3', '19'), 40: ('9/8', '343/6'),
            41: ('2+2√6', '4√10'), 42: ('17', '1'), 43: ('10/17', '765/56'), 44: ('468√3', '4√7'),
            45: ('18', '2√3+1'),
        },
    },
    {
        'file': 'MS_04.10.2026_1-smena.pdf',
        'title': 'Matematika — 04.10.2026, 1-smena',
        'key': {
            36: ('4', '6√3'), 37: ('8', '8π'), 38: ('3,5', '5'), 39: ('12', '2/3'), 40: ('-3/8', '16/3'),
            41: ('2√5', '20'), 42: ('168', '1,5'), 43: ('8', '70√3'), 44: ('9', '36π'), 45: ('20', '54000'),
        },
    },
    {
        'file': 'MS_03.10.2026_1-smena.pdf',
        'title': 'Matematika — 03.10.2026, 1-smena',
        'key': {
            36: ('1', '4'), 37: ('2π/3', '5'), 38: ('1/3', '3√3/2'), 39: ('1/2', '-1/16'), 40: ('2/5', '27/4'),
            41: ('10√3', '√21/3'), 42: ('5', '325/24'), 43: ('3', '45√3'),
            # 44 b: PDF kalitida 2√2, lekin shartda "R ning h ga nisbati" so'ralgan: 2/(2√2) = √2/2
            44: ('8π', '√2/2'),
            45: ('9/40', '9/4'),
        },
    },
    {
        'file': '2-OKTYABR 2-SMENA SAVOLLARI.pdf',
        'title': 'Matematika — 02.10.2026, 2-smena (kalitsiz)',
        'key': None,
    },
]
