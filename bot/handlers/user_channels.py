import html
import logging
from typing import Optional, Union
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.database.db import (
    get_channel, save_channel, set_channel_status,
    get_user_all_channels, unlink_user_channel,
    is_user_authorized_for_channel_db, record_user_channel_access,
    get_user_language
)
from bot.keyboards.inline import (
    build_user_channels_keyboard,
    build_user_channel_detail_keyboard,
    build_user_channel_confirm_delete_keyboard,
    make_custom_button,
    STEP1_TITLE_CUSTOM_EMOJI_ID,
    START_MENU_CUSTOM_EMOJI_ID,
    ADD_CHANNEL_CUSTOM_EMOJI_ID,
    ADDED_CHANNELS_CUSTOM_EMOJI_ID
)
from bot.handlers.poll_create import PollCreationState, safe_answer_or_edit

logger = logging.getLogger(__name__)

router = Router()


class UserChannelStates(StatesGroup):
    add_channel = State()


async def show_user_channels(
    target: Union[Message, CallbackQuery],
    bot,
    user_id: int,
    is_callback: bool = False
):
    """
    Renders the Added Channels dashboard for a user.
    Shows all connected channels with status indicators (🟢 Active / 🔴 Inactive)
    and quick actions.
    """
    lang = await get_user_language(user_id)
    channels = await get_user_all_channels(user_id)
    bot_info = await bot.get_me()
    add_channel_url = (
        f"https://t.me/{bot_info.username}?startchannel=true&admin=post_messages+edit_messages+delete_messages"
        if bot_info.username else None
    )

    total = len(channels)
    active_cnt = sum(1 for c in channels if c.get("is_active", 1) == 1)
    inactive_cnt = total - active_cnt

    if lang == "en":
        if total == 0:
            text = (
                "📢 <b>Added Channels / Your Connected Channels</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "ℹ️ You have not added any channels yet.\n\n"
                "To post polls and host contests in your Telegram channel, "
                "add the bot as an Administrator using the 1-click button or enter your channel manually below:"
            )
        else:
            text = (
                "📢 <b>Your Added Channels</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"📊 <b>Total Channels:</b> <code>{total}</code>\n"
                f"🟢 <b>Active & Ready:</b> <code>{active_cnt}</code> | "
                f"🔴 <b>Needs Attention:</b> <code>{inactive_cnt}</code>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "<i>Tap any channel below to view details, test permissions, or create a poll:</i>"
            )
    elif lang == "hi":
        if total == 0:
            text = (
                "📢 <b>जुड़े हुए चैनल (Added Channels)</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "ℹ️ आपने अभी तक कोई चैनल नहीं जोड़ा है।\n\n"
                "अपने टेलीग्राम चैनल में पोल चलाने के लिए नीचे दिए गए 1-क्लिक बटन पर टैप करें या मैन्युअल रूप से जोड़ें:"
            )
        else:
            text = (
                "📢 <b>आपके जुड़े हुए चैनल (Added Channels)</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"📊 <b>कुल चैनल:</b> <code>{total}</code>\n"
                f"🟢 <b>सक्रिय:</b> <code>{active_cnt}</code> | "
                f"🔴 <b>निष्क्रिय:</b> <code>{inactive_cnt}</code>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "<i>विवरण देखने या पोल बनाने के लिए किसी भी चैनल पर टैপ करें:</i>"
            )
    elif lang == "ar":
        if total == 0:
            text = (
                "📢 <b>القنوات المضافة (Added Channels)</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "ℹ️ لم تقم بإضافة أي قنوات بعد.\n\n"
                "لنشر استطلاعات الرأي في قناتك، أضف البوت كمشرف عبر زر النقرة الواحدة أو أرسل المعرف أدناه:"
            )
        else:
            text = (
                "📢 <b>قنواتك المضافة (Added Channels)</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"📊 <b>إجمالي القنوات:</b> <code>{total}</code>\n"
                f"🟢 <b>نشطة وجاهزة:</b> <code>{active_cnt}</code> | "
                f"🔴 <b>بحاجة إلى انتباه:</b> <code>{inactive_cnt}</code>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "<i>اضغط على أي قناة أدناه للاطلاع على التفاصيل، فحص الأذونات، أو إنشاء استطلاع:</i>"
            )
    elif lang == "ru":
        if total == 0:
            text = (
                "📢 <b>Добавленные каналы (Added Channels)</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "ℹ️ Вы еще не добавили ни одного канала.\n\n"
                "Чтобы проводить опросы в своем канале, добавьте бота администратором в 1 клик или отправьте логин канала вручную:"
            )
        else:
            text = (
                "📢 <b>Ваши добавленные каналы (Added Channels)</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"📊 <b>Всего каналов:</b> <code>{total}</code>\n"
                f"🟢 <b>Активные и готовые:</b> <code>{active_cnt}</code> | "
                f"🔴 <b>Требуют внимания:</b> <code>{inactive_cnt}</code>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "<i>Нажмите на любой канал для просмотра, проверки прав или запуска опроса:</i>"
            )
    else:
        if total == 0:
            text = (
                "📢 <b>যুক্ত চ্যানেলসমূহ / Added Channels</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "ℹ️ আপনার কোনো চ্যানেল যুক্ত করা নেই।\n\n"
                "টেলিগ্রাম চ্যানেলে পোল তৈরি ও ভোট গ্রহণ করতে নিচের <b>'১-ক্লিক এডমিন'</b> "
                "বাটনে চাপ দিয়ে বট যুক্ত করুন অথবা ইউজারনেম/আইডি দিয়ে ম্যানুয়ালি যুক্ত করুন:"
            )
        else:
            text = (
                "📢 <b>আপনার যুক্তকৃত চ্যানেলসমূহ (Added Channels)</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"📊 <b>মোট চ্যানেল:</b> <code>{total}</code> টি\n"
                f"🟢 <b>সক্রিয় ও প্রস্তুত:</b> <code>{active_cnt}</code> টি | "
                f"🔴 <b>নিষ্ক্রিয়/পারমিশন প্রয়োজন:</b> <code>{inactive_cnt}</code> টি\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "<i>যেকোনো চ্যানেলের বিস্তারিত দেখতে, পারমিশন যাচাই করতে বা পোল তৈরি করতে চ্যানেলের নামের বাটনে চাপ দিন:</i>"
            )

    keyboard = build_user_channels_keyboard(channels, add_channel_url, lang)

    if is_callback:
        try:
            await target.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        except Exception:
            await target.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await target.answer(text, reply_markup=keyboard, parse_mode="HTML")


# --- Callback query: menu_my_channels ---
@router.callback_query(F.data == "menu_my_channels")
async def cb_user_my_channels(callback: CallbackQuery, state: FSMContext = None):
    if state:
        await state.clear()
    await show_user_channels(callback, callback.bot, callback.from_user.id, is_callback=True)
    await callback.answer()


# --- View a specific channel ---
@router.callback_query(F.data.startswith("user_chan_view:"))
async def cb_user_chan_view(callback: CallbackQuery):
    chat_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    lang = await get_user_language(user_id)

    # Multi-tenant isolation check: only authorized user can view
    is_auth = await is_user_authorized_for_channel_db(user_id, chat_id)
    if not is_auth:
        err_msg = "⛔ Access Denied: You are not authorized for this channel!" if lang == "en" else "⛔ অননুমোদিত চ্যানেল / আপনি এই চ্যানেলের মালিক বা এডমিন নন!"
        await callback.answer(err_msg, show_alert=True)
        await show_user_channels(callback, callback.bot, user_id, is_callback=True)
        return

    ch = await get_channel(chat_id)
    if not ch:
        not_found = "Channel not found!" if lang == "en" else "চ্যানেলটি পাওয়া যায়নি!"
        await callback.answer(not_found, show_alert=True)
        await show_user_channels(callback, callback.bot, user_id, is_callback=True)
        return

    is_active = (ch.get("is_active", 1) == 1)
    status_str = "🟢 Active & Ready / সক্রিয় ও প্রস্তুত" if is_active else "🔴 Inactive / পারমিশন ত্রুটি বা সরানো হয়েছে"
    username_str = f"@{ch['username']}" if ch.get("username") else "No public username / পাবলিক লিংক নেই"

    if lang == "en":
        text = (
            "📢 <b>Channel Details</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>Title:</b> {html.escape(ch.get('title') or 'Untitled')}\n"
            f"🆔 <b>Chat ID:</b> <code>{ch['chat_id']}</code>\n"
            f"🔗 <b>Username:</b> {username_str}\n"
            f"⚡ <b>Status:</b> {status_str}\n"
            f"📅 <b>Added Date:</b> {ch.get('created_at', 'N/A')}\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Choose an action below:"
        )
    elif lang == "hi":
        text = (
            "📢 <b>चैनल विवरण (Channel Details)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>नाम:</b> {html.escape(ch.get('title') or 'Untitled')}\n"
            f"🆔 <b>चैनल आईडी:</b> <code>{ch['chat_id']}</code>\n"
            f"🔗 <b>यूजरनेम:</b> {username_str}\n"
            f"⚡ <b>स्थिति:</b> {status_str}\n"
            f"📅 <b>जोड़ने की तिथि:</b> {ch.get('created_at', 'N/A')}\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "नीचे कोई क्रिया चुनें:"
        )
    elif lang == "ar":
        text = (
            "📢 <b>تفاصيل القناة (Channel Details)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>الاسم:</b> {html.escape(ch.get('title') or 'Untitled')}\n"
            f"🆔 <b>معرف القناة:</b> <code>{ch['chat_id']}</code>\n"
            f"🔗 <b>اسم المستخدم:</b> {username_str}\n"
            f"⚡ <b>الحالة:</b> {status_str}\n"
            f"📅 <b>تاريخ الإضافة:</b> {ch.get('created_at', 'N/A')}\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "اختر إجراءً أدناه:"
        )
    elif lang == "ru":
        text = (
            "📢 <b>Детали канала (Channel Details)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>Название:</b> {html.escape(ch.get('title') or 'Untitled')}\n"
            f"🆔 <b>ID чата:</b> <code>{ch['chat_id']}</code>\n"
            f"🔗 <b>Юзернейм:</b> {username_str}\n"
            f"⚡ <b>Статус:</b> {status_str}\n"
            f"📅 <b>Дата добавления:</b> {ch.get('created_at', 'N/A')}\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Выберите действие ниже:"
        )
    else:
        text = (
            "📢 <b>চ্যানেল বিবরণ (Channel Details)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>নাম:</b> {html.escape(ch.get('title') or 'Untitled')}\n"
            f"🆔 <b>চ্যানেল আইডি:</b> <code>{ch['chat_id']}</code>\n"
            f"🔗 <b>ইউজারনেম:</b> {username_str}\n"
            f"⚡ <b>স্ট্যাটাস:</b> {status_str}\n"
            f"📅 <b>যুক্ত হওয়ার তারিখ:</b> {ch.get('created_at', 'N/A')}\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "নিচের যেকোনো অপশন বেছে নিন:"
        )

    await callback.message.edit_text(
        text,
        reply_markup=build_user_channel_detail_keyboard(chat_id, is_active, lang),
        parse_mode="HTML"
    )
    await callback.answer()


# --- Re-test channel permissions ---
@router.callback_query(F.data.startswith("user_chan_test:"))
async def cb_user_chan_test(callback: CallbackQuery):
    chat_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    lang = await get_user_language(user_id)

    is_auth = await is_user_authorized_for_channel_db(user_id, chat_id)
    if not is_auth:
        await callback.answer("⛔ Access Denied!", show_alert=True)
        return

    bot = callback.bot
    try:
        member = await bot.get_chat_member(chat_id, bot.id)
        if member.status in ["administrator", "creator"]:
            can_post = getattr(member, "can_post_messages", True)
            if can_post:
                await set_channel_status(chat_id, 1)
                msg = "✅ পারমিশন ঠিক আছে! বট সক্রিয় এবং মেসেজ পোস্ট করতে পারবে।" if lang == "bn" else "✅ All permissions verified! Bot is active."
                await callback.answer(msg, show_alert=True)
            else:
                await set_channel_status(chat_id, 0)
                msg = "⚠️ বট এডমিন আছে, কিন্তু 'Post Messages' পারমিশন বন্ধ আছে! চ্যানেলের সেটিংসে অন করুন।" if lang == "bn" else "⚠️ Bot is admin, but lacks 'Post Messages' permission!"
                await callback.answer(msg, show_alert=True)
        else:
            await set_channel_status(chat_id, 0)
            msg = "❌ বট এই চ্যানেলে আর এডমিন নেই! দয়া করে বটকে পুনরায় এডমিন করুন।" if lang == "bn" else "❌ Bot is no longer an admin in this channel!"
            await callback.answer(msg, show_alert=True)
    except Exception as e:
        await set_channel_status(chat_id, 0)
        await callback.answer(f"❌ Connection error: {e}", show_alert=True)

    await cb_user_chan_view(callback)


# --- Disconnect channel confirmation ---
@router.callback_query(F.data.startswith("user_chan_del:"))
async def cb_user_chan_del(callback: CallbackQuery):
    chat_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    lang = await get_user_language(user_id)

    is_auth = await is_user_authorized_for_channel_db(user_id, chat_id)
    if not is_auth:
        await callback.answer("⛔ Access Denied!", show_alert=True)
        return

    ch = await get_channel(chat_id)
    title = ch.get("title") if ch else "Channel"

    if lang == "en":
        text = (
            f"⚠️ <b>Disconnect Channel?</b>\n\n"
            f"Are you sure you want to remove <b>{html.escape(title)}</b> from your connected channels?\n\n"
            "<i>(You can reconnect it anytime by adding the bot as admin again.)</i>"
        )
    elif lang == "hi":
        text = (
            f"⚠️ <b>चैनल हटाएं?</b>\n\n"
            f"क्या आप वाकई <b>{html.escape(title)}</b> को अपने जुड़े हुए चैनलों से हटाना चाहते हैं?\n\n"
            "<i>(आप बॉट को फिर से एडमिन बनाकर कभी भी जोड़ सकते हैं।)</i>"
        )
    elif lang == "ar":
        text = (
            f"⚠️ <b>فصل القناة؟</b>\n\n"
            f"هل أنت متأكد من رغبتك في إزالة <b>{html.escape(title)}</b> من قنواتك المتصلة؟\n\n"
            "<i>(يمكنك إعادة توصيلها في أي وقت بإضافة البوت كمشرف مرة أخرى.)</i>"
        )
    elif lang == "ru":
        text = (
            f"⚠️ <b>Отключить канал?</b>\n\n"
            f"Вы уверены, что хотите удалить <b>{html.escape(title)}</b> из подключенных каналов?\n\n"
            "<i>(Вы можете повторно подключить его в любое время, добавив бота админом.)</i>"
        )
    else:
        text = (
            f"⚠️ <b>চ্যানেলটি সরাতে চান?</b>\n\n"
            f"আপনি কি নিশ্চিত <b>{html.escape(title)}</b> চ্যানেলটি আপনার যুক্ত চ্যানেল তালিকা থেকে সরাতে চান?\n\n"
            "<i>(পরবর্তীতে প্রয়োজন হলে যেকোনো সময় আবার যুক্ত করতে পারবেন।)</i>"
        )

    await callback.message.edit_text(
        text,
        reply_markup=build_user_channel_confirm_delete_keyboard(chat_id, lang),
        parse_mode="HTML"
    )
    await callback.answer()


# --- Confirm disconnect channel ---
@router.callback_query(F.data.startswith("user_chan_del_confirm:"))
async def cb_user_chan_del_confirm(callback: CallbackQuery):
    chat_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    lang = await get_user_language(user_id)

    is_auth = await is_user_authorized_for_channel_db(user_id, chat_id)
    if not is_auth:
        await callback.answer("⛔ Access Denied!", show_alert=True)
        return

    await unlink_user_channel(user_id, chat_id)
    msg = "🗑️ চ্যানেলটি আপনার তালিকা থেকে সরানো হয়েছে।" if lang == "bn" else "🗑️ Channel removed from your list."
    await callback.answer(msg, show_alert=True)
    await show_user_channels(callback, callback.bot, user_id, is_callback=True)


# --- Create poll shortcut directly from channel view ---
@router.callback_query(F.data.startswith("chan_create_poll:"))
async def cb_chan_create_poll(callback: CallbackQuery, state: FSMContext):
    chat_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    lang = await get_user_language(user_id)

    is_auth = await is_user_authorized_for_channel_db(user_id, chat_id)
    if not is_auth:
        await callback.answer("⛔ Access Denied!", show_alert=True)
        return

    ch = await get_channel(chat_id)
    if not ch:
        await callback.answer("Channel not found!", show_alert=True)
        return

    await state.clear()
    await state.set_state(PollCreationState.title)
    await state.update_data(
        preselected_target_chat_id=chat_id,
        preselected_target_chat_title=ch.get("title"),
        preselected_target_chat_username=ch.get("username")
    )

    back_btn_text = "🔙 Cancel & Back / ফিরে যান" if lang == "bn" else "🔙 Cancel & Back to Menu"
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [make_custom_button(text=back_btn_text, callback_data="menu_back_main", custom_emoji_id=START_MENU_CUSTOM_EMOJI_ID)]
    ])

    chan_title = html.escape(ch.get("title") or "Channel")
    prompt = (
        f'<tg-emoji emoji-id="{STEP1_TITLE_CUSTOM_EMOJI_ID}">📝</tg-emoji> <b>Step 1/4: Poll Title / পোলের শিরোনাম</b>\n\n'
        f"🎯 <b>Target Channel:</b> {chan_title}\n\n"
        "Enter your poll question or giveaway title:\n"
        "<i>আপনার পোলের টাইটেল বা প্রশ্ন লিখে পাঠান।</i>\n"
        "<i>(Example: 🎉 Eid Mega Giveaway 2026: Vote Your Favorite Creator!)</i>\n\n"
        "To cancel, type /cancel or tap below:"
    )

    await safe_answer_or_edit(
        callback,
        prompt,
        reply_markup=cancel_kb,
        is_callback=True,
        parse_mode="HTML"
    )
    await callback.answer()


# --- Error-Free Manual Channel Addition ---
@router.callback_query(F.data == "user_chan_add_manual")
async def cb_user_chan_add_manual(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    lang = await get_user_language(user_id)
    bot_info = await callback.bot.get_me()
    add_channel_url = (
        f"https://t.me/{bot_info.username}?startchannel=true&admin=post_messages+edit_messages+delete_messages"
        if bot_info.username else None
    )

    await state.set_state(UserChannelStates.add_channel)

    if lang == "en":
        txt = (
            "➕ <b>Add Channel to Your Dashboard</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Send any of the following:\n"
            "1. Channel <b>Username</b> (e.g. <code>@MyChannel</code>)\n"
            "2. Channel <b>Chat ID</b> (e.g. <code>-1001234567890</code>)\n"
            "3. Or <b>Forward any message</b> from your channel right here!\n\n"
            "⚠️ <b>Requirements:</b>\n"
            f"• <b>{bot_info.first_name}</b> must already be an <b>Administrator</b> in that channel with 'Post Messages' enabled.\n"
            "• You must be an Administrator or Owner of that channel.\n\n"
            "Type /cancel to abort."
        )
        cancel_txt = "❌ Cancel"
        one_click_txt = "📢 1-Click Setup (Recommended) ➔"
    else:
        txt = (
            "➕ <b>ম্যানুয়ালি চ্যানেল যুক্ত করুন (Add Channel)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "নিচের যেকোনো একটি পাঠিয়ে দিন:\n"
            "১. চ্যানেলের <b>ইউজারনেম</b> (যেমন: <code>@MyChannel</code>)\n"
            "২. অথবা চ্যানেলের <b>আইডি</b> (যেমন: <code>-1001234567890</code>)\n"
            "৩. অথবা আপনার চ্যানেল থেকে <b>যেকোনো একটি মেসেজ এখানে ফরোয়ার্ড</b> করুন!\n\n"
            "⚠️ <b>প্রয়োজনীয় শর্ত:</b>\n"
            f"• <b>{bot_info.first_name}</b> বটকে চ্যানেলে অবশ্যই <b>Administrator</b> করতে হবে (Post Messages অন রাখুন)।\n"
            "• আপনি নিজে ঐ চ্যানেলের এডমিন বা মালিক হতে হবে।\n\n"
            "বাতিল করতে /cancel লিখুন।"
        )
        cancel_txt = "❌ বাতিল / Cancel"
        one_click_txt = "📢 ১-ক্লিক সহজ সেটআপ (প্রস্তাবিত) ➔"

    kb_rows = []
    if add_channel_url:
        kb_rows.append([make_custom_button(text=one_click_txt, url=add_channel_url, custom_emoji_id=ADD_CHANNEL_CUSTOM_EMOJI_ID)])
    kb_rows.append([InlineKeyboardButton(text=cancel_txt, callback_data="menu_my_channels")])

    await callback.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="HTML")
    await callback.answer()


@router.message(UserChannelStates.add_channel)
async def process_user_add_channel(message: Message, state: FSMContext):
    user_id = message.from_user.id
    lang = await get_user_language(user_id)
    bot = message.bot
    bot_info = await bot.get_me()

    if message.text and message.text.startswith("/cancel"):
        await state.clear()
        cancel_reply = "❌ প্রক্রিয়া বাতিল করা হয়েছে।" if lang == "bn" else "❌ Process cancelled."
        await message.answer(cancel_reply)
        await show_user_channels(message, bot, user_id, is_callback=False)
        return

    # Check if forwarded from channel
    chat = None
    if message.forward_from_chat and message.forward_from_chat.type in ["channel", "supergroup"]:
        chat = message.forward_from_chat
    elif message.text:
        query = message.text.strip()
        status_msg = await message.answer("⏳ চ্যানেল ও পারমিশন পরীক্ষা করা হচ্ছে..." if lang == "bn" else "⏳ Verifying channel & permissions...")
        try:
            chat = await bot.get_chat(query)
        except Exception as e:
            err_txt = (
                f"❌ <b>চ্যানেলটি খুঁজে পাওয়া যায়নি! / Chat Not Found</b>\n\n"
                f"ভুল: <code>{html.escape(str(e))}</code>\n\n"
                "দয়া করে নিশ্চিত করুন ইউজারনেম সঠিক (যেমন: <code>@MyChannel</code>) এবং বটটি ঐ চ্যানেলে মেম্বার/এডমিন হিসেবে যুক্ত আছে।"
                if lang == "bn" else
                f"❌ <b>Channel Not Found!</b>\n\n"
                f"Error: <code>{html.escape(str(e))}</code>\n\n"
                "Please make sure the username/ID is correct and the bot has been added to the channel."
            )
            await status_msg.edit_text(err_txt, parse_mode="HTML")
            return
    else:
        await message.answer("⚠️ অনুগ্রহ করে চ্যানেলের ইউজারনেম/আইডি লিখুন অথবা চ্যানেল থেকে একটি মেসেজ ফরোয়ার্ড করুন।")
        return

    if chat.type not in ["channel", "supergroup"]:
        await message.answer("⚠️ এটি কোনো চ্যানেল বা সুপারগ্রুপ নয়! শুধুমাত্র চ্যানেল যুক্ত করা যাবে।")
        return

    # 1. Verify Bot is Admin
    try:
        bot_member = await bot.get_chat_member(chat.id, bot.id)
    except Exception as e:
        await message.answer(f"❌ বট পারমিশন যাচাই করতে পারেনি: <code>{html.escape(str(e))}</code>\nবটকে চ্যানেলে এডমিন করুন এবং আবার চেষ্টা করুন।", parse_mode="HTML")
        return

    if bot_member.status not in ["administrator", "creator"]:
        add_url = f"https://t.me/{bot_info.username}?startchannel=true&admin=post_messages+edit_messages+delete_messages"
        admin_kb = InlineKeyboardMarkup(inline_keyboard=[
            [make_custom_button(text="📢 বটকে এখনই এডমিন করুন ➔" if lang == "bn" else "📢 Add Bot as Admin Now ➔", url=add_url, custom_emoji_id=ADD_CHANNEL_CUSTOM_EMOJI_ID)],
            [InlineKeyboardButton(text="❌ বাতিল / Cancel", callback_data="menu_my_channels")]
        ])
        await message.answer(
            f"⚠️ <b>বট এখনও এই চ্যানেলের Administrator নয়!</b>\n\n"
            f"চ্যানেল: <b>{html.escape(chat.title or '')}</b>\n\n"
            "পোস্ট করার জন্য বটকে অবশ্যই এডমিন হতে হবে। নিচের বাটনে চাপ দিয়ে বটকে এডমিন করুন এবং তারপর আবার ইউজারনেম পাঠান:",
            reply_markup=admin_kb,
            parse_mode="HTML"
        )
        return

    can_post = getattr(bot_member, "can_post_messages", True)
    if not can_post:
        await message.answer(
            f"⚠️ <b>'Post Messages' অনুমতি বন্ধ আছে!</b>\n\n"
            f"চ্যানেল: <b>{html.escape(chat.title or '')}</b>\n\n"
            "বট এডমিন আছে কিন্তু চ্যানেলে মেসেজ পোস্ট করার পারমিশন দেওয়া হয়নি। "
            "চ্যানেল সেটিংসে গিয়ে Post Messages চালু করুন এবং আবার পাঠান:",
            parse_mode="HTML"
        )
        return

    # 2. Verify User is Admin/Owner of the Channel (Strict Security Isolation)
    try:
        user_member = await bot.get_chat_member(chat.id, user_id)
        is_user_admin = user_member.status in ["administrator", "creator"]
    except Exception:
        is_user_admin = False

    if not is_user_admin:
        await message.answer(
            f"⛔ <b>অননুমোদিত চ্যানেল / Access Denied!</b>\n\n"
            f"আপনি <b>{html.escape(chat.title or '')}</b> চ্যানেলের এডমিন বা মালিক নন!\n"
            "নিরাপত্তার স্বার্থে অন্যের চ্যানেল নিজের একাউন্টে যুক্ত করা নিষিদ্ধ।",
            parse_mode="HTML"
        )
        return

    # All checks passed! Save without errors ("kono bul cara add hoi")
    await save_channel(
        chat_id=chat.id,
        title=chat.title or "Untitled Channel",
        username=chat.username,
        added_by=user_id
    )
    await set_channel_status(chat.id, 1)
    await record_user_channel_access(user_id, chat.id)
    await state.clear()

    chan_title = html.escape(chat.title or "Untitled")
    success_text = (
        "✅ <b>চ্যানেল কোনো ভুল ছাড়াই সফলভাবে যুক্ত হয়েছে!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📢 <b>চ্যানেল:</b> {chan_title}\n"
        f"🆔 <b>আইডি:</b> <code>{chat.id}</code>\n"
        f"🔗 <b>ইউজারনেম:</b> @{chat.username or 'N/A'}\n"
        "🟢 <b>স্ট্যাটাস:</b> সক্রিয় ও ভেরিফাইড (Active & Verified)\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "এখন আপনি '📢 Added Channels' তালিকায় এই চ্যানেল দেখতে পাবেন এবং যেকোনো সময় পোল পরিচালনা করতে পারবেন।"
        if lang == "bn" else
        "✅ <b>Channel Connected Successfully Without Any Errors!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📢 <b>Title:</b> {chan_title}\n"
        f"🆔 <b>ID:</b> <code>{chat.id}</code>\n"
        f"🔗 <b>Username:</b> @{chat.username or 'N/A'}\n"
        "🟢 <b>Status:</b> Active & Verified\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "You can now manage this channel and create polls anytime."
    )

    success_kb = InlineKeyboardMarkup(inline_keyboard=[
        [make_custom_button(text="📢 Added Channels / যুক্ত চ্যানেলসমূহ", callback_data="menu_my_channels", custom_emoji_id=ADDED_CHANNELS_CUSTOM_EMOJI_ID)],
        [InlineKeyboardButton(text="📊 এই চ্যানেলে পোল দিন / Create Poll Here", callback_data=f"chan_create_poll:{chat.id}")],
        [make_custom_button(text="🏠 মূল মেনু / Main Menu", callback_data="menu_back_main", custom_emoji_id=START_MENU_CUSTOM_EMOJI_ID)]
    ])

    await message.answer(success_text, reply_markup=success_kb, parse_mode="HTML")
