# Milliy Sertifikat: test boti

Telegram bot (aiogram 3) va Web App (Django). Rollar: o'quvchi, o'qituvchi, admin.

## Test tuzilishi (namunalardan va rasmiy spetsifikatsiyadan)

| Savollar | Turi | Kalit |
|---|---|---|
| 1–32 | Yopiq test, A–D | bitta harf |
| 33–35 | Moslashtirish, A–F (bitta umumiy shart) | bitta harf |
| 36–45 | Yozma javob, a) va b) bandlar | ikkita qiymat |

Jami 45 topshiriq, 55 band, 150 daqiqa, 75 ballik shkala.
Daraja: A+ 70, A 65, B+ 60, B 55, C+ 50, C 46.

**Ball Rasch modeli bilan** (`exams/rasch.py`). Savol qiyinligi va o'quvchi qobiliyati shu testni
yechganlarning hammasi bo'yicha birga baholanadi (JML), keyin T = 50 + 10·Z ballga o'tkaziladi va
75 bilan cheklanadi. Ball boshqalar natijasiga bog'liq: har yangi yakunlangan urinishdan keyin hamma
uchun qayta hisoblanadi. O'quvchiga ball ko'rsatilmaydi, natijani o'qituvchi guruhga tashlaydi.
Savol vaznlari Rasch ballga ta'sir qilmaydi.

## Telefonda (Termux) ishlatish — hostsiz

Sayt va ikkala bot Android telefonda: [TERMUX.md](TERMUX.md).
Kompyuterda `python termux_paket.py`, telefonda `bash ~/storage/downloads/ornatish.sh` va `bio start`.

## Ishga tushirish

```bash
py -3.13 -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
copy .env.example .env
.venv/Scripts/python manage.py migrate
.venv/Scripts/python manage.py runserver
```

`.env` da `BOT_TOKEN`, `BOT_USERNAME`, `SECRET_KEY` to'ldiriladi. `.env` gitga tushmaydi.

Alohida oynada bot:

```bash
.venv/Scripts/python manage.py runbot
```

Tokenda webhook o'rnatilgan bo'lsa, bot to'xtaydi va ogohlantiradi. Webhook kerak emasligiga ishonch
hosil qilgach: `runbot --webhookni-ochir`.

Web App tugmasi faqat `WEBAPP_URL=https://...` yozilganda paydo bo'ladi: Telegram http ni qabul qilmaydi.

O'qituvchi boti (`TEACHER_BOT_TOKEN`), alohida oynada:

```bash
.venv/Scripts/python manage.py runteacherbot
```

## O'quvchi testga qanday kiradi

O'quvchida testlar ro'yxati yo'q: kirish faqat kod bilan. O'qituvchi botiga fayl yuboriladi (bot uni o'qimaydi va
o'zgartirmaydi, javoblar yozilgan fayl yubormang), 4 variantli, 6 variantli va yozma savollar soni `+`, `-` tugmalari bilan tanlanadi
(boshida 32, 3, 10), nom yoziladi. Kalit uch bosqichda: 4 variantli `1a2b3c`, 6 variantli `1a2f3d`
(raqam bo'lim ichida), yozma savollarga bittadan javob, bir nechta to'g'ri javob `2√5 or √20` ko'rinishida. Vaqt «Joriy etish»da so'raladi; shundan keyin bot fayl, kirish kodi, boshlanish va tugash vaqti yozilgan tayyor xabarni
qaytaradi, o'qituvchi uni guruhga uzatadi. O'qituvchi botiga faqat `teacher` yoki `admin` roli kira oladi:
`manage.py rol <telegram_id> teacher`.

## Foydali buyruqlar

| Buyruq | Vazifasi |
|---|---|
| `manage.py rol <telegram_id> admin` | Rol berish (`student`, `teacher`, `admin`) |
| `manage.py kirish_havolasi <telegram_id>` | Brauzer uchun bir martalik kirish havolasi (10 daqiqa) |
| `manage.py import_namunalar "<papka>"` | Namuna PDF testlarni yuklash |
| `manage.py test` | Avtomatik testlar |

Birinchi admin: botga `/id` yuboring, so'ng `.env` dagi `ADMIN_TELEGRAM_IDS` ga yozing yoki `rol` buyrug'ini ishlating.

## Yangi test qo'shish

O'qituvchi paneli → Yangi test → PDF yuklash. Savollar raqam bo'yicha topilib, har biri rasm qilib
kesiladi; formulalar buzilmaydi. PDF oxirida `JAVOBLAR` jadvali bo'lsa, yopiq savollar kaliti o'zi olinadi.
Yozma javoblar kaliti qo'lda kiritiladi: `2√5`, `16/3`, `8π`, `-1/16`, `3,5`. Bir nechta ko'rinish: `2√5 | √20`.
Javoblar qiymati bo'yicha solishtiriladi: `√20` va `2√5` ikkalasi to'g'ri. Kaliti to'liq bo'lmagan test e'lon qilinmaydi.

To'g'ri javobi belgilangan PDF yuklanmasin: belgi rasmda ko'rinib qoladi.

## Tuzilishi

- `accounts/`: foydalanuvchi, guruh, Telegram orqali kirish (initData imzosi)
- `exams/`: test, savol, urinish, baholash, PDF kesish, o'quvchi va o'qituvchi/admin sahifalari
- `tgbot/`: aiogram handlerlari, `runbot`, natijani botga yuborish
- `templates/`, `static/`: Web App interfeysi

## Hostga chiqarishdan oldin

- `DEBUG=0`, `WEBAPP_URL`, `manage.py collectstatic`
- Bot alohida doimiy jarayon sifatida ishlashi kerak (`runbot`)
- Ko'p foydalanuvchi uchun SQLite o'rniga PostgreSQL
- Namuna PDF lar boshqa mualliflarniki: ommaga ochishdan oldin ruxsatni aniqlang

## Versiyalash

```bash
.venv/Scripts/python versiya.py 1.1.0 "Qisqa izoh" -b "Tafsilot"
```
