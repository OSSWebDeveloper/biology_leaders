# -*- coding: utf-8 -*-
"""Milliy sertifikat botini telefonga (Termux) ko'chirish uchun paket.

    python termux_paket.py              zip yasaydi; telefon USB'da bo'lsa Download'ga yuboradi
    python termux_paket.py --adbsiz     faqat zip (telefonga o'zingiz ko'chirasiz)

Paketga kiradi: kod, baza (ishlab turgan bo'lsa ham to'g'ri nusxa), media/, .env va
ngrok sozlamasi (authtoken). DIQQAT: zip ichida bot tokenlari bor — uni boshqalarga bermang.
Telefonga yuborishda .env da DEBUG=0 va BROWSER_STUDENTS=0 qilib qo'yiladi (sinov rejimi
haqiqiy serverda yoqilmasin); kompyuterdagi .env o'zgarmaydi.

Telefonda:
    termux-setup-storage                        (faqat birinchi marta)
    bash ~/storage/downloads/ornatish.sh
    bio start
"""
import argparse
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ILDIZ = Path(__file__).resolve().parent
DIST = ILDIZ / 'dist'
ZIP_NOM = 'biology_termux.zip'
KOD = ['accounts', 'config', 'exams', 'tgbot', 'templates', 'static', 'termux', 'manage.py',
       'versiya.txt', 'VERSIYALAR.md', 'README.md', 'TERMUX.md', 'requirements.txt']
NGROK_YML = Path(os.environ.get('LOCALAPPDATA', '')) / 'ngrok' / 'ngrok.yml'
ADB = [Path(r'D:\android\sdk\platform-tools\adb.exe')]
TELEFON_JOY = '/sdcard/Download/'


def lf(data, nom):
    return data.replace(b'\r\n', b'\n') if nom.endswith(('.sh', '.env')) else data


def telefon_env():
    t = (ILDIZ / '.env').read_text(encoding='utf-8-sig')
    for k, v in (('DEBUG', '0'), ('BROWSER_STUDENTS', '0')):
        t, n = re.subn(r'(?m)^%s=.*$' % k, '%s=%s' % (k, v), t)
        if not n:
            t = t.rstrip('\n') + '\n%s=%s\n' % (k, v)
    return t.replace('\r\n', '\n').encode('utf-8')


def paket():
    DIST.mkdir(exist_ok=True)
    chiqish = DIST / ZIP_NOM
    with zipfile.ZipFile(chiqish, 'w', zipfile.ZIP_DEFLATED) as z:
        for nom in KOD:
            p = ILDIZ / nom
            if not p.exists():
                continue
            for f in ([p] if p.is_file() else [x for x in p.rglob('*') if x.is_file()]):
                rel = f.relative_to(ILDIZ).as_posix()
                if '__pycache__' in rel or rel.endswith('.pyc'):
                    continue
                z.writestr(rel, lf(f.read_bytes(), rel))
        tmp = Path(tempfile.mkdtemp()) / 'db.sqlite3'
        src, dst = sqlite3.connect(ILDIZ / 'db.sqlite3'), sqlite3.connect(tmp)
        src.backup(dst)
        dst.close()
        src.close()
        z.write(tmp, 'db.sqlite3')
        shutil.rmtree(tmp.parent, ignore_errors=True)
        for f in (ILDIZ / 'media').rglob('*'):
            if f.is_file():
                z.write(f, f.relative_to(ILDIZ).as_posix())
        z.writestr('.env', telefon_env())
        if NGROK_YML.exists():
            z.writestr('ngrok.yml', lf(NGROK_YML.read_bytes(), '.sh'))
        else:
            print('Eslatma: ngrok.yml topilmadi (%s) — telefonda TUNNEL=cloudflare ishlating '
                  'yoki ngrok authtoken ni qo\'lda kiriting.' % NGROK_YML)
    (DIST / 'ornatish.sh').write_bytes(lf((ILDIZ / 'termux' / 'ornatish.sh').read_bytes(), '.sh'))
    print('Paket: %s (%.1f MB)' % (chiqish, chiqish.stat().st_size / 1e6))


def yubor():
    adb = next((str(p) for p in ADB if p.exists()), None) or shutil.which('adb')
    if not adb:
        print("adb topilmadi — dist/ dagi 2 faylni telefonning Download papkasiga o'zingiz ko'chiring.")
        return
    chiqish = subprocess.run([adb, 'devices'], capture_output=True, text=True).stdout
    qurilmalar = [q.split('\t')[0] for q in chiqish.splitlines()[1:] if q.endswith('\tdevice')]
    if not qurilmalar:
        print("Telefon USB'da ulanmagan (yoki «USB debugging» o'chiq) — dist/ dagi 2 faylni "
              "Download'ga o'zingiz ko'chiring.")
        return
    for f in (DIST / ZIP_NOM, DIST / 'ornatish.sh'):
        r = subprocess.run([adb, '-s', qurilmalar[0], 'push', str(f), TELEFON_JOY],
                           capture_output=True, text=True)
        if r.returncode:
            print('Yuborishda xato:', (r.stderr or r.stdout).strip())
            return
    print('Telefonga yuborildi:', TELEFON_JOY)


def main():
    a = argparse.ArgumentParser(description='Termux paketi')
    a.add_argument('--adbsiz', action='store_true')
    args = a.parse_args()
    paket()
    if not args.adbsiz:
        yubor()
    print()
    print("Telefonda (Termux):")
    print("  termux-setup-storage                      (faqat birinchi marta)")
    print("  bash ~/storage/downloads/ornatish.sh      (o'rnatish yoki yangilash)")
    print("  bio start")
    print("Avval kompyuterdagi server va botlarni to'xtating (token va domen bitta joyda ishlaydi).")
    return 0


if __name__ == '__main__':
    sys.exit(main())
