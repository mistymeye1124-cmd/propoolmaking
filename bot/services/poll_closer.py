import asyncio
import html
import logging
from aiogram import Bot
from bot.database.db import (
    get_poll, end_poll, get_expired_active_polls, get_user_language, get_button_icon_style,
    cleanup_expired_ended_polls, get_poll_parts, get_multi_part_aggregated_results, get_candidates
)
from bot.handlers.poll_create import get_base_title
from bot.keyboards.inline import build_poll_keyboard, build_winner_announcement_choice_keyboard
from bot.templates import render_poll_ended, render_poll_cta, format_winners_display, safe_bot_edit_message, safe_send_message

logger = logging.getLogger(__name__)

async def close_and_announce_poll(bot: Bot, poll_id: int):
    """
    Closes an expired poll, updates the channel message with the winner announcement,
    and sends a private notification to the poll creator.
    Supports Top N Winners, multi-part unified aggregation, and per-poll icon styles.
    """
    poll = await get_poll(poll_id)
    if not poll or poll["status"] != "active":
        return

    logger.info(f"Auto-closing expired poll #{poll_id} ('{poll.get('title')}')")

    parts = await get_poll_parts(poll_id)
    is_multi_part = len(parts) > 1

    # End all connected active parts simultaneously
    for p in parts:
        if p.get("status") == "active":
            await end_poll(p["poll_id"])

    creator_id = poll["creator_id"]
    creator_lang = await get_user_language(creator_id)
    channel_lang = poll.get("language") or creator_lang
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

    winner_text_channel = format_winners_display(top_winners, lang=channel_lang, is_multi_part=is_multi_part)
    winner_text_creator = format_winners_display(top_winners, lang=creator_lang, is_multi_part=is_multi_part)

    # 1. Update Channel Message for ALL connected parts
    for p in parts:
        if p.get("channel_message_id") and p.get("target_chat_id"):
            try:
                p_cands = await get_candidates(p["poll_id"])
                p_chan_lang = p.get("language") or channel_lang
                p_winner_text = format_winners_display(top_winners, lang=p_chan_lang, is_multi_part=is_multi_part)
                cta_text, cta_url = await render_poll_cta(bot_info.username, lang=p_chan_lang, creator_id=creator_id)
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
                    creator_id=creator_id,
                    contact_username=p.get("contact_username") or poll.get("contact_username")
                )
                await safe_bot_edit_message(
                    bot=bot,
                    chat_id=p["target_chat_id"],
                    message_id=p["channel_message_id"],
                    text=results_channel_text,
                    reply_markup=closed_kb,
                    parse_mode="HTML"
                )
                logger.info(f"Channel message updated for auto-ended poll #{p['poll_id']}")
            except Exception as e:
                logger.warning(f"Failed to update channel message for poll #{p['poll_id']}: {e}")

    # 2. Private Alert to Poll Creator
    if creator_id:
        try:
            channel_name = html.escape(poll.get('target_chat_title') or 'Your Channel')
            choice_kb = build_winner_announcement_choice_keyboard(poll_id, lang=creator_lang)
            if is_multi_part:
                if creator_lang == "en":
                    status_line = f"⏱️ <b>Contest Ended! (All {len(parts)} parts closed together)</b>"
                    vote_lbl = "Total Combined Votes"
                elif creator_lang == "hi":
                    status_line = f"⏱️ <b>प्रतियोगिता समाप्त! (सभी {len(parts)} भाग एक साथ बंद)</b>"
                    vote_lbl = "कुल संयुक्त वोट"
                else:
                    status_line = f"⏱️ <b>কনটেস্ট সমাপ্ত! (সকল {len(parts)}টি পর্ব একসাথে ক্লোজ হয়েছে)</b>"
                    vote_lbl = "সর্বমোট সম্মিলিত ভোট"
            else:
                if creator_lang == "en":
                    status_line = f"⏱️ <b>Poll #{poll_id} Timer Expired!</b>"
                    vote_lbl = "Total Votes"
                elif creator_lang == "hi":
                    status_line = f"⏱️ <b>पोल #{poll_id} की समय सीमा समाप्त!</b>"
                    vote_lbl = "कुल वोट"
                else:
                    status_line = f"⏱️ <b>পোল #{poll_id}-এর সময়সীমা শেষ হয়েছে!</b>"
                    vote_lbl = "সর্বমোট ভোট"

            if creator_lang == "en":
                notify_text = (
                    f"{status_line}\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"📌 <b>Title:</b> {html.escape(base_title)}\n"
                    f"📢 <b>Channel:</b> {channel_name}\n\n"
                    f"{winner_text_creator}\n\n"
                    f"🗳️ <b>{vote_lbl}:</b> <code>{total_votes}</code>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "📢 <b>Would you like to post a winner announcement to the channel?</b>\n\n"
                    "• <b>Auto:</b> Send official winner list with medals.\n"
                    "• <b>Custom:</b> Write custom text (Brand credit & button are preserved)."
                )
            elif creator_lang == "hi":
                notify_text = (
                    f"{status_line}\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"📌 <b>शीर्षक:</b> {html.escape(base_title)}\n"
                    f"📢 <b>चैनल:</b> {channel_name}\n\n"
                    f"{winner_text_creator}\n\n"
                    f"🗳️ <b>{vote_lbl}:</b> <code>{total_votes}</code>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "📢 <b>क्या आप चैनल में विजेता घोषणा पोस्ट भेजना चाहते हैं?</b>\n\n"
                    "• <b>ऑटो:</b> मेडल और नाम के साथ आधिकारिक सूची भेजें।\n"
                    "• <b>कस्टम:</b> अपना संदेश लिखें (ब्रांड क्रेडिट और लिंक सुरक्षित रहेगा)।"
                )
            else:
                notify_text = (
                    f"{status_line}\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"📌 <b>শিরোনাম:</b> {html.escape(base_title)}\n"
                    f"📢 <b>চ্যানেল:</b> {channel_name}\n\n"
                    f"{winner_text_creator}\n\n"
                    f"🗳️ <b>{vote_lbl}:</b> <code>{total_votes}</code> টি\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "📢 <b>আপনি কি চ্যানেলে চূড়ান্ত বিজয়ী ঘোষণা পাঠাতে চান?</b>\n\n"
                    "• <b>অটো:</b> মেডেল ও ভোটসহ স্বয়ংক্রিয় অফিসিয়াল বিজয়ী তালিকা পাঠাবে।\n"
                    "• <b>কাস্টম:</b> নিজের মতো শুভেচ্ছা মেসেজ লিখে পাঠান (বট ক্রেডিট সংরক্ষিত থাকবে)।"
                )

            await safe_send_message(bot, creator_id, text=notify_text, reply_markup=choice_kb, parse_mode="HTML")
            logger.info(f"Creator #{creator_id} notified with winner announcement choices for auto-ended poll #{poll_id}")
        except Exception as e:
            logger.warning(f"Could not notify creator #{creator_id} for poll #{poll_id}: {e}")

async def start_poll_timer_worker(bot: Bot):
    """
    Background worker loop that periodically checks for expired polls
    and closes them automatically.
    """
    logger.info("Starting background poll timer worker...")
    while True:
        try:
            expired_polls = await get_expired_active_polls()
            if expired_polls:
                logger.info(f"Found {len(expired_polls)} expired poll(s) to close.")
                for p in expired_polls:
                    await close_and_announce_poll(bot, p["poll_id"])

            # Purge polls ended more than 2 days ago
            await cleanup_expired_ended_polls(days=2)
        except Exception as e:
            logger.error(f"Error in poll timer worker loop: {e}")
        await asyncio.sleep(15)
