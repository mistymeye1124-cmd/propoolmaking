import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User, Message, CallbackQuery
from bot.database.db import save_user

logger = logging.getLogger(__name__)

class UserTrackerMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user: User = data.get("event_from_user")
        if user and not user.is_bot:
            await save_user(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name
            )
            # Log user action for real-time console & file tracking
            uname = f"@{user.username}" if user.username else f"{user.first_name} (ID: {user.id})"
            if isinstance(event, Message) and event.text:
                logger.info(f"📨 [MESSAGE] {uname} -> {event.text[:60]}")
            elif isinstance(event, CallbackQuery):
                logger.info(f"🔘 [BUTTON] {uname} clicked -> {event.data}")
        return await handler(event, data)
