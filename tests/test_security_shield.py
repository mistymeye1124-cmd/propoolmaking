import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DATABASE_PATH"] = "test_security_shield.sqlite3"
os.environ["ADMIN_IDS"] = "99999999"

from aiogram.types import User, CallbackQuery, Message, ChatMemberMember, ChatMemberLeft
from bot.middlewares.anti_flood import AntiFloodMiddleware
from bot.handlers.voting import check_membership
from bot.handlers.admin import AdminSecurityMiddleware, is_admin
from bot.database.db import init_db, cast_vote, create_poll, save_user, get_candidates


class TestSecurityShield(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        if os.path.exists("test_security_shield.sqlite3"):
            try:
                os.remove("test_security_shield.sqlite3")
            except Exception:
                pass
        await init_db()

    async def asyncTearDown(self):
        if os.path.exists("test_security_shield.sqlite3"):
            try:
                os.remove("test_security_shield.sqlite3")
            except Exception:
                pass

    async def test_anti_flood_rate_limiting(self):
        """Test AntiFloodMiddleware throttles users sending more than 3 actions/sec."""
        middleware = AntiFloodMiddleware(rate_limit_count=3, rate_limit_window=1.0)
        handler = AsyncMock(return_value="OK")

        normal_user = MagicMock(spec=User)
        normal_user.id = 11112222
        normal_user.is_bot = False
        normal_user.username = "normal_user"

        cb_event = AsyncMock(spec=CallbackQuery)
        cb_event.answer = AsyncMock()

        data = {"event_from_user": normal_user}

        # First 3 actions must pass
        res1 = await middleware(handler, cb_event, data)
        self.assertEqual(res1, "OK")
        res2 = await middleware(handler, cb_event, data)
        self.assertEqual(res2, "OK")
        res3 = await middleware(handler, cb_event, data)
        self.assertEqual(res3, "OK")

        # 4th action immediately within the same second must be THROTTLED
        res4 = await middleware(handler, cb_event, data)
        self.assertIsNone(res4, "4th action must be dropped/throttled by anti-flood shield")
        cb_event.answer.assert_called()
        self.assertTrue(
            "খুব দ্রুত" in cb_event.answer.call_args[0][0] or
            "fast" in cb_event.answer.call_args[0][0].lower()
        )

    async def test_anti_flood_admin_bypass(self):
        """Test Super Admins bypass anti-flood rate limits."""
        middleware = AntiFloodMiddleware(rate_limit_count=3, rate_limit_window=1.0)
        handler = AsyncMock(return_value="OK")

        admin_user = MagicMock(spec=User)
        admin_user.id = 99999999  # in ADMIN_IDS
        admin_user.is_bot = False

        cb_event = AsyncMock(spec=CallbackQuery)
        data = {"event_from_user": admin_user}

        # 10 rapid actions from admin must all succeed without throttle
        for _ in range(10):
            res = await middleware(handler, cb_event, data)
            self.assertEqual(res, "OK")

    async def test_anti_bot_account_blocked(self):
        """Test automated bot accounts are completely blocked from voting or interacting."""
        middleware = AntiFloodMiddleware()
        handler = AsyncMock(return_value="OK")

        bot_user = MagicMock(spec=User)
        bot_user.id = 55556666
        bot_user.is_bot = True  # Scripted Telegram bot
        bot_user.username = "spam_bot"

        cb_event = AsyncMock(spec=CallbackQuery)
        cb_event.answer = AsyncMock()
        data = {"event_from_user": bot_user}

        res = await middleware(handler, cb_event, data)
        self.assertIsNone(res, "Bot account must be rejected by anti-bot shield")
        handler.assert_not_called()

    async def test_strict_force_sub_anti_cheat(self):
        """Test check_membership strictly rejects non-participants, left members, and exceptions."""
        bot = AsyncMock()

        # 1. Real member -> True
        member = MagicMock(spec=ChatMemberMember)
        member.status = "member"
        bot.get_chat_member = AsyncMock(return_value=member)
        self.assertTrue(await check_membership(bot, -100123, 1001))

        # 2. Left member -> False
        left = MagicMock(spec=ChatMemberLeft)
        left.status = "left"
        bot.get_chat_member = AsyncMock(return_value=left)
        self.assertFalse(await check_membership(bot, -100123, 1002))

        # 3. Exception (USER_NOT_PARTICIPANT / user not found) -> False (NO BYPASS!)
        bot.get_chat_member = AsyncMock(side_effect=Exception("Bad Request: USER_NOT_PARTICIPANT"))
        self.assertFalse(await check_membership(bot, -100123, 1003))

        bot.get_chat_member = AsyncMock(side_effect=Exception("Bad Request: user not found"))
        self.assertFalse(await check_membership(bot, -100123, 1004))

    async def test_concurrent_vote_atomic_lock(self):
        """Test atomic vote locking prevents double voting and cleanly maps UNIQUE error."""
        poll_id = await create_poll(
            creator_id=9999,
            target_chat_id=-100999,
            target_chat_title="Test Chat",
            target_chat_username="testchat",
            title="Presidential Contest",
            candidates=["Candidate 1", "Candidate 2"],
            part_number=1
        )

        voter_id = 77778888
        cands = await get_candidates(poll_id)
        cid1 = cands[0]["candidate_id"]
        cid2 = cands[1]["candidate_id"]

        # First vote succeeds
        ok1, reason1 = await cast_vote(poll_id, cid1, voter_id)
        self.assertTrue(ok1)
        self.assertEqual(reason1, "VOTE_CAST")

        # Second vote from same voter fails cleanly as ALREADY_VOTED
        ok2, reason2 = await cast_vote(poll_id, cid2, voter_id)
        self.assertFalse(ok2)
        self.assertEqual(reason2, "ALREADY_VOTED")

    async def test_zero_trust_admin_guard(self):
        """Test AdminSecurityMiddleware drops non-admin requests with Access Denied."""
        middleware = AdminSecurityMiddleware()
        handler = AsyncMock(return_value="ADMIN_OK")

        # Non-admin
        stranger = MagicMock(spec=User)
        stranger.id = 123456
        cb_event = AsyncMock(spec=CallbackQuery)
        cb_event.answer = AsyncMock()

        res_stranger = await middleware(handler, cb_event, {"event_from_user": stranger})
        self.assertIsNone(res_stranger)
        cb_event.answer.assert_called()
        # Stealth verification: silent answer with no disclosure of admin privileges
        self.assertEqual(len(cb_event.answer.call_args[0]), 0)
        handler.assert_not_called()

        # Verified Super Admin
        admin = MagicMock(spec=User)
        admin.id = 99999999
        res_admin = await middleware(handler, cb_event, {"event_from_user": admin})
        self.assertEqual(res_admin, "ADMIN_OK")


if __name__ == "__main__":
    unittest.main()
