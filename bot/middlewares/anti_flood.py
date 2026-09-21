import time
import logging
from collections import defaultdict, deque
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User, CallbackQuery, Message
from bot.config import ADMIN_IDS

logger = logging.getLogger(__name__)

class AntiFloodMiddleware(BaseMiddleware):
    """
    Enterprise-grade Anti-Flood and Anti-Bot Rate Limiting Middleware.
    - Prevents spam, DDoS attacks, and Telegram 429 Flood limits.
    - Rejects fake bot accounts (user.is_bot == True).
    - Throttles users exceeding 3 actions per second.
    - Bypasses rate limits for Super Admins.
    """
    def __init__(
        self,
        rate_limit_count: int = 3,
        rate_limit_window: float = 1.0,
        burst_limit_count: int = 7,
        burst_limit_window: float = 3.0
    ):
        super().__init__()
        self.rate_limit_count = rate_limit_count
        self.rate_limit_window = rate_limit_window
        self.burst_limit_count = burst_limit_count
        self.burst_limit_window = burst_limit_window
        # user_id -> deque of timestamps
        self._user_history: Dict[int, deque] = defaultdict(deque)
        self._last_warned: Dict[int, float] = {}
        self._last_callback: Dict[Any, float] = {}
        self._last_cleanup: float = time.time()

    def _cleanup_old_entries(self, now: float):
        """Periodically clean up inactive user records to keep memory usage minimal."""
        if now - self._last_cleanup < 60.0:
            return
        self._last_cleanup = now
        stale_threshold = now - 10.0
        keys_to_remove = []
        for uid, history in self._user_history.items():
            while history and history[0] < stale_threshold:
                history.popleft()
            if not history:
                keys_to_remove.append(uid)
        for uid in keys_to_remove:
            self._user_history.pop(uid, None)
            self._last_warned.pop(uid, None)

        cb_stale = [k for k, v in self._last_callback.items() if now - v > 5.0]
        for k in cb_stale:
            self._last_callback.pop(k, None)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user: User = data.get("event_from_user") or getattr(event, "from_user", None)
        if not user:
            return await handler(event, data)

        # 1. Anti-Bot Account Shield: Never allow automated bot accounts to interact
        if user.is_bot:
            logger.warning(f"🛡️ [Anti-Bot Shield] Blocked automated bot interaction: @{user.username} (ID: {user.id})")
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer("⛔ Bots are not permitted / বট অ্যাকাউন্ট নিষিদ্ধ!", show_alert=True)
                except Exception:
                    pass
            return None

        # 2. Duplicate Callback Debounce: Prevent rapid double-taps on the same button (under 450ms)
        now = time.time()
        event_data = getattr(event, "data", None)
        if isinstance(event, CallbackQuery) and event_data:
            cb_key = (user.id, event_data)
            last_cb_time = self._last_callback.get(cb_key, 0.0)
            if now - last_cb_time < 0.45:
                logger.debug(f"Debounced duplicate tap on {event_data} for user {user.id}")
                try:
                    await event.answer()
                except Exception:
                    pass
                return None
            self._last_callback[cb_key] = now

        # 3. Super Admin Bypass: No rate limits for bot owners
        if user.id in ADMIN_IDS:
            return await handler(event, data)

        now = time.time()
        self._cleanup_old_entries(now)

        history = self._user_history[user.id]
        # Remove timestamps older than burst window
        while history and history[0] < (now - self.burst_limit_window):
            history.popleft()

        # Check 1-second short window
        recent_count = sum(1 for t in history if t >= (now - self.rate_limit_window))
        # Check 3-second burst window
        burst_count = len(history)

        if recent_count >= self.rate_limit_count or burst_count >= self.burst_limit_count:
            # Throttle this request!
            logger.warning(f"🛡️ [Anti-Flood] Rate limit triggered for user {user.id} ({recent_count}/sec, {burst_count}/3sec)")
            
            # Send throttle warning if not warned in last 2 seconds
            last_warn = self._last_warned.get(user.id, 0.0)
            if now - last_warn >= 2.0:
                self._last_warned[user.id] = now
                if isinstance(event, CallbackQuery):
                    try:
                        await event.answer(
                            "⚠️ খুব দ্রুত ক্লিক করছেন! অনুগ্রহ করে ১-২ সেকেন্ড অপেক্ষা করুন।\n"
                            "⚠️ Tapping too fast! Please slow down.",
                            show_alert=True
                        )
                    except Exception:
                        pass
                elif isinstance(event, Message):
                    try:
                        await event.answer(
                            "⚠️ <b>অনুগ্রহ করে কিছুক্ষণ অপেক্ষা করুন!</b>\n"
                            "খুব দ্রুত রিকোয়েস্ট পাঠানো হচ্ছে। কিছুক্ষণ পর আবার চেষ্টা করুন।",
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass
            return None

        # Record this action timestamp
        history.append(now)
        return await handler(event, data)
