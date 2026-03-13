"""
Telegram-бот для визначення банку по номеру картки або IBAN.
Fallback ланцюжок BIN: Neutrino → moocher.io → BIN/IP Checker → CC BIN Checker → binlist.net
IBAN: перевірка контрольної суми + lookup через api.iban.com

Змінні середовища:
    BOT_TOKEN      — токен Telegram бота
    RAPIDAPI_KEY   — ключ RapidAPI (X-RapidAPI-Key)
"""

import os
import re
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")

# ── IBAN helpers ──────────────────────────────────────────────────────────────

IBAN_LENGTHS = {
    "AL": 28, "AD": 24, "AT": 20, "AZ": 28, "BH": 22, "BY": 28, "BE": 16,
    "BA": 20, "BR": 29, "BG": 22, "CR": 22, "HR": 21, "CY": 28, "CZ": 24,
    "DK": 18, "DO": 28, "EG": 29, "SV": 28, "EE": 20, "FO": 18, "FI": 18,
    "FR": 27, "GE": 22, "DE": 22, "GI": 23, "GR": 27, "GL": 18, "GT": 28,
    "HU": 28, "IS": 26, "IQ": 23, "IE": 22, "IL": 23, "IT": 27, "JO": 30,
    "KZ": 20, "XK": 20, "KW": 30, "LV": 21, "LB": 28, "LI": 21, "LT": 20,
    "LU": 20, "MT": 31, "MR": 27, "MU": 30, "MD": 24, "MC": 27, "ME": 22,
    "NL": 18, "MK": 19, "NO": 15, "PK": 24, "PS": 29, "PL": 28, "PT": 25,
    "QA": 29, "RO": 24, "LC": 32, "SM": 27, "ST": 25, "SA": 24, "RS": 22,
    "SC": 31, "SK": 24, "SI": 19, "ES": 24, "SE": 24, "CH": 21, "TL": 23,
    "TN": 24, "TR": 26, "UA": 29, "AE": 23, "GB": 22, "VA": 22, "VG": 24,
}
# ── Таблиця МФО банcodes → назва банку (Україна) ─────────────────────────────

UA_MFO = {
    "300001": "Національний банк України",
    "300012": "Промінвестбанк",
    "300119": "Альянс",
    "300346": "Альфа-Банк",
    "300465": "Ощадбанк",
    "300506": "Перший Інвестиційний Банк",
    "300528": "ОТП Банк",
    "300539": "ІНГ Банк Україна",
    "300614": "Креді Агріколь Банк",
    "300647": "Банк Кліринговий Дім",
    "300658": "Піреус Банк МКБ",
    "305299": "ПриватБанк",
    "305749": "Кредит Дніпро",
    "305880": "Земельний Капітал",
    "307123": "Схід",
    "307350": "Конкорд",
    "307770": "А-Банк",
    "309858": "Укргазбанк",
    "311498": "Укрексімбанк",
    "312248": "Комінвестбанк",
    "313009": "Мотор-Банк",
    "313582": "Метабанк",
    "313849": "Індустриалбанк",
    "320984": "ПроКредит Банк",
    "320940": "Альтбанк",
    "321723": "БТА Банк",
    "322001": "Монобанк (Універсал Банк)",
    "322302": "IBOX bank",
    "322335": "Аркада",
    "322540": "Комерційний Індустріальний Банк",
    "325268": "Львів",
    "325365": "Кредобанк",
    "325990": "Оксі Банк",
    "328209": "Південний",
    "328760": "Місто Банк",
    "329138": "Укрсиббанк",
    "351005": "Укрсиббанк (АТ UKRSIBBANK)",
    "331401": "ПриватБанк (Полтава)",
    "331489": "Полтава-банк",
    "334851": "ПУМБ",
    "336310": "Ідея Банк",
    "339016": "Портал",
    "339050": "Крісталбанк",
    "351607": "Грант",
    "351629": "Мегабанк",
    "353100": "Полікомбанк",
    "353489": "Асвіо Банк",
    "377090": "Європейський Промисловий Банк",
    "380281": "Банк інвестицій і заощаджень",
    "380366": "Кредит Європа Банк",
    "380441": "Кредитвест Банк",
    "380526": "Глобус",
    "380548": "Агропросперис Банк",
    "380582": "Міжнародний Інвестиційний Банк",
    "380634": "АккордБанк",
    "380645": "Банк 3/4",
    "380731": "Дойче Банк ДБУ",
    "380838": "Правекс-Банк",
    "380894": "Альпарі Банк",
    "380946": "Авангард",
    "300711": "Райффайзен Банк",
    "380805": "Сенс Банк (Альфа-Банк)",
    "380775": "Таскомбанк",
    "322499": "Банк Кредит Дніпро",
    "380432": "Форвард Банк",
    "300131": "Укрінбанк",
    "321760": "МТБ Банк",
    "380483": "Банк Січ",
    "380596": "Sky Bank",
    "380643": "БанГрант",
    "300191": "Приватбанк філія",
}


def lookup_ua_bank_by_mfo(mfo_code: str) -> str | None:
    """Повертає назву банку за кодом МФО (6 цифр)."""
    return UA_MFO.get(mfo_code.strip().zfill(6))


# Офіційний план рахунків НБУ (Постанова Правління НБУ №89 від 11.09.2017)
# Клас 2 — Операції з клієнтами, Розділ 26 — Кошти клієнтів
ACCOUNT_TYPES = {
    # Група 260 — Кошти на вимогу суб'єктів господарювання
    "2600": "💼 Поточний рахунок суб'єкта господарювання (ФОП / юрособа)",
    "2601": "💼 Поточний рахунок управителя (довірче управління)",
    "2602": "💼 Кошти в розрахунках суб'єктів господарювання",
    "2603": "💼 Розподільчий рахунок суб'єкта господарювання",
    "2604": "💼 Цільові кошти до запитання суб'єктів господарювання",
    "2605": "💼 Рахунок суб'єкта господарювання для платіжних карток",
    "2606": "💼 Рахунок платника ПДВ",
    # Група 261 — Строкові кошти суб'єктів господарювання
    "2610": "💼 Короткостроковий депозит суб'єкта господарювання",
    "2615": "💼 Довгостроковий депозит суб'єкта господарювання",
    # Група 262 — Кошти на вимогу фізичних осіб
    "2620": "🧑 Поточний рахунок фізичної особи",
    "2622": "🧑 Кошти фізичної особи за рахунком умовного зберігання (ескроу)",
    "2625": "🧑 Рахунок фізичної особи для платіжних карток",
    # Група 263 — Строкові кошти фізичних осіб
    "2630": "🧑 Короткостроковий депозит фізичної особи",
    "2635": "🧑 Довгостроковий депозит фізичної особи",
    # Група 264 — Кошти виборчого фонду
    "2640": "🗳 Кошти виборчого фонду",
    # Група 265 — Кошти небанківських фінансових установ
    "2650": "🏛 Поточний рахунок небанківської фінансової установи",
    "2655": "🏛 Строковий рахунок небанківської фінансової установи",
    # Група 292 — Транзитні рахунки
    "2924": "🔄 Транзитний рахунок за операціями з платіжними картками",
}


def get_ua_account_type(prefix: str) -> str | None:
    """Повертає тип рахунку за першими 4 цифрами номера рахунку."""
    return ACCOUNT_TYPES.get(prefix[:4]) if prefix else None


def get_ua_mfo_from_iban(iban: str) -> str | None:
    """Витягує МФО з українського IBAN (позиції 4-9)."""
    clean = re.sub(r"\s", "", iban).upper()
    if clean.startswith("UA") and len(clean) >= 10:
        return clean[4:10]
    return None



def validate_iban(iban: str) -> bool:
    """Перевірка контрольної суми IBAN (MOD-97)."""
    iban = re.sub(r"\s", "", iban).upper()
    if len(iban) < 4:
        return False
    country = iban[:2]
    expected_len = IBAN_LENGTHS.get(country)
    if expected_len and len(iban) != expected_len:
        return False
    rearranged = iban[4:] + iban[:4]
    numeric = ""
    for ch in rearranged:
        if ch.isdigit():
            numeric += ch
        elif ch.isalpha():
            numeric += str(ord(ch) - ord("A") + 10)
        else:
            return False
    return int(numeric) % 97 == 1


def _iban_lookup_openiban(clean: str) -> dict | None:
    """openiban.com — безкоштовно, без ключа. Повертає банк, BIC, місто."""
    try:
        resp = requests.get(
            f"https://openiban.com/validate/{clean}",
            params={"getBIC": "true", "validateBankCode": "true"},
            timeout=10,
        )
        if resp.status_code == 200:
            d = resp.json()
            if d.get("valid") and d.get("bankData"):
                return {"_source": "openiban", **d}
    except Exception as e:
        logger.warning("openiban error: %s", e)
    return None


def _iban_lookup_apininjas(clean: str) -> dict | None:
    """api-ninjas.com — безкоштовний tier з API ключем."""
    api_key = os.environ.get("APININJAS_KEY", "")
    if not api_key:
        return None
    try:
        resp = requests.get(
            "https://api.api-ninjas.com/v1/iban",
            params={"iban": clean},
            headers={"X-Api-Key": api_key},
            timeout=10,
        )
        if resp.status_code == 200:
            d = resp.json()
            if d.get("bank_name") or d.get("bank_address"):
                return {"_source": "apininjas", **d}
    except Exception as e:
        logger.warning("api-ninjas IBAN error: %s", e)
    return None


def lookup_iban(iban: str) -> dict | None:
    """Fallback ланцюжок: openiban.com → api-ninjas."""
    clean = re.sub(r"\s", "", iban).upper()
    for fn in [_iban_lookup_openiban, _iban_lookup_apininjas]:
        result = fn(clean)
        if result:
            logger.info("IBAN lookup success via %s", result.get("_source"))
            return result
    return None


def format_iban_info(iban: str) -> str:
    """Форматує інформацію про IBAN — компактний блок."""
    clean = re.sub(r"\s", "", iban).upper()
    country_code = clean[:2]
    bban = clean[4:]
    pretty = " ".join(clean[i:i+4] for i in range(0, len(clean), 4))

    country_names = {
        "UA": "🇺🇦 Україна", "DE": "🇩🇪 Німеччина", "PL": "🇵🇱 Польща",
        "GB": "🇬🇧 Великобританія", "FR": "🇫🇷 Франція", "IT": "🇮🇹 Італія",
        "ES": "🇪🇸 Іспанія", "NL": "🇳🇱 Нідерланди", "BE": "🇧🇪 Бельгія",
        "CH": "🇨🇭 Швейцарія", "AT": "🇦🇹 Австрія", "SE": "🇸🇪 Швеція",
        "NO": "🇳🇴 Норвегія", "DK": "🇩🇰 Данія", "FI": "🇫🇮 Фінляндія",
        "CZ": "🇨🇿 Чехія", "SK": "🇸🇰 Словаччина", "HU": "🇭🇺 Угорщина",
        "RO": "🇷🇴 Румунія", "BG": "🇧🇬 Болгарія", "HR": "🇭🇷 Хорватія",
        "LT": "🇱🇹 Литва", "LV": "🇱🇻 Латвія", "EE": "🇪🇪 Естонія",
        "TR": "🇹🇷 Туреччина", "AE": "🇦🇪 ОАЕ", "SA": "🇸🇦 Саудівська Аравія",
        "IL": "🇮🇱 Ізраїль", "LU": "🇱🇺 Люксембург", "PT": "🇵🇹 Португалія",
        "GR": "🇬🇷 Греція", "IE": "🇮🇪 Ірландія", "MT": "🇲🇹 Мальта",
        "CY": "🇨🇾 Кіпр", "LI": "🇱🇮 Ліхтенштейн", "MC": "🇲🇨 Монако",
    }
    bank_code_len = {
        "UA": 6, "DE": 8, "PL": 8, "GB": 4, "FR": 5, "IT": 5,
        "ES": 4, "NL": 4, "BE": 3, "CH": 5, "AT": 5, "SE": 3,
        "NO": 4, "DK": 4, "FI": 3, "CZ": 4, "SK": 4, "HU": 3,
        "LT": 5, "LV": 4, "EE": 2,
    }

    country_display = country_names.get(country_code, f"🌍 {country_code}")
    SEP = "━━━━━━━━━━━━━━━━━"

    lines = [
        f"🏦 <b>IBAN рахунок</b>",
        SEP,
        f"<code>{pretty}</code>",
        f"🌍 {country_display}  ✅ {len(clean)} символів",
        SEP,
    ]

    bank_len = bank_code_len.get(country_code)
    if bank_len:
        bank_code = bban[:bank_len]

        if country_code == "UA":
            bank_name_local = lookup_ua_bank_by_mfo(bank_code)
            account_prefix = bban[11:15] if len(bban) >= 15 else ""
            account_type = get_ua_account_type(account_prefix)

            if bank_name_local:
                lines.append(f"🏛 <b>{bank_name_local}</b>")
            lines.append(f"🔢 МФО: <code>{bank_code}</code>")
            if account_type:
                lines.append(f"👤 {account_type}")
            return "\n".join(lines)

        else:
            lines.append(f"🔢 Код банку: <code>{bank_code}</code>")

    # Зовнішній lookup для не-UA
    data = lookup_iban(clean)
    if data:
        src = data.get("_source", "")
        if src == "openiban":
            bd = data.get("bankData") or {}
            bank_name = bd.get("name")
            bic       = bd.get("bic")
            city      = bd.get("city")
            zip_code  = bd.get("zip")
        elif src == "apininjas":
            bank_name = data.get("bank_name")
            bic       = data.get("bic")
            city      = data.get("city")
            zip_code  = None
        else:
            bd = data.get("bank_data") or data.get("bankData") or {}
            bank_name = bd.get("bank") or bd.get("name")
            bic       = bd.get("bic") or bd.get("swift")
            city      = bd.get("city")
            zip_code  = bd.get("zip")

        if bank_name:
            lines.append(f"🏛 <b>{bank_name}</b>")
        if bic:
            lines.append(f"🔑 BIC/SWIFT: <code>{bic}</code>")
        if city:
            loc = f"{zip_code} {city}".strip() if zip_code else city
            lines.append(f"📍 {loc}")

    return "\n".join(lines)


def is_iban(text: str) -> bool:
    """Визначає чи схожий рядок на IBAN."""
    clean = re.sub(r"\s", "", text).upper()
    return bool(re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]{4,}$", clean)) and len(clean) >= 15


# ── BIN lookup providers ──────────────────────────────────────────────────────

def _rapidapi_headers(host: str) -> dict:
    return {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": host,
    }


def _lookup_neutrino(bin_code: str) -> dict | None:
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


# ── Normalize & Format BIN ────────────────────────────────────────────────────

def _normalize(data: dict) -> dict:
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
    """Форматує відповідь BIN API — компактний блок."""
    n = _normalize(data)
    SEP = "━━━━━━━━━━━━━━━━━"

    scheme    = n.get("scheme", "").upper()
    card_type = n.get("card_type", "").capitalize()
    level     = n.get("level", "").capitalize()
    bank_name = n.get("bank_name", "")
    bank_city = n.get("bank_city", "")
    bank_url  = n.get("bank_url", "")
    bank_phone= n.get("bank_phone", "")
    country_name  = n.get("country_name", "")
    country_emoji = n.get("country_emoji", "")
    currency      = n.get("currency", "")
    prepaid       = n.get("prepaid")

    # Рядок платіжної системи + тип + рівень
    card_meta = " · ".join(filter(None, [scheme, card_type, level]))

    # Рядок країни
    country_line = ""
    if country_name:
        flag = f"{country_emoji} " if country_emoji else ""
        cur  = f" · {currency}" if currency else ""
        country_line = f"{flag}{country_name}{cur}"

    lines = ["💳 <b>Банківська картка</b>", SEP]

    if card_meta:
        lines.append(f"💠 {card_meta}")
    if bank_name:
        lines.append(f"🏛 <b>{bank_name}</b>")
    if bank_city:
        lines.append(f"📍 {bank_city}")
    if bank_url or bank_phone:
        contact = "  ".join(filter(None, [bank_url, bank_phone]))
        lines.append(f"🌐 {contact}")

    lines.append(SEP)

    if country_line:
        lines.append(f"🌍 {country_line}")
    if prepaid is not None:
        lines.append(f"💵 Передоплачена: {'Так' if prepaid else 'Ні'}")

    return "\n".join(lines) if len(lines) > 2 else "ℹ️ Інформація не знайдена."


# ── Card number helpers ───────────────────────────────────────────────────────

def extract_card_numbers(text: str) -> list[str]:
    tokens = re.split(r"[\s,;]+", text.strip())
    results = []
    for token in tokens:
        digits = re.sub(r"\D", "", token)
        if len(digits) >= 6:
            results.append(digits)
    return results


# ── Keyboards ─────────────────────────────────────────────────────────────────

def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💳 Картка", callback_data="mode_card"),
            InlineKeyboardButton("🏦 IBAN рахунок", callback_data="mode_iban"),
        ]
    ])


# ── Handlers ─────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 Привіт! Я можу визначити банк за номером картки або IBAN рахунку.\n\n"
        "Обери тип або просто надішли номер — я визначу автоматично:",
        parse_mode="HTML",
        reply_markup=main_keyboard(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "ℹ️ <b>Як користуватись:</b>\n\n"
        "💳 <b>Картка:</b> надішли номер картки (6–16 цифр).\n"
        "   Можна кілька через пробіл, кому або новий рядок.\n\n"
        "🏦 <b>IBAN:</b> надішли IBAN рахунок.\n"
        "   Приклад: <code>UA213996220000026007233566001</code>\n\n"
        "Або натисни кнопку нижче для підказки.\n\n"
        "Команди: /start, /help",
        parse_mode="HTML",
        reply_markup=main_keyboard(),
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "mode_card":
        await query.message.reply_text(
            "💳 <b>Режим: Картка</b>\n\n"
            "Надішли номер картки або кілька через пробіл/кому:\n"
            "<code>4149 4996 0000 0000</code>\n"
            "<code>5375414100000000, 4111111111111111</code>",
            parse_mode="HTML",
        )
    elif query.data == "mode_iban":
        await query.message.reply_text(
            "🏦 <b>Режим: IBAN рахунок</b>\n\n"
            "Надішли IBAN рахунок:\n"
            "<code>UA213996220000026007233566001</code>\n"
            "<code>DE89370400440532013000</code>\n\n"
            "Я перевірю контрольну суму та визначу банк.",
            parse_mode="HTML",
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()

    # Автовизначення: IBAN чи картка?
    clean = re.sub(r"\s", "", text).upper()

    if is_iban(clean):
        # ── IBAN flow ──
        await update.message.reply_text("🔍 Перевіряю IBAN…")

        if not validate_iban(clean):
            await update.message.reply_text(
                "❌ <b>Невірний IBAN</b>\n\n"
                "Контрольна сума не співпадає. Перевір правильність номера.",
                parse_mode="HTML",
                reply_markup=main_keyboard(),
            )
            return

        reply = format_iban_info(clean)
        await update.message.reply_text(reply, parse_mode="HTML", reply_markup=main_keyboard())
        return

    # ── Card flow ──
    card_numbers = extract_card_numbers(text)

    if not card_numbers:
        await update.message.reply_text(
            "❓ Не вдалось розпізнати номер картки або IBAN.\n\n"
            "Обери тип вручну:",
            reply_markup=main_keyboard(),
        )
        return

    if len(card_numbers) > 10:
        await update.message.reply_text(
            f"⚠️ Максимум 10 карток за один запит. Оброблю перші 10 з {len(card_numbers)}."
        )
        card_numbers = card_numbers[:10]

    if len(card_numbers) > 1:
        await update.message.reply_text(f"🔍 Знайдено {len(card_numbers)} карток. Шукаю…")
    else:
        await update.message.reply_text("🔍 Шукаю інформацію…")

    for i, digits in enumerate(card_numbers, start=1):
        data = lookup_bin(digits)
        prefix = f"<b>Картка {i}:</b> <code>{digits}</code>\n" if len(card_numbers) > 1 else f"<code>{digits}</code>\n"

        if data is None:
            reply = prefix + "⚠️ Інформацію не знайдено. Перевір номер або спробуй пізніше."
        else:
            reply = prefix + format_bin_info(data)

        is_last = (i == len(card_numbers))
        await update.message.reply_text(
            reply,
            parse_mode="HTML",
            reply_markup=main_keyboard() if is_last else None,
        )


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("Не знайдено BOT_TOKEN.")

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Бот запущено.")
    app.run_polling()


if __name__ == "__main__":
    main()
