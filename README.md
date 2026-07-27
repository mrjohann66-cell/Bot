# 🍌 Nano Banana Prompts Telegram Bot Qo'llanmasi

## Bot Imkoniyatlari:
1. **Majburiy A'zolik**: Foydalanuvchilar kanallarga a'zo bo'lgach botdan foydalana oladi.
2. **Prompt Topish**: Kalit so'z yozilsa, rasm va ustiga bossa nusxalanadigan `<code>` formatdagi prompt jo'natiladi.
3. **Admin Paneli**:
   - Prompt qo'shish va o'chirish
   - Statistika
   - Majburiy kanal qo'shish va olib tashlash

## Serverda Ishga Tushirish (VPS, Termux)
```bash
# 1. Python o'rnatilganini tekshiring:
python3 --version

# 2. Botni ishga tushiring:
python3 bot.py
```

## Railway.app yoki Render.com da Ishga Tushirish ⚠️ (Muhim)
Agar kodni Github orqali cloud hostga (Railway) ulamoqchi bo'lsangiz:

1. Github da yangi **bo'sh** repozitoriya yarating.
2. Shu fayllarni o'sha repoga joylang:
   - `bot.py` (yoki `bot_aiogram.py`)
   - `requirements.txt` (aiogram ishlatsangiz)
   - `Procfile` (YANGI FAYL OCHIB YARATING, ichida shunday yozuv bo'lsin:)
```
worker: python3 bot.py
```
(Agar aiogram tanlagan bo'lsangiz `bot.py` o'rniga `bot_aiogram.py` deb yozing)

3. Railway.app ga kiring va shu reponi deploy qiling!
Bot kodi o'z ichida DummyServer orqali Port band qiladi va Railway "Port Topilmadi" degan xatoni bermay, to'xtovsiz ishlaydi.

💡 Database (bot_database.db) o'chib ketmasligi uchun Railway panelidan "Volume" yaratib botni saqlang, yoki to'g'ridan to'g'ri bulutli databasedan foydalaning.
