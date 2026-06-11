# card_bank_bot.py
# Повністю робоча версія для webhook на Render (Python 3.14+)

import os
import asyncio
import logging
from aiohttp import web
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# Налаштування логування
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Отримуємо токен з оточення
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Не знайдено BOT_TOKEN.")

# Створюємо Application
app = Application.builder().token(BOT_TOKEN).build()

# ---- Обробники команд ----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    logger.info("/start від %s (%s)", user.id, user.username)
    if update.message:
        await update.message.reply_text("Привіт! Я бот карт-банку (webhook).")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    logger.info("/help від %s (%s)", user.id, user.username)
    if update.message:
        await update.message.reply_text("Напишіть повідомлення, і я відповім.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    logger.info("callback від %s (%s)", user.id, user.username)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Натиснуто кнопку.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    text = update.message.text if update.message else ""
    logger.info("message від %s (%s): %s", user.id, user.username, text)
    if update.message:
        await update.message.reply_text(f"Отримано: {text}")

# Додаємо хендлери
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CallbackQueryHandler(button_handler))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# ---- Webhook обробник для aiohttp ----
async def webhook_handler(request):
    """Приймає POST-запити від Telegram"""
    try:
        data = await request.json()
        logger.info("Отримано update_id: %s", data.get("update_id"))
        update = Update.de_json(data, app.bot)
        await app.process_update(update)
        return web.Response(status=200)
    except Exception as e:
        logger.exception("Помилка в webhook_handler: %s", e)
        return web.Response(status=200)  # Завжди повертаємо 200, щоб уникнути повторів

# ---- Health check для Render ----
async def health(request):
    return web.Response(text="OK")

def create_aiohttp_app():
    """Створює aiohttp додаток з маршрутами"""
    aiohttp_app = web.Application()
    aiohttp_app.router.add_post("/webhook", webhook_handler)
    aiohttp_app.router.add_get("/", health)
    return aiohttp_app

# ---- Головна асинхронна функція ----
async def main_async():
    port = int(os.environ.get("PORT", 8080))
    render_hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
    
    if render_hostname:
        webhook_url = f"https://{render_hostname}/webhook"
    else:
        webhook_url = f"http://localhost:{port}/webhook"
        logger.warning("RENDER_EXTERNAL_HOSTNAME не встановлено, використовується локальний URL")
    
    # Встановлюємо webhook у Telegram
    await app.bot.set_webhook(webhook_url, drop_pending_updates=True)
    logger.info("Webhook встановлено на %s", webhook_url)
    
    # Запускаємо aiohttp сервер
    aiohttp_app = create_aiohttp_app()
    runner = web.AppRunner(aiohttp_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Сервер запущено на порту %s", port)
    
    # Тримаємо сервер активним
    await asyncio.Event().wait()

def main():
    """Точка входу для Render"""
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
