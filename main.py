import asyncio
import logging
import sys

# Ensure UTF-8 console output for Windows cmd/powershell
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import BOT_TOKEN, ADMIN_IDS
from bot.database.db import init_db
from bot.handlers import register_all_handlers
from bot.middlewares import UserTrackerMiddleware, AntiFloodMiddleware

from logging.handlers import RotatingFileHandler

file_handler = RotatingFileHandler(
    "bot.log",
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8"
)
stream_handler = logging.StreamHandler(sys.stdout)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
    handlers=[stream_handler, file_handler]
)
logger = logging.getLogger(__name__)

async def main():
    if not BOT_TOKEN or BOT_TOKEN.startswith("YOUR_") or ":" not in BOT_TOKEN:
        logger.error(
            "\n"
            "===============================================================\n"
            "⚠️ [জরুরি] .env ফাইলে আপনার আসল BOT_TOKEN বসানো হয়নি!\n"
            "👉 অনুগ্রহ করে .env ফাইলটি নোটপ্যাডে ওপেন করুন এবং @BotFather\n"
            "   থেকে পাওয়া আপনার বটের API Token বসান।\n"
            "   উদাহরণ: BOT_TOKEN=7891234567:AAHdefGhIJKlmNoPQRsTUVwxyZ\n"
            "===============================================================\n"
        )
        return

    # 1. Initialize SQLite Database
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized successfully.")

    # 2. Setup Bot and Dispatcher
    try:
        bot = Bot(
            token=BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
    except Exception as e:
        logger.error(f"\n❌ [ভুল টোকেন] .env ফাইলের BOT_TOKEN টি সঠিক নয়: {e}\nঅনুগ্রহ করে @BotFather থেকে সঠিক টোকেন কপি করে বসান।\n")
        return
    dp = Dispatcher(storage=MemoryStorage())

    # 3. Register Security & Tracking Middlewares
    dp.message.middleware(AntiFloodMiddleware())
    dp.callback_query.middleware(AntiFloodMiddleware())
    dp.message.middleware(UserTrackerMiddleware())
    dp.callback_query.middleware(UserTrackerMiddleware())

    # 4. Register Handlers
    register_all_handlers(dp)

    # 5. Fetch bot info with automatic retry loop
    bot_info = None
    retry_count = 0
    max_retries = 10
    while not bot_info:
        try:
            bot_info = await bot.get_me()
            logger.info(f"Bot connected successfully! @{bot_info.username} ({bot_info.first_name})")
        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                logger.error(f"Failed to connect to Telegram API after {max_retries} attempts: {e}")
                await bot.session.close()
                return
            logger.warning(f"Telegram network/DNS error ({e}). Retrying in 3 seconds... ({retry_count}/{max_retries})")
            await asyncio.sleep(3)

    # 6. Configure Telegram Native Menu Button & Quick Commands
    from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat, MenuButtonCommands
    try:
        # Public commands visible to everyone (Strictly zero admin exposure)
        public_commands = [
            BotCommand(command="start", description="🏠 Start / মূল মেনু - Open Dashboard"),
            BotCommand(command="newpoll", description="➕ Create Poll - নতুন পোল তৈরি করুন"),
            BotCommand(command="mypolls", description="📊 My Polls - আমার পোলসমূহ"),
            BotCommand(command="icons", description="🎯 Button Icons - বাটন আইকন স্টাইল"),
            BotCommand(command="language", description="🌐 Language - ভাষা পরিবর্তন"),
            BotCommand(command="help", description="ℹ️ Help - ব্যবহারের গাইড"),
        ]
        await bot.set_my_commands(public_commands, scope=BotCommandScopeDefault())

        # Secret Admin Command exclusively registered for verified ADMIN_IDS
        admin_commands = public_commands + [
            BotCommand(command="admin", description="👑 Super Admin Panel [Confidential]")
        ]
        for admin_id in ADMIN_IDS:
            try:
                await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_id))
            except Exception as e:
                logger.debug(f"Could not register admin command scope for {admin_id}: {e}")

        await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        logger.info("Bot commands & native Chat Menu button registered successfully (Stealth admin scope enabled).")
    except Exception as e:
        logger.warning(f"Could not register Telegram bot commands: {e}")

    # Global Error Handler to log any unhandled exceptions to bot.log
    @dp.error()
    async def global_error_handler(event):
        exc = getattr(event, "exception", event)
        logger.error(f"❌ [GLOBAL BOT ERROR] Exception: {exc}", exc_info=exc)
        return True

    from bot.services.poll_closer import start_poll_timer_worker

    logger.info(
        f"\n"
        f"===============================================================\n"
        f"🟢 BOT IS FULLY ACTIVE & LISTENING! (বট সফলভাবে চালু আছে)\n"
        f"👉 Bot Username: @{bot_info.username} ({bot_info.first_name})\n"
        f"👉 Direct Telegram Link: https://t.me/{bot_info.username}\n"
        f"👉 Test Now: Open Telegram and send /start to test the bot.\n"
        f"👉 All logs and errors are permanently saved in: bot.log\n"
        f"===============================================================\n"
    )
    timer_task = asyncio.create_task(start_poll_timer_worker(bot))
    try:
        # Delete webhook if previously set to avoid conflict (with retry)
        for _ in range(3):
            try:
                await bot.delete_webhook(drop_pending_updates=True)
                break
            except Exception:
                await asyncio.sleep(2)

        logger.info("Listening for Telegram updates...")
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query", "chat_member", "my_chat_member"]
        )
    finally:
        timer_task.cancel()
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
    except Exception as e:
        logger.exception("Fatal exception in bot runtime: %s", e)
