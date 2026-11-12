# -*- coding: utf-8 -*-
"""«Biology Ngrok» oynasi: kompyuterdagi ngrok telefondagi serverga USB orqali ulanadi.

Kabel uzilsa ngrok darhol yopiladi — shunda telefonda `biologiya start` yozilganda
ngrok domeni telefonga o'tadi (bitta domen bir vaqtda faqat bitta joyda ishlaydi).
«Biology telefonga.bat» bu skriptni o'zi ochadi.
"""
import subprocess
import sys
import time

import telefonga as t


def telefon_ulanganmi():
    try:
        return t.adb('get-state', timeout=10).strip() == 'device'
    except Exception:
        return False


def main():
    port = str(t.SERVER_PORT)
    t.adb('forward', 'tcp:' + port, 'tcp:' + port)
    ngrok = subprocess.Popen([t.NGROK_EXE, 'http', port, '--url', t.NGROK_DOMEN])
    try:
        while ngrok.poll() is None:
            time.sleep(3)
            if not telefon_ulanganmi():
                time.sleep(3)          # qisqa uzilish (kabel qimirlashi) bo'lsa — yana bir tekshiruv
                if telefon_ulanganmi():
                    continue
                ngrok.terminate()
                try:
                    ngrok.wait(10)
                except subprocess.TimeoutExpired:
                    ngrok.kill()
                print('\n\nKabel uzildi — kompyuterdagi ngrok yopildi.')
                print("Telefonda Termux'ni ochib yozing:   biologiya start")
                print("(ngrok telefonning o'zida ochiladi, manzil o'sha: %s)" % t.NGROK_DOMEN)
                print("Kabelni qayta ulasangiz — «Biology telefonga.bat» ni bosing.")
                return 0
        print('\nngrok to\'xtadi (kod %s).' % ngrok.returncode)
        return 1
    except KeyboardInterrupt:
        ngrok.terminate()
        return 0


if __name__ == '__main__':
    sys.exit(main())
