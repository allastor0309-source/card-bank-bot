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
# Додаємо логування у кожний хендлер, щоб бачити активність у логах.
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    logger.info("/start від %s (%s)", user.id if user else None, user.username if user else None)
    if update.message:
        await update.message.reply_text("Привіт! Я бот карт-банку.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    logger.info("/help від %s (%s)", user.id if user else None, user.username if user else None)
    if update.message:
        await update.message.reply_text("Напишіть повідомлення, і я відповім (поки що простий режим).")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    logger.info("callback від %s (%s)", user.id if user else None, user.username if user else None)
    # Обробка CallbackQuery
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Натиснуто кнопку.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    text = (update.message.text if update.message else None) or ""
    logger.info("message від %s (%s): %s", user.id if user else None, user.username if user else None, text)
    if update.message:
        # Ехо-повідомлення як заглушка
        await update.message.reply_text(f"Отримано: {text}")


def main() -> None:
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("Не знайдено BOT_TOKEN.")

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Бот ініціалізовано, готуємось до запуску polling...")

    # Надійніший спосіб для різних версій Python/хостів: створюємо власний цикл і запускаємо в ньому
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        # Спробуємо видалити webhook (якщо був встановлений) щоб polling міг отримувати апдейти
        try:
            loop.run_until_complete(app.bot.delete_webhook(drop_pending_updates=True))
            logger.info("Webhook видалено (якщо існував)")
        except Exception as e:
            logger.debug("Помилка при delete_webhook (можливо не встановлений): %s", e)

        loop.run_until_complete(app.run_polling())
    finally:
        try:
            loop.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
