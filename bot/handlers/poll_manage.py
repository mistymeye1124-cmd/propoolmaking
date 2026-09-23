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
    delete_poll_by_id, delete_user_ended_polls, add_candidates_to_poll, get_user_icon_style,
    get_multi_part_aggregated_results
)
from bot.handlers.poll_create import get_base_title
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
    waiting_for_new_candidates = State()

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
async def _handle_end_poll_unified(callback: CallbackQuery, poll_id: int):
    user_id = callback.from_user.id
    lang = await get_user_language(user_id)
    poll = await get_poll(poll_id)

    if not poll or (poll["creator_id"] != user_id and user_id not in ADMIN_IDS):
        msg = "You don't have permission to end this poll!" if lang == "en" else "আপনার এই পোল সমাপ্ত করার অনুমতি নেই!"
        await callback.answer(msg, show_alert=True)
        return

    parts = await get_poll_parts(poll_id)
    is_multi_part = len(parts) > 1
    any_active = any(p.get("status") == "active" for p in parts)
    if not any_active and poll.get("status") != "active":
        msg = "Poll is already ended!" if lang == "en" else "পোলটি ইতোমধ্যে সমাপ্ত করা হয়েছে!"
        await callback.answer(msg, show_alert=True)
        return

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.answer("⏳ Ending contest... / পোল সমাপ্ত করা হচ্ছে...")

    # Close all active connected parts simultaneously
    for p in parts:
        if p.get("status") == "active":
            await end_poll(p["poll_id"])

    bot = callback.bot
    bot_info = await bot.get_me()

    if is_multi_part:
        agg = await get_multi_part_aggregated_results(poll_id)
        top_winners = agg.get("top_winners", [])
        total_votes = agg.get("total_votes", 0)
        base_title = get_base_title(poll["title"])
    else:
        poll_data = await get_poll(poll_id)
        candidates = await get_candidates(poll_id)
        w_count = int(poll.get("winner_count") or 1)
        voted = [c for c in candidates if c.get("votes_count", 0) > 0]
        top_winners = voted[:w_count] if voted else candidates[:w_count]
        total_votes = sum(c.get("votes_count", 0) for c in candidates)
        base_title = poll["title"]

    winner_text = format_winners_display(top_winners, lang=lang, is_multi_part=is_multi_part)
    channel_lang = poll.get("language") or lang

    # 1. Update Channel Message to closed state for ALL connected parts
    for p in parts:
        if p.get("channel_message_id") and p.get("target_chat_id"):
            try:
                p_cands = await get_candidates(p["poll_id"])
                p_chan_lang = p.get("language") or channel_lang
                p_winner_text = format_winners_display(top_winners, lang=p_chan_lang, is_multi_part=is_multi_part)
                cta_text, cta_url = await render_poll_cta(bot_info.username, lang=p_chan_lang, creator_id=user_id)
                icon_style = p.get("icon_style") or await get_button_icon_style()
                closed_kb = build_poll_keyboard(
                    poll_id=p["poll_id"],
                    candidates=p_cands,
                    bot_username=bot_info.username,
                    is_closed=True,
                    cta_text=cta_text,
                    cta_url=cta_url,
                    icon_style=icon_style
                )
                results_channel_text = await render_poll_ended(
                    title=p['title'],
                    winner=p_winner_text,
                    votes=total_votes,
                    bot_username=bot_info.username,
                    lang=p_chan_lang,
                    created_at=p.get("created_at"),
                    ended_at=p.get("ended_at"),
                    creator_id=user_id,
                    contact_username=p.get("contact_username") or poll.get("contact_username")
                )
                await safe_bot_edit_message(
                    bot=bot,
                    chat_id=p["target_chat_id"],
                    message_id=p["channel_message_id"],
                    text=results_channel_text,
                    reply_markup=closed_kb,
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
            except Exception:
                pass

    # 2. Ask Creator whether to send Auto Winner list, Custom announcement, or Skip
    channel_name = html.escape(poll.get('target_chat_title') or 'Your Channel')
    if is_multi_part:
        if lang == "en":
            header_status = f"🏆 <b>Contest Ended Successfully! (All {len(parts)} connected parts closed together)</b>"
            vote_label = "Total Combined Votes"
        elif lang == "hi":
            header_status = f"🏆 <b>प्रतियोगिता सफलतापूर्वक समाप्त! (सभी {len(parts)} भाग एक साथ बंद)</b>"
            vote_label = "कुल संयुक्त वोट"
        else:
            header_status = f"🏆 <b>কনটেস্ট সফলভাবে সমাপ্ত হয়েছে! (সকল {len(parts)}টি পর্ব একসাথে ক্লোজ করা হয়েছে)</b>"
            vote_label = "সর্বমোট সম্মিলিত ভোট"
    else:
        if lang == "en":
            header_status = f"🏆 <b>Poll #{poll_id} Ended Successfully!</b>"
            vote_label = "Total Votes"
        elif lang == "hi":
            header_status = f"🏆 <b>पोल #{poll_id} सफलतापूर्वक समाप्त हुआ!</b>"
            vote_label = "कुल वोट"
        else:
            header_status = f"🏆 <b>পোল #{poll_id} সফলভাবে সমাপ্ত হয়েছে!</b>"
            vote_label = "সর্বমোট ভোট"

    if lang == "en":
        prompt_text = (
            f"{header_status}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>Title:</b> {html.escape(base_title)}\n"
            f"📢 <b>Channel:</b> {channel_name}\n\n"
            f"{winner_text}\n\n"
            f"🗳️ <b>{vote_label}:</b> <code>{total_votes}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📢 <b>Would you like to post a winner announcement to the channel?</b>\n\n"
            f"• <b>Auto Announcement:</b> Bot sends official winner list with medals.\n"
            f"• <b>Custom Announcement:</b> Write your own message (Brand credit & button are preserved automatically)."
        )
    elif lang == "hi":
        prompt_text = (
            f"{header_status}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>शीर्षक:</b> {html.escape(base_title)}\n"
            f"📢 <b>चैनल:</b> {channel_name}\n\n"
            f"{winner_text}\n\n"
            f"🗳️ <b>{vote_label}:</b> <code>{total_votes}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📢 <b>क्या आप चैनल में विजेता घोषणा भेजना चाहते हैं?</b>\n\n"
            f"• <b>ऑटो घोषणा:</b> बॉट सीधे मेडल और नामों के साथ पोस्ट भेजेगा।\n"
            f"• <b>कस्टम घोषणा:</b> अपना संदेश लिखें (बॉट क्रेडिट और लिंक सुरक्षित रहेगा)।"
        )
    else:
        prompt_text = (
            f"{header_status}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>শিরোনাম:</b> {html.escape(base_title)}\n"
            f"📢 <b>চ্যানেল:</b> {channel_name}\n\n"
            f"{winner_text}\n\n"
            f"🗳️ <b>{vote_label}:</b> <code>{total_votes}</code> টি\n"
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

@router.callback_query(F.data.startswith("end_poll:"))
async def cb_end_poll(callback: CallbackQuery):
    poll_id = int(callback.data.split(":")[1])
    await _handle_end_poll_unified(callback, poll_id)

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

        parts = await get_poll_parts(poll_id)
        is_multi_part = len(parts) > 1

        if is_multi_part:
            agg = await get_multi_part_aggregated_results(poll_id)
            top_winners = agg.get("top_winners", [])
            total_votes = agg.get("total_votes", 0)
            clean_title = get_base_title(poll["title"])
        else:
            candidates = await get_candidates(poll_id)
            w_count = int(poll.get("winner_count") or 1)
            voted = [c for c in candidates if c.get("votes_count", 0) > 0]
            top_winners = voted[:w_count] if voted else candidates[:w_count]
            total_votes = sum(c.get("votes_count", 0) for c in candidates)
            clean_title = poll["title"]

        channel_lang = poll.get("language") or lang
        bot_info = await callback.bot.get_me()

        announcement_text = await render_winner_announcement(
            title=clean_title,
            top_winners=top_winners,
            total_votes=total_votes,
            bot_username=bot_info.username,
            lang=channel_lang,
            creator_id=user_id,
            contact_username=poll.get("contact_username"),
            is_multi_part=is_multi_part
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
    poll_id = int(callback.data.split(":")[1])
    await _handle_end_poll_unified(callback, poll_id)
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

# --- Add Candidates to Active Live Poll ---

@router.callback_query(F.data.startswith("add_cands:"))
async def cb_add_candidates_start(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    lang = await get_user_language(user_id)
    poll_id = int(callback.data.split(":")[1])
    poll = await get_poll(poll_id)
    if not poll or (poll["creator_id"] != user_id and user_id not in ADMIN_IDS):
        err = "Poll not found or no permission!" if lang == "en" else "পোলটি পাওয়া যায়নি বা দেখার অনুমতি নেই!"
        await callback.answer(err, show_alert=True)
        return

    if poll["status"] != "active":
        err = "This poll has already ended!" if lang == "en" else "এই পোলটি ইতিমধ্যে সমাপ্ত হয়েছে!"
        await callback.answer(err, show_alert=True)
        return

    existing_candidates = await get_candidates(poll_id)
    current_count = len(existing_candidates)
    remaining_slots = max(0, 29 - current_count)

    await state.clear()
    await state.set_state(PollManagementState.waiting_for_new_candidates)
    await state.update_data(target_add_poll_id=poll_id)

    cancel_btn_text = "🔙 Cancel & Back / ফিরে যান" if lang == "bn" else "🔙 Cancel & Back"
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=cancel_btn_text, callback_data=f"view_poll:{poll_id}")]
    ])

    clean_title = strip_tg_emoji_tags(poll.get("title") or "")
    if lang == "en":
        prompt = (
            f"➕ <b>Add Candidates to Live Poll (#{poll_id})</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>Title:</b> {clean_title}\n"
            f"📢 <b>Channel:</b> {html.escape(poll.get('target_chat_title') or 'Channel')}\n"
            f"👥 <b>Current Candidates:</b> {current_count} (Max 29 per post)\n"
            f"✨ <b>Available Slots in this post:</b> {remaining_slots}\n\n"
            f"Send the new candidate names (one per line or comma-separated):\n"
            f"<i>Example:</i>\n"
            f"<code>Candidate {current_count + 1}\nCandidate {current_count + 2}</code>\n\n"
            f"💡 <i>These candidates will be immediately added as voting buttons to your live channel post! Previous votes remain 100% safe.</i>\n\n"
            f"To cancel, tap below or type /cancel"
        )
    else:
        prompt = (
            f"➕ <b>চলমান পোলে নতুন প্রার্থী যোগ (#{poll_id})</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>শিরোনাম:</b> {clean_title}\n"
            f"📢 <b>চ্যানেল:</b> {html.escape(poll.get('target_chat_title') or 'Channel')}\n"
            f"👥 <b>বর্তমান প্রার্থী সংখ্যা:</b> {current_count} জন (পোস্টে সর্বোচ্চ ২৯ জন)\n"
            f"✨ <b>এই পোস্টে খালি স্লট:</b> {remaining_slots} টি\n\n"
            f"নতুন প্রার্থীদের নাম লিখে পাঠান (প্রতি লাইনে একটি করে অথবা কমা দিয়ে):\n"
            f"<i>উদাহরণ:</i>\n"
            f"<code>Candidate {current_count + 1}\nCandidate {current_count + 2}</code>\n\n"
            f"💡 <i>নামগুলো পাঠানো মাত্রই চ্যানেলের লাইভ পোস্টে নতুন বাটন হিসেবে যুক্ত হয়ে যাবে! আগের কোনো ভোট নষ্ট হবে না।</i>\n\n"
            f"বাতিল করতে নিচের বাটনে চাপুন বা /cancel লিখুন।"
        )

    await callback.message.edit_text(prompt, reply_markup=cancel_kb, parse_mode="HTML")
    await callback.answer()

@router.message(PollManagementState.waiting_for_new_candidates)
async def process_add_candidates(message: Message, state: FSMContext):
    from bot.handlers.poll_create import check_command_breakout
    if await check_command_breakout(message, state):
        return

    data = await state.get_data()
    poll_id = data.get("target_add_poll_id")
    if not poll_id:
        await state.clear()
        await message.answer("⚠️ Session expired. Please open /mypolls again.")
        return

    poll = await get_poll(poll_id)
    if not poll or poll["status"] != "active":
        await state.clear()
        await message.answer("⚠️ Poll is no longer active.")
        return

    raw_text = (message.text or "").strip()
    if not raw_text:
        await message.answer("⚠️ Please send valid candidate names / অনুগ্রহ করে সঠিক নাম পাঠান:")
        return

    if "\n" in raw_text:
        new_names = [n.strip() for n in raw_text.split("\n") if n.strip()]
    else:
        new_names = [n.strip() for n in raw_text.split(",") if n.strip()]

    if not new_names:
        await message.answer("⚠️ No names found. Please send at least 1 candidate name.")
        return

    user_id = message.from_user.id
    lang = await get_user_language(user_id)
    existing_candidates = await get_candidates(poll_id)
    current_count = len(existing_candidates)
    existing_names_lower = {c["name"].lower() for c in existing_candidates}

    unique_new = []
    for n in new_names:
        if n.lower() not in existing_names_lower and n.lower() not in [x.lower() for x in unique_new]:
            unique_new.append(n)

    if not unique_new:
        msg = "⚠️ All provided names already exist in this poll!" if lang == "en" else "⚠️ এই নামগুলো ইতিমধ্যে এই পোলে যুক্ত আছে!"
        await message.answer(msg)
        return

    available_slots = max(0, 29 - current_count)
    to_add = unique_new[:available_slots]
    overflow = unique_new[available_slots:]

    if not to_add:
        msg = (
            f"⚠️ <b>This post has reached its limit of 29 candidates!</b>\n\n"
            f"You have {len(unique_new)} new candidates. Please use <b>📑 Next Part</b> to publish them as Part 2 in the same channel."
            if lang == "en" else
            f"⚠️ <b>এই পোস্টটিতে সর্বোচ্চ ২৯ জন প্রার্থীর জায়গা পূর্ণ হয়ে গেছে!</b>\n\n"
            f"আপনার {len(unique_new)} জন নতুন প্রার্থী রয়েছে। একই চ্যানেলে এগুলো পর্ব ২ (Part 2) হিসেবে দিতে <b>📑 পরবর্তী পর্ব</b> বাটনটি ব্যবহার করুন।"
        )
        back_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📑 Next Part / পরবর্তী পর্ব", callback_data=f"add_part:{poll_id}")],
            [InlineKeyboardButton(text="🔙 Back to Poll", callback_data=f"view_poll:{poll_id}")]
        ])
        await state.clear()
        await message.answer(msg, reply_markup=back_kb, parse_mode="HTML")
        return

    await add_candidates_to_poll(poll_id, to_add)

    all_candidates = await get_candidates(poll_id)

    bot = message.bot
    bot_info = await bot.get_me()
    poll_lang = poll.get("language") or lang
    icon_style = poll.get("icon_style") or await get_user_icon_style(poll["creator_id"])
    cta_text, cta_url = await render_poll_cta(bot_info.username, lang=poll_lang, creator_id=poll["creator_id"])

    new_poll_kb = build_poll_keyboard(
        poll_id,
        all_candidates,
        bot_info.username,
        cta_text=cta_text,
        cta_url=cta_url,
        icon_style=icon_style
    )

    card_text = await render_poll_card(
        poll["title"],
        bot_info.username,
        lang=poll_lang,
        ends_at=poll.get("ends_at"),
        created_at=poll.get("created_at"),
        winner_count=poll.get("winner_count") or 1,
        creator_id=poll["creator_id"]
    )

    channel_updated = False
    if poll.get("target_chat_id") and poll.get("channel_message_id"):
        try:
            await safe_bot_edit_message(
                bot,
                poll["target_chat_id"],
                poll["channel_message_id"],
                text=card_text,
                reply_markup=new_poll_kb
            )
            channel_updated = True
        except Exception:
            pass

    await state.clear()

    added_list_str = "\n".join([f"   • {html.escape(n)}" for n in to_add])
    overflow_note = ""
    if overflow:
        overflow_note = (
            f"\n\n⚠️ <i>Note: Post reached 29 candidates. {len(overflow)} remaining candidates were not added. Tap '📑 Next Part' below to publish Part 2.</i>"
            if lang == "en" else
            f"\n\n⚠️ <i>বিঃদ্রঃ পোস্টে ২৯ জন পূর্ণ হওয়ায় বাকি {len(overflow)} জন যোগ হয়নি। তাদের পর্ব ২ হিসেবে দিতে নিচে '📑 পরবর্তী পর্ব' চাপুন।</i>"
        )

    view_btn_text = "📊 View Poll / পোল দেখুন" if lang == "bn" else "📊 View Poll"
    btn_row = [InlineKeyboardButton(text=view_btn_text, callback_data=f"view_poll:{poll_id}")]
    if overflow:
        btn_row.append(InlineKeyboardButton(text="📑 Next Part", callback_data=f"add_part:{poll_id}"))
    success_kb = InlineKeyboardMarkup(inline_keyboard=[btn_row])

    if lang == "en":
        confirm_text = (
            f"✅ <b>Successfully added {len(to_add)} new candidate(s)!</b>\n\n"
            f"📋 <b>Newly Added:</b>\n{added_list_str}\n\n"
            f"👥 <b>Total Candidates now:</b> {len(all_candidates)}\n"
            f"📢 <b>Live Channel Post:</b> {'Updated with new voting buttons! ✅' if channel_updated else 'Saved in DB'}"
            f"{overflow_note}"
        )
    else:
        confirm_text = (
            f"✅ <b>সফলভাবে {len(to_add)} জন নতুন প্রার্থী যোগ করা হয়েছে!</b>\n\n"
            f"📋 <b>নতুন যুক্ত প্রার্থীরা:</b>\n{added_list_str}\n\n"
            f"👥 <b>বর্তমানে সর্বমোট প্রার্থী:</b> {len(all_candidates)} জন\n"
            f"📢 <b>চ্যানেলের পোস্ট:</b> {'সরাসরি নতুন বাটনসহ লাইভ আপডেট হয়েছে! ✅' if channel_updated else 'ডাটাবেসে সংরক্ষিত'}"
            f"{overflow_note}"
        )

    await message.answer(confirm_text, reply_markup=success_kb, parse_mode="HTML")

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


