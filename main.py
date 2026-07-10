import asyncio
import html
import logging
import os

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_URL = "https://open.er-api.com/v6/latest/"

dp = Dispatcher()

POPULAR = ["USD", "EUR", "RUB", "GBP", "KZT", "TRY"]


def rates_keyboard():
    builder = InlineKeyboardBuilder()
    for code in POPULAR:
        builder.button(text=code, callback_data=f"rate:{code}")
    builder.adjust(3)
    return builder.as_markup()


async def get_rates(base: str) -> dict | None:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_URL}{base}") as resp:
            data = await resp.json()
    if data.get("result") == "success":
        return data.get("rates")
    return None


def parse_query(text: str):
    """'100 USD UZS' -> (100.0, 'USD', 'UZS'). Miqdor ixtiyoriy, nishon standart UZS."""
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
        "• Konvertatsiya: <code>100 USD UZS</code> ko'rinishida yozing",
        reply_markup=rates_keyboard(),
    )


@dp.callback_query(F.data.startswith("rate:"))
async def rate(callback: CallbackQuery):
    code = callback.data.split(":")[1]
    rates = await get_rates(code)
    await callback.answer()
    if not rates or "UZS" not in rates:
        await callback.message.answer("❌ Kursni olishda xatolik yuz berdi.")
        return
    await callback.message.answer(f"💱 1 {code} = <b>{rates['UZS']:,.2f}</b> UZS")


@dp.message(F.text)
async def convert(message: Message):
    parsed = parse_query(message.text)
    if not parsed:
        await message.answer("❌ Namuna: <code>100 USD UZS</code>")
        return

    amount, base, target = parsed
    rates = await get_rates(base)
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
