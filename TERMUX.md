# Milliy sertifikat — telefonda (Termux) ishlatish

Bot hostga qo'yilmaydi: sayt va ikkala bot Android telefonda ishlaydi, internetga
tunnel (ngrok yoki Cloudflare) orqali chiqadi. Telegram Web App https talab qiladi —
tunnel shuni beradi.

## 1. Telefonga Termux

**F-Droid** yoki GitHub (`termux/termux-app` → Releases) dan o'rnating. Play Market'dagi
eski Termux'da `pkg` ishlamaydi. Ixtiyoriy: **Termux:Widget** (bosh ekranda tugma).

## 2. Kompyuterda paket

```
python termux_paket.py
```

Telefon USB'da va «Отладка по USB» yoqiq bo'lsa, `biology_termux.zip` va `ornatish.sh`
telefonning **Download** papkasiga o'zi tushadi. Aks holda `dist/` dagi ikki faylni o'zingiz
ko'chiring. **Zip ichida bot tokenlari bor — boshqalarga yubormang.**

Paketga hozirgi baza, media, `.env` va ngrok kaliti kiradi. Telefondagi `.env` da
`DEBUG=0`, `BROWSER_STUDENTS=0` bo'ladi (kompyuterdagisi o'zgarmaydi).

## 3. Termux'da o'rnatish

```
termux-setup-storage
bash ~/storage/downloads/ornatish.sh
```

Birinchi o'rnatish uzoq (20–40 daqiqa): `pydantic-core` (aiogram uchun) telefonda yig'iladi.
Keyingi yangilashlar tez.

## 4. Ishga tushirish

**Avval kompyuterdagi «Biology» oynalarini (server, botlar, ngrok) yoping** — bitta bot tokeni
va bitta ngrok domeni bir vaqtda faqat bitta joyda ishlay oladi.

```
bio start
```

Ketma-ketlik: tunnel → `.env` dagi `WEBAPP_URL` yangilanadi → Django (gunicorn) → o'quvchi boti →
o'qituvchi boti. Biror qism yiqilsa (internet uzilishi va h.k.) 5 soniyada o'zi qayta turadi.

Telefon sozlamalarida Termux uchun **batareya tejashni o'chiring** («Без ограничений»), aks holda
Android ekran o'chganda jarayonlarni to'xtatishi mumkin. `bio start` ekran o'chsa ham ishlashi
uchun wake-lock oladi.

## Buyruqlar

```
bio start | stop | restart
bio holat                 nima ishlayapti, joriy manzil
bio log bot               jurnal (bot | oqituvchi | django | tunnel)
bio zaxira                baza + media → Download/biology_zaxira_….zip
bio yangilash             yangi kodni o'rnatish (telefondagi baza saqlanadi)
bio yangilash --baza-bilan   bazani kompyuterdagisi bilan almashtirish (avval zaxira olinadi)
```

## Tunnel tanlash — `~/milliy_sertifikat/sozlama.env`

| | ngrok (standart) | cloudflare |
|---|---|---|
| Manzil | doimiy: `roughy-outgoing-iguana.ngrok-free.app` | har `bio start` da yangi `….trycloudflare.com` |
| Chegara | bepul tarif: oyiga ~20 000 so'rov (800 kishilik test ~40 000) | so'rov chegarasi yo'q |

Katta test oldidan `TUNNEL=cloudflare` qilib `bio restart` qilish mumkin: manzil o'zgaradi,
lekin botlar yangi manzil bilan qayta turadi, o'quvchilar odatdagidek bot orqali kiradi.

## Muhim

- Telefon ishga tushgach **asosiy baza — telefonda**. Kompyuterda o'zgartirilgan ma'lumot
  telefonga o'tmaydi (faqat `bio yangilash --baza-bilan` bilan, telefondagi o'zgarishlar ustidan).
- Haftada bir `bio zaxira` qilib, zip'ni kompyuterga ko'chiring.
