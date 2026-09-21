import re
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, ChatMemberUpdated, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.config import ADMIN_IDS
from bot.keyboards.inline import (
    build_main_menu, build_language_selection_keyboard, build_icon_style_keyboard,
    make_custom_button, CREATE_POLL_CUSTOM_EMOJI_ID, ADD_CHANNEL_CUSTOM_EMOJI_ID,
    MY_POLLS_CUSTOM_EMOJI_ID, BUTTON_ICONS_CUSTOM_EMOJI_ID, LANGUAGE_CUSTOM_EMOJI_ID,
    HELP_CUSTOM_EMOJI_ID, START_MENU_CUSTOM_EMOJI_ID
)
from bot.keyboards.reply import build_persistent_menu
from bot.database.db import (
    save_channel, deactivate_channel, get_user_language, set_user_language, get_user_icon_style,
    set_user_icon_style, set_button_icon_style, record_user_channel_access,
    add_user_saved_emoji, get_user_saved_emojis, delete_user_saved_emoji
)
from bot.templates import render_start_text, render_help_text, safe_send_message, safe_edit_message

router = Router()

class UserIconStates(StatesGroup):
    custom_icon = State()

HELP_TEXT_BN = """
📖 <b>কীভাবে আপনার চ্যানেলে পোল তৈরি করবেন:</b>

1. প্রথমে এই বটটিকে আপনার চ্যানেলে <b>Administrator</b> হিসেবে যুক্ত করুন (মেসেজ পোস্ট করার অনুমতি দিন)।
2. বটে এসে <b>/newpoll</b> কমান্ড দিন অথবা <b>"➕ নতুন পোল তৈরি করুন"</b> বাটনে চাপুন।
3. পোলের টাইটেল, প্রার্থীদের নাম এবং আপনার চ্যানেলের ইউজারনেম (যেমন <code>@mychannel</code>) দিন।
4. বট আপনার চ্যানেলে সুন্দর বাটনসহ পোল পোস্ট করে দেবে!

💡 <b>টিপস:</b> ভোট দেওয়ার জন্য ভোটারদের চ্যানেলে জয়েন থাকতে হবে, ফলে মেম্বার সংখ্যা দ্রুত বাড়বে!
"""

HELP_TEXT_EN = """
📖 <b>How to Create a Poll in Your Channel:</b>

1. Add this bot as an <b>Administrator</b> to your Telegram channel (enable 'Post Messages' permission).
2. Send <b>/newpoll</b> command here or tap <b>"➕ Create New Poll"</b>.
3. Provide your Poll Title, Candidate Names, and Channel username (e.g. <code>@mychannel</code>).
4. The bot will automatically publish the interactive poll to your channel!

💡 <b>Tip:</b> Voters must join your channel to vote, generating viral organic channel growth!
"""

HELP_TEXT_HI = """
📖 <b>अपने चैनल में पोल कैसे बनाएं:</b>

1. इस बॉट को अपने टेलीग्राम चैनल में <b>Administrator</b> बनाएं ('Post Messages' अनुमति चालू रखें)।
2. यहां <b>/newpoll</b> कमांड भेजें या <b>"➕ नया पोल बनाएं"</b> पर टैप करें।
3. पोल का शीर्षक (Title), उम्मीदवारों के नाम और चैनल यूजरनेम (उदा. <code>@mychannel</code>) दें।
4. बॉट आपके चैनल में सुंदर बटन के साथ पोल पोस्ट कर देगा!

💡 <b>सुझाव:</b> वोट देने के लिए सदस्यों को आपके चैनल में शामिल होना होगा, जिससे चैनल तेजी से बढ़ेगा!
"""

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext = None):
    if state:
        await state.clear()
    user = message.from_user
    user_id = user.id
    bot_info = await message.bot.get_me()
    is_admin = user_id in ADMIN_IDS

    lang = await get_user_language(user_id)
    user_name = user.full_name or user.first_name or "User"

    # Check deep link (e.g. /start create_poll)
    # Check deep link (e.g. /start create_poll)
    args = message.text.split()[1:] if message.text else []
    if args and args[0] == "create_poll":
        from bot.handlers.poll_create import start_poll_wizard
        await start_poll_wizard(message, state)
        return

    start_text = await render_start_text(bot_info.username, lang, user_name)
    await safe_send_message(
        message.bot,
        message.chat.id,
        start_text,
        reply_markup=build_main_menu(is_admin, bot_info.username, lang),
        parse_mode="HTML"
    )
    menu_confirm = (
        "✅ Bottom keyboard is active below:" if lang == "en" else
        "✅ मेनू सक्रिय है। नीचे स्थायी कीबोर्ड तैयार है:" if lang == "hi" else
        "✅ لوحة المفاتيح الدائمة جاهزة أدناه:" if lang == "ar" else
        "✅ Меню обновлено. Постоянная клавиатура внизу:" if lang == "ru" else
        "✅ নিচের স্থায়ী কিবোর্ড বাটন সবসময় রেডি:"
    )
    await message.answer(
        menu_confirm,
        reply_markup=build_persistent_menu(lang, is_admin)
    )

@router.callback_query(F.data.startswith("set_lang:"))
async def cb_set_language(callback: CallbackQuery):
    lang = callback.data.split(":")[1]
    user = callback.from_user
    user_id = user.id
    bot_info = await callback.bot.get_me()
    is_admin = user_id in ADMIN_IDS

    await set_user_language(user_id, lang)
    user_name = user.full_name or user.first_name or "User"

    start_text = await render_start_text(bot_info.username, lang, user_name)
    await safe_edit_message(
        callback.message,
        start_text,
        reply_markup=build_main_menu(is_admin, bot_info.username, lang),
        parse_mode="HTML"
    )
    if lang == "en":
        toast = "Language set to English 🇬🇧"
        menu_confirm = "✅ Menu updated. Bottom keyboard is always ready below:"
    elif lang == "hi":
        toast = "भाषा हिन्दी चुनी गई 🇮🇳"
        menu_confirm = "✅ मेनू अपडेट हो गया। नीचे हमेशा सक्रिय कीबोर्ड उपलब्ध है:"
    elif lang == "ar":
        toast = "تم تعيين اللغة إلى العربية 🇸🇦"
        menu_confirm = "✅ تم تحديث القائمة. لوحة المفاتيح الدائمة متاحة أدناه:"
    elif lang == "ru":
        toast = "Язык установлен на Русский 🇷🇺"
        menu_confirm = "✅ Меню обновлено. Постоянная клавиатура прикреплена ниже:"
    else:
        toast = "ভাষা বাংলা নির্ধারণ করা হয়েছে 🇧🇩"
        menu_confirm = "✅ মেনু আপডেট হয়েছে। নিচের স্থায়ী কিবোর্ড বাটন সবসময় রেডি:"

    await callback.answer(toast)
    await callback.message.answer(
        menu_confirm,
        reply_markup=build_persistent_menu(lang, is_admin)
    )

@router.callback_query(F.data == "menu_change_lang")
async def cb_change_language_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    lang = await get_user_language(user_id)
    prompt = f'<tg-emoji emoji-id="{LANGUAGE_CUSTOM_EMOJI_ID}">🌐</tg-emoji> <b>Please choose your language / আপনার ভাষা নির্বাচন করুন / अपनी भाषा चुनें:</b>'
    await callback.message.edit_text(
        prompt,
        reply_markup=build_language_selection_keyboard(show_back=True, lang=lang),
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext = None):
    if state:
        await state.clear()
    lang = await get_user_language(message.from_user.id)
    bot_info = await message.bot.get_me()
    add_channel_url = f"https://t.me/{bot_info.username}?startchannel=true&admin=post_messages+edit_messages+delete_messages"

    help_text = await render_help_text(bot_info.username, lang)

    if lang == "en":
        create_btn = "Create New Poll"
        add_btn = "Add Bot to Channel (1-Click) ➔"
        back_btn = "🔙 Back to Main Menu"
    elif lang == "hi":
        create_btn = "नया पोल बनाएं"
        add_btn = "चैनल में बॉट जोड़ें (1-क्লিক) ➔"
        back_btn = "🔙 मुख्य मेनू"
    else:
        create_btn = "নতুন পোল তৈরি করুন"
        add_btn = "চ্যানেলে যুক্ত করুন (১-ক্লিক এডমিন) ➔"
        back_btn = "🔙 মূল মেনুতে ফিরে যান"

    help_kb = InlineKeyboardMarkup(inline_keyboard=[
        [make_custom_button(text=create_btn, callback_data="menu_create_poll", custom_emoji_id=CREATE_POLL_CUSTOM_EMOJI_ID)],
        [make_custom_button(text=add_btn, url=add_channel_url, custom_emoji_id=ADD_CHANNEL_CUSTOM_EMOJI_ID)],
        [make_custom_button(text=back_btn, callback_data="menu_back_main", custom_emoji_id=START_MENU_CUSTOM_EMOJI_ID)]
    ])
    await safe_send_message(message.bot, message.chat.id, help_text, reply_markup=help_kb, parse_mode="HTML")


@router.callback_query(F.data == "menu_help")
async def cb_help(callback: CallbackQuery):
    user_id = callback.from_user.id
    lang = await get_user_language(user_id)
    bot_info = await callback.bot.get_me()
    add_channel_url = f"https://t.me/{bot_info.username}?startchannel=true&admin=post_messages+edit_messages+delete_messages"

    help_text = await render_help_text(bot_info.username, lang)
    create_btn = "Create New Poll" if lang == "en" else "নতুন পোল তৈরি করুন"
    add_btn = "Add Bot to Channel (1-Click) ➔" if lang == "en" else "চ্যানেলে যুক্ত করুন (১-ক্লিক এডমিন) ➔"
    back_btn = "🔙 Back to Main Menu" if lang == "en" else "🔙 মূল মেনুতে ফিরে যান"
    help_kb = InlineKeyboardMarkup(inline_keyboard=[
        [make_custom_button(text=create_btn, callback_data="menu_create_poll", custom_emoji_id=CREATE_POLL_CUSTOM_EMOJI_ID)],
        [make_custom_button(text=add_btn, url=add_channel_url, custom_emoji_id=ADD_CHANNEL_CUSTOM_EMOJI_ID)],
        [make_custom_button(text=back_btn, callback_data="menu_back_main", custom_emoji_id=START_MENU_CUSTOM_EMOJI_ID)]
    ])
    await safe_edit_message(callback.message, help_text, reply_markup=help_kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "menu_back_main")
async def cb_back_main(callback: CallbackQuery, state: FSMContext = None):
    if state:
        await state.clear()
    user = callback.from_user
    user_id = user.id
    bot_info = await callback.bot.get_me()
    is_admin = user_id in ADMIN_IDS
    lang = await get_user_language(user_id)
    user_name = user.full_name or user.first_name or "User"

    start_text = await render_start_text(bot_info.username, lang, user_name)
    await callback.message.edit_text(
        start_text,
        reply_markup=build_main_menu(is_admin, bot_info.username, lang),
        parse_mode="HTML"
    )
    await callback.answer()

# --- Automatic Channel Network Tracking & Admin Alert ---
@router.my_chat_member()
async def on_my_chat_member_update(event: ChatMemberUpdated):
    chat = event.chat
    new_member = event.new_chat_member
    user = event.from_user
    bot = event.bot

    if chat.type in ["channel", "supergroup", "group"]:
        if new_member.status in ["administrator", "creator"]:
            await save_channel(
                chat_id=chat.id,
                title=chat.title or "Untitled Channel",
                username=chat.username,
                added_by=user.id if user else None
            )
            if user:
                await record_user_channel_access(user.id, chat.id)

            # Instant Super Admin Notification
            can_post = getattr(new_member, "can_post_messages", True)
            post_status_str = "✅ Yes / অনুমোদিত" if can_post else "⚠️ No Post Permission / পোস্টের অনুমতি নেই"
            user_mention = f"@{user.username}" if (user and user.username) else (user.full_name if user else "Unknown")
            channel_link = f"@{chat.username}" if chat.username else f"ID: <code>{chat.id}</code>"

            admin_alert = (
                "🚨 <b>New Channel/Group Connected! / নতুন চ্যানেল যুক্ত হয়েছে!</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"📢 <b>Channel/Group:</b> {chat.title or 'Untitled'}\n"
                f"🆔 <b>Chat ID:</b> <code>{chat.id}</code>\n"
                f"🔗 <b>Username/Link:</b> {channel_link}\n"
                f"📂 <b>Chat Type:</b> <code>{chat.type}</code>\n"
                f"👤 <b>Added By:</b> {user_mention} (<code>{user.id if user else 'N/A'}</code>)\n"
                f"🛡️ <b>Post Messages:</b> {post_status_str}\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "📡 <i>Mass Channel Post-এ এই চ্যানেলে এখন স্বয়ংক্রিয়ভাবে ব্রডকাস্ট পৌঁছাবে!</i>"
            )

            for admin_id in ADMIN_IDS:
                try:
                    await bot.send_message(chat_id=admin_id, text=admin_alert, parse_mode="HTML")
                except Exception:
                    pass

        elif new_member.status in ["kicked", "left", "member"]:
            await deactivate_channel(chat.id)

            user_mention = f"@{user.username}" if (user and user.username) else (user.full_name if user else "Someone")
            remove_alert = (
                "⚠️ <b>Bot Removed from Channel / চ্যানেল থেকে বট সরানো হয়েছে!</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"📢 <b>Chat:</b> {chat.title or 'Untitled'} (<code>{chat.id}</code>)\n"
                f"👤 <b>Removed By:</b> {user_mention}\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "ℹ️ <i>এই চ্যানেলটি স্বয়ংক্রিয়ভাবে চ্যানেল নেটওয়ার্কে ইনঅ্যাক্টিভ করা হয়েছে।</i>"
            )
            for admin_id in ADMIN_IDS:
                try:
                    await bot.send_message(chat_id=admin_id, text=remove_alert, parse_mode="HTML")
                except Exception:
                    pass

# --- Slash Command Aliases for Quick Access ---
@router.message(Command("icons"))
async def cmd_icons(message: Message, state: FSMContext = None):
    if state:
        await state.clear()
    await reply_btn_icon_style(message)

@router.message(Command("language"))
async def cmd_language(message: Message, state: FSMContext = None):
    if state:
        await state.clear()
    await reply_btn_language(message)


# --- Persistent Bottom Menu Button Listeners ---

START_BUTTON_TEXTS = [
    "🏠 Start / মূল মেনু", "🏠 Start / Main Menu", "🏠 Start / मुख्य मेनू",
    "🏠 Start / القائمة الرئيسية", "🏠 Start / Главное меню",
    "🏠 Start", "🏠 শুরু করুন", "🏠 মূল মেনু", "🏠 Main Menu",
    "🏠 Start Bot", "🏠 মেনু",
    "Start / মূল মেনু", "Start / Main Menu", "Start / मुख्य मेनू",
    "Start / القائمة الرئيسية", "Start / Главное меню",
    "Start", "শুরু করুন", "মূল মেনু", "Main Menu",
    "Start Bot", "মেনু"
]

@router.message(F.text.in_(START_BUTTON_TEXTS))
async def reply_btn_start(message: Message, state: FSMContext = None):
    if state:
        await state.clear()
    user = message.from_user
    user_id = user.id
    bot_info = await message.bot.get_me()
    is_admin = user_id in ADMIN_IDS
    lang = await get_user_language(user_id)
    user_name = user.full_name or user.first_name or "User"

    start_text = await render_start_text(bot_info.username, lang, user_name)
    await message.answer(
        start_text,
        reply_markup=build_main_menu(is_admin, bot_info.username, lang),
        parse_mode="HTML"
    )

@router.message(F.text.in_([
    "➕ Create New Poll", "➕ নতুন পোল তৈরি করুন", "➕ नया पोल बनाएं",
    "➕ إنشاء استطلاع جديد", "➕ Создать новый опрос",
    "Create New Poll", "নতুন পোল তৈরি করুন", "नया पोल बनाएं",
    "إنشاء استطلاع جديد", "Создать новый опрос"
]))
async def reply_btn_create_poll(message: Message, state: FSMContext):
    from bot.handlers.poll_create import start_poll_wizard
    await start_poll_wizard(message, state)

@router.message(F.text.in_([
    "📊 My Polls", "📊 আমার পোল তালিকা", "📊 मेरे पोल्स",
    "📊 استطلاعاتي", "📊 Мои опросы",
    "My Polls", "আমার পোল তালিকা", "मेरे पोल्स",
    "استطلاعاتي", "Мои опросы"
]))
async def reply_btn_my_polls(message: Message, state: FSMContext = None):
    if state:
        await state.clear()
    from bot.handlers.poll_manage import cmd_mypolls
    await cmd_mypolls(message, state)

@router.message(F.text.in_([
    "📢 Add Bot to Channel", "📢 চ্যানেলে যুক্ত করুন (১-ক্লিক)", "📢 चैनल में बॉट जोड़ें",
    "📢 إضافة البوت للقناة", "📢 Добавить в канал",
    "Add Bot to Channel", "চ্যানেলে যুক্ত করুন (১-ক্লিক)", "चैनल में बॉट जोड़ें",
    "إضافة البوت للقناة", "Добавить в канал"
]))
async def reply_btn_add_channel(message: Message):
    bot_info = await message.bot.get_me()
    lang = await get_user_language(message.from_user.id)
    add_channel_url = f"https://t.me/{bot_info.username}?startchannel=true&admin=post_messages+edit_messages+delete_messages"
    
    if lang == "en":
        txt = (
            "📢 <b>1-Click Channel Administrator:</b>\n\n"
            "Tap the button below to select your Telegram Channel. The bot will automatically be added with all needed permissions!"
        )
        btn_txt = "Add Bot to Channel (1-Click) ➔"
    elif lang == "hi":
        txt = (
            "📢 <b>1-क्लिक चैनल एडमिनिस्ट्रेटर:</b>\n\n"
            "अपना टेलीग्राम चैनल चुनने के लिए नीचे दिए गए बटन पर टैप करें। बॉट आवश्यक सभी अनुमतियों के साथ स्वचालित रूप से जुड़ जाएगा!"
        )
        btn_txt = "चैनल में बॉट जोड़ें (1-क्लिक) ➔"
    else:
        txt = (
            "📢 <b>১-ক্লিক চ্যানেল এডমিন:</b>\n\n"
            "নিচের বাটনে চাপ দিয়ে আপনার টেলিগ্রাম চ্যানেল নির্বাচন করুন। প্রয়োজনীয় সব পারমিশনসহ বট স্বয়ংক্রিয়ভাবে এডমিন হয়ে যাবে!"
        )
        btn_txt = "চ্যানেলে যুক্ত করুন (১-ক্লিক এডমিন) ➔"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [make_custom_button(text=btn_txt, url=add_channel_url, custom_emoji_id=ADD_CHANNEL_CUSTOM_EMOJI_ID)]
    ])
    await message.answer(txt, reply_markup=kb, parse_mode="HTML")

@router.message(F.text.in_([
    "🏷️ Brand & Link", "🏷️ ব্র্যান্ড ও লিংক", "🏷️ ব্র্যান্ড এবং লিংক",
    "🏷️ ब्रांड और लिंक", "🏷️ العلامة والرابط", "🏷️ Бренд и ссылка"
]))
async def reply_btn_brand(message: Message):
    from bot.handlers.admin import show_credit_manager, is_super_admin
    if not is_super_admin(message.from_user.id):
        return
    await show_credit_manager(message, message.bot, message.from_user.id, is_callback=False)

@router.message(F.text.in_([
    "🎯 Button Icons", "🎯 বাটন আইকন স্টাইল", "🎯 बटन आइकन",
    "🎯 نمط الأيقونات", "🎯 Стиль иконок",
    "🎨 Button Icons", "🎨 বাটন আইকন", "🎨 বাটনের আইকন",
    "Button Icons", "বাটন আইকন স্টাইল", "बटन आइकन",
    "نمط الأيقونات", "Стиль иконок"
]))
async def reply_btn_icon_style(message: Message):
    user_id = message.from_user.id
    from bot.database.db import get_user_icon_style
    cur_style = await get_user_icon_style(user_id)
    saved_emojis = await get_user_saved_emojis(user_id)
    kb = build_icon_style_keyboard(cur_style, back_to="main", saved_emojis=saved_emojis)
    lang = await get_user_language(user_id)
    if lang == "en":
        txt = "🎯 <b>Choose Your Poll Button Icon Theme:</b>\n\nSelect your personal icon style or use custom premium emoji codes:"
    elif lang == "hi":
        txt = "🎯 <b>अपने पोल बटन आइकन की थीम चुनें:</b>\n\nअपनी व्यक्तिगत आइकन शैली चुनें या कस्टम प्रीमियम इमोजी कोड का उपयोग करें:"
    else:
        txt = "🎯 <b>আপনার পোলের বাটন আইকন স্টাইল বেছে নিন:</b>\n\nআপনার তৈরি করা পোলের জন্য পছন্দের আইকন থিম সিলেক্ট করুন অথবা নিজের কাস্টম প্রিমিয়াম ইমোজি কোড ব্যবহার করুন:"
    await message.answer(txt, reply_markup=kb, parse_mode="HTML")

@router.message(F.text.in_([
    "🌐 Language", "🌐 ভাষা পরিবর্তন", "🌐 भाषा", "🌐 اللغة", "🌐 Язык",
    "Language", "ভাষা পরিবর্তন", "भाषा", "اللغة", "Язык"
]))
async def reply_btn_language(message: Message):
    lang = await get_user_language(message.from_user.id)
    prompt = f'<tg-emoji emoji-id="{LANGUAGE_CUSTOM_EMOJI_ID}">🌐</tg-emoji> <b>Please choose your language / আপনার ভাষা নির্বাচন করুন / अपनी भाषा चुनें:</b>'
    await message.answer(
        prompt,
        reply_markup=build_language_selection_keyboard(show_back=True, lang=lang),
        parse_mode="HTML"
    )

@router.message(F.text.in_([
    "ℹ️ Help & Guide", "ℹ️ ব্যবহারের নিয়ম ও গাইড", "ℹ️ सहायता एवं गाइड",
    "ℹ️ مساعدة ودليل", "ℹ️ Помощь и гид",
    "ℹ️ Help & Support", "ℹ️ ব্যবহারের নিয়ম ও সাপোর্ট",
    "Help & Guide", "ব্যবহারের নিয়ম ও গাইড", "सहायता एवं गाइड",
    "مساعدة ودليل", "Помощь и гид",
    "Help & Support", "ব্যবহারের নিয়ম ও সাপোর্ট"
]))
async def reply_btn_help(message: Message):
    await cmd_help(message)

@router.message(F.text.in_(["👑 Admin Panel", "👑 এডমিন প্যানেল", "👑 सुपर एडमिन"]))
async def reply_btn_admin(message: Message):
    from bot.handlers.admin import show_admin_panel, is_admin
    if is_admin(message.from_user.id):
        await show_admin_panel(message, is_callback=False, user_id=message.from_user.id)

# --- User-Facing Poll Button Icon Style Handlers (100% Free & Open For All) ---

@router.callback_query(F.data == "user_set_icon_style")
async def cb_user_set_icon_style(callback: CallbackQuery):
    user_id = callback.from_user.id
    cur_style = await get_user_icon_style(user_id)
    is_user_admin = user_id in ADMIN_IDS
    back_to = "admin" if is_user_admin else "main"
    saved_emojis = await get_user_saved_emojis(user_id)
    kb = build_icon_style_keyboard(cur_style, back_to=back_to, saved_emojis=saved_emojis)
    lang = await get_user_language(user_id)
    if lang == "en":
        txt = (
            "🎯 <b>Choose Your Poll Button Icon Theme:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Select your favorite icon theme for your polls, or add custom premium emoji codes:\n\n"
            "• <b>👑 Dynamic Leader:</b> Animated dynamic ranking icons!\n"
            "• <b>💎 VIP Diamond:</b> Sparkling luxury diamond.\n"
            "• <b>⚡ Lightning Zap:</b> Energetic lightning bolt.\n"
            "• <b>⭐ Golden Star:</b> Shining gold stars.\n\n"
            "👇 <i>Tap below to select or add your custom premium emoji code:</i>"
        )
    elif lang == "hi":
        txt = (
            "🎯 <b>अपने पोल बटन आइकन की थीम चुनें:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "अपने पोल्स के लिए पसंदीदा आइकन शैली चुनें या कस्टम प्रीमियम इमोजी कोड जोड़ें:\n\n"
            "• <b>👑 Dynamic Leader:</b> डायनामिक लीडर आइकन!\n"
            "• <b>💎 VIP Diamond:</b> शानदार डायमंड।\n\n"
            "👇 <i>नीचे क्लिक करके स्टाइल चुनें:</i>"
        )
    else:
        txt = (
            "🎯 <b>আপনার পোলের বাটন আইকন স্টাইল বেছে নিন:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "আপনার তৈরি করা পোলের বাটনে কোন ধরনের প্রিমিয়াম আইকন থাকবে তা নির্বাচন করুন:\n\n"
            "• <b>👑 Dynamic Leader:</b> ভোটের অগ্রগতির সাথে লাইভ লিডার আইকন।\n"
            "• <b>💎 VIP Diamond:</b> এক্সক্লুসিভ ভিআইপি ডায়মন্ড।\n"
            "• <b>⚡ Lightning Zap:</b> পাওয়ারফুল লাইটনিং আইকন।\n"
            "• <b>⭐ Golden Star:</b> গোল্ডেন স্টার প্রিমিয়াম লুক।\n\n"
            "👇 <i>পছন্দের স্টাইল সিলেক্ট করুন অথবা নিচে থেকে কাস্টম কোড যোগ করুন:</i>"
        )
    try:
        await callback.message.edit_text(txt, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(txt, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery):
    await callback.answer()

@router.callback_query(F.data.startswith("del_custom_emoji:"))
async def cb_delete_custom_emoji(callback: CallbackQuery):
    parts = callback.data.split(":")
    emoji_id = parts[1] if len(parts) > 1 else ""
    raw_back = parts[2] if len(parts) > 2 else "main"
    user_id = callback.from_user.id
    is_user_admin = user_id in ADMIN_IDS
    back_to = "admin" if (raw_back == "admin" and is_user_admin) else "main"

    await delete_user_saved_emoji(user_id, emoji_id)
    cur_style = await get_user_icon_style(user_id)
    if emoji_id in cur_style:
        await set_user_icon_style(user_id, "dynamic")
        cur_style = "dynamic"

    saved = await get_user_saved_emojis(user_id)
    kb = build_icon_style_keyboard(cur_style, back_to=back_to, saved_emojis=saved)
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass
    await callback.answer("🗑️ Custom emoji deleted / সংরক্ষিত ইমোজি মুছে ফেলা হয়েছে!", show_alert=False)

@router.callback_query(F.data.startswith("set_icon_style:"))
async def cb_set_icon_style(callback: CallbackQuery):
    parts = callback.data.split(":")
    # Handling cases where style has colons like custom_tg:ID:FALLBACK
    if callback.data.startswith("set_icon_style:custom_tg:"):
        sub_parts = callback.data.split(":")
        new_style = f"{sub_parts[1]}:{sub_parts[2]}:{sub_parts[3]}"
        raw_back = sub_parts[4] if len(sub_parts) > 4 else "main"
    else:
        new_style = parts[1]
        raw_back = parts[2] if len(parts) > 2 else "main"

    user_id = callback.from_user.id
    is_user_admin = user_id in ADMIN_IDS

    # Always save to this user's personal preferred icon style
    await set_user_icon_style(user_id, new_style)

    # If super admin, also update global default
    if is_user_admin:
        await set_button_icon_style(new_style)

    # Strictly enforce: non-admins NEVER get back_to="admin"
    back_to = "admin" if (raw_back == "admin" and is_user_admin) else "main"

    saved = await get_user_saved_emojis(user_id)
    kb = build_icon_style_keyboard(new_style, back_to=back_to, saved_emojis=saved)
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass
    await callback.answer("✅ Button icon style updated / আইকন স্টাইল সেভ হয়েছে!", show_alert=False)

@router.callback_query(F.data.startswith("prompt_custom_icon:"))
async def cb_prompt_custom_icon(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    raw_back = parts[1] if len(parts) > 1 else "main"
    back_to = "admin" if (raw_back == "admin" and callback.from_user.id in ADMIN_IDS) else "main"
    await state.set_state(UserIconStates.custom_icon)
    await state.update_data(back_to=back_to)

    msg = (
        "🎨 <b>Custom Button Emoji / কাস্টম বাটন ইমোজি নির্ধারণ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "আপনার পছন্দের যেকোনো <b>Telegram Premium Emoji Code (ID)</b> অথবা সরাসরি প্রিমিয়াম ইমোজি পাঠান।\n\n"
        "👉 <b>যেভাবে পাঠাতে পারেন:</b>\n"
        "• সরাসরি প্রিমিয়াম ইমোজি কোড (যেমন: <code>6271494293383286950</code>)\n"
        "• কোড ও নাম একসাথে: <code>6271494293383286950 VIP Diamond</code>\n"
        "• আপনার টেলিগ্রাম প্রিমিয়াম কিবোর্ড থেকে সরাসরি যেকোনো ইমোজি সেন্ড করুন\n"
        "• সাধারণ ইমোজি (যেমন: 💎, 🌟, 🔥, 👑, 🎯)\n\n"
        "✨ <i>আপনার দেওয়া ইমোজিটি আপনার অ্যাকাউন্টে সবসময় <b>Saved</b> থাকবে এবং আপনি যেকোনো সময় এটি পোলের অপশনে ব্যবহার করতে পারবেন!</i>\n\n"
        "বাতিল করতে /cancel লিখুন।"
    )
    await safe_edit_message(callback.message, msg, parse_mode="HTML")
    await callback.answer()

@router.message(UserIconStates.custom_icon)
async def process_custom_icon(message: Message, state: FSMContext):
    if message.text and message.text.startswith("/cancel"):
        await state.clear()
        await message.answer("❌ Cancelled / বাতিল করা হয়েছে।")
        return

    data = await state.get_data()
    raw_back = data.get("back_to", "main")
    back_to = "admin" if (raw_back == "admin" and message.from_user.id in ADMIN_IDS) else "main"
    await state.clear()

    user_id = message.from_user.id
    raw_text = (message.text or message.caption or "").strip()
    custom_emoji_id = None
    fallback_char = "✨"
    custom_name = ""

    # 1. Check message entities for Telegram Premium custom emoji
    for entity in (message.entities or []):
        if entity.type == "custom_emoji" and entity.custom_emoji_id:
            custom_emoji_id = str(entity.custom_emoji_id)
            if raw_text and entity.offset is not None:
                fallback_char = raw_text[entity.offset : entity.offset + (entity.length or 2)]
            break

    # 2. Check HTML text for <tg-emoji> tags
    if not custom_emoji_id and message.html_text:
        m = re.search(r'<tg-emoji\b[^>]*(?:emoji-id|id)="([0-9]+)"[^>]*>([\s\S]*?)</tg-emoji>', message.html_text, re.IGNORECASE)
        if m:
            custom_emoji_id = m.group(1)
            fallback_char = m.group(2) or "✨"

    # 3. Check for raw numeric Telegram Premium Emoji ID (15-22 digits)
    if not custom_emoji_id:
        id_match = re.search(r'\b(\d{15,22})\b', raw_text)
        if id_match:
            custom_emoji_id = id_match.group(1)
            # Remaining text is the custom name
            rest_name = re.sub(r'\b\d{15,22}\b', '', raw_text).strip()
            if rest_name:
                custom_name = rest_name[:30].strip()

    if custom_emoji_id:
        if not custom_name:
            custom_name = f"Custom {custom_emoji_id[-6:]}"
        # Save to user's saved custom emojis table!
        await add_user_saved_emoji(user_id, custom_emoji_id, name=custom_name, fallback_char=fallback_char)
        custom_val = f"custom_tg:{custom_emoji_id}:{fallback_char}"
        display_name = f'<tg-emoji emoji-id="{custom_emoji_id}">{fallback_char}</tg-emoji> <b>{html.escape(custom_name)}</b>\n🆔 <b>Emoji Code:</b> <code>{custom_emoji_id}</code>'
    else:
        clean_icon = raw_text[:10].strip() or "🗳️"
        custom_val = f"custom:{clean_icon}"
        display_name = f"<code>{html.escape(clean_icon)}</code>"

    await set_user_icon_style(user_id, custom_val)
    if user_id in ADMIN_IDS:
        await set_button_icon_style(custom_val)

    saved_emojis = await get_user_saved_emojis(user_id)
    kb = build_icon_style_keyboard(custom_val, back_to=back_to, saved_emojis=saved_emojis)
    await message.answer(
        f"✅ <b>Custom Icon Saved / কাস্টম আইকন সফলভাবে সেভ হয়েছে!</b>\n\n"
        f"🎯 <b>নির্বাচিত আইকন:</b> {display_name}\n\n"
        f"✨ এই প্রিমিয়াম ইমোজিটি আপনার অ্যাকাউন্টে স্থায়ীভাবে সেভ থাকবে এবং আপনার তৈরি করা সকল পোলের অপশনে ব্যবহৃত হবে!",
        reply_markup=kb,
        parse_mode="HTML"
    )

