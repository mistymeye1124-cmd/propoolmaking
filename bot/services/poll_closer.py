import asyncio
import html
import logging
from aiogram import Bot
from bot.database.db import (
    get_poll, end_poll, get_expired_active_polls, get_user_language, get_button_icon_style,
    cleanup_expired_ended_polls
)
from bot.keyboards.inline import build_poll_keyboard, build_winner_announcement_choice_keyboard
from bot.templates import render_poll_ended, render_poll_cta, format_winners_display, safe_bot_edit_message, safe_send_message

logger = logging.getLogger(__name__)

async def close_and_announce_poll(bot: Bot, poll_id: int):
    """
    Closes an expired poll, updates the channel message with the winner announcement,
    and sends a private notification to the poll creator.
    Supports Top N Winners and per-poll icon styles.
    """
    poll = await get_poll(poll_id)
    if not poll or poll["status"] != "active":
        return

    logger.info(f"Auto-closing expired poll #{poll_id} ('{poll.get('title')}')")

    poll_data = await end_poll(poll_id)
    if not poll_data:
        return

    creator_id = poll["creator_id"]
    creator_lang = await get_user_language(creator_id)
    channel_lang = poll.get("language") or creator_lang
    bot_info = await bot.get_me()

    candidates = poll_data.get("candidates", [])
    winner = poll_data.get("winner")
    top_winners = poll_data.get("top_winners") or ([winner] if winner and winner.get('votes_count', 0) > 0 else [])
    total_votes = sum(c["votes_count"] for c in candidates)

    winner_text_channel = format_winners_display(top_winners, lang=channel_lang)
    winner_text_creator = format_winners_display(top_winners, lang=creator_lang)

    # 1. Update Channel Message
    if poll.get("channel_message_id") and poll.get("target_chat_id"):
        try:
            cta_text, cta_url = await render_poll_cta(bot_info.username, lang=channel_lang, creator_id=creator_id)
            icon_style = poll.get("icon_style") or await get_button_icon_style()
            closed_kb = build_poll_keyboard(
                poll_id=poll_id,
                candidates=candidates,
                bot_username=bot_info.username,
                is_closed=True,
                cta_text=cta_text,
                cta_url=cta_url,
                icon_style=icon_style
            )

            results_channel_text = await render_poll_ended(
                title=poll['title'],
                winner=winner_text_channel,
                votes=total_votes,
                bot_username=bot_info.username,
                lang=channel_lang,
                created_at=poll.get("created_at"),
                ended_at=poll_data.get("ended_at"),
                creator_id=creator_id,
                contact_username=poll.get("contact_username")
            )
            await safe_bot_edit_message(
                bot=bot,
                chat_id=poll["target_chat_id"],
                message_id=poll["channel_message_id"],
                text=results_channel_text,
                reply_markup=closed_kb,
                parse_mode="HTML"
            )
            logger.info(f"Channel message updated for auto-ended poll #{poll_id}")
        except Exception as e:
            logger.warning(f"Failed to update channel message for poll #{poll_id}: {e}")

    # 2. Private Alert to Poll Creator
    if creator_id:
        try:
            channel_name = html.escape(poll.get('target_chat_title') or 'Your Channel')
            choice_kb = build_winner_announcement_choice_keyboard(poll_id, lang=creator_lang)
            if creator_lang == "en":
                notify_text = (
                    f"⏱️ <b>Poll #{poll_id} Timer Expired!</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"📌 <b>Title:</b> {html.escape(poll['title'])}\n"
                    f"📢 <b>Channel:</b> {channel_name}\n\n"
                    f"{winner_text_creator}\n\n"
                    f"🗳️ <b>Total Votes:</b> <code>{total_votes}</code>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "📢 <b>Would you like to post a winner announcement to the channel?</b>\n\n"
                    "• <b>Auto:</b> Send official winner list with medals.\n"
                    "• <b>Custom:</b> Write custom text (Brand credit & button are preserved)."
                )
            elif creator_lang == "hi":
                notify_text = (
                    f"⏱️ <b>पोल #{poll_id} की समय सीमा समाप्त!</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"📌 <b>शीर्षक:</b> {html.escape(poll['title'])}\n"
                    f"📢 <b>चैनल:</b> {channel_name}\n\n"
                    f"{winner_text_creator}\n\n"
                    f"🗳️ <b>कुल वोट:</b> <code>{total_votes}</code>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "📢 <b>क्या आप चैनल में विजेता घोषणा पोस्ट भेजना चाहते हैं?</b>\n\n"
                    "• <b>ऑटो:</b> मेडल और नाम के साथ आधिकारिक सूची भेजें।\n"
                    "• <b>कस्टम:</b> अपना संदेश लिखें (ब्रांड क्रेडिट और लिंक सुरक्षित रहेगा)।"
                )
            else:
                notify_text = (
                    f"⏱️ <b>পোল #{poll_id} এর সময়সীমা শেষ হয়েছে!</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"📌 <b>শিরোনাম:</b> {html.escape(poll['title'])}\n"
                    f"📢 <b>চ্যানেল:</b> {channel_name}\n\n"
                    f"{winner_text_creator}\n\n"
                    f"🗳️ <b>সর্বমোট ভোট:</b> <code>{total_votes}</code> টি\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "📢 <b>আপনি কি চ্যানেলে বিজয়ী ঘোষণা মেসেজ পাঠাতে চান?</b>\n\n"
                    "• <b>অটো:</b> মেডেল ও ভোটসহ স্বয়ংক্রিয় বিজয়ী তালিকা পাঠান।\n"
                    "• <b>কাস্টম:</b> নিজের পছন্দমতো শুভেচ্ছা লিখুন (বট ক্রেডিট ও বাটন লিংক যুক্ত থাকবে)।"
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
