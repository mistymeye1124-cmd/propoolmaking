import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

# Ensure UTF-8 output
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DATABASE_PATH"] = "test_start_btn.sqlite3"

from bot.database.db import init_db, save_user, set_user_language
from bot.keyboards.reply import build_persistent_menu
from bot.handlers.start import reply_btn_start, START_BUTTON_TEXTS, cmd_start
from bot.templates import render_start_text

class TestStartButtonFeature(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        await init_db()
        await save_user(user_id=88889999, username="startuser", first_name="Boss", last_name="Man")

    async def asyncTearDown(self):
        db_path = "test_start_btn.sqlite3"
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except Exception:
                pass

    def test_persistent_keyboard_top_row_has_start_button(self):
        """Verify that Start button is placed in Row 0 as the very first omnipresent button in all languages."""
        for lang, expected_token in [("bn", "মূল মেনু"), ("en", "Main Menu"), ("hi", "मुख्य मेनू"), ("ar", "القائمة"), ("ru", "Главное меню")]:
            kb = build_persistent_menu(lang=lang, is_admin=False)
            self.assertTrue(kb.is_persistent)
            self.assertTrue(kb.resize_keyboard)
            self.assertGreaterEqual(len(kb.keyboard), 4)
            top_btn = kb.keyboard[0][0].text
            self.assertIn("Start", top_btn)
            self.assertIn(expected_token, top_btn)

    async def test_reply_btn_start_renders_dashboard(self):
        """Verify that tapping the persistent Start button clears FSM state and renders executive dashboard."""
        mock_message = MagicMock()
        mock_message.from_user.id = 88889999
        mock_message.from_user.full_name = "Boss Man"
        mock_message.from_user.first_name = "Boss"
        mock_message.bot.get_me = AsyncMock(return_value=MagicMock(username="propollbot"))
        mock_message.answer = AsyncMock()

        mock_state = MagicMock()
        mock_state.clear = AsyncMock()

        await reply_btn_start(mock_message, state=mock_state)

        # Ensure state was cleared cleanly
        mock_state.clear.assert_awaited_once()

        # Ensure answer was sent with executive dashboard text
        mock_message.answer.assert_awaited_once()
        args, kwargs = mock_message.answer.call_args
        sent_text = args[0]
        self.assertIn("PRO POLL ENGINE v3.5", sent_text)
        self.assertIn("Boss Man", sent_text)
        self.assertIn("৭-লেয়ার সিকিউরিটি", sent_text)

    async def test_start_button_texts_coverage(self):
        """Verify that START_BUTTON_TEXTS covers multiple languages and variations."""
        self.assertIn("🏠 Start / মূল মেনু", START_BUTTON_TEXTS)
        self.assertIn("🏠 Start / Main Menu", START_BUTTON_TEXTS)
        self.assertIn("🏠 Start / मुख्य मेनू", START_BUTTON_TEXTS)
        self.assertIn("🏠 Start", START_BUTTON_TEXTS)
        self.assertIn("🏠 মূল মেনু", START_BUTTON_TEXTS)

    def test_persistent_menu_has_hide_button_all_languages(self):
        """Verify that build_persistent_menu includes the hide button in all languages."""
        from bot.handlers.start import HIDE_KEYBOARD_TEXTS
        for lang, expected_token in [("bn", "লুকান"), ("en", "Hide"), ("hi", "छिपाएं"), ("ar", "إخفاء"), ("ru", "Скрыть")]:
            kb = build_persistent_menu(lang=lang, is_admin=False)
            last_row = kb.keyboard[-1]
            hide_btn = last_row[0].text
            self.assertIn(expected_token, hide_btn)
            self.assertIn(hide_btn, HIDE_KEYBOARD_TEXTS)

    def test_main_menu_has_toggle_bottom_menu_button(self):
        """Verify that build_main_menu contains toggle_bottom_menu button in all languages."""
        from bot.keyboards.inline import build_main_menu
        for lang in ["bn", "en", "hi", "ar", "ru"]:
            kb = build_main_menu(is_admin=False, bot_username="propollbot", lang=lang)
            callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row if btn.callback_data]
            self.assertIn("toggle_bottom_menu", callbacks)

    async def test_reply_btn_hide_keyboard_removes_markup(self):
        """Verify that reply_btn_hide_keyboard sends ReplyKeyboardRemove."""
        from bot.handlers.start import reply_btn_hide_keyboard
        from aiogram.types import ReplyKeyboardRemove
        mock_msg = MagicMock()
        mock_msg.from_user.id = 88889999
        mock_msg.answer = AsyncMock()
        await reply_btn_hide_keyboard(mock_msg)
        mock_msg.answer.assert_awaited_once()
        _, kwargs = mock_msg.answer.call_args
        self.assertIsInstance(kwargs.get("reply_markup"), ReplyKeyboardRemove)

if __name__ == "__main__":
    unittest.main()

