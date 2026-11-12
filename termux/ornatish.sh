#!/data/data/com.termux/files/usr/bin/bash
# Milliy sertifikat (biology_leaders) — telefonga Termux orqali o'rnatish va yangilash.
#
#   bash ~/storage/downloads/ornatish.sh                  Download'dagi biology_termux.zip dan
#   bash ornatish.sh /yo'l/biology_termux.zip             boshqa joydagi zip'dan
#   bash ornatish.sh --baza-bilan                         telefondagi bazani zip'dagisi bilan ALMASHTIRISH
#
# Birinchi marta: kod + baza + media + .env + ngrok sozlamasi o'rnatiladi.
# Keyingi safar (yangilash): faqat KOD almashadi — telefondagi baza, media va .env saqlanadi
# (baza avval ~/milliy_sertifikat/zaxira/ ga nusxalanadi).
set -e

ILDIZ="$HOME/milliy_sertifikat"
ZIP="$HOME/storage/downloads/biology_termux.zip"
BAZA_BILAN=0
for a in "$@"; do
  case "$a" in
    --baza-bilan) BAZA_BILAN=1 ;;
    *) ZIP="$a" ;;
  esac
done

yashil() { printf '\033[1;32m%s\033[0m\n' "$*"; }
sariq()  { printf '\033[1;33m%s\033[0m\n' "$*"; }
qizil()  { printf '\033[1;31m%s\033[0m\n' "$*"; }

if [ ! -d "$HOME/storage" ]; then
  sariq "Telefon xotirasiga ruxsat so'ralmoqda — «Разрешить / Allow» ni bosing."
  termux-setup-storage || true
  sleep 3
fi
if [ ! -f "$ZIP" ]; then
  qizil "Zip topilmadi: $ZIP"
  echo "Kompyuterda:  python termux_paket.py   — u zip'ni telefonning Download papkasiga qo'yadi."
  exit 1
fi

yashil "1/6  Termux paketlari (birinchi marta 10-20 daqiqa)…"
pkg update -y
pkg install -y python python-pip python-pymupdf python-pillow ttf-dejavu \
               clang rust make binutils proot resolv-conf curl openssl-tool cloudflared util-linux

yashil "2/6  Python kutubxonalari (pydantic-core telefonda yig'iladi — sabr qiling)…"
# aiohttp oilasining C kengaytmalari shart emas — toza Python varianti ishlatiladi
export AIOHTTP_NO_EXTENSIONS=1 YARL_NO_EXTENSIONS=1 MULTIDICT_NO_EXTENSIONS=1 \
       PROPCACHE_NO_EXTENSIONS=1 FROZENLIST_NO_EXTENSIONS=1
# maturin (pydantic-core) Android'da shu o'zgaruvchini so'raydi
export ANDROID_API_LEVEL="$(getprop ro.build.version.sdk 2>/dev/null || echo 24)"
pip install --disable-pip-version-check \
  'Django>=5.2,<5.3' 'aiogram>=3.13,<4' 'openpyxl>=3.1' 'python-dotenv>=1.0' 'whitenoise>=6.6' gunicorn
python -c "import pymupdf, PIL, aiogram, django" || { qizil "Kutubxonalar to'liq o'rnatilmadi — yuqoridagi xatoni o'qing."; exit 1; }

yashil "3/6  Fayllar…"
VAQT="$(date +%Y%m%d_%H%M%S)"
BIRINCHI=0
[ -f "$ILDIZ/db.sqlite3" ] || BIRINCHI=1
if [ "$BIRINCHI" = 0 ]; then
  mkdir -p "$ILDIZ/zaxira"
  python - "$ILDIZ/db.sqlite3" "$ILDIZ/zaxira/db_${VAQT}.sqlite3" <<'PY'
import sqlite3, sys
s, d = sqlite3.connect(sys.argv[1]), sqlite3.connect(sys.argv[2])
s.backup(d); d.close(); s.close()
PY
  sariq "     Telefondagi baza zaxiraga olindi: zaxira/db_${VAQT}.sqlite3"
fi
TMP="$(mktemp -d)"
python - "$ZIP" "$TMP" <<'PY'
import sys, zipfile
zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])
PY
mkdir -p "$ILDIZ"
for f in accounts config exams tgbot templates static termux manage.py versiya.txt VERSIYALAR.md \
         README.md TERMUX.md requirements.txt; do
  if [ -e "$TMP/$f" ]; then rm -rf "${ILDIZ:?}/$f"; cp -r "$TMP/$f" "$ILDIZ/$f"; fi
done
# ngrok sozlamasi (authtoken) har doim kompyuterdagisidan
[ -f "$TMP/ngrok.yml" ] && cp "$TMP/ngrok.yml" "$ILDIZ/ngrok.yml"
if [ "$BIRINCHI" = 1 ] || [ "$BAZA_BILAN" = 1 ]; then
  rm -f "$ILDIZ/db.sqlite3" "$ILDIZ/db.sqlite3-wal" "$ILDIZ/db.sqlite3-shm"
  cp "$TMP/db.sqlite3" "$ILDIZ/db.sqlite3"
  rm -rf "$ILDIZ/media"; cp -r "$TMP/media" "$ILDIZ/media" 2>/dev/null || mkdir -p "$ILDIZ/media"
  [ "$BAZA_BILAN" = 1 ] && sariq "     Baza va media kompyuterdagisi bilan almashtirildi."
fi
[ -f "$ILDIZ/.env" ] || cp "$TMP/.env" "$ILDIZ/.env"
# Telefon sozlamasi (tunnel turi, domen) kod papkasidan tashqarida — yangilashda saqlanadi
[ -f "$ILDIZ/sozlama.env" ] || cp "$ILDIZ/termux/sozlama.namuna.env" "$ILDIZ/sozlama.env"
rm -rf "$TMP"

yashil "4/6  PDF hisobot uchun shrift…"
mkdir -p "$ILDIZ/static/fonts"
for nom in DejaVuSans.ttf DejaVuSans-Bold.ttf; do
  manba="$(find "$PREFIX/share/fonts" -name "$nom" 2>/dev/null | head -n1)"
  [ -n "$manba" ] && cp "$manba" "$ILDIZ/static/fonts/$nom"
done

yashil "5/6  ngrok…"
if [ ! -x "$ILDIZ/bin/ngrok" ]; then
  case "$(uname -m)" in
    aarch64) arx=arm64 ;; armv7l|armv8l) arx=arm ;; x86_64) arx=amd64 ;; *) arx=arm64 ;;
  esac
  mkdir -p "$ILDIZ/bin"
  curl -fL -o "$ILDIZ/bin/ngrok.tgz" "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-${arx}.tgz"
  tar -xzf "$ILDIZ/bin/ngrok.tgz" -C "$ILDIZ/bin" && rm -f "$ILDIZ/bin/ngrok.tgz"
  chmod +x "$ILDIZ/bin/ngrok"
fi

yashil "6/6  Baza, statik fayllar va 'bio' buyrug'i…"
cd "$ILDIZ"
python manage.py migrate --noinput
python manage.py collectstatic --noinput -v0
install -m 755 "$ILDIZ/termux/bio.sh" "$PREFIX/bin/bio"
mkdir -p "$HOME/.shortcuts"
printf '#!/data/data/com.termux/files/usr/bin/bash\nbio start\n' > "$HOME/.shortcuts/Biology ishga tushirish"
printf '#!/data/data/com.termux/files/usr/bin/bash\nbio stop\n'  > "$HOME/.shortcuts/Biology to'xtatish"
chmod +x "$HOME/.shortcuts/"*

echo
yashil "Tayyor! Versiya: $(cat "$ILDIZ/versiya.txt")"
echo "Ishga tushirish:  bio start      Buyruqlar:  bio yordam"
sariq "Eslatma: kompyuterdagi server va botlarni avval to'xtating — bitta bot tokeni va ngrok"
sariq "domeni bir vaqtda faqat BITTA joyda ishlay oladi."
