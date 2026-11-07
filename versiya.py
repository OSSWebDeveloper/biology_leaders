# -*- coding: utf-8 -*-
"""Milliy Sertifikat loyihasi versiyasini yangilaydi — yagona joydan.

    py versiya.py                          hozirgi versiyani ko'rsatadi
    py versiya.py 1.2.0 "Qisqa izoh"       versiyani oshiradi
    py versiya.py 1.2.0 "Izoh" -b "Birinchi o'zgarish" -b "Ikkinchisi"
                                           + VERSIYALAR.md ga band-band tafsilot
    py versiya.py 1.2.0 "Izoh" --push      + GitHub'ga yuboradi (origin bo'lsa)

Nima qiladi:
  * `versiya.txt` ni yangilaydi — uni sayt o'qiydi va sahifa pastida
    ko'rsatadi;
  * `VERSIYALAR.md` ning tepasiga yangi versiyani sana bilan yozadi;
  * shu ikki faylni commit qiladi va `v1.2.0` degan teg qo'yadi;
  * `--push` berilsa — commit va tegni GitHub'ga yuboradi.

Boshqa o'zgargan fayllar commitga TUSHMAYDI (avval ularni o'zingiz commit
qiling) — `--hammasi` bayrog'i bilan majburlash mumkin.

Eski versiyani ishlatib ko'rish:  git switch --detach v1.0.0
Yana oxirgisiga qaytish:          git switch main
"""
import argparse
import datetime
import re
import subprocess
import sys
from pathlib import Path

ILDIZ = Path(__file__).resolve().parent
VERSIYA_FAYL = ILDIZ / 'versiya.txt'
TARIX_FAYL = ILDIZ / 'VERSIYALAR.md'
SARLAVHA = '# Versiyalar tarixi\n\n'
KOLIP = re.compile(r'^\d+\.\d+\.\d+$')


def hozirgi():
    if not VERSIYA_FAYL.exists():
        return '0.0.0'
    return VERSIYA_FAYL.read_text(encoding='utf-8-sig').strip()


def raqamlar(v):
    return tuple(int(q) for q in v.split('.'))


def git(*argv, tekshir=True):
    natija = subprocess.run(['git'] + list(argv), cwd=ILDIZ,
                            capture_output=True, text=True, encoding='utf-8')
    if tekshir and natija.returncode != 0:
        chiqish = (natija.stderr or natija.stdout or '').strip()
        raise SystemExit("XATO (git %s): %s" % (' '.join(argv), chiqish))
    return (natija.stdout or '').strip()


def tarixga_yoz(yangi, izoh, bandlar):
    """Yangi versiyani VERSIYALAR.md ning tepasiga qo'shadi."""
    sana = datetime.date.today().isoformat()
    yozuv = '## %s — %s\n\n%s\n\n' % (yangi, sana, izoh)
    if bandlar:
        yozuv += ''.join('- %s\n' % b for b in bandlar) + '\n'
    matn = TARIX_FAYL.read_text(encoding='utf-8-sig') if TARIX_FAYL.exists() else ''
    if matn.startswith(SARLAVHA):
        matn = matn[len(SARLAVHA):]
    TARIX_FAYL.write_text(SARLAVHA + yozuv + matn, encoding='utf-8')


def main(argv=None):
    p = argparse.ArgumentParser(description='Milliy Sertifikat loyihasi versiyasini yangilaydi.')
    p.add_argument('yangi', nargs='?', help='Yangi versiya, masalan 1.2.0')
    p.add_argument('izoh', nargs='?', help='Nima o\'zgardi (bir jumla)')
    p.add_argument('-b', '--band', action='append', default=[],
                   help='Tafsilot bandi (bir necha marta berish mumkin)')
    p.add_argument('--push', action='store_true', help='GitHub\'ga yuborilsin')
    p.add_argument('--hammasi', action='store_true',
                   help='Boshqa o\'zgarishlar ham shu commitga qo\'shilsin')
    a = p.parse_args(argv)

    eski = hozirgi()
    if not a.yangi:
        print('Hozirgi versiya: %s' % eski)
        return 0

    if not KOLIP.match(a.yangi):
        raise SystemExit('XATO: versiya "1.2.0" ko\'rinishida bo\'lsin.')
    if raqamlar(a.yangi) <= raqamlar(eski):
        raise SystemExit('XATO: %s -> %s. Yangi versiya kattaroq bo\'lishi kerak.'
                         % (eski, a.yangi))
    if not a.izoh:
        raise SystemExit('XATO: izoh yozing — u VERSIYALAR.md ga tushadi.')

    VERSIYA_FAYL.write_text(a.yangi, encoding='utf-8')
    tarixga_yoz(a.yangi, a.izoh, a.band)
    print('%s -> %s' % (eski, a.yangi))

    if a.hammasi:
        git('add', '-A')
    else:
        git('add', VERSIYA_FAYL.name, TARIX_FAYL.name)
        qolgan = git('diff', '--name-only')
        if qolgan:
            print('Eslatma: commitga tushmagan o\'zgarishlar bor:')
            for q in qolgan.splitlines():
                print('   ', q)

    xabar = 'Versiya %s — %s' % (a.yangi, a.izoh)
    if a.band:
        xabar += '\n\n' + '\n'.join('- %s' % b for b in a.band)
    git('commit', '-m', xabar)
    git('tag', '-a', 'v%s' % a.yangi, '-m', a.izoh)
    print('Commit va teg tayyor: v%s' % a.yangi)

    origin = 'origin' in git('remote').split()
    if a.push:
        if not origin:
            raise SystemExit('XATO: "origin" yo\'q — avval: git remote add origin <manzil>')
        git('push', 'origin', 'HEAD')
        git('push', 'origin', 'v%s' % a.yangi)
        print('GitHub\'ga yuborildi.')
    elif origin:
        print('Yuborish uchun:  git push origin HEAD && git push origin v%s' % a.yangi)
    return 0


if __name__ == '__main__':
    sys.exit(main())
