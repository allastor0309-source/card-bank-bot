import os
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

# Створюємо Application (без запуску polling)
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

# ---- aiohttp webhook сервер ----
async def webhook(request):
    """Обробляє POST-запити від Telegram"""
    try:
        data = await request.json()
        logger.info("Отримано update: %s", data.get("update_id"))
        update = Update.de_json(data, app.bot)
        await app.process_update(update)
        return web.Response(status=200)
    except Exception as e:
        logger.error("Помилка обробки webhook: %s", e)
        return web.Response(status=500)

async def setup_webhook(app_instance, webhook_url):
    """Встановлює webhook у Telegram"""
    await app_instance.bot.set_webhook(webhook_url, drop_pending_updates=True)
    logger.info("Webhook встановлено на %s", webhook_url)

async def main():
    # Отримуємо порт від Render (або 8080 за замовчуванням)
    port = int(os.environ.get("PORT", 8080))
    
    # Формуємо URL webhook (автоматично підставляє ім'я вашого сервісу)
    # Render задає змінну RENDER_EXTERNAL_HOSTNAME, якщо ні – використовуємо localhost (для тесту)
    render_hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
    if render_hostname:
        webhook_url = f"https://{render_hostname}/webhook"
    else:
        # Для локального тестування (не на Render) – використовуйте ngrok або реальний URL
        webhook_url = f"http://localhost:{port}/webhook"
        logger.warning("RENDER_EXTERNAL_HOSTNAME не встановлено, webhook URL = %s", webhook_url)
    
    # Встановлюємо webhook у Telegram
    await setup_webhook(app, webhook_url)
    
    # Запускаємо aiohttp сервер
    runner = web.AppRunner(web_app())
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Сервер запущено на порту %s", port)
    
    # Тримаємо сервер активним
    await asyncio.Event().wait()

def web_app():
    """Створює aiohttp додаток з маршрутом /webhook"""
    aiohttp_app = web.Application()
    aiohttp_app.router.add_post("/webhook", webhook)
    # Додаємо health-check для Render (не обов'язково, але корисно)
    async def health(request):
        return web.Response(text="OK")
    aiohttp_app.router.add_get("/", health)
    return aiohttp_app

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
