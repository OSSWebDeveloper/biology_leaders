# Milliy sertifikat — telefonda (Termux) ishlatish

Bot hostga qo'yilmaydi: sayt va ikkala bot Android telefonda ishlaydi, internetga
tunnel (ngrok yoki Cloudflare) orqali chiqadi. Telegram Web App https talab qiladi —
tunnel shuni beradi.

## Eng oson yo'l: bitta bat

1. Telefonda bir marta: **Settings → About phone** da **Build number** ni 7 marta bosing
   (Xiaomi'da: **MIUI version**), so'ng **Settings → System → Developer options → USB debugging**
   ni yoqing. Xiaomi'da qo'shimcha **USB debugging (Security settings)** ham yoqilsin — usiz
   kompyuter Termux'ga buyruq tera olmaydi.
2. Telefonni USB bilan ulang, ekran qulfini oching. Birinchi ulanganda **«Allow USB debugging?»**
   chiqadi: **Always allow from this computer** ni belgilab, **Allow** ni bosing.
3. Ish stolidagi **«Biology telefonga.bat»** ni bosing (yoki loyihadagi xuddi shu fayl).

Bat (`telefonga.py`) o'zi: telefonni topadi → Termux yo'q bo'lsa rasmiy GitHub'dan o'rnatadi →
Termux uchun batareya cheklovini olib tashlaydi → Termux'da SSH'ni yoqadi (birinchi marta
buyruqni telefonga o'zi teradi — ekranga tegmang) → telefondagi bazani kompyuterga
`telefon_zaxira/` ga oladi → paketni USB orqali yuboradi va o'rnatadi → kompyuterdagi
«Biology» server/bot/ngrok'ni to'xtatadi → telefonda `bio start`.

Keyin ham har safar kodni yangilash uchun shu bat'ning o'zini bosasiz: telefondagi baza
saqlanadi (va kompyuterga zaxiralanadi). Bazani kompyuterdagisi bilan almashtirish:
`Biology telefonga.bat --baza-bilan`.

Quyidagi qo'lda yo'l — bat ishlamagan holatlar uchun.

## 1. Telefonga Termux

**F-Droid** yoki GitHub (`termux/termux-app` → Releases) dan o'rnating. Play Market'dagi
eski Termux'da `pkg` ishlamaydi. Ixtiyoriy: **Termux:Widget** (bosh ekranda tugma).

## 2. Kompyuterda paket

```
python termux_paket.py
```

Telefon USB'da va «USB debugging» yoqiq bo'lsa, `biology_termux.zip` va `ornatish.sh`
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

Telefon sozlamalarida Termux uchun **batareya tejashni o'chiring** (Settings → Apps → Termux → Battery → **Unrestricted**; bat buni o'zi ham qiladi), aks holda
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
