#!/data/data/com.termux/files/usr/bin/bash
# Milliy sertifikat — telefonda boshqarish:  bio start | stop | restart | holat | log | zaxira | yangilash
# Ishga tushadi: tunnel (kompyuter, ngrok yoki cloudflare) → .env dagi WEBAPP_URL → Django (gunicorn)
#                → o'quvchi boti → o'qituvchi boti. Har biri yiqilsa 5 soniyada o'zi qayta turadi.
ILDIZ="$HOME/milliy_sertifikat"
RUN="$ILDIZ/run"
LOG="$ILDIZ/log"

yashil() { printf '\033[1;32m%s\033[0m\n' "$*"; }
sariq()  { printf '\033[1;33m%s\033[0m\n' "$*"; }
qizil()  { printf '\033[1;31m%s\033[0m\n' "$*"; }

[ -d "$ILDIZ" ] || { qizil "$ILDIZ yo'q — avval ornatish.sh ni ishga tushiring."; exit 1; }
cd "$ILDIZ" || exit 1
mkdir -p "$RUN" "$LOG"

TUNNEL=ngrok; NGROK_DOMEN=""; PORT=8123; ISHCHILAR=2; OQIMLAR=8
# shellcheck disable=SC1091
[ -f "$ILDIZ/sozlama.env" ] && . "$ILDIZ/sozlama.env"
# Kompyuterdagi bat USB rejimida TUNNEL_MAJBURIY=kompyuter bilan chaqiradi; qo'lda
# `biologiya start` (kabelsiz) esa sozlama.env dagi TUNNEL=ngrok — ngrok telefonning o'zida
[ -n "${TUNNEL_MAJBURIY:-}" ] && TUNNEL="$TUNNEL_MAJBURIY"
export PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8

QISMLAR=(tunnel django bot oqituvchi)
# TUNNEL=kompyuter: ngrok kompyuterda ishlaydi va USB (adb forward) orqali shu serverga ulanadi
[ "$TUNNEL" = kompyuter ] && QISMLAR=(django bot oqituvchi)

tirikmi() { [ -f "$RUN/$1.pid" ] && kill -0 "$(cat "$RUN/$1.pid")" 2>/dev/null; }

# Jarayonni fonda, yiqilsa qayta tushiradigan aylanma bilan ochadi
fonda() {
  local nom="$1"; shift
  # tunnel: kompyuterdagi ngrok domenni ushlab turgan bo'lsa, ngrok serveriga tez-tez urinmasin
  local kut=5; [ "$nom" = tunnel ] && kut=20
  setsid nohup bash -c '
    kut="$1"; shift
    while true; do
      "$@"
      echo "[$(date "+%F %T")] to'"'"'xtadi (kod $?) — $kut soniyadan keyin qayta ishga tushadi"
      sleep "$kut"
    done' _ "$kut" "$@" >> "$LOG/$nom.log" 2>&1 < /dev/null &
  echo $! > "$RUN/$nom.pid"
}

toxtat_qism() {
  local p
  if [ -f "$RUN/$1.pid" ]; then
    p="$(cat "$RUN/$1.pid")"
    kill -- "-$p" 2>/dev/null || pkill -P "$p" 2>/dev/null
    kill "$p" 2>/dev/null
    rm -f "$RUN/$1.pid"
  fi
}

tunnel_manzili() {
  if [ "$TUNNEL" = cloudflare ]; then
    grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG/tunnel.log" 2>/dev/null | tail -n1
  else
    python - "$PORT" <<'PY' 2>/dev/null
import json, sys, urllib.request
try:
    d = json.load(urllib.request.urlopen('http://127.0.0.1:4040/api/tunnels', timeout=2))
    for t in d.get('tunnels', []):
        if t.get('public_url', '').startswith('https://') and t['config']['addr'].endswith(':' + sys.argv[1]):
            print(t['public_url']); break
except Exception:
    pass
PY
  fi
}

env_yoz() {  # .env dagi KALIT=qiymat ni almashtiradi (yo'q bo'lsa qo'shadi)
  python - "$ILDIZ/.env" "$1" "$2" <<'PY'
import re, sys
f, k, v = sys.argv[1:]
t = open(f, encoding='utf-8').read()
t, n = re.subn(r'(?m)^%s=.*$' % re.escape(k), '%s=%s' % (k, v), t)
if not n:
    t = t.rstrip('\n') + '\n%s=%s\n' % (k, v)
open(f, 'w', encoding='utf-8').write(t)
PY
}

tunnel_och() {
  yashil "1/4  Tunnel ($TUNNEL)…"
  : > "$LOG/tunnel.log"
  if [ "$TUNNEL" = kompyuter ]; then
    [ -n "$NGROK_DOMEN" ] || { qizil "sozlama.env da NGROK_DOMEN yo'q."; exit 1; }
    echo "     ngrok kompyuterda; manzil: $NGROK_DOMEN"
  elif [ "$TUNNEL" = cloudflare ]; then
    fonda tunnel cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:$PORT"
  else
    [ -x "$ILDIZ/bin/ngrok" ] || { qizil "ngrok o'rnatilmagan — ornatish.sh ni qayta ishga tushiring."; exit 1; }
    local qosh=(); [ -n "$NGROK_DOMEN" ] && qosh=(--url "$NGROK_DOMEN")
    # Android'da /etc/resolv.conf yo'q — ngrok (Go) DNS topa olmaydi. proot faqat shu bitta
    # faylni Termux'dagisi bilan almashtiradi, qolgan yo'llar o'zgarmaydi.
    fonda tunnel proot -b "$PREFIX/etc/resolv.conf:/etc/resolv.conf" "$ILDIZ/bin/ngrok" \
      http "$PORT" "${qosh[@]}" --config "$ILDIZ/ngrok.yml" --log stdout
  fi
  local url="" i
  [ "$TUNNEL" = kompyuter ] && url="$NGROK_DOMEN"
  for i in $(seq 1 45); do
    [ -n "$url" ] && break
    url="$(tunnel_manzili)"; [ -n "$url" ] && break; sleep 1
  done
  if [ -z "$url" ] && [ "$TUNNEL" = ngrok ] && [ -n "$NGROK_DOMEN" ]; then
    # Domen doimiy: kompyuterdagi ngrok hali ochiq bo'lsa, u yopilishi bilan telefondagisi
    # o'zi ulanadi (har 5 soniyada qayta urinadi) — sayt va botlar kutib turmaydi
    sariq "     ngrok hali ulanmadi (kompyuterdagi ngrok ochiq bo'lishi mumkin) — o'zi qayta urinadi."
    tail -n 3 "$LOG/tunnel.log" | cut -c1-160
    url="$NGROK_DOMEN"
  fi
  if [ -z "$url" ]; then
    qizil "Tunnel ochilmadi. Jurnal:"; tail -n 15 "$LOG/tunnel.log"
    toxtat_qism tunnel; exit 1
  fi
  echo "     $url"
  env_yoz WEBAPP_URL "$url"
}

start() {
  command -v termux-wake-lock >/dev/null && termux-wake-lock
  # Kompyuterdagi bat USB orqali SSH bilan ulanadi — Termux qayta ochilganda ham yoqiq tursin
  command -v sshd >/dev/null && ! pgrep -x sshd >/dev/null && sshd 2>/dev/null
  if tirikmi django; then
    # Sayt va botlar ishlayapti (masalan USB rejimida), faqat tunnel yo'q — kabel uzilgan
    if [ "$TUNNEL" != kompyuter ] && ! tirikmi tunnel; then
      tunnel_och
    else
      sariq "Allaqachon ishlayapti."
    fi
    holat; return
  fi
  tunnel_och

  yashil "2/4  Baza…"
  python manage.py migrate --noinput >> "$LOG/django.log" 2>&1 || { qizil "migrate xato — bio log django"; exit 1; }

  yashil "3/4  Django serveri…"
  fonda django gunicorn config.wsgi:application -b "127.0.0.1:$PORT" \
    -w "$ISHCHILAR" -k gthread --threads "$OQIMLAR" --backlog 2048 --timeout 120 \
    --access-logfile - --error-logfile -
  for i in $(seq 1 30); do
    curl -s -o /dev/null "http://127.0.0.1:$PORT/" && break; sleep 1
  done

  yashil "4/4  Botlar…"
  fonda bot python manage.py runbot
  fonda oqituvchi python manage.py runteacherbot
  sleep 3
  holat
}

stop() {
  local q
  for q in oqituvchi bot django tunnel; do toxtat_qism "$q"; done
  command -v termux-wake-unlock >/dev/null && termux-wake-unlock
  yashil "To'xtatildi."
}

holat() {
  local q
  echo
  for q in "${QISMLAR[@]}"; do
    if tirikmi "$q"; then printf '  \033[1;32m●\033[0m %-10s ishlayapti\n' "$q"
    else printf '  \033[1;31m●\033[0m %-10s to'"'"'xtagan\n' "$q"; fi
  done
  echo "  Manzil: $(grep -m1 '^WEBAPP_URL=' .env | cut -d= -f2-)"
  echo "  Versiya: $(cat versiya.txt)"
  echo
}

zaxira() {
  local joy="$HOME/storage/downloads"; [ -d "$joy" ] || joy="$ILDIZ/zaxira"
  mkdir -p "$joy"
  python - "$ILDIZ" "$joy/biology_zaxira_$(date +%Y%m%d_%H%M%S).zip" <<'PY'
import os, sqlite3, sys, tempfile, zipfile
ildiz, chiqish = sys.argv[1:]
tmp = tempfile.mktemp(suffix='.sqlite3')
s, d = sqlite3.connect(os.path.join(ildiz, 'db.sqlite3')), sqlite3.connect(tmp)
s.backup(d); d.close(); s.close()
with zipfile.ZipFile(chiqish, 'w', zipfile.ZIP_DEFLATED) as z:
    z.write(tmp, 'db.sqlite3')
    for papka, _, fayllar in os.walk(os.path.join(ildiz, 'media')):
        for f in fayllar:
            p = os.path.join(papka, f)
            z.write(p, os.path.relpath(p, ildiz))
os.remove(tmp)
print(chiqish, '%.1f MB' % (os.path.getsize(chiqish) / 1e6))
PY
  yashil "Zaxira tayyor (baza + media). Kompyuterga ham ko'chirib qo'ying."
}

case "${1:-yordam}" in
  start)     start ;;
  stop)      stop ;;
  restart)   stop; sleep 1; start ;;
  holat)     holat ;;
  log)       tail -n "${3:-40}" "$LOG/${2:-bot}.log" ;;
  zaxira)    zaxira ;;
  yangilash) stop; bash "$ILDIZ/termux/ornatish.sh" "${@:2}" && start ;;
  *)
    cat <<'MATN'
Milliy sertifikat — telefondagi buyruqlar:
  biologiya start        sayt + ikkala bot + ngrok (telefonda) — kabel ulanmagan bo'lsa ham ishlaydi
  bio start              xuddi shu (biologiya = bio)
  bio stop               hammasini to'xtatish
  bio restart            qayta ishga tushirish
  bio holat              nima ishlayapti, joriy manzil
  bio log [qism]         jurnal: bot | oqituvchi | django | tunnel
  bio zaxira             baza + media → Download/biology_zaxira_….zip
  bio yangilash          Download'dagi yangi zip'dan kodni yangilash (baza saqlanadi)
  bio yangilash --baza-bilan   bazani ham kompyuterdagisi bilan almashtirish
Sozlama (tunnel turi, domen): nano ~/milliy_sertifikat/sozlama.env
MATN
    ;;
esac
