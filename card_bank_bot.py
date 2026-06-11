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

# Налаштування логування
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Натиснуто кнопку.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    text = (update.message.text if update.message else None) or ""
    logger.info("message від %s (%s): %s", user.id if user else None, user.username if user else None, text)
    if update.message:
        await update.message.reply_text(f"Отримано: {text}")


async def main_async() -> None:
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("Не знайдено BOT_TOKEN.")

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Бот ініціалізовано, видаляємо webhook (якщо є)...")
    await app.bot.delete_webhook(drop_pending_updates=True)
    logger.info("Запускаємо polling...")
    await app.run_polling()


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
