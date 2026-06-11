# ── Main ─────────────────────────────────────────────────────────────

import asyncio
import os
import logging

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Просте налаштування логування
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Мінімальні обробники, щоб бот не падав через NameError.
# Ви можете розширити їхній функціонал пізніше.
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text("Привіт! Я бот карт-банку.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text("Напишіть повідомлення, і я відповім (поки що простий режим).")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Обробка CallbackQuery
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Натиснуто кнопку.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        txt = update.message.text or ""
        # Ехо-повідомлення як заглушка
        await update.message.reply_text(f"Отримано: {txt}")


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
    
    # Фікс для Python 3.14+ на Render
    try:
        asyncio.run(app.run_polling())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(app.run_polling())


if __name__ == "__main__":
    main()
