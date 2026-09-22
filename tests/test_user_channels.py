import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DATABASE_PATH"] = "test_user_channels.sqlite3"
os.environ["ADMIN_IDS"] = "99999999"

from aiogram.types import (
    User, Chat, Message, CallbackQuery, ChatMemberAdministrator,
    ChatMemberMember, ChatMemberLeft, ChatMemberUpdated, InlineKeyboardMarkup
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage, StorageKey

from bot.database.db import (
    init_db, save_channel, get_channel, get_user_all_channels,
    unlink_user_channel, set_channel_status, is_user_authorized_for_channel_db,
    record_user_channel_access
)
from bot.keyboards.inline import (
    build_main_menu, build_user_channels_keyboard,
    build_user_channel_detail_keyboard, build_user_channel_confirm_delete_keyboard
)
from bot.keyboards.reply import build_persistent_menu
from bot.handlers.user_channels import (
    show_user_channels, cb_user_my_channels, cb_user_chan_view,
    cb_user_chan_test, cb_user_chan_del, cb_user_chan_del_confirm,
    process_user_add_channel, UserChannelStates
)
from bot.handlers.start import on_my_chat_member_update


class TestUserChannels(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        if os.path.exists("test_user_channels.sqlite3"):
            try:
                os.remove("test_user_channels.sqlite3")
            except Exception:
                pass
        await init_db()

    async def asyncTearDown(self):
        if os.path.exists("test_user_channels.sqlite3"):
            try:
                os.remove("test_user_channels.sqlite3")
            except Exception:
                pass

    async def test_db_get_user_all_channels_and_isolation(self):
        """Test that get_user_all_channels returns active and inactive channels for the user only."""
        user_1 = 1111
        user_2 = 2222

        # User 1 channels
        await save_channel(chat_id=-100101, title="User 1 Active Chan", username="u1_active", added_by=user_1)
        await save_channel(chat_id=-100102, title="User 1 Inactive Chan", username="u1_inactive", added_by=user_1)
        await set_channel_status(-100102, 0)

        # User 2 channel
        await save_channel(chat_id=-100201, title="User 2 Channel", username="u2_chan", added_by=user_2)

        # 1. User 1 channels check
        u1_channels = await get_user_all_channels(user_1)
        u1_ids = [c["chat_id"] for c in u1_channels]
        self.assertEqual(len(u1_channels), 2)
        self.assertIn(-100101, u1_ids)
        self.assertIn(-100102, u1_ids)
        self.assertNotIn(-100201, u1_ids, "User 1 must NEVER see User 2's channels!")

        # 2. User 2 channels check
        u2_channels = await get_user_all_channels(user_2)
        u2_ids = [c["chat_id"] for c in u2_channels]
        self.assertEqual(len(u2_channels), 1)
        self.assertIn(-100201, u2_ids)
        self.assertNotIn(-100101, u2_ids)
        self.assertNotIn(-100102, u2_ids)

        # 3. Unlink channel
        await unlink_user_channel(user_1, -100101)
        u1_after = await get_user_all_channels(user_1)
        u1_after_ids = [c["chat_id"] for c in u1_after]
        self.assertNotIn(-100101, u1_after_ids)

    async def test_keyboards_contain_added_channels_button(self):
        """Test that build_main_menu and build_persistent_menu contain Added Channels."""
        # Check inline menu in all languages
        for lang in ["bn", "en", "hi", "ar", "ru"]:
            kb = build_main_menu(is_admin=False, bot_username="TestBot", lang=lang)
            all_callbacks = [
                btn.callback_data for row in kb.inline_keyboard for btn in row if btn.callback_data
            ]
            self.assertIn("menu_my_channels", all_callbacks, f"menu_my_channels missing in lang {lang}")

        # Check reply menu in all languages
        for lang in ["bn", "en", "hi", "ar", "ru"]:
            reply_kb = build_persistent_menu(lang=lang, is_admin=False)
            all_texts = [btn.text for row in reply_kb.keyboard for btn in row]
            has_channel_btn = any("Added Channels" in t or "যুক্ত চ্যানেল" in t or "जुड़े हुए चैनल" in t or "القنوات المضافة" in t or "Добавленные каналы" in t for t in all_texts)
            self.assertTrue(has_channel_btn, f"Added Channels text missing from reply menu in {lang}")

    async def test_user_chan_view_and_strict_security(self):
        """Test viewing channel details and ensuring unauthorized users are blocked."""
        owner_id = 5001
        stranger_id = 9002
        chan_id = -100555555

        await save_channel(chat_id=chan_id, title="Secret Club", username="secret_club", added_by=owner_id)

        # 1. Stranger tries to view channel
        cb_stranger = MagicMock(spec=CallbackQuery)
        cb_stranger.data = f"user_chan_view:{chan_id}"
        cb_stranger.from_user = User(id=stranger_id, is_bot=False, first_name="Stranger")
        cb_stranger.answer = AsyncMock()
        cb_stranger.message = MagicMock(spec=Message)
        cb_stranger.message.edit_text = AsyncMock()
        cb_stranger.bot = MagicMock()
        cb_stranger.bot.get_me = AsyncMock(return_value=MagicMock(username="TestBot"))

        await cb_user_chan_view(cb_stranger)
        cb_stranger.answer.assert_called_once()
        self.assertIn("অননুমোদিত", cb_stranger.answer.call_args[0][0])

        # 2. Owner views channel
        cb_owner = MagicMock(spec=CallbackQuery)
        cb_owner.data = f"user_chan_view:{chan_id}"
        cb_owner.from_user = User(id=owner_id, is_bot=False, first_name="Owner")
        cb_owner.answer = AsyncMock()
        cb_owner.message = MagicMock(spec=Message)
        cb_owner.message.edit_text = AsyncMock()
        cb_owner.bot = MagicMock()
        cb_owner.bot.get_me = AsyncMock(return_value=MagicMock(username="TestBot"))

        await cb_user_chan_view(cb_owner)
        cb_owner.message.edit_text.assert_called_once()
        call_text = cb_owner.message.edit_text.call_args[0][0]
        self.assertIn("Secret Club", call_text)
        self.assertIn(str(chan_id), call_text)

    async def test_on_my_chat_member_update_sends_user_notification(self):
        """Test that when a user adds the bot to a channel, the bot sends them a DM with the Added Channels button."""
        user_id = 77778888
        chan_id = -100777888

        bot_mock = MagicMock()
        bot_mock.send_message = AsyncMock()
        bot_mock.get_me = AsyncMock(return_value=MagicMock(username="TestBot"))

        admin_member = MagicMock(spec=ChatMemberAdministrator)
        admin_member.status = "administrator"
        admin_member.can_post_messages = True

        event = MagicMock(spec=ChatMemberUpdated)
        event.chat = Chat(id=chan_id, type="channel", title="VIP Channel", username="vip_chan")
        event.new_chat_member = admin_member
        event.from_user = User(id=user_id, is_bot=False, first_name="VIP Admin")
        event.bot = bot_mock

        await on_my_chat_member_update(event)

        # Verify channel saved in DB
        ch = await get_channel(chan_id)
        self.assertIsNotNone(ch)
        self.assertEqual(ch["title"], "VIP Channel")
        self.assertEqual(ch["is_active"], 1)

        # Verify access recorded for user
        self.assertTrue(await is_user_authorized_for_channel_db(user_id, chan_id))

        # Verify DM sent to user.id
        dm_calls = [
            c for c in bot_mock.send_message.call_args_list if c.kwargs.get("chat_id") == user_id
        ]
        self.assertTrue(len(dm_calls) >= 1, "Bot must send DM to user who added it to the channel!")
        dm_text = dm_calls[0].kwargs.get("text")
        self.assertIn("VIP Channel", dm_text)
        self.assertIn("যুক্ত হয়েছে", dm_text)

        # Verify DM has Added Channels button
        reply_markup = dm_calls[0].kwargs.get("reply_markup")
        self.assertIsInstance(reply_markup, InlineKeyboardMarkup)
        callbacks = [btn.callback_data for row in reply_markup.inline_keyboard for btn in row if btn.callback_data]
        self.assertIn("menu_my_channels", callbacks)

    async def test_error_free_manual_add_channel_validation(self):
        """Test manual channel addition validates bot admin, post messages, and user ownership before saving."""
        user_id = 123456
        bot_id = 987654

        storage = MemoryStorage()
        state = FSMContext(
            storage=storage,
            key=StorageKey(bot_id=bot_id, chat_id=user_id, user_id=user_id)
        )
        await state.set_state(UserChannelStates.add_channel)

        bot_mock = MagicMock()
        bot_mock.id = bot_id
        bot_mock.get_me = AsyncMock(return_value=MagicMock(id=bot_id, username="TestBot", first_name="TestBot"))

        target_chat = Chat(id=-100999888, type="channel", title="Manual Test Chan", username="manual_chan")
        bot_mock.get_chat = AsyncMock(return_value=target_chat)

        # 1. Failure: Bot is NOT an administrator
        bot_member_non_admin = MagicMock(spec=ChatMemberMember)
        bot_member_non_admin.status = "member"
        bot_mock.get_chat_member = AsyncMock(return_value=bot_member_non_admin)

        msg = MagicMock(spec=Message)
        msg.from_user = User(id=user_id, is_bot=False, first_name="Tester")
        msg.forward_from_chat = None
        msg.text = "@manual_chan"
        msg.bot = bot_mock
        msg.answer = AsyncMock(return_value=MagicMock(edit_text=AsyncMock()))

        await process_user_add_channel(msg, state)

        # State should still be add_channel because it failed
        current_state = await state.get_state()
        self.assertEqual(current_state, UserChannelStates.add_channel.state)

        # Channel should NOT be in DB
        ch_fail = await get_channel(-100999888)
        self.assertIsNone(ch_fail)

        # 2. Failure: Bot is admin, but USER is NOT an admin of the channel
        async def mock_get_chat_member(chat_id, member_id):
            if member_id == bot_id:
                adm = MagicMock(spec=ChatMemberAdministrator)
                adm.status = "administrator"
                adm.can_post_messages = True
                return adm
            else:
                mem = MagicMock(spec=ChatMemberMember)
                mem.status = "member"
                return mem

        bot_mock.get_chat_member = AsyncMock(side_effect=mock_get_chat_member)
        await process_user_add_channel(msg, state)

        # Channel still NOT in DB
        ch_fail2 = await get_channel(-100999888)
        self.assertIsNone(ch_fail2)

        # 3. Success: Bot is admin with Post Messages, User is Creator of the channel
        async def mock_get_chat_member_success(chat_id, member_id):
            if member_id == bot_id:
                adm = MagicMock(spec=ChatMemberAdministrator)
                adm.status = "administrator"
                adm.can_post_messages = True
                return adm
            else:
                creator = MagicMock(spec=ChatMemberAdministrator)
                creator.status = "creator"
                return creator

        bot_mock.get_chat_member = AsyncMock(side_effect=mock_get_chat_member_success)
        await process_user_add_channel(msg, state)

        # Channel MUST be in DB now
        ch_success = await get_channel(-100999888)
        self.assertIsNotNone(ch_success)
        self.assertEqual(ch_success["title"], "Manual Test Chan")
        self.assertEqual(ch_success["is_active"], 1)

        # State should be cleared
        self.assertIsNone(await state.get_state())


if __name__ == "__main__":
    unittest.main()
