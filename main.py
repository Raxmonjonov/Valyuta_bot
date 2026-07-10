import asyncio
import html
import logging
import os

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_URL = "https://open.er-api.com/v6/latest/"
TIMEOUT = aiohttp.ClientTimeout(total=15)

dp = Dispatcher()
POPULAR = ["USD", "EUR", "RUB", "GBP", "KZT", "TRY", "CNY", "JPY", "AED"]


def rates_keyboard():
    builder = InlineKeyboardBuilder()
    for code in POPULAR:
        builder.button(text=code, callback_data=f"rate:{code}")
    builder.adjust(3)
    return builder.as_markup()


async def get_rates(base: str):
    """None = tarmoq xatosi, {} = valyuta noto'g'ri, dict = kurslar."""
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            async with session.get(f"{API_URL}{base}") as resp:
                data = await resp.json()
    except (aiohttp.ClientError, asyncio.TimeoutError):
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


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "💱 <b>Valyuta Bot</b>ga xush kelibsiz!\n\n"
        "• Kursni ko'rish uchun valyutani tanlang 👇\n"
        "• Konvertatsiya: <code>100 USD UZS</code>\n"
        "• /rates — asosiy kurslar jadvali",
        reply_markup=rates_keyboard(),
    )


@dp.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(
        "💱 <b>Valyuta Bot</b> — yordam\n\n"
        "• <code>100 USD UZS</code> — konvertatsiya\n"
        "• <code>USD</code> — 1 USD ning UZS dagi kursi\n"
        "• /rates — asosiy valyutalar jadvali\n"
        "• Tugmalar — tezkor kurs"
    )


@dp.message(Command("rates"))
async def rates_cmd(message: Message):
    await message.bot.send_chat_action(message.chat.id, "typing")
    rates = await get_rates("USD")
    if not rates or "UZS" not in rates:
        await message.answer("🌐 Tarmoqda muammo. Keyinroq urinib ko'ring.")
        return
    uzs_per_usd = rates["UZS"]
    lines = ["💱 <b>Kurslar (1 birlik = ? UZS):</b>\n"]
    for code in POPULAR:
        if rates.get(code):
            lines.append(f"{code}: <b>{uzs_per_usd / rates[code]:,.2f}</b>")
    await message.answer("\n".join(lines))


@dp.callback_query(F.data.startswith("rate:"))
async def rate(callback: CallbackQuery):
    code = callback.data.split(":")[1]
    await callback.answer()
    rates = await get_rates(code)
    if not rates or "UZS" not in rates:
        await callback.message.answer("🌐 Kursni olishda muammo. Keyinroq urinib ko'ring.")
        return
    await callback.message.answer(f"💱 1 {code} = <b>{rates['UZS']:,.2f}</b> UZS")


@dp.message(F.text)
async def convert(message: Message):
    parsed = parse_query(message.text)
    if not parsed:
        await message.answer("❌ Namuna: <code>100 USD UZS</code>")
        return

    amount, base, target = parsed
    await message.bot.send_chat_action(message.chat.id, "typing")
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
    await message.answer(f"💱 <b>{amount:g} {base}</b> = <b>{result:,.2f} {target}</b>")


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN topilmadi. .env faylini to'ldiring.")
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
