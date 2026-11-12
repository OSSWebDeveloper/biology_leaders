# -*- coding: utf-8 -*-
"""Telefonni USB bilan ulab, shu skriptni (yoki «Biology telefonga.bat» ni) ishga tushiring —
sayt va ikkala bot telefonda o'zi o'rnatiladi va ishga tushadi.

Qadamlar:
  1. adb orqali telefon topiladi (USB debugging yoqilgan bo'lishi kerak).
  2. Termux yo'q bo'lsa — rasmiy GitHub'dan yuklab o'rnatiladi.
  3. Termux uchun batareya cheklovi olib tashlanadi.
  4. Termux'da SSH yoqiladi (birinchi marta buyruq telefonga «terib» beriladi — ekran yoniq
     va qulfi ochiq bo'lsin), so'ng hamma ish USB ustidagi SSH orqali.
  5. Telefonda o'rnatilgan bo'lsa — uning bazasi kompyuterga zaxiralanadi (telefon_zaxira/).
  6. Paket (kod; birinchi marta baza + media + .env + ngrok) telefonga yuboriladi va o'rnatiladi.
  7. Kompyuterdagi «Biology» server/bot/ngrok to'xtatiladi, telefonda `bio start`.

    python telefonga.py
    python telefonga.py --baza-bilan     telefondagi bazani kompyuterdagisi bilan almashtirish
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import termux_paket

ILDIZ = Path(__file__).resolve().parent
ADB = next((str(p) for p in termux_paket.ADB if p.exists()), None) or shutil.which('adb')
SSH_PAPKA = Path(r'C:\Windows\System32\OpenSSH')
SSH = str(SSH_PAPKA / 'ssh.exe') if (SSH_PAPKA / 'ssh.exe').exists() else shutil.which('ssh')
SCP = str(SSH_PAPKA / 'scp.exe') if (SSH_PAPKA / 'scp.exe').exists() else shutil.which('scp')
SSH_KEYGEN = str(SSH_PAPKA / 'ssh-keygen.exe') if (SSH_PAPKA / 'ssh-keygen.exe').exists() else shutil.which('ssh-keygen')
KALIT = Path.home() / '.ssh' / 'biology_termux'
PORT = 8022
TERMUX = 'com.termux'
TERMUX_ENV = ('export PREFIX=/data/data/com.termux/files/usr; '
              'export PATH=$PREFIX/bin:$PATH; export LANG=en_US.UTF-8; ')
ZAXIRA = ILDIZ / 'telefon_zaxira'

seriya = None
yangi_termux = False  # shu safar o'rnatildimi (birinchi ochilishi uzoqroq)


# ───────────────────────── yordamchilar ─────────────────────────

def sarlavha(matn):
    print('\n=== %s ===' % matn, flush=True)


def xato(matn):
    print('\nXATO: ' + matn, flush=True)
    sys.exit(1)


def adb(*argv, tekshir=False, timeout=120):
    buyruq = [ADB] + (['-s', seriya] if seriya else []) + list(argv)
    r = subprocess.run(buyruq, capture_output=True, text=True, encoding='utf-8', errors='replace',
                       timeout=timeout)
    if tekshir and r.returncode:
        xato('adb %s: %s' % (' '.join(argv), (r.stderr or r.stdout).strip()))
    return (r.stdout or '').strip()


def ssh_argv():
    return ['-p', str(PORT), '-i', str(KALIT), '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=NUL', '-o', 'LogLevel=ERROR', '-o', 'BatchMode=yes',
            '-o', 'ConnectTimeout=8', '-o', 'ServerAliveInterval=30']


def ssh(buyruq, korsat=False, timeout=None):
    """Telefondagi Termux'da buyruq. korsat=True — chiqishi shu oynada jonli ko'rinadi."""
    argv = [SSH] + ssh_argv() + ['termux@127.0.0.1', TERMUX_ENV + buyruq]
    if korsat:
        return subprocess.run(argv, timeout=timeout).returncode, ''
    r = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8', errors='replace',
                       timeout=timeout or 60)
    return r.returncode, (r.stdout or '').strip()


def scp(manba, manzil, yuklash=True):
    yol = ['termux@127.0.0.1:' + manzil]
    argv = [SCP, '-P', str(PORT)] + ssh_argv()[2:] + ([str(manba)] + yol if yuklash else yol + [str(manba)])
    r = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode:
        xato('nusxalash: ' + (r.stderr or r.stdout).strip())


def termux_versiyasi():
    m = re.search(r'versionName=(\S+)', adb('shell', 'dumpsys', 'package', TERMUX))
    return m.group(1) if m else None


def raqamlar(v):
    return tuple(int(x) for x in re.findall(r'\d+', v)[:3])


# ───────────────────────── qadamlar ─────────────────────────

def telefonni_top():
    global seriya
    sarlavha('1. Telefon')
    if not ADB:
        xato("adb topilmadi (D:\\android\\sdk\\platform-tools\\adb.exe).")
    adb('start-server')
    for i in range(60):
        qatorlar = [q.split('\t') for q in adb('devices').splitlines()[1:] if '\t' in q]
        tayyor = [s for s, h in qatorlar if h == 'device']
        if tayyor:
            seriya = tayyor[0]
            break
        if i == 0:
            if any(h == 'unauthorized' for _, h in qatorlar):
                print("Telefon ekranida «Разрешить отладку по USB?» oynasi chiqdi — «Разрешить» ni bosing.")
            else:
                print("Telefon topilmadi. USB kabelni ulang va telefonda «Для разработчиков → "
                      "Отладка по USB» ni yoqing. Kutyapman…")
        time.sleep(2)
    else:
        xato('telefon 2 daqiqa ichida ulanmadi.')
    model = adb('shell', 'getprop', 'ro.product.model')
    android = adb('shell', 'getprop', 'ro.build.version.release')
    print('Ulandi: %s (Android %s)' % (model, android))


def termuxni_tekshir():
    sarlavha('2. Termux')
    v = termux_versiyasi()
    if v and raqamlar(v) < (0, 118):
        xato("Telefondagi Termux eski (%s) — Play Market versiyasi ishlamaydi. Uni telefondan "
             "o'chiring (Termux ichidagi ma'lumot ham o'chadi) va shu skriptni qayta ishga tushiring — "
             "yangisi o'zi o'rnatiladi." % v)
    if v:
        print('Termux bor: ' + v)
        return
    abi = adb('shell', 'getprop', 'ro.product.cpu.abi') or 'arm64-v8a'
    print('Termux yo\'q — rasmiy GitHub\'dan yuklanmoqda (%s)…' % abi)
    so_rov = urllib.request.Request('https://api.github.com/repos/termux/termux-app/releases/latest',
                                    headers={'User-Agent': 'biology-setup'})
    reliz = json.load(urllib.request.urlopen(so_rov, timeout=30))
    apk = next((a for a in reliz['assets'] if a['name'].endswith('_%s.apk' % abi)), None) or \
        next(a for a in reliz['assets'] if a['name'].endswith('universal.apk'))
    fayl = ILDIZ / 'dist' / apk['name']
    fayl.parent.mkdir(exist_ok=True)
    if not fayl.exists():
        urllib.request.urlretrieve(apk['browser_download_url'], fayl)
    print('O\'rnatilmoqda: ' + apk['name'])
    natija = adb('install', '-r', str(fayl), timeout=300)
    if 'Success' not in natija:
        xato('Termux o\'rnatilmadi: ' + natija)
    print('Termux o\'rnatildi: ' + (termux_versiyasi() or '?'))
    global yangi_termux
    yangi_termux = True


def batareya():
    sarlavha('3. Batareya cheklovi')
    adb('shell', 'dumpsys', 'deviceidle', 'whitelist', '+' + TERMUX)
    adb('shell', 'cmd', 'appops', 'set', TERMUX, 'RUN_ANY_IN_BACKGROUND', 'allow')
    adb('shell', 'cmd', 'appops', 'set', TERMUX, 'RUN_IN_BACKGROUND', 'allow')
    print('Termux uchun batareya tejash o\'chirildi.')


def ssh_ulanish():
    sarlavha('4. Termux bilan ulanish (SSH, USB orqali)')
    if not (SSH and SCP and SSH_KEYGEN):
        xato("Windows OpenSSH topilmadi (Параметры → Приложения → Доп. компоненты → «Клиент OpenSSH»).")
    if not KALIT.exists():
        KALIT.parent.mkdir(exist_ok=True)
        subprocess.run([SSH_KEYGEN, '-t', 'ed25519', '-N', '', '-C', '', '-q', '-f', str(KALIT)], check=True)
    adb('forward', 'tcp:%d' % PORT, 'tcp:%d' % PORT, tekshir=True)
    if ssh('echo ok')[1] == 'ok':
        print('Ulandi.')
        return

    ochiq = KALIT.with_suffix('.pub').read_text().split()
    # Android 13+: bildirishnoma so'rovi oynasi terilayotgan buyruqni to'sib qo'ymasin
    adb('shell', 'pm', 'grant', TERMUX, 'android.permission.POST_NOTIFICATIONS')
    print("Termux'da SSH yoqilmoqda: telefon ekrani YONIQ va QULFI OCHIQ bo'lsin, "
          "ekranga tegmang — buyruq o'zi teriladi.")
    adb('shell', 'input', 'keyevent', 'KEYCODE_WAKEUP')
    adb('shell', 'am', 'start', '-n', TERMUX + '/.app.TermuxActivity')
    # Termux birinchi ochilganda o'z tizimini o'rnatadi (~30 s)
    time.sleep(40 if yangi_termux else 6)
    buyruq = ('pkg install -y openssh;mkdir -p ~/.ssh;echo %s %s >>~/.ssh/authorized_keys;'
              'chmod 600 ~/.ssh/authorized_keys;sshd;echo SSH-TAYYOR' % (ochiq[0], ochiq[1]))
    terish = buyruq.replace(' ', '%s')
    for urinish in range(3):
        adb('shell', "input text '%s'" % terish)
        adb('shell', 'input', 'keyevent', 'KEYCODE_ENTER')
        print('Kutilmoqda (openssh o\'rnatilyapti, 1-5 daqiqa)…', flush=True)
        for _ in range(100):
            time.sleep(3)
            if ssh('echo ok')[1] == 'ok':
                print('Ulandi.')
                return
        print("Hali ulanmadi — Termux ekranida xato bormi? Qayta urinilmoqda…")
        adb('shell', 'am', 'start', '-n', TERMUX + '/.app.TermuxActivity')
        time.sleep(5)
    xato("SSH yoqilmadi. Termux'ni qo'lda ochib yozing:  pkg install openssh && sshd   "
         "so'ng skriptni qayta ishga tushiring.")


def telefon_zaxirasi():
    """Telefonda baza bo'lsa — nusxasini kompyuterga oladi. True = telefonda o'rnatilgan."""
    kod, chiqish = ssh('test -f ~/milliy_sertifikat/db.sqlite3 && echo BOR')
    if chiqish != 'BOR':
        return False
    sarlavha('5. Telefondagi baza kompyuterga zaxiralanmoqda')
    # Ishlab turgan bazadan ham to'g'ri nusxa — SQLite backup API
    kod, _ = ssh("cd ~ && python -c 'import sqlite3; s=sqlite3.connect(\"milliy_sertifikat/db.sqlite3\"); "
                 "d=sqlite3.connect(\"zaxira_tmp.sqlite3\"); s.backup(d); d.close(); s.close()'")
    if kod:
        xato("telefondagi bazaning nusxasi olinmadi.")
    ZAXIRA.mkdir(exist_ok=True)
    fayl = ZAXIRA / ('telefon_db_%s.sqlite3' % datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
    scp(fayl, 'zaxira_tmp.sqlite3', yuklash=False)
    ssh('rm -f ~/zaxira_tmp.sqlite3')
    print('Saqlandi: %s (%.1f MB)' % (fayl, fayl.stat().st_size / 1e6))
    return True


def kompyuterni_toxtat():
    sarlavha("Kompyuterdagi server, botlar va ngrok to'xtatilmoqda")
    for nom in ('Biology Django*', 'Biology Bot*', 'Biology Oqituvchi*', 'Biology Ngrok*', 'Biology Server*'):
        subprocess.run(['taskkill', '/fi', 'WINDOWTITLE eq ' + nom, '/t', '/f'], capture_output=True)
    ps = ("Get-NetTCPConnection -State Listen -LocalPort 8123 -ErrorAction SilentlyContinue | "
          "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }; "
          "Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'ngrok.exe' -and $_.CommandLine -match 'http 8123') "
          "-or ($_.CommandLine -match 'manage.py (runbot|runteacherbot)' -and $_.CommandLine -match 'python') } | "
          "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
    subprocess.run(['powershell', '-NoProfile', '-Command', ps], capture_output=True)
    print("To'xtatildi (bitta bot tokeni va ngrok domeni bir vaqtda faqat bitta joyda ishlaydi).")


def main():
    a = argparse.ArgumentParser(description='Botni telefonga o\'rnatish va ishga tushirish')
    a.add_argument('--baza-bilan', action='store_true',
                   help="telefondagi bazani kompyuterdagisi bilan almashtirish (avval zaxiralanadi)")
    args = a.parse_args()
    os.chdir(ILDIZ)

    telefonni_top()
    termuxni_tekshir()
    batareya()
    ssh_ulanish()
    ornatilgan = telefon_zaxirasi()

    # Birinchi o'rnatishda (yoki bazani almashtirishda) kompyuter avval to'xtaydi —
    # shunda telefonga ketadigan baza nusxasi oxirgi holatda bo'ladi
    toxtatildi = False
    if not ornatilgan or args.baza_bilan:
        kompyuterni_toxtat()
        toxtatildi = True

    sarlavha('6. Paket tayyorlanmoqda va telefonga yuborilmoqda')
    termux_paket.paket()
    scp(termux_paket.DIST / termux_paket.ZIP_NOM, 'biology_termux.zip')
    scp(termux_paket.DIST / 'ornatish.sh', 'ornatish.sh')
    print('Yuborildi.')

    sarlavha("7. Telefonda o'rnatilmoqda" + (' (birinchi marta 20-40 daqiqa)' if not ornatilgan else ''))
    ssh('command -v bio >/dev/null && bio stop')
    kod, _ = ssh('bash ~/ornatish.sh ~/biology_termux.zip' + (' --baza-bilan' if args.baza_bilan else ''),
                 korsat=True)
    if kod:
        xato("telefonda o'rnatish to'xtadi (yuqoridagi xabarni o'qing). Kompyuterdagi bot "
             + ("to'xtatilgan — kerak bo'lsa BiologyServerRun.bat bilan qayta yoqing." if toxtatildi
                else "ishlashda davom etyapti."))
    ssh('rm -f ~/biology_termux.zip')

    if not toxtatildi:
        kompyuterni_toxtat()

    sarlavha('8. Telefonda ishga tushirilmoqda')
    kod, _ = ssh('bio start', korsat=True)
    if kod:
        xato("ishga tushmadi. Telefonda Termux'ni ochib `bio log tunnel` yoki `bio log bot` ni ko'ring.")
    print('\nTAYYOR. Kabelni ajratsangiz bo\'ladi — sayt va botlar telefonda ishlayapti.')
    print("Telefon qayta yoqilsa: Termux'ni ochib  bio start  deb yozing (yoki shu bat'ni qayta bosing).")
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('\nTo\'xtatildi.')
        sys.exit(1)
