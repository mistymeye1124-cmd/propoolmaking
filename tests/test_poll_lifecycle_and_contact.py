import asyncio
import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import CallbackQuery, User

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DATABASE_PATH"] = "test_lifecycle.sqlite3"

from bot.database.db import (
    init_db, save_user, create_poll, end_poll, get_poll, get_user_polls,
    cleanup_expired_ended_polls, delete_poll_by_id, delete_user_ended_polls,
    get_db
)
from bot.middlewares.anti_flood import AntiFloodMiddleware
from bot.templates import render_poll_ended, render_winner_announcement

class TestPollLifecycleAndContact(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        await init_db()
        async with get_db() as db:
            await db.execute("DELETE FROM votes")
            await db.execute("DELETE FROM candidates")
            await db.execute("DELETE FROM polls")
            await db.execute("DELETE FROM users")
            await db.commit()
        await save_user(user_id=111222, username="creator_one", first_name="Creator", last_name="One")
        await save_user(user_id=333444, username="other_user", first_name="Other", last_name="User")

    async def asyncTearDown(self):
        db_path = "test_lifecycle.sqlite3"
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except Exception:
                pass

    async def test_auto_cleanup_expired_ended_polls(self):
        """Verify polls ended > 2 days ago are automatically deleted, while recent/active are kept."""
        # 1. Create 3 polls
        pid1 = await create_poll(
            creator_id=111222, target_chat_id=-1001, target_chat_title="Chan 1",
            target_chat_username="chan1", title="Active Poll", candidates=["Option A", "Option B"]
        )
        pid2 = await create_poll(
            creator_id=111222, target_chat_id=-1001, target_chat_title="Chan 1",
            target_chat_username="chan1", title="Recent Ended Poll", candidates=["Option A", "Option B"]
        )
        pid3 = await create_poll(
            creator_id=111222, target_chat_id=-1001, target_chat_title="Chan 1",
            target_chat_username="chan1", title="Expired Ended Poll", candidates=["Option A", "Option B"]
        )

        await end_poll(pid2)
        await end_poll(pid3)

        # Manually set pid2 ended 1 day ago (24 hrs) and pid3 ended 3 days ago (72 hrs)
        one_day_ago = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        three_days_ago = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")

        async with get_db() as conn:
            await conn.execute("UPDATE polls SET ended_at = ? WHERE poll_id = ?", (one_day_ago, pid2))
            await conn.execute("UPDATE polls SET ended_at = ? WHERE poll_id = ?", (three_days_ago, pid3))
            await conn.commit()

        # Run cleanup (2 days threshold)
        deleted_count = await cleanup_expired_ended_polls(days=2)
        self.assertEqual(deleted_count, 1)

        # Verify: pid1 (active) and pid2 (1 day ago) exist, pid3 (3 days ago) is gone
        self.assertIsNotNone(await get_poll(pid1))
        self.assertIsNotNone(await get_poll(pid2))
        self.assertIsNone(await get_poll(pid3))

    async def test_manual_delete_poll_by_id(self):
        """Verify creator can delete individual poll and non-creators are rejected."""
        pid = await create_poll(
            creator_id=111222, target_chat_id=-1001, target_chat_title="Chan 1",
            target_chat_username="chan1", title="Delete Me", candidates=["Cand 1", "Cand 2"]
        )

        # Attempt deletion by different user
        fail_del = await delete_poll_by_id(pid, creator_id=333444)
        self.assertFalse(fail_del)
        self.assertIsNotNone(await get_poll(pid))

        # Deletion by owner
        success_del = await delete_poll_by_id(pid, creator_id=111222)
        self.assertTrue(success_del)
        self.assertIsNone(await get_poll(pid))

    async def test_delete_user_ended_polls(self):
        """Verify delete_user_ended_polls only purges ended polls and preserves active ones."""
        pid_active = await create_poll(
            creator_id=111222, target_chat_id=-1001, target_chat_title="Chan 1",
            target_chat_username="chan1", title="Keep Active", candidates=["A", "B"]
        )
        pid_ended1 = await create_poll(
            creator_id=111222, target_chat_id=-1001, target_chat_title="Chan 1",
            target_chat_username="chan1", title="Ended 1", candidates=["A", "B"]
        )
        pid_ended2 = await create_poll(
            creator_id=111222, target_chat_id=-1001, target_chat_title="Chan 1",
            target_chat_username="chan1", title="Ended 2", candidates=["A", "B"]
        )

        await end_poll(pid_ended1)
        await end_poll(pid_ended2)

        deleted = await delete_user_ended_polls(111222)
        self.assertEqual(deleted, 2)

        remaining = await get_user_polls(111222)
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["poll_id"], pid_active)

    async def test_contact_id_rendering_username_and_numeric_id(self):
        """Verify contact ID is properly rendered with username and tg://user?id= links."""
        # 1. With Telegram @username
        txt_ended_user = await render_poll_ended(
            title="Channel Contest",
            winner="🥇 Winner A (50 votes)",
            votes=50,
            bot_username="propollbot",
            lang="en",
            creator_id=111222,
            contact_username="giveaway_host"
        )
        self.assertIn("giveaway_host", txt_ended_user)
        self.assertIn("https://t.me/giveaway_host", txt_ended_user)

        announcement_user = await render_winner_announcement(
            title="Channel Contest",
            top_winners=[{"name": "Winner A", "votes_count": 50}],
            total_votes=50,
            bot_username="propollbot",
            lang="en",
            creator_id=111222,
            contact_username="@giveaway_host"
        )
        self.assertIn("https://t.me/giveaway_host", announcement_user)

        # 2. With numeric Telegram ID
        txt_ended_id = await render_poll_ended(
            title="ID Contest",
            winner="🥇 Winner B (20 votes)",
            votes=20,
            bot_username="propollbot",
            lang="bn",
            creator_id=111222,
            contact_username="id_987654321"
        )
        self.assertIn("tg://user?id=987654321", txt_ended_id)

        announcement_id = await render_winner_announcement(
            title="ID Contest",
            top_winners=[{"name": "Winner B", "votes_count": 20}],
            total_votes=20,
            bot_username="propollbot",
            lang="en",
            creator_id=111222,
            contact_username="987654321"
        )
        self.assertIn("tg://user?id=987654321", announcement_id)

    async def test_anti_flood_duplicate_callback_debounce(self):
        """Verify duplicate callbacks within 450ms are debounced and answered immediately."""
        middleware = AntiFloodMiddleware()
        handler_mock = AsyncMock(return_value="OK")

        user = User(id=555, is_bot=False, first_name="Clicker")
        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = user
        cb.data = "view_poll:100"
        cb.answer = AsyncMock()

        # First tap -> Should pass to handler
        res1 = await middleware(handler_mock, cb, {})
        self.assertEqual(res1, "OK")
        self.assertEqual(handler_mock.call_count, 1)

        # Immediate second tap (rapid double click within 450ms) -> Should debounce and NOT execute handler
        res2 = await middleware(handler_mock, cb, {})
        self.assertIsNone(res2)
        self.assertEqual(handler_mock.call_count, 1)
        cb.answer.assert_called()

if __name__ == "__main__":
    unittest.main()
