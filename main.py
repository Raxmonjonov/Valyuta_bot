"""
Valyuta Bot — Production Ready
Open Exchange Rates API orqali real vaqtli valyuta kurslari va konvertatsiya
"""

import asyncio
import html
import logging
import os
import time

import aiohttp
import aiosqlite
from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

# ─── Konfiguratsiya ─────────────────────────────────────────────────
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
DB_PATH = os.getenv("DB_PATH", "valyuta.db")
THROTTLE_RATE = float(os.getenv("THROTTLE_RATE", "0.5"))
API_URL = "https://open.er-api.com/v6/latest/"
TIMEOUT = aiohttp.ClientTimeout(total=15)

# ─── Logging ────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("valyuta-bot")

# ─── Konstantalar ───────────────────────────────────────────────────
POPULAR = ["USD", "EUR", "RUB", "GBP", "KZT", "TRY", "CNY", "JPY", "AED", "UZS"]


# ─── Database ───────────────────────────────────────────────────────
async def init_db():
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS conversions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    from_currency TEXT NOT NULL,
                    to_currency TEXT NOT NULL,
                    result REAL NOT NULL,
                    converted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS rates_cache (
                    base TEXT PRIMARY KEY,
                    rates TEXT NOT NULL,
                    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()
        logger.info("Database muvaffaqiyatli ishga tushirildi: %s", DB_PATH)
    except Exception as e:
        logger.error("Database xatosi: %s", e)
        raise


async def add_user(user_id: int, username: str | None, full_name: str | None):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT OR IGNORE INTO users (user_id, username, full_name)
                VALUES (?, ?, ?)
            """, (user_id, username, full_name))
            await db.execute(
                "UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?",
                (user_id,),
            )
            await db.commit()
    except Exception as e:
        logger.error("User qo'shishda xato: %s", e)


async def save_conversion(user_id: int, amount: float, from_cur: str, to_cur: str, result: float):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO conversions (user_id, amount, from_currency, to_currency, result) VALUES (?, ?, ?, ?, ?)",
                (user_id, amount, from_cur, to_cur, result),
            )
            await db.commit()
    except Exception as e:
        logger.error("Konvertatsiyani saqlashda xato: %s", e)


async def get_stats() -> dict:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            row = await db.execute("SELECT COUNT(*) FROM users")
            users = (await row.fetchone())[0]
            row = await db.execute("SELECT COUNT(*) FROM conversions")
            conversions = (await row.fetchone())[0]
            return {"users": users, "conversions": conversions}
    except Exception as e:
        logger.error("Statistika xatosi: %s", e)
        return {"users": 0, "conversions": 0}


# ─── Middleware ──────────────────────────────────────────────────────
class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, rate: float = 0.5):
        self.rate = rate
        self.user_timestamps: dict[int, float] = {}
        super().__init__()

    async def __call__(self, handler, event, data):
        user_id = event.from_user.id
        now = time.time()
        last = self.user_timestamps.get(user_id, 0)
        if now - last < self.rate:
            return
        self.user_timestamps[user_id] = now
        return await handler(event, data)


class ErrorMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        try:
            return await handler(event, data)
        except TelegramAPIError as e:
            logger.error("Telegram API xatosi: %s", e)
        except Exception as e:
            logger.error("Kutilmagan xatolik: %s", e, exc_info=True)
            try:
                if isinstance(event, Message):
                    await event.answer("❌ Xatolik yuz berdi.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("Xatolik.", show_alert=True)
            except Exception:
                pass


# ─── Dispatcher ─────────────────────────────────────────────────────
dp = Dispatcher(storage=MemoryStorage())
dp.message.middleware(ThrottlingMiddleware(THROTTLE_RATE))
dp.message.middleware(ErrorMiddleware())
dp.callback_query.middleware(ThrottlingMiddleware(THROTTLE_RATE))
dp.callback_query.middleware(ErrorMiddleware())


# ─── API ─────────────────────────────────────────────────────────────
async def get_rates(base: str) -> dict | None:
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            async with session.get(f"{API_URL}{base}") as resp:
                try:
                    data = await resp.json()
                except Exception:
                    return None
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        logger.error("Valyuta API xatosi: %s", e)
        return None
    if data.get("result") == "success":
        return data.get("rates", {})
    return {}


def parse_query(text: str):
    amount = 1.0
    codes = []
    for part in text.upper().replace(",", ".").split():
        try:
            amount = float(part)
        except ValueError:
            if part.isalpha() and 2 <= len(part) <= 4:
                codes.append(part)
    if len(codes) == 1:
        return amount, codes[0], "UZS"
    if len(codes) >= 2:
        return amount, codes[0], codes[1]
    return None


# ─── Keyboardlar ────────────────────────────────────────────────────
def rates_keyboard():
    builder = InlineKeyboardBuilder()
    for code in POPULAR:
        builder.button(text=code, callback_data=f"rate:{code}")
    builder.adjust(3)
    return builder.as_markup()


# ─── Handlerlar ─────────────────────────────────────────────────────
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    try:
        await state.clear()
        await add_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
        logger.info("Start — user %d (@%s)", message.from_user.id, message.from_user.username)
        await message.answer(
            "💱 <b>Valyuta Bot</b>ga xush kelibsiz!\n\n"
            "• Kursni ko'rish uchun valyutani tanlang 👇\n"
            "• Konvertatsiya: <code>100 USD UZS</code>\n\n"
            "📋 <b>Buyruqlar:</b>\n"
            "• /start — Botni qayta ishga tushirish\n"
            "• /help — Yordam\n"
            "• /rates — Asosiy kurslar\n"
            "• /stats — Statistika",
            reply_markup=rates_keyboard(),
        )
    except Exception as e:
        logger.error("Start handler xatosi: %s", e)


@dp.message(Command("help"))
async def cmd_help(message: Message):
    try:
        await message.answer(
            "💱 <b>Valyuta Bot</b> — Yordam\n\n"
            "📝 <b>Foydalanish:</b>\n"
            "• <code>100 USD UZS</code> — konvertatsiya\n"
            "• <code>USD</code> — 1 USD ning UZS dagi kursi\n"
            "• Tugmalar — tezkor kurs\n\n"
            "📋 <b>Buyruqlar:</b>\n"
            "• /start — Botni qayta ishga tushirish\n"
            "• /help — Yordam\n"
            "• /rates — Asosiy valyutalar jadvali\n"
            "• /stats — Statistika"
        )
    except Exception as e:
        logger.error("Help handler xatosi: %s", e)


@dp.message(Command("rates"))
async def cmd_rates(message: Message):
    try:
        await message.bot.send_chat_action(message.chat.id, "typing")
        rates = await get_rates("USD")
        if not rates or "UZS" not in rates:
            await message.answer("🌐 Tarmoqda muammo. Keyinroq urinib ko'ring.")
            return
        uzs_per_usd = rates["UZS"]
        lines = ["💱 <b>Kurslar (1 birlik = ? UZS):</b>\n"]
        for code in POPULAR:
            if rates.get(code) and rates[code] != 0:
                lines.append(f"  {code}: <b>{uzs_per_usd / rates[code]:,.2f}</b>")
        await message.answer("\n".join(lines))
    except Exception as e:
        logger.error("Rates handler xatosi: %s", e)


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    try:
        if message.from_user.id not in ADMIN_IDS:
            await message.answer("⛔ Sizda ruxsat yo'q.")
            return
        stats = await get_stats()
        await message.answer(
            "📊 <b>Bot Statistikasi</b>\n\n"
            f"👥 Foydalanuvchilar: {stats['users']}\n"
            f"💱 Konvertatsiyalar: {stats['conversions']}"
        )
    except Exception as e:
        logger.error("Stats handler xatosi: %s", e)


@dp.callback_query(F.data.startswith("rate:"))
async def cb_rate(callback: CallbackQuery):
    try:
        parts = callback.data.split(":")
        if len(parts) < 2 or not parts[1]:
            await callback.answer("Xatolik", show_alert=True)
            return
        code = parts[1].upper()
        if code not in POPULAR:
            await callback.answer("Noto'g'ri valyuta", show_alert=True)
            return
        await callback.answer()
        await callback.message.bot.send_chat_action(callback.message.chat.id, "typing")
        rates = await get_rates(code)
        if not rates or "UZS" not in rates:
            await callback.message.answer("🌐 Kursni olishda muammo.")
            return
        await callback.message.answer(f"💱 1 {code} = <b>{rates['UZS']:,.2f}</b> UZS")
    except Exception as e:
        logger.error("Rate handler xatosi: %s", e)


@dp.message(StateFilter(None), F.text)
async def handle_convert(message: Message):
    try:
        parsed = parse_query(message.text)
        if not parsed:
            await message.answer("❌ Namuna: <code>100 USD UZS</code>")
            return
        amount, base, target = parsed
        await add_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
        await message.bot.send_chat_action(message.chat.id, "typing")
        logger.info("Konvertatsiya — user %d: %s %s → %s", message.from_user.id, amount, base, target)
        rates = await get_rates(base)
        if rates is None:
            await message.answer("🌐 Tarmoqda muammo. Keyinroq urinib ko'ring.")
            return
        if not rates:
            await message.answer(f"❌ '{html.escape(base)}' valyutasi topilmadi.")
            return
        if target not in rates:
            await message.answer(f"❌ '{html.escape(target)}' valyutasi topilmadi.")
            return
        result = amount * rates[target]
        await save_conversion(message.from_user.id, amount, base, target, result)
        await message.answer(f"💱 <b>{amount:g} {base}</b> = <b>{result:,.2f} {target}</b>")
    except Exception as e:
        logger.error("Konvertatsiya handler xatosi: %s", e)


# ─── Bot ishga tushirish ───────────────────────────────────────────
async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN topilmadi. .env faylini to'ldiring.")
    await init_db()
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    me = await bot.get_me()
    logger.info("🤖 Valyuta Bot ishga tushdi! (@%s)", me.username)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
