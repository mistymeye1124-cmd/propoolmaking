import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery
from bot.database.db import (
    get_poll, get_candidates, has_user_voted, cast_vote, get_user_language,
    get_button_icon_style, save_user
)
from bot.keyboards.inline import build_poll_keyboard
from bot.templates import render_fsub_alert, render_vote_success, render_poll_cta, safe_send_message

logger = logging.getLogger(__name__)
router = Router()

async def check_membership(bot, chat_id: int, user_id: int) -> bool:
    """
    Checks if a user is an active member in a Telegram chat/channel.
    Strictly verifies that the voter is creator, administrator, member, or restricted.
    Returns False if user is not in the channel or has left/been kicked.
    """
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        if member.status in ["creator", "administrator", "member", "restricted"]:
            return True
        return False
    except Exception as e:
        err_msg = str(e).lower()
        if any(term in err_msg for term in ["user not found", "participant", "left", "kicked", "not a member"]):
            return False
        logger.warning(f"Error checking membership for user {user_id} in chat {chat_id}: {e}")
        return False

_cached_bot_username = None

async def get_bot_username(bot) -> str:
    global _cached_bot_username
    if not _cached_bot_username:
        info = await bot.get_me()
        _cached_bot_username = info.username
    return _cached_bot_username

@router.callback_query(F.data.startswith("vote:"))
async def handle_vote(callback: CallbackQuery):
    # 0. Anti-Bot Account & Invalid ID Shield
    if callback.from_user.is_bot or not callback.from_user.id or callback.from_user.id <= 0:
        await callback.answer("⛔ Automated or invalid accounts cannot vote / বট বা ভুয়া অ্যাকাউন্ট নিষিদ্ধ!", show_alert=True)
        return

    user_id = callback.from_user.id
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Invalid Request / ত্রুটিপূর্ণ অনুরোধ!", show_alert=True)
        return

    try:
        poll_id = int(parts[1])
        candidate_id = int(parts[2])
    except ValueError:
        await callback.answer("Invalid Data / অকার্যকর ডেটা!", show_alert=True)
        return

    # 1. Fetch Poll
    poll = await get_poll(poll_id)
    if not poll:
        await callback.answer("⚠️ Poll not found / পোলটি পাওয়া যায়নি!", show_alert=True)
        return

    if poll["status"] != "active":
        await callback.answer("⚠️ This poll has ended / এই পোলটি সমাপ্ত হয়ে গেছে!", show_alert=True)
        return

    # 2. Check if user already voted (Single vote rule)
    already_voted = await has_user_voted(poll_id, user_id)
    if already_voted:
        await callback.answer(
            "⚠️ You have already voted in this poll!\n"
            "আপনি ইতিমধ্যে এই পোলে ভোট দিয়েছেন (১ বারই ভোট দেওয়া যায়)।",
            show_alert=True
        )
        return

    bot = callback.bot

    # 3. Force-Subscription Check: Channel Membership only
    voter_lang = await get_user_language(user_id)
    is_channel_member = await check_membership(bot, poll["target_chat_id"], user_id)
    if not is_channel_member:
        channel_user = poll.get("target_chat_username")
        join_hint = f"@{channel_user}" if channel_user else ("the channel" if voter_lang == "en" else "চ্যানেলটিতে")
        fsub_msg = await render_fsub_alert(join_hint, lang=voter_lang)
        await callback.answer(fsub_msg, show_alert=True)
        return

    # 4. Cast Vote Atomic Operation
    success, reason = await cast_vote(poll_id, candidate_id, user_id)
    if not success:
        if reason == "ALREADY_VOTED":
            msg = "⚠️ You have already voted!" if voter_lang == "en" else "⚠️ আপনি ইতোমধ্যে ভোট দিয়েছেন (১ বারই ভোট দেওয়া যায়)!"
            await callback.answer(msg, show_alert=True)
        elif reason == "POLL_CLOSED":
            msg = "⚠️ This poll has ended!" if voter_lang == "en" else "⚠️ পোলটি সমাপ্ত হয়ে গেছে!"
            await callback.answer(msg, show_alert=True)
        elif reason == "INVALID_CANDIDATE":
            msg = "⚠️ Invalid candidate!" if voter_lang == "en" else "⚠️ অকার্যকর প্রার্থী!"
            await callback.answer(msg, show_alert=True)
        else:
            await callback.answer(f"Voting error: {reason}", show_alert=True)
        return

    # Record voter in audit database
    await save_user(
        user_id=user_id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name or "",
        last_name=callback.from_user.last_name
    )

    # Instant Toast Feedback to Voter (Zero Lag)
    candidates = await get_candidates(poll_id)
    voted_name = next((c["name"] for c in candidates if c["candidate_id"] == candidate_id), "Option")
    success_toast = await render_vote_success(voted_name, lang=voter_lang)
    await callback.answer(success_toast, show_alert=False)

    # 5. Success: Update message with live counts
    b_username = await get_bot_username(bot)
    poll_creator_id = poll.get("creator_id")
    poll_lang = poll.get("language") or ((await get_user_language(poll_creator_id)) if poll_creator_id else "bn")
    cta_text, cta_url = await render_poll_cta(b_username, lang=poll_lang, creator_id=poll_creator_id)
    icon_style = poll.get("icon_style") or await get_button_icon_style()
    new_keyboard = build_poll_keyboard(poll_id, candidates, b_username, cta_text=cta_text, cta_url=cta_url, icon_style=icon_style)

    try:
        await callback.message.edit_reply_markup(reply_markup=new_keyboard)
    except Exception as e:
        logger.info(f"Message reply markup unchanged or edit error: {e}")

    # 6. Instant Notification to Poll Creator / Owner
    creator_id = poll.get("creator_id")
    if creator_id:
        try:
            import html
            creator_lang = await get_user_language(creator_id)
            voter_user = callback.from_user
            voter_name = html.escape(voter_user.full_name or "Voter")
            voter_handle = f"@{voter_user.username}" if voter_user.username else f"ID: <code>{voter_user.id}</code>"

            cand_obj = next((c for c in candidates if c["candidate_id"] == candidate_id), None)
            cand_votes = cand_obj["votes_count"] if cand_obj else 1
            total_poll_votes = sum(c["votes_count"] for c in candidates)
            channel_title = html.escape(poll.get("target_chat_title") or "Channel")

            if creator_lang == "en":
                creator_alert = (
                    "🔔 <b>New Vote Received in Your Poll!</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"📊 <b>Poll:</b> {html.escape(poll['title'])}\n"
                    f"👤 <b>Candidate:</b> <b>{html.escape(voted_name)}</b> (Now: <code>{cand_votes}</code> votes)\n"
                    f"🗳️ <b>Total Votes:</b> <code>{total_poll_votes}</code>\n"
                    f"📢 <b>Channel:</b> {channel_title}\n"
                    f"🧑‍💼 <b>Voter:</b> {voter_name} ({voter_handle})\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "⚡ <i>Live update from your viral poll</i>"
                )
            else:
                creator_alert = (
                    "🔔 <b>আপনার পোলে নতুন একটি ভোট পড়েছে!</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"📊 <b>পোল:</b> {html.escape(poll['title'])}\n"
                    f"👤 <b>প্রার্থী:</b> <b>{html.escape(voted_name)}</b> (বর্তমান ভোট: <code>{cand_votes}</code>)\n"
                    f"🗳️ <b>সর্বমোট ভোট:</b> <code>{total_poll_votes}</code> টি\n"
                    f"📢 <b>চ্যানেল:</b> {channel_title}\n"
                    f"🧑‍💼 <b>ভোটার:</b> {voter_name} ({voter_handle})\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "⚡ <i>আপনার পোলের লাইভ আপডেট</i>"
                )

            await safe_send_message(bot, creator_id, text=creator_alert, parse_mode="HTML")
        except Exception as e:
            logger.info(f"Could not notify poll creator {creator_id}: {e}")

@router.callback_query(F.data.startswith("poll_closed:"))
async def handle_poll_closed(callback: CallbackQuery):
    voter_lang = await get_user_language(callback.from_user.id)
    if voter_lang == "en":
        msg = "🏁 This poll has ended! Voting is closed."
    elif voter_lang == "hi":
        msg = "🏁 यह पोल समाप्त हो चुका है! वोटिंग बंद है।"
    elif voter_lang == "ar":
        msg = "🏁 لقد انتهى هذا الاستطلاع! التصويت مغلق."
    elif voter_lang == "ru":
        msg = "🏁 Этот опрос завершен! Голосование закрыто."
    else:
        msg = "🏁 এই পোলটি সমাপ্ত হয়ে গেছে! ভোট গ্রহণ বন্ধ আছে।"
    await callback.answer(msg, show_alert=True)
