#!/data/data/com.termux/files/usr/bin/bash
# Bosh ekran yorliqlari (Termux:Widget) — 6 ta: sayt, o'quvchi boti, o'qituvchi boti × yoqish/to'xtatish.
# Yoqish yorlig'i ishga tushirgach jonli holat oynasini ochiq qoldiradi (bio kuzat).
S="$HOME/.shortcuts"
mkdir -p "$S"
rm -f "$S/Biology ishga tushirish" "$S/Biology to'xtatish"   # eski 2 ta yorliq (v1.31 gacha)

yoq() {   # $1 = yorliq nomi, $2 = qism
  printf '#!/data/data/com.termux/files/usr/bin/bash\nbio start %s\nexec bio kuzat\n' "$2" > "$S/$1"
}
ochir() {
  printf '#!/data/data/com.termux/files/usr/bin/bash\nbio stop %s\necho\nread -r -t 8 -p "Oyna 8 soniyada yopiladi (Enter - hozir)..." _\n' "$2" > "$S/$1"
}

yoq   "Sayt ▶"          sayt
ochir "Sayt ■"          sayt
yoq   "O'quvchi ▶"      oquvchi
ochir "O'quvchi ■"      oquvchi
yoq   "O'qituvchi ▶"    oqituvchi
ochir "O'qituvchi ■"    oqituvchi
chmod 700 "$S" "$S"/*
