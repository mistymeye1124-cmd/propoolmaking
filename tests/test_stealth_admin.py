import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.types import Message, CallbackQuery, User, InlineKeyboardMarkup

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock ADMIN_IDS before importing modules
os.environ["ADMIN_IDS"] = "99999999"
os.environ["BOT_TOKEN"] = "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ"

from bot.config import ADMIN_IDS
from bot.handlers.admin import is_admin, AdminSecurityMiddleware, cb_admin
from bot.handlers.start import (
    reply_btn_admin, reply_btn_brand, cb_user_set_icon_style, cb_set_icon_style
)
from bot.keyboards.inline import build_main_menu, build_icon_style_keyboard

class TestStealthAdmin(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.non_admin_id = 11112222
        self.admin_id = 99999999

    def test_is_admin_check(self):
        self.assertFalse(is_admin(self.non_admin_id))
        self.assertTrue(is_admin(self.admin_id))

    def test_main_menu_visibility(self):
        """Verify normal users NEVER see Admin Panel button in Main Menu."""
        # Non-admin
        user_menu = build_main_menu(is_admin=False, bot_username="PollTestBot", lang="bn")
        all_user_callbacks = [btn.callback_data for row in user_menu.inline_keyboard for btn in row if btn.callback_data]
        all_user_texts = [btn.text for row in user_menu.inline_keyboard for btn in row]
        self.assertNotIn("menu_admin", all_user_callbacks)
        self.assertFalse(any("panel" in t.lower() or "প্যানেল" in t or "👑" in t for t in all_user_texts))

        # Admin
        admin_menu = build_main_menu(is_admin=True, bot_username="PollTestBot", lang="bn")
        all_admin_callbacks = [btn.callback_data for row in admin_menu.inline_keyboard for btn in row if btn.callback_data]
        self.assertIn("menu_admin", all_admin_callbacks)

    async def test_stealth_admin_text_handling(self):
        """Verify non-admin sending admin text gets ZERO response (complete silence)."""
        msg = AsyncMock(spec=Message)
        msg.from_user = MagicMock(spec=User)
        msg.from_user.id = self.non_admin_id
        msg.answer = AsyncMock()

        # Non-admin sending '👑 Admin Panel'
        await reply_btn_admin(msg)
        msg.answer.assert_not_called()

        # Non-admin sending '🏷️ Brand & Link'
        await reply_btn_brand(msg)
        msg.answer.assert_not_called()

    async def test_stealth_unauthorized_callback_rejection(self):
        """Verify non-admin invoking admin callback receives silent answer (no leak)."""
        middleware = AdminSecurityMiddleware()
        handler = AsyncMock()

        cb = AsyncMock(spec=CallbackQuery)
        cb.answer = AsyncMock()
        user = MagicMock(spec=User)
        user.id = self.non_admin_id

        res = await middleware(handler, cb, {"event_from_user": user})
        self.assertIsNone(res)
        cb.answer.assert_called_once()
        # Silent answer: zero arguments passed
        self.assertEqual(len(cb.answer.call_args[0]), 0)
        handler.assert_not_called()

    @patch("bot.handlers.start.get_user_icon_style", new_callable=AsyncMock)
    @patch("bot.handlers.start.get_user_language", new_callable=AsyncMock)
    async def test_user_icon_style_access(self, mock_lang, mock_style):
        """Verify ANY regular user can access icon style settings freely."""
        mock_style.return_value = "dynamic"
        mock_lang.return_value = "bn"

        cb = AsyncMock(spec=CallbackQuery)
        cb.from_user = MagicMock(spec=User)
        cb.from_user.id = self.non_admin_id
        cb.message = AsyncMock(spec=Message)
        cb.message.edit_text = AsyncMock()
        cb.answer = AsyncMock()

        await cb_user_set_icon_style(cb)

        cb.message.edit_text.assert_called_once()
        cb.answer.assert_called_once()
        
        # Check that back button points to main menu for regular users
        sent_kb = cb.message.edit_text.call_args[1]["reply_markup"]
        all_cbs = [btn.callback_data for row in sent_kb.inline_keyboard for btn in row if btn.callback_data]
        self.assertIn("menu_back_main", all_cbs)
        self.assertNotIn("menu_admin", all_cbs)

    @patch("bot.handlers.start.set_user_icon_style", new_callable=AsyncMock)
    @patch("bot.handlers.start.set_button_icon_style", new_callable=AsyncMock)
    async def test_non_admin_cannot_forge_admin_back_button(self, mock_global_style, mock_user_style):
        """Verify non-admin setting icon style is forced to back_to='main' even if forging ':admin'."""
        cb = AsyncMock(spec=CallbackQuery)
        cb.from_user = MagicMock(spec=User)
        cb.from_user.id = self.non_admin_id
        cb.data = "set_icon_style:diamond:admin"  # Malicious user forging :admin
        cb.message = AsyncMock(spec=Message)
        cb.message.edit_reply_markup = AsyncMock()
        cb.answer = AsyncMock()

        await cb_set_icon_style(cb)

        # Personal style saved
        mock_user_style.assert_called_once_with(self.non_admin_id, "diamond")
        # Global admin default NOT updated
        mock_global_style.assert_not_called()

        # Keyboard strictly forces back_to='main'
        sent_kb = cb.message.edit_reply_markup.call_args[1]["reply_markup"]
        all_cbs = [btn.callback_data for row in sent_kb.inline_keyboard for btn in row if btn.callback_data]
        self.assertIn("menu_back_main", all_cbs)
        self.assertNotIn("menu_admin", all_cbs)

    @patch("bot.handlers.start.set_user_icon_style", new_callable=AsyncMock)
    @patch("bot.handlers.start.set_button_icon_style", new_callable=AsyncMock)
    async def test_admin_icon_style_updates_global_default(self, mock_global_style, mock_user_style):
        """Verify verified admin setting icon style updates both personal and global default."""
        cb = AsyncMock(spec=CallbackQuery)
        cb.from_user = MagicMock(spec=User)
        cb.from_user.id = self.admin_id
        cb.data = "set_icon_style:zap:admin"
        cb.message = AsyncMock(spec=Message)
        cb.message.edit_reply_markup = AsyncMock()
        cb.answer = AsyncMock()

        await cb_set_icon_style(cb)

        mock_user_style.assert_called_once_with(self.admin_id, "zap")
        mock_global_style.assert_called_once_with("zap")

        sent_kb = cb.message.edit_reply_markup.call_args[1]["reply_markup"]
        all_cbs = [btn.callback_data for row in sent_kb.inline_keyboard for btn in row if btn.callback_data]
        self.assertIn("menu_admin", all_cbs)

    def test_super_admin_sensitive_controls_isolation(self):
        """Verify the 5 sensitive tools are ONLY visible to Super Admin / Owner."""
        from bot.keyboards.inline import build_admin_keyboard
        from bot.handlers.admin import is_super_admin

        sensitive_callbacks = {
            "admin_manage_credit",
            "admin_manage_channels",
            "admin_broadcast",
            "admin_channel_broadcast",
            "admin_stats"
        }

        # Owner / Super Admin
        owner_id = 8370293945
        self.assertTrue(is_super_admin(owner_id))
        owner_kb = build_admin_keyboard(user_id=owner_id)
        owner_cbs = {btn.callback_data for row in owner_kb.inline_keyboard for btn in row if btn.callback_data}
        for sc in sensitive_callbacks:
            self.assertIn(sc, owner_cbs)

        # External channel owners / non-super admins
        external_ids = [7343013808, 8442202927, 11112222]
        for ext_id in external_ids:
            self.assertFalse(is_super_admin(ext_id))
            ext_kb = build_admin_keyboard(user_id=ext_id)
            ext_cbs = {btn.callback_data for row in ext_kb.inline_keyboard for btn in row if btn.callback_data}
            for sc in sensitive_callbacks:
                self.assertNotIn(sc, ext_cbs)

if __name__ == "__main__":
    unittest.main()

