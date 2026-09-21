import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DATABASE_PATH"] = "test_cmd_breakout.sqlite3"

from bot.database.db import (
    init_db, save_user, create_poll, get_user_polls
)
from bot.config import ADMIN_IDS
from bot.handlers.poll_create import check_command_breakout, process_candidates
from bot.templates import render_start_text, render_help_text, strip_tg_emoji_tags


class TestCommandBreakoutAndCleanHome(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        await init_db()
        await save_user(user_id=12345, username="creator1", first_name="User1", last_name="")
        await save_user(user_id=67890, username="creator2", first_name="User2", last_name="")

    async def asyncTearDown(self):
        db_path = "test_cmd_breakout.sqlite3"
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except Exception:
                pass

    async def test_cmd_cancel_in_fsm(self):
        msg = AsyncMock()
        msg.text = "/cancel"
        msg.answer = AsyncMock()
        state = AsyncMock()
        handled = await check_command_breakout(msg, state)
        self.assertTrue(handled)
        state.clear.assert_awaited_once()

    async def test_cmd_start_in_fsm(self):
        msg = AsyncMock()
        msg.text = "/start"
        msg.from_user.id = 12345
        msg.from_user.full_name = "User One"
        msg.from_user.first_name = "User"
        msg.answer = AsyncMock()
        msg.bot.get_me = AsyncMock(return_value=MagicMock(username="propollbot"))
        state = AsyncMock()
        handled = await check_command_breakout(msg, state)
        self.assertTrue(handled)
        state.clear.assert_awaited_once()

    async def test_per_user_my_polls_isolation(self):
        # Creator 1 creates a poll
        pid1 = await create_poll(12345, -100123, "Chan 1", "ch1", "Poll 1", ["Opt 1", "Opt 2"])
        # Creator 2 creates a poll
        pid2 = await create_poll(67890, -100456, "Chan 2", "ch2", "Poll 2", ["Opt A", "Opt B"])

        # Creator 1 sees ONLY poll 1
        c1_polls = await get_user_polls(12345)
        c1_pids = [p["poll_id"] for p in c1_polls]
        self.assertIn(pid1, c1_pids)
        self.assertNotIn(pid2, c1_pids)

        # Creator 2 sees ONLY poll 2
        c2_polls = await get_user_polls(67890)
        c2_pids = [p["poll_id"] for p in c2_polls]
        self.assertIn(pid2, c2_pids)
        self.assertNotIn(pid1, c2_pids)

        # If user is in ADMIN_IDS, they see both polls
        admin_id = next(iter(ADMIN_IDS)) if ADMIN_IDS else 9999999
        ADMIN_IDS.add(admin_id)
        admin_polls = await get_user_polls(admin_id)
        admin_pids = [p["poll_id"] for p in admin_polls]
        self.assertIn(pid1, admin_pids)
        self.assertIn(pid2, admin_pids)

    async def test_start_dashboard_single_line_bullets(self):
        """Verify that home start dashboard has crisp single line bullets without multi-line breaks."""
        start_bn = await render_start_text("propollbot", lang="bn", user_name="TestAdmin")
        # Check that bullets are short and concise (measuring rendered text without HTML/tg-emoji markup tags)
        for line in start_bn.split("\n"):
            if line.startswith("•"):
                clean_line = strip_tg_emoji_tags(line)
                self.assertLess(len(clean_line), 75, f"Bullet line is too long for a single line: {clean_line}")

        start_en = await render_start_text("propollbot", lang="en", user_name="TestAdmin")
        for line in start_en.split("\n"):
            if line.startswith("•"):
                clean_line = strip_tg_emoji_tags(line)
                self.assertLess(len(clean_line), 75, f"Bullet line is too long for a single line: {clean_line}")

    async def test_help_guide_has_complete_details(self):
        """Verify that /help contains full detailed instructions."""
        help_bn = await render_help_text("propollbot", lang="bn")
        self.assertIn("বট ব্যবহারের সম্পূর্ণ নিয়মাবলী ও গাইড", help_bn)
        self.assertIn("১-ক্লিক এডমিন", help_bn)
        self.assertIn("ফোর্স সাবস্ক্রিপশন", help_bn)
        self.assertIn("অ্যান্টি-চিট শিল্ড", help_bn)

        help_en = await render_help_text("propollbot", lang="en")
        self.assertIn("Complete Bot Guide & Instructions", help_en)
        self.assertIn("1-Click Admin", help_en)
        self.assertIn("Force Subscription", help_en)
        self.assertIn("Anti-Cheat Shield", help_en)


if __name__ == "__main__":
    unittest.main()
