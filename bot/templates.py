import re
import html
from typing import Dict, Any, Tuple, Optional, List
from aiogram.exceptions import TelegramBadRequest
from bot.database.db import get_setting, set_setting, get_custom_credit, get_effective_credit
from bot.utils.translator import translate_text_preserving_tags, detect_is_bengali

TG_EMOJI_PATTERN = re.compile(r'<tg-emoji\b[^>]*>([\s\S]*?)</tg-emoji>', re.IGNORECASE)

# Pattern matching supported Telegram HTML tags so they are not destroyed by escaping
ALLOWED_TAGS_PATTERN = re.compile(
    r'(</?(?:b|strong|i|em|u|ins|s|strike|del|span|tg-spoiler|code|pre)\b[^>]*>|'
    r'<a\s+href="[^"]*"\s*>|</a>|'
    r'<tg-emoji\b[^>]*>[\s\S]*?</tg-emoji>)',
    re.IGNORECASE
)

def strip_tg_emoji_tags(text: str) -> str:
    """
    Converts <tg-emoji emoji-id="..." or id="...">FALLBACK</tg-emoji> into plain FALLBACK.
    Used as an automatic fallback when Telegram Bot API rejects custom emojis.
    """
    if not text:
        return ""
    return TG_EMOJI_PATTERN.sub(r'\1', text)

def safe_html_preserve_tg_emoji(text: str) -> str:
    """
    Preserves valid Telegram HTML tags and Telegram Premium Emojis (<tg-emoji emoji-id="...">...</tg-emoji>),
    while safely escaping any invalid or dangerous raw angle brackets.
    """
    if not text:
        return ""
    placeholders = []
    def repl_save(match):
        idx = len(placeholders)
        placeholders.append(match.group(0))
        return f"___TG_HTML_PH_{idx}___"
    
    st = ALLOWED_TAGS_PATTERN.sub(repl_save, text)
    st = html.escape(st)
    for idx, orig in enumerate(placeholders):
        st = st.replace(f"___TG_HTML_PH_{idx}___", orig)
    return st

def strip_button_custom_emojis(reply_markup):
    """
    Strips icon_custom_emoji_id from all InlineKeyboardButtons or KeyboardButtons in reply_markup.
    Used as an automatic fallback if Telegram Bot API rejects custom emoji in buttons.
    """
    if not reply_markup:
        return reply_markup
    if hasattr(reply_markup, "inline_keyboard"):
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        new_rows = []
        for row in reply_markup.inline_keyboard:
            new_row = []
            for btn in row:
                d = btn.model_dump(exclude_none=True)
                d.pop("icon_custom_emoji_id", None)
                new_row.append(InlineKeyboardButton(**d))
            new_rows.append(new_row)
        return InlineKeyboardMarkup(inline_keyboard=new_rows)
    elif hasattr(reply_markup, "keyboard"):
        from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
        new_rows = []
        for row in reply_markup.keyboard:
            new_row = []
            for btn in row:
                d = btn.model_dump(exclude_none=True)
                d.pop("icon_custom_emoji_id", None)
                new_row.append(KeyboardButton(**d))
            new_rows.append(new_row)
        d_rm = reply_markup.model_dump(exclude_none=True)
        d_rm["keyboard"] = new_rows
        return ReplyKeyboardMarkup(**d_rm)
    return reply_markup

def extract_custom_emoji_info(text: str) -> Tuple[str, Optional[str]]:
    """
    Parses a string that might contain a Telegram Premium custom emoji tag:
    <tg-emoji emoji-id="123">🔥</tg-emoji> or <tg-emoji id="123">🔥</tg-emoji>.
    Returns: (clean_text_with_fallback_emoji, custom_emoji_id_or_none)
    """
    if not text:
        return "", None
    m = re.search(r'<tg-emoji\b[^>]*(?:emoji-id|id)="([0-9]+)"[^>]*>([\s\S]*?)</tg-emoji>', text, re.IGNORECASE)
    if m:
        custom_emoji_id = m.group(1)
        clean = re.sub(r'<tg-emoji\b[^>]*>([\s\S]*?)</tg-emoji>', r'\1', text, flags=re.IGNORECASE)
        clean = re.sub(r'<[^>]+>', '', clean).strip()
        return clean, custom_emoji_id
    clean = re.sub(r'<[^>]+>', '', text).strip()
    return clean, None

async def safe_send_message(
    bot,
    chat_id: int,
    text: str,
    reply_markup=None,
    parse_mode: str = "HTML",
    disable_web_page_preview: bool = True,
    **kwargs
):
    """
    Sends message with rich Telegram Premium Emojis (<tg-emoji> and icon_custom_emoji_id).
    If Telegram Bot API raises 'can't use custom emoji' on messages or buttons,
    it automatically strips custom emoji tags and button icons and retries cleanly.
    """
    try:
        return await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview,
            **kwargs
        )
    except TelegramBadRequest as e:
        err_msg = str(e).lower()
        if ("custom emoji" in err_msg or "button" in err_msg) and (parse_mode == "HTML" or reply_markup):
            fallback_text = strip_tg_emoji_tags(text) if parse_mode == "HTML" else text
            fallback_markup = strip_button_custom_emojis(reply_markup)
            return await bot.send_message(
                chat_id=chat_id,
                text=fallback_text,
                reply_markup=fallback_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview,
                **kwargs
            )
        raise

async def safe_edit_message(
    message_or_cb,
    text: str,
    reply_markup=None,
    parse_mode: str = "HTML",
    disable_web_page_preview: bool = True,
    **kwargs
):
    """
    Edits message with rich Telegram Premium Emojis (<tg-emoji> and icon_custom_emoji_id).
    If Telegram Bot API raises 'can't use custom emoji' on messages or buttons,
    it automatically strips custom emoji tags and button icons and retries cleanly.
    """
    try:
        return await message_or_cb.edit_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview,
            **kwargs
        )
    except TelegramBadRequest as e:
        err_msg = str(e).lower()
        if ("custom emoji" in err_msg or "button" in err_msg) and (parse_mode == "HTML" or reply_markup):
            fallback_text = strip_tg_emoji_tags(text) if parse_mode == "HTML" else text
            fallback_markup = strip_button_custom_emojis(reply_markup)
            return await message_or_cb.edit_text(
                text=fallback_text,
                reply_markup=fallback_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview,
                **kwargs
            )
        raise

async def safe_bot_edit_message(
    bot,
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup=None,
    parse_mode: str = "HTML",
    disable_web_page_preview: bool = True,
    **kwargs
):
    try:
        return await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview,
            **kwargs
        )
    except TelegramBadRequest as e:
        err_msg = str(e).lower()
        if ("custom emoji" in err_msg or "button" in err_msg) and (parse_mode == "HTML" or reply_markup):
            fallback_text = strip_tg_emoji_tags(text) if parse_mode == "HTML" else text
            fallback_markup = strip_button_custom_emojis(reply_markup)
            return await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=fallback_text,
                reply_markup=fallback_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview,
                **kwargs
            )
        raise



DEFAULTS_BN: Dict[str, str] = {
    "tpl_start": (
        '<tg-emoji emoji-id="5323642109767460983">🏠</tg-emoji> <b>Start / Main Menu</b> • <b>PRO POLL ENGINE v3.5</b>\n'
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "স্বাগতম, <b>{user_name}</b>!\n"
        "টেলিগ্রাম চ্যানেলের জন্য ফাস্ট ও সুরক্ষিত পোল সিস্টেম।\n\n"
        "<b>প্রধান সুবিধাসমূহ:</b>\n"
        '• <tg-emoji emoji-id="5202167764483076994">🎯</tg-emoji> <b>ফোর্স সাব:</b> জয়েন না করলে ভোট লক\n'
        '• <tg-emoji emoji-id="6271459718896554468">⚡</tg-emoji> <b>লাইভ স্কোর:</b> বাটনে রিয়েল-টাইম আপডেট\n'
        '• <tg-emoji emoji-id="5188344996356448758">🏆</tg-emoji> <b>অটো র‍্যাংকিং:</b> সমাপ্তিতে স্বয়ংক্রিয় মেধা তালিকা\n'
        '• <tg-emoji emoji-id="5201762530023733712">🎨</tg-emoji> <b>আইকন স্টাইল:</b> প্রিমিয়াম বাটন থিম সাপোর্ট\n'
        '• <tg-emoji emoji-id="6050646916109179497">🛡️</tg-emoji> <b>৭-লেয়ার সিকিউরিটি:</b> ডুপ্লিকেট ভোট প্রতিরোধ\n'
        '• <tg-emoji emoji-id="5296369303661067030">🔒</tg-emoji> <b>চ্যানেল আইসোলেশন:</b> শতভাগ প্রাইভেসি ও নিয়ন্ত্রণ\n\n'
        "<i>শুরু করতে নিচের অপশন থেকে নির্বাচন করুন:</i>"
    ),
    "tpl_poll_card": (
        '<tg-emoji emoji-id="5202167764483076994">📊</tg-emoji> <b>{title}</b>\n'
        "━━━━━━━━━━━━━━━━━━━━\n"
        '<tg-emoji emoji-id="5837134496868077492">🗳️</tg-emoji> <i>পছন্দের প্রার্থীকে ভোট দিতে নিচের বাটনে ক্লিক করুন:</i>\n\n'
        '⚠️ <b>সতর্কতা:</b> ভোট দিতে হলে অবশ্যই আমাদের চ্যানেলে জয়েন থাকতে হবে!\n'
        "━━━━━━━━━━━━━━━━━━━━\n"
        '<tg-emoji emoji-id="6271459718896554468">⚡</tg-emoji> <b>Powered by:</b> {bot_username}'
    ),
    "tpl_poll_cta": (
        "⚡ নিজের চ্যানেলের জন্য পোল তৈরি করুন ➔"
    ),
    "tpl_fsub_alert": (
        "⚠️ ভোট দিতে হলে আগে আপনাকে {channel} জয়েন করতে হবে!\n\n"
        "অনুগ্রহ করে জয়েন করে আবার ভোট দিন।"
    ),
    "tpl_vote_success": (
        "✅ '{candidate}' এর জন্য আপনার ভোট সফলভাবে গ্রহণ করা হয়েছে!"
    ),
    "tpl_poll_ended": (
        '<tg-emoji emoji-id="5204244329631082615">🏁</tg-emoji> <b>{title}</b>\n'
        "━━━━━━━━━━━━━━━━━━━━\n"
        '<tg-emoji emoji-id="5226431245918942763">🏆</tg-emoji> <b>পোল সমাপ্ত হয়েছে!</b>\n\n'
        "{winner}\n"
        '<tg-emoji emoji-id="5837134496868077492">🗳️</tg-emoji> <b>সর্বমোট কাস্ট করা ভোট:</b> <code>{votes}</code>\n'
        "━━━━━━━━━━━━━━━━━━━━\n"
        '<tg-emoji emoji-id="6179411633371095707">🎉</tg-emoji> অংশগ্রহণকারী সবাইকে ধন্যবাদ!\n'
        '<tg-emoji emoji-id="6271459718896554468">⚡</tg-emoji> <b>Powered by:</b> {bot_username}'
    ),
    "tpl_winner_announcement": (
        '<tg-emoji emoji-id="5226431245918942763">🏆</tg-emoji> <b>অফিসিয়াল বিজয়ী ঘোষণা</b>\n'
        "━━━━━━━━━━━━━━━━━━━━\n"
        '📌 <b>{title}</b>\n\n'
        "{winners}\n\n"
        "{stats}\n\n"
        "{claim_info}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        '<tg-emoji emoji-id="6179411633371095707">🎉</tg-emoji> <i>কনটেস্টে অংশগ্রহণকারী এবং ভোট প্রদানকারী সবাইকে ধন্যবাদ!</i>\n'
        '<tg-emoji emoji-id="6271459718896554468">⚡</tg-emoji> <b>Powered by:</b> {bot_username}'
    ),
    "tpl_prize_claim": (
        '<tg-emoji emoji-id="6271494293383286950">🎁</tg-emoji> <b>পুরস্কার দাবি ও যোগাযোগ / Prize Claim:</b>\n'
        '<tg-emoji emoji-id="5292109589456645419">📩</tg-emoji> <i>বিজয়ীগণ আপনার পুরস্কার ক্লেইম করতে নিম্নের হোস্ট এডমিনের সাথে যোগাযোগ করুন:</i>\n'
        '👉 <b>Giveaway Host:</b> {contact_link}'
    ),
    "tpl_anti_cheat_badge": (
        '<tg-emoji emoji-id="5202167764483076994">📊</tg-emoji> <b>কনটেস্ট পরিসংখ্যান:</b>\n'
        '<tg-emoji emoji-id="5837134496868077492">🗳️</tg-emoji> <b>সর্বমোট কাস্ট করা ভোট:</b> <code>{total_votes}</code> টি\n'
        '<tg-emoji emoji-id="6050646916109179497">🛡️</tg-emoji> <b>অ্যান্টি-চিট স্ট্যাটাস:</b> ১০০% ভেরিফাইড ও নিরপেক্ষ'
    ),
    "tpl_help": (
        '<tg-emoji emoji-id="5373098009640836781">📖</tg-emoji> <b>বট ব্যবহারের সম্পূর্ণ নিয়মাবলী ও গাইড (Complete Bot Guide & Instructions)</b>\n'
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "১️⃣ <b>চ্যানেলে বট যুক্ত করা (১-ক্লিক এডমিন):</b>\n"
        "• বটটিকে আপনার টেলিগ্রাম চ্যানেলে <b>Administrator</b> বানাতে হবে।\n"
        "• 'Post Messages' পারমিশন চালু রাখবেন যাতে বট পোল পোস্ট করতে পারে।\n"
        "• সবচেয়ে সহজে করতে '📢 চ্যানেলে যুক্ত করুন (১-ক্লিক)' বাটনে চাপ দিন।\n\n"
        "২️⃣ <b>নতুন পোল তৈরি ও প্রার্থী তালিকা:</b>\n"
        "• <b>/newpoll</b> কমান্ড দিন বা মেনু থেকে '➕ নতুন পোল তৈরি করুন' চাপুন।\n"
        "• পোলের শিরোনাম এবং প্রার্থীদের নাম প্রতি লাইনে একটি করে লিখে পাঠান।\n"
        "• ১ম পর্বে সর্বোচ্চ ২৯ জন প্রার্থী দিতে পারবেন। ২৯ জনের বেশি দিলে স্বয়ংক্রিয়ভাবে পরবর্তী পর্ব (Part 2, Part 3) হিসেবে পোস্ট হবে।\n\n"
        "৩️⃣ <b>ফোর্স সাবস্ক্রিপশন (অর্গানিক মেম্বার গ্রোথ):</b>\n"
        "• চ্যানেলে জয়েন না করা পর্যন্ত কেউ ভোট দিতে পারবে না।\n"
        "• ভোট দিতে আসলেই চ্যানেলে জয়েন করতে হবে, ফলে চ্যানেলের মেম্বার সংখ্যা অত্যন্ত দ্রুত বৃদ্ধি পায়।\n\n"
        "৪️⃣ <b>ডায়নামিক লাইভ রেজাল্ট ও বাটন আইকন:</b>\n"
        "• ভোট পড়ার সাথে সাথে বাটন টেক্সট ও পার্সেন্টেজ রিয়েল-টাইমে লাইভ আপডেট হয়।\n"
        "• <b>/icons</b> কমান্ড দিয়ে ১৫+ প্রিমিয়াম ডিজাইনের বাটন আইকন থিম বেছে নিতে পারবেন।\n\n"
        "৫️⃣ <b>অটো উইনার ঘোষণা ও পুরস্কার ক্লেইম:</b>\n"
        "• পোল শেষ হলে শীর্ষ বিজয়ীদের মেধা তালিকা চ্যানেলে স্বয়ংক্রিয়ভাবে ব্রডকাস্ট হবে।\n"
        "• ক্লেইম অপশনে গিভঅ্যাওয়ে হোস্টের প্রোফাইল লিংক স্বয়ংক্রিয়ভাবে যুক্ত থাকবে।\n"
        "• সমাপ্ত পোল ২ দিন (৪৮ ঘণ্টা) পর স্বয়ংক্রিয়ভাবে মুছে যাবে।\n\n"
        "৬️⃣ <b>অ্যান্টি-চিট শিল্ড ও নিরাপত্তা:</b>\n"
        "• ১ জন ভোটার কেবল ১ বারই ভোট দিতে পারবেন। স্প্যাম ও বট ভোট ১০০% ব্লক।\n"
        "• চ্যানেল আইসোলেশন: আপনি যে চ্যানেল যুক্ত করবেন কেবল আপনিই সেখানে পোল দিতে পারবেন।\n\n"
        "📌 <b>প্রয়োজনীয় শর্টকাট কমান্ডসমূহ:</b>\n"
        "• <code>/start</code> - মূল মেনু ও ড্যাশবোর্ড\n"
        "• <code>/newpoll</code> - নতুন পোল তৈরি করুন\n"
        "• <code>/mypolls</code> - আপনার সমস্ত পোল তালিকা ও লাইভ কন্ট্রোল\n"
        "• <code>/icons</code> - বাটন আইকন স্টাইল পরিবর্তন\n"
        "• <code>/language</code> - ভাষা পরিবর্তন (বাংলা / English / হিন্দি)\n"
        "• <code>/cancel</code> - যেকোনো চলমান প্রক্রিয়া বাতিল\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ <b>Powered by:</b> {bot_username}"
    ),
    # 🔘 Button Labels
    "btn_main_create": "➕ নতুন পোল তৈরি করুন",
    "btn_main_mypolls": "📊 আমার পোলসমূহ",
    "btn_main_icons": "🎨 বাটন আইকন স্টাইল",
    "btn_main_lang": "🌐 ভাষা পরিবর্তন",
    "btn_main_help": "ℹ️ ব্যবহারের গাইড",
    "btn_main_addchannel": "📢 চ্যানেলে বট যুক্ত করুন (১-ক্লিক) ➔",
    "btn_fsub_join": "📢 চ্যানেলে জয়েন করুন ➔",
    "tpl_vote_btn_format": "{icon}{name} • {votes}"
}


DEFAULTS_EN: Dict[str, str] = {
    "tpl_start": (
        '<tg-emoji emoji-id="5323642109767460983">🏠</tg-emoji> <b>Start / Main Menu</b> • <b>PRO POLL ENGINE v3.5</b>\n'
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Welcome, <b>{user_name}</b>!\n"
        "Fast and secure channel polling & contest platform.\n\n"
        "<b>Key Features:</b>\n"
        '• <tg-emoji emoji-id="5202167764483076994">🎯</tg-emoji> <b>Force Sub:</b> Lock votes until members join\n'
        '• <tg-emoji emoji-id="6271459718896554468">⚡</tg-emoji> <b>Live Scores:</b> Real-time button percentages\n'
        '• <tg-emoji emoji-id="5188344996356448758">🏆</tg-emoji> <b>Auto Rankings:</b> Instant winner calculations\n'
        '• <tg-emoji emoji-id="5201762530023733712">🎨</tg-emoji> <b>Icon Styles:</b> Premium button themes\n'
        '• <tg-emoji emoji-id="6050646916109179497">🛡️</tg-emoji> <b>7-Layer Active Security:</b> Duplicate vote protection\n'
        '• <tg-emoji emoji-id="5296369303661067030">🔒</tg-emoji> <b>Channel Isolation:</b> Strict authenticated access\n\n'
        "<i>Select an option below to get started:</i>"
    ),
    "tpl_poll_card": (
        '<tg-emoji emoji-id="5202167764483076994">📊</tg-emoji> <b>{title}</b>\n'
        "━━━━━━━━━━━━━━━━━━━━\n"
        '<tg-emoji emoji-id="5837134496868077492">🗳️</tg-emoji> <i>Tap a button below to cast your vote:</i>\n\n'
        '⚠️ <b>Note:</b> You must be a member of this channel to vote.\n'
        "━━━━━━━━━━━━━━━━━━━━\n"
        '<tg-emoji emoji-id="6271459718896554468">⚡</tg-emoji> <b>Powered by:</b> {bot_username}'
    ),
    "tpl_poll_cta": (
        "⚡ Create Your Own Poll ➔"
    ),
    "tpl_fsub_alert": (
        "⚠️ Please join {channel} first to cast your vote!\n\n"
        "Join the channel and tap the vote button again."
    ),
    "tpl_vote_success": (
        "✅ Vote cast successfully for '{candidate}'!"
    ),
    "tpl_poll_ended": (
        '<tg-emoji emoji-id="5204244329631082615">🏁</tg-emoji> <b>{title}</b>\n'
        "━━━━━━━━━━━━━━━━━━━━\n"
        '<tg-emoji emoji-id="5226431245918942763">🏆</tg-emoji> <b>POLL ENDED!</b>\n\n'
        "{winner}\n"
        '<tg-emoji emoji-id="5837134496868077492">🗳️</tg-emoji> <b>Total Votes Cast:</b> <code>{votes}</code>\n'
        "━━━━━━━━━━━━━━━━━━━━\n"
        '<tg-emoji emoji-id="6179411633371095707">🎉</tg-emoji> Thank you all for participating!\n'
        '<tg-emoji emoji-id="6271459718896554468">⚡</tg-emoji> <b>Powered by:</b> {bot_username}'
    ),
    "tpl_winner_announcement": (
        '<tg-emoji emoji-id="5226431245918942763">🏆</tg-emoji> <b>OFFICIAL WINNERS ANNOUNCEMENT</b>\n'
        "━━━━━━━━━━━━━━━━━━━━\n"
        '📌 <b>{title}</b>\n\n'
        "{winners}\n\n"
        "{stats}\n\n"
        "{claim_info}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        '<tg-emoji emoji-id="6179411633371095707">🎉</tg-emoji> <i>Thank you to everyone who participated!</i>\n'
        '<tg-emoji emoji-id="6271459718896554468">⚡</tg-emoji> <b>Powered by:</b> {bot_username}'
    ),
    "tpl_prize_claim": (
        '<tg-emoji emoji-id="6271494293383286950">🎁</tg-emoji> <b>Prize Claim Information:</b>\n'
        '<tg-emoji emoji-id="5292109589456645419">📩</tg-emoji> <i>Winners must contact the host to claim reward:</i>\n'
        '👉 <b>Official Host:</b> {contact_link}'
    ),
    "tpl_anti_cheat_badge": (
        '<tg-emoji emoji-id="5202167764483076994">📊</tg-emoji> <b>Contest Statistics:</b>\n'
        '<tg-emoji emoji-id="5837134496868077492">🗳️</tg-emoji> <b>Total Verified Votes:</b> <code>{total_votes}</code>\n'
        '<tg-emoji emoji-id="6050646916109179497">🛡️</tg-emoji> <b>Anti-Cheat Status:</b> 100% Verified & Validated'
    ),
    "tpl_help": (
        '<tg-emoji emoji-id="5373098009640836781">📖</tg-emoji> <b>Complete Bot Guide & Instructions</b>\n'
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "1️⃣ <b>Add Bot to Channel (1-Click Admin):</b>\n"
        "• Add this bot as an <b>Administrator</b> in your Telegram channel.\n"
        "• Ensure 'Post Messages' permission is granted so the bot can publish polls.\n"
        "• Tap '📢 Add Bot to Channel (1-Click)' for instant 1-tap setup.\n\n"
        "2️⃣ <b>Create Poll & Add Candidates:</b>\n"
        "• Send <b>/newpoll</b> command or tap '➕ Create New Poll'.\n"
        "• Enter poll question/title and send candidate names (one per line).\n"
        "• Up to 29 candidates in Part 1. Adding more than 29 automatically creates multi-part polls (Part 2, Part 3).\n\n"
        "3️⃣ <b>Force Subscription (Viral Member Growth):</b>\n"
        "• Channel members must join your channel to vote.\n"
        "• Non-members will receive a prompt to join first, generating rapid viral growth.\n\n"
        "4️⃣ <b>Dynamic Live Results & Button Icons:</b>\n"
        "• Button scores and percentages update in real-time on every single vote.\n"
        "• Use <b>/icons</b> command to choose from 15+ premium button icon themes.\n\n"
        "5️⃣ <b>Automated Winners & Prize Claim:</b>\n"
        "• When a poll ends, winner rankings are automatically published to the channel.\n"
        "• Giveaway Host contact profile link is included for easy prize claiming.\n"
        "• Ended polls are automatically cleaned up after 2 days (48 hours).\n\n"
        "6️⃣ <b>Anti-Cheat Shield & Security:</b>\n"
        "• Strict 1-vote-per-user enforcement with anti-flood and anti-bot protection.\n"
        "• Channel Isolation: Only the user who connected a channel can post polls there.\n\n"
        "📌 <b>Helpful Shortcut Commands:</b>\n"
        "• <code>/start</code> - Main Menu & Dashboard\n"
        "• <code>/newpoll</code> - Create a new poll\n"
        "• <code>/mypolls</code> - View & manage all your created polls\n"
        "• <code>/icons</code> - Change button icon themes\n"
        "• <code>/language</code> - Switch language (Bangla / English / Hindi)\n"
        "• <code>/cancel</code> - Cancel any active creation wizard\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ <b>Powered by:</b> {bot_username}"
    ),
    # 🔘 Button Labels
    "btn_main_create": "➕ Create New Poll",
    "btn_main_mypolls": "📊 My Polls",
    "btn_main_icons": "🎨 Button Icons",
    "btn_main_lang": "🌐 Language",
    "btn_main_help": "ℹ️ Help & Guide",
    "btn_main_addchannel": "📢 Add Bot to Channel (1-Click) ➔",
    "btn_fsub_join": "📢 Join Channel to Vote ➔",
    "tpl_vote_btn_format": "{icon}{name} • {votes}"
}


DEFAULTS_HI: Dict[str, str] = {
    "tpl_start": (
        '<tg-emoji emoji-id="5323642109767460983">🏠</tg-emoji> <b>Start / Main Menu</b> • <b>PRO POLL ENGINE v3.5</b>\n'
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "स्वागत है, <b>{user_name}</b>!\n"
        "टेलीग्राम चैनलों के लिए सुरक्षित और तेज़ पोल प्लेटफॉर्म।\n\n"
        "<b>मुख्य विशेषताएं:</b>\n"
        '• <tg-emoji emoji-id="5202167764483076994">🎯</tg-emoji> <b>फ़ोर्स सदस्यता:</b> जुड़ने पर ही वोट मान्य\n'
        '• <tg-emoji emoji-id="6271459718896554468">⚡</tg-emoji> <b>लाइव स्कोर:</b> बटन पर रीयल-टाइम परिणाम\n'
        '• <tg-emoji emoji-id="5188344996356448758">🏆</tg-emoji> <b>ऑटो रैंकिंग:</b> समाप्ति पर स्वचालित विजेता\n'
        '• <tg-emoji emoji-id="5201762530023733712">🎨</tg-emoji> <b>आइकन स्टाइल:</b> १५+ प्रीमियम बटन थीम\n'
        '• <tg-emoji emoji-id="6050646916109179497">🛡️</tg-emoji> <b>सुरक्षा कवच:</b> स्पैम और नकली वोट सुरक्षा\n'
        '• <tg-emoji emoji-id="5296369303661067030">🔒</tg-emoji> <b>चैनल सुरक्षा:</b> शत-प्रतिशत निजी नियंत्रण\n\n'
        "<i>आरंभ करने के लिए नीचे दिए गए विकल्प चुनें:</i>"
    ),
    "tpl_poll_card": (
        "📊 <b>{title}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🗳 <i>वोट देने के लिए नीचे दिए गए बटन पर टैप करें:</i>\n\n"
        "⚠️ <b>सूचना:</b> वोट देने के लिए आपको चैनल का सदस्य होना आवश्यक है।\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ <b>Powered by:</b> {bot_username}"
    ),
    "tpl_poll_cta": (
        "⚡ अपना खुद का पोल बनाएं ➔"
    ),
    "tpl_fsub_alert": (
        "⚠️ वोट देने के लिए कृपया पहले {channel} चैनल जॉइन करें!\n\n"
        "जॉइन करने के बाद दोबारा वोट बटन दबाएं।"
    ),
    "tpl_vote_success": (
        "✅ '{candidate}' के लिए आपका वोट सफलतापूर्वक दर्ज कर लिया गया है!"
    ),
    "tpl_poll_ended": (
        "🏁 <b>{title}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🏆 <b>प्रतियोगिता समाप्त हो चुकी है!</b>\n\n"
        "{winner}\n"
        "🗳️ <b>कुल प्राप्त वोट:</b> <code>{votes}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🎉 भाग लेने के लिए सभी का धन्यवाद!\n"
        "⚡ <b>Powered by:</b> {bot_username}"
    ),
    "tpl_winner_announcement": (
        "🏆 <b>आधिकारिक विजेता घोषणा</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📌 <b>{title}</b>\n\n"
        "{winners}\n\n"
        "{stats}\n\n"
        "{claim_info}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🎉 <i>भाग लेने के लिए आप सभी का धन्यवाद!</i>\n"
        "⚡ <b>Powered by:</b> {bot_username}"
    ),
    "tpl_prize_claim": (
        "🎁 <b>पुरस्कार दावा एवं संपर्क:</b>\n"
        "📩 <i>सभी विजेता अपना इनाम प्राप्त करने हेतु संपर्क करें:</i>\n"
        "👉 <b>आधिकारिक होस्ट:</b> {contact_link}"
    ),
    "tpl_anti_cheat_badge": (
        "📊 <b>प्रतियोगिता सांख्यिकी:</b>\n"
        "🗳️ <b>कुल प्राप्त वोट:</b> <code>{total_votes}</code>\n"
        "🛡️ <b>एंटी-चीट स्थिति:</b> 100% सत्यापित एवं सुरक्षित"
    ),
    "tpl_help": (
        "📖 <b>बॉट उपयोग की संपूर्ण गाइड और नियम</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "1️⃣ <b>चैनल में बॉट जोड़ें (1-क्लिक एडमिन):</b>\n"
        "• बॉट को अपने टेलीग्राम चैनल में <b>Administrator</b> बनाएं।\n"
        "• 'Post Messages' अनुमति चालू रखें ताकि बॉट पोल पोस्ट कर सके।\n"
        "• सबसे आसान तरीके के लिए '📢 चैनल में बॉट जोड़ें (1-क्लिक)' बटन दबाएं।\n\n"
        "2️⃣ <b>नया पोल और उम्मीदवार जोड़ें:</b>\n"
        "• <b>/newpoll</b> कमांड भेजें या '➕ नया पोल बनाएं' चुनें।\n"
        "• पोल का शीर्षक और उम्मीदवारों के नाम प्रति पंक्ति एक लिखकर भेजें।\n"
        "• २९ से अधिक उम्मीदवार होने पर स्वचालित रूप से अगले भाग (Part 2) में बंट जाएगा।\n\n"
        "3️⃣ <b>फ़ोर्स सदस्यता (तेज़ सदस्य वृद्धि):</b>\n"
        "• वोट करने के लिए चैनल से जुड़ना अनिवार्य है, जिससे चैनल के सदस्य तेजी से बढ़ते हैं।\n\n"
        "4️⃣ <b>रीयल-टाइम स्कोर और बटन स्टाइल:</b>\n"
        "• प्रत्येक वोट के साथ बटन पर प्रतिशत लाइव अपडेट होता है।\n"
        "• <b>/icons</b> कमांड से १५+ प्रीमियम थीम में से अपनी पसंद का स्टाइल चुनें।\n\n"
        "5️⃣ <b>स्वचालित विजेता और इनाम दावा:</b>\n"
        "• पोल समाप्त होने पर शीर्ष विजेताओं की सूची चैनल में प्रकाशित होती है।\n"
        "• इनाम प्राप्त करने के लिए होस्ट का संपर्क लिंक स्वतः जुड़ जाता है।\n"
        "• समाप्त पोल २ दिन बाद स्वतः हट जाते हैं।\n\n"
        "📌 <b>उपयोगी कमांड्स:</b>\n"
        "• <code>/start</code> - मुख्य मेनू\n"
        "• <code>/newpoll</code> - नया पोल बनाएं\n"
        "• <code>/mypolls</code> - अपने सभी पोल्स देखें\n"
        "• <code>/icons</code> - आइकन स्टाइल बदलें\n"
        "• <code>/language</code> - भाषा बदलें\n"
        "• <code>/cancel</code> - प्रक्रिया रद्द करें\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ <b>Powered by:</b> {bot_username}"
    ),
    # 🔘 Button Labels
    "btn_main_create": "➕ नया पोल बनाएं",
    "btn_main_mypolls": "📊 मेरे पोल्स",
    "btn_main_icons": "🎨 बटन आइकन",
    "btn_main_lang": "🌐 भाषा",
    "btn_main_help": "ℹ️ सहायता एवं गाइड",
    "btn_main_addchannel": "📢 चैनल में बॉट जोड़ें (1-क्लिक) ➔",
    "btn_fsub_join": "📢 वोट करने के लिए चैनल जॉइन करें ➔",
    "tpl_vote_btn_format": "{icon}{name} • {votes}"
}


DEFAULTS_AR: Dict[str, str] = {
    "tpl_start": (
        '<tg-emoji emoji-id="5323642109767460983">🏠</tg-emoji> <b>Start / Main Menu</b> • <b>PRO POLL ENGINE v3.5 [ENTERPRISE PRO]</b>\n'
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "👑 <b>مرحبًا بك، {user_name}!</b>\n"
        "أقوى منصة آمنة واحترافية لإنشاء <b>الاستطلاعات والمسابقات الفيروسية</b> عبر تيليجرام.\n\n"
        "🛡️ <b>حالة النظام والأمان:</b>\n"
        "• 🟢 <b>محرك النظام:</b> نشط (استجابة فائقة السرعة)\n"
        "• 🛡️ <b>درع الأمان ومكافحة التلاعب:</b> نشط بـ 7 طبقات حماية\n"
        "• ⚡ <b>العداد المباشر:</b> مزامنة فورية بالمللي ثانية\n"
        "• 📢 <b>شبكة القنوات:</b> إرسال ونشر تلقائي بضغطة زر\n\n"
        "✨ <b>أبرز المزايا:</b>\n"
        '├ <tg-emoji emoji-id="5202167764483076994">🎯</tg-emoji> <b>الاشتراك الإجباري:</b> زيادة أعضاء قناتك تلقائيًا للتصويت\n'
        '├ <tg-emoji emoji-id="6271459718896554468">📊</tg-emoji> <b>أزرار تفاعلية فورية:</b> تحديث لحظي للأصوات والنسب\n'
        '├ <tg-emoji emoji-id="5188344996356448758">🏆</tg-emoji> <b>نظام الفائزين الذكي:</b> إعلان الفائزين وترتيبهم بدقة\n'
        '├ <tg-emoji emoji-id="5201762530023733712">🎨</tg-emoji> <b>تخصيص الأيقونات:</b> أكثر من 15 مظهرًا مميزًا\n'
        '└ <tg-emoji emoji-id="5296369303661067030">🔒</tg-emoji> <b>عزل القنوات:</b> أمان كامل وخصوصية تامة لقناتك\n\n'
        "👇 <i>اختر أحد الخيارات أدناه للمتابعة:</i>"
    ),
    "tpl_poll_card": (
        "📊 <b>{title}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🗳 <i>اضغط على أحد الأزرار أدناه للإدلاء بصوتك:</i>\n\n"
        "⚠️ <b>ملاحظة:</b> يجب أن تكون عضوًا في القناة لتتمكن من التصويت.\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ <b>Powered by:</b> {bot_username}"
    ),
    "tpl_poll_cta": (
        "⚡ أنشئ استطلاعك الخاص الآن ➔"
    ),
    "tpl_fsub_alert": (
        "⚠️ يرجى الانضمام إلى القناة {channel} أولاً لتتمكن من التصويت!\n\n"
        "انضم إلى القناة ثم اضغط على زر التصويت مرة أخرى."
    ),
    "tpl_vote_success": (
        "✅ تم تسجيل صوتك بنجاح لـ '{candidate}'!"
    ),
    "tpl_poll_ended": (
        "🏁 <b>{title}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🏆 <b>انتهى الاستطلاع!</b>\n\n"
        "{winner}\n"
        "🗳️ <b>إجمالي الأصوات:</b> <code>{votes}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🎉 شكرًا لجميع المشاركين!\n"
        "⚡ <b>Powered by:</b> {bot_username}"
    ),
    "tpl_winner_announcement": (
        "🏆 <b>الإعلان الرسمي عن الفائزين</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📌 <b>{title}</b>\n\n"
        "{winners}\n\n"
        "{stats}\n\n"
        "{claim_info}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🎉 <i>شكرًا لكل من شارك في هذا الاستطلاع!</i>\n"
        "⚡ <b>Powered by:</b> {bot_username}"
    ),
    "tpl_prize_claim": (
        "🎁 <b>معلومات استلام الجوائز والتواصل:</b>\n"
        "📩 <i>يرجى من الفائزين التواصل مع المنظم لاستلام الجوائز:</i>\n"
        "👉 <b>المسؤول:</b> {contact_link}"
    ),
    "tpl_anti_cheat_badge": (
        "📊 <b>إحصائيات المسابقة:</b>\n"
        "🗳️ <b>إجمالي الأصوات الموثقة:</b> <code>{total_votes}</code>\n"
        "🛡️ <b>حماية مكافحة التلاعب:</b> تم التحقق بنسبة 100%"
    ),
    "tpl_help": (
        "📖 <b>طريقة إنشاء استطلاع في قناتك:</b>\n\n"
        "1️⃣ قم بإضافة هذا البوت كـ <b>مسؤول (Administrator)</b> في قناتك.\n"
        "2️⃣ أرسل الأمر <b>/newpoll</b> هنا أو اضغط على <b>\"➕ إنشاء استطلاع جديد\"</b>.\n"
        "3️⃣ اكتب عنوان الاستطلاع وأسماء المرشحين ومعرّف القناة.\n"
        "4️⃣ سينشر البوت الاستطلاع فورًا في قناتك بأزرار تفاعلية!\n\n"
        "💡 <b>ملاحظة:</b> يجب على الأعضاء الاشتراك في قناتك ليتمكنوا من التصويت!"
    )
}

DEFAULTS_RU: Dict[str, str] = {
    "tpl_start": (
        '<tg-emoji emoji-id="5323642109767460983">🏠</tg-emoji> <b>Start / Main Menu</b> • <b>PRO POLL ENGINE v3.5 [ENTERPRISE PRO]</b>\n'
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "👑 <b>Добро пожаловать, {user_name}!</b>\n"
        "Самая мощная и безопасная платформа для создания <b>вирусных опросов и конкурсов</b> в Telegram.\n\n"
        "🛡️ <b>Безопасность и статус системы:</b>\n"
        "• 🟢 <b>Ядро системы:</b> Активно (Ultra Low-Latency)\n"
        "• 🛡️ <b>Защита от накрутки:</b> 7 уровней безопасности активны\n"
        "• ⚡ <b>Живой счетчик:</b> Мгновенная синхронизация голосов\n"
        "• 📢 <b>Сеть каналов:</b> Авто-публикация в 1 клик готова\n\n"
        "✨ <b>Возможности платформы:</b>\n"
        '├ <tg-emoji emoji-id="5202167764483076994">🎯</tg-emoji> <b>Обязательная подписка:</b> Взрывной рост подписчиков канала\n'
        '├ <tg-emoji emoji-id="6271459718896554468">📊</tg-emoji> <b>Интерактивные кнопки:</b> Мгновенное обновление счетчиков\n'
        '├ <tg-emoji emoji-id="5188344996356448758">🏆</tg-emoji> <b>Умное определение победителей:</b> Точный расчет и публикация\n'
        '├ <tg-emoji emoji-id="5201762530023733712">🎨</tg-emoji> <b>Стили иконок:</b> 15+ премиальных тем оформления\n'
        '└ <tg-emoji emoji-id="5296369303661067030">🔒</tg-emoji> <b>Изоляция каналов:</b> Полная защита от постороннего доступа\n\n'
        "👇 <i>Выберите действие ниже для продолжения:</i>"
    ),
    "tpl_poll_card": (
        "📊 <b>{title}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🗳 <i>Нажмите кнопку ниже, чтобы отдать свой голос:</i>\n\n"
        "⚠️ <b>Внимание:</b> Для голосования необходимо быть подписчиком канала.\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ <b>Powered by:</b> {bot_username}"
    ),
    "tpl_poll_cta": (
        "⚡ Создать свой опрос ➔"
    ),
    "tpl_fsub_alert": (
        "⚠️ Пожалуйста, сначала подпишитесь на канал {channel}, чтобы проголосовать!\n\n"
        "После подписки нажмите кнопку голосования снова."
    ),
    "tpl_vote_success": (
        "✅ Ваш голос за '{candidate}' успешно учтен!"
    ),
    "tpl_poll_ended": (
        "🏁 <b>{title}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🏆 <b>ОПРОС ЗАВЕРШЕН!</b>\n\n"
        "{winner}\n"
        "🗳️ <b>Всего голосов:</b> <code>{votes}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🎉 Спасибо всем за участие!\n"
        "⚡ <b>Powered by:</b> {bot_username}"
    ),
    "tpl_winner_announcement": (
        "🏆 <b>ОФИЦИАЛЬНЫЕ ИТОГИ И ПОБЕДИТЕЛИ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📌 <b>{title}</b>\n\n"
        "{winners}\n\n"
        "{stats}\n\n"
        "{claim_info}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🎉 <i>Спасибо всем за участие в голосовании!</i>\n"
        "⚡ <b>Powered by:</b> {bot_username}"
    ),
    "tpl_prize_claim": (
        "🎁 <b>Получение призов и контакты:</b>\n"
        "📩 <i>Победителям необходимо связаться с организатором:</i>\n"
        "👉 <b>Организатор:</b> {contact_link}"
    ),
    "tpl_anti_cheat_badge": (
        "📊 <b>Итоги голосования:</b>\n"
        "🗳️ <b>Всего верифицированных голосов:</b> <code>{total_votes}</code>\n"
        "🛡️ <b>Защита от накрутки:</b> 100% Проверено и подтверждено"
    ),
    "tpl_help": (
        "📖 <b>Как создать опрос в вашем канале:</b>\n\n"
        "1️⃣ Добавьте бота в ваш канал в качестве <b>Администратора</b> (с правом публикации сообщений).\n"
        "2️⃣ Отправьте команду <b>/newpoll</b> или нажмите <b>\"➕ Создать новый опрос\"</b>.\n"
        "3️⃣ Укажите заголовок опроса, имена участников и юзернейм канала.\n"
        "4️⃣ Бот мгновенно опубликует интерактивный опрос в вашем канале!\n\n"
        "💡 <b>Совет:</b> Для голосования пользователям потребуется подписаться на канал!"
    )
}

DESCRIPTIONS: Dict[str, Dict[str, str]] = {
    # 📢 Channel Broadcast Templates
    "tpl_poll_card": {
        "title": "📊 Channel Poll Card / চ্যানেলের পোল কার্ড",
        "category": "channel",
        "vars": "{title}, {bot_username}"
    },
    "tpl_poll_cta": {
        "title": "⚡ Poll Bottom Button / পোলের বাটন টেক্সট",
        "category": "channel",
        "vars": "{bot_username}"
    },
    "tpl_winner_announcement": {
        "title": "🏆 Official Winner Post / অফিশিয়াল বিজয়ী পোস্ট",
        "category": "channel",
        "vars": "{title}, {winners}, {stats}, {claim_info}, {bot_username}"
    },
    "tpl_prize_claim": {
        "title": "🎁 Prize Claim Block / পুরষ্কার দাবি বক্স",
        "category": "channel",
        "vars": "{contact_link}"
    },
    "tpl_anti_cheat_badge": {
        "title": "🛡️ Anti-Cheat & Stats / সিকিউরিটি ও ভোট অডিট",
        "category": "channel",
        "vars": "{total_votes}"
    },
    "tpl_poll_ended": {
        "title": "🏁 Poll Ended Card / সমাপ্ত পোল কার্ড",
        "category": "channel",
        "vars": "{title}, {winner}, {votes}, {bot_username}"
    },
    # 🤖 Bot UI & Alerts Templates
    "tpl_start": {
        "title": "🏠 Start Dashboard / স্টার্ট ড্যাশবোর্ড",
        "category": "bot",
        "vars": "{bot_username}, {user_name}"
    },
    "tpl_fsub_alert": {
        "title": "⚠️ Force Join Alert / জয়েন সতর্কবার্তা",
        "category": "bot",
        "vars": "{channel}"
    },
    "tpl_vote_success": {
        "title": "✅ Vote Success Alert / ভোট সফল পপ-আপ",
        "category": "bot",
        "vars": "{candidate}"
    },
    "tpl_help": {
        "title": "📖 Help & Guide / ব্যবহারের গাইড",
        "category": "bot",
        "vars": "{bot_username}"
    },
    # 🔘 Button Customization (A to Z Buttons & Emojis)
    "btn_main_create": {
        "title": "🔘 Create Poll Button / তৈরি বাটন",
        "category": "button",
        "vars": "None"
    },
    "btn_main_mypolls": {
        "title": "🔘 My Polls Button / আমার পোল বাটন",
        "category": "button",
        "vars": "None"
    },
    "btn_main_icons": {
        "title": "🔘 Button Icons / বাটন আইকন মেনু বাটন",
        "category": "button",
        "vars": "None"
    },
    "btn_main_lang": {
        "title": "🔘 Language Button / ভাষা বাটন",
        "category": "button",
        "vars": "None"
    },
    "btn_main_help": {
        "title": "🔘 Help Button / গাইড বাটন",
        "category": "button",
        "vars": "None"
    },
    "btn_main_addchannel": {
        "title": "🔘 Add Bot Button / চ্যানেল যুক্ত বাটন",
        "category": "button",
        "vars": "None"
    },
    "btn_fsub_join": {
        "title": "🔘 Force Join Button / জয়েন চ্যানেল বাটন",
        "category": "button",
        "vars": "None"
    },
    "tpl_vote_btn_format": {
        "title": "🔘 Vote Button Format / প্রার্থীর বাটন ফরম্যাট",
        "category": "button",
        "vars": "{icon}, {name}, {votes}"
    }
}


TEMPLATE_KEYS = list(DESCRIPTIONS.keys())

async def get_raw_template(key: str, lang: str = "bn") -> str:
    db_key = f"{key}_{lang}"
    if lang == "bn":
        default_val = DEFAULTS_BN.get(key, "")
    elif lang == "hi":
        default_val = DEFAULTS_HI.get(key, "") or DEFAULTS_EN.get(key, "")
    elif lang == "ar":
        default_val = DEFAULTS_AR.get(key, "") or DEFAULTS_EN.get(key, "")
    elif lang == "ru":
        default_val = DEFAULTS_RU.get(key, "") or DEFAULTS_EN.get(key, "")
    else:
        default_val = DEFAULTS_EN.get(key, "")
    val = await get_setting(db_key, default_val)
    return val or default_val


async def save_template_with_autotranslate(key: str, input_text: str) -> Tuple[str, str]:
    """
    Saves the edited text, detects its language, auto-translates to the other language,
    and stores BOTH 'bn' and 'en' templates in the database.
    Returns: (bn_text, en_text)
    """
    is_bn = detect_is_bengali(input_text)
    if is_bn:
        bn_text = input_text
        en_text = await translate_text_preserving_tags(input_text, "en")
    else:
        en_text = input_text
        bn_text = await translate_text_preserving_tags(input_text, "bn")

    await set_setting(f"{key}_bn", bn_text)
    await set_setting(f"{key}_en", en_text)
    return bn_text, en_text

async def set_custom_template(key: str, lang: str, text: str):
    """
    Directly sets a custom template for a specific language without auto-translation.
    Preserves exact custom text and Telegram Premium custom emoji tags.
    """
    await set_setting(f"{key}_{lang}", text)

async def reset_template(key: str):
    await set_setting(f"{key}_bn", DEFAULTS_BN.get(key, ""))
    await set_setting(f"{key}_en", DEFAULTS_EN.get(key, ""))


SUGGESTIONS_BN: Dict[str, str] = {

    "tpl_poll_card": (
        "✨ <b>{title}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🗳️ <i>আপনার পছন্দের প্রার্থীকে ভোট দিতে নিচের বাটনে চাপ দিন:</i>\n\n"
        "📢 <b>নিয়মাবলী ও সতর্কতা:</b>\n"
        "• ভোট কার্যকর হতে অবশ্যই আমাদের চ্যানেলে যুক্ত থাকতে হবে!\n"
        "• একজন ভোটার শুধুমাত্র একবারই ভোট দিতে পারবেন।\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ <b>Powered by:</b> {bot_username}"
    ),
    "tpl_poll_cta": (
        "⚡ নিজের চ্যানেলের জন্য পোল তৈরি করুন ➔"
    ),
    "tpl_winner_announcement": (
        "🏆 <b>অফিসিয়াল চূড়ান্ত ফলাফল ও বিজয়ী ঘোষণা</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📌 <b>{title}</b>\n\n"
        "{winners}\n\n"
        "{stats}\n\n"
        "{claim_info}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🎉 <i>কনটেস্টে অংশগ্রহণকারী এবং ভোট প্রদানকারী সবাইকে আন্তরিক ধন্যবাদ!</i>\n"
        "⚡ <b>Powered by:</b> {bot_username}"
    ),
    "tpl_prize_claim": (
        "🎁 <b>পুরস্কার দাবি ও যোগাযোগ / Prize Claim:</b>\n"
        "📩 <i>বিজয়ীগণ আপনার পুরস্কার ক্লেইম করতে নিম্নের হোস্ট এডমিনের সাথে যোগাযোগ করুন:</i>\n"
        "👉 <b>Giveaway Host:</b> {contact_link}"
    ),
    "tpl_anti_cheat_badge": (
        "📊 <b>কনটেস্ট পরিসংখ্যান:</b>\n"
        "🗳️ <b>সর্বমোট কাস্ট করা ভোট:</b> <code>{total_votes}</code> টি\n"
        "🛡️ <b>অ্যান্টি-চিট শিল্ড:</b> ১০০% ভেরিফাইড ও নিরপেক্ষ"
    ),
    "tpl_poll_ended": (
        "🏁 <b>{title}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🏆 <b>পোল সমাপ্ত হয়েছে!</b>\n\n"
        "{winner}\n"
        "🗳️ <b>সর্বমোট কাস্ট করা ভোট:</b> <code>{votes}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🎉 অংশগ্রহণকারী সবাইকে ধন্যবাদ!\n"
        "⚡ <b>Powered by:</b> {bot_username}"
    ),
    "tpl_start": DEFAULTS_BN["tpl_start"],
    "tpl_fsub_alert": DEFAULTS_BN["tpl_fsub_alert"],
    "tpl_vote_success": DEFAULTS_BN["tpl_vote_success"],
    "tpl_help": DEFAULTS_BN["tpl_help"],
    "btn_main_create": "✨ ➕ নতুন পোল তৈরি করুন",
    "btn_main_mypolls": "📊 আমার সমস্ত পোলসমূহ",
    "btn_main_icons": "🎨 বাটন প্রিমিয়াম আইকন থিম",
    "btn_main_lang": "🌐 ভাষা নির্ধারণ করুন",
    "btn_main_help": "📖 ব্যবহারের সম্পূর্ণ গাইড",
    "btn_main_addchannel": "📢 চ্যানেলে বট যুক্ত করুন (১-ট্যাপ) ➔",
    "btn_fsub_join": "📢 ভোট দিতে চ্যানেলে জয়েন করুন ➔",
    "tpl_vote_btn_format": "{icon}{name} • {votes}"
}

SUGGESTIONS_EN: Dict[str, str] = {
    "tpl_poll_card": (
        "✨ <b>{title}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🗳️ <i>Tap a button below to cast your vote:</i>\n\n"
        "📢 <b>Rules & Instructions:</b>\n"
        "• You must be a member of this channel for your vote to count!\n"
        "• Each member can vote only once.\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ <b>Powered by:</b> {bot_username}"
    ),
    "tpl_poll_cta": (
        "⚡ Create Your Own Poll ➔"
    ),
    "tpl_winner_announcement": (
        "🏆 <b>Official Final Results & Winner Announcement</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📌 <b>{title}</b>\n\n"
        "{winners}\n\n"
        "{stats}\n\n"
        "{claim_info}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🎉 <i>Special thanks to all participants and voters!</i>\n"
        "⚡ <b>Powered by:</b> {bot_username}"
    ),
    "tpl_prize_claim": (
        "🎁 <b>Prize Claim & Host Contact:</b>\n"
        "📩 <i>Winners, please reach out to our official giveaway host to claim your prize:</i>\n"
        "👉 <b>Giveaway Host:</b> {contact_link}"
    ),
    "tpl_anti_cheat_badge": (
        "📊 <b>Contest Statistics:</b>\n"
        "🗳️ <b>Total Verified Votes:</b> <code>{total_votes}</code>\n"
        "🛡️ <b>Anti-Cheat Shield:</b> 100% Genuine & Verified"
    ),
    "tpl_poll_ended": (
        "🏁 <b>{title}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🏆 <b>Poll Concluded!</b>\n\n"
        "{winner}\n"
        "🗳️ <b>Total Votes Cast:</b> <code>{votes}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🎉 Thanks to everyone who participated!\n"
        "⚡ <b>Powered by:</b> {bot_username}"
    ),
    "tpl_start": DEFAULTS_EN["tpl_start"],
    "tpl_fsub_alert": DEFAULTS_EN["tpl_fsub_alert"],
    "tpl_vote_success": DEFAULTS_EN["tpl_vote_success"],
    "tpl_help": DEFAULTS_EN["tpl_help"],
    "btn_main_create": "✨ ➕ Create New Poll",
    "btn_main_mypolls": "📊 My Active Polls",
    "btn_main_icons": "🎨 Button Icon Styles",
    "btn_main_lang": "🌐 Change Language",
    "btn_main_help": "📖 Bot Usage Guide",
    "btn_main_addchannel": "📢 Add Bot to Channel (1-Click) ➔",
    "btn_fsub_join": "📢 Join Channel to Vote ➔",
    "tpl_vote_btn_format": "{icon}{name} • {votes}"
}


def get_suggestion(key: str, lang: str = "bn") -> str:
    if lang == "bn":
        return SUGGESTIONS_BN.get(key) or DEFAULTS_BN.get(key, "")
    else:
        return SUGGESTIONS_EN.get(key) or DEFAULTS_EN.get(key, "")

# Pattern for capturing Telegram Premium custom emojis (<tg-emoji>) and Unicode emojis
TG_EMOJI_OR_UNICODE = re.compile(
    r'(<tg-emoji\b[^>]*>[\s\S]*?</tg-emoji>|[\U00010000-\U0010ffff\u2600-\u26ff\u2700-\u27bf\u2300-\u23ff\u2b50\u2b55\u200d\ufe0f]+)',
    re.IGNORECASE
)

def extract_leading_emoji(line: str) -> Optional[str]:
    stripped = line.strip()
    m = TG_EMOJI_OR_UNICODE.match(stripped)
    if m:
        return m.group(0).strip()
    return None

def replace_leading_emoji(line: str, new_emoji: str) -> str:
    stripped = line.strip()
    m = TG_EMOJI_OR_UNICODE.match(stripped)
    leading_space = line[:len(line) - len(line.lstrip())]
    if m:
        rest = stripped[m.end():].lstrip()
        return leading_space + new_emoji + " " + rest
    else:
        return leading_space + new_emoji + " " + stripped

def sync_emojis_between_texts(source_text: str, target_text: str) -> str:
    """
    Intelligently synchronizes emojis (including Telegram Premium <tg-emoji> tags)
    from source_text to target_text, preserving the linguistic content of target_text.
    """
    if not source_text or not target_text:
        return target_text

    src_lines = source_text.splitlines()
    tgt_lines = target_text.splitlines()

    # If line counts match exactly, do line-by-line sync
    if len(src_lines) == len(tgt_lines):
        new_tgt_lines = []
        for s_line, t_line in zip(src_lines, tgt_lines):
            s_strip = s_line.strip()
            t_strip = t_line.strip()
            if not s_strip or not t_strip or "━" in s_strip:
                new_tgt_lines.append(t_line)
                continue
            s_emoji = extract_leading_emoji(s_line)
            if s_emoji:
                new_tgt_lines.append(replace_leading_emoji(t_line, s_emoji))
            else:
                new_tgt_lines.append(t_line)
        return "\n".join(new_tgt_lines)

    # If line counts differ, map by variables and semantic structure
    var_map = {}
    for s_line in src_lines:
        s_emoji = extract_leading_emoji(s_line)
        if s_emoji:
            for v in re.findall(r"\{[a-zA-Z0-9_]+\}", s_line):
                var_map[v] = s_emoji

    src_extra_emojis = []
    for s_line in src_lines:
        s_strip = s_line.strip()
        if not s_strip or "━" in s_strip or re.search(r"\{[a-zA-Z0-9_]+\}", s_line):
            continue
        e = extract_leading_emoji(s_line)
        if e:
            src_extra_emojis.append(e)

    new_tgt_lines = []
    extra_idx = 0
    for t_line in tgt_lines:
        t_strip = t_line.strip()
        if not t_strip or "━" in t_strip:
            new_tgt_lines.append(t_line)
            continue

        vars_in_tgt = re.findall(r"\{[a-zA-Z0-9_]+\}", t_line)
        matched_var = next((v for v in vars_in_tgt if v in var_map), None)
        if matched_var:
            new_tgt_lines.append(replace_leading_emoji(t_line, var_map[matched_var]))
        elif extra_idx < len(src_extra_emojis):
            new_tgt_lines.append(replace_leading_emoji(t_line, src_extra_emojis[extra_idx]))
            extra_idx += 1
        else:
            new_tgt_lines.append(t_line)

    return "\n".join(new_tgt_lines)

async def sync_emojis_to_other_languages(key: str, source_text: str, source_lang: str = "bn"):
    """
    Propagates all emojis (Unicode + <tg-emoji>) from source_text to all other language templates.
    """
    target_langs = ["en", "hi", "ar", "ru"] if source_lang == "bn" else ["bn", "hi", "ar", "ru"]
    for l in target_langs:
        current_val = await get_raw_template(key, l)
        if current_val:
            updated_val = sync_emojis_between_texts(source_text, current_val)
            if updated_val and updated_val != current_val:
                await set_setting(f"{key}_{l}", updated_val)

async def apply_suggestion(key: str):
    """
    Applies the recommended suggestion for this template in both BN and EN,
    and automatically propagates emojis to other languages.
    """
    sug_bn = get_suggestion(key, "bn")
    sug_en = get_suggestion(key, "en")
    await set_setting(f"{key}_bn", sug_bn)
    await set_setting(f"{key}_en", sug_en)
    await sync_emojis_to_other_languages(key, sug_bn, source_lang="bn")

async def render_template_live_preview(key: str, lang: str = "bn") -> Tuple[str, Any]:
    """
    Renders a realistic live preview of the template with dummy data and interactive buttons,
    exactly as it will look in Telegram channels.
    """
    from datetime import datetime, timedelta
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    if key == "tpl_poll_card":
        mock_title = "🌟 সেরা কনটেন্ট ক্রিয়েটর নির্বাচন ২০২৬" if lang == "bn" else "🌟 Best Content Creator Contest 2026"
        mock_ends = (datetime.utcnow() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        mock_created = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        card_content = await render_poll_card(
            title=mock_title,
            bot_username="ProPoolMaking_bot",
            lang=lang,
            ends_at=mock_ends,
            created_at=mock_created,
            winner_count=2
        )
        
        banner = (
            "👁️ <b>[ LIVE CHANNEL PREVIEW / চ্যানেলের লাইভ প্রিভিউ ]</b>\n"
            "<i>(চ্যানেলে এই পোল কার্ডটি ঠিক নিচের মতো দেখতে লাগবে)</i>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
        )
        full_text = banner + card_content
        
        btn_c1 = "👑 ১ম প্রার্থী [ ৬৫% | ১২০ ভোট ]" if lang == "bn" else "👑 Candidate 1 [ 65% | 120 votes ]"
        btn_c2 = "🥈 ২য় প্রার্থী [ ৩৫% | ৬৫ ভোট ]" if lang == "bn" else "🥈 Candidate 2 [ 35% | 65 votes ]"
        btn_cta = "⚡ নিজের চ্যানেলের জন্য পোল তৈরি করুন ➔" if lang == "bn" else "⚡ Create Your Own Poll ➔"
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text=btn_c1, callback_data="dummy_vote_preview"),
                InlineKeyboardButton(text=btn_c2, callback_data="dummy_vote_preview")
            ],
            [
                InlineKeyboardButton(text=btn_cta, url="https://t.me/ProPoolMaking_bot")
            ],
            [
                InlineKeyboardButton(
                    text="🇧🇩 বাংলা প্রিভিউ" if lang != "bn" else "✅ 🇧🇩 বাংলা প্রিভিউ (সক্রিয়)",
                    callback_data=f"tpl_preview:{key}:bn"
                ),
                InlineKeyboardButton(
                    text="🇬🇧 English Preview" if lang != "en" else "✅ 🇬🇧 English Preview (Active)",
                    callback_data=f"tpl_preview:{key}:en"
                )
            ],
            [
                InlineKeyboardButton(text="✏️ Edit Bangla / বাংলা এডিট", callback_data=f"tpl_edit:{key}:bn"),
                InlineKeyboardButton(text="✏️ Edit English / ইংরেজি এডিট", callback_data=f"tpl_edit:{key}:en")
            ],
            [
                InlineKeyboardButton(text="🔙 Back to Edit Menu / এডিটে ফিরুন", callback_data=f"tpl_view:{key}")
            ]
        ])
        return full_text, kb
    elif key == "tpl_winner_announcement":
        mock_title = "🌟 সেরা কনটেন্ট ক্রিয়েটর নির্বাচন ২০২৬" if lang == "bn" else "🌟 Best Content Creator Contest 2026"
        mock_winners = (
            "🥇 <b>১ম স্থান:</b> আকাশ চৌধুরী (৭৫০ ভোট)\n🥈 <b>২য় স্থান:</b> তানভীর আহমেদ (৬২০ ভোট)"
            if lang == "bn" else
            "🥇 <b>1st Place:</b> Akash Chowdhury (750 votes)\n🥈 <b>2nd Place:</b> Tanvir Ahmed (620 votes)"
        )
        post_content = await render_winner_announcement(
            title=mock_title,
            winners_display=mock_winners,
            bot_username="ProPoolMaking_bot",
            total_votes=1370,
            lang=lang,
            contact_link="@AdminSupport"
        )
        banner = (
            "👁️ <b>[ LIVE CHANNEL PREVIEW / বিজয়ী ঘোষণার লাইভ প্রিভিউ ]</b>\n"
            "<i>(চ্যানেলে অফিসিয়াল বিজয়ী পোস্টটি ঠিক নিচের মতো দেখতে লাগবে)</i>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
        )
        full_text = banner + post_content
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🇧🇩 বাংলা প্রিভিউ" if lang != "bn" else "✅ 🇧🇩 বাংলা প্রিভিউ (সক্রিয়)",
                    callback_data=f"tpl_preview:{key}:bn"
                ),
                InlineKeyboardButton(
                    text="🇬🇧 English Preview" if lang != "en" else "✅ 🇬🇧 English Preview (Active)",
                    callback_data=f"tpl_preview:{key}:en"
                )
            ],
            [
                InlineKeyboardButton(text="✏️ Edit Bangla / বাংলা এডিট", callback_data=f"tpl_edit:{key}:bn"),
                InlineKeyboardButton(text="✏️ Edit English / ইংরেজি এডিট", callback_data=f"tpl_edit:{key}:en")
            ],
            [
                InlineKeyboardButton(text="🔙 Back to Edit Menu / এডিটে ফিরুন", callback_data=f"tpl_view:{key}")
            ]
        ])
        return full_text, kb
    else:
        raw_val = await get_raw_template(key, lang)
        banner = (
            f"👁️ <b>[ LIVE PREVIEW / লাইভ প্রিভিউ: {key} ]</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
        )
        full_text = banner + raw_val
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🇧🇩 বাংলা প্রিভিউ" if lang != "bn" else "✅ 🇧🇩 বাংলা প্রিভিউ (সক্রিয়)",
                    callback_data=f"tpl_preview:{key}:bn"
                ),
                InlineKeyboardButton(
                    text="🇬🇧 English Preview" if lang != "en" else "✅ 🇬🇧 English Preview (Active)",
                    callback_data=f"tpl_preview:{key}:en"
                )
            ],
            [
                InlineKeyboardButton(text="🔙 Back to Edit Menu / এডিটে ফিরুন", callback_data=f"tpl_view:{key}")
            ]
        ])
        return full_text, kb

# --- Formatters for handlers (accepting user's language) ---

async def render_start_text(bot_username: str, lang: str = "bn", user_name: str = "") -> str:
    tpl = await get_raw_template("tpl_start", lang)

    display_user = user_name or ("User" if lang == "en" else "ব্যবহারকারী")
    return tpl.replace("{bot_username}", bot_username).replace("{user_name}", display_user)

def format_datetime_readable(dt_str: Optional[str]) -> str:
    if not dt_str:
        return ""
    try:
        from datetime import datetime
        cleaned = str(dt_str).replace("T", " ")
        if "." in cleaned:
            cleaned = cleaned.split(".")[0]
        dt = datetime.strptime(cleaned, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%I:%M %p, %d %b")
    except Exception:
        return str(dt_str)

def format_timer_badge(ends_at: Optional[str], lang: str = "bn", created_at: Optional[str] = None) -> str:
    start_str = format_datetime_readable(created_at) if created_at else ""
    end_str = format_datetime_readable(ends_at) if ends_at else ""

    t_icon = '<tg-emoji emoji-id="5399850755337240950">⏱️</tg-emoji>'
    g_icon = '<tg-emoji emoji-id="5395542928909150340">🟢</tg-emoji>'
    r_icon = '<tg-emoji emoji-id="5136918320674505825">🔴</tg-emoji>'
    f_icon = '<tg-emoji emoji-id="5204244329631082615">🏁</tg-emoji>'
    h_icon = '<tg-emoji emoji-id="5399850755337240950">⏳</tg-emoji>'

    if ends_at:
        if lang == "bn":
            if start_str:
                return (
                    f"{t_icon} <b>ভোটিং সময়সূচি:</b>\n"
                    f"{g_icon} <b>শুরু:</b> <code>{start_str}</code>\n"
                    f"{r_icon} <b>শেষ:</b> <code>{end_str}</code>"
                )
            else:
                return f"{h_icon} <b>ভোটের শেষ সময়:</b> <code>{end_str}</code>"
        else:
            if start_str:
                return (
                    f"{t_icon} <b>Voting Schedule:</b>\n"
                    f"{g_icon} <b>Start:</b> <code>{start_str}</code>\n"
                    f"{r_icon} <b>End:</b> <code>{end_str}</code>"
                )
            else:
                return f"{h_icon} <b>Poll Deadline:</b> <code>{end_str}</code>"
    else:
        # Manual closure (No timer)
        if lang == "bn":
            if start_str:
                return (
                    f"{t_icon} <b>ভোটিং সময়সূচি:</b>\n"
                    f"{g_icon} <b>শুরু:</b> <code>{start_str}</code>\n"
                    f"{f_icon} <b>সমাপ্তি:</b> <code>ম্যানুয়াল সমাপ্তি</code>"
                )
            else:
                return f"{t_icon} <b>সময়সীমা:</b> ♾️ <code>ম্যানুয়াল সমাপ্তি</code>"
        else:
            if start_str:
                return (
                    f"{t_icon} <b>Voting Schedule:</b>\n"
                    f"{g_icon} <b>Start:</b> <code>{start_str}</code>\n"
                    f"{f_icon} <b>End:</b> <code>Manual Closure</code>"
                )
            else:
                return f"{t_icon} <b>Schedule:</b> ♾️ <code>Manual Closure</code>"

def to_bengali_num(n: Any) -> str:
    bn_digits = "০১২৩৪৫৬৭৮৯"
    return "".join(bn_digits[int(d)] if d.isdigit() else d for d in str(n))

def to_hindi_num(n: Any) -> str:
    hi_digits = "०१२३४५६७८९"
    return "".join(hi_digits[int(d)] if d.isdigit() else d for d in str(n))

async def render_poll_card(
    title: str,
    bot_username: str,
    lang: str = "bn",
    ends_at: Optional[str] = None,
    created_at: Optional[str] = None,
    winner_count: int = 1,
    creator_id: Optional[int] = None
) -> str:
    import html
    from bot.database.db import get_effective_credit
    tpl = await get_raw_template("tpl_poll_card", lang)
    custom_name, custom_url, _ = await get_effective_credit(creator_id)
    clean_user = custom_name.lstrip("@") if custom_name else (bot_username.lstrip("@") if bot_username else "ProPoolMaking_bot")
    credit_name = custom_name.strip() if custom_name else "@ProPoolMaking_bot"
    if not custom_url:
        custom_url = f"https://t.me/{clean_user}"

    credit_display = f'<a href="{custom_url}">{safe_html_preserve_tg_emoji(credit_name)}</a>'

    if "@{bot_username}" in tpl:
        tpl = tpl.replace("@{bot_username}", "{bot_username}")

    # Prevent nested <b><b>...</b></b> if user submitted bold title
    clean_tpl = tpl
    if "<b>{title}</b>" in clean_tpl and (title.strip().startswith("<b>") or title.strip().startswith("<strong>")):
        clean_tpl = clean_tpl.replace("<b>{title}</b>", "{title}")

    # Optimize fallback emojis inside <tg-emoji> so that if Telegram strips custom emoji in channels,
    # it displays full-color emoji (e.g. ✅) instead of monochrome text [V] on Windows Desktop.
    enhanced_title = re.sub(r'(<tg-emoji\b[^>]*>)\s*(\u2714\ufe0f|\u2714)\s*(</tg-emoji>)', r'\1✅\3', title)

    card_text = clean_tpl.replace("{title}", enhanced_title).replace("{bot_username}", credit_display)

    # Winner badge
    winner_badge = ""
    trophy_icon = '<tg-emoji emoji-id="5226431245918942763">🏆</tg-emoji>'
    if winner_count > 1:
        if lang == "en":
            winner_badge = f"{trophy_icon} <b>Winner Announcement:</b> Top {winner_count} Winners"
        elif lang == "hi":
            hi_n = to_hindi_num(winner_count)
            winner_badge = f"{trophy_icon} <b>विजेता घोषणा:</b> शीर्ष {hi_n} विजेता (Top {winner_count} Winners)"
        elif lang == "ar":
            winner_badge = f"{trophy_icon} <b>الفائزون:</b> أفضل {winner_count} فائزين (Top {winner_count} Winners)"
        elif lang == "ru":
            winner_badge = f"{trophy_icon} <b>Победители:</b> Топ-{winner_count} участников"
        else:
            bn_n = to_bengali_num(winner_count)
            winner_badge = f"{trophy_icon} <b>বিজয়ী ঘোষণা:</b> শীর্ষ {bn_n} জন (Top {winner_count} Winners)"

    timer_line = format_timer_badge(ends_at, lang=lang, created_at=created_at)

    info_blocks = []
    if winner_badge:
        info_blocks.append(winner_badge)
    if timer_line:
        info_blocks.append(timer_line)

    if info_blocks:
        joined_info = "\n\n".join(info_blocks)
        if "━━━━━━━━━━━━━━━━━━━━\n⚡ <b>Powered by:</b>" in card_text:
            card_text = card_text.replace(
                "━━━━━━━━━━━━━━━━━━━━\n⚡ <b>Powered by:</b>",
                f"{joined_info}\n━━━━━━━━━━━━━━━━━━━━\n⚡ <b>Powered by:</b>"
            )
        else:
            card_text += f"\n\n{joined_info}"

    return card_text

async def render_poll_cta(bot_username: str, lang: str = "bn", creator_id: Optional[int] = None) -> Tuple[str, str]:
    """Returns (button_text, button_url) with custom credit and custom button text support."""
    custom_name, custom_url, custom_btn = await get_effective_credit(creator_id)
    clean_user = custom_name.lstrip("@") if custom_name else (bot_username.lstrip("@") if bot_username else "ProPoolMaking_bot")

    if custom_btn and "sponsor" not in custom_btn.lower():
        btn_text = custom_btn.strip()
    else:
        tpl = await get_raw_template("tpl_poll_cta", lang)
        btn_text = tpl.replace("{bot_username}", f"@{clean_user}")

    if custom_url and custom_url != "https://t.me/ProPoolMaking_bot":
        btn_url = custom_url
    else:
        btn_url = f"https://t.me/{clean_user}?start=create_poll"

    return btn_text, btn_url

async def render_fsub_alert(channel: str, lang: str = "bn") -> str:
    tpl = await get_raw_template("tpl_fsub_alert", lang)
    return strip_tg_emoji_tags(tpl.replace("{channel}", channel))

async def render_vote_success(candidate: str, lang: str = "bn") -> str:
    tpl = await get_raw_template("tpl_vote_success", lang)
    return strip_tg_emoji_tags(tpl.replace("{candidate}", candidate))

async def render_poll_ended(
    title: str,
    winner: str,
    votes: int,
    bot_username: str,
    lang: str = "bn",
    created_at: Optional[str] = None,
    ended_at: Optional[str] = None,
    creator_id: Optional[int] = None,
    contact_username: Optional[str] = None
) -> str:
    import html
    from bot.database.db import get_effective_credit, get_user_default_contact
    tpl = await get_raw_template("tpl_poll_ended", lang)
    custom_name, custom_url, _ = await get_effective_credit(creator_id)
    clean_user = custom_name.lstrip("@") if custom_name else (bot_username.lstrip("@") if bot_username else "ProPoolMaking_bot")
    credit_name = custom_name.strip() if custom_name else "@ProPoolMaking_bot"
    if not custom_url:
        custom_url = f"https://t.me/{clean_user}"

    credit_display = f'<a href="{custom_url}">{safe_html_preserve_tg_emoji(credit_name)}</a>'

    if "@{bot_username}" in tpl:
        tpl = tpl.replace("@{bot_username}", "{bot_username}")

    card_text = tpl.replace("{title}", title).replace("{winner}", winner).replace("{votes}", str(votes)).replace("{bot_username}", credit_display)

    start_str = format_datetime_readable(created_at) if created_at else ""
    end_str = format_datetime_readable(ended_at) if ended_at else ""
    t_icon = '<tg-emoji emoji-id="5399850755337240950">⏱️</tg-emoji>'
    g_icon = '<tg-emoji emoji-id="5395542928909150340">🟢</tg-emoji>'
    f_icon = '<tg-emoji emoji-id="5204244329631082615">🏁</tg-emoji>'
    mail_icon = '<tg-emoji emoji-id="5292109589456645419">📩</tg-emoji>'
    rocket_icon = '<tg-emoji emoji-id="5445118546700954082">🚀</tg-emoji>'

    if start_str and end_str:
        lbl = "সময়সীমা" if lang == "bn" else ("समय सीमा" if lang == "hi" else "Timeline")
        start_lbl = "শুরু" if lang == "bn" else ("प्रारंभ" if lang == "hi" else "Start")
        end_lbl = "সমাপ্তি" if lang == "bn" else ("समाप्त" if lang == "hi" else "Ended")
        timeline_line = (
            f"{t_icon} <b>{lbl}:</b>\n"
            f"{g_icon} <b>{start_lbl}:</b> <code>{start_str}</code>\n"
            f"{f_icon} <b>{end_lbl}:</b> <code>{end_str}</code>"
        )
    elif end_str:
        lbl = "সমাপ্তির সময়" if lang == "bn" else ("समाप्ति समय" if lang == "hi" else "Ended At")
        timeline_line = f"{f_icon} <b>{lbl}:</b> <code>{end_str}</code>"
    else:
        timeline_line = ""

    # Giveaway Host Contact line
    clean_contact = contact_username.strip() if contact_username else ""
    if not clean_contact and creator_id:
        default_c = await get_user_default_contact(creator_id)
        if default_c:
            clean_contact = default_c.strip()

    contact_line = ""
    if clean_contact:
        c_raw = clean_contact.lstrip("@")
        if c_raw.startswith("id_") or c_raw.isdigit():
            num_id = c_raw.replace("id_", "")
            c_link = f'<a href="tg://user?id={num_id}">ID: {num_id}</a>'
        else:
            c_link = f'<a href="https://t.me/{c_raw}">@{c_raw}</a>'
        c_lbl = "Giveaway Host" if lang == "en" else ("गिवअवे होस्ट" if lang == "hi" else "গিভওয়ে হোস্ট")
        contact_line = f"{mail_icon} <b>{c_lbl}:</b> {c_link}"
    elif creator_id:
        c_link = f'<a href="tg://user?id={creator_id}">ID: {creator_id}</a>'
        c_lbl = "Giveaway Host" if lang == "en" else ("गिवअवे होस्ट" if lang == "hi" else "গিভওয়ে হোস্ট")
        contact_line = f"{mail_icon} <b>{c_lbl}:</b> {c_link}"

    # Bot viral promotional invite line
    if lang == "hi":
        promo_line = f"{rocket_icon} <b>अपने चैनल के लिए ऐसा पोल बनाने के लिए जुड़ें:</b> @{clean_user}"
    elif lang == "en":
        promo_line = f"{rocket_icon} <b>To create viral polls like this for your channel, join:</b> @{clean_user}"
    else:
        promo_line = f"{rocket_icon} <b>নিজের চ্যানেলের জন্য এমন পোল তৈরি করতে যুক্ত করুন:</b> @{clean_user}"

    middle_parts = []
    if contact_line:
        middle_parts.append(contact_line)
    if timeline_line:
        middle_parts.append(timeline_line)

    middle_block = "\n".join(middle_parts)
    footer_content = f"{middle_block}\n\n{promo_line}" if middle_block else promo_line

    if "━━━━━━━━━━━━━━━━━━━━\n🎉" in card_text:
        card_text = card_text.replace(
            "━━━━━━━━━━━━━━━━━━━━\n🎉",
            f"{footer_content}\n━━━━━━━━━━━━━━━━━━━━\n🎉"
        )
    elif "━━━━━━━━━━━━━━━━━━━━\n⚡" in card_text:
        card_text = card_text.replace(
            "━━━━━━━━━━━━━━━━━━━━\n⚡",
            f"{footer_content}\n━━━━━━━━━━━━━━━━━━━━\n⚡"
        )
    else:
        card_text += f"\n\n{footer_content}"

    return card_text




def _format_part_badge(part_num: int, lang: str) -> str:
    if not part_num:
        return ""
    if lang == "en":
        return f" <i>(Part {part_num})</i>"
    elif lang == "hi":
        return f" <i>(भाग {part_num})</i>"
    elif lang == "ar":
        return f" <i>(الجزء {part_num})</i>"
    elif lang == "ru":
        return f" <i>(Часть {part_num})</i>"
    else:
        return f" <i>(পর্ব {to_bengali_num(part_num)})</i>"


def format_winners_display(
    top_winners: List[Dict[str, Any]],
    lang: str = "bn",
    is_multi_part: Optional[bool] = None
) -> str:
    """
    Renders top winners formatted strictly descending from MAX votes to LOW votes.
    Supports Telegram Premium Custom Emojis (<tg-emoji> tags).
    If is_multi_part is True (or winners contain part_number > 1), origin parts are tagged.
    """
    crown_icon = '<tg-emoji emoji-id="6235252066554484059">👑</tg-emoji>'
    trophy_icon = '<tg-emoji emoji-id="5226431245918942763">🏆</tg-emoji>'
    party_icon = '<tg-emoji emoji-id="6179411633371095707">🎉</tg-emoji>'
    gold_icon = '<tg-emoji emoji-id="5226431245918942763">🥇</tg-emoji>'
    silver_icon = '<tg-emoji emoji-id="6181535395914718008">🥈</tg-emoji>'
    bronze_icon = '<tg-emoji emoji-id="5348084369217052513">🥉</tg-emoji>'
    medal_icon = '<tg-emoji emoji-id="6181535395914718008">🏅</tg-emoji>'
    star_icon = '<tg-emoji emoji-id="6181535395914718008">🎖️</tg-emoji>'

    if not top_winners:
        if lang == "en":
            return f"{crown_icon} <b>No winner determined</b> (0 votes cast)."
        elif lang == "hi":
            return f"{crown_icon} <b>कोई विजेता नहीं चुना गया</b> (0 वोट प्राप्त)।"
        elif lang == "ar":
            return f"{crown_icon} <b>لم يتم تحديد فائز</b> (0 أصوات)."
        elif lang == "ru":
            return f"{crown_icon} <b>Победитель не определен</b> (0 голосов)."
        else:
            return f"{crown_icon} <b>কোনো বিজয়ী নির্ধারিত হয়নি</b> (কোনো ভোট পড়েনি)।"

    if is_multi_part is None:
        is_multi_part = any(w.get("part_number", 1) > 1 for w in top_winners)

    # Strictly sort candidates descending: MAX votes -> LOW votes
    sorted_winners = sorted(
        top_winners,
        key=lambda c: c.get("votes_count", c.get("votes", 0)),
        reverse=True
    )

    medals = [gold_icon, silver_icon, bronze_icon, medal_icon, star_icon]
    lines = []
    if len(sorted_winners) > 1:
        if is_multi_part:
            if lang == "en":
                lines.append(f"{trophy_icon} <b>Top {len(sorted_winners)} Contest Winners (Across All Connected Parts):</b>")
            elif lang == "hi":
                lines.append(f"{trophy_icon} <b>शीर्ष {len(sorted_winners)} विजेता (सभी भागों को मिलाकर):</b>")
            elif lang == "ar":
                lines.append(f"{trophy_icon} <b>أفضل {len(sorted_winners)} فائزين (عبر جميع الأجزاء):</b>")
            elif lang == "ru":
                lines.append(f"{trophy_icon} <b>Топ-{len(sorted_winners)} победителей (по всем частям вместе):</b>")
            else:
                lines.append(f"{trophy_icon} <b>কনটেস্টের শীর্ষ {len(sorted_winners)} জন বিজয়ী (সকল পর্ব মিলিয়ে):</b>")
        else:
            if lang == "en":
                lines.append(f"{trophy_icon} <b>Top {len(sorted_winners)} Contest Winners (Ranked Max to Low):</b>")
            elif lang == "hi":
                lines.append(f"{trophy_icon} <b>शीर्ष {len(sorted_winners)} विजेता (अधिकतम से न्यूनतम):</b>")
            elif lang == "ar":
                lines.append(f"{trophy_icon} <b>أفضل {len(sorted_winners)} فائزين (من الأعلى إلى الأدنى):</b>")
            elif lang == "ru":
                lines.append(f"{trophy_icon} <b>Топ-{len(sorted_winners)} победителей (по убыванию):</b>")
            else:
                lines.append(f"{trophy_icon} <b>কনটেস্টের শীর্ষ {len(sorted_winners)} জন বিজয়ী (সর্বোচ্চ থেকে ক্রমানুসারে):</b>")

        for idx, w in enumerate(sorted_winners):
            medal = medals[idx] if idx < len(medals) else star_icon
            name = safe_html_preserve_tg_emoji(w["name"])
            votes = w.get("votes_count", w.get("votes", 0))
            part_tag = _format_part_badge(w.get("part_number", 1), lang) if is_multi_part else ""

            if lang == "en":
                v_label = "vote" if votes == 1 else "votes"
                lines.append(f"{medal} <b>#{idx+1} Place:</b> {name}{part_tag} (<code>{votes}</code> {v_label})")
            elif lang == "hi":
                lines.append(f"{medal} <b>#{idx+1} स्थान:</b> {name}{part_tag} (<code>{votes}</code> वोट)")
            elif lang == "ar":
                lines.append(f"{medal} <b>المركز {idx+1}:</b> {name}{part_tag} (<code>{votes}</code> أصوات)")
            elif lang == "ru":
                lines.append(f"{medal} <b>{idx+1}-е место:</b> {name}{part_tag} (<code>{votes}</code> голосов)")
            else:
                lines.append(f"{medal} <b>{idx+1}ম স্থান:</b> {name}{part_tag} (<code>{votes}</code> ভোট)")

        congrats = (
            f"{party_icon} <i>Congratulations to all winners!</i>"
            if lang == "en" else (
                f"{party_icon} <i>सभी विजेताओं को हार्दिक बधाई!</i>"
                if lang == "hi" else
                f"{party_icon} <i>অভিনন্দন সকল বিজয়ীদের!</i>"
            )
        )
        lines.append(congrats)
        return "\n".join(lines)
    else:
        w = sorted_winners[0]
        name = safe_html_preserve_tg_emoji(w["name"])
        votes = w.get("votes_count", w.get("votes", 0))
        part_tag = _format_part_badge(w.get("part_number", 1), lang) if is_multi_part else ""

        if lang == "en":
            v_label = "vote" if votes == 1 else "votes"
            return (
                f"{crown_icon} <b>#1 Winner:</b> {name}{part_tag} (<code>{votes}</code> {v_label})\n"
                f"{party_icon} Congratulations to the top winner!"
            )
        elif lang == "hi":
            return (
                f"{crown_icon} <b>#1 विजेता:</b> {name}{part_tag} (<code>{votes}</code> वोट)\n"
                f"{party_icon} शीर्ष विजेता को हार्दिक बधाई!"
            )
        elif lang == "ar":
            return (
                f"{crown_icon} <b>#1 الفائز:</b> {name}{part_tag} (<code>{votes}</code> أصوات)\n"
                f"{party_icon} مبروك للفائز بالمركز الأول!"
            )
        elif lang == "ru":
            return (
                f"{crown_icon} <b>#1 Победитель:</b> {name}{part_tag} (<code>{votes}</code> голосов)\n"
                f"{party_icon} Поздравляем главного победителя!"
            )
        else:
            return (
                f"{crown_icon} <b>১ম বিজয়ী:</b> {name}{part_tag} (<code>{votes}</code> ভোট)\n"
                f"{party_icon} অভিনন্দন সর্বোচ্চ ভোটপ্রাপ্ত ক্রিয়েটরকে!"
            )


async def render_winner_announcement(
    title: str,
    top_winners: List[Dict[str, Any]],
    total_votes: int,
    bot_username: str,
    lang: str = "bn",
    creator_id: Optional[int] = None,
    contact_username: Optional[str] = None,
    is_multi_part: Optional[bool] = None
) -> str:
    """
    Renders the full winner announcement post for the channel with title,
    medals, vote counts, prize claim contact info, and brand credit watermark.
    """
    import html
    from bot.database.db import get_effective_credit, get_user_default_contact
    custom_name, custom_url, _ = await get_effective_credit(creator_id)
    clean_user = custom_name.lstrip("@") if custom_name else (bot_username.lstrip("@") if bot_username else "ProPoolMaking_bot")
    credit_name = custom_name.strip() if custom_name else "@ProPoolMaking_bot"
    if not custom_url:
        custom_url = f"https://t.me/{clean_user}"
    credit_display = f'<a href="{custom_url}">{safe_html_preserve_tg_emoji(credit_name)}</a>'

    # Determine contact username
    clean_contact = contact_username.strip() if contact_username else ""
    if not clean_contact and creator_id:
        default_c = await get_user_default_contact(creator_id)
        if default_c:
            clean_contact = default_c.strip()

    winners_text = format_winners_display(top_winners, lang=lang, is_multi_part=is_multi_part)

    tpl_winner = await get_raw_template("tpl_winner_announcement", lang=lang)
    tpl_claim = await get_raw_template("tpl_prize_claim", lang=lang)
    tpl_stats = await get_raw_template("tpl_anti_cheat_badge", lang=lang)

    # Build Prize Claim Section
    if clean_contact:
        c_raw = clean_contact.lstrip("@")
        if c_raw.startswith("id_") or c_raw.isdigit():
            num_id = c_raw.replace("id_", "")
            contact_link = f'<a href="tg://user?id={num_id}">ID: {num_id}</a>'
        else:
            contact_link = f'<a href="https://t.me/{c_raw}">@{c_raw}</a>'
        claim_box = tpl_claim.replace("{contact_link}", contact_link)
    elif creator_id:
        contact_link = f'<a href="tg://user?id={creator_id}">Host (ID: {creator_id})</a>'
        claim_box = tpl_claim.replace("{contact_link}", contact_link)
    else:
        if lang == "en":
            claim_box = (
                "<b>Prize Claim Information:</b>\n"
                "📩 <i>Winners, please contact the channel administrators to claim your reward!</i>"
            )
        elif lang == "hi":
            claim_box = (
                "<b>पुरस्कार दावा:</b>\n"
                "📩 <i>विजेता कृपया अपना पुरस्कार प्राप्त करने हेतु चैनल एडमिन से संपर्क करें!</i>"
            )
        elif lang == "ar":
            claim_box = (
                "<b>استلام الجوائز:</b>\n"
                "📩 <i>يرجى من الفائزين التواصل مع إدارة القناة لاستلام الجوائز!</i>"
            )
        elif lang == "ru":
            claim_box = (
                "<b>Получение призов:</b>\n"
                "📩 <i>Победители, свяжитесь с администрацией канала для получения награды!</i>"
            )
        else:
            claim_box = (
                "<b>পুরস্কার দাবি ও যোগাযোগ:</b>\n"
                "📩 <i>বিজয়ীগণ আপনার পুরস্কার গ্রহণের জন্য চ্যানেল এডমিনের সাথে যোগাযোগ করুন!</i>"
            )

    stats_box = tpl_stats.replace("{total_votes}", str(total_votes))

    if "{winners}" in tpl_winner:
        return (
            tpl_winner
            .replace("{title}", safe_html_preserve_tg_emoji(title))
            .replace("{winners}", winners_text)
            .replace("{stats}", stats_box)
            .replace("{claim_info}", claim_box)
            .replace("{bot_username}", credit_display)
        )

    # Fallback to standard structure if user customized template without {winners} placeholder
    if lang == "en":
        header = "🏆 <b>OFFICIAL WINNERS ANNOUNCEMENT</b>"
        vote_line = (
            f"📊 <b>Contest Statistics:</b>\n"
            f"🗳️ <b>Total Verified Votes:</b> <code>{total_votes}</code>\n"
            f"🛡️ <b>Anti-Cheat Status:</b> 100% Verified & Validated"
        )
        footer = "🎉 <i>Thank you to everyone who participated!</i>"
    elif lang == "hi":
        header = "🏆 <b>आधिकारिक विजेता घोषणा</b>"
        vote_line = (
            f"📊 <b>प्रतियोगिता सांख्यिकी:</b>\n"
            f"🗳️ <b>कुल प्राप्त वोट:</b> <code>{total_votes}</code>\n"
            f"🛡️ <b>एंटी-चीट स्थिति:</b> 100% सत्यापित एवं सुरक्षित"
        )
        footer = "🎉 <i>भाग लेने के लिए आप सभी का धन्यवाद!</i>"
    elif lang == "ar":
        header = "🏆 <b>الإعلان الرسمي عن الفائزين</b>"
        vote_line = (
            f"📊 <b>إحصائيات المسابقة:</b>\n"
            f"🗳️ <b>إجمالي الأصوات الموثقة:</b> <code>{total_votes}</code>\n"
            f"🛡️ <b>حماية مكافحة التلاعب:</b> تم التحقق بنسبة 100%"
        )
        footer = "🎉 <i>شكرًا لكل من شارك في هذا الاستطلاع!</i>"
    elif lang == "ru":
        header = "🏆 <b>ОФИЦИАЛЬНЫЕ ИТОГИ И ПОБЕДИТЕЛИ</b>"
        vote_line = (
            f"📊 <b>Итоги голосования:</b>\n"
            f"🗳️ <b>Всего верифицированных голосов:</b> <code>{total_votes}</code>\n"
            f"🛡️ <b>Защита от накрутки:</b> 100% Проверено и подтверждено"
        )
        footer = "🎉 <i>Спасибо всем за участие в голосовании!</i>"
    else:
        header = "🏆 <b>অফিসিয়াল বিজয়ী ঘোষণা</b>"
        vote_line = (
            f"📊 <b>কনটেস্ট পরিসংখ্যান:</b>\n"
            f"🗳️ <b>সর্বমোট কাস্ট করা ভোট:</b> <code>{total_votes}</code> টি\n"
            f"🛡️ <b>অ্যান্টি-চিট স্ট্যাটাস:</b> ১০০% ভেরিফাইড ও নিরপেক্ষ"
        )
        footer = "🎉 <i>কনটেস্টে অংশগ্রহণকারী এবং ভোট প্রদানকারী সবাইকে ধন্যবাদ!</i>"

    return (
        f"{header}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>{safe_html_preserve_tg_emoji(title)}</b>\n\n"
        f"{winners_text}\n\n"
        f"{vote_line}\n\n"
        f"{claim_box}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{footer}\n"
        f"⚡ <b>Powered by:</b> {credit_display}"
    )


async def render_help_text(bot_username: str, lang: str = "bn") -> str:
    tpl = await get_raw_template("tpl_help", lang=lang)
    return tpl.replace("{bot_username}", bot_username)


async def render_custom_winner_announcement(
    custom_text: str,
    bot_username: str,
    creator_id: Optional[int] = None,
    contact_username: Optional[str] = None
) -> str:
    """
    Appends the brand credit footer to any custom text submitted by the admin,
    ensuring brand credit and link are 100% preserved, plus optional prize claim contact info.
    """
    import html
    from bot.database.db import get_effective_credit, get_user_default_contact
    custom_name, custom_url, _ = await get_effective_credit(creator_id)
    clean_user = custom_name.lstrip("@") if custom_name else (bot_username.lstrip("@") if bot_username else "ProPoolMaking_bot")
    credit_name = custom_name.strip() if custom_name else "@ProPoolMaking_bot"
    if not custom_url:
        custom_url = f"https://t.me/{clean_user}"
    credit_display = f'<a href="{custom_url}">{safe_html_preserve_tg_emoji(credit_name)}</a>'

    clean_contact = contact_username.strip().lstrip("@") if contact_username else ""
    if not clean_contact and creator_id:
        default_c = await get_user_default_contact(creator_id)
        if default_c:
            clean_contact = default_c.strip().lstrip("@")

    contact_block = ""
    if clean_contact and f"@{clean_contact}" not in custom_text:
        contact_block = (
            f"\n\n🎁 <b>Prize Claim / পুরষ্কার যোগাযোগ:</b> <a href=\"https://t.me/{clean_contact}\">@{clean_contact}</a>"
        )

    return (
        f"{custom_text}{contact_block}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ <b>Powered by:</b> {credit_display}"
    )


