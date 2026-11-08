# Versiyalar tarixi

## 1.8.1 — 2026-11-08

Ball tekshiruvi va savol rasmlari himoyasi tuzatildi

- Yozma javob: 3,5 endi 3 deb o'qilmaydi (3,7 to'g'ri chiqmaydi); nisbat 9:3:3:1 bo'lish emas; 2c va 2n har xil javob
- Rasch ajrata olmasa (bitta qatnashchi, hamma bir xil, hammasi 0 yoki hammasi to'g'ri) hammaga 50 o'rniga to'g'ri javoblar ulushidan ball
- Savol rasmlari ochiq /media/ orqali berilmaydi: faqat test egasi, admin va testni boshlagan o'quvchi ko'radi
- Obunasiz kelgan /start g_KOD havolasi Obuna bo'ldim bosilgach guruhga qo'shadi

## 1.8.0 — 2026-11-08

Kanalga majburiy obuna

- O'quvchi botdan foydalanishdan oldin kanalga obuna bo'lishi kerak: kanal havolasi va 'Obuna bo'ldim' tugmasi
- Saytda ham kod kiritish va test boshlashda obuna tekshiriladi (menyu tugmasi botni chetlab o'tmasin)
- Kanal .env da: REQUIRED_CHANNEL_ID, REQUIRED_CHANNEL_URL; Telegram javob bermasa test to'xtamaydi

## 1.7.0 — 2026-11-08

Rasch modeli bilan baholash, kirish kodini o'qituvchi beradi

- Ball Rasch modeli (JML) bilan shu testni yechgan hamma bo'yicha hisoblanadi, T = 50 + 10*Z, 75 gacha; har yakunlangan urinishdan keyin hammasi qayta hisoblanadi
- Joriy etishda bot avval kirish kodini so'raydi: 3-8 lotin harfi yoki raqam, band kod qabul qilinmaydi
- O'qituvchi natijalarida 'darajasiz' yozuvi olib tashlandi

## 1.6.0 — 2026-11-08

Javoblar varag'i bitta sahifada, o'quvchiga ball ko'rsatilmaydi

- Savollar faylda bo'lsa hamma savol bitta varaqda: 4 va 6 variantli harf tugmalari, yozma javob maydonlari
- Natija sahifasi, Natijalarim, bot xabari va reytingda o'quvchiga ball va daraja ko'rsatilmaydi: 'Natijalar guruhga tashlanadi'
- CSS va JS fayllariga versiya qo'shildi: Telegram eski faylni keshdan olmaydi

## 1.5.0 — 2026-11-08

Kalit uch bosqichda, yozma savolga bitta javob va or

- 4 va 6 variantli bo'limlar: 1a2b3c ko'rinishida, raqam bo'lim ichida
- Yozma savolga bittadan javob, or bilan cheksiz to'g'ri variant
- Eski a/b testlar o'zgarmaydi

## 1.4.2 — 2026-11-08

Boshlang'ich tuzilish: 32 ta 4 variantli, 3 ta 6 variantli, 10 ta yozma

## 1.4.1 — 2026-11-08

Test tekshiruvi tuzatildi

## 1.4.0 — 2026-11-08

Savollar soni o'rniga uch tur: 4 variantli, 6 variantli, yozma

- Har bir tur soni + va - tugmalari bilan o'zgaradi, boshida 32, 3, 0
- Javob namunasi testdagi haqiqiy raqamlardan tuziladi

## 1.3.0 — 2026-11-07

Test yaratish va joriy etish ajratildi

- Vaqt faqat joriy etishda so'raladi, tayyor xabar shundan keyin chiqadi
- Menyuga chiqib ketganda chala test va javoblar saqlanib qoladi

## 1.2.0 — 2026-11-07

O'qituvchi boti faylni o'qimaydi, savollar soni tugmalar bilan

- Fayl o'zgarishsiz saqlanadi va guruhga shu holida ketadi
- Savollar soni standart 35, tugmalar: +, -, Tayyor

## 1.1.1 — 2026-11-07

Guruh nusxasida bo'sh sahifa qolmaydi

## 1.1.0 — 2026-11-07

Testga faqat kod bilan kirish va o'qituvchi boti

- O'quvchida testlar ro'yxati yo'q, kirish kodi orqali kiradi
- O'qituvchi boti: fayl, vaqt va kalit qatorlar bilan, guruhga uzatish uchun tayyor xabar
- PDF kalit sahifasi guruh nusxasidan o'chiriladi, Word uchun javob varag'i
- To'g'ri javoblar test tugagach ko'rinadi, yangi testda urinish 1 ta

## 1.0.2 — 2026-11-07

Web App'dan kirish tuzatildi

- Bosh sahifa CSRF cookie o'rnatadi: Telegramdan kirish 403 bilan rad etilardi
- Server xatosi endi internet uzilishi deb ko'rsatilmaydi

## 1.0.1 — 2026-11-07

Start bosilganda yangi salomlashuv matni

- Ism so'rovi: Assalomu aleykum, namuna Behruz Hodiyev
- Noto'g'ri ism kiritilganda ham shu namuna ko'rsatiladi

## 1.0.0 — 2026-11-07

Birinchi ishlaydigan holat: bot, Web App, o'quvchi/o'qituvchi/admin rollari

- 45 savollik format: yopiq, moslashtirish, a/b yozma
- PDF dan savollarni rasm qilib kesish va kalitni o'qish
- Taxminiy 75 ballik baholash va darajalar

