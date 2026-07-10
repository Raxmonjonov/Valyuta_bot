# 💱 Valyuta Bot

Valyutalar kursini ko'rsatuvchi va konvertatsiya qiluvchi Telegram bot.

## ✨ Imkoniyatlar
- Mashhur valyutalar kursi (UZS ga nisbatan)
- Ixtiyoriy konvertatsiya: `100 USD UZS`
- Real vaqtli kurslar

## 🛠 Texnologiyalar
- Python 3.11+
- [aiogram 3.x](https://docs.aiogram.dev/)
- [ExchangeRate API](https://www.exchangerate-api.com/) (open.er-api.com) — API kalit shart emas

## 🚀 O'rnatish

1. Kutubxonalarni o'rnating:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate      # Windows
   pip install -r requirements.txt
   ```

2. `.env.example` dan nusxa olib `.env` yarating:
   ```
   BOT_TOKEN=...
   ```
   `BOT_TOKEN` ni [@BotFather](https://t.me/BotFather) dan oling.

3. Ishga tushiring:
   ```bash
   python main.py
   ```

## 💬 Foydalanish
- `/start` — botni ishga tushirish
- Valyuta tugmasini bosing → kursni ko'ring
- `100 USD UZS` deb yozing → konvertatsiya natijasi
