import asyncio
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage, StorageKey
from aiogram.types import Chat, ChatMemberAdministrator, ChatMemberMember, Message, CallbackQuery, User

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Ensure test DB is used
os.environ["DATABASE_PATH"] = "test_channel_isolation.sqlite3"
os.environ["ADMIN_IDS"] = "99999999"

from bot.config import ADMIN_IDS
from bot.database.db import (
    init_db, save_channel, get_user_selectable_channels,
    is_user_authorized_for_channel_db, record_user_channel_access,
    get_db
)
from bot.handlers.poll_create import validate_and_proceed_channel, PollCreationState


class TestChannelIsolation(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        if os.path.exists("test_channel_isolation.sqlite3"):
            try:
                os.remove("test_channel_isolation.sqlite3")
            except Exception:
                pass
        await init_db()

    async def asyncTearDown(self):
        if os.path.exists("test_channel_isolation.sqlite3"):
            try:
                os.remove("test_channel_isolation.sqlite3")
            except Exception:
                pass

    async def test_strict_channel_visibility_isolation(self):
        """Test that User A and User B can only see their own channels."""
        user_a = 1001
        user_b = 2002
        super_admin = 99999999

        # User A connects Channel A
        await save_channel(
            chat_id=-100111111,
            title="Channel Alpha (User A)",
            username="channel_alpha",
            added_by=user_a
        )

        # User B connects Channel B
        await save_channel(
            chat_id=-100222222,
            title="Channel Beta (User B)",
            username="channel_beta",
            added_by=user_b
        )

        # 1. Check selectable channels for User A
        channels_a = await get_user_selectable_channels(user_a)
        channel_ids_a = [c["chat_id"] for c in channels_a]
        self.assertIn(-100111111, channel_ids_a, "User A must see Channel A")
        self.assertNotIn(-100222222, channel_ids_a, "User A must NEVER see User B's Channel B!")

        # 2. Check selectable channels for User B
        channels_b = await get_user_selectable_channels(user_b)
        channel_ids_b = [c["chat_id"] for c in channels_b]
        self.assertIn(-100222222, channel_ids_b, "User B must see Channel B")
        self.assertNotIn(-100111111, channel_ids_b, "User B must NEVER see User A's Channel A!")

        # 3. Check authorization helper
        self.assertTrue(await is_user_authorized_for_channel_db(user_a, -100111111))
        self.assertFalse(await is_user_authorized_for_channel_db(user_b, -100111111))
        self.assertTrue(await is_user_authorized_for_channel_db(user_b, -100222222))
        self.assertFalse(await is_user_authorized_for_channel_db(user_a, -100222222))

        # 4. Super admin strict isolation check:
        # Super admin did NOT connect Channel A or B, so they must NOT see them or have unauthorized DB access!
        self.assertFalse(await is_user_authorized_for_channel_db(super_admin, -100111111))
        admin_channels = await get_user_selectable_channels(super_admin)
        admin_ids = [c["chat_id"] for c in admin_channels]
        self.assertNotIn(-100111111, admin_ids, "Super Admin must NOT see Channel A added by User A")
        self.assertNotIn(-100222222, admin_ids, "Super Admin must NOT see Channel B added by User B")

        # When Super Admin connects their own channel:
        await save_channel(
            chat_id=-100999999,
            title="Super Admin Channel",
            username="admin_chan",
            added_by=super_admin
        )
        admin_channels_after = await get_user_selectable_channels(super_admin)
        admin_ids_after = [c["chat_id"] for c in admin_channels_after]
        self.assertIn(-100999999, admin_ids_after, "Super Admin must see their own added channel")
        self.assertNotIn(-100111111, admin_ids_after, "Super Admin must still not see User A's channel")
        self.assertNotIn(-100222222, admin_ids_after, "Super Admin must still not see User B's channel")

    async def test_co_admin_access_grant(self):
        """Test that multiple genuine admins can be granted access without collision."""
        owner = 1001
        co_admin = 3003
        stranger = 4004

        await save_channel(
            chat_id=-100333333,
            title="Team Channel",
            username="team_chan",
            added_by=owner
        )

        # Before granting, co_admin has no access
        self.assertFalse(await is_user_authorized_for_channel_db(co_admin, -100333333))

        # Record co_admin
        await record_user_channel_access(co_admin, -100333333)

        # Now both owner and co_admin have access
        self.assertTrue(await is_user_authorized_for_channel_db(owner, -100333333))
        self.assertTrue(await is_user_authorized_for_channel_db(co_admin, -100333333))
        self.assertFalse(await is_user_authorized_for_channel_db(stranger, -100333333))

        # Both see it in their selectable list
        channels_owner = await get_user_selectable_channels(owner)
        channels_coadmin = await get_user_selectable_channels(co_admin)
        channels_stranger = await get_user_selectable_channels(stranger)

        self.assertIn(-100333333, [c["chat_id"] for c in channels_owner])
        self.assertIn(-100333333, [c["chat_id"] for c in channels_coadmin])
        self.assertNotIn(-100333333, [c["chat_id"] for c in channels_stranger])

    async def test_validate_and_proceed_channel_blocks_unauthorized_user(self):
        """Test validate_and_proceed_channel rejects stranger attempting to post to someone else's channel."""
        storage = MemoryStorage()
        bot = AsyncMock()
        bot.id = 999
        bot_info = MagicMock()
        bot_info.username = "test_poll_bot"
        bot_info.first_name = "PollBot"
        bot.get_me = AsyncMock(return_value=bot_info)

        # Mock target chat
        chat = MagicMock(spec=Chat)
        chat.id = -100555555
        chat.title = "Target Secret Channel"
        chat.username = "secret_chan"
        chat.type = "channel"
        bot.get_chat = AsyncMock(return_value=chat)

        # Mock bot is admin in channel
        bot_admin = MagicMock(spec=ChatMemberAdministrator)
        bot_admin.status = "administrator"
        bot_admin.can_post_messages = True

        # Mock stranger is NOT admin in channel (just a normal member)
        stranger_member = MagicMock(spec=ChatMemberMember)
        stranger_member.status = "member"

        async def get_chat_member_side_effect(chat_id, user_id):
            if user_id == bot.id:
                return bot_admin
            elif user_id == 7777: # stranger
                return stranger_member
            return stranger_member

        bot.get_chat_member = AsyncMock(side_effect=get_chat_member_side_effect)

        # State for stranger
        key = StorageKey(bot_id=bot.id, chat_id=7777, user_id=7777)
        state = FSMContext(storage=storage, key=key)
        await state.set_state(PollCreationState.channel)

        message = AsyncMock(spec=Message)
        message.answer = AsyncMock()

        # Run validate_and_proceed_channel for stranger
        await validate_and_proceed_channel(
            bot=bot,
            target=-100555555,
            state=state,
            msg_or_cb=message,
            user_id=7777,
            is_callback=False
        )

        # Verify: State must NOT have advanced to duration!
        current_state = await state.get_state()
        self.assertNotEqual(current_state, PollCreationState.duration)
        self.assertEqual(current_state, PollCreationState.channel)

        # Verify error message sent to stranger
        message.answer.assert_called_once()
        sent_text = message.answer.call_args[0][0]
        self.assertTrue("অননুমোদিত চ্যানেল" in sent_text or "Access Denied" in sent_text)

    async def test_validate_and_proceed_channel_allows_verified_admin(self):
        """Test validate_and_proceed_channel allows actual channel admin."""
        storage = MemoryStorage()
        bot = AsyncMock()
        bot.id = 999
        bot_info = MagicMock()
        bot_info.username = "test_poll_bot"
        bot_info.first_name = "PollBot"
        bot.get_me = AsyncMock(return_value=bot_info)

        chat = MagicMock(spec=Chat)
        chat.id = -100666666
        chat.title = "Verified Admin Channel"
        chat.username = "verified_chan"
        chat.type = "channel"
        bot.get_chat = AsyncMock(return_value=chat)

        bot_admin = MagicMock(spec=ChatMemberAdministrator)
        bot_admin.status = "administrator"
        bot_admin.can_post_messages = True

        admin_user_member = MagicMock(spec=ChatMemberAdministrator)
        admin_user_member.status = "administrator"

        async def get_chat_member_side_effect(chat_id, user_id):
            if user_id == bot.id:
                return bot_admin
            elif user_id == 8888:
                return admin_user_member
            return None

        bot.get_chat_member = AsyncMock(side_effect=get_chat_member_side_effect)

        key = StorageKey(bot_id=bot.id, chat_id=8888, user_id=8888)
        state = FSMContext(storage=storage, key=key)
        await state.set_state(PollCreationState.channel)

        message = AsyncMock(spec=Message)
        message.answer = AsyncMock()

        # Run validate_and_proceed_channel for verified admin
        await validate_and_proceed_channel(
            bot=bot,
            target=-100666666,
            state=state,
            msg_or_cb=message,
            user_id=8888,
            is_callback=False
        )

        # Verify: State advanced to duration!
        current_state = await state.get_state()
        self.assertEqual(current_state, PollCreationState.duration)

        # Verify user was automatically granted and stored in user_channel_permissions
        self.assertTrue(await is_user_authorized_for_channel_db(8888, -100666666))


if __name__ == "__main__":
    unittest.main()
