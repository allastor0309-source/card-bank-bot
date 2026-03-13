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


# ── Helpers ───────────────────────────────────────────────────────────────────

def extract_card_numbers(text: str) -> list[str]:
    """
    Витягує всі потенційні номери карток з тексту.
    Розбиває по пробілах, комах, крапках з комою та нових рядках.
    Повертає список рядків що містять тільки цифри (≥6 символів).
    """
    # Розбиваємо по будь-яких роздільниках: пробіл, кома, крапка з комою, новий рядок
    tokens = re.split(r"[\s,;]+", text.strip())
    results = []
    for token in tokens:
        digits = re.sub(r"\D", "", token)
        if len(digits) >= 6:
            results.append(digits)
    return results


# ── Handlers ─────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 Привіт! Я можу визначити банк за номером картки.\n\n"
        "Надішли мені <b>один або кілька номерів карток</b> — "
        "через пробіл, кому або з нового рядка.\n\n"
        "Приклад:\n"
        "<code>4149 4996 0000 0000</code>\n"
        "<code>5375 4141 0000 0000, 4111111111111111</code>\n\n"
        "⚠️ <i>Бот читає лише перші 8 цифр (BIN). "
        "Повний номер картки нікуди не зберігається.</i>",
        parse_mode="HTML",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "ℹ️ <b>Як користуватись:</b>\n\n"
        "• Надішли один або кілька номерів карток.\n"
        "• Роздільники: пробіл, кома, крапка з комою або новий рядок.\n"
        "• Пробіли всередині номера — не проблема.\n"
        "• Команди: /start, /help",
        parse_mode="HTML",
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()

    card_numbers = extract_card_numbers(text)

    if not card_numbers:
        await update.message.reply_text(
            "❌ Не знайдено жодного номера картки.\n"
            "Введи не менше 6 цифр."
        )
        return

    # Обмеження — не більше 10 карток за раз
    if len(card_numbers) > 10:
        await update.message.reply_text(
            "⚠️ Максимум 10 карток за один запит. "
            f"Ти надіслав {len(card_numbers)}, оброблю перші 10."
        )
        card_numbers = card_numbers[:10]

    if len(card_numbers) > 1:
        await update.message.reply_text(f"🔍 Знайдено {len(card_numbers)} карток. Шукаю…")
    else:
        await update.message.reply_text("🔍 Шукаю інформацію…")

    for i, digits in enumerate(card_numbers, start=1):
        data = lookup_bin(digits)

        masked = digits[:6] + "••••••" + digits[-2:] if len(digits) >= 8 else digits

        if data is None:
            reply = (
                f"<b>Картка {i}:</b> <code>{masked}</code>\n"
                "⚠️ Інформацію не знайдено. Перевір номер або спробуй пізніше."
            )
        else:
            bin_info = format_bin_info(data)
            header = f"<b>Картка {i}:</b> <code>{masked}</code>\n"
            reply = header + bin_info

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
