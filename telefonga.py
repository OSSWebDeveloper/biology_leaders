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
import urllib.error
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
    # stderr ham qaytariladi: masalan Xiaomi'da `input` ruxsat xatosi shu yerga chiqadi
    return ((r.stdout or '') + (r.stderr or '')).strip()


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
                print("Telefon ekranida «Allow USB debugging?» oynasi chiqdi — «Always allow from this "
                      "computer» ni belgilab, «Allow» ni bosing.")
            else:
                print("Telefon topilmadi. USB kabelni ulang va telefonda «Settings → System → "
                      "Developer options → USB debugging» ni yoqing. Kutyapman…")
        time.sleep(2)
    else:
        xato('telefon 2 daqiqa ichida ulanmadi.')
    model = adb('shell', 'getprop', 'ro.product.model')
    android = adb('shell', 'getprop', 'ro.build.version.release')
    print('Ulandi: %s (Android %s)' % (model, android))


def play_termux(versiya):
    """Google Play'dagi Termux boshqa ombor (termux.net) va boshqa kalit bilan ishlaydi —
    unda python-pymupdf yo'q, rasmiy omborga ham ulanib bo'lmaydi."""
    if 'googleplay' in versiya.lower():
        return True
    return 'com.android.vending' in adb('shell', 'pm', 'list', 'packages', '-i', TERMUX)


def play_termuxni_almashtir(versiya):
    # Termux qo'shimchalari (API, Widget, Boot…) ham bir xil imzoda bo'lishi shart — ular ham almashadi
    paketlar = sorted({q.split(':', 1)[1].split()[0] for q in
                       adb('shell', 'pm', 'list', 'packages', 'com.termux').splitlines() if ':' in q})
    print("Telefondagi Termux — Google Play versiyasi (%s)." % versiya)
    print("U boshqa paket omboridan foydalanadi va unda bot uchun kerakli PDF kutubxonasi (pymupdf) yo'q.")
    print("Uni rasmiy GitHub versiyasiga almashtirish kerak. Bunda Termux ICHIDAGI barcha fayllar o'chadi")
    print("(telefondagi rasm, kontakt va boshqa ilovalarga tegilmaydi).")
    print("O'chiriladi: " + ', '.join(paketlar))
    try:
        javob = input("\nAlmashtirilsinmi? Ha uchun Enter, bekor qilish uchun N yozib Enter: ").strip().lower()
    except EOFError:
        javob = 'n'
    if javob in ('n', "yo'q", 'yoq', 'no'):
        xato("bekor qilindi. Play Market'dagi Termux bilan bot ishlamaydi.")
    for p in paketlar:
        natija = adb('uninstall', p, timeout=120)
        print('  %s: %s' % (p, 'o\'chirildi' if 'Success' in natija else natija))
    if termux_versiyasi():
        xato("Termux o'chmadi. Telefonda Settings → Apps → Termux → Uninstall qiling va bat'ni qayta bosing.")


def termux_apk(abi):
    """Rasmiy Termux APK (GitHub). api.github.com ishlatilmaydi — u soatiga 60 so'rov bilan
    cheklangan; oxirgi versiya sahifa yo'naltirishidan olinadi, fayl to'g'ridan-to'g'ri yuklanadi."""
    dist = ILDIZ / 'dist'
    dist.mkdir(exist_ok=True)
    tayyor = sorted(dist.glob('termux-app_*_%s.apk' % abi)) or sorted(dist.glob('termux-app_*_universal.apk'))
    if tayyor:
        return tayyor[-1]
    teg = 'v0.118.3'
    try:
        javob = urllib.request.urlopen(urllib.request.Request(
            'https://github.com/termux/termux-app/releases/latest', headers={'User-Agent': 'biology-setup'}),
            timeout=30)
        m = re.search(r'/releases/tag/(v[\w.\-]+)$', javob.geturl())
        if m:
            teg = m.group(1)
    except Exception:
        pass
    for tur in (abi, 'universal'):
        nom = 'termux-app_%s+github-debug_%s.apk' % (teg, tur)
        url = 'https://github.com/termux/termux-app/releases/download/%s/%s' % (teg, nom)
        fayl = dist / nom
        try:
            urllib.request.urlretrieve(url, fayl)
            return fayl
        except Exception as e:
            fayl.unlink(missing_ok=True)
            oxirgi = e
    xato("Termux yuklab olinmadi (%s). Internetni tekshirib, bat'ni qayta bosing." % oxirgi)


def termuxni_tekshir():
    sarlavha('2. Termux')
    v = termux_versiyasi()
    if v and raqamlar(v) < (0, 118):
        xato("Telefondagi Termux eski (%s) — Play Market versiyasi ishlamaydi. Uni telefondan "
             "o'chiring (Termux ichidagi ma'lumot ham o'chadi) va shu skriptni qayta ishga tushiring — "
             "yangisi o'zi o'rnatiladi." % v)
    if v and play_termux(v):
        play_termuxni_almashtir(v)
        v = None
    if v:
        print('Termux bor: ' + v)
        return
    abi =adb('shell', 'getprop', 'ro.product.cpu.abi') or 'arm64-v8a'
    print('Termux yo\'q — rasmiy GitHub\'dan yuklanmoqda (%s)…' % abi)
    fayl = termux_apk(abi)
    print('O\'rnatilmoqda: ' + fayl.name)
    natija = adb('install', '-r', str(fayl), timeout=300)
    if 'Success' not in natija:
        if 'USER_RESTRICTED' in natija:
            xato("Telefon USB orqali ilova o'rnatishga ruxsat bermadi. Xiaomi'da: Developer options → "
                 "«Install via USB» ni yoqing (yoki ekrandagi so'rovda «Install» ni bosing) va qayta bosing.")
        xato('Termux o\'rnatilmadi: ' + natija)
    print('Termux o\'rnatildi: ' + (termux_versiyasi() or '?'))
    global yangi_termux
    yangi_termux = True


def widget_ornat():
    """Termux:Widget — bosh ekranda «Biology ishga tushirish» yorlig'i uchun. Majburiy emas."""
    if 'package:com.termux.widget' in adb('shell', 'pm', 'list', 'packages', 'com.termux.widget'):
        return
    nom = 'termux-widget-app_v0.15.0+github.debug.apk'
    fayl = ILDIZ / 'dist' / nom
    try:
        if not fayl.exists():
            urllib.request.urlretrieve('https://github.com/termux/termux-widget/releases/download/v0.15.0/' + nom, fayl)
    except Exception as e:
        print('Termux:Widget yuklanmadi (%s) — yorliqsiz davom etiladi.' % e)
        return
    print("Termux:Widget o'rnatilmoqda (telefonda «Install» chiqsa, bosing)…", flush=True)
    natija = adb('install', '-r', str(fayl), timeout=300)
    print("Termux:Widget o'rnatildi." if 'Success' in natija else 'Termux:Widget o\'rnatilmadi: ' + natija)


def batareya():
    sarlavha('3. Batareya cheklovi')
    adb('shell', 'dumpsys', 'deviceidle', 'whitelist', '+' + TERMUX)
    adb('shell', 'cmd', 'appops', 'set', TERMUX, 'RUN_ANY_IN_BACKGROUND', 'allow')
    adb('shell', 'cmd', 'appops', 'set', TERMUX, 'RUN_IN_BACKGROUND', 'allow')
    print('Termux uchun batareya tejash o\'chirildi.')


def termux_oldindami():
    oyna = re.search(r'mCurrentFocus=.*', adb('shell', 'dumpsys', 'window', 'windows'))
    return bool(oyna and 'com.termux/' in oyna.group(0))


def termuxni_old_ga():
    """Termux'ni ekranga chiqaradi va haqiqatan oldinda ekanini tekshiradi."""
    for i in range(60):
        if i % 5 == 0:
            adb('shell', 'input', 'keyevent', 'KEYCODE_WAKEUP')
            adb('shell', 'am', 'start', '-n', TERMUX + '/.app.TermuxActivity')
        time.sleep(2)
        if termux_oldindami():
            return
        if i == 5:
            print("Termux ekranga chiqmayapti — telefon qulfini oching va Termux ilovasini o'zingiz oching.",
                  flush=True)
    xato("Termux ekranga chiqmadi. Telefonda Termux'ni ochib, bat'ni qayta bosing.")


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
    termuxni_old_ga()
    # Termux birinchi ochilganda o'z tizimini o'rnatadi (~30 s)
    time.sleep(40 if yangi_termux else 6)
    # yes| — paket yangilanishida chiqadigan savollarga (masalan sozlama fayli) o'zi javob beradi
    buyruq = ('yes|pkg install -y openssh;mkdir -p ~/.ssh;echo %s %s >>~/.ssh/authorized_keys;'
              'chmod 600 ~/.ssh/authorized_keys;sshd;echo SSH-TAYYOR' % (ochiq[0], ochiq[1]))
    terish = buyruq.replace(' ', '%s')
    for urinish in range(3):
        # Matn faqat Termux ekranda turganda teriladi — aks holda brauzer/qidiruvga tushib ketadi
        termuxni_old_ga()
        natija = adb('shell', "input text '%s'" % terish)
        if 'INJECT_EVENTS' in natija or 'SecurityException' in natija:
            xato("Telefon kompyuterga matn terishga ruxsat bermadi. Xiaomi'da: Developer options → "
                 "«USB debugging (Security settings)» ni yoqing va qayta bosing.")
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
    # adb.exe ham 8123 ni tinglaydi (telefonga USB yo'naltirish) — uni o'ldirmaslik kerak, aks holda
    # SSH ulanishi ham uziladi
    ps = ("Get-NetTCPConnection -State Listen -LocalPort 8123 -ErrorAction SilentlyContinue | "
          "Where-Object { (Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue).Name -ne 'adb' } | "
          "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }; "
          "Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'ngrok.exe' -and $_.CommandLine -match 'http 8123') "
          "-or ($_.CommandLine -match 'manage.py (runbot|runteacherbot)' -and $_.CommandLine -match 'python') } | "
          "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
    subprocess.run(['powershell', '-NoProfile', '-Command', ps], capture_output=True)
    print("To'xtatildi (bitta bot tokeni va ngrok domeni bir vaqtda faqat bitta joyda ishlaydi).")


NGROK_DOMEN = 'https://roughy-outgoing-iguana.ngrok-free.app'
NGROK_EXE = (r'D:\asosiy\ngrok.exe' if os.path.exists(r'D:\asosiy\ngrok.exe') else shutil.which('ngrok'))
SERVER_PORT = 8123


def tunnel_bormi():
    try:
        d = json.load(urllib.request.urlopen('http://127.0.0.1:4040/api/tunnels', timeout=2))
    except Exception:
        return False
    return any(x.get('public_url') == NGROK_DOMEN for x in d.get('tunnels', []))


def kompyuterda_ngrok():
    """Kompyuterning 8123-porti USB orqali telefondagi serverga ulanadi, ngrok shu portni ochadi."""
    sarlavha('9. Kompyuterda ngrok (telefonga USB orqali)')
    port = str(SERVER_PORT)
    adb('forward', 'tcp:' + port, 'tcp:' + port, tekshir=True)
    try:
        urllib.request.urlopen('http://127.0.0.1:%s/' % port, timeout=20)
    except urllib.error.HTTPError:
        pass  # server javob berdi (302/404 ham bo'ladi) — ulanish bor
    except Exception as e:
        kompyuterni_yoq()
        xato("kompyuter telefondagi serverga USB orqali ulana olmadi: %s" % e)
    print('USB ulanish: kompyuter :%s → telefon :%s' % (port, port))
    if not NGROK_EXE:
        xato(r'ngrok.exe topilmadi (D:\asosiy\ngrok.exe).')
    if not tunnel_bormi():
        # /d — cmd AutoRun (chcp 1251) ishlamasin; alohida oyna: bat yopilsa ham ngrok ishlab turadi
        # ngrok_kuzatuv.py: kabel uzilsa ngrok'ni o'zi yopadi (domen telefonga o'tishi uchun)
        subprocess.Popen('cmd /d /s /k "title Biology Ngrok& chcp 65001 >nul& "%s" ngrok_kuzatuv.py"'
                         % sys.executable, cwd=str(ILDIZ), creationflags=subprocess.CREATE_NEW_CONSOLE)
        for _ in range(30):
            time.sleep(1)
            if tunnel_bormi():
                break
        else:
            xato("ngrok ochilmadi — «Biology Ngrok» oynasidagi xabarni o'qing.")
    so_rov = urllib.request.Request(NGROK_DOMEN + '/', headers={'ngrok-skip-browser-warning': '1',
                                                                'User-Agent': 'biology-setup'})
    try:
        urllib.request.urlopen(so_rov, timeout=30)
        print('Tekshirildi: %s ochilyapti.' % NGROK_DOMEN)
    except urllib.error.HTTPError as e:
        print('Tekshirildi: %s javob berdi (HTTP %s).' % (NGROK_DOMEN, e.code))
    except Exception as e:
        print("Diqqat: %s tekshirilmadi (%s) — brauzerda ochib ko'ring." % (NGROK_DOMEN, e))


SERVER_BAT = Path(os.path.expanduser('~')) / 'Desktop' / 'BiologyServerRun.bat'


def kompyuterni_yoq():
    """Telefonga o'rnatish muvaffaqiyatsiz bo'lsa — kompyuterdagi bot qayta yoqiladi."""
    sarlavha("Kompyuterdagi server va botlar qayta yoqilmoqda")
    if not SERVER_BAT.exists():
        print("BiologyServerRun.bat topilmadi (%s) — botni o'zingiz yoqing." % SERVER_BAT)
        return
    # 8123 telefonga yo'naltirilgan bo'lsa, kompyuterdagi Django u portni ola olmaydi
    adb('forward', '--remove', 'tcp:%d' % SERVER_PORT)
    # os.startfile — alohida oyna; shu oynaning kodirovkasiga tegmaydi (cmd AutoRun'dagi chcp 1251)
    os.startfile(str(SERVER_BAT))
    print('Yoqildi: alohida «Biology Server» oynasi ochildi — bot avvalgidek kompyuterda ishlaydi.')


def main():
    a = argparse.ArgumentParser(description='Botni telefonga o\'rnatish va ishga tushirish')
    a.add_argument('--baza-bilan', action='store_true',
                   help="telefondagi bazani kompyuterdagisi bilan almashtirish (avval zaxiralanadi)")
    args = a.parse_args()
    os.chdir(ILDIZ)

    telefonni_top()
    termuxni_tekshir()
    widget_ornat()
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
        if toxtatildi:
            kompyuterni_yoq()
        else:
            print("\nKompyuterdagi bot ishlashda davom etyapti.")
        xato("telefonda o'rnatish to'xtadi (yuqoridagi xabarni o'qing).")
    ssh('rm -f ~/biology_termux.zip')

    if not toxtatildi:
        kompyuterni_toxtat()

    sarlavha('8. Telefonda server va botlar ishga tushirilmoqda')
    # Kabel ulangan: ngrok kompyuterda (TUNNEL_MAJBURIY=kompyuter). sozlama.env da esa TUNNEL=ngrok —
    # kabelsiz `biologiya start` yozilganda ngrok telefonning o'zida ochiladi
    ssh("cd ~/milliy_sertifikat && sed -i 's/^TUNNEL=.*/TUNNEL=ngrok/' sozlama.env && "
        "(grep -q '^NGROK_DOMEN=' sozlama.env && sed -i 's#^NGROK_DOMEN=.*#NGROK_DOMEN=%s#' sozlama.env "
        "|| echo NGROK_DOMEN=%s >> sozlama.env)" % (NGROK_DOMEN, NGROK_DOMEN))
    kod, _ = ssh('bio stop >/dev/null; TUNNEL_MAJBURIY=kompyuter bio start', korsat=True)
    if kod:
        kompyuterni_yoq()
        xato("telefonda ishga tushmadi. Termux'da `bio log django` yoki `bio log bot` ni ko'ring.")

    kompyuterda_ngrok()
    print('\nTAYYOR: sayt va ikkala bot TELEFONDA ishlayapti, ngrok — kompyuterda (%s).' % NGROK_DOMEN)
    print("Kabelni uzsangiz: telefonda Termux'ni ochib  biologiya start  deb yozing — ngrok telefonga o'tadi.")
    print("Kabelni qayta ulasangiz: shu bat'ni bosing — ngrok yana kompyuterga qaytadi.")
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('\nTo\'xtatildi.')
        sys.exit(1)
