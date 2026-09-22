import html
import re
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from aiogram import Router, F, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from bot.config import ADMIN_IDS
from bot.database.db import (
    create_poll, set_poll_message_id, save_channel, get_candidates, get_user_language,
    get_user_selectable_channels, get_button_icon_style, get_user_icon_style, get_last_user_poll,
    get_poll_parts, get_next_part_number, get_poll, update_poll_title,
    is_user_authorized_for_channel_db, record_user_channel_access,
    remove_user_channel_permission
)
from bot.keyboards.inline import (
    build_poll_keyboard, build_duration_keyboard, build_winner_count_keyboard,
    build_poll_language_keyboard, make_custom_button, CREATE_POLL_CUSTOM_EMOJI_ID,
    ADD_CHANNEL_CUSTOM_EMOJI_ID, HELP_CUSTOM_EMOJI_ID, START_MENU_CUSTOM_EMOJI_ID,
    STEP1_TITLE_CUSTOM_EMOJI_ID, STEP2_CANDIDATES_CUSTOM_EMOJI_ID,
    STEP3_CHANNEL_CUSTOM_EMOJI_ID, STEP4_DURATION_CUSTOM_EMOJI_ID
)
from bot.templates import render_poll_card, render_poll_cta, format_datetime_readable, safe_send_message, safe_edit_message

router = Router()

class PollCreationState(StatesGroup):
    title = State()
    candidates = State()
    channel = State()
    duration = State()
    winner_count = State()
    poll_language = State()
    contact_id = State()
    confirm = State()
    add_part = State()

def get_base_title(title: str) -> str:
    """Strips any [Part X] or [পর্ব X] suffixes from a title."""
    return re.sub(r"\s*\[(Part|পর্ব)\s*\d+\]\s*$", "", title, flags=re.IGNORECASE).strip()

async def check_command_breakout(message: Message, state: FSMContext) -> bool:
    """
    If user sends a slash command OR taps a persistent menu reply button
    while in an FSM creation state, immediately clear state and route to the
    corresponding command handler so the user is never stuck and buttons/commands
    are never swallowed as poll text.
    Returns True if handled (caller should return immediately).
    """
    raw_text = (message.text or "").strip()
    if not raw_text:
        return False

    # 1. Slash commands
    if raw_text.startswith("/"):
        cmd_raw = raw_text.split()[0].lower()
        cmd = cmd_raw.split("@")[0]  # strip bot username if present, e.g. /mypolls@bot

        if cmd == "/cancel":
            await state.clear()
            await message.answer("❌ Poll creation cancelled / পোল তৈরির প্রক্রিয়া বাতিল করা হয়েছে।")
            return True
        elif cmd == "/mypolls":
            await state.clear()
            from bot.handlers.poll_manage import show_user_polls
            await show_user_polls(message.from_user.id, message)
            return True
        elif cmd == "/start":
            await state.clear()
            from bot.handlers.start import cmd_start
            await cmd_start(message)
            return True
        elif cmd == "/help":
            await state.clear()
            from bot.handlers.start import cmd_help
            await cmd_help(message)
            return True
        elif cmd in ("/newpoll", "/createpoll"):
            await state.clear()
            await start_poll_wizard(message, state)
            return True
        elif cmd == "/icons":
            await state.clear()
            from bot.handlers.start import reply_btn_icon_style
            await reply_btn_icon_style(message)
            return True
        elif cmd == "/language":
            await state.clear()
            from bot.handlers.start import reply_btn_language
            await reply_btn_language(message)
            return True
        elif cmd in ("/channels", "/mychannels", "/addedchannels"):
            await state.clear()
            from bot.handlers.user_channels import show_user_channels
            await show_user_channels(message, message.bot, message.from_user.id, is_callback=False)
            return True
        elif cmd == "/admin":
            if message.from_user.id in ADMIN_IDS:
                await state.clear()
                from bot.handlers.admin import cmd_admin
                await cmd_admin(message)
                return True
            return False

        await state.clear()
        await message.answer("❌ Process cancelled / প্রক্রিয়াটি বাতিল করা হয়েছে।")
        return True

    # 2. Persistent Menu Reply Buttons (across all supported languages)
    from bot.handlers.start import START_BUTTON_TEXTS, ADDED_CHANNELS_BUTTON_TEXTS

    if raw_text in START_BUTTON_TEXTS:
        await state.clear()
        from bot.handlers.start import reply_btn_start
        await reply_btn_start(message, None)
        return True

    if raw_text in (
        "➕ Create New Poll", "➕ নতুন পোল তৈরি করুন", "➕ नया पोल बनाएं",
        "➕ إنشاء استطلاع جديد", "➕ Создать новый опрос",
        "Create New Poll", "নতুন পোল তৈরি করুন", "नया पोल बनाएं",
        "إنشاء استطلاع جديد", "Создать новый опрос"
    ):
        await state.clear()
        await start_poll_wizard(message, state)
        return True

    if raw_text in (
        "📊 My Polls", "📊 আমার পোল তালিকা", "📊 मेरे पोल्स",
        "📊 استطلاعاتي", "📊 Мои опросы",
        "My Polls", "আমার পোল তালিকা", "मेरे पोल्स",
        "استطلاعاتي", "Мои опросы"
    ):
        await state.clear()
        from bot.handlers.poll_manage import cmd_mypolls
        await cmd_mypolls(message, None)
        return True

    if raw_text in ADDED_CHANNELS_BUTTON_TEXTS:
        await state.clear()
        from bot.handlers.user_channels import show_user_channels
        await show_user_channels(message, message.bot, message.from_user.id, is_callback=False)
        return True

    if raw_text in (
        "📢 Add Bot to Channel", "📢 চ্যানেলে যুক্ত করুন (১-ক্লিক)", "📢 चैनल में बॉट जोड़ें",
        "📢 إضافة البوت للقناة", "📢 Добавить в канал",
        "Add Bot to Channel", "চ্যানেলে যুক্ত করুন (১-ক্লিক)", "चैनल में बॉट जोड़ें",
        "إضافة البوت للقناة", "Добавить в канал"
    ):
        await state.clear()
        from bot.handlers.start import reply_btn_add_channel
        await reply_btn_add_channel(message)
        return True

    if raw_text in (
        "🎯 Button Icons", "🎯 বাটন আইকন স্টাইল", "🎯 बटन आइकन",
        "🎯 نمط الأيقونات", "🎯 Стиль иконок",
        "🎨 Button Icons", "🎨 বাটন আইকন", "🎨 বাটনের আইকন",
        "Button Icons", "বাটন আইকন স্টাইল", "बटन आइकन",
        "نمط الأيقونات", "Стиль иконок"
    ):
        await state.clear()
        from bot.handlers.start import reply_btn_icon_style
        await reply_btn_icon_style(message)
        return True

    if raw_text in (
        "🌐 Language", "🌐 ভাষা পরিবর্তন", "🌐 भाषा", "🌐 اللغة", "🌐 Язык",
        "Language", "ভাষা পরিবর্তন", "ভাষা", "اللغة", "Язык"
    ):
        await state.clear()
        from bot.handlers.start import reply_btn_language
        await reply_btn_language(message)
        return True

    if raw_text in (
        "ℹ️ Help & Guide", "ℹ️ ব্যবহারের নিয়ম ও গাইড", "ℹ️ सहायता एवं गाइड",
        "ℹ️ مساعدة ودليل", "ℹ️ Помощь и гид",
        "ℹ️ Help & Support", "ℹ️ ব্যবহারের নিয়ম ও সাপোর্ট",
        "Help & Guide", "ব্যবহারের নিয়ম ও গাইড", "सहायता एवं गाइड",
        "مساعدة ودليل", "Помощь и гид",
        "Help & Support", "ব্যবহারের নিয়ম ও সাপোর্ট"
    ):
        await state.clear()
        from bot.handlers.start import reply_btn_help
        await reply_btn_help(message)
        return True

    if raw_text in ("👑 Admin Panel", "👑 এডমিন প্যানেল", "👑 সুপার এডমিন"):
        if message.from_user.id in ADMIN_IDS:
            await state.clear()
            from bot.handlers.admin import cmd_admin
            await cmd_admin(message)
            return True

    return False

async def publish_single_part(
    bot: Bot,
    creator_id: int,
    parent_poll: Dict[str, Any],
    candidates_list: List[str],
    part_number: int,
    lang: str = "bn"
) -> Tuple[int, Optional[str]]:
    poll_lang = parent_poll.get("language") or lang
    base_title = get_base_title(parent_poll["title"])
    part_suffix = f"[Part {part_number}]" if poll_lang == "en" else f"[পর্ব {part_number}]"
    part_title = f"{base_title} {part_suffix}"

    target_chat_id = parent_poll["target_chat_id"]
    target_chat_title = parent_poll["target_chat_title"]
    target_chat_username = parent_poll.get("target_chat_username")
    ends_at = parent_poll.get("ends_at")
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    root_poll_id = parent_poll.get("parent_poll_id") or parent_poll["poll_id"]

    w_count = parent_poll.get("winner_count") or 1
    i_style = parent_poll.get("icon_style") or await get_user_icon_style(creator_id)

    new_poll_id = await create_poll(
        creator_id=creator_id,
        target_chat_id=target_chat_id,
        target_chat_title=target_chat_title,
        target_chat_username=target_chat_username,
        title=part_title,
        candidates=candidates_list,
        ends_at=ends_at,
        created_at=created_at,
        parent_poll_id=root_poll_id,
        part_number=part_number,
        winner_count=w_count,
        icon_style=i_style,
        language=poll_lang,
        contact_username=parent_poll.get("contact_username")
    )

    bot_info = await bot.get_me()
    channel_msg_text = await render_poll_card(
        part_title,
        bot_info.username,
        lang=poll_lang,
        ends_at=ends_at,
        created_at=created_at,
        winner_count=w_count,
        creator_id=creator_id
    )
    cta_text, cta_url = await render_poll_cta(bot_info.username, lang=poll_lang, creator_id=creator_id)
    real_candidates = await get_candidates(new_poll_id)
    poll_kb = build_poll_keyboard(
        new_poll_id,
        real_candidates,
        bot_info.username,
        cta_text=cta_text,
        cta_url=cta_url,
        icon_style=i_style
    )

    sent_msg = await safe_send_message(
        bot,
        chat_id=target_chat_id,
        text=channel_msg_text,
        reply_markup=poll_kb,
        parse_mode="HTML"
    )
    await set_poll_message_id(new_poll_id, sent_msg.message_id)

    if target_chat_username:
        channel_link = f"https://t.me/{target_chat_username}/{sent_msg.message_id}"
    elif str(target_chat_id).startswith("-100"):
        internal_id = str(abs(target_chat_id))[3:]
        channel_link = f"https://t.me/c/{internal_id}/{sent_msg.message_id}"
    else:
        channel_link = None

    return new_poll_id, channel_link

async def safe_answer_or_edit(
    msg_or_cb,
    text: str,
    reply_markup=None,
    is_callback: bool = False,
    parse_mode: str = "HTML",
    **kwargs
):
    from bot.templates import strip_tg_emoji_tags, strip_button_custom_emojis
    try:
        if is_callback:
            target = getattr(msg_or_cb, "message", msg_or_cb)
            if hasattr(target, "edit_text"):
                return await target.edit_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode, **kwargs)
            elif hasattr(msg_or_cb, "edit_text"):
                return await msg_or_cb.edit_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode, **kwargs)
        if hasattr(msg_or_cb, "answer"):
            return await msg_or_cb.answer(text=text, reply_markup=reply_markup, parse_mode=parse_mode, **kwargs)
        elif hasattr(msg_or_cb, "edit_text"):
            return await msg_or_cb.edit_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode, **kwargs)
    except Exception as e:
        err_msg = str(e).lower()
        if "message is not modified" in err_msg:
            return None
        if "custom emoji" in err_msg or "button" in err_msg:
            fallback_text = strip_tg_emoji_tags(text) if parse_mode == "HTML" else text
            fallback_markup = strip_button_custom_emojis(reply_markup)
            if is_callback:
                target = getattr(msg_or_cb, "message", msg_or_cb)
                if hasattr(target, "edit_text"):
                    return await target.edit_text(text=fallback_text, reply_markup=fallback_markup, parse_mode=parse_mode, **kwargs)
                elif hasattr(msg_or_cb, "edit_text"):
                    return await msg_or_cb.edit_text(text=fallback_text, reply_markup=fallback_markup, parse_mode=parse_mode, **kwargs)
            if hasattr(msg_or_cb, "answer"):
                return await msg_or_cb.answer(text=fallback_text, reply_markup=fallback_markup, parse_mode=parse_mode, **kwargs)
            elif hasattr(msg_or_cb, "edit_text"):
                return await msg_or_cb.edit_text(text=fallback_text, reply_markup=fallback_markup, parse_mode=parse_mode, **kwargs)
        raise

@router.message(Command("newpoll"))
@router.message(Command("createpoll"))
async def start_poll_wizard(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(PollCreationState.title)
    await safe_answer_or_edit(
        message,
        f'<tg-emoji emoji-id="{STEP1_TITLE_CUSTOM_EMOJI_ID}">📝</tg-emoji> <b>Step 1/4: Poll Title / পোলের শিরোনাম</b>\n\n'
        "Enter your poll question or giveaway title:\n"
        "<i>আপনার পোলের টাইটেল বা প্রশ্ন লিখে পাঠান।</i>\n"
        "<i>(Example: 🎉 Eid Mega Giveaway 2026: Vote Your Favorite Creator!)</i>\n\n"
        "To cancel, type /cancel",
        parse_mode="HTML"
    )

@router.callback_query(F.data == "menu_create_poll")
async def cb_start_poll_wizard(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass
    await state.clear()
    await state.set_state(PollCreationState.title)
    user_lang = await get_user_language(callback.from_user.id)
    back_btn_text = "🔙 Cancel & Back / ফিরে যান" if user_lang == "bn" else "🔙 Cancel & Back to Menu"
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [make_custom_button(text=back_btn_text, callback_data="menu_back_main", custom_emoji_id=START_MENU_CUSTOM_EMOJI_ID)]
    ])
    await safe_answer_or_edit(
        callback,
        f'<tg-emoji emoji-id="{STEP1_TITLE_CUSTOM_EMOJI_ID}">📝</tg-emoji> <b>Step 1/4: Poll Title / পোলের শিরোনাম</b>\n\n'
        "Enter your poll question or giveaway title:\n"
        "<i>আপনার পোলের টাইটেল বা প্রশ্ন লিখে পাঠান।</i>\n"
        "<i>(Example: 🎉 Eid Mega Giveaway 2026: Vote Your Favorite Creator!)</i>\n\n"
        "To cancel, type /cancel or tap below:",
        reply_markup=cancel_kb,
        is_callback=True,
        parse_mode="HTML"
    )

@router.message(Command("cancel"))
async def cancel_wizard(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("No active process / কোনো সক্রিয় প্রক্রিয়া নেই।")
        return
    await state.clear()
    await message.answer("❌ Poll creation cancelled / পোল তৈরির প্রক্রিয়া বাতিল করা হয়েছে।")

@router.message(PollCreationState.title)
async def process_title(message: Message, state: FSMContext):
    if await check_command_breakout(message, state):
        return
    title = message.html_text.strip() if message.html_text else (message.text.strip() if message.text else "")
    plain_title = message.text.strip() if message.text else ""
    user_lang = await get_user_language(message.from_user.id)
    if len(plain_title) < 3:
        if user_lang == "en":
            err_title = (
                "⚠️ <b>Auto-Help: Title Too Short!</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "🔴 <b>Issue:</b> The title is less than 3 characters.\n"
                "💡 <b>Why:</b> A clear giveaway or contest title helps channel members understand what they are voting for.\n\n"
                "🛠️ <b>Example (You can copy & modify):</b>\n"
                "<code>🎉 Eid Mega Giveaway 2026: Vote Your Favorite Creator!</code>\n\n"
                "<i>Please enter your title again:</i>"
            )
        else:
            err_title = (
                "⚠️ <b>অটো-হেল্প: শিরোনাম খুব ছোট!</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "🔴 <b>সমস্যা:</b> আপনার পোলের শিরোনাম ৩ অক্ষরের কম হয়েছে।\n"
                "💡 <b>কেন:</b> স্পষ্ট ও আকর্ষণীয় টাইটেল দিলে চ্যানেলের সদস্যরা সহজে ভোট দিতে আকৃষ্ট হয়।\n\n"
                "🛠️ <b>উদাহরণ (কপি করে দিতে পারেন):</b>\n"
                "<code>🎉 ঈদ মেগা গিভঅ্যাওয়ে ২০২৬: পছন্দের ক্রিয়েটরকে ভোট দিন!</code>\n\n"
                "<i>অনুগ্রহ করে আপনার পোলের শিরোনামটি লিখে পাঠান:</i>"
            )
        await message.answer(err_title, parse_mode="HTML")
        return

    await state.update_data(title=title)

    data = await state.get_data()
    # If candidates were already provided (e.g. from pasted candidates flow)
    if data.get("candidates"):
        candidates = data["candidates"]
        chunks = data.get("candidate_chunks") or [candidates]
        if len(chunks) > 1:
            if user_lang == "en":
                chunk_summary = "\n".join([f"   • Part {i+1}: {len(ch)} candidates" for i, ch in enumerate(chunks)])
                info_note = (
                    f"💡 <b>Received {len(candidates)} candidates!</b>\n\n"
                    f"Each poll comfortably fits up to 29 candidates. Your contest will be automatically published as <b>{len(chunks)} sequential parts</b>:\n"
                    f"{chunk_summary}\n\n"
                    f"All parts will be published consecutively in your channel under the same title with the same timer!"
                )
            else:
                chunk_summary = "\n".join([f"   • পর্ব {i+1}: {len(ch)} জন" for i, ch in enumerate(chunks)])
                info_note = (
                    f"💡 <b>মোট {len(candidates)} জন প্রার্থীর নাম পাওয়া গেছে!</b>\n\n"
                    f"প্রতিটি পোলে সর্বোচ্চ ২৯ জন সুন্দরভাবে সাজানো থাকে। আপনার এই কনটেস্টটি স্বয়ংক্রিয়ভাবে <b>{len(chunks)} টি পর্বে (Parts)</b> ভাগ হয়ে চ্যানেলে পরপর পোস্ট হবে:\n"
                    f"{chunk_summary}\n\n"
                    f"সবগুলো পর্ব একই শিরোনামে একই সময়সীমা অনুযায়ী চ্যানেলে একটার নিচে আরেকটা পাবলিশ হবে।"
                )
            await message.answer(info_note, parse_mode="HTML")

        await state.set_state(PollCreationState.channel)
        preselected_id = data.get("preselected_target_chat_id")
        if preselected_id:
            await validate_and_proceed_channel(message.bot, preselected_id, state, message, message.from_user.id, False)
            return
        await show_channel_selection_prompt(message.bot, message.from_user.id, message, is_callback=False)
        return

    await state.set_state(PollCreationState.candidates)
    if user_lang == "en":
        prompt = (
            f'<tg-emoji emoji-id="{STEP2_CANDIDATES_CUSTOM_EMOJI_ID}">👥</tg-emoji> <b>Step 2/4: Candidates / অপশন নির্ধারণ</b>\n\n'
            "Send candidate names or options (separated by newlines or commas).\n"
            "💡 <i>You can add 29 candidates for Part 1. If you send more than 29 candidates, they will automatically be split into sequential parts!</i>\n\n"
            "<b>Example:</b>\n"
            "<code>Candidate 1\nCandidate 2\nCandidate 3\n...</code>\n\n"
            "Cancel: /cancel"
        )
    else:
        prompt = (
            f'<tg-emoji emoji-id="{STEP2_CANDIDATES_CUSTOM_EMOJI_ID}">👥</tg-emoji> <b>Step 2/4: Candidates / অপশন নির্ধারণ</b>\n\n'
            "প্রার্থীদের নাম বা অপশনগুলো প্রতি লাইনে একটি করে অথবা কমা দিয়ে লিখে পাঠান।\n"
            "💡 <i>১ম পর্বের জন্য ২৯ জনের নাম দিতে পারবেন। আর ২৯ জনের বেশি দিলে স্বয়ংক্রিয়ভাবে পরবর্তী পর্ব (Part 2, Part 3) হিসেবে পরপর পোস্ট হবে!</i>\n\n"
            "<b>উদাহরণ:</b>\n"
            "<code>প্রার্থী ১\nপ্রার্থী ২\nপ্রার্থী ৩\n...</code>\n\n"
            "বাতিল করতে: /cancel"
        )
    await safe_answer_or_edit(message, prompt, parse_mode="HTML")

async def show_channel_selection_prompt(bot: Bot, user_id: int, message_or_cb, is_callback: bool = False):
    user_lang = await get_user_language(user_id)
    selectable_channels = await get_user_selectable_channels(user_id)
    bot_info = await bot.get_me()
    clean_bot = bot_info.username.lstrip("@")
    add_channel_url = f"https://t.me/{clean_bot}?startchannel=true&admin=post_messages+edit_messages+delete_messages"

    channel_buttons = []
    # 1-Click Add Channel button at the very top!
    add_btn_text = "Add Bot to Channel (1-Click) ➔" if user_lang == "en" else "নতুন চ্যানেলে এডমিন করুন (১-ক্লিক) ➔"
    channel_buttons.append([make_custom_button(text=add_btn_text, url=add_channel_url, custom_emoji_id=ADD_CHANNEL_CUSTOM_EMOJI_ID)])

    for ch in selectable_channels[:8]:
        ch_type = "🔒 Private" if not ch.get("username") else f"@{ch['username']}"
        btn_text = f"📢 {ch['title'][:20]} ({ch_type})"
        channel_buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"sel_chan:{ch['chat_id']}")])

    channel_buttons.append([InlineKeyboardButton(text="❌ Cancel / বাতিল", callback_data="cancel_publish")])
    chan_kb = InlineKeyboardMarkup(inline_keyboard=channel_buttons)

    if user_lang == "en":
        prompt = (
            f'<tg-emoji emoji-id="{STEP3_CHANNEL_CUSTOM_EMOJI_ID}">📢</tg-emoji> <b>Step 3/4: Target Channel / চ্যানেল নির্ধারণ</b>\n\n'
            "Choose or provide your target channel:\n\n"
            "👉 <b>Option 1 (Fastest):</b> Tap <b>'Add Bot to Channel (1-Click)'</b> above to select a channel.\n"
            "👉 <b>Option 2:</b> Tap an existing channel button below.\n"
            "👉 <b>Option 3 (For Private Channels):</b> Simply <b>forward any message</b> from your private channel here!\n"
            "👉 <b>Option 4:</b> Send public username (e.g. <code>@MyChannel</code>) or Channel ID.\n\n"
            "⚠️ <i>Requirements: Bot must be an Administrator in your channel with 'Post Messages' permission!</i>"
        )
    else:
        prompt = (
            f'<tg-emoji emoji-id="{STEP3_CHANNEL_CUSTOM_EMOJI_ID}">📢</tg-emoji> <b>Step 3/4: Target Channel / চ্যানেল নির্ধারণ</b>\n\n'
            "যে চ্যানেলে পোল পাঠাতে চান তা নির্বাচন করুন:\n\n"
            "👉 <b>পদ্ধতি ১ (সবচেয়ে সহজ):</b> উপরের <b>'নতুন চ্যানেলে এডমিন করুন (১-ক্লিক)'</b> বাটনে চাপ দিন।\n"
            "👉 <b>পদ্ধতি ২:</b> নিচের তালিকা থেকে আপনার চ্যানেলটিতে সরাসরি ক্লিক করুন।\n"
            "👉 <b>পদ্ধতি ৩ (প্রাইভেট চ্যানেলের জন্য):</b> আপনার চ্যানেল থেকে যেকোনো একটি পোস্ট এখানে <b>Forward (ফরওয়ার্ড)</b> করুন! বট চিনে নেবে।\n"
            "👉 <b>পদ্ধতি ৪:</b> পাবলিক চ্যানেলের ইউজারনেম (যেমন: <code>@MyChannel</code>) বা আইডি লিখে পাঠান।\n\n"
            "⚠️ <i>বটটিকে অবশ্যই চ্যানেলে এডমিন বানিয়ে মেসেজ পোস্ট করার অনুমতি দিতে হবে।</i>"
        )

    await safe_answer_or_edit(message_or_cb, prompt, reply_markup=chan_kb, is_callback=is_callback, parse_mode="HTML")

@router.callback_query(F.data == "retry_channel_step")
async def cb_retry_channel_step(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass
    await state.set_state(PollCreationState.channel)
    await show_channel_selection_prompt(callback.bot, callback.from_user.id, callback.message, is_callback=True)

@router.message(PollCreationState.candidates)
async def process_candidates(message: Message, state: FSMContext):
    if await check_command_breakout(message, state):
        return
    raw_text = (message.html_text or message.text or "").strip()
    user_lang = await get_user_language(message.from_user.id)
    
    if "\n" in raw_text:
        candidates = [c.strip() for c in raw_text.split("\n") if c.strip()]
    else:
        candidates = [c.strip() for c in raw_text.split(",") if c.strip()]
        
    if len(candidates) < 2:
        if user_lang == "en":
            err_cands = (
                "⚠️ <b>Auto-Help: Minimum 2 Candidates Required!</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "🔴 <b>Issue:</b> You provided less than 2 candidates.\n"
                "💡 <b>Why:</b> A contest or poll requires at least 2 candidates so members can cast a vote.\n\n"
                "🛠️ <b>How to Format:</b>\n"
                "Send candidate names separated by newlines (Enter) or commas:\n\n"
                "<b>Example:</b>\n"
                "<code>Candidate 1\nCandidate 2\nCandidate 3</code>\n\n"
                "💡 <i>Tip: You can send up to 29 candidates for Part 1! If you send more than 29, the bot will automatically split them into sequential parts.</i>"
            )
        else:
            err_cands = (
                "⚠️ <b>অটো-হেল্প: কমপক্ষে ২টি প্রার্থীর নাম দিন!</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "🔴 <b>সমস্যা:</b> আপনি পর্যাপ্ত প্রার্থীর নাম দেননি (কমপক্ষে ২টি নাম প্রয়োজন)।\n"
                "💡 <b>কীভাবে লিখবেন:</b>\n"
                "প্রতিটি প্রার্থীর নাম আলাদা লাইনে (Enter দিয়ে) অথবা কমা (,) দিয়ে লিখুন।\n\n"
                "<b>উদাহরণ:</b>\n"
                "<code>প্রার্থী ১\nপ্রার্থী ২\nপ্রার্থী ৩</code>\n\n"
                "💡 <i>টিপস: ১ম পর্বের জন্য সর্বোচ্চ ২৯ জন দেওয়া যাবে। ২৯ জনের বেশি দিলে স্বয়ংক্রিয়ভাবে পরবর্তী পর্বে (Part 2) ভাগ হয়ে যাবে।</i>"
            )
        await message.answer(err_cands, parse_mode="HTML")
        return

    if len(candidates) > 200:
        await message.answer(f"⚠️ Maximum 200 candidates allowed across parts (you provided {len(candidates)}):")
        return

    CHUNK_SIZE = 29
    chunks = [candidates[i:i + CHUNK_SIZE] for i in range(0, len(candidates), CHUNK_SIZE)]

    await state.update_data(candidates=candidates, candidate_chunks=chunks)
    await state.set_state(PollCreationState.channel)

    if len(chunks) > 1:
        if user_lang == "en":
            chunk_summary = "\n".join([f"   • Part {i+1}: {len(ch)} candidates" for i, ch in enumerate(chunks)])
            info_note = (
                f"💡 <b>Received {len(candidates)} candidates!</b>\n\n"
                f"Each poll comfortably fits up to 29 candidates. Your contest will be automatically published as <b>{len(chunks)} sequential parts</b>:\n"
                f"{chunk_summary}\n\n"
                f"All parts will be published consecutively in your channel under the same title with the same timer!"
            )
        else:
            chunk_summary = "\n".join([f"   • পর্ব {i+1}: {len(ch)} জন" for i, ch in enumerate(chunks)])
            info_note = (
                f"💡 <b>মোট {len(candidates)} জন প্রার্থীর নাম পাওয়া গেছে!</b>\n\n"
                f"প্রতিটি পোলে সর্বোচ্চ ২৯ জন সুন্দরভাবে সাজানো থাকে। আপনার এই কনটেস্টটি স্বয়ংক্রিয়ভাবে <b>{len(chunks)} টি পর্বে (Parts)</b> ভাগ হয়ে চ্যানেলে পরপর পোস্ট হবে:\n"
                f"{chunk_summary}\n\n"
                f"সবগুলো পর্ব একই শিরোনামে একই সময়সীমা অনুযায়ী চ্যানেলে একটার নিচে আরেকটা পাবলিশ হবে।"
            )
        await message.answer(info_note, parse_mode="HTML")

    data = await state.get_data()
    preselected_id = data.get("preselected_target_chat_id")
    if preselected_id:
        await validate_and_proceed_channel(message.bot, preselected_id, state, message, message.from_user.id, False)
        return
    await show_channel_selection_prompt(message.bot, message.from_user.id, message, is_callback=False)

@router.callback_query(F.data.startswith("sel_chan:"))
async def cb_select_channel(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass

    chat_id = int(callback.data.split(":")[1])
    data = await state.get_data()

    # If state was lost or expired (e.g. after bot restart or idle)
    if not data.get("candidates") and not data.get("title"):
        user_lang = await get_user_language(callback.from_user.id)
        bot_info = await callback.bot.get_me()
        is_admin = callback.from_user.id in ADMIN_IDS
        from bot.keyboards.inline import build_main_menu
        expired_msg = (
            "⚠️ <b>সেশনের সময় শেষ হয়েছে বা পোল পুনরায় শুরু করতে হবে!</b>\n\n"
            "অনুগ্রহ করে নিচের <b>'নতুন পোল তৈরি করুন'</b> বাটনে চাপ দিয়ে আবার শুরু করুন।"
            if user_lang == "bn" else
            "⚠️ <b>Session expired or poll creation needs to be restarted!</b>\n\n"
            "Please tap <b>'Create New Poll'</b> below to start fresh."
        )
        await callback.message.answer(
            expired_msg,
            reply_markup=build_main_menu(is_admin, bot_info.username, user_lang),
            parse_mode="HTML"
        )
        return

    await state.set_state(PollCreationState.channel)
    await validate_and_proceed_channel(callback.bot, chat_id, state, callback.message, callback.from_user.id, is_callback=True)

@router.message(PollCreationState.channel)
async def process_channel(message: Message, state: FSMContext):
    if await check_command_breakout(message, state):
        return

    bot = message.bot
    user_id = message.from_user.id
    user_lang = await get_user_language(user_id)

    target = None

    # Check if user forwarded a message from their channel
    if message.forward_from_chat:
        target = message.forward_from_chat.id
    elif message.text:
        raw = message.text.strip()
        # Check if user pasted an invite link like https://t.me/+... or t.me/joinchat/...
        if "t.me/+" in raw or "t.me/joinchat/" in raw:
            bot_info = await bot.get_me()
            clean_bot = bot_info.username.lstrip("@")
            add_channel_url = f"https://t.me/{clean_bot}?startchannel=true&admin=post_messages+edit_messages+delete_messages"

            selectable_channels = await get_user_selectable_channels(user_id)
            channel_buttons = []
            add_btn_text = "Add Bot to Channel (1-Click) ➔" if user_lang == "en" else "নতুন চ্যানেলে এডমিন করুন (১-ক্লিক) ➔"
            channel_buttons.append([make_custom_button(text=add_btn_text, url=add_channel_url, custom_emoji_id=ADD_CHANNEL_CUSTOM_EMOJI_ID)])

            for ch in selectable_channels[:8]:
                ch_type = "🔒 Private" if not ch.get("username") else f"@{ch['username']}"
                btn_text = f"📢 {ch['title'][:20]} ({ch_type})"
                channel_buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"sel_chan:{ch['chat_id']}")])
            channel_buttons.append([InlineKeyboardButton(text="❌ Cancel / বাতিল", callback_data="cancel_publish")])
            chan_kb = InlineKeyboardMarkup(inline_keyboard=channel_buttons)

            warn = (
                "⚠️ <b>প্রাইভেট চ্যানেলের ইনভাইট লিংক টেলিগ্রাম Bot API তে সরাসরি কাজ করে না।</b>\n\n"
                "👉 <b>সবচেয়ে সহজ সমাধান:</b> আপনার চ্যানেল থেকে যেকোনো একটি পোস্ট এখানে <b>Forward (ফরওয়ার্ড)</b> করে দিন! বট সাথে সাথে চিনে নেবে।\n"
                "👉 অথবা উপরের <b>'এডমিন করুন'</b> বাটন বা নিচের চ্যানেল বাটন থেকে বেছে নিন:"
                if user_lang == "bn" else
                "⚠️ <b>Private invite links cannot be resolved directly via Telegram Bot API.</b>\n\n"
                "👉 <b>Fastest Solution:</b> Simply <b>forward any message</b> from your channel here! The bot will instantly recognize it.\n"
                "👉 Or tap the <b>'Add Bot to Channel'</b> button above or select below:"
            )
            await message.answer(warn, reply_markup=chan_kb, parse_mode="HTML")
            return

        # Check if numeric ID (e.g. -1003963886285 or 1003963886285 or 3963886285)
        clean_num = raw.replace("-", "").replace(" ", "")
        if clean_num.isdigit():
            if raw.startswith("-100"):
                target = int(raw)
            elif raw.startswith("-"):
                target = int(raw)
            else:
                target = int(f"-100{clean_num}") if not clean_num.startswith("100") else int(f"-{clean_num}")
        else:
            target = raw

    if not target:
        bot_info = await bot.get_me()
        clean_bot = bot_info.username.lstrip("@")
        add_channel_url = f"https://t.me/{clean_bot}?startchannel=true&admin=post_messages+edit_messages+delete_messages"
        help_kb = InlineKeyboardMarkup(inline_keyboard=[
            [make_custom_button(text="চ্যানেলে যুক্ত করুন (১-ক্লিক) ➔" if user_lang == "bn" else "Add Bot to Channel (1-Click) ➔", url=add_channel_url, custom_emoji_id=ADD_CHANNEL_CUSTOM_EMOJI_ID)],
            [InlineKeyboardButton(text="❌ বাতিল / Cancel", callback_data="cancel_publish")]
        ])
        await message.answer(
            "⚠️ <b>অনুগ্রহ করে একটি সঠিক চ্যানেল দিন / Please provide a valid channel</b>\n\n"
            "👉 নিচের 'চ্যানেলে যুক্ত করুন' বাটনে চাপুন অথবা আপনার চ্যানেল থেকে যেকোনো মেসেজ Forward করুন:"
            if user_lang == "bn" else
            "⚠️ <b>Please provide a valid channel username or ID</b>\n\n"
            "👉 Tap 'Add Bot to Channel' below or forward any message from your channel:",
            reply_markup=help_kb,
            parse_mode="HTML"
        )
        return

    await validate_and_proceed_channel(bot, target, state, message, user_id, is_callback=False)

async def validate_and_proceed_channel(bot, target, state: FSMContext, msg_or_cb, user_id: int, is_callback: bool):
    user_lang = await get_user_language(user_id)
    bot_info = await bot.get_me()
    clean_bot = bot_info.username.lstrip("@")
    add_chan_url = f"https://t.me/{clean_bot}?startchannel=true&admin=post_messages+edit_messages+delete_messages"

    try:
        chat = await bot.get_chat(target)
    except Exception as e:
        if user_lang == "en":
            err_text = (
                "⚠️ <b>Auto-Help: Channel Not Found!</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "🔴 <b>Issue:</b> The bot cannot find the channel you specified.\n"
                "💡 <b>Common Reasons:</b>\n"
                "   • Typo in channel username or ID.\n"
                "   • Bot is not added to the channel yet.\n"
                "   • Private invite links (t.me/+) cannot be resolved directly.\n\n"
                "🛠️ <b>How to Solve (Choose one):</b>\n"
                "👉 <b>Fastest:</b> Tap <b>'Add Bot as Admin (1-Click)'</b> below to select your channel.\n"
                "👉 <b>For Private Channels:</b> Simply <b>forward any message</b> from your private channel here!\n"
                "👉 <b>Manual:</b> Send channel username (e.g. <code>@MyChannel</code>) or ID."
            )
        else:
            err_text = (
                "⚠️ <b>অটো-হেল্প: চ্যানেলটি খুঁজে পাওয়া যায়নি!</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "🔴 <b>সমস্যা:</b> বটটি আপনার দেওয়া চ্যানেল খুঁজে পাচ্ছে না।\n"
                "💡 <b>সাধারণ কারণসমূহ:</b>\n"
                "   • ইউজারনেম বা আইডি লিখতে ভুল হতে পারে।\n"
                "   • বটটিকে এখনও চ্যানেলে এডমিন করা হয়নি।\n"
                "   • টেলিগ্রাম Bot API তে প্রাইভেট ইনভাইট লিংক সরাসরি কাজ করে না।\n\n"
                "🛠️ <b>সহজ সমাধান (যেকোনো ১টি করুন):</b>\n"
                "👉 <b>সবচেয়ে সহজ:</b> নিচের <b>'এডমিন করুন (১-ক্লিক)'</b> বাটনে চাপ দিন—টেলিগ্রাম চ্যানেল সিলেক্ট করতে দেবে।\n"
                "👉 <b>প্রাইভেট চ্যানেলের জন্য:</b> আপনার চ্যানেল থেকে যেকোনো পোস্ট এখানে <b>Forward (ফরওয়ার্ড)</b> করুন!\n"
                "👉 <b>ম্যানুয়াল:</b> চ্যানেলের ইউজারনেম (যেমন: <code>@MyChannel</code>) বা আইডি লিখে পাঠান।"
            )
        err_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="📢 এডমিন করুন (১-ক্লিক বাটন) ➔" if user_lang == "bn" else "📢 Add Bot as Admin (1-Click) ➔",
                url=add_chan_url
            )],
            [
                InlineKeyboardButton(text="🔄 আবার চেষ্টা করুন / Retry" if user_lang == "bn" else "🔄 Try Again", callback_data="retry_channel_step"),
                InlineKeyboardButton(text="❌ বাতিল / Cancel" if user_lang == "bn" else "❌ Cancel", callback_data="cancel_publish")
            ]
        ])
        if is_callback:
            await msg_or_cb.edit_text(err_text, reply_markup=err_kb, parse_mode="HTML")
        else:
            await msg_or_cb.answer(err_text, reply_markup=err_kb, parse_mode="HTML")
        return

    if chat.type not in ["channel", "supergroup", "group"]:
        err_msg = (
            "⚠️ <b>Auto-Help: Invalid Chat Type!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🔴 <b>Issue:</b> The target is not a channel or supergroup (personal user or bot).\n"
            "🛠️ <b>How to Solve:</b> Please provide a valid Telegram Channel username or forward a message from your channel."
            if user_lang == "en" else
            "⚠️ <b>অটো-হেল্প: এটি চ্যানেল নয়!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🔴 <b>সমস্যা:</b> আপনি যে আইডি বা লিংক দিয়েছেন তা চ্যানেল নয় (ব্যক্তিগত প্রোফাইল বা বট)।\n"
            "🛠️ <b>সহজ সমাধান:</b> অনুগ্রহ করে একটি টেলিগ্রাম চ্যানেলের ইউজারনেম দিন অথবা চ্যানেল থেকে মেসেজ ফরওয়ার্ড করুন।"
        )
        type_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 এডমিন করুন (১-ক্লিক) ➔" if user_lang == "bn" else "📢 Add Bot as Admin ➔", url=add_chan_url)],
            [InlineKeyboardButton(text="🔄 অন্য চ্যানেল দিন / Retry" if user_lang == "bn" else "🔄 Try Again", callback_data="retry_channel_step")],
            [InlineKeyboardButton(text="❌ বাতিল / Cancel" if user_lang == "bn" else "❌ Cancel", callback_data="cancel_publish")]
        ])
        if is_callback:
            await msg_or_cb.edit_text(err_msg, reply_markup=type_kb, parse_mode="HTML")
        else:
            await msg_or_cb.answer(err_msg, reply_markup=type_kb, parse_mode="HTML")
        return

    try:
        bot_member = await bot.get_chat_member(chat.id, bot.id)
        if bot_member.status not in ["administrator", "creator"]:
            if user_lang == "en":
                not_admin = (
                    f"⚠️ <b>Auto-Help: Admin Rights Required!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🔴 <b>Issue:</b> The bot is not an Administrator in <b>{html.escape(chat.title or '')}</b>.\n"
                    f"💡 <b>Why:</b> Telegram requires bots to be Channel Admins in order to post interactive polls.\n\n"
                    f"🛠️ <b>How to Solve:</b>\n"
                    f"👉 Tap <b>'Add as Admin Now'</b> below to automatically grant permissions (keep 'Post Messages' ON),\n"
                    f"then tap <b>'I Added Admin (Recheck)'</b> to continue!"
                )
            else:
                not_admin = (
                    f"⚠️ <b>অটো-হেল্প: এডমিন পারমিশন প্রয়োজন!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🔴 <b>সমস্যা:</b> বটটি <b>{html.escape(chat.title or '')}</b> চ্যানেলে Administrator নেই।\n"
                    f"💡 <b>কেন হয়েছে:</b> টেলিগ্রামের নিয়ম অনুযায়ী চ্যানেলে ভোটিং পোল পাঠাতে হলে বটকে অবশ্যই এডমিন হতে হয়।\n\n"
                    f"🛠️ <b>কীভাবে সমাধান করবেন:</b>\n"
                    f"👉 নিচের <b>'এখনই এডমিন করুন'</b> বাটনে চাপ দিন (<b>Post Messages</b> অন রাখুন)।\n"
                    f"এডমিন করা হয়ে গেলে <b>'এডমিন করেছি, চেক করুন'</b> বাটনে চাপলেই বট সাথে সাথে পোল প্রসেস করবে!"
                )
            admin_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="📢 এখনই চ্যানেলে এডমিন করুন ➔" if user_lang == "bn" else "📢 Add as Admin Now ➔",
                    url=add_chan_url
                )],
                [
                    InlineKeyboardButton(
                        text="✅ এডমিন করেছি, চেক করুন" if user_lang == "bn" else "✅ I Added Admin (Recheck)",
                        callback_data=f"sel_chan:{chat.id}"
                    )
                ],
                [InlineKeyboardButton(text="❌ বাতিল / Cancel" if user_lang == "bn" else "❌ Cancel", callback_data="cancel_publish")]
            ])
            if is_callback:
                await msg_or_cb.edit_text(not_admin, reply_markup=admin_kb, parse_mode="HTML")
            else:
                await msg_or_cb.answer(not_admin, reply_markup=admin_kb, parse_mode="HTML")
            return

        if hasattr(bot_member, "can_post_messages") and bot_member.can_post_messages is False:
            if user_lang == "en":
                no_post = (
                    f"⚠️ <b>Auto-Help: 'Post Messages' Permission Missing!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🔴 <b>Issue:</b> The bot is an Admin in <b>{html.escape(chat.title or '')}</b>, but lacks permission to post messages.\n"
                    f"💡 <b>Why:</b> In Telegram channel settings, 'Post Messages' was left disabled.\n\n"
                    f"🛠️ <b>How to Solve:</b>\n"
                    f"1. Open channel <b>Settings ➔ Administrators ➔ {bot_info.first_name}</b>.\n"
                    f"2. Turn ON the <b>'Post Messages'</b> switch and tap Save.\n"
                    f"3. Tap <b>'Permission Enabled, Recheck'</b> below!"
                )
            else:
                no_post = (
                    f"⚠️ <b>অটো-হেল্প: 'পোস্ট করার অনুমতি' বন্ধ আছে!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🔴 <b>সমস্যা:</b> বটটি <b>{html.escape(chat.title or '')}</b> চ্যানেলে এডমিন আছে, কিন্তু মেসেজ পোস্ট করার অনুমতি নেই।\n"
                    f"💡 <b>কেন হয়েছে:</b> চ্যানেল এডমিন সেটিংসে 'Post Messages' পারমিশন অন করা হয়নি।\n\n"
                    f"🛠️ <b>কীভাবে সমাধান করবেন:</b>\n"
                    f"১. চ্যানেলের <b>Settings ➔ Administrators ➔ {bot_info.first_name}</b> এ যান।\n"
                    f"২. <b>'Post Messages'</b> অপশনটি চালু (Enable) করে Save করুন।\n"
                    f"৩. নিচের <b>'অনুমতি দিয়েছি, চেক করুন'</b> বাটনে চাপ দিন!"
                )
            post_kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ অনুমতি দিয়েছি, চেক করুন" if user_lang == "bn" else "✅ Permission Enabled (Recheck)",
                        callback_data=f"sel_chan:{chat.id}"
                    )
                ],
                [InlineKeyboardButton(text="❌ বাতিল / Cancel" if user_lang == "bn" else "❌ Cancel", callback_data="cancel_publish")]
            ])
            if is_callback:
                await msg_or_cb.edit_text(no_post, reply_markup=post_kb, parse_mode="HTML")
            else:
                await msg_or_cb.answer(no_post, reply_markup=post_kb, parse_mode="HTML")
            return
    except Exception as e:
        err_perm = (
            f"⚠️ <b>Auto-Help: Verification Error!</b>\n<code>{html.escape(str(e))}</code>"
            if user_lang == "en" else
            f"⚠️ <b>অটো-হেল্প: পারমিশন যাচাই করতে ত্রুটি হয়েছে!</b>\n<code>{html.escape(str(e))}</code>"
        )
        perm_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 আবার চেষ্টা করুন / Retry" if user_lang == "bn" else "🔄 Try Again", callback_data=f"sel_chan:{chat.id}")],
            [InlineKeyboardButton(text="❌ বাতিল / Cancel" if user_lang == "bn" else "❌ Cancel", callback_data="cancel_publish")]
        ])
        if is_callback:
            await msg_or_cb.edit_text(err_perm, reply_markup=perm_kb, parse_mode="HTML")
        else:
            await msg_or_cb.answer(err_perm, reply_markup=perm_kb, parse_mode="HTML")
        return

    # ── Strict User Authorization & Channel Isolation Check ──
    # CRITICAL: A user can ONLY publish polls in channels where they have
    # verified Administrator/Creator rights on Telegram!
    # Even Bot Admins cannot post to channels where they are not an administrator.
    is_authorized = False
    try:
        user_member = await bot.get_chat_member(chat.id, user_id)
        if user_member.status in ["administrator", "creator"]:
            is_authorized = True
            await record_user_channel_access(user_id, chat.id)
        else:
            is_authorized = False
            await remove_user_channel_permission(user_id, chat.id)
    except Exception:
        # Fallback to database check only if Telegram API call fails (e.g. rate limit or mock test)
        is_authorized = await is_user_authorized_for_channel_db(user_id, chat.id)

    if not is_authorized:
        chan_title = html.escape(chat.title or "Channel")
        if user_lang == "en":
            denied_msg = (
                f"⛔ <b>Access Denied: Channel Not Authorized!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🔴 <b>Issue:</b> You are not an Administrator or Owner of <b>{chan_title}</b>.\n"
                f"💡 <b>Security Policy:</b> For channel safety and privacy, users can ONLY publish polls in channels where they have Administrator rights. You cannot post to another user's channel!\n\n"
                f"🛠️ <b>How to Solve:</b>\n"
                f"👉 Use <b>'Add Bot to Channel (1-Click)'</b> below to add the bot to your own channel,\n"
                f"👉 Or select one of your own channels from the list."
            )
        else:
            denied_msg = (
                f"⛔ <b>অননুমোদিত চ্যানেল / Access Denied!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🔴 <b>সমস্যা:</b> আপনি <b>{chan_title}</b> চ্যানেলের অ্যাডমিন বা মালিক নন!\n"
                f"💡 <b>নিরাপত্তা সতর্কতা:</b> সুরক্ষার স্বার্থে একজন ব্যবহারকারী শুধুমাত্র নিজের অ্যাডমিন থাকা চ্যানেলেই পোল তৈরি করতে পারবেন। অন্যের চ্যানেলে পোল তৈরি করা বা পোস্ট দেওয়া সম্পূর্ণ নিষিদ্ধ!\n\n"
                f"🛠️ <b>কীভাবে সমাধান করবেন:</b>\n"
                f"👉 নিচের <b>'নতুন চ্যানেলে এডমিন করুন (১-ক্লিক)'</b> বাটনে চাপ দিয়ে আপনার নিজস্ব চ্যানেলে বটটি যুক্ত করুন,\n"
                f"👉 অথবা শুধুমাত্র নিজের চ্যানেল সিলেক্ট করুন।"
            )
        denied_kb = InlineKeyboardMarkup(inline_keyboard=[
            [make_custom_button(
                text="নতুন চ্যানেলে এডমিন করুন (১-ক্লিক) ➔" if user_lang == "bn" else "Add Bot to Channel (1-Click) ➔",
                url=add_chan_url,
                custom_emoji_id=ADD_CHANNEL_CUSTOM_EMOJI_ID
            )],
            [
                InlineKeyboardButton(text="🔄 অন্য চ্যানেল দিন / Retry" if user_lang == "bn" else "🔄 Try Another Channel", callback_data="retry_channel_step"),
                InlineKeyboardButton(text="❌ বাতিল / Cancel" if user_lang == "bn" else "❌ Cancel", callback_data="cancel_publish")
            ]
        ])
        if is_callback:
            await msg_or_cb.edit_text(denied_msg, reply_markup=denied_kb, parse_mode="HTML")
        else:
            await msg_or_cb.answer(denied_msg, reply_markup=denied_kb, parse_mode="HTML")
        return

    # Authorized! Record access for quick future usage
    await record_user_channel_access(user_id, chat.id)

    # Success! Save channel data
    await state.update_data(
        target_chat_id=chat.id,
        target_chat_title=chat.title or "Channel",
        target_chat_username=chat.username
    )
    await state.set_state(PollCreationState.duration)

    dur_prompt = (
        f'<tg-emoji emoji-id="{STEP4_DURATION_CUSTOM_EMOJI_ID}">⏱️</tg-emoji> <b>Step 4/4: Poll Duration / লাইভ টাইমার নির্ধারণ</b>\n\n'
        f"📢 Selected Channel: <b>{html.escape(chat.title or '')}</b>\n\n"
        "Choose how long the poll will remain active. When the timer expires, the bot will <b>automatically end the contest and announce the winner!</b>\n\n"
        "<i>পোলটি কতক্ষণ চলবে তা নির্বাচন করুন। সময় শেষ হলে বট স্বয়ংক্রিয়ভাবে বিজয়ী ঘোষণা করে দেবে:</i>\n\n"
        "💡 <i>Tip: You can tap a button below, or type custom duration (e.g. <code>45m</code>, <code>2h</code>, <code>3d</code>). If you prefer to end manually anytime, choose 'No Timer':</i>"
        if user_lang == "en" else
        f'<tg-emoji emoji-id="{STEP4_DURATION_CUSTOM_EMOJI_ID}">⏱️</tg-emoji> <b>Step 4/4: Poll Duration / লাইভ টাইমার নির্ধারণ</b>\n\n'
        f"📢 নির্বাচিত চ্যানেল: <b>{html.escape(chat.title or '')}</b>\n\n"
        "পোলটি কতক্ষণ চলবে তা নির্ধারণ করুন। নির্ধারিত সময় শেষ হলে বট <b>স্বয়ংক্রিয়ভাবে পোল ক্লোজ করে চ্যানেলে বিজয়ী ঘোষণা করবে!</b>\n\n"
        "<i>নিচের যেকোনো অপশন বেছে নিন, অথবা লিখে পাঠান (যেমন: <code>45m</code>, <code>2h</code>, <code>3d</code>)। নিজে যখন ইচ্ছা তখন ম্যানুয়ালি বন্ধ করতে চাইলে 'কোনো সময়সীমা নেই' বাটনে চাপুন:</i>"
    )

    await safe_answer_or_edit(msg_or_cb, dur_prompt, reply_markup=build_duration_keyboard(user_lang), is_callback=is_callback, parse_mode="HTML")

def parse_custom_duration(text: str) -> Optional[int]:
    raw = text.strip().lower()
    if raw in ["0", "no", "none", "manual", "off"]:
        return 0
    match = re.match(r"^(\d+)\s*([mhd])$", raw)
    if not match:
        if raw.isdigit():
            return int(raw) * 60
        return None
    val = int(match.group(1))
    unit = match.group(2)
    if unit == "m":
        return val * 60
    elif unit == "h":
        return val * 3600
    elif unit == "d":
        return val * 86400
    return None

def format_duration_label(seconds: int, lang: str = "bn") -> str:
    if seconds <= 0:
        return "♾️ No Timer (Manual End)" if lang == "en" else "♾️ কোনো সময়সীমা নেই (ম্যানুয়ালি সমাপ্তি)"
    if seconds < 3600:
        mins = seconds // 60
        return f"⚡ {mins} Minutes" if lang == "en" else f"⚡ {mins} মিনিট"
    elif seconds < 86400:
        hrs = seconds // 3600
        return f"🕐 {hrs} Hours" if lang == "en" else f"🕐 {hrs} ঘণ্টা"
    else:
        days = seconds // 86400
        return f"🗓️ {days} Days" if lang == "en" else f"🗓️ {days} দিন"

@router.callback_query(F.data.startswith("dur:"))
async def cb_select_duration(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass
    seconds = int(callback.data.split(":")[1])
    data = await state.get_data()
    if not data.get("title") or not data.get("target_chat_id"):
        user_lang = await get_user_language(callback.from_user.id)
        bot_info = await callback.bot.get_me()
        is_admin = callback.from_user.id in ADMIN_IDS
        from bot.keyboards.inline import build_main_menu
        await callback.message.answer(
            "⚠️ <b>Session expired!</b> Please start fresh with /newpoll"
            if user_lang == "en" else
            "⚠️ <b>সেশনের সময় শেষ হয়েছে!</b> অনুগ্রহ করে /newpoll দিয়ে আবার শুরু করুন।",
            reply_markup=build_main_menu(is_admin, bot_info.username, user_lang),
            parse_mode="HTML"
        )
        await state.clear()
        return
    await apply_duration(callback.from_user.id, seconds, state, callback.message, is_callback=True)

@router.message(PollCreationState.duration)
async def process_text_duration(message: Message, state: FSMContext):
    if await check_command_breakout(message, state):
        return
    parsed_sec = parse_custom_duration(message.text)
    if parsed_sec is None:
        user_lang = await get_user_language(message.from_user.id)
        if user_lang == "en":
            err_dur = (
                "⚠️ <b>Auto-Help: Unrecognized Duration Format!</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "🔴 <b>Issue:</b> The duration text you entered could not be understood.\n"
                "💡 <b>Why:</b> Timers require specifying units like minutes (m), hours (h), or days (d).\n\n"
                "🛠️ <b>How to Solve (Choose either):</b>\n"
                "👉 <b>Option 1:</b> Simply tap one of the preset duration buttons below.\n"
                "👉 <b>Option 2:</b> Type your duration with a unit:\n"
                "   • <code>45m</code> ➔ 45 minutes\n"
                "   • <code>2h</code> ➔ 2 hours\n"
                "   • <code>3d</code> ➔ 3 days\n"
                "   • <code>0</code> or <code>manual</code> ➔ No timer (End manually anytime)\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "👉 <i>Please tap a button below or type your desired time:</i>"
            )
        else:
            err_dur = (
                "⚠️ <b>অটো-হেল্প: সময়সীমার ফরম্যাট বুঝতে পারিনি!</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "🔴 <b>সমস্যা:</b> আপনি যে সময়সীমা লিখেছেন তা সঠিক ফরম্যাটে ছিল না।\n"
                "💡 <b>কেন হয়েছে:</b> টাইমার সেট করতে মিনিট (m), ঘণ্টা (h) বা দিন (d) উল্লেখ করতে হয়।\n\n"
                "🛠️ <b>কীভাবে সমাধান করবেন (যেকোনো একটি বেছে নিন):</b>\n"
                "👉 <b>পদ্ধতি ১:</b> নিচের বাটনগুলোর যেকোনো একটিতে সরাসরি চাপ দিন।\n"
                "👉 <b>পদ্ধতি ২:</b> লিখে পাঠান:\n"
                "   • <code>45m</code> ➔ ৪৫ মিনিট\n"
                "   • <code>2h</code> ➔ ২ ঘণ্টা\n"
                "   • <code>3d</code> ➔ ৩ দিন\n"
                "   • <code>0</code> ➔ কোনো সময়সীমা নেই (যখন ইচ্ছা নিজে বন্ধ করবেন)\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "👉 <i>নিচের বাটনে চাপুন অথবা সময় লিখে পাঠান:</i>"
            )
        await message.answer(
            err_dur,
            reply_markup=build_duration_keyboard(user_lang),
            parse_mode="HTML"
        )
        return
    await apply_duration(message.from_user.id, parsed_sec, state, message, is_callback=False)

async def apply_duration(user_id: int, seconds: int, state: FSMContext, msg_or_cb, is_callback: bool):
    creator_lang = await get_user_language(user_id)
    now = datetime.now()
    created_at_str = now.strftime("%Y-%m-%d %H:%M:%S")
    ends_at_str = None
    if seconds > 0:
        ends_dt = now + timedelta(seconds=seconds)
        ends_at_str = ends_dt.strftime("%Y-%m-%d %H:%M:%S")

    duration_label = format_duration_label(seconds, creator_lang)
    await state.update_data(
        duration_seconds=seconds,
        created_at=created_at_str,
        ends_at=ends_at_str,
        duration_label=duration_label
    )
    await state.set_state(PollCreationState.winner_count)

    if creator_lang == "en":
        prompt_w = (
            "🏆 <b>Step 5/5: Number of Winners / বিজয়ী সংখ্যা নির্ধারণ</b>\n\n"
            "Choose how many top-voted candidates will be declared winners when this contest ends:\n\n"
            "💡 <i>Example: If you select 'Top 2 Winners', the candidates with 1st and 2nd highest votes will both be celebrated as winners in your channel!</i>"
        )
    elif creator_lang == "hi":
        prompt_w = (
            "🏆 <b>चरण ५/५: विजेताओं की संख्या चुनें</b>\n\n"
            "प्रतियोगिता समाप्त होने पर कितने शीर्ष उम्मीदवारों को विजेता घोषित किया जाएगा:\n\n"
            "💡 <i>उदाहरण: यदि आप 'शीर्ष 2 विजेता' चुनते हैं, तो बॉट पहले और दूसरे स्थान वाले दोनों उम्मीदवारों को विजेता घोषित करेगा!</i>"
        )
    else:
        prompt_w = (
            "🏆 <b>ধাপ ৫/৫: কতজন বিজয়ী নির্বাচন করবেন?</b>\n\n"
            "পোল বা কনটেস্ট শেষ হলে সর্বোচ্চ ভোট পাওয়া কতজনকে বিজয়ী ঘোষণা করতে চান তা নির্বাচন করুন:\n\n"
            "💡 <i>উদাহরণ: আপনি যদি 'শীর্ষ ২ জন' বেছে নেন, তবে ১ম ও ২য় সর্বোচ্চ ভোটপ্রাপ্ত উভয় প্রার্থীকেই চ্যানেলে বিজয়ী ঘোষণা করা হবে!</i>"
        )

    kb = build_winner_count_keyboard(creator_lang)
    if is_callback:
        await msg_or_cb.edit_text(prompt_w, reply_markup=kb, parse_mode="HTML")
    else:
        await msg_or_cb.answer(prompt_w, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("win_cnt:"))
async def cb_select_winner_count(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass
    action = callback.data.split(":")[1]
    user_lang = await get_user_language(callback.from_user.id)
    if action == "custom":
        msg = (
            "🔢 <b>Type Winner Count / বিজয়ী সংখ্যা লিখে পাঠান:</b>\n\n"
            "Please send the number of winners (e.g. <code>2</code>, <code>3</code>, <code>5</code>):\n\n"
            "Cancel: /cancel"
            if user_lang == "en" else
            "🔢 <b>বিজয়ী সংখ্যা লিখে পাঠান:</b>\n\n"
            "কতজনকে বিজয়ী করতে চান সেই সংখ্যাটি লিখে পাঠান (যেমন: <code>২</code>, <code>৩</code>, <code>৫</code>):\n\n"
            "বাতিল করতে: /cancel"
        )
        await callback.message.edit_text(msg, parse_mode="HTML")
        return

    count = int(action)
    await state.update_data(winner_count=count)
    await prompt_poll_language_step(callback.from_user.id, state, callback.message, is_callback=True)

@router.message(PollCreationState.winner_count)
async def process_text_winner_count(message: Message, state: FSMContext):
    if await check_command_breakout(message, state):
        return
    text = message.text.strip()
    if not text.isdigit() or int(text) < 1:
        user_lang = await get_user_language(message.from_user.id)
        err = (
            "⚠️ Please enter a valid positive number of winners (e.g. <code>1</code>, <code>2</code>, <code>3</code>):"
            if user_lang == "en" else
            "⚠️ অনুগ্রহ করে একটি সঠিক ইতিবাচক সংখ্যা লিখে পাঠান (যেমন: <code>১</code>, <code>২</code>, <code>৩</code>):"
        )
        await message.answer(err, reply_markup=build_winner_count_keyboard(user_lang), parse_mode="HTML")
        return

    count = int(text)
    await state.update_data(winner_count=count)
    await prompt_poll_language_step(message.from_user.id, state, message, is_callback=False)

async def prompt_poll_language_step(user_id: int, state: FSMContext, msg_or_cb, is_callback: bool):
    await state.set_state(PollCreationState.poll_language)
    creator_lang = await get_user_language(user_id)
    if creator_lang == "en":
        txt = (
            "🌐 <b>Step 6/6: Choose Channel Poll Language / পোলের ভাষা নির্ধারণ</b>\n\n"
            "Select which language this poll will use inside your Telegram Channel:\n\n"
            "💡 <i>This sets the poll card text, voting notice, CTA button, and winner announcement to your chosen language!</i>"
        )
    elif creator_lang == "hi":
        txt = (
            "🌐 <b>चरण ६/६: चैनल के लिए पोल की भाषा चुनें</b>\n\n"
            "चुनें कि आपके टेलीग्राम चैनल में यह पोल किस भाषा में पोस्ट होगा:\n\n"
            "💡 <i>यह पोल कार्ड, वोटिंग नोटिस और विजेता घोषणा की भाषा निर्धारित करेगा!</i>"
        )
    else:
        txt = (
            "🌐 <b>ধাপ ৬/৬: চ্যানেলে পোলের ভাষা নির্বাচন করুন</b>\n\n"
            "আপনার টেলিগ্রাম চ্যানেলে পোলটি কোন ভাষায় পোস্ট করতে চান তা নির্বাচন করুন:\n\n"
            "💡 <i>চ্যানেলের সদস্যরা পোলের কার্ড, নিয়মাবলী, বাটন এবং বিজয়ী ঘোষণার মেসেজ আপনার পছন্দ করা এই ভাষায় দেখতে পাবে!</i>"
        )
    kb = build_poll_language_keyboard(creator_lang)
    if is_callback:
        await msg_or_cb.edit_text(txt, reply_markup=kb, parse_mode="HTML")
    else:
        await msg_or_cb.answer(txt, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("poll_lang:"))
async def cb_select_poll_language(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass
    target_lang = callback.data.split(":")[1]
    await state.update_data(poll_language=target_lang)
    await prompt_giveaway_contact_step(callback.from_user.id, state, callback.message, is_callback=True, user=callback.from_user)

async def prompt_giveaway_contact_step(user_id: int, state: FSMContext, msg_or_cb, is_callback: bool, user=None):
    await state.set_state(PollCreationState.contact_id)
    creator_lang = await get_user_language(user_id)
    from bot.database.db import get_user_default_contact
    default_c = await get_user_default_contact(user_id)

    u_name = (user.username if user and user.username else "") or default_c
    buttons = []
    if u_name:
        clean_u = u_name.lstrip("@")
        suggested_contact = clean_u
        disp_contact = f"@{clean_u}"
        btn_self = f"✅ Use @{clean_u}" if creator_lang == "en" else f"✅ ব্যবহার করুন: @{clean_u}"
        buttons.append([InlineKeyboardButton(text=btn_self, callback_data=f"contact_self:{clean_u}")])
    else:
        suggested_contact = f"id_{user_id}"
        disp_contact = f"ID: {user_id}"
        btn_self = f"✅ Use ID: {user_id}" if creator_lang == "en" else f"✅ ব্যবহার করুন (ID: {user_id})"
        buttons.append([InlineKeyboardButton(text=btn_self, callback_data=f"contact_self:id_{user_id}")])

    # Pre-populate state with detected contact so user doesn't have to struggle typing
    await state.update_data(contact_username=suggested_contact)

    skip_text = "⏩ Skip (No Contact)" if creator_lang == "en" else "⏩ স্কিপ করুন (কন্ট্যাক্ট ছাড়া)"
    buttons.append([InlineKeyboardButton(text=skip_text, callback_data="contact_skip")])
    contact_kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    if creator_lang == "en":
        txt = (
            "<b>Step 7/7: Giveaway Host Contact ID</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Auto-detected Host: <b>{disp_contact}</b>\n\n"
            "Contest winners will contact this ID to claim their giveaway prize.\n\n"
            f"• Tap <b>✅ Use {disp_contact}</b> to confirm instantly.\n"
            "• Or send a different Telegram username / ID in chat.\n"
            "• Or tap 'Skip' if no contact is required."
        )
    elif creator_lang == "hi":
        txt = (
            "<b>चरण ७/७: गिवअवे होस्ट संपर्क आईडी</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"पहचाना गया होस्ट: <b>{disp_contact}</b>\n\n"
            "प्रतियोगिता समाप्त होने पर विजेता पुरस्कार के लिए इस आईडी पर संपर्क करेंगे।\n\n"
            f"• <b>✅ {disp_contact} का उपयोग करें</b> पर तुरंत टैप करें।\n"
            "• या चैट में कोई अन्य यूजरनेम / आईडी भेजें।\n"
            "• या 'स्किप' चुनें।"
        )
    else:
        txt = (
            "<b>ধাপ ৭/৭: গিভওয়ে হোস্টের যোগাযোগ আইডি</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"শনাক্তকৃত হোস্ট: <b>{disp_contact}</b>\n\n"
            "পোল শেষে বিজয়ীগণ পুরস্কার ক্লেইম করতে এই আইডিতে যোগাযোগ করবে।\n\n"
            f"• সরাসরি <b>✅ ব্যবহার করুন: {disp_contact}</b> বাটনে চাপুন (টাইপ করার কষ্ট ছাড়াই)।\n"
            "• অন্য কারো ইউজারনেম দিতে চাইলে চ্যাটে লিখে পাঠান (যেমন: <code>@username</code>)।\n"
            "• কোনো যোগাযোগ আইডি না রাখতে চাইলে 'স্কিপ' করুন।"
        )

    if is_callback:
        await msg_or_cb.edit_text(txt, reply_markup=contact_kb, parse_mode="HTML")
    else:
        await msg_or_cb.answer(txt, reply_markup=contact_kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("contact_self:"))
async def cb_contact_self(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass
    contact = callback.data.split(":", 1)[1]
    await state.update_data(contact_username=contact)
    from bot.database.db import set_user_default_contact
    await set_user_default_contact(callback.from_user.id, contact)
    await show_poll_preview(callback.from_user.id, state, callback.message, is_callback=True)

@router.callback_query(F.data == "contact_skip")
async def cb_contact_skip(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass
    await state.update_data(contact_username="")
    await show_poll_preview(callback.from_user.id, state, callback.message, is_callback=True)

@router.message(PollCreationState.contact_id)
async def process_text_contact(message: Message, state: FSMContext):
    if await check_command_breakout(message, state):
        return
    raw = message.text.strip()
    clean = raw.replace("https://t.me/", "").replace("t.me/", "").lstrip("@").strip()
    if clean.lower() in ["skip", "স্কিপ", "none", "no"]:
        clean = ""
    await state.update_data(contact_username=clean)
    if clean:
        from bot.database.db import set_user_default_contact
        await set_user_default_contact(message.from_user.id, clean)
    await show_poll_preview(message.from_user.id, state, message, is_callback=False)

async def show_poll_preview(user_id: int, state: FSMContext, msg_or_cb, is_callback: bool):
    await state.set_state(PollCreationState.confirm)
    creator_lang = await get_user_language(user_id)
    data = await state.get_data()
    title = data["title"]
    candidates = data["candidates"]
    chunks = data.get("candidate_chunks") or [candidates]
    target_chat_title = data["target_chat_title"]
    target_chat_id = data["target_chat_id"]
    created_at_str = data.get("created_at")
    ends_at_str = data.get("ends_at")
    winner_count = data.get("winner_count", 1)
    poll_lang = data.get("poll_language") or creator_lang

    lang_names = {
        "bn": "🇧🇩 বাংলা (Bangla)",
        "en": "🇬🇧 English",
        "hi": "🇮🇳 हिन्दी (Hindi)",
        "ar": "🇸🇦 العربية (Arabic)",
        "ru": "🇷🇺 Русский (Russian)"
    }
    lang_disp = lang_names.get(poll_lang, poll_lang.upper())

    start_display = format_datetime_readable(created_at_str)
    end_display = format_datetime_readable(ends_at_str) if ends_at_str else ("ম্যানুয়াল সমাপ্তি" if creator_lang == "bn" else "Manual Closure")

    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚀 Publish to Channel / পাবলিশ করুন", callback_data="confirm_publish"),
            InlineKeyboardButton(text="❌ Cancel / বাতিল", callback_data="cancel_publish")
        ]
    ])

    if len(chunks) > 1:
        cands_disp_en = f"{len(candidates)} candidates ({len(chunks)} Parts)\n" + "\n".join([f"   • Part {i+1}: {len(ch)} options" for i, ch in enumerate(chunks)])
        cands_disp_bn = f"{len(candidates)} জন ({len(chunks)} টি পর্ব)\n" + "\n".join([f"   • পর্ব {i+1}: {len(ch)} জন" for i, ch in enumerate(chunks)])
    else:
        cands_disp_en = f"{len(candidates)} candidates"
        cands_disp_bn = f"{len(candidates)} জন"

    win_label = f"Top {winner_count} Winners" if creator_lang == "en" else f"শীর্ষ {winner_count} জন বিজয়ী"

    contact_username = data.get("contact_username", "")
    if contact_username:
        if contact_username.startswith("id_") or contact_username.isdigit():
            c_num = contact_username.replace("id_", "")
            contact_disp_en = f"ID: {c_num}"
            contact_disp_bn = f"ID: {c_num}"
        else:
            clean_c = contact_username.lstrip("@")
            contact_disp_en = f"@{clean_c}"
            contact_disp_bn = f"@{clean_c}"
    else:
        contact_disp_en = "Not Set"
        contact_disp_bn = "সেট করা নেই"

    if creator_lang == "en":
        preview_text = (
            f"📋 <b>Poll Preview:</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📢 <b>Channel:</b> {html.escape(target_chat_title)} (<code>{target_chat_id}</code>)\n"
            f"📌 <b>Title:</b> {title}\n"
            f"🌐 <b>Channel Language:</b> {lang_disp}\n"
            f"👥 <b>Candidates:</b> {cands_disp_en}\n"
            f"🏆 <b>Winners:</b> {win_label}\n"
            f"📩 <b>Giveaway Host:</b> <code>{contact_disp_en}</code>\n"
            f"⏱️ <b>Schedule:</b>\n"
            f"   🟢 <b>Start:</b> <code>{start_display}</code>\n"
            f"   🔴 <b>End:</b> <code>{end_display}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            "Tap below to publish to your channel:\n"
            "<i>সব ঠিক থাকলে নিচের বাটনে চাপুন:</i>"
        )
    else:
        preview_text = (
            f"📋 <b>পোলের প্রিভিউ:</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📢 <b>চ্যানেল:</b> {html.escape(target_chat_title)} (<code>{target_chat_id}</code>)\n"
            f"📌 <b>শিরোনাম:</b> {title}\n"
            f"🌐 <b>পোলের ভাষা:</b> {lang_disp}\n"
            f"👥 <b>প্রার্থী সংখ্যা:</b> {cands_disp_bn}\n"
            f"🏆 <b>বিজয়ী নির্বাচন:</b> {win_label}\n"
            f"📩 <b>হোস্ট কন্ট্যাক্ট:</b> <code>{contact_disp_bn}</code>\n"
            f"⏱️ <b>সময়সূচি:</b>\n"
            f"   🟢 <b>শুরু:</b> <code>{start_display}</code>\n"
            f"   🔴 <b>শেষ:</b> <code>{end_display}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            "পোস্ট করতে নিচের বাটনে চাপুন:"
        )

    if is_callback:
        await safe_edit_message(msg_or_cb, preview_text, reply_markup=confirm_kb, parse_mode="HTML")
    else:
        await safe_send_message(msg_or_cb.bot, msg_or_cb.chat.id, preview_text, reply_markup=confirm_kb, parse_mode="HTML")


@router.callback_query(F.data == "confirm_publish")
async def publish_poll(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass
    data = await state.get_data()
    if not data.get("title") or not data.get("candidates") or not data.get("target_chat_id"):
        user_lang = await get_user_language(callback.from_user.id)
        bot_info = await callback.bot.get_me()
        is_admin = callback.from_user.id in ADMIN_IDS
        from bot.keyboards.inline import build_main_menu
        await callback.message.answer(
            "⚠️ <b>Session expired!</b> Please start fresh with /newpoll"
            if user_lang == "en" else
            "⚠️ <b>সেশনের সময় শেষ হয়েছে!</b> অনুগ্রহ করে /newpoll দিয়ে আবার শুরু করুন।",
            reply_markup=build_main_menu(is_admin, bot_info.username, user_lang),
            parse_mode="HTML"
        )
        await state.clear()
        return

    if data.get("_is_publishing"):
        await callback.answer(
            "⏳ Already publishing... Please wait! / ইতোমধ্যে পোস্ট করা হচ্ছে, দয়া করে অপেক্ষা করুন!",
            show_alert=True
        )
        return

    # Immediately lock and remove buttons to prevent double-clicks
    await state.update_data(_is_publishing=True)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    try:
        await callback.answer("⏳ Publishing to channel... / চ্যানেলে পোস্ট হচ্ছে...")
    except Exception:
        pass

    creator_id = callback.from_user.id
    target_chat_id = data["target_chat_id"]
    target_chat_title = data["target_chat_title"]
    target_chat_username = data.get("target_chat_username")
    title = data["title"]
    candidates = data["candidates"]
    chunks = data.get("candidate_chunks") or [candidates]
    created_at = data.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ends_at = data.get("ends_at")
    bot = callback.bot
    bot_info = await bot.get_me()
    creator_lang = await get_user_language(creator_id)

    # Final security check before publishing: ensure user is authorized
    is_authorized = False
    try:
        user_member = await bot.get_chat_member(target_chat_id, creator_id)
        if user_member.status in ["administrator", "creator"]:
            is_authorized = True
            await record_user_channel_access(creator_id, target_chat_id)
        else:
            is_authorized = False
            await remove_user_channel_permission(creator_id, target_chat_id)
    except Exception:
        is_authorized = await is_user_authorized_for_channel_db(creator_id, target_chat_id)

    if not is_authorized:
        await state.update_data(_is_publishing=False)
        retry_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancel / বাতিল", callback_data="cancel_publish")]
        ])
        try:
            await callback.message.edit_reply_markup(reply_markup=retry_kb)
        except Exception:
            pass
        await callback.answer(
            "⛔ Access Denied: You are not an administrator of this channel!" if creator_lang == "en" else "⛔ আপনি এই চ্যানেলের এডমিন নন! অন্য চ্যানেলে পোল দেওয়া নিষিদ্ধ।",
            show_alert=True
        )
        return

    # Save channel for network tracking
    await save_channel(
        chat_id=target_chat_id,
        title=target_chat_title,
        username=target_chat_username,
        added_by=creator_id
    )
    await record_user_channel_access(creator_id, target_chat_id)

    try:
        base_title = get_base_title(title)
        num_parts = len(chunks)

        winner_count = int(data.get("winner_count") or 1)
        icon_style = await get_user_icon_style(creator_id)

        poll_lang = data.get("poll_language") or creator_lang

        if num_parts == 1:
            poll_id = await create_poll(
                creator_id=creator_id,
                target_chat_id=target_chat_id,
                target_chat_title=target_chat_title,
                target_chat_username=target_chat_username,
                title=title,
                candidates=candidates,
                ends_at=ends_at,
                created_at=created_at,
                part_number=1,
                winner_count=winner_count,
                icon_style=icon_style,
                language=poll_lang,
                contact_username=data.get("contact_username")
            )
            channel_msg_text = await render_poll_card(
                title,
                bot_info.username,
                lang=poll_lang,
                ends_at=ends_at,
                created_at=created_at,
                winner_count=winner_count,
                creator_id=creator_id
            )
            cta_text, cta_url = await render_poll_cta(bot_info.username, lang=poll_lang, creator_id=creator_id)
            real_candidates = await get_candidates(poll_id)
            poll_kb = build_poll_keyboard(poll_id, real_candidates, bot_info.username, cta_text=cta_text, cta_url=cta_url, icon_style=icon_style)

            sent_msg = await bot.send_message(
                chat_id=target_chat_id,
                text=channel_msg_text,
                reply_markup=poll_kb,
                parse_mode="HTML"
            )
            await set_poll_message_id(poll_id, sent_msg.message_id)

            if target_chat_username:
                channel_link = f"https://t.me/{target_chat_username}/{sent_msg.message_id}"
            elif str(target_chat_id).startswith("-100"):
                internal_id = str(abs(target_chat_id))[3:]
                channel_link = f"https://t.me/c/{internal_id}/{sent_msg.message_id}"
            else:
                channel_link = None

            start_display = format_datetime_readable(created_at)
            end_display = format_datetime_readable(ends_at) if ends_at else ("ম্যানুয়াল সমাপ্তি" if creator_lang == "bn" else "Manual Closure")

            if creator_lang == "en":
                congrats_text = (
                    f"🎉 <b>Poll Published Successfully!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🆔 <b>Poll ID:</b> <code>#{poll_id}</code>\n"
                    f"📢 <b>Channel:</b> {html.escape(target_chat_title)}\n"
                    f"📌 <b>Title:</b> {title}\n"
                    f"👥 <b>Candidates:</b> {len(candidates)} options\n"
                    f"⏱️ <b>Schedule:</b>\n"
                    f"   🟢 <b>Start:</b> <code>{start_display}</code>\n"
                    f"   🔴 <b>End:</b> <code>{end_display}</code>\n"
                    f"━━━━━━━━━━━━━━━━━━━━"
                )
            else:
                congrats_text = (
                    f"🎉 <b>পোল সফলভাবে চ্যানেলে পোস্ট হয়েছে!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🆔 <b>পোল আইডি:</b> <code>#{poll_id}</code>\n"
                    f"📢 <b>চ্যানেল:</b> {html.escape(target_chat_title)}\n"
                    f"📌 <b>শিরোনাম:</b> {title}\n"
                    f"👥 <b>প্রার্থী সংখ্যা:</b> {len(candidates)} জন\n"
                    f"⏱️ <b>সময়সূচি:</b>\n"
                    f"   🟢 <b>শুরু:</b> <code>{start_display}</code>\n"
                    f"   🔴 <b>শেষ:</b> <code>{end_display}</code>\n"
                    f"━━━━━━━━━━━━━━━━━━━━"
                )

            if ends_at:
                congrats_text += "\n\n⏱️ <i>নির্ধারিত শেষ সময়ে বট স্বয়ংক্রিয়ভাবে চ্যানেলে বিজয়ী ঘোষণা করবে!</i>"
            else:
                congrats_text += "\n\n💡 <i>যেকোনো সময় /mypolls থেকে পোলটি সমাপ্ত করে বিজয়ী ঘোষণা করতে পারবেন।</i>"

            action_buttons = [
                [InlineKeyboardButton(
                    text="➕ Add Part 2 / পরবর্তী পর্ব যোগ করুন (আরো নাম)" if creator_lang == "bn" else "➕ Add Part 2 (More Candidates)",
                    callback_data=f"add_part:{poll_id}"
                )]
            ]
            if channel_link:
                action_buttons.append([InlineKeyboardButton(text="🔗 View Poll in Channel / চ্যানেলে দেখুন", url=channel_link)])
            action_buttons.append([make_custom_button(text="🔙 Main Menu / মূল মেনু" if creator_lang == "bn" else "🔙 Main Menu", callback_data="menu_back_main", custom_emoji_id=START_MENU_CUSTOM_EMOJI_ID)])

            await callback.message.edit_text(
                congrats_text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=action_buttons),
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        else:
            base_title = get_base_title(title)
            part1_suffix = "[Part 1]" if poll_lang == "en" else "[পর্ব ১]"
            part1_title = f"{base_title} {part1_suffix}"

            part1_id = await create_poll(
                creator_id=creator_id,
                target_chat_id=target_chat_id,
                target_chat_title=target_chat_title,
                target_chat_username=target_chat_username,
                title=part1_title,
                candidates=chunks[0],
                ends_at=ends_at,
                created_at=created_at,
                part_number=1,
                winner_count=winner_count,
                icon_style=icon_style,
                language=poll_lang,
                contact_username=data.get("contact_username")
            )
            card1_text = await render_poll_card(
                part1_title,
                bot_info.username,
                lang=poll_lang,
                ends_at=ends_at,
                created_at=created_at,
                winner_count=winner_count,
                creator_id=creator_id
            )
            cta_text, cta_url = await render_poll_cta(bot_info.username, lang=poll_lang, creator_id=creator_id)
            cands1 = await get_candidates(part1_id)
            kb1 = build_poll_keyboard(part1_id, cands1, bot_info.username, cta_text=cta_text, cta_url=cta_url, icon_style=icon_style)

            msg1 = await bot.send_message(
                chat_id=target_chat_id,
                text=card1_text,
                reply_markup=kb1,
                parse_mode="HTML"
            )
            await set_poll_message_id(part1_id, msg1.message_id)

            if target_chat_username:
                link1 = f"https://t.me/{target_chat_username}/{msg1.message_id}"
            elif str(target_chat_id).startswith("-100"):
                internal_id = str(abs(target_chat_id))[3:]
                link1 = f"https://t.me/c/{internal_id}/{msg1.message_id}"
            else:
                link1 = None

            parent_info = {
                "poll_id": part1_id,
                "parent_poll_id": part1_id,
                "title": base_title,
                "target_chat_id": target_chat_id,
                "target_chat_title": target_chat_title,
                "target_chat_username": target_chat_username,
                "ends_at": ends_at,
                "language": poll_lang,
                "winner_count": winner_count,
                "icon_style": icon_style
            }

            all_parts_summary = [(part1_id, 1, len(chunks[0]), link1)]
            for p_idx, chunk in enumerate(chunks[1:], start=2):
                p_id, p_link = await publish_single_part(
                    bot=bot,
                    creator_id=creator_id,
                    parent_poll=parent_info,
                    candidates_list=chunk,
                    part_number=p_idx,
                    lang=poll_lang
                )
                all_parts_summary.append((p_id, p_idx, len(chunk), p_link))

            start_display = format_datetime_readable(created_at)
            end_display = format_datetime_readable(ends_at) if ends_at else ("ম্যানুয়াল সমাপ্তি" if creator_lang == "bn" else "Manual Closure")

            if creator_lang == "en":
                parts_lines = "\n".join([f"   • Part {p_num} (ID #{p_id}): {c_count} candidates" for p_id, p_num, c_count, _ in all_parts_summary])
                congrats_text = (
                    f"🎉 <b>Multi-Part Poll Published Successfully!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"📢 <b>Channel:</b> {html.escape(target_chat_title)}\n"
                    f"📌 <b>Title:</b> {base_title}\n"
                    f"📑 <b>Published Parts ({num_parts} total):</b>\n{parts_lines}\n"
                    f"⏱️ <b>Schedule:</b>\n"
                    f"   🟢 <b>Start:</b> <code>{start_display}</code>\n"
                    f"   🔴 <b>End:</b> <code>{end_display}</code>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"<i>All {num_parts} parts have been posted sequentially in your channel right below each other!</i>"
                )
            else:
                parts_lines = "\n".join([f"   • পর্ব {p_num} (আইডি #{p_id}): {c_count} জন প্রার্থী" for p_id, p_num, c_count, _ in all_parts_summary])
                congrats_text = (
                    f"🎉 <b>মাল্টি-পার্ট পোল সফলভাবে চ্যানেলে পোস্ট হয়েছে!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"📢 <b>চ্যানেল:</b> {html.escape(target_chat_title)}\n"
                    f"📌 <b>মূল শিরোনাম:</b> {base_title}\n"
                    f"📑 <b>পোস্ট হওয়া পর্বসমূহ (মোট {num_parts} টি):</b>\n{parts_lines}\n"
                    f"⏱️ <b>সময়সূচি:</b>\n"
                    f"   🟢 <b>শুরু:</b> <code>{start_display}</code>\n"
                    f"   🔴 <b>শেষ:</b> <code>{end_display}</code>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"<i>সবগুলো পর্ব ধারাবাহিকভাবে চ্যানেলে একটার নিচে আরেকটা পোস্ট হয়েছে!</i>"
                )

            action_buttons = [
                [InlineKeyboardButton(
                    text=f"➕ Add Part {num_parts + 1} / পরবর্তী পর্ব যোগ করুন (আরো নাম)" if creator_lang == "bn" else f"➕ Add Part {num_parts + 1} (More Candidates)",
                    callback_data=f"add_part:{part1_id}"
                )]
            ]
            if link1:
                action_buttons.append([InlineKeyboardButton(text="🔗 View Part 1 in Channel / চ্যানেলে দেখুন", url=link1)])
            action_buttons.append([make_custom_button(text="🔙 Main Menu / মূল মেনু" if creator_lang == "bn" else "🔙 Main Menu", callback_data="menu_back_main", custom_emoji_id=START_MENU_CUSTOM_EMOJI_ID)])

            await callback.message.edit_text(
                congrats_text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=action_buttons),
                parse_mode="HTML",
                disable_web_page_preview=True
            )

        await state.clear()
        await callback.answer("Published successfully!")

    except Exception as e:
        await state.update_data(_is_publishing=False)
        retry_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Retry Publish / আবার চেষ্টা করুন", callback_data="confirm_publish"),
                InlineKeyboardButton(text="❌ Cancel / বাতিল", callback_data="cancel_publish")
            ]
        ])
        await callback.message.answer(
            f"❌ Failed to post message: <code>{html.escape(str(e))}</code>\n\n"
            "চ্যানেলে বটটি Administrator কিনা এবং 'Post Messages' পারমিশন অন আছে কিনা দেখে আবার চেষ্টা করুন:",
            reply_markup=retry_kb,
            parse_mode="HTML"
        )
        await callback.answer()

@router.callback_query(F.data.startswith("add_part:"))
async def cb_add_part(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user_lang = await get_user_language(user_id)
    poll_id = int(callback.data.split(":")[1])
    parent_poll = await get_poll(poll_id)
    if not parent_poll:
        await callback.answer("Poll not found!", show_alert=True)
        return
    if parent_poll["creator_id"] != user_id:
        await callback.answer("No permission!", show_alert=True)
        return

    root_id = parent_poll.get("parent_poll_id") or parent_poll["poll_id"]
    next_part = await get_next_part_number(root_id)

    await state.clear()
    await state.set_state(PollCreationState.add_part)
    await state.update_data(target_parent_poll_id=root_id, next_part_number=next_part)

    cancel_btn_text = "🔙 Cancel / বাতিল" if user_lang == "bn" else "🔙 Cancel"
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=cancel_btn_text, callback_data="cancel_publish")]
    ])

    base_title = get_base_title(parent_poll["title"])
    if user_lang == "en":
        prompt = (
            f"➕ <b>Add Part {next_part} / পরবর্তী পর্ব যোগ করুন</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>Contest:</b> {base_title}\n"
            f"📢 <b>Channel:</b> {html.escape(parent_poll.get('target_chat_title') or 'Channel')}\n\n"
            f"Send the candidate names for <b>Part {next_part}</b> (separated by newlines or commas, up to 29 candidates):\n\n"
            f"💡 <i>These candidates will be published directly to <b>{html.escape(parent_poll.get('target_chat_title') or '')}</b> right below Part 1 with the same duration and settings!</i>\n\n"
            f"Cancel: /cancel"
        )
    else:
        prompt = (
            f"➕ <b>Part {next_part} (পরবর্তী পর্ব) যোগ করুন</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>মূল শিরোনাম:</b> {base_title}\n"
            f"📢 <b>চ্যানেল:</b> {html.escape(parent_poll.get('target_chat_title') or 'Channel')}\n\n"
            f"<b>Part {next_part}</b> এর প্রার্থীদের নাম লিখে পাঠান (প্রতি লাইনে একটি করে অথবা কমা দিয়ে, সর্বোচ্চ ২৯ জন):\n\n"
            f"💡 <i>এই প্রার্থীরা একই চ্যানেলে প্রথম পোলের ঠিক নিচে একই সময়সীমা ও টাইটেল অনুযায়ী লাইভ হবে!</i>\n\n"
            f"বাতিল করতে: /cancel"
        )
    await callback.message.edit_text(prompt, reply_markup=cancel_kb, parse_mode="HTML")
    await callback.answer()

@router.message(PollCreationState.add_part)
async def process_add_part_candidates(message: Message, state: FSMContext):
    if await check_command_breakout(message, state):
        return

    raw_text = message.text.strip()
    if "\n" in raw_text:
        candidates = [c.strip() for c in raw_text.split("\n") if c.strip()]
    else:
        candidates = [c.strip() for c in raw_text.split(",") if c.strip()]

    if len(candidates) < 2:
        await message.answer("⚠️ Minimum 2 candidates required / কমপক্ষে ২টি নাম দিন:")
        return

    data = await state.get_data()
    if data.get("_is_processing"):
        return
    await state.update_data(_is_processing=True)

    root_poll_id = data.get("target_parent_poll_id")
    parent_poll = await get_poll(root_poll_id)
    if not parent_poll:
        await state.clear()
        await message.answer("⚠️ Original poll not found!")
        return

    user_id = message.from_user.id
    user_lang = await get_user_language(user_id)
    bot = message.bot

    CHUNK_SIZE = 29
    chunks = [candidates[i:i + CHUNK_SIZE] for i in range(0, len(candidates), CHUNK_SIZE)]
    next_part = await get_next_part_number(root_poll_id)

    # Ensure Part 1 has [Part 1]
    base_title = get_base_title(parent_poll["title"])
    if not re.search(r"\[(Part|পর্ব)\s*\d+\]", parent_poll["title"], re.IGNORECASE):
        part1_title = f"{base_title} [Part 1]" if user_lang == "en" else f"{base_title} [পর্ব ১]"
        await update_poll_title(parent_poll["poll_id"], part1_title)
        if parent_poll.get("channel_message_id") and parent_poll.get("target_chat_id"):
            try:
                bot_info = await bot.get_me()
                updated_card = await render_poll_card(
                    part1_title,
                    bot_info.username,
                    lang=user_lang,
                    ends_at=parent_poll.get("ends_at"),
                    created_at=parent_poll.get("created_at")
                )
                p1_cands = await get_candidates(parent_poll["poll_id"])
                cta_text, cta_url = await render_poll_cta(bot_info.username, lang=user_lang)
                icon_style = parent_poll.get("icon_style") or await get_user_icon_style(parent_poll.get("creator_id", 0))
                p1_kb = build_poll_keyboard(parent_poll["poll_id"], p1_cands, bot_info.username, cta_text=cta_text, cta_url=cta_url, icon_style=icon_style)
                await bot.edit_message_text(
                    chat_id=parent_poll["target_chat_id"],
                    message_id=parent_poll["channel_message_id"],
                    text=updated_card,
                    reply_markup=p1_kb,
                    parse_mode="HTML"
                )
            except Exception:
                pass

    created_part_ids = []
    links = []
    current_p_num = next_part
    for chunk in chunks:
        new_poll_id, channel_link = await publish_single_part(
            bot=bot,
            creator_id=user_id,
            parent_poll=parent_poll,
            candidates_list=chunk,
            part_number=current_p_num,
            lang=user_lang
        )
        created_part_ids.append((new_poll_id, current_p_num, len(chunk)))
        if channel_link:
            links.append((current_p_num, channel_link))
        current_p_num += 1

    await state.clear()
    next_next_part = current_p_num
    success_buttons = [
        [InlineKeyboardButton(
            text=f"➕ Add Part {next_next_part} / আরো নাম দিন" if user_lang == "bn" else f"➕ Add Part {next_next_part} (More Candidates)",
            callback_data=f"add_part:{root_poll_id}"
        )]
    ]
    if links:
        link_row = [InlineKeyboardButton(text=f"🔗 View Part {num} / পর্বে যান", url=url) for num, url in links[:2]]
        success_buttons.append(link_row)
    success_buttons.append([
        make_custom_button(text="🔙 Main Menu / মূল মেনু" if user_lang == "bn" else "🔙 Main Menu", callback_data="menu_back_main", custom_emoji_id=START_MENU_CUSTOM_EMOJI_ID)
    ])

    if user_lang == "en":
        summary_items = "\n".join([f"• <b>Part {p_num} (ID #{p_id}):</b> {c_count} candidates" for p_id, p_num, c_count in created_part_ids])
        congrats = (
            f"🎉 <b>Successfully Published to Channel!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>Title:</b> {base_title}\n"
            f"📢 <b>Channel:</b> {html.escape(parent_poll.get('target_chat_title') or '')}\n"
            f"👥 <b>New Parts Added:</b>\n{summary_items}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>The new part has been published right below Part 1 with the same duration and settings!</i>"
        )
    else:
        summary_items_bn = "\n".join([f"• <b>পর্ব {p_num} (আইডি #{p_id}):</b> {c_count} জন প্রার্থী" for p_id, p_num, c_count in created_part_ids])
        congrats = (
            f"🎉 <b>পরবর্তী পর্ব সফলভাবে চ্যানেলে পোস্ট হয়েছে!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>মূল শিরোনাম:</b> {base_title}\n"
            f"📢 <b>চ্যানেল:</b> {html.escape(parent_poll.get('target_chat_title') or '')}\n"
            f"👥 <b>নতুন যুক্ত হওয়া পর্ব:</b>\n{summary_items_bn}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>নতুন পর্বটি চ্যানেলে আগের পোলের ঠিক নিচে একই সময়সীমা অনুযায়ী লাইভ হয়ে গেছে!</i>"
        )

    await message.answer(congrats, reply_markup=InlineKeyboardMarkup(inline_keyboard=success_buttons), parse_mode="HTML")

@router.message(StateFilter(None), F.text)
async def check_unprompted_candidate_paste(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        return
    text = message.text.strip()
    if text.startswith("/"):
        return

    if "\n" in text:
        candidates = [c.strip() for c in text.split("\n") if c.strip()]
    else:
        candidates = [c.strip() for c in text.split(",") if c.strip()]

    user_id = message.from_user.id
    user_lang = await get_user_language(user_id)

    if len(candidates) < 2:
        bot_info = await message.bot.get_me()
        clean_bot = bot_info.username.lstrip("@")
        add_chan_url = f"https://t.me/{clean_bot}?startchannel=true&admin=post_messages+edit_messages+delete_messages"

        if user_lang == "en":
            guide_text = (
                "🤖 <b>Smart Assistant & Quick Guide</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "I noticed your message! Here is how you can use me easily:\n\n"
                "📢 <b>Add Bot to your Channel:</b>\n"
                "Tap <b>'Add Bot to Channel (1-Click)'</b> below — select your channel and the bot will instantly be appointed Administrator with all required permissions!\n\n"
                "📊 <b>Create a Contest / Poll:</b>\n"
                "Tap <b>'Create New Poll'</b> or send <code>/newpoll</code>. You can also paste 2 or more candidate names (one per line) anytime!\n\n"
                "⚙️ <b>Manage Live Contests:</b> Check your active contests with <code>/mypolls</code>."
            )
            btn_add = "Add Bot to Channel (1-Click) ➔"
            btn_create = "Create New Poll"
            btn_help = "Help & Guide"
        else:
            guide_text = (
                "🤖 <b>স্মার্ট সহকারী ও তাৎক্ষণিক গাইড</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "আপনার বার্তাটি পেয়েছি! কীভাবে সহজে বট ব্যবহার করবেন দেখে নিন:\n\n"
                "📢 <b>চ্যানেলে বট এডমিন করতে চান?</b>\n"
                "নিচের <b>'চ্যানেলে যুক্ত করুন (১-ক্লিক)'</b> বাটনে চাপুন — চ্যানেল বেছে নিলেই স্বয়ংক্রিয়ভাবে সব পারমিশনসহ এডমিন হয়ে যাবে!\n\n"
                "📊 <b>নতুন পোল তৈরি করতে চান?</b>\n"
                "নিচের <b>'নতুন পোল তৈরি করুন'</b> বাটনে চাপুন অথবা <code>/newpoll</code> লিখুন। এছাড়া যেকোনো সময় প্রার্থীদের নামের তালিকা (কমপক্ষে ২টি নাম, প্রতি লাইনে ১টি) পাঠিয়ে দিলে বট সাথে সাথে পোল তৈরি শুরু করবে!\n\n"
                "⚙️ <b>চলমান পোল দেখতে:</b> <code>/mypolls</code> কমান্ড ব্যবহার করুন।"
            )
            btn_add = "চ্যানেলে যুক্ত করুন (১-ক্লিক এডমিন) ➔"
            btn_create = "নতুন পোল তৈরি করুন"
            btn_help = "ব্যবহারের নিয়ম ও গাইড"

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [make_custom_button(text=btn_add, url=add_chan_url, custom_emoji_id=ADD_CHANNEL_CUSTOM_EMOJI_ID)],
            [
                make_custom_button(text=btn_create, callback_data="create_new_poll", custom_emoji_id=CREATE_POLL_CUSTOM_EMOJI_ID),
                make_custom_button(text=btn_help, callback_data="help", custom_emoji_id=HELP_CUSTOM_EMOJI_ID)
            ]
        ])
        await message.answer(guide_text, reply_markup=kb, parse_mode="HTML")
        return

    # User sent 2 or more candidate names directly!
    # Immediately save them and begin poll creation wizard at Title step!
    CHUNK_SIZE = 29
    chunks = [candidates[i:i + CHUNK_SIZE] for i in range(0, len(candidates), CHUNK_SIZE)]
    await state.clear()
    await state.update_data(
        candidates=candidates,
        candidate_chunks=chunks,
        pasted_candidates=candidates
    )
    await state.set_state(PollCreationState.title)

    cancel_btn_text = "🔙 Cancel / বাতিল" if user_lang == "bn" else "🔙 Cancel"
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=cancel_btn_text, callback_data="cancel_publish")]
    ])

    if user_lang == "en":
        prompt = (
            f"💡 <b>{len(candidates)} candidate names detected & saved!</b>\n\n"
            f'<tg-emoji emoji-id="{STEP1_TITLE_CUSTOM_EMOJI_ID}">📝</tg-emoji> <b>Step 1/4: Poll Title / পোলের শিরোনাম</b>\n'
            f"Please enter the Title or Question for this poll / giveaway:\n"
            f"<i>(Example: 🎉 Eid Mega Giveaway 2026: Vote Your Favorite Creator!)</i>\n\n"
            f"To cancel, type /cancel or tap below:"
        )
    else:
        prompt = (
            f"💡 <b>{len(candidates)} জন প্রার্থীর নাম পাওয়া গেছে এবং সংরক্ষিত হয়েছে!</b>\n\n"
            f'<tg-emoji emoji-id="{STEP1_TITLE_CUSTOM_EMOJI_ID}">📝</tg-emoji> <b>ধাপ ১/৪: পোলের শিরোনাম / টাইটেল</b>\n'
            f"এই পোলের জন্য একটি আকর্ষণীয় টাইটেল বা প্রশ্ন লিখে পাঠান:\n"
            f"<i>(উদাহরণ: 🎉 ঈদ মেগা গিভঅ্যাওয়ে ২০২৬: পছন্দের ক্রিয়েটরকে ভোট দিন!)</i>\n\n"
            f"বাতিল করতে /cancel লিখুন বা নিচের বাটনে চাপুন:"
        )
    await message.answer(prompt, reply_markup=cancel_kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("apply_paste_part:"))
async def cb_apply_paste_part(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass
    data = await state.get_data()
    candidates = data.get("pasted_candidates") or data.get("candidates")
    root_id = int(callback.data.split(":")[1])
    parent_poll = await get_poll(root_id)
    user_id = callback.from_user.id
    user_lang = await get_user_language(user_id)
    bot = callback.bot

    if not candidates or not parent_poll:
        await callback.answer("Data expired, please resend candidates.", show_alert=True)
        await state.clear()
        return

    CHUNK_SIZE = 29
    chunks = [candidates[i:i + CHUNK_SIZE] for i in range(0, len(candidates), CHUNK_SIZE)]
    next_part = await get_next_part_number(root_id)

    # Ensure Part 1 has [Part 1]
    base_title = get_base_title(parent_poll["title"])
    if not re.search(r"\[(Part|পর্ব)\s*\d+\]", parent_poll["title"], re.IGNORECASE):
        part1_title = f"{base_title} [Part 1]" if user_lang == "en" else f"{base_title} [পর্ব ১]"
        await update_poll_title(parent_poll["poll_id"], part1_title)
        if parent_poll.get("channel_message_id") and parent_poll.get("target_chat_id"):
            try:
                bot_info = await bot.get_me()
                updated_card = await render_poll_card(
                    part1_title,
                    bot_info.username,
                    lang=user_lang,
                    ends_at=parent_poll.get("ends_at"),
                    created_at=parent_poll.get("created_at")
                )
                p1_cands = await get_candidates(parent_poll["poll_id"])
                cta_text, cta_url = await render_poll_cta(bot_info.username, lang=user_lang)
                icon_style = parent_poll.get("icon_style") or await get_user_icon_style(parent_poll.get("creator_id", 0))
                p1_kb = build_poll_keyboard(parent_poll["poll_id"], p1_cands, bot_info.username, cta_text=cta_text, cta_url=cta_url, icon_style=icon_style)
                await bot.edit_message_text(
                    chat_id=parent_poll["target_chat_id"],
                    message_id=parent_poll["channel_message_id"],
                    text=updated_card,
                    reply_markup=p1_kb,
                    parse_mode="HTML"
                )
            except Exception:
                pass

    created_part_ids = []
    links = []
    current_p_num = next_part
    for chunk in chunks:
        new_poll_id, channel_link = await publish_single_part(
            bot=bot,
            creator_id=user_id,
            parent_poll=parent_poll,
            candidates_list=chunk,
            part_number=current_p_num,
            lang=user_lang
        )
        created_part_ids.append((new_poll_id, current_p_num, len(chunk)))
        if channel_link:
            links.append((current_p_num, channel_link))
        current_p_num += 1

    await state.clear()
    next_next_part = current_p_num
    success_buttons = [
        [InlineKeyboardButton(
            text=f"➕ Add Part {next_next_part} / আরো নাম দিন" if user_lang == "bn" else f"➕ Add Part {next_next_part} (More Candidates)",
            callback_data=f"add_part:{root_id}"
        )]
    ]
    if links:
        link_row = [InlineKeyboardButton(text=f"🔗 View Part {num} / পর্বে যান", url=url) for num, url in links[:2]]
        success_buttons.append(link_row)
    success_buttons.append([
        make_custom_button(text="🔙 Main Menu / মূল মেনু" if user_lang == "bn" else "🔙 Main Menu", callback_data="menu_back_main", custom_emoji_id=START_MENU_CUSTOM_EMOJI_ID)
    ])

    if user_lang == "en":
        summary_items = "\n".join([f"• <b>Part {p_num} (ID #{p_id}):</b> {c_count} candidates" for p_id, p_num, c_count in created_part_ids])
        congrats = (
            f"🎉 <b>Successfully Published to Channel!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>Title:</b> {base_title}\n"
            f"📢 <b>Channel:</b> {html.escape(parent_poll.get('target_chat_title') or '')}\n"
            f"👥 <b>New Parts Added:</b>\n{summary_items}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>The new part has been published right below Part 1 with the same duration and settings!</i>"
        )
    else:
        summary_items_bn = "\n".join([f"• <b>পর্ব {p_num} (আইডি #{p_id}):</b> {c_count} জন প্রার্থী" for p_id, p_num, c_count in created_part_ids])
        congrats = (
            f"🎉 <b>পরবর্তী পর্ব সফলভাবে চ্যানেলে পোস্ট হয়েছে!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>মূল শিরোনাম:</b> {base_title}\n"
            f"📢 <b>চ্যানেল:</b> {html.escape(parent_poll.get('target_chat_title') or '')}\n"
            f"👥 <b>নতুন যুক্ত হওয়া পর্ব:</b>\n{summary_items_bn}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>নতুন পর্বটি চ্যানেলে আগের পোলের ঠিক নিচে একই সময়সীমা অনুযায়ী লাইভ হয়ে গেছে!</i>"
        )
    await callback.message.edit_text(congrats, reply_markup=InlineKeyboardMarkup(inline_keyboard=success_buttons), parse_mode="HTML")
    await callback.answer("Published successfully!")

@router.callback_query(F.data == "apply_paste_new")
async def cb_apply_paste_new(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass
    data = await state.get_data()
    candidates = data.get("pasted_candidates") or data.get("candidates")
    user_lang = await get_user_language(callback.from_user.id)
    if not candidates:
        await start_poll_wizard(callback.message, state)
        return
    await state.clear()
    CHUNK_SIZE = 29
    chunks = [candidates[i:i + CHUNK_SIZE] for i in range(0, len(candidates), CHUNK_SIZE)]
    await state.update_data(candidates=candidates, candidate_chunks=chunks)
    await state.set_state(PollCreationState.title)
    cancel_btn_text = "🔙 Cancel / বাতিল" if user_lang == "bn" else "🔙 Cancel"
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=cancel_btn_text, callback_data="cancel_publish")]
    ])
    if user_lang == "en":
        text = (
            f"📝 <b>Create New Poll ({len(candidates)} Candidates Saved)</b>\n\n"
            f"Enter the Title for this new poll / giveaway:\n\n"
            f"To cancel, type /cancel or tap below:"
        )
    else:
        text = (
            f"📝 <b>নতুন পোল তৈরি (মোট {len(candidates)} জনের নাম সংরক্ষিত)</b>\n\n"
            f"এই নতুন পোলের জন্য একটি আকর্ষণীয় টাইটেল বা শিরোনাম লিখে পাঠান:\n\n"
            f"বাতিল করতে /cancel লিখুন বা নিচের বাটনে চাপুন:"
        )
    await callback.message.edit_text(text, reply_markup=cancel_kb, parse_mode="HTML")

@router.callback_query(F.data == "apply_paste_dismiss")
async def cb_apply_paste_dismiss(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass
    await state.clear()
    try:
        await callback.message.delete()
    except Exception:
        pass

@router.callback_query(F.data == "cancel_publish")
async def cancel_publish(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass
    await state.clear()
    user_lang = await get_user_language(callback.from_user.id)
    back_text = "🔙 Back to Main Menu / মূল মেনু" if user_lang == "bn" else "🔙 Back to Main Menu"
    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [make_custom_button(text=back_text, callback_data="menu_back_main", custom_emoji_id=START_MENU_CUSTOM_EMOJI_ID)]
    ])
    await safe_answer_or_edit(
        callback,
        "❌ Poll publication cancelled / পোল বাতিল করা হয়েছে।",
        reply_markup=back_kb,
        is_callback=True,
        parse_mode="HTML"
    )

# Alias for backwards compatibility
cmd_new_poll = start_poll_wizard

