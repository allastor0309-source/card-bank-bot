"""
Telegram-бот для визначення банку по номеру картки.
Fallback ланцюжок: Neutrino → moocher.io → BIN/IP Checker → Credit Card BIN Checker → binlist.net

Встановлення залежностей:
    pip install python-telegram-bot requests

Змінні середовища:
    BOT_TOKEN      — токен Telegram бота
    RAPIDAPI_KEY   — ключ RapidAPI (X-RapidAPI-Key)
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

RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")

# ── BIN lookup providers ──────────────────────────────────────────────────────

def _rapidapi_headers(host: str) -> dict:
    return {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": host,
    }


def _lookup_neutrino(bin_code: str) -> dict | None:
    """Neutrino API — найповніша БД."""
    try:
        resp = requests.post(
            "https://neutrinoapi-bin-lookup.p.rapidapi.com/bin-lookup",
            headers=_rapidapi_headers("neutrinoapi-bin-lookup.p.rapidapi.com"),
            data={"bin-number": bin_code},
            timeout=10,
        )
        if resp.status_code == 200:
            d = resp.json()
            if d.get("valid"):
                return {"_source": "neutrino", **d}
    except Exception as e:
        logger.warning("Neutrino error: %s", e)
    return None


def _lookup_moocher(bin_code: str) -> dict | None:
    """moocher.io — рівень картки (Classic/Gold/Platinum)."""
    try:
        resp = requests.get(
            "https://bin-issuer-identification-number-database.p.rapidapi.com/",
            headers=_rapidapi_headers("bin-issuer-identification-number-database.p.rapidapi.com"),
            params={"bin": bin_code},
            timeout=10,
        )
        if resp.status_code == 200:
            d = resp.json()
            if d:
                return {"_source": "moocher", **d}
    except Exception as e:
        logger.warning("moocher.io error: %s", e)
    return None


def _lookup_bin_ip_checker(bin_code: str) -> dict | None:
    """BIN/IP Checker."""
    try:
        resp = requests.get(
            "https://bin-ip-checker.p.rapidapi.com/",
            headers=_rapidapi_headers("bin-ip-checker.p.rapidapi.com"),
            params={"bin": bin_code},
            timeout=10,
        )
        if resp.status_code == 200:
            d = resp.json()
            if d.get("BIN", {}).get("valid"):
                return {"_source": "bin_ip_checker", **d.get("BIN", {})}
    except Exception as e:
        logger.warning("BIN/IP Checker error: %s", e)
    return None


def _lookup_cc_bin_checker(bin_code: str) -> dict | None:
    """Credit Card BIN Checker."""
    try:
        resp = requests.get(
            "https://credit-card-bin-checker-validator.p.rapidapi.com/bin",
            headers=_rapidapi_headers("credit-card-bin-checker-validator.p.rapidapi.com"),
            params={"bin": bin_code},
            timeout=10,
        )
        if resp.status_code == 200:
            d = resp.json()
            if d:
                return {"_source": "cc_bin_checker", **d}
    except Exception as e:
        logger.warning("CC BIN Checker error: %s", e)
    return None


def _lookup_binlist(bin_code: str) -> dict | None:
    """binlist.net — безкоштовний fallback."""
    try:
        resp = requests.get(
            f"https://lookup.binlist.net/{bin_code}",
            headers={"Accept-Version": "3"},
            timeout=10,
        )
        if resp.status_code == 200:
            return {"_source": "binlist", **resp.json()}
    except Exception as e:
        logger.warning("binlist.net error: %s", e)
    return None


def lookup_bin(card_number: str) -> dict | None:
    """
    Спробувати всі провайдери по черзі, повернути перший успішний результат.
    Порядок: Neutrino → moocher.io → BIN/IP Checker → CC BIN Checker → binlist.net
    """
    bin_code = re.sub(r"\D", "", card_number)[:8]
    if len(bin_code) < 6:
        return None

    providers = []
    if RAPIDAPI_KEY:
        providers = [_lookup_neutrino, _lookup_moocher, _lookup_bin_ip_checker, _lookup_cc_bin_checker]
    providers.append(_lookup_binlist)

    for provider in providers:
        result = provider(bin_code)
        if result:
            logger.info("BIN lookup success via %s", result.get("_source", "unknown"))
            return result

    return None


# ── Normalize & Format ────────────────────────────────────────────────────────

def _normalize(data: dict) -> dict:
    """Нормалізує відповідь різних API до єдиного формату."""
    src = data.get("_source", "binlist")
    out = {}

    if src == "neutrino":
        out["scheme"]        = data.get("card-brand", "")
        out["card_type"]     = data.get("card-type", "")
        out["level"]         = data.get("card-category", "")
        out["prepaid"]       = data.get("is-prepaid")
        out["bank_name"]     = data.get("issuer", "")
        out["bank_city"]     = data.get("issuer-city", "")
        out["bank_url"]      = data.get("issuer-website", "")
        out["bank_phone"]    = data.get("issuer-phone", "")
        out["country_name"]  = data.get("country", "")
        out["country_emoji"] = data.get("country-flag", "")
        out["currency"]      = data.get("currency-code", "")

    elif src == "moocher":
        out["scheme"]        = data.get("scheme", "")
        out["card_type"]     = data.get("type", "")
        out["level"]         = data.get("level", "")
        out["prepaid"]       = data.get("prepaid")
        bank = data.get("bank") or {}
        out["bank_name"]     = bank.get("name", "") if isinstance(bank, dict) else str(bank)
        out["bank_url"]      = bank.get("url", "") if isinstance(bank, dict) else ""
        out["bank_city"]     = bank.get("city", "") if isinstance(bank, dict) else ""
        out["bank_phone"]    = bank.get("phone", "") if isinstance(bank, dict) else ""
        country = data.get("country") or {}
        out["country_name"]  = country.get("name", "") if isinstance(country, dict) else str(country)
        out["country_emoji"] = country.get("emoji", "") if isinstance(country, dict) else ""
        out["currency"]      = country.get("currency", "") if isinstance(country, dict) else ""

    elif src == "bin_ip_checker":
        out["scheme"]        = data.get("scheme", "")
        out["card_type"]     = data.get("type", "")
        out["level"]         = data.get("level", "")
        out["prepaid"]       = data.get("prepaid")
        issuer = data.get("issuer") or {}
        out["bank_name"]     = issuer.get("name", "") if isinstance(issuer, dict) else str(issuer)
        out["bank_url"]      = issuer.get("website", "") if isinstance(issuer, dict) else ""
        out["bank_phone"]    = issuer.get("phone", "") if isinstance(issuer, dict) else ""
        out["bank_city"]     = ""
        country = data.get("country") or {}
        out["country_name"]  = country.get("name", "") if isinstance(country, dict) else str(country)
        out["country_emoji"] = country.get("flag", "") if isinstance(country, dict) else ""
        out["currency"]      = country.get("currency", "") if isinstance(country, dict) else ""

    elif src == "cc_bin_checker":
        bin_data = data.get("BIN") or data
        out["scheme"]        = bin_data.get("scheme", "")
        out["card_type"]     = bin_data.get("type", "")
        out["level"]         = bin_data.get("level", "")
        out["prepaid"]       = bin_data.get("is_prepaid")
        issuer = bin_data.get("issuer") or {}
        out["bank_name"]     = issuer.get("name", "") if isinstance(issuer, dict) else str(issuer)
        out["bank_url"]      = issuer.get("website", "") if isinstance(issuer, dict) else ""
        out["bank_phone"]    = issuer.get("phone", "") if isinstance(issuer, dict) else ""
        out["bank_city"]     = ""
        country = bin_data.get("country") or {}
        out["country_name"]  = country.get("name", "") if isinstance(country, dict) else str(country)
        out["country_emoji"] = country.get("flag", "") if isinstance(country, dict) else ""
        out["currency"]      = country.get("currency", "") if isinstance(country, dict) else ""

    else:  # binlist
        out["scheme"]        = data.get("scheme", "")
        out["card_type"]     = data.get("type", "")
        out["level"]         = ""
        out["prepaid"]       = data.get("prepaid")
        bank = data.get("bank") or {}
        out["bank_name"]     = bank.get("name", "")
        out["bank_url"]      = bank.get("url", "")
        out["bank_city"]     = bank.get("city", "")
        out["bank_phone"]    = bank.get("phone", "")
        country = data.get("country") or {}
        out["country_name"]  = country.get("name", "")
        out["country_emoji"] = country.get("emoji", "")
        out["currency"]      = country.get("currency", "")

    return out


def format_bin_info(data: dict) -> str:
    """Форматує відповідь BIN API у читабельний текст."""
    n = _normalize(data)
    lines = []

    scheme    = n.get("scheme", "").upper()
    card_type = n.get("card_type", "").capitalize()
    level     = n.get("level", "").capitalize()

    if scheme:
        lines.append(f"💳 <b>Платіжна система:</b> {scheme}")
    if card_type:
        lines.append(f"📋 <b>Тип картки:</b> {card_type}")
    if level:
        lines.append(f"🎖 <b>Рівень:</b> {level}")

    bank_name  = n.get("bank_name", "")
    bank_city  = n.get("bank_city", "")
    bank_url   = n.get("bank_url", "")
    bank_phone = n.get("bank_phone", "")

    if bank_name:
        lines.append(f"\n🏦 <b>Банк:</b> {bank_name}")
    if bank_city:
        lines.append(f"📍 <b>Місто:</b> {bank_city}")
    if bank_url:
        lines.append(f"🌐 <b>Сайт:</b> {bank_url}")
    if bank_phone:
        lines.append(f"📞 <b>Телефон:</b> {bank_phone}")

    country_name  = n.get("country_name", "")
    country_emoji = n.get("country_emoji", "")
    currency      = n.get("currency", "")

    if country_name:
        flag = f" {country_emoji}" if country_emoji else ""
        lines.append(f"\n🌍 <b>Країна:</b>{flag} {country_name}")
    if currency:
        lines.append(f"💰 <b>Валюта:</b> {currency}")

    prepaid = n.get("prepaid")
    if prepaid is not None:
        lines.append(f"💵 <b>Передоплачена:</b> {'Так' if prepaid else 'Ні'}")

    return "\n".join(lines) if lines else "ℹ️ Інформація не знайдена."


# ── Helpers ───────────────────────────────────────────────────────────────────

def extract_card_numbers(text: str) -> list[str]:
    """
    Витягує всі потенційні номери карток з тексту.
    Розбиває по пробілах, комах, крапках з комою та нових рядках.
    """
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

        if data is None:
            reply = (
                f"<b>Картка {i}:</b> <code>{digits}</code>\n"
                "⚠️ Інформацію не знайдено. Перевір номер або спробуй пізніше."
            )
        else:
            bin_info = format_bin_info(data)
            header = f"<b>Картка {i}:</b> <code>{digits}</code>\n"
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
