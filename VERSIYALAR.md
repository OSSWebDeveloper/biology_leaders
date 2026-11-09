# Versiyalar tarixi

## 1.18.0 — 2026-11-09

Rasch hisobi tuzatildi (agentlar tekshiruvi bo'yicha)

- Chegaraviy savol/o'quvchilar takroriy kesiladi: bitta bo'sh varaq oson savol qiyinligini cheksizga olib ketib, hamma ballni siqib qo'ymaydi; kesilgan savollar 0,3 siljitish bilan qaytariladi (ko'proq to'g'ri — doim yuqoriroq ball)
- Model yaqinlashmasa yoki qiymatlar cheksizga ketsa (Guttman ko'rinishi) ball to'g'ri javoblar ulushidan
- Javob bergan o'quvchi 20 tadan kam bo'lsa ball doim 75 x ulush (kichik guruhda Rasch ishonchsiz)
- Bo'sh varaq Rasch hisobiga kirmaydi, unga 0 ball
- Yakunlash va tekshirish bitta tranzaksiyada; Rasch qayta hisobi faqat bot aylanishida (30 s), sayt va bot bir-birini bosib ketmaydi
- O'qituvchi botida kalitning har bir qismi saqlanganda javoblar qayta tekshiriladi
- A+ faqat 70 dan yuqori ball (70 — A)

## 1.17.0 — 2026-11-09

Boshlanish vaqtida avtomatik e'lon va kanalga xabar

- Bot har 30 soniyada tekshiradi: boshlanish vaqti kelgan qoralama test (kaliti to'liq bo'lsa) e'lon qilinadi
- Shu paytda kanalga bir marta xabar ketadi: test fayli + kirish kodi + vaqtlar (fayl bo'lmasa matn)
- Kanal: .env ANNOUNCE_CHANNEL_ID, bo'sh bo'lsa majburiy obuna kanali; yuborilmasa tugash vaqtigacha qayta urinadi
- Boshlanish vaqti o'zgartirilsa yangi vaqtda qayta e'lon qilinadi; test sahifasida «Kanalga e'lon» holati
- Yangilanishgacha boshlanib bo'lgan testlar kanalga yuborilmaydi

## 1.16.0 — 2026-11-09

Kirish kodi test formasida

- «Yangi test» va «Test sozlamalari» formasida «Kirish kodi» (3–8 lotin harfi yoki raqam, band bo'lsa xato)
- Yangi testda «Test vaqti (daqiqa)» bo'sh turadi, o'qituvchi o'zi yozadi
- Test sahifasidan «Kalitsiz savollar» ogohlantirishi, «Fayl yuklash» va «Natijalar» tugmalari olib tashlandi

## 1.15.0 — 2026-11-09

Test faylini yaratish sahifasida biriktirish

- «Yangi test» va «Test sozlamalari» formasida ixtiyoriy «Test fayli (PDF yoki Word)» maydoni
- Savollar soni formadan olinadi, fayl faqat saqlanadi (PDF dan «JAVOBLAR» sahifasi olib tashlanadi)
- Yangi test saqlangach to'g'ridan-to'g'ri test sahifasiga (javoblar kaliti) o'tadi

## 1.14.0 — 2026-11-09

O'qituvchi botida Web App

- O'qituvchi botining menyu tugmasi «O'qituvchi» va /start dagi «🎓 O'qituvchi ilovasi» tugmasi /ustoz/ ni Web App qilib ochadi
- Sayt initData imzosini o'quvchi va o'qituvchi botlari tokeni bilan tekshiradi

## 1.13.0 — 2026-11-09

Tugash vaqti avtomatik, «Fan» olib tashlandi

- Test sozlamalarida «Tugash vaqti» maydoni yo'q: boshlanish vaqti + test vaqti (daqiqa) bo'yicha hisoblanadi
- «Fan» maydoni formadan va o'quvchi sahifasidan olib tashlandi

## 1.12.0 — 2026-11-09

Test sozlamalarida savollar soni

- «Urinishlar soni» maydoni olib tashlandi (test bir marta yechiladi, o'quvchi sahifasida ham ko'rsatilmaydi)
- Uchta «vazn» maydoni o'rniga: 4 variantli, 6 variantli va ochiq savollar soni
- Son o'zgarsa savollar oxiridan qo'shiladi yoki o'chiriladi, kiritilgan kalitlar saqlanadi, raqamlar qayta tartiblanadi
- Testni yechganlar bo'lsa savollar sonini o'zgartirib bo'lmaydi
- Saytda yangi test yaratilganda javob varag'i shu sonlar bilan darhol yaratiladi

## 1.11.0 — 2026-11-09

Brauzerda parol bilan kirish

- /mrclayd va /ustoz kompyuter brauzerida parol so'raydi; o'qituvchi boti orqali tasdiqlash olib tashlandi
- Parol admin hisobining Django paroli (bazada hash, kodda yo'q); bir IP dan 5 marta xato — 15 daqiqa kutish
- Telegram Web App ichida /ustoz avvalgidek o'zi kiradi, /mrclayd esa «Sahifa topilmadi»

## 1.10.0 — 2026-11-09

Chrome orqali kirish va texnik qism statistikasi

- /mrclayd va /ustoz kompyuter brauzerida ham ochiladi: «Telegram orqali kirish» o'qituvchi botini ochadi, «Tasdiqlash» bosilgach sahifa o'zi kiradi (token 5 daqiqa, bir martalik, faqat so'ragan brauzerga)
- /mrclayd faqat brauzer sessiyasida: Telegram Web App ichidan ochilsa «Sahifa topilmadi»; botdagi /mrclayd buyrug'i olib tashlandi
- /ustoz avvalgidek Web App ichida ham ishlaydi (/ustoz buyrug'i)
- Texnik qism: hozir onlayn (sayt va bot alohida), test yechayotganlar, bugun/7/30 kunda faol, yangi foydalanuvchilar, 14 kunlik grafik, darajalar, testlar jadvali, server holati; 30 soniyada yangilanadi
- Foydalanuvchida last_seen va last_bot_seen maydonlari (daqiqasiga ko'pi bilan bir marta yoziladi)
- .env: TEACHER_BOT_USERNAME

## 1.9.0 — 2026-11-09

Yashirin kirish manzillari: /mrclayd va /ustoz

- /mrclayd — texnik qism (Boshqaruv): faqat admin; boshqalarga 404, manzil borligi bilinmaydi
- /ustoz — o'qituvchi bo'limi: o'qituvchi va admin; o'quvchiga ruxsat yo'q
- Telegram ichida ochilsa initData bilan kiradi va shu bo'limga yo'naltiradi
- O'quvchi botida /mrclayd va /ustoz buyruqlari bo'limni ochish tugmasini beradi; ruxsati yo'qqa javob yo'q
- Admin Telegram ID .env dagi ADMIN_TELEGRAM_IDS orqali beriladi

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

