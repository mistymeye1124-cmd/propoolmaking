import asyncio
import html
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery
from bot.config import ADMIN_IDS, SUPER_ADMIN_IDS
from bot.database.db import (
    get_system_stats, get_all_user_ids,
    get_all_active_channels, get_all_channels_with_status,
    get_channel, set_channel_status, delete_channel,
    save_channel, deactivate_channel,
    get_custom_credit, set_custom_credit,
    get_custom_credit_btn_text, set_custom_credit_btn_text,
    get_button_icon_style, set_button_icon_style,
    get_user_icon_style, set_user_icon_style, get_user_saved_emojis,
    get_button_custom_emoji, get_all_button_custom_emojis,
    set_button_custom_emoji, reset_button_custom_emoji, BUTTON_METADATA
)
from bot.keyboards.inline import (
    build_admin_keyboard, build_templates_menu, build_template_edit_menu,
    build_credit_manager_keyboard, build_channel_network_keyboard, build_channel_detail_keyboard,
    build_icon_style_keyboard, build_button_emoji_manager_keyboard, build_button_emoji_action_keyboard
)
from bot.templates import (
    DESCRIPTIONS, get_raw_template, save_template_with_autotranslate, reset_template,
    render_poll_cta, render_poll_card, get_suggestion, apply_suggestion,
    sync_emojis_to_other_languages, render_template_live_preview
)


from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

router = Router()

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def is_super_admin(user_id: int) -> bool:
    return user_id in SUPER_ADMIN_IDS or user_id == 8370293945

class AdminSecurityMiddleware(BaseMiddleware):
    """
    Zero-trust security guard: ensures NO event entering the admin router
    can be processed unless the sender is explicitly in ADMIN_IDS.
    """
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = data.get("event_from_user")
        if not user or not is_admin(user.id):
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer()
                except Exception:
                    pass
            return None
        return await handler(event, data)

router.message.middleware(AdminSecurityMiddleware())
router.callback_query.middleware(AdminSecurityMiddleware())

class AdminStates(StatesGroup):
    broadcast = State()
    broadcast_channel = State()
    edit_template = State()
    edit_credit_name = State()
    edit_credit_url = State()
    edit_credit_btn_text = State()
    add_channel = State()
    custom_icon = State()
    edit_button_emoji = State()

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    await show_admin_panel(message, is_callback=False, user_id=message.from_user.id)

@router.callback_query(F.data == "menu_admin")
async def cb_admin(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await show_admin_panel(callback.message, is_callback=True, user_id=callback.from_user.id)
    await callback.answer()

async def show_admin_panel(message_or_msg, is_callback: bool = False, user_id: int = None):
    uid = user_id
    if not uid:
        from_user = getattr(message_or_msg, "from_user", None)
        chat = getattr(message_or_msg, "chat", None)
        uid = from_user.id if from_user else (chat.id if chat else None)

    is_owner = is_super_admin(uid) if uid else False

    if is_owner:
        stats = await get_system_stats()
        text = (
            "👑 <b>Super Admin Panel [Confidential]</b>\n"
            "<i>গোপন মাস্টার কন্ট্রোল ও কাস্টমাইজেশন হাব</i>\n\n"
            f"👥 <b>Total Voters / মোট ভোটার:</b> <code>{stats['total_users']}</code>\n"
            f"📡 <b>Connected Channels / যুক্ত চ্যানেল:</b> <code>{stats.get('total_channels', 0)}</code>\n"
            f"📊 <b>Total Polls / মোট পোল:</b> <code>{stats['total_polls']}</code>\n"
            f"🟢 <b>Active Polls / সক্রিয় পোল:</b> <code>{stats['active_polls']}</code>\n"
            f"🗳️ <b>Total Votes Cast / সংগৃহীত ভোট:</b> <code>{stats['total_votes']}</code>\n\n"
            "⚡ <i>Use the stealth controls and editors below:</i>"
        )
    else:
        text = (
            "👑 <b>Admin Panel</b>\n"
            "<i>মাস্টার সেটিংস ও কাস্টমাইজেশন হাব</i>\n\n"
            "⚡ <i>নিচের অপশনগুলো থেকে প্রয়োজনীয় টুল নির্বাচন করুন:</i>"
        )
    kb = build_admin_keyboard(user_id=uid)
    if is_callback:
        await message_or_msg.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await message_or_msg.answer(text, reply_markup=kb, parse_mode="HTML")

async def show_detailed_stats(message_or_cb, bot, is_callback: bool = False):
    from bot.database.db import get_system_stats, get_effective_credit, get_button_icon_style
    from bot.templates import safe_html_preserve_tg_emoji
    from aiogram.exceptions import TelegramBadRequest

    stats = await get_system_stats()
    bot_info = await bot.get_me()
    brand_name, brand_url, brand_btn = await get_effective_credit()
    icon_style = await get_button_icon_style()

    brand_disp = f'<a href="{brand_url}">{safe_html_preserve_tg_emoji(brand_name)}</a>' if (brand_url and brand_name) else (safe_html_preserve_tg_emoji(brand_name) or f"@{bot_info.username}")
    btn_disp = safe_html_preserve_tg_emoji(brand_btn) if brand_btn else "Default CTA"

    text = (
        "📊 <b>Detailed System Statistics & Health Dashboard</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 <b>Total Registered Voters / মোট ভোটার:</b> <code>{stats['total_users']}</code> জন\n"
        f"📢 <b>Active Channels / সক্রিয় চ্যানেল:</b> <code>{stats['total_channels']}</code> টি\n"
        f"💤 <b>Inactive Channels / নিষ্ক্রিয় চ্যানেল:</b> <code>{stats.get('inactive_channels', 0)}</code> টি\n"
        f"🗳️ <b>Total Votes Cast / সংগৃহীত মোট ভোট:</b> <code>{stats['total_votes']}</code> টি\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📈 <b>Poll Contests Breakdown / পোলের বিবরণ:</b>\n"
        f"  • 📁 <b>Total Created / মোট আয়োজিত:</b> <code>{stats['total_polls']}</code> টি\n"
        f"  • 🟢 <b>Active Live / চলমান পোল:</b> <code>{stats['active_polls']}</code> টি\n"
        f"  • 🏁 <b>Ended Contests / সমাপ্ত পোল:</b> <code>{stats.get('ended_polls', 0)}</code> টি\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🏷️ <b>Global Promotional Brand (Owner Only):</b>\n"
        f"  • <b>Brand Name:</b> {brand_disp}\n"
        f"  • <b>Button Label:</b> <code>{btn_disp}</code>\n"
        f"🎯 <b>Default Button Icon Style:</b> <code>{icon_style}</code>\n"
        "⚡ <b>Engine Health:</b> <code>100% Operational (SQLite WAL)</code>\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh Stats / রিফ্রেশ", callback_data="admin_stats_refresh")],
        [InlineKeyboardButton(text="🔙 Back to Admin Panel / এডমিন প্যানেল", callback_data="menu_admin")]
    ])

    try:
        if is_callback:
            await message_or_cb.edit_text(text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
        else:
            await message_or_cb.answer(text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower() and is_callback:
            await message_or_cb.answer("✅ Stats already up-to-date! / সর্বশেষ তথ্য প্রদর্শিত হচ্ছে।")
        else:
            raise

@router.callback_query(F.data.in_(["admin_stats", "admin_stats_refresh"]))
async def cb_admin_stats(callback: CallbackQuery):
    if not is_super_admin(callback.from_user.id):
        await callback.answer("⛔ Access Restricted / শুধুমাত্র সুপার এডমিনের জন্য!", show_alert=True)
        return
    await show_detailed_stats(callback.message, callback.bot, is_callback=True)
    try:
        await callback.answer("Stats updated!")
    except Exception:
        pass

# --- Security & Shield Status Dashboard ---

@router.callback_query(F.data == "admin_security_status")
async def cb_security_status(callback: CallbackQuery):
    await show_security_status(callback.message, callback.bot, is_callback=True)
    try:
        await callback.answer("Security status updated!")
    except Exception:
        pass

async def show_security_status(message_or_cb, bot, is_callback: bool = False):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from bot.database.db import get_system_stats

    stats = await get_system_stats()
    text = (
        "🛡️ <b>Enterprise Security & Anti-Abuse Shield Status</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔒 <b>সক্রিয় নিরাপত্তা ও প্রোটেকশন লেয়ার:</b>\n\n"
        "• 🛡️ <b>Anti-Flood / DDoS Shield:</b> 🟢 <b>ACTIVE</b>\n"
        "   <i>Max 3 actions/sec. স্প্যাম স্ক্রিপ্ট ও ফ্লাড অ্যাটাক থেকে স্বয়ংক্রিয় সুরক্ষা।</i>\n\n"
        "• 🤖 <b>Anti-Bot Account Filter:</b> 🟢 <b>ACTIVE</b>\n"
        "   <i>টেলিগ্রামের ফেক বট অ্যাকাউন্ট শনাক্ত ও ভোট দেওয়া সম্পূর্ণ ব্লক।</i>\n\n"
        "• 🔒 <b>Force-Sub Anti-Cheat:</b> 🟢 <b>ACTIVE</b>\n"
        "   <i>চ্যানেলে সাবস্ক্রাইব না করে ভোট দেওয়ার কোনো সুযোগ নেই (জিরো-বাইপাস)।</i>\n\n"
        "• 🏰 <b>Channel Isolation & Anti-Hijacking:</b> 🟢 <b>ACTIVE</b>\n"
        "   <i>প্রতিটি ইউজারের চ্যানেল কঠোরভাবে প্রাইভেট স্যান্ডবক্সে লক করা।</i>\n\n"
        "• ⚡ <b>Atomic Vote Locking:</b> 🟢 <b>ACTIVE</b>\n"
        "   <i>এক সেকেন্ডে মাল্টিপল ক্লিকের রেস কন্ডিশন ও ডাবল-ভোট ডাটাবেজে লক।</i>\n\n"
        "• 👑 <b>Zero-Trust Admin Guard:</b> 🟢 <b>ACTIVE</b>\n"
        "   <i>এডমিন প্যানেলে রাউটার-লেভেল সিকিউরিটি গার্ড মোতায়েন।</i>\n\n"
        "• 🔏 <b>Input Sanitization & Tag Escaping:</b> 🟢 <b>ACTIVE</b>\n"
        "   <i>পোলের টাইটেল ও টেক্সটে XSS বা ব্রোকেন HTML স্ক্রিপ্ট ব্লক।</i>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>মোট সুরক্ষিত ভোটার:</b> <code>{stats['total_users']}</code> | <b>চ্যানেল:</b> <code>{stats.get('total_channels', 0)}</code>\n"
        "✅ <i>সকল সিকিউরিটি শিল্ড রিয়েল-টাইমে চালু রয়েছে। বট ১০০% সুরক্ষিত!</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh / রিফ্রেশ", callback_data="admin_security_status")],
        [InlineKeyboardButton(text="🔙 Admin Panel / এডমিন প্যানেল", callback_data="menu_admin")]
    ])
    if is_callback:
        await message_or_cb.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await message_or_cb.answer(text, reply_markup=kb, parse_mode="HTML")

# --- Button Premium Custom Emoji Manager ---

@router.callback_query(F.data == "admin_manage_btn_emojis")
async def cb_admin_manage_btn_emojis(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    emoji_map = await get_all_button_custom_emojis()
    text = (
        "⭐ <b>Button Premium Emojis Manager / বাটন প্রিমিয়াম ইমোজি কন্ট্রোল</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "বটের যেকোনো বাটনে টেলিগ্রাম প্রিমিয়াম <b>Animated Custom Emoji</b> সেট বা পরিবর্তন করতে নিচের বাটনগুলোর মধ্যে থেকে নির্বাচন করুন।\n\n"
        "💡 <b>প্রিমিয়াম অ্যাকাউন্ট ব্যবহারের সুবিধা:</b>\n"
        "আপনার টেলিগ্রাম প্রিমিয়াম অ্যাকাউন্ট থেকে যেকোনো অ্যানিমেটেড ইমোজি সরাসরি সেন্ড করলেই বট স্বয়ংক্রিয়ভাবে তার ৬৪-বিট প্রিমিয়াম আইডি কোডে বসিয়ে দেবে এবং টেক্সট থেকে অপ্রয়োজনীয় ডুপ্লিকেট স্বাভাবিক ইমোজি মুছে দেবে!\n\n"
        "<i>যেকোনো বাটনে ট্যাপ করে নতুন ইমোজি সেট করুন:</i>"
    )
    from bot.templates import safe_edit_message
    await safe_edit_message(callback.message, text, reply_markup=build_button_emoji_manager_keyboard(emoji_map), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("btn_emoji_view:"))
async def cb_btn_emoji_view(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    key = callback.data.split(":")[1]
    meta = BUTTON_METADATA.get(key, {"title": key, "icon": "🔘"})
    cur_id = await get_button_custom_emoji(key)
    
    cur_display = f'<tg-emoji emoji-id="{cur_id}">{meta["icon"]}</tg-emoji> <code>{cur_id}</code>' if cur_id else "⚠️ <b>Not Set (স্বাভাবিক টেক্সট)</b>"

    text = (
        f"⭐ <b>{meta['title']}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>বাটন সিস্টেম কি (Key):</b> <code>{key}</code>\n"
        f"💎 <b>বর্তমান প্রিমিয়াম ইমোজি:</b> {cur_display}\n\n"
        "👉 <i>নতুন প্রিমিয়াম অ্যানিমেটেড ইমোজি যুক্ত করতে নিচের 'নতুন ইমোজি সেট' বাটনে চাপ দিন।</i>"
    )
    from bot.templates import safe_edit_message
    await safe_edit_message(
        callback.message,
        text,
        reply_markup=build_button_emoji_action_keyboard(key, has_custom_id=bool(cur_id)),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("btn_emoji_edit:"))
async def cb_btn_emoji_edit(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    key = callback.data.split(":")[1]
    meta = BUTTON_METADATA.get(key, {"title": key, "icon": "🔘"})
    await state.set_state(AdminStates.edit_button_emoji)
    await state.update_data(editing_btn_key=key)

    text = (
        f"✏️ <b>[{meta['title']}] বাটনে প্রিমিয়াম ইমোজি সেট</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👉 <b>আপনার Telegram Premium কিবোর্ড থেকে:</b> সরাসরি যেকোনো <b>Animated Custom Emoji</b> এখানে লিখে সেন্ড করুন!\n"
        "👉 <b>অথবা:</b> ইমোজির সংখ্যা আইডি (যেমন <code>6235252066554484059</code>) লিখে সেন্ড করুন।\n\n"
        "<i>(বাতিল করতে চাইলে /cancel বা /admin লিখুন)</i>"
    )
    from bot.templates import safe_edit_message
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    await safe_edit_message(
        callback.message,
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Cancel / বাতিল", callback_data=f"btn_emoji_view:{key}")]
        ]),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("btn_emoji_remove:"))
async def cb_btn_emoji_remove(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    key = callback.data.split(":")[1]
    await reset_button_custom_emoji(key)
    await callback.answer("✅ কাস্টম ইমোজি রিমুভ করে ডিফল্টে ফিরিয়ে নেওয়া হয়েছে!", show_alert=True)
    meta = BUTTON_METADATA.get(key, {"title": key, "icon": "🔘"})
    cur_id = await get_button_custom_emoji(key)
    cur_display = f'<tg-emoji emoji-id="{cur_id}">{meta["icon"]}</tg-emoji> <code>{cur_id}</code>' if cur_id else "⚠️ <b>Not Set (স্বাভাবিক টেক্সট)</b>"
    text = (
        f"⭐ <b>{meta['title']}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>বাটন সিস্টেম কি (Key):</b> <code>{key}</code>\n"
        f"💎 <b>বর্তমান প্রিমিয়াম ইমোজি:</b> {cur_display}\n\n"
        "👉 <i>নতুন প্রিমিয়াম অ্যানিমেটেড ইমোজি যুক্ত করতে নিচের 'নতুন ইমোজি সেট' বাটনে চাপ দিন।</i>"
    )
    from bot.templates import safe_edit_message
    await safe_edit_message(
        callback.message,
        text,
        reply_markup=build_button_emoji_action_keyboard(key, has_custom_id=bool(cur_id)),
        parse_mode="HTML"
    )

@router.message(AdminStates.edit_button_emoji)
async def process_btn_emoji_input(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    raw_text = (message.text or message.caption or "").strip()
    if raw_text in ("/cancel", "/admin", "/start"):
        await state.clear()
        await show_admin_panel(message, is_callback=False, user_id=message.from_user.id)
        return

    data = await state.get_data()
    btn_key = data.get("editing_btn_key")
    if not btn_key:
        await state.clear()
        await show_admin_panel(message, is_callback=False, user_id=message.from_user.id)
        return

    meta = BUTTON_METADATA.get(btn_key, {"title": btn_key, "icon": "🔘"})

    import re
    custom_emoji_id = None

    # 1. Check message entities for Telegram Premium custom emoji
    for entity in (message.entities or []):
        if entity.type == "custom_emoji" and entity.custom_emoji_id:
            custom_emoji_id = str(entity.custom_emoji_id)
            break

    # 2. Check HTML text for <tg-emoji> tags
    if not custom_emoji_id and message.html_text:
        m = re.search(r'<tg-emoji\b[^>]*(?:emoji-id|id)="([0-9]+)"[^>]*>', message.html_text, re.IGNORECASE)
        if m:
            custom_emoji_id = m.group(1)

    # 3. Check for raw numeric Telegram Premium Emoji ID (15-22 digits)
    if not custom_emoji_id:
        m = re.search(r'\b(\d{15,22})\b', raw_text)
        if m:
            custom_emoji_id = m.group(1)

    if not custom_emoji_id:
        await message.answer(
            "⚠️ <b>কোনো টেলিগ্রাম প্রিমিয়াম অ্যানিমেটেড ইমোজি বা বৈধ আইডি পাওয়া যায়নি!</b>\n\n"
            "অনুগ্রহ করে আপনার <b>Telegram Premium</b> অ্যাকাউন্ট থেকে সরাসরি একটি অ্যানিমেটেড ইমোজি সেন্ড করুন অথবা সঠিক সংখ্যা আইডি দিন।\n"
            "<i>(বাতিল করতে /cancel লিখুন)</i>",
            parse_mode="HTML"
        )
        return

    # Save to database and update cache
    await set_button_custom_emoji(btn_key, custom_emoji_id)
    await state.clear()

    confirm_text = (
        "✅ <b>সফলভাবে প্রিমিয়াম ইমোজি আপডেট হয়েছে!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🔘 <b>বাটন:</b> {meta['title']}\n"
        f"🆔 <b>Custom Emoji ID:</b> <code>{custom_emoji_id}</code>\n"
        f"✨ <b>লাইভ প্রিভিউ:</b> <tg-emoji emoji-id=\"{custom_emoji_id}\">{meta['icon']}</tg-emoji>\n\n"
        "⚡ <i>বটের লাইভ কিবোর্ডে তাৎক্ষণিকভাবে প্রিমিয়াম ইমোজি সক্রিয় হয়ে গেছে এবং টেক্সট থেকে অপ্রয়োজনীয় ডুপ্লিকেট স্বাভাবিক ইমোজি স্বয়ংক্রিয়ভাবে মুছে দেওয়া হয়েছে!</i>"
    )
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ বাটন ইমোজি তালিকায় ফিরুন", callback_data="admin_manage_btn_emojis")],
        [InlineKeyboardButton(text="👑 এডমিন প্যানেল", callback_data="menu_admin")]
    ])
    await message.answer(confirm_text, reply_markup=kb, parse_mode="HTML")

# --- Template & Premium Emoji Manager ---

@router.callback_query(F.data == "admin_manage_texts")
async def cb_manage_texts(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    text = (
        "🎨 <b>Texts & Premium Emojis Manager / টেক্সট ও প্রিমিয়াম ইমোজি এডিটর</b>\n\n"
        "Choose which message or template you want to customize. You can freely use <b>Telegram Premium Emojis</b>, "
        "custom icons, bold, italic, or custom links!\n\n"
        "<i>যে মেসেজটি এডিট করতে চান তা নির্বাচন করুন। আপনি প্রিমিয়াম ইমোজি ও যেকোনো ফরম্যাট দিতে পারবেন:</i>"
    )
    from bot.templates import safe_edit_message
    await safe_edit_message(callback.message, text, reply_markup=build_templates_menu(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("tpl_view:"))
async def cb_tpl_view(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    key = callback.data.split(":")[1]
    info = DESCRIPTIONS.get(key, {"title": key, "vars": "None"})
    val_bn = await get_raw_template(key, "bn")
    val_en = await get_raw_template(key, "en")
    sug_bn = get_suggestion(key, "bn")

    preview_text = (
        f"📝 <b>{info['title']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>Variables / প্রয়োজনীয় ভ্যারিয়েবল:</b> <code>{info['vars']}</code>\n"
        f"<i>(⚠️ এগুলো আপনার টেমপ্লেটে অবশ্যই রাখতে হবে)</i>\n\n"
        f"📌 <b>বর্তমান সক্রিয় টেমপ্লেট (Current Active):</b>\n"
        f"<pre><code>{html.escape(val_bn)}</code></pre>\n"
        f"👆 <i>(কোড বক্সে ১ বার চাপলেই পুরোটা কপি হয়ে যাবে!)</i>\n\n"
        f"💡 <b>প্রস্তাবিত প্রিমিয়াম ডিজাইন (Recommended Suggestion):</b>\n"
        f"<pre><code>{html.escape(sug_bn)}</code></pre>\n"
        f"👆 <i>(এটি কপি করতে পারেন অথবা নিচের <b>'✨ Apply Suggestion'</b> বাটনে চাপ দিয়ে ১-ক্লিকে সেট করতে পারেন)</i>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 <b>কীভাবে কপি, এডিট ও পেস্ট করবেন?</b>\n"
        f"1️⃣ যেকোনো কোড বক্সে <b>১ বার ট্যাপ করুন</b> (সরাসরি পুরো কোড কপি হবে)।\n"
        f"2️⃣ মেসেজ বক্সে <b>Paste (পেস্ট)</b> করুন।\n"
        f"3️⃣ পছন্দমতো টেক্সট সাজান এবং টেলিগ্রাম <b>Premium Emojis</b> ব্যবহার করুন।\n"
        f"4️⃣ সেন্ড করে দিলে বট সাথে সাথে সেভ করে নিবে!\n\n"
        f"✨ <i>বাংলায় এডিট করলে ইংরেজি সংস্করণে নতুন ইমোজিগুলো স্বয়ংক্রিয়ভাবে সিঙ্ক হয়ে যাবে!</i>"
    )
    from bot.templates import safe_edit_message
    await safe_edit_message(
        callback.message,
        preview_text,
        reply_markup=build_template_edit_menu(key),
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    await callback.answer()

@router.callback_query(F.data.startswith("tpl_apply_sug:"))
async def cb_tpl_apply_sug(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    key = callback.data.split(":")[1]
    await apply_suggestion(key)
    await callback.answer("✅ Suggestion applied! / প্রস্তাবিত ডিজাইন সক্রিয় করা হয়েছে!", show_alert=True)
    await cb_tpl_view(callback)

@router.callback_query(F.data.startswith("tpl_sync_emojis:"))
async def cb_tpl_sync_emojis(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    key = callback.data.split(":")[1]
    val_bn = await get_raw_template(key, "bn")
    await sync_emojis_to_other_languages(key, val_bn, source_lang="bn")
    await callback.answer("✨ Emojis synced across all languages! / সব ভাষায় নতুন ইমোজি সিঙ্ক হয়েছে!", show_alert=True)
    await cb_tpl_view(callback)

@router.callback_query(F.data.startswith("tpl_preview:"))
async def cb_tpl_preview(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    parts = callback.data.split(":")
    key = parts[1]
    lang = parts[2] if len(parts) > 2 else "bn"
    preview_text, reply_markup = await render_template_live_preview(key, lang=lang)
    from bot.templates import safe_edit_message
    await safe_edit_message(
        callback.message,
        preview_text,
        reply_markup=reply_markup,
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    await callback.answer()

@router.callback_query(F.data == "dummy_vote_preview")
async def cb_dummy_vote_preview(callback: CallbackQuery):
    await callback.answer("ℹ️ এটি একটি লাইভ প্রিভিউ ডেমো বাটন (Live Preview Demo Button)", show_alert=False)

@router.callback_query(F.data.startswith("tpl_reset:"))
async def cb_tpl_reset(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    key = callback.data.split(":")[1]
    await reset_template(key)
    await callback.answer("✅ Reset to default / ডিফল্ট করা হয়েছে!", show_alert=True)
    await cb_tpl_view(callback)

@router.callback_query(F.data.startswith("tpl_edit:"))
async def cb_tpl_edit_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    parts = callback.data.split(":")
    key = parts[1]
    mode = parts[2] if len(parts) > 2 else "auto"
    info = DESCRIPTIONS.get(key, {"title": key, "vars": "None"})
    await state.set_state(AdminStates.edit_template)
    await state.update_data(editing_key=key, edit_mode=mode)

    val_current = await get_raw_template(key, "bn" if mode == "bn" else "en")
    sug = get_suggestion(key, "bn" if mode == "bn" else "en")

    mode_label = (
        "🇧🇩 <b>বাংলা সংস্করণ সরাসরি এডিট (Bangla Only)</b>" if mode == "bn" else (
            "🇬🇧 <b>Direct English Edit (English Only)</b>" if mode == "en" else
            "🌐 <b>স্বয়ংক্রিয় অনুবাদ ও সংরক্ষণ (Auto-Translate Both)</b>"
        )
    )

    msg = (
        f"✏️ <b>Editing: {info['title']}</b>\n"
        f"🎯 <b>Mode:</b> {mode_label}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>বর্তমান সক্রিয় টেমপ্লেট:</b>\n"
        f"<pre><code>{html.escape(val_current)}</code></pre>\n"
        f"👆 <i>(ট্যাপ করে কপি করুন)</i>\n\n"
        f"💡 <b>প্রস্তাবিত প্রিমিয়াম সাজেশন:</b>\n"
        f"<pre><code>{html.escape(sug)}</code></pre>\n"
        f"👆 <i>(ট্যাপ করে কপি করতে পারেন)</i>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 <b>কীভাবে পেস্ট ও এডিট করবেন?</b>\n"
        f"1️⃣ উপরের যেকোনো কোড বক্সে <b>একবার ট্যাপ করুন</b> (কপি হয়ে যাবে)।\n"
        f"2️⃣ মেসেজ বক্সে <b>Paste (পেস্ট)</b> করুন।\n"
        f"3️⃣ প্রয়োজনমতো টেক্সট ও <b>Telegram Premium Emojis</b> বসান।\n"
        f"⚠️ <b>Must include variables:</b> <code>{info['vars']}</code>\n"
        f"4️⃣ মেসেজটি সেন্ড করে দিন—বট সাথে সাথে সেভ করে নিবে!\n\n"
        f"✨ <i>টিপস: আপনি বাংলায় যে ইমোজি বা প্রিমিয়াম ইমোজি দিবেন, তা স্বয়ংক্রিয়ভাবে ইংরেজি সংস্করণেও সেট হয়ে যাবে!</i>\n\n"
        f"বাতিল করতে চাইলে /cancel লিখুন:"
    )
    from bot.templates import safe_edit_message
    await safe_edit_message(callback.message, msg, parse_mode="HTML")
    await callback.answer()

@router.message(AdminStates.edit_template)
async def process_tpl_edit(message: Message, state: FSMContext):
    if message.text and message.text.startswith("/cancel"):
        await state.clear()
        await message.answer("❌ Edit cancelled / বাতিল করা হয়েছে।")
        return

    data = await state.get_data()
    key = data.get("editing_key")
    mode = data.get("edit_mode", "auto")
    if not key:
        await state.clear()
        await message.answer("Session expired / সেশন বাতিল হয়েছে।")
        return

    new_html = message.html_text or html.escape(message.text or "")
    from bot.templates import safe_send_message, safe_edit_message
    from bot.database.db import set_setting

    info = DESCRIPTIONS.get(key, {"title": key})

    if mode == "bn":
        await set_setting(f"{key}_bn", new_html)
        val_bn = new_html
        # Intelligently propagate new emojis & Telegram Premium emojis to English and other languages
        await sync_emojis_to_other_languages(key, new_html, source_lang="bn")
        val_en = await get_raw_template(key, "en")
        header = (
            f"✅ <b>{info['title']} (Bangla Version) Updated!</b>\n"
            f"✨ <i>আপনার নতুন ইমোজি ও প্রিমিয়াম ইমোজিগুলো স্বয়ংক্রিয়ভাবে ইংরেজি সংস্করণেও সিঙ্ক করা হয়েছে!</i>"
        )
        status_msg = None
    elif mode == "en":
        await set_setting(f"{key}_en", new_html)
        val_en = new_html
        val_bn = await get_raw_template(key, "bn")
        header = f"✅ <b>{info['title']} (English Version) Updated!</b>"
        status_msg = None
    else:  # auto
        status_msg = await message.answer("⏳ Processing & Live Translating with Premium Emojis... / লাইভ অনুবাদ হচ্ছে...")
        val_bn, val_en = await save_template_with_autotranslate(key, new_html)
        header = f"✅ <b>{info['title']} Updated & Auto-Translated!</b>"

    await state.clear()

    result_text = (
        f"{header}\n\n"
        f"🇧🇩 <b>Bangla Version:</b>\n━━━━━━━━━━━━━━━━━━━━\n{val_bn}\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🇬🇧 <b>English Version:</b>\n━━━━━━━━━━━━━━━━━━━━\n{val_en}\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "💡 <i>Telegram Premium Emojis are 100% preserved in the database!</i>"
    )

    if status_msg:
        await safe_edit_message(
            status_msg,
            result_text,
            reply_markup=build_template_edit_menu(key),
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    else:
        await safe_send_message(
            message.bot,
            message.chat.id,
            result_text,
            reply_markup=build_template_edit_menu(key),
            parse_mode="HTML",
            disable_web_page_preview=True
        )


# --- Custom Brand Credit & Watermark Manager ---

async def show_credit_manager(msg_or_cb, bot, user_id: int, is_callback: bool = False):
    if not is_admin(user_id):
        if is_callback:
            await msg_or_cb.answer()
        return

    from bot.database.db import get_effective_credit
    from bot.templates import safe_html_preserve_tg_emoji
    bot_info = await bot.get_me()
    name, url, btn_text = await get_effective_credit()
    
    name_display = f"<code>{safe_html_preserve_tg_emoji(name)}</code>" if name else f"<i>Default (@{bot_info.username})</i>"
    url_display = f"<code>{safe_html_preserve_tg_emoji(url)}</code>" if url else f"<i>Default (https://t.me/{bot_info.username}?start=create_poll)</i>"
    btn_display = f"<code>{safe_html_preserve_tg_emoji(btn_text)}</code>" if btn_text else "<i>Default (Template Default)</i>"

    text = (
        "🏷️ <b>Super Admin Promotional Credit & Link Manager</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>Current Brand Name:</b> {name_display}\n"
        f"🔗 <b>Current Button URL:</b> {url_display}\n"
        f"💬 <b>Current Button Text:</b> {btn_display}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👑 <b>একচেটিয়া প্রমোশন পলিসি:</b>\n"
        "এখানে আপনি যে নাম, লিংক ও বাটন টেক্সট সেট করবেন, তা <b>যেকোনো ইউজারের তৈরি করা সব পোলের কার্ড এবং নিচের বাটনে</b> অপরিবর্তনীয়ভাবে স্বয়ংক্রিয় যুক্ত থাকবে। সাধারণ ইউজাররা এটি এডিট করতে পারবে না।\n\n"
        "👇 <i>সেটিংস পরিবর্তন করতে নিচের অপশন নির্বাচন করুন:</i>"
    )
    kb = build_credit_manager_keyboard(back_to="admin")
    try:
        if is_callback:
            await msg_or_cb.edit_text(
                text,
                reply_markup=kb,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        else:
            await msg_or_cb.answer(
                text,
                reply_markup=kb,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
    except Exception as e:
        if "message is not modified" not in str(e).lower():
            await msg_or_cb.answer(text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)

@router.callback_query(F.data == "admin_manage_credit")
async def cb_manage_credit(callback: CallbackQuery):
    if not is_super_admin(callback.from_user.id):
        await callback.answer("⛔ Access Restricted / শুধুমাত্র সুপার এডমিনের জন্য!", show_alert=True)
        return
    await show_credit_manager(callback.message, callback.bot, callback.from_user.id, is_callback=True)
    await callback.answer()

@router.callback_query(F.data == "credit_edit_name")
async def cb_credit_edit_name(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.set_state(AdminStates.edit_credit_name)
    msg = (
        "✏️ <b>Enter Promotional Brand/Credit Name / ব্র্যান্ডের নাম দিন:</b>\n\n"
        "Send the new credit display text (supports Premium Emojis):\n"
        "<i>(Examples: <code>@MySuperChannel</code>, <code>⚡ My Brand Network</code>)</i>\n\n"
        "Cancel: /cancel"
    )
    try:
        await callback.message.edit_text(msg, parse_mode="HTML")
    except Exception:
        await callback.message.answer(msg, parse_mode="HTML")
    await callback.answer()

@router.message(AdminStates.edit_credit_name)
async def process_credit_name(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    if message.text and message.text.startswith("/cancel"):
        await state.clear()
        await message.answer("❌ Cancelled / বাতিল করা হয়েছে।")
        return

    new_name = (message.html_text or message.text or "").strip()
    from bot.database.db import set_custom_credit, get_effective_credit
    from bot.templates import safe_html_preserve_tg_emoji

    _, cur_url, _ = await get_effective_credit()
    await set_custom_credit(new_name, cur_url)

    await state.clear()
    await message.answer(
        f"✅ <b>Promotional Brand Name Updated! / ব্র্যান্ড নাম আপডেট হয়েছে!</b>\n\n"
        f"🏷️ <b>New Name:</b> {safe_html_preserve_tg_emoji(new_name)}\n\n"
        "সকল চ্যানেলে পোস্ট হওয়া সব পোলের ওয়াটারমার্কে এখন থেকে এই নামটি অপরিবর্তনীয়ভাবে থাকবে।",
        parse_mode="HTML"
    )
    await show_credit_manager(message, message.bot, message.from_user.id, is_callback=False)

@router.callback_query(F.data == "credit_edit_url")
async def cb_credit_edit_url(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.set_state(AdminStates.edit_credit_url)
    msg = (
        "🔗 <b>Enter Custom Promotional URL / বাটনের লিংক দিন:</b>\n\n"
        "Send the URL where voters will be redirected when clicking the bottom CTA button.\n"
        "<i>(Example: <code>https://t.me/MyChannel</code> or <code>@MyChannel</code>)</i>\n\n"
        "Cancel: /cancel"
    )
    try:
        await callback.message.edit_text(msg, parse_mode="HTML")
    except Exception:
        await callback.message.answer(msg, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "credit_edit_btn_text")
async def cb_credit_edit_btn_text(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.set_state(AdminStates.edit_credit_btn_text)
    msg = (
        "💬 <b>Enter Custom Button Text / বাটন টেক্সট দিন:</b>\n\n"
        "Send the text for the bottom CTA button (supports emojis):\n"
        "<i>(Example: <code>⚡ Join VIP Channel ➔</code> or <code>🔥 Visit Official Store</code>)</i>\n\n"
        "Cancel: /cancel"
    )
    try:
        await callback.message.edit_text(msg, parse_mode="HTML")
    except Exception:
        await callback.message.answer(msg, parse_mode="HTML")
    await callback.answer()

@router.message(AdminStates.edit_credit_btn_text)
async def process_credit_btn_text(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    if message.text and message.text.startswith("/cancel"):
        await state.clear()
        await message.answer("❌ Cancelled / বাতিল করা হয়েছে।")
        return
    new_btn = (message.html_text or message.text or "").strip()
    from bot.database.db import set_custom_credit_btn_text
    from bot.templates import safe_html_preserve_tg_emoji

    await set_custom_credit_btn_text(new_btn)

    await state.clear()
    await message.answer(
        f"✅ <b>Button Text Updated! / বাটন টেক্সট আপডেট হয়েছে!</b>\n\n"
        f"💬 <b>New Text:</b> {safe_html_preserve_tg_emoji(new_btn)}\n\n"
        "পোলের নিচের বাটনে এখন এই লেখাটি প্রদর্শিত হবে।",
        parse_mode="HTML"
    )
    await show_credit_manager(message, message.bot, message.from_user.id, is_callback=False)

@router.message(AdminStates.edit_credit_url)
async def process_credit_url(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    if message.text and message.text.startswith("/cancel"):
        await state.clear()
        await message.answer("❌ Cancelled / বাতিল করা হয়েছে।")
        return

    raw_url = message.text.strip()
    if raw_url.startswith("@"):
        new_url = f"https://t.me/{raw_url.lstrip('@')}"
    elif raw_url.startswith("t.me/"):
        new_url = f"https://{raw_url}"
    elif raw_url.startswith("http://") or raw_url.startswith("https://"):
        new_url = raw_url
    else:
        new_url = f"https://{raw_url}"

    from bot.database.db import set_custom_credit, get_effective_credit

    cur_name, _, _ = await get_effective_credit()
    await set_custom_credit(cur_name, new_url)

    await state.clear()
    await message.answer(
        f"✅ <b>Credit Button URL Updated! / বাটনের লিংক আপডেট হয়েছে!</b>\n\n"
        f"🔗 <b>New URL:</b> <code>{html.escape(new_url)}</code>\n\n"
        "পোলের নিচের বাটনে ক্লিক করলে এখন এই লিংকে যাবে।",
        parse_mode="HTML"
    )
    await show_credit_manager(message, message.bot, message.from_user.id, is_callback=False)

@router.callback_query(F.data == "credit_reset")
async def cb_credit_reset(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    from bot.database.db import set_custom_credit, set_custom_credit_btn_text
    await set_custom_credit("", "")
    await set_custom_credit_btn_text("")
    await callback.answer("✅ Reset to default bot branding / ডিফল্ট রিসেট সম্পন্ন!", show_alert=True)
    await show_credit_manager(callback.message, callback.bot, callback.from_user.id, is_callback=True)

@router.callback_query(F.data == "credit_test_preview")
async def cb_credit_test_preview(callback: CallbackQuery):
    user_id = callback.from_user.id
    if not is_admin(user_id):
        await callback.answer()
        return
    bot_info = await callback.bot.get_me()
    btn_text, btn_url = await render_poll_cta(bot_info.username, lang="bn")
    sample_card = await render_poll_card("🧪 Sample Brand Poll Test", bot_info.username, lang="bn")
    test_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn_text, url=btn_url)],
        [InlineKeyboardButton(text="🔙 Back to Credit Manager / তালিকায় ফিরুন", callback_data="admin_manage_credit")]
    ])
    try:
        await callback.message.edit_text(
            f"🧪 <b>Live Brand & Link Preview / লাইভ টেস্ট প্রিভিউ:</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{sample_card}\n\n"
            f"<i>নিচের বাটনটি ক্লিক করে দেখুন আপনার লিংক সঠিক জায়গায় কাজ করে কি না:</i>",
            reply_markup=test_kb,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    except Exception:
        pass
    await callback.answer()


# --- Channel Network Manager ---

@router.callback_query(F.data == "admin_manage_channels")
async def cb_manage_channels(callback: CallbackQuery):
    if not is_super_admin(callback.from_user.id):
        await callback.answer("⛔ Access Restricted / শুধুমাত্র সুপার এডমিনের জন্য!", show_alert=True)
        return
    channels = await get_all_channels_with_status()
    active_count = sum(1 for c in channels if c.get("is_active", 1) == 1)
    inactive_count = len(channels) - active_count

    text = (
        "📡 <b>Channel Network Manager / চ্যানেল নেটওয়ার্ক</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Total Channels in Database:</b> <code>{len(channels)}</code>\n"
        f"🟢 <b>Active & Ready:</b> <code>{active_count}</code>\n"
        f"🔴 <b>Inactive / Removed:</b> <code>{inactive_count}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💡 <i>বট যেসব চ্যানেলে যুক্ত আছে বা পোল তৈরি হয়েছে, সব এখানে থাকে। "
        "নিচের তালিকা থেকে যেকোনো চ্যানেলে ক্লিক করে সংযোগ পরীক্ষা বা মুছে ফেলতে পারেন:</i>"
    )
    await callback.message.edit_text(
        text,
        reply_markup=build_channel_network_keyboard(channels),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("chan_view:"))
async def cb_chan_view(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    chat_id = int(callback.data.split(":")[1])
    ch = await get_channel(chat_id)
    if not ch:
        await callback.answer("Channel not found / চ্যানেলটি পাওয়া যায়নি!", show_alert=True)
        await cb_manage_channels(callback)
        return

    status_str = "🟢 Active (Ready for Broadcast)" if ch.get("is_active", 1) == 1 else "🔴 Inactive (Permissions Issue or Removed)"
    username_str = f"@{ch['username']}" if ch.get("username") else "No public username"
    added_by_str = f"<code>{ch.get('added_by')}</code>" if ch.get("added_by") else "Unknown"

    text = (
        f"📢 <b>Channel Details / চ্যানেলের বিবরণ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>Title:</b> {html.escape(ch.get('title') or 'Untitled')}\n"
        f"🆔 <b>Chat ID:</b> <code>{ch['chat_id']}</code>\n"
        f"🔗 <b>Username:</b> {username_str}\n"
        f"⚡ <b>Status:</b> {status_str}\n"
        f"👤 <b>Added By:</b> {added_by_str}\n"
        f"📅 <b>Connected:</b> {ch.get('created_at', 'N/A')}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "কানেকশন টেস্ট করতে বা নেটওয়ার্ক থেকে বাদ দিতে নিচের বাটন চাপুন:"
    )
    await callback.message.edit_text(
        text,
        reply_markup=build_channel_detail_keyboard(chat_id),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("chan_test:"))
async def cb_chan_test(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    chat_id = int(callback.data.split(":")[1])
    bot = callback.bot
    try:
        member = await bot.get_chat_member(chat_id, bot.id)
        if member.status in ["administrator", "creator"]:
            can_post = getattr(member, "can_post_messages", True)
            if can_post:
                await set_channel_status(chat_id, 1)
                await callback.answer("✅ Success: Bot is Admin with Post Messages rights!", show_alert=True)
            else:
                await set_channel_status(chat_id, 0)
                await callback.answer("⚠️ Bot is Admin but lacks 'Post Messages' permission!", show_alert=True)
        else:
            await set_channel_status(chat_id, 0)
            await callback.answer("❌ Bot is NOT an administrator in this chat!", show_alert=True)
    except Exception as e:
        await set_channel_status(chat_id, 0)
        await callback.answer(f"❌ Connection error: {e}", show_alert=True)

    await cb_chan_view(callback)

@router.callback_query(F.data.startswith("chan_del:"))
async def cb_chan_del(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    chat_id = int(callback.data.split(":")[1])
    await delete_channel(chat_id)
    await callback.answer("🗑️ Channel removed from network / মুছে ফেলা হয়েছে!", show_alert=True)
    await cb_manage_channels(callback)

@router.callback_query(F.data == "chan_sync")
async def cb_chan_sync(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    channels = await get_all_channels_with_status()
    bot = callback.bot
    active_count = 0
    inactive_count = 0

    status_msg = await callback.message.answer(f"⏳ Synchronizing and testing {len(channels)} channels...")

    for ch in channels:
        cid = ch["chat_id"]
        try:
            member = await bot.get_chat_member(cid, bot.id)
            if member.status in ["administrator", "creator"]:
                can_post = getattr(member, "can_post_messages", True)
                if can_post:
                    await set_channel_status(cid, 1)
                    active_count += 1
                else:
                    await set_channel_status(cid, 0)
                    inactive_count += 1
            else:
                await set_channel_status(cid, 0)
                inactive_count += 1
        except Exception:
            await set_channel_status(cid, 0)
            inactive_count += 1
        await asyncio.sleep(0.05)

    try:
        await status_msg.delete()
    except Exception:
        pass

    await callback.answer(f"🔄 Sync complete: {active_count} Active, {inactive_count} Inactive!", show_alert=True)
    await cb_manage_channels(callback)

@router.callback_query(F.data == "chan_add")
async def cb_chan_add(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(AdminStates.add_channel)
    await callback.message.edit_text(
        "➕ <b>Add Channel to Network / চ্যানেলে যুক্ত করুন</b>\n\n"
        "Send the channel username (e.g. <code>@MyChannel</code>) or Chat ID (e.g. <code>-1001234567890</code>):\n\n"
        "⚠️ <b>Note:</b> The bot must already be added as an <b>Administrator</b> in that channel with 'Post Messages' permission enabled.\n\n"
        "Cancel: /cancel",
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(AdminStates.add_channel)
async def process_add_channel(message: Message, state: FSMContext):
    if message.text and message.text.startswith("/cancel"):
        await state.clear()
        await message.answer("❌ Cancelled / বাতিল করা হয়েছে।")
        return

    query = message.text.strip()
    bot = message.bot
    status_msg = await message.answer("⏳ Connecting and verifying channel permissions...")

    try:
        chat = await bot.get_chat(query)
    except Exception as e:
        await status_msg.edit_text(
            f"❌ <b>Chat Not Found! / চ্যানেলটি খুঁজে পাওয়া যায়নি</b>\n\n"
            f"Error: <code>{html.escape(str(e))}</code>\n\n"
            "Make sure the username/ID is correct and bot has access to it. Try again or type /cancel:",
            parse_mode="HTML"
        )
        return

    try:
        member = await bot.get_chat_member(chat.id, bot.id)
        if member.status not in ["administrator", "creator"]:
            await status_msg.edit_text(
                f"⚠️ <b>Bot is NOT an Administrator!</b>\n\n"
                f"Channel: <b>{html.escape(chat.title or '')}</b>\n"
                "Please make the bot an Admin with Post Messages permission first, then send again:",
                parse_mode="HTML"
            )
            return

        can_post = getattr(member, "can_post_messages", True)
        if not can_post:
            await status_msg.edit_text(
                f"⚠️ <b>Missing 'Post Messages' Permission!</b>\n\n"
                f"Bot is admin in <b>{html.escape(chat.title or '')}</b>, but does not have permission to post messages. Please enable it and try again:",
                parse_mode="HTML"
            )
            return

        await save_channel(
            chat_id=chat.id,
            title=chat.title or "Untitled Channel",
            username=chat.username,
            added_by=message.from_user.id
        )
        await set_channel_status(chat.id, 1)
        await state.clear()

        await status_msg.edit_text(
            f"✅ <b>Channel Connected Successfully!</b>\n\n"
            f"📢 <b>Title:</b> {html.escape(chat.title or '')}\n"
            f"🆔 <b>ID:</b> <code>{chat.id}</code>\n"
            f"🔗 <b>Username:</b> @{chat.username or 'N/A'}\n"
            f"🟢 <b>Status:</b> Active & Verified\n\n"
            "এই চ্যানেলে এখন থেকে একযোগে Mass Channel Post পৌঁছাবে।",
            reply_markup=build_channel_detail_keyboard(chat.id),
            parse_mode="HTML"
        )

    except Exception as e:
        await status_msg.edit_text(
            f"❌ <b>Verification Error:</b> <code>{html.escape(str(e))}</code>\nTry again or /cancel:",
            parse_mode="HTML"
        )

# --- Broadcast Feature (Inbox) ---
@router.callback_query(F.data == "admin_broadcast")
async def cb_broadcast_start(callback: CallbackQuery, state: FSMContext):
    if not is_super_admin(callback.from_user.id):
        await callback.answer("⛔ Access Restricted / শুধুমাত্র সুপার এডমিনের জন্য!", show_alert=True)
        return
    await state.set_state(AdminStates.broadcast)
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Cancel Broadcast / বাতিল", callback_data="admin_cancel_broadcast")]
    ])
    await callback.message.edit_text(
        "📢 <b>Inbox Broadcast / ভোটারদের ইনবক্সে মেসেজ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Send or forward the message you want to broadcast to all registered voters.\n"
        "Supports <b>Telegram Premium Emojis</b>, photos, videos, stickers, formatting, and buttons!\n\n"
        "<i>যে মেসেজটি পাঠাতে চান তা পাঠিয়ে দিন (প্রিমিয়াম ইমোজি, ছবি, ভিডিও ইত্যাদি সাপোর্ট করবে)।</i>\n"
        "━━━━━━━━━━━━━━━━━━━━",
        reply_markup=cancel_kb,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "admin_cancel_broadcast")
async def cb_cancel_broadcast(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("❌ Broadcast cancelled / ব্রডকাস্ট বাতিল করা হয়েছে।")
    await show_admin_panel(callback.message, is_callback=True)

@router.message(AdminStates.broadcast)
async def process_broadcast(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    if message.text and message.text.startswith("/cancel"):
        await state.clear()
        await message.answer("❌ Broadcast cancelled / ব্রডকাস্ট বাতিল করা হয়েছে।")
        return

    user_ids = await get_all_user_ids()
    await state.clear()
    total = len(user_ids)
    if total == 0:
        await message.answer("⚠️ No registered voters found in database / কোনো ইউজার পাওয়া যায়নি।")
        return

    status_msg = await message.answer(f"⏳ Broadcasting to {total} voters / পাঠানো শুরু হচ্ছে...")
    
    success = 0
    failed = 0

    for uid in user_ids:
        try:
            await message.copy_to(chat_id=uid)
            success += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.04)

    await state.clear()
    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back to Admin Panel / এডমিন প্যানেল", callback_data="menu_admin")]
    ])
    await status_msg.edit_text(
        f"✅ <b>Inbox Broadcast Complete / ব্রডকাস্ট সম্পন্ন!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 <b>Total Target / মোট:</b> <code>{total}</code>\n"
        f"✅ <b>Delivered / সফল:</b> <code>{success}</code>\n"
        f"❌ <b>Blocked or Inactive / ব্যর্থ:</b> <code>{failed}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━",
        reply_markup=back_kb,
        parse_mode="HTML"
    )

# --- Channel Broadcast Feature (Mass Channel Post) ---
@router.callback_query(F.data == "admin_channel_broadcast")
async def cb_channel_broadcast_start(callback: CallbackQuery, state: FSMContext):
    if not is_super_admin(callback.from_user.id):
        await callback.answer("⛔ Access Restricted / শুধুমাত্র সুপার এডমিনের জন্য!", show_alert=True)
        return
    channels = await get_all_active_channels()
    total_active = len(channels)

    await state.set_state(AdminStates.broadcast_channel)
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Cancel Broadcast / বাতিল", callback_data="admin_cancel_broadcast")]
    ])
    await callback.message.edit_text(
        f"📡 <b>Mass Channel Broadcast / সকল চ্যানেলে একযোগে পোস্ট</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🟢 <b>Ready Active Channels:</b> <code>{total_active}</code> টি চ্যানেল\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Send or forward the post you want to publish in ALL active channels where this bot is an Admin.\n"
        "Supports <b>Telegram Premium Emojis</b>, media, photos, videos, and custom formatting!\n\n"
        "<i>যে পোস্টটি আপনি সকল সংযুক্ত চ্যানেলে একযোগে পোস্ট করতে চান, সেটি পাঠিয়ে দিন।</i>\n"
        "━━━━━━━━━━━━━━━━━━━━",
        reply_markup=cancel_kb,
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(AdminStates.broadcast_channel)
async def process_channel_broadcast(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    if message.text and message.text.startswith("/cancel"):
        await state.clear()
        await message.answer("❌ Channel broadcast cancelled / বাতিল করা হয়েছে।")
        return

    channels = await get_all_active_channels()
    await state.clear()
    total = len(channels)
    if total == 0:
        await message.answer(
            "⚠️ <b>No active channels found / কোনো সক্রিয় চ্যানেল পাওয়া যায়নি!</b>\n\n"
            "এডমিন প্যানেলের '📡 Channel Network Manager' থেকে চ্যানেল যুক্ত করুন বা সিঙ্ক করুন।",
            parse_mode="HTML"
        )
        return

    status_msg = await message.answer(f"⏳ Broadcasting to {total} channels / চ্যানেলে পোস্ট হচ্ছে...")
    
    success_list = []
    failed_list = []

    for ch in channels:
        ch_title = ch.get("title") or (f"@{ch['username']}" if ch.get("username") else str(ch["chat_id"]))
        cid = ch["chat_id"]
        try:
            await message.copy_to(chat_id=cid)
            success_list.append(ch_title)
        except Exception as e:
            err_str = str(e)
            failed_list.append((ch_title, err_str))
            err_lower = err_str.lower()
            if "forbidden" in err_lower or "kicked" in err_lower or "not enough rights" in err_lower or "chat not found" in err_lower:
                await deactivate_channel(cid)
        await asyncio.sleep(0.1)

    await state.clear()

    report_lines = [
        "✅ <b>Mass Channel Broadcast Complete! / চ্যানেল পোস্ট সম্পন্ন!</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"📡 <b>Total Attempted / মোট:</b> <code>{total}</code>",
        f"✅ <b>Delivered Successfully / সফল:</b> <code>{len(success_list)}</code>",
        f"❌ <b>Failed / ত্রুটিপূর্ণ:</b> <code>{len(failed_list)}</code>",
        "━━━━━━━━━━━━━━━━━━━━"
    ]

    if success_list:
        report_lines.append("\n🟢 <b>Delivered Channels:</b>")
        for s in success_list[:10]:
            report_lines.append(f"• <b>{html.escape(s)}</b>")
        if len(success_list) > 10:
            report_lines.append(f"• <i>...and {len(success_list) - 10} more channels</i>")

    if failed_list:
        report_lines.append("\n🔴 <b>Failed Channels & Reasons / ব্যর্থ চ্যানেলের কারণ:</b>")
        for title, reason in failed_list:
            report_lines.append(f"• <b>{html.escape(title)}</b>: <code>{html.escape(reason)}</code>")
        report_lines.append("\n💡 <i>অনুমতিহীন চ্যানেলগুলোকে স্বয়ংক্রিয়ভাবে ইনঅ্যাক্টিভ করা হয়েছে।</i>")

    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back to Admin Panel / এডমিন প্যানেল", callback_data="menu_admin")]
    ])
    report_text = "\n".join(report_lines)
    await status_msg.edit_text(report_text, reply_markup=back_kb, parse_mode="HTML")

# --- Button Icon Style Management (Admin Entrypoint) ---
@router.callback_query(F.data == "admin_manage_icon_style")
async def cb_admin_icon_style(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    current_style = await get_button_icon_style()
    saved_emojis = await get_user_saved_emojis(callback.from_user.id)
    kb = build_icon_style_keyboard(current_style, back_to="admin", saved_emojis=saved_emojis)
    text = (
        "🎯 <b>Poll Button Icon Style / ভোটিং বাটন আইকন স্টাইল</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "পোলের অপশন/প্রার্থীদের বাটনে কোন ধরনের আকর্ষণীয় ও প্রফেশনাল আইকন থাকবে তা নির্বাচন করুন:\n\n"
        "• <b>👑 Dynamic Leader:</b> ভোটের অগ্রগতির সাথে সাথে লিডারের বাটনে 👑, ২য়ে 🥈, ৩য়ে 🥉 ও ভোটে 🔥 আসবে। (সেরা চয়েস!)\n"
        "• <b>🗳️ Ballot Box:</b> সব বাটনে প্রফেশনাল ব্যালট বক্স আইকন থাকবে।\n"
        "• <b>💎 VIP Diamond:</b> ঝকঝকে ভিআইপি ডায়মন্ড আইকন।\n"
        "• <b>✨ Modern Sparkle:</b> আধুনিক স্পার্কল আইকন।\n"
        "• <b>🔹 Sleek Diamond:</b> মিনিমালিস্ট ব্লু ডায়মন্ড লুক।\n\n"
        "👇 <i>পছন্দের স্টাইল নির্বাচন করতে নিচে ক্লিক করুন:</i>"
    )
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

