import html
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from bot.config import ADMIN_IDS
from bot.database.db import (
    get_user_polls, get_poll, get_candidates, end_poll, get_user_language,
    get_button_icon_style, get_poll_parts, update_poll_contact, set_user_default_contact,
    delete_poll_by_id, delete_user_ended_polls
)
from bot.keyboards.inline import (
    build_poll_manage_keyboard, build_poll_keyboard,
    build_winner_announcement_choice_keyboard,
    make_custom_button, CREATE_POLL_CUSTOM_EMOJI_ID, MY_POLLS_CUSTOM_EMOJI_ID,
    START_MENU_CUSTOM_EMOJI_ID, POLL_ACTIVE_CUSTOM_EMOJI_ID, POLL_ENDED_CUSTOM_EMOJI_ID
)
from bot.templates import (
    render_poll_card, render_poll_cta, format_datetime_readable, format_winners_display,
    render_poll_ended, render_winner_announcement, render_custom_winner_announcement,
    strip_tg_emoji_tags, safe_bot_edit_message, safe_edit_message, safe_send_message
)

router = Router()

_announcing_polls = set()

class PollManagementState(StatesGroup):
    waiting_for_contact = State()

class WinnerAnnouncementState(StatesGroup):
    waiting_for_custom_text = State()

@router.message(Command("mypolls"))
async def cmd_mypolls(message: Message, state: FSMContext = None):
    if state:
        await state.clear()
    await show_user_polls(message.from_user.id, message)

cmd_my_polls = cmd_mypolls

@router.callback_query(F.data == "menu_my_polls")
async def cb_mypolls(callback: CallbackQuery):
    await callback.answer()
    await show_user_polls(callback.from_user.id, callback.message, is_callback=True)

async def show_user_polls(user_id: int, message_or_cb, is_callback: bool = False):
    lang = await get_user_language(user_id)
    polls = await get_user_polls(user_id)
    if not polls:
        text = (
            "<b>No Polls Found</b>\n\n"
            "You haven't created any polls yet.\n"
            "Type /newpoll or tap below to create one."
            if lang == "en" else
            "<b>কোনো পোল পাওয়া যায়নি</b>\n\n"
            "আপনি এখনও কোনো পোল তৈরি করেননি।\n"
            "নতুন পোল তৈরি করতে নিচের বাটনে চাপুন:"
        )
        create_btn = "Create New Poll" if lang == "en" else "নতুন পোল তৈরি করুন"
        back_btn = "🔙 Main Menu" if lang == "en" else "🔙 মূল মেনু"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [make_custom_button(text=create_btn, callback_data="menu_create_poll", custom_emoji_id=CREATE_POLL_CUSTOM_EMOJI_ID)],
            [make_custom_button(text=back_btn, callback_data="menu_back_main", custom_emoji_id=START_MENU_CUSTOM_EMOJI_ID)]
        ])
        if is_callback:
            await message_or_cb.edit_text(text, reply_markup=kb, parse_mode="HTML")
        else:
            await message_or_cb.answer(text, reply_markup=kb, parse_mode="HTML")
        return

    buttons = []
    has_ended = any(p.get("status") != "active" for p in polls)

    # Cap to latest 25 polls to ensure keyboard payload fits within Telegram size limits
    display_polls = polls[:25]
    for p in display_polls:
        is_active = (p["status"] == "active")
        status_emoji_id = POLL_ACTIVE_CUSTOM_EMOJI_ID if is_active else POLL_ENDED_CUSTOM_EMOJI_ID
        v_label = "votes" if lang == "en" else "ভোট"
        clean_title = strip_tg_emoji_tags(p.get("title") or "").strip()
        btn_text = f"#{p['poll_id']}: {clean_title[:24]} ({p.get('total_votes') or 0} {v_label})"
        buttons.append([make_custom_button(text=btn_text, callback_data=f"view_poll:{p['poll_id']}", custom_emoji_id=status_emoji_id)])

    if has_ended:
        del_ended_btn = "🗑️ Delete Ended Polls" if lang == "en" else "🗑️ সমাপ্ত পোলগুলো মুছুন"
        buttons.append([InlineKeyboardButton(text=del_ended_btn, callback_data="del_all_ended_ask")])

    back_text = "🔙 Main Menu" if lang == "en" else "🔙 মূল মেনু"
    buttons.append([make_custom_button(text=back_text, callback_data="menu_back_main", custom_emoji_id=START_MENU_CUSTOM_EMOJI_ID)])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    auto_del_note = (
        "💡 <i>Ended polls are automatically cleared after 2 days.</i>"
        if lang == "en" else
        "💡 <i>সমাপ্ত পোলগুলো ২ দিন (৪৮ ঘণ্টা) পর স্বয়ংক্রিয়ভাবে মুছে যায়।</i>"
    )
    count_note = f"\n<i>(Showing latest 25 of {len(polls)} polls)</i>" if len(polls) > 25 else ""
    text = (
        f"<b>Your Created Polls</b>{count_note}\n\n"
        f"Select a poll to view live stats or manage:\n\n"
        f"{auto_del_note}"
        if lang == "en" else
        f"<b>আপনার তৈরি করা পোলসমূহ</b>{count_note}\n\n"
        f"বিস্তারিত দেখতে এবং নিয়ন্ত্রণ করতে পোলে ক্লিক করুন:\n\n"
        f"{auto_del_note}"
    )

    if is_callback:
        await safe_edit_message(message_or_cb, text, reply_markup=kb, parse_mode="HTML")
    else:
        await safe_send_message(message_or_cb.bot, message_or_cb.chat.id, text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("view_poll:"))
async def cb_view_poll(callback: CallbackQuery):
    await callback.answer()  # Immediate answer prevents double-click spinning
    user_id = callback.from_user.id
    lang = await get_user_language(user_id)
    poll_id = int(callback.data.split(":")[1])
    poll = await get_poll(poll_id)
    if not poll or (poll["creator_id"] != user_id and user_id not in ADMIN_IDS):
        err = "Poll not found!" if lang == "en" else "পোলটি পাওয়া যায়নি বা দেখার অনুমতি নেই!"
        await callback.answer(err, show_alert=True)
        return

    candidates = await get_candidates(poll_id)
    total_votes = sum(c["votes_count"] for c in candidates)

    cand_lines = []
    for c in candidates:
        pct = (c["votes_count"] / total_votes * 100) if total_votes > 0 else 0
        v_word = "votes" if lang == "en" else "ভোট"
        cand_lines.append(f"• <b>{html.escape(c['name'])}</b>: <code>{c['votes_count']}</code> {v_word} ({pct:.1f}%)")

    ends_at_val = poll.get("ends_at")
    created_at_val = poll.get("created_at")
    start_disp = format_datetime_readable(created_at_val)
    end_disp = format_datetime_readable(ends_at_val) if ends_at_val else None

    if ends_at_val:
        timer_info_en = (
            f"⏱️ <b>Schedule:</b>\n"
            f"   🟢 <b>Start:</b> <code>{start_disp}</code>\n"
            f"   🔴 <b>End:</b> <code>{end_disp}</code>"
        )
        timer_info_bn = (
            f"⏱️ <b>সময়সূচি:</b>\n"
            f"   🟢 <b>শুরু:</b> <code>{start_disp}</code>\n"
            f"   🔴 <b>শেষ:</b> <code>{end_disp}</code>"
        )
    else:
        timer_info_en = (
            f"⏱️ <b>Schedule:</b>\n"
            f"   🟢 <b>Start:</b> <code>{start_disp}</code>\n"
            f"   ♾️ <b>End:</b> <code>Manual Closure</code>"
        )
        timer_info_bn = (
            f"⏱️ <b>সময়সূচি:</b>\n"
            f"   🟢 <b>শুরু:</b> <code>{start_disp}</code>\n"
            f"   ♾️ <b>সমাপ্তি:</b> <code>ম্যানুয়াল সমাপ্তি</code>"
        )

    parts = await get_poll_parts(poll_id)
    has_parts = len(parts) > 1
    part_buttons = []
    part_summary_lines = []
    if has_parts:
        for p in parts:
            p_num = p.get("part_number") or 1
            is_p_act = (p["status"] == "active")
            p_emoji_id = POLL_ACTIVE_CUSTOM_EMOJI_ID if is_p_act else POLL_ENDED_CUSTOM_EMOJI_ID
            p_status = f'<tg-emoji emoji-id="{p_emoji_id}">{"🔵" if is_p_act else "🔴"}</tg-emoji>'
            p_label = f'{"🔵" if is_p_act else "🔴"} Part {p_num}' if p["poll_id"] != poll_id else f"👉 Part {p_num}"
            part_buttons.append((p["poll_id"], p_label))
            part_summary_lines.append(f"• <b>Part {p_num} (ID #{p['poll_id']}):</b> {p_status} {p['title']}")

    parts_section_en = ("\n\n📑 <b>Connected Parts:</b>\n" + "\n".join(part_summary_lines)) if has_parts else ""
    parts_section_bn = ("\n\n📑 <b>সংযুক্ত পর্বসমূহ:</b>\n" + "\n".join(part_summary_lines)) if has_parts else ""

    contact_val = poll.get("contact_username") or ""
    contact_disp_en = f"@{contact_val}" if contact_val else "Not Set"
    contact_disp_bn = f"@{contact_val}" if contact_val else "সেট করা নেই"

    if lang == "en":
        status_str = f'<tg-emoji emoji-id="{POLL_ACTIVE_CUSTOM_EMOJI_ID}">🔵</tg-emoji> Active' if poll["status"] == "active" else f'<tg-emoji emoji-id="{POLL_ENDED_CUSTOM_EMOJI_ID}">🔴</tg-emoji> Ended'
        details = (
            f"📊 <b>Poll Details (ID: #{poll['poll_id']})</b>\n\n"
            f"📌 <b>Title:</b> {poll['title']}\n"
            f"📢 <b>Channel:</b> {html.escape(poll.get('target_chat_title') or 'N/A')}\n"
            f"⏳ <b>Status:</b> {status_str}\n"
            f"📩 <b>Giveaway Host:</b> <code>{contact_disp_en}</code>\n"
            f"{timer_info_en}\n"
            f"🗳️ <b>Total Votes:</b> <code>{total_votes}</code>"
            f"{parts_section_en}\n\n"
            f"👥 <b>Current Standings:</b>\n" + "\n".join(cand_lines)
        )
    else:
        status_str = f'<tg-emoji emoji-id="{POLL_ACTIVE_CUSTOM_EMOJI_ID}">🔵</tg-emoji> সক্রিয়' if poll["status"] == "active" else f'<tg-emoji emoji-id="{POLL_ENDED_CUSTOM_EMOJI_ID}">🔴</tg-emoji> সমাপ্ত'
        details = (
            f"📊 <b>পোলের বিবরণ (ID: #{poll['poll_id']})</b>\n\n"
            f"📌 <b>শিরোনাম:</b> {poll['title']}\n"
            f"📢 <b>চ্যানেল:</b> {html.escape(poll.get('target_chat_title') or 'N/A')}\n"
            f"⏳ <b>অবস্থা:</b> {status_str}\n"
            f"📩 <b>গিভওয়ে হোস্ট:</b> <code>{contact_disp_bn}</code>\n"
            f"{timer_info_bn}\n"
            f"🗳️ <b>সর্বমোট ভোট:</b> <code>{total_votes}</code>"
            f"{parts_section_bn}\n\n"
            f"👥 <b>প্রার্থীদের ফলাফল:</b>\n" + "\n".join(cand_lines)
        )

    is_active = poll["status"] == "active"
    await callback.message.edit_text(
        details,
        reply_markup=build_poll_manage_keyboard(
            poll_id,
            is_active,
            lang=lang,
            has_parts=has_parts,
            part_buttons=part_buttons
        ),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("end_poll:"))
async def cb_end_poll(callback: CallbackQuery):
    user_id = callback.from_user.id
    lang = await get_user_language(user_id)
    poll_id = int(callback.data.split(":")[1])
    poll = await get_poll(poll_id)

    if not poll or (poll["creator_id"] != user_id and user_id not in ADMIN_IDS):
        msg = "You don't have permission to end this poll!" if lang == "en" else "আপনার এই পোল সমাপ্ত করার অনুমতি নেই!"
        await callback.answer(msg, show_alert=True)
        return

    if poll["status"] != "active":
        msg = "Poll is already ended!" if lang == "en" else "পোলটি ইতোমধ্যে সমাপ্ত করা হয়েছে!"
        await callback.answer(msg, show_alert=True)
        return

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.answer("⏳ Ending poll... / পোল সমাপ্ত করা হচ্ছে...")

    poll_data = await end_poll(poll_id)
    bot = callback.bot
    bot_info = await bot.get_me()

    candidates = poll_data.get("candidates", [])
    winner = poll_data.get("winner")
    top_winners = poll_data.get("top_winners") or ([winner] if winner and winner.get('votes_count', 0) > 0 else [])
    total_votes = sum(c["votes_count"] for c in candidates)

    winner_text = format_winners_display(top_winners, lang=lang)
    channel_lang = poll.get("language") or lang
    winner_text_channel = format_winners_display(top_winners, lang=channel_lang)

    # 1. Update Channel Message to closed state
    if poll.get("channel_message_id") and poll.get("target_chat_id"):
        try:
            cta_text, cta_url = await render_poll_cta(bot_info.username, lang=channel_lang, creator_id=user_id)
            icon_style = poll.get("icon_style") or await get_button_icon_style()
            closed_kb = build_poll_keyboard(poll_id, candidates, bot_info.username, is_closed=True, cta_text=cta_text, cta_url=cta_url, icon_style=icon_style)
            results_channel_text = await render_poll_ended(
                title=poll['title'],
                winner=winner_text_channel,
                votes=total_votes,
                bot_username=bot_info.username,
                lang=channel_lang,
                created_at=poll.get("created_at"),
                ended_at=poll_data.get("ended_at"),
                creator_id=user_id,
                contact_username=poll.get("contact_username")
            )
            await safe_bot_edit_message(
                bot=bot,
                chat_id=poll["target_chat_id"],
                message_id=poll["channel_message_id"],
                text=results_channel_text,
                reply_markup=closed_kb,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        except Exception:
            pass

    # 2. Ask Creator whether to send Auto Winner list, Custom announcement, or Skip
    channel_name = html.escape(poll.get('target_chat_title') or 'Your Channel')
    if lang == "en":
        prompt_text = (
            f"🏆 <b>Poll #{poll_id} Ended Successfully!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>Title:</b> {html.escape(poll['title'])}\n"
            f"📢 <b>Channel:</b> {channel_name}\n\n"
            f"{winner_text}\n\n"
            f"🗳️ <b>Total Votes:</b> <code>{total_votes}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📢 <b>Would you like to post a winner announcement to the channel?</b>\n\n"
            f"• <b>Auto Announcement:</b> Bot sends official winner list with medals.\n"
            f"• <b>Custom Announcement:</b> Write your own message (Brand credit & button are preserved automatically)."
        )
    elif lang == "hi":
        prompt_text = (
            f"🏆 <b>पोल #{poll_id} सफलतापूर्वक समाप्त हुआ!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>शीर्षक:</b> {html.escape(poll['title'])}\n"
            f"📢 <b>चैनल:</b> {channel_name}\n\n"
            f"{winner_text}\n\n"
            f"🗳️ <b>कुल वोट:</b> <code>{total_votes}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📢 <b>क्या आप चैनल में विजेता घोषणा भेजना चाहते हैं?</b>\n\n"
            f"• <b>ऑटो घोषणा:</b> बॉट सीधे मेडल और नामों के साथ पोस्ट भेजेगा।\n"
            f"• <b>कस्टम घोषणा:</b> अपना संदेश लिखें (बॉट क्रेडिट और लिंक सुरक्षित रहेगा)।"
        )
    else:
        prompt_text = (
            f"🏆 <b>পোল #{poll_id} সফলভাবে সমাপ্ত হয়েছে!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>শিরোনাম:</b> {html.escape(poll['title'])}\n"
            f"📢 <b>চ্যানেল:</b> {channel_name}\n\n"
            f"{winner_text}\n\n"
            f"🗳️ <b>সর্বমোট ভোট:</b> <code>{total_votes}</code> টি\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📢 <b>আপনি কি চ্যানেলে বিজয়ী ঘোষণা মেসেজ পাঠাতে চান?</b>\n\n"
            f"• <b>অটো ঘোষণা:</b> বট স্বয়ংক্রিয়ভাবে মেডেল ও ভোটসহ তালিকা পাঠাবে।\n"
            f"• <b>কাস্টম ঘোষণা:</b> নিজের মতো করে মেসেজ লিখুন (বট ক্রেডিট ও বাটন লিংক যুক্ত থাকবে)।"
        )

    await callback.message.edit_text(
        prompt_text,
        reply_markup=build_winner_announcement_choice_keyboard(poll_id, lang=lang),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("post_winner_auto:"))
async def cb_post_winner_auto(callback: CallbackQuery):
    user_id = callback.from_user.id
    lang = await get_user_language(user_id)
    poll_id = int(callback.data.split(":")[1])

    if poll_id in _announcing_polls:
        await callback.answer(
            "⏳ Announcement already being sent! / ইতোমধ্যে চ্যানেলে পাঠানো হচ্ছে!",
            show_alert=True
        )
        return

    _announcing_polls.add(poll_id)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.answer("⏳ Posting winner announcement... / চ্যানেলে ঘোষণা পাঠানো হচ্ছে...")

    try:
        poll = await get_poll(poll_id)

        if not poll or (poll["creator_id"] != user_id and user_id not in ADMIN_IDS):
            await callback.answer("Access denied!", show_alert=True)
            return

        candidates = await get_candidates(poll_id)
        w_count = int(poll.get("winner_count") or 1)
        voted = [c for c in candidates if c.get("votes_count", 0) > 0]
        top_winners = voted[:w_count] if voted else candidates[:w_count]
        total_votes = sum(c.get("votes_count", 0) for c in candidates)

        channel_lang = poll.get("language") or lang
        bot_info = await callback.bot.get_me()

        announcement_text = await render_winner_announcement(
            title=poll["title"],
            top_winners=top_winners,
            total_votes=total_votes,
            bot_username=bot_info.username,
            lang=channel_lang,
            creator_id=user_id,
            contact_username=poll.get("contact_username")
        )

        cta_text, cta_url = await render_poll_cta(bot_info.username, lang=channel_lang, creator_id=user_id)
        cta_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=cta_text, url=cta_url)]
        ])

        try:
            await callback.bot.send_message(
                chat_id=poll["target_chat_id"],
                text=announcement_text,
                reply_markup=cta_kb,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        except Exception as e:
            err_str = str(e).lower()
            if "custom emoji" in err_str or "entity" in err_str:
                clean_text = strip_tg_emoji_tags(announcement_text)
                try:
                    await callback.bot.send_message(
                        chat_id=poll["target_chat_id"],
                        text=clean_text,
                        reply_markup=cta_kb,
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                except Exception as e2:
                    err_msg = f"Failed to send announcement to channel: {e2}" if lang == "en" else f"চ্যানেলে মেসেজ পাঠানো যায়নি: {e2}"
                    await callback.answer(err_msg, show_alert=True)
                    return
            else:
                err_msg = f"Failed to send announcement to channel: {e}" if lang == "en" else f"চ্যানেলে মেসেজ পাঠানো যায়নি: {e}"
                await callback.answer(err_msg, show_alert=True)
                return

        success_msg = (
            f"✅ <b>Official Winner Announcement Posted to Channel!</b>\n\n"
            f"The winner list with medals and brand credit has been posted to <b>{html.escape(poll.get('target_chat_title') or '')}</b>."
            if lang == "en" else
            f"✅ <b>চ্যানেলে স্বয়ংক্রিয় বিজয়ী ঘোষণা সফলভাবে পোস্ট করা হয়েছে!</b>\n\n"
            f"মেডেল, ভোট ও ব্র্যান্ড ক্রেডিটসহ বিজয়ী তালিকা <b>{html.escape(poll.get('target_chat_title') or '')}</b> চ্যানেলে পাঠানো হয়েছে।"
        )
        back_kb = InlineKeyboardMarkup(inline_keyboard=[
            [make_custom_button(text="My Polls / আমার পোল", callback_data="menu_my_polls", custom_emoji_id=MY_POLLS_CUSTOM_EMOJI_ID)],
            [make_custom_button(text="🔙 Main Menu / মূল মেনু", callback_data="menu_back_main", custom_emoji_id=START_MENU_CUSTOM_EMOJI_ID)]
        ])
        await callback.message.edit_text(success_msg, reply_markup=back_kb, parse_mode="HTML")
        await callback.answer("Announcement sent!" if lang == "en" else "ঘোষণা পাঠানো হয়েছে!")
    finally:
        _announcing_polls.discard(poll_id)

@router.callback_query(F.data.startswith("post_winner_custom:"))
async def cb_post_winner_custom(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass
    user_id = callback.from_user.id
    lang = await get_user_language(user_id)
    poll_id = int(callback.data.split(":")[1])
    poll = await get_poll(poll_id)

    if not poll or (poll["creator_id"] != user_id and user_id not in ADMIN_IDS):
        await callback.answer("Access denied!", show_alert=True)
        return

    await state.set_state(WinnerAnnouncementState.waiting_for_custom_text)
    await state.update_data(poll_id=poll_id)

    if lang == "en":
        prompt = (
            f"✏️ <b>Write Your Custom Winner Announcement:</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📢 <b>Target Channel:</b> {html.escape(poll.get('target_chat_title') or '')}\n\n"
            f"Type and send your custom congratulatory message below.\n\n"
            f"💡 <i>Note: Your brand watermark (Powered by) and clickable CTA button will automatically be attached to the bottom of your post.</i>\n\n"
            f"👉 Type /cancel to cancel."
        )
    elif lang == "hi":
        prompt = (
            f"✏️ <b>अपना कस्टम विजेता संदेश लिखें:</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📢 <b>लक्ष्य चैनल:</b> {html.escape(poll.get('target_chat_title') or '')}\n\n"
            f"नीचे अपना बधाई संदेश लिखकर भेजें।\n\n"
            f"💡 <i>नोट: आपके पोस्ट के नीचे आपका ब्रांड वॉटरमार्क (Powered by) और क्लिक करने योग्य बटन स्वचालित रूप से जुड़ा रहेगा।</i>\n\n"
            f"👉 रद्द करने के लिए /cancel टाइप करें।"
        )
    else:
        prompt = (
            f"✏️ <b>আপনার কাস্টম বিজয়ী ঘোষণা লিখুন:</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📢 <b>টার্গেট চ্যানেল:</b> {html.escape(poll.get('target_chat_title') or '')}\n\n"
            f"আপনার চ্যানেলে যে কাস্টম মেসেজ বা শুভেচ্ছা পোস্ট পাঠাতে চান, তা লিখে নিচে সেন্ড করুন।\n\n"
            f"💡 <i>নোট: আপনার মেসেজের নিচে স্বয়ংক্রিয়ভাবে আপনার ব্র্যান্ড ক্রেডিট (Powered by) এবং ক্লিকেবল বাটন লিংক যুক্ত থাকবে।</i>\n\n"
            f"👉 বাতিল করতে /cancel কমান্ড দিন।"
        )

    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Cancel / বাতিল", callback_data=f"post_winner_skip:{poll_id}")]
    ])
    await callback.message.edit_text(prompt, reply_markup=cancel_kb, parse_mode="HTML")
    await callback.answer()

@router.message(WinnerAnnouncementState.waiting_for_custom_text)
async def handle_custom_winner_text(message: Message, state: FSMContext):
    user_id = message.from_user.id
    lang = await get_user_language(user_id)
    data = await state.get_data()
    poll_id = data.get("poll_id")
    await state.clear()

    raw_text = (message.text or "").strip()
    if raw_text.lower() in ["/cancel", "cancel", "বাতিল"]:
        await message.answer("❌ Cancelled / বাতিল করা হয়েছে।")
        return
    if raw_text.lower().startswith("/mypolls"):
        await show_user_polls(user_id, message)
        return

    if not poll_id:
        await message.answer("Session expired. Please try again.")
        return

    poll = await get_poll(poll_id)
    if not poll or (poll["creator_id"] != user_id and user_id not in ADMIN_IDS):
        await message.answer("Access denied.")
        return

    custom_text = message.html_text or html.escape(message.text or "")
    if custom_text.strip().lower() in ["/cancel", "cancel", "বাতিল"]:
        cancel_msg = "❌ Announcement cancelled." if lang == "en" else "❌ ঘোষণা পোস্ট বাতিল করা হয়েছে।"
        await message.answer(cancel_msg)
        return

    if not custom_text.strip():
        await message.answer("Please send a valid text message.")
        return

    bot_info = await message.bot.get_me()
    channel_lang = poll.get("language") or lang

    final_post_text = await render_custom_winner_announcement(
        custom_text=custom_text,
        bot_username=bot_info.username,
        creator_id=user_id,
        contact_username=poll.get("contact_username")
    )

    cta_text, cta_url = await render_poll_cta(bot_info.username, lang=channel_lang, creator_id=user_id)
    cta_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=cta_text, url=cta_url)]
    ])

    try:
        await message.bot.send_message(
            chat_id=poll["target_chat_id"],
            text=final_post_text,
            reply_markup=cta_kb,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    except Exception as e:
        err_str = str(e).lower()
        if "custom emoji" in err_str or "entity" in err_str:
            clean_text = strip_tg_emoji_tags(final_post_text)
            try:
                await message.bot.send_message(
                    chat_id=poll["target_chat_id"],
                    text=clean_text,
                    reply_markup=cta_kb,
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
            except Exception as e2:
                err_msg = f"❌ Failed to send message to channel: {e2}" if lang == "en" else f"❌ চ্যানেলে মেসেজ পাঠানো যায়নি: {e2}"
                await message.answer(err_msg)
                return
        else:
            err_msg = f"❌ Failed to send message to channel: {e}" if lang == "en" else f"❌ চ্যানেলে মেসেজ পাঠানো যায়নি: {e}"
            await message.answer(err_msg)
            return

    success_msg = (
        f"✅ <b>Custom Announcement Posted to Channel!</b>\n\n"
        f"Your custom text with brand credit and link button has been posted to <b>{html.escape(poll.get('target_chat_title') or '')}</b>."
        if lang == "en" else
        f"✅ <b>কাস্টম বিজয়ী ঘোষণা চ্যানেলে সফলভাবে পোস্ট করা হয়েছে!</b>\n\n"
        f"ব্র্যান্ড ক্রেডিট ও লিংক বাটনসহ আপনার মেসেজটি <b>{html.escape(poll.get('target_chat_title') or '')}</b> চ্যানেলে পাঠানো হয়েছে।"
    )
    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [make_custom_button(text="My Polls / আমার পোল", callback_data="menu_my_polls", custom_emoji_id=MY_POLLS_CUSTOM_EMOJI_ID)],
        [make_custom_button(text="🔙 Main Menu / মূল মেনু", callback_data="menu_back_main", custom_emoji_id=START_MENU_CUSTOM_EMOJI_ID)]
    ])
    await message.answer(success_msg, reply_markup=back_kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("post_winner_skip:"))
async def cb_post_winner_skip(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass
    await state.clear()
    user_id = callback.from_user.id
    lang = await get_user_language(user_id)
    poll_id = int(callback.data.split(":")[1])

    skip_msg = (
        f"ℹ️ <b>Poll #{poll_id} closed without channel announcement post.</b>\n"
        f"Channel poll message buttons remain disabled."
        if lang == "en" else
        f"ℹ️ <b>পোল #{poll_id} সমাপ্ত করা হয়েছে (চ্যানেলে আলাদা ঘোষণা পাঠানো হয়নি)।</b>\n"
        f"চ্যানেলে মূল পোলের বাটনগুলো ক্লোজ রাখা হয়েছে।"
    )
    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [make_custom_button(text="My Polls / আমার পোল", callback_data="menu_my_polls", custom_emoji_id=MY_POLLS_CUSTOM_EMOJI_ID)],
        [make_custom_button(text="🔙 Main Menu / মূল মেনু", callback_data="menu_back_main", custom_emoji_id=START_MENU_CUSTOM_EMOJI_ID)]
    ])
    try:
        await callback.message.edit_text(skip_msg, reply_markup=back_kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(skip_msg, reply_markup=back_kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("end_all_parts:"))
async def cb_end_all_parts(callback: CallbackQuery):
    user_id = callback.from_user.id
    lang = await get_user_language(user_id)
    poll_id = int(callback.data.split(":")[1])
    poll = await get_poll(poll_id)

    if not poll or (poll["creator_id"] != user_id and user_id not in ADMIN_IDS):
        msg = "You don't have permission to end this poll!" if lang == "en" else "আপনার এই পোল সমাপ্ত করার অনুমতি নেই!"
        await callback.answer(msg, show_alert=True)
        return

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.answer("⏳ Ending all parts... / সকল পর্ব সমাপ্ত করা হচ্ছে...")

    parts = await get_poll_parts(poll_id)
    bot = callback.bot
    bot_info = await bot.get_me()

    ended_count = 0
    all_candidates = []
    for part in parts:
        if part["status"] == "active":
            p_data = await end_poll(part["poll_id"])
            ended_count += 1
            if part.get("channel_message_id") and part.get("target_chat_id"):
                try:
                    candidates = p_data.get("candidates", [])
                    winner = p_data.get("winner")
                    top_winners = p_data.get("top_winners") or ([winner] if winner and winner.get('votes_count', 0) > 0 else [])
                    total_votes = sum(c["votes_count"] for c in candidates)
                    channel_lang = part.get("language") or lang
                    winner_text_chan = format_winners_display(top_winners, lang=channel_lang)

                    cta_text, cta_url = await render_poll_cta(bot_info.username, lang=channel_lang, creator_id=user_id)
                    icon_style = part.get("icon_style") or await get_button_icon_style()
                    closed_kb = build_poll_keyboard(part["poll_id"], candidates, bot_info.username, is_closed=True, cta_text=cta_text, cta_url=cta_url, icon_style=icon_style)
                    results_channel_text = await render_poll_ended(
                        title=part['title'],
                        winner=winner_text_chan,
                        votes=total_votes,
                        bot_username=bot_info.username,
                        lang=channel_lang,
                        created_at=part.get("created_at"),
                        ended_at=p_data.get("ended_at"),
                        creator_id=user_id,
                        contact_username=part.get("contact_username") or poll.get("contact_username")
                    )
                    await safe_bot_edit_message(
                        bot=bot,
                        chat_id=part["target_chat_id"],
                        message_id=part["channel_message_id"],
                        text=results_channel_text,
                        reply_markup=closed_kb,
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                except Exception:
                    pass

    # Ask creator whether to post announcement for the series
    channel_name = html.escape(poll.get('target_chat_title') or 'Your Channel')
    prompt_text = (
        f"✅ <b>All {ended_count} connected parts ended!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>Title:</b> {html.escape(poll['title'])}\n"
        f"📢 <b>Channel:</b> {channel_name}\n\n"
        f"📢 <b>Would you like to post an official winner announcement to the channel?</b>"
        if lang == "en" else
        f"✅ <b>সকল {ended_count} টি সংযুক্ত পর্ব সফলভাবে সমাপ্ত করা হয়েছে!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>শিরোনাম:</b> {html.escape(poll['title'])}\n"
        f"📢 <b>চ্যানেল:</b> {channel_name}\n\n"
        f"📢 <b>আপনি কি চ্যানেলে চূড়ান্ত বিজয়ী ঘোষণা মেসেজ পাঠাতে চান?</b>"
    )
    await callback.message.edit_text(
        prompt_text,
        reply_markup=build_winner_announcement_choice_keyboard(poll_id, lang=lang),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("poll_contact:"))
async def cb_poll_contact(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass
    user_id = callback.from_user.id
    lang = await get_user_language(user_id)
    poll_id = int(callback.data.split(":")[1])
    poll = await get_poll(poll_id)
    if not poll or (poll["creator_id"] != user_id and user_id not in ADMIN_IDS):
        await callback.answer("Access denied!", show_alert=True)
        return

    await state.set_state(PollManagementState.waiting_for_contact)
    await state.update_data(poll_id=poll_id)

    u_name = callback.from_user.username
    buttons = []
    if u_name:
        clean_u = u_name.lstrip("@")
        btn_self = f"👤 Use @{clean_u}" if lang == "en" else f"👤 ব্যবহার করুন: @{clean_u}"
        buttons.append([InlineKeyboardButton(text=btn_self, callback_data=f"poll_contact_self:{poll_id}:{clean_u}")])

    cancel_text = "❌ Cancel / বাতিল"
    buttons.append([InlineKeyboardButton(text=cancel_text, callback_data=f"view_poll:{poll_id}")])

    cur = f"@{poll.get('contact_username')}" if poll.get("contact_username") else "None"
    if lang == "en":
        txt = (
            f"📩 <b>Set Giveaway Host Contact ID (Poll #{poll_id}):</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Current Contact: <code>{cur}</code>\n\n"
            "Send your Telegram username (e.g. <code>@admin_username</code>). "
            "Contest winners will contact this ID to claim their giveaway prize!\n\n"
            "👉 Tap below or type your username:"
        )
    elif lang == "hi":
        txt = (
            f"📩 <b>गिवअवे होस्ट संपर्क आईडी सेट करें (Poll #{poll_id}):</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"वर्तमान संपर्क: <code>{cur}</code>\n\n"
            "अपना टेलीग्राम यूजरनेम भेजें (उदा. <code>@admin_username</code>)। "
            "विजेता अपना पुरस्कार प्राप्त करने के लिए इस आईडी पर संपर्क करेंगे!\n\n"
            "👉 नीचे टैप करें या अपना यूजरनेम लिखें:"
        )
    else:
        txt = (
            f"📩 <b>গিভওয়ে হোস্ট যোগাযোগ আইডি নির্ধারণ (পোল #{poll_id}):</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"বর্তমান কন্ট্যাক্ট: <code>{cur}</code>\n\n"
            "বিজয়ীরা পুরস্কার পাওয়ার জন্য যার সাথে যোগাযোগ করবে তার টেলিগ্রাম ইউজারনেম লিখে পাঠান (যেমন: <code>@admin_username</code>)।\n\n"
            "👉 নিচের বাটনে চাপুন বা ইউজারনেম লিখে পাঠান:"
        )
    await callback.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("poll_contact_self:"))
async def cb_poll_contact_self(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    parts = callback.data.split(":")
    poll_id = int(parts[1])
    contact = parts[2]
    user_id = callback.from_user.id
    lang = await get_user_language(user_id)

    await update_poll_contact(poll_id, contact)
    await set_user_default_contact(user_id, contact)

    toast = f"Contact ID updated to @{contact}" if lang == "en" else f"যোগাযোগ আইডি @{contact} সেট করা হয়েছে!"
    await callback.answer(toast, show_alert=True)
    callback.data = f"view_poll:{poll_id}"
    await cb_view_poll(callback)

@router.message(PollManagementState.waiting_for_contact)
async def process_poll_contact_text(message: Message, state: FSMContext):
    data = await state.get_data()
    poll_id = data.get("poll_id")
    await state.clear()
    user_id = message.from_user.id
    lang = await get_user_language(user_id)

    if not poll_id:
        await message.answer("Session expired.")
        return

    raw = (message.text or "").strip()
    if raw.lower() in ["/cancel", "cancel", "বাতিল"]:
        await message.answer("❌ Cancelled / বাতিল করা হয়েছে।")
        return
    if raw.lower().startswith("/mypolls"):
        await show_user_polls(user_id, message)
        return

    clean = raw.replace("https://t.me/", "").replace("t.me/", "").lstrip("@").strip()
    await update_poll_contact(poll_id, clean)
    if clean:
        await set_user_default_contact(user_id, clean)

    confirm_msg = (
        f"✅ <b>Giveaway Contact ID updated to @{clean}!</b>\n\n"
        f"Contest winners will be directed to contact <b>@{clean}</b> when this poll ends."
        if lang == "en" else
        f"✅ <b>গিভওয়ে যোগাযোগ আইডি সফলভাবে @{clean} নির্ধারণ করা হয়েছে!</b>\n\n"
        f"পোল শেষ হলে বিজয়ীরা পুরস্কার দাবি করতে সরাসরি <b>@{clean}</b> এর সাথে যোগাযোগ করতে পারবে।"
    )
    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 View Poll Details / পোলের বিবরণ", callback_data=f"view_poll:{poll_id}")],
        [InlineKeyboardButton(text="🔙 My Polls / আমার পোল", callback_data="menu_my_polls")]
    ])
    await message.answer(confirm_msg, reply_markup=back_kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("del_poll_ask:"))
async def cb_del_poll_ask(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    lang = await get_user_language(user_id)
    poll_id = int(callback.data.split(":")[1])
    poll = await get_poll(poll_id)
    if not poll or (poll["creator_id"] != user_id and user_id not in ADMIN_IDS):
        err = "Poll not found!" if lang == "en" else "পোলটি পাওয়া যায়নি বা দেখার অনুমতি নেই!"
        await callback.answer(err, show_alert=True)
        return

    text = (
        f"<b>Delete Poll #{poll_id}?</b>\n\n"
        f"Title: <b>{html.escape(poll['title'])}</b>\n\n"
        f"⚠️ Are you sure you want to permanently delete this poll from your list?"
        if lang == "en" else
        f"<b>পোল #{poll_id} মুছে ফেলতে চান?</b>\n\n"
        f"শিরোনাম: <b>{html.escape(poll['title'])}</b>\n\n"
        f"⚠️ আপনি কি নিশ্চিতভাবে এই পোলটি স্থায়ীভাবে তালিকা থেকে মুছে ফেলতে চান?"
    )
    yes_btn = "🗑️ Yes, Delete" if lang == "en" else "🗑️ হ্যাঁ, মুছুন"
    no_btn = "❌ Cancel" if lang == "en" else "❌ বাতিল"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=yes_btn, callback_data=f"del_poll_do:{poll_id}"),
            InlineKeyboardButton(text=no_btn, callback_data=f"view_poll:{poll_id}")
        ]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("del_poll_do:"))
async def cb_del_poll_do(callback: CallbackQuery):
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.answer()
    user_id = callback.from_user.id
    lang = await get_user_language(user_id)
    poll_id = int(callback.data.split(":")[1])

    c_id = None if user_id in ADMIN_IDS else user_id
    success = await delete_poll_by_id(poll_id, creator_id=c_id)
    if success:
        toast = "Poll deleted successfully." if lang == "en" else "পোলটি সফলভাবে মুছে ফেলা হয়েছে।"
        await callback.answer(toast, show_alert=True)
    else:
        toast = "Poll could not be deleted." if lang == "en" else "পোলটি মুছে ফেলা সম্ভব হয়নি।"
        await callback.answer(toast, show_alert=True)

    await show_user_polls(user_id, callback.message, is_callback=True)

@router.callback_query(F.data == "del_all_ended_ask")
async def cb_del_all_ended_ask(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    lang = await get_user_language(user_id)

    text = (
        "<b>Delete All Ended Polls?</b>\n\n"
        "⚠️ This will permanently remove all finished and closed polls from your dashboard. Active polls will not be affected.\n\n"
        "Are you sure?"
        if lang == "en" else
        "<b>সকল সমাপ্ত পোল মুছে ফেলতে চান?</b>\n\n"
        "⚠️ এটি আপনার তালিকার সকল সমাপ্ত বা বন্ধ হয়ে যাওয়া পোল স্থায়ীভাবে মুছে ফেলবে। সক্রিয় পোলগুলো অক্ষত থাকবে।\n\n"
        "আপনি কি নিশ্চিত?"
    )
    yes_btn = "🗑️ Yes, Delete Ended" if lang == "en" else "🗑️ হ্যাঁ, সমাপ্ত পোলগুলো মুছুন"
    no_btn = "❌ Cancel" if lang == "en" else "❌ বাতিল"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=yes_btn, callback_data="del_all_ended_do")],
        [InlineKeyboardButton(text=no_btn, callback_data="menu_my_polls")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "del_all_ended_do")
async def cb_del_all_ended_do(callback: CallbackQuery):
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.answer()
    user_id = callback.from_user.id
    lang = await get_user_language(user_id)

    count = await delete_user_ended_polls(user_id)
    toast = (
        f"{count} ended polls deleted."
        if lang == "en" else
        f"{count} টি সমাপ্ত পোল মুছে ফেলা হয়েছে।"
    )
    await callback.answer(toast, show_alert=True)
    await show_user_polls(user_id, callback.message, is_callback=True)


