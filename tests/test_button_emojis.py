import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DATABASE_PATH"] = "test_button_emojis.sqlite3"
os.environ["ADMIN_IDS"] = "8370293945"

from bot.database.db import (
    init_db, get_button_custom_emoji, set_button_custom_emoji,
    reset_button_custom_emoji, get_all_button_custom_emojis,
    get_cached_button_custom_emoji, DEFAULT_BUTTON_CUSTOM_EMOJIS
)
from bot.keyboards.inline import (
    make_custom_button, build_main_menu, build_poll_keyboard,
    build_button_emoji_manager_keyboard, build_button_emoji_action_keyboard,
    strip_all_emojis
)


class TestButtonCustomEmojis(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        if os.path.exists("test_button_emojis.sqlite3"):
            try:
                os.remove("test_button_emojis.sqlite3")
            except Exception:
                pass
        await init_db()

    async def asyncTearDown(self):
        if os.path.exists("test_button_emojis.sqlite3"):
            try:
                os.remove("test_button_emojis.sqlite3")
            except Exception:
                pass

    def test_make_custom_button_emoji_stripping(self):
        """Verify make_custom_button strips unicode emojis ONLY when custom_emoji_id is active."""
        # 1. With custom_emoji_id -> unicode emoji stripped from text
        btn_with_emoji = make_custom_button(
            text="👑 Super Admin Panel",
            callback_data="menu_admin",
            custom_emoji_id="6235252066554484059"
        )
        self.assertEqual(btn_with_emoji.text, "Super Admin Panel")
        self.assertEqual(btn_with_emoji.icon_custom_emoji_id, "6235252066554484059")

        btn_channels = make_custom_button(
            text="📢 Added Channels",
            callback_data="menu_my_channels",
            custom_emoji_id="6032575759606878027"
        )
        self.assertEqual(btn_channels.text, "Added Channels")
        self.assertEqual(btn_channels.icon_custom_emoji_id, "6032575759606878027")

        # 2. Without custom_emoji_id -> normal emoji kept intact
        btn_without_emoji = make_custom_button(
            text="📱 Bottom Keyboard (Quick Menu)",
            callback_data="toggle_bottom_menu",
            custom_emoji_id=None
        )
        self.assertEqual(btn_without_emoji.text, "📱 Bottom Keyboard (Quick Menu)")
        self.assertIsNone(btn_without_emoji.icon_custom_emoji_id)

    def test_build_poll_keyboard_candidate_emoji_no_duplicate(self):
        """Verify candidate button omits text icon when custom emoji ID is resolved."""
        cands = [
            {"candidate_id": 1, "name": "Shakib", "votes_count": 10},
            {"candidate_id": 2, "name": "Tamim", "votes_count": 5}
        ]
        # Using dynamic style which has animated crown for leader
        kb = build_poll_keyboard(poll_id=1, candidates=cands, bot_username="TestBot", icon_style="dynamic")
        
        # Shakib is #1 leader with votes -> has style_emoji_id ("6235252066554484059")
        shakib_btn = kb.inline_keyboard[0][0]
        self.assertEqual(shakib_btn.icon_custom_emoji_id, "6235252066554484059")
        # Text must NOT contain "👑"
        self.assertNotIn("👑", shakib_btn.text)
        self.assertIn("Shakib • 10", shakib_btn.text)

    async def test_db_button_custom_emoji_crud_and_cache(self):
        """Test database persistence and in-memory cache for button custom emojis."""
        # Initial state: quick_menu is None
        initial_val = await get_button_custom_emoji("quick_menu")
        self.assertIsNone(initial_val)

        # Set animated emoji ID for quick_menu
        test_id = "5445118546700954082"  # Rocket
        res = await set_button_custom_emoji("quick_menu", test_id)
        self.assertTrue(res)

        # Check async getter & cached synchronous getter
        val_after = await get_button_custom_emoji("quick_menu")
        self.assertEqual(val_after, test_id)
        self.assertEqual(get_cached_button_custom_emoji("quick_menu"), test_id)

        # Check in build_main_menu: quick_menu now has the custom emoji and stripped text!
        menu_kb = build_main_menu(is_admin=True, bot_username="TestBot", lang="en")
        # Find quick menu button
        quick_btn = None
        for row in menu_kb.inline_keyboard:
            for btn in row:
                if btn.callback_data == "toggle_bottom_menu":
                    quick_btn = btn
                    break
        self.assertIsNotNone(quick_btn)
        self.assertEqual(quick_btn.icon_custom_emoji_id, test_id)
        self.assertEqual(quick_btn.text, "Bottom Keyboard (Quick Menu)")

        # Reset button custom emoji
        await reset_button_custom_emoji("quick_menu")
        val_reset = await get_button_custom_emoji("quick_menu")
        self.assertIsNone(val_reset)
        self.assertIsNone(get_cached_button_custom_emoji("quick_menu"))

    def test_manager_keyboards_structure(self):
        """Verify button emoji manager keyboards build cleanly."""
        all_emojis = {k: "123456789012345" for k in DEFAULT_BUTTON_CUSTOM_EMOJIS}
        mgr_kb = build_button_emoji_manager_keyboard(all_emojis)
        self.assertGreaterEqual(len(mgr_kb.inline_keyboard), 10)

        action_kb = build_button_emoji_action_keyboard("create_poll", has_custom_id=True)
        self.assertEqual(len(action_kb.inline_keyboard), 3)


if __name__ == "__main__":
    unittest.main()
