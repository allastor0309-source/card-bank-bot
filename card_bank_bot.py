"""
Telegram-бот для визначення банку по номеру картки.
Використовує публічний BIN lookup API (binlist.net).

Встановлення залежностей:
    pip install python-telegram-bot requests

Запуск:
    BOT_TOKEN=your_token python card_bank_bot.py
"""

import os
import re
import logging
import requests
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── BIN lookup ────────────────────────────────────────────────────────────────

def lookup_bin(card_number: str) -> dict | None:
    """
    Отримати інформацію про BIN через https://lookup.binlist.net
    Повертає словник або None при помилці.
    """
    bin_code = re.sub(r"\D", "", card_number)[:8]  # тільки цифри, перші 8
    if len(bin_code) < 6:
        return None

    url = f"https://lookup.binlist.net/{bin_code}"
    headers = {"Accept-Version": "3"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        return None
    except requests.RequestException as e:
        logger.error("BIN lookup error: %s", e)
        return None


def format_bin_info(data: dict) -> str:
    """Форматує відповідь BIN API у читабельний текст."""
    lines = []

    # Схема (Visa / Mastercard тощо)
    scheme = data.get("scheme", "").upper()
    card_type = data.get("type", "").capitalize()
    brand = data.get("brand", "")

    if scheme:
        lines.append(f"💳 <b>Платіжна система:</b> {scheme}")
    if card_type:
        lines.append(f"📋 <b>Тип картки:</b> {card_type}")
    if brand:
        lines.append(f"🏷 <b>Бренд:</b> {brand}")

    # Банк
    bank = data.get("bank", {})
    bank_name = bank.get("name")
    bank_url  = bank.get("url")
    bank_city = bank.get("city")
    bank_phone = bank.get("phone")

    if bank_name:
        lines.append(f"\n🏦 <b>Банк:</b> {bank_name}")
    if bank_city:
        lines.append(f"📍 <b>Місто:</b> {bank_city}")
    if bank_url:
        lines.append(f"🌐 <b>Сайт:</b> {bank_url}")
    if bank_phone:
        lines.append(f"📞 <b>Телефон:</b> {bank_phone}")

    # Країна
    country = data.get("country", {})
    country_name  = country.get("name")
    country_emoji = country.get("emoji", "")
    currency      = country.get("currency")

    if country_name:
        lines.append(f"\n🌍 <b>Країна:</b> {country_emoji} {country_name}")
    if currency:
        lines.append(f"💰 <b>Валюта:</b> {currency}")

    # Передоплачена?
    prepaid = data.get("prepaid")
    if prepaid is not None:
        lines.append(f"💵 <b>Передоплачена:</b> {'Так' if prepaid else 'Ні'}")

    return "\n".join(lines) if lines else "ℹ️ Інформація не знайдена."


# ── PrivatBank cardholder name ────────────────────────────────────────────────

def lookup_privat_name(card_number: str) -> str | None:
    """
    Отримати ім'я власника картки ПриватБанку через API переказів.
    Повертає рядок з іменем або None.
    """
    digits = re.sub(r"\D", "", card_number)
    if len(digits) != 16:
        return None

    try:
        # Endpoint який використовують платіжні сервіси для показу імені
        url = "https://api.privatbank.ua/p24api/accountCard"
        params = {"card": digits}
        resp = requests.get(url, params=params, timeout=10)
        logger.info("PrivatBank API status: %s, body: %s", resp.status_code, resp.text[:200])
        if resp.status_code == 200:
            data = resp.json()
            name = (
                data.get("name")
                or data.get("cardholder")
                or data.get("firstName", "") + " " + data.get("lastName", "")
            )
            name = name.strip()
            return name if name else None
        return None
    except Exception as e:
        logger.error("PrivatBank name lookup error: %s", e)
        return None


# ── Handlers ─────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 Привіт! Я можу визначити банк за номером картки.\n\n"
        "Надішли мені <b>номер картки</b> (або перші 6–16 цифр) — "
        "і я поверну інформацію про банк та платіжну систему.\n\n"
        "⚠️ <i>Бот читає лише перші 8 цифр (BIN). "
        "Повний номер картки нікуди не зберігається.</i>",
        parse_mode="HTML",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "ℹ️ <b>Як користуватись:</b>\n\n"
        "• Просто надішли номер картки або перші 6–8 цифр.\n"
        "• Пробіли та дефіси — не проблема, я їх прибираю.\n"
        "• Команди: /start, /help",
        parse_mode="HTML",
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()

    # Витягнути лише цифри
    digits = re.sub(r"\D", "", text)

    if len(digits) < 6:
        await update.message.reply_text(
            "❌ Введи не менше 6 цифр номера картки."
        )
        return

    await update.message.reply_text("🔍 Шукаю інформацію…")

    data = lookup_bin(digits)

    if data is None:
        await update.message.reply_text(
            "⚠️ Не вдалося знайти інформацію по цьому BIN.\n"
            "Перевір правильність номера або спробуй пізніше."
        )
        return

    reply = format_bin_info(data)

    # Спробувати отримати ім'я власника для карток ПриватБанку
    bank_name = (data.get("bank") or {}).get("name", "")
    if len(digits) == 16 and "privat" in bank_name.lower():
        cardholder = lookup_privat_name(digits)
        if cardholder:
            reply += f"\n\n👤 <b>Власник:</b> {cardholder}"

    await update.message.reply_text(reply, parse_mode="HTML")


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "Не знайдено BOT_TOKEN. "
            "Встанови змінну середовища: export BOT_TOKEN=your_token"
        )

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Бот запущено. Натисни Ctrl+C для зупинки.")
    app.run_polling()


if __name__ == "__main__":
    main()
