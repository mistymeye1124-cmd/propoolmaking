import unicodedata
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict, Any, Optional, Tuple

def name_has_leading_emoji(text: str) -> bool:
    if not text:
        return False
    first = text.strip()[0]
    cp = ord(first)
    if cp in (0x200D, 0x20E3, 0xFE0F):
        return True
    if 0x1F000 <= cp <= 0x1FAFF or 0x2600 <= cp <= 0x27BF or 0x2300 <= cp <= 0x23FF or 0x2B50 <= cp <= 0x2B55:
        return True
    return unicodedata.category(first) in ("So", "Sk")

def get_candidate_icon(
    cand: Dict[str, Any],
    all_candidates: List[Dict[str, Any]],
    style: str = "dynamic",
    is_closed: bool = False
) -> str:
    name = cand.get("name", "").strip()
    votes = cand.get("votes_count", 0)
    
    # If candidate name already starts with an emoji, don't prepend another emoji
    if name_has_leading_emoji(name):
        return ""

    if is_closed:
        max_votes = max((c.get("votes_count", 0) for c in all_candidates), default=0)
        if max_votes > 0:
            distinct_sorted = sorted(list(set(c.get("votes_count", 0) for c in all_candidates if c.get("votes_count", 0) > 0)), reverse=True)
            if len(distinct_sorted) > 0 and votes == distinct_sorted[0]:
                return "🏆 "
            elif len(distinct_sorted) > 1 and votes == distinct_sorted[1]:
                return "🥈 "
            elif len(distinct_sorted) > 2 and votes == distinct_sorted[2]:
                return "🥉 "
            elif votes > 0:
                return "🔥 "
        # For non-winning or zero-vote candidates, fall through to preserve chosen style (e.g. 💎, ⚡, ⭐, etc.)

    if style == "dynamic":
        max_votes = max((c.get("votes_count", 0) for c in all_candidates), default=0)
        if votes > 0:
            distinct_sorted_votes = sorted(list(set(c.get("votes_count", 0) for c in all_candidates if c.get("votes_count", 0) > 0)), reverse=True)
            if len(distinct_sorted_votes) > 0 and votes == distinct_sorted_votes[0]:
                return "👑 "
            elif len(distinct_sorted_votes) > 1 and votes == distinct_sorted_votes[1]:
                return "🥈 "
            elif len(distinct_sorted_votes) > 2 and votes == distinct_sorted_votes[2]:
                return "🥉 "
            else:
                return "🔥 "
        return "🗳️ "
    elif style in EMOJI_ID_TO_ICON:
        return f"{EMOJI_ID_TO_ICON[style]} "
    elif style == "ballot":
        return "🗳️ "
    elif style == "diamond":
        return "💎 "
    elif style == "sparkle":
        return "✨ "
    elif style == "zap":
        return "⚡ "
    elif style == "fire":
        return "🔥 "
    elif style == "star":
        return "⭐ "
    elif style == "target":
        return "🎯 "
    elif style == "radio":
        return "🔘 "
    elif style == "sleek":
        return "🔹 "
    elif style == "rocket":
        return "🚀 "
    elif style == "trophy":
        return "🏆 "
    elif style == "shield":
        return "🔰 "
    elif style == "neon":
        return "🟢 "
    elif style.startswith("custom_tg:"):
        parts = style.split(":")
        emoji_id = parts[1] if len(parts) > 1 else ""
        if emoji_id in EMOJI_ID_TO_ICON:
            return f"{EMOJI_ID_TO_ICON[emoji_id]} "
        fallback = parts[2] if len(parts) > 2 and parts[2] and parts[2] not in ("main", "admin") else ""
        if fallback:
            return f"{fallback} "
        return "✨ "
    elif style.startswith("custom:"):
        custom_icon = style[7:].strip()
        return f"{custom_icon} " if custom_icon else "✨ "
    elif style == "profile":
        return "👤 "
    else:
        return "🗳️ "

def strip_all_emojis(text: str) -> str:
    """
    Strips all unicode emojis, symbols, and variation selectors from a string
    so that only clean text remains without duplicate icons.
    """
    if not text:
        return ""
    chars = []
    for c in text:
        cat = unicodedata.category(c)
        cp = ord(c)
        if (
            cat in ('So', 'Sk') or
            0x1F000 <= cp <= 0x1FAFF or
            0x2600 <= cp <= 0x27BF or
            0x2300 <= cp <= 0x23FF or
            0x2B50 <= cp <= 0x2B55 or
            0xFE00 <= cp <= 0xFE0F or
            cp == 0x200D or cp == 0x20E3
        ):
            continue
        chars.append(c)
    cleaned = ''.join(chars).strip()
    return cleaned if cleaned else text.strip()

STYLE_PRESETS = [
    ("dynamic", "Dynamic Leader", "6235252066554484059", "👑"),
    ("diamond", "VIP Diamond", "6271494293383286950", "💎"),
    ("zap", "Lightning Zap", "6271459718896554468", "⚡"),
    ("star", "Golden Star", "6181535395914718008", "⭐"),
    ("radio", "Radio Circle", "5348084369217052513", "🔘"),
    ("rocket", "Rocket Speed", "5445118546700954082", "🚀"),
    ("shield", "Verified Shield", "5465154440287757794", "🔰"),
    ("ballot", "Ballot Box", "5837134496868077492", "🗳️"),
    ("sparkle", "Modern Sparkle", "6179411633371095707", "✨"),
    ("fire", "Fire Trend", "5136918320674505825", "🔥"),
    ("target", "Bullseye Target", "5310278924616356636", "🎯"),
    ("sleek", "Sleek Rhombus", "5393383127294953991", "🔹"),
    ("trophy", "Champion Trophy", "5226431245918942763", "🏆"),
    ("neon", "Neon Dot", "5395542928909150340", "🟢"),
]

STYLE_CUSTOM_EMOJIS = {code: emoji_id for code, _, emoji_id, _ in STYLE_PRESETS}
EMOJI_ID_TO_ICON = {emoji_id: icon for _, _, emoji_id, icon in STYLE_PRESETS}

def resolve_candidate_icon_and_emoji(
    cand: Dict[str, Any],
    all_candidates: List[Dict[str, Any]],
    style: str = "dynamic",
    is_closed: bool = False
) -> Tuple[str, Optional[str]]:
    """
    Resolves both the display text icon and any Telegram Premium custom emoji ID.
    Returns: (icon_str, custom_emoji_id_or_none)
    """
    icon_text = get_candidate_icon(cand, all_candidates, style=style, is_closed=is_closed)
    
    # 1. Closed Poll winner custom emoji IDs
    if is_closed:
        if icon_text == "🏆 ":
            return icon_text, "5226431245918942763"
        elif icon_text == "🥈 ":
            return icon_text, "6181535395914718008"
        elif icon_text == "🥉 ":
            return icon_text, "5348084369217052513"
        elif icon_text == "🔥 ":
            return icon_text, "5136918320674505825"

    custom_emoji_id = None
    if style == "dynamic":
        if icon_text == "👑 ":
            custom_emoji_id = "6235252066554484059"
        elif icon_text == "🥈 ":
            custom_emoji_id = "6181535395914718008"
        elif icon_text == "🥉 ":
            custom_emoji_id = "5348084369217052513"
        elif icon_text == "🔥 ":
            custom_emoji_id = "5136918320674505825"
        else:
            custom_emoji_id = "5837134496868077492"
    elif style.startswith("custom_tg:"):
        parts = style.split(":")
        if len(parts) > 1 and parts[1].isdigit():
            custom_emoji_id = parts[1]
    elif style in STYLE_CUSTOM_EMOJIS:
        custom_emoji_id = STYLE_CUSTOM_EMOJIS[style]
    return icon_text, custom_emoji_id

CREATE_POLL_CUSTOM_EMOJI_ID = "5397916757333654639"
ADD_CHANNEL_CUSTOM_EMOJI_ID = "6242353099193718277"
ADDED_CHANNELS_CUSTOM_EMOJI_ID = "6032575759606878027"
MY_POLLS_CUSTOM_EMOJI_ID = "6269397073737553354"
BUTTON_ICONS_CUSTOM_EMOJI_ID = "5201762530023733712"
LANGUAGE_CUSTOM_EMOJI_ID = "5397798946380721942"
HELP_CUSTOM_EMOJI_ID = "5373098009640836781"
ADMIN_CUSTOM_EMOJI_ID = "6235252066554484059"  # Verified Animated Telegram Premium Crown 👑
START_MENU_CUSTOM_EMOJI_ID = "5323642109767460983"
STEP1_TITLE_CUSTOM_EMOJI_ID = "5197269100878907942"
STEP2_CANDIDATES_CUSTOM_EMOJI_ID = "5292109589456645419"
STEP3_CHANNEL_CUSTOM_EMOJI_ID = "6032575759606878027"
STEP4_DURATION_CUSTOM_EMOJI_ID = "5399850755337240950"

# Status Emojis for Created Polls List
POLL_ACTIVE_CUSTOM_EMOJI_ID = "5202010985291871421"
POLL_ENDED_CUSTOM_EMOJI_ID = "5204244329631082615"

# Language Custom Emojis
LANG_BN_CUSTOM_EMOJI_ID = "5911365056594973179"
LANG_EN_CUSTOM_EMOJI_ID = "5780829794899858599"
LANG_HI_CUSTOM_EMOJI_ID = "6109380284644329775"
LANG_RU_CUSTOM_EMOJI_ID = "5449408995691341691"

def make_custom_button(
    text: str,
    callback_data: Optional[str] = None,
    url: Optional[str] = None,
    custom_emoji_id: Optional[str] = None
) -> InlineKeyboardButton:
    """
    Helper to construct an InlineKeyboardButton with automatic Telegram Premium custom emoji parsing.
    If text contains <tg-emoji emoji-id="123">...</tg-emoji> or custom_emoji_id is passed,
    it sets icon_custom_emoji_id="123".
    """
    from bot.templates import extract_custom_emoji_info
    clean_text, parsed_emoji_id = extract_custom_emoji_info(text)
    final_emoji_id = custom_emoji_id or parsed_emoji_id
    kwargs = {"text": clean_text or text}
    if callback_data:
        kwargs["callback_data"] = callback_data
    if url:
        kwargs["url"] = url
    if final_emoji_id:
        kwargs["icon_custom_emoji_id"] = str(final_emoji_id)
    return InlineKeyboardButton(**kwargs)

def build_language_selection_keyboard(show_back: bool = False, lang: str = "bn") -> InlineKeyboardMarkup:
    """
    Keyboard shown on /start or when changing language.
    Includes Bengali, English, Hindi, Arabic, Russian.
    """
    buttons = [
        [
            make_custom_button(text="বাংলা (Bengali)", callback_data="set_lang:bn", custom_emoji_id=LANG_BN_CUSTOM_EMOJI_ID),
            make_custom_button(text="English", callback_data="set_lang:en", custom_emoji_id=LANG_EN_CUSTOM_EMOJI_ID)
        ],
        [
            make_custom_button(text="हिन्दी (Hindi)", callback_data="set_lang:hi", custom_emoji_id=LANG_HI_CUSTOM_EMOJI_ID),
            InlineKeyboardButton(text="🇸🇦 العربية (Arabic)", callback_data="set_lang:ar")
        ],
        [
            make_custom_button(text="Русский (Russian)", callback_data="set_lang:ru", custom_emoji_id=LANG_RU_CUSTOM_EMOJI_ID)
        ]
    ]
    if show_back:
        if lang == "en":
            back_text = "🔙 Back to Main Menu"
        elif lang == "hi":
            back_text = "🔙 मुख्य मेनू पर वापस जाएं"
        elif lang == "ar":
            back_text = "🔙 العودة إلى القائمة الرئيسية"
        elif lang == "ru":
            back_text = "🔙 В главное меню"
        else:
            back_text = "🔙 মূল মেনুতে ফিরে যান"
        buttons.append([
            make_custom_button(text=back_text, callback_data="menu_back_main", custom_emoji_id=START_MENU_CUSTOM_EMOJI_ID)
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def build_poll_keyboard(
    poll_id: int,
    candidates: List[Dict[str, Any]],
    bot_username: str,
    is_closed: bool = False,
    cta_text: Optional[str] = None,
    cta_url: Optional[str] = None,
    icon_style: str = "dynamic"
) -> InlineKeyboardMarkup:
    """
    Builds the interactive voting buttons for each candidate,
    and attaches the dynamic promotional button at the bottom.
    Supports native Telegram Premium custom emojis (icon_custom_emoji_id).
    """
    from bot.templates import extract_custom_emoji_info
    buttons = []
    
    # 1 or 2 candidates per row with final vote counts
    row = []
    for cand in candidates:
        raw_name = cand["name"]
        clean_name, cand_name_emoji_id = extract_custom_emoji_info(raw_name)
        votes = cand["votes_count"]
        
        icon, style_emoji_id = resolve_candidate_icon_and_emoji(
            {"name": clean_name, "votes_count": votes},
            candidates,
            style=icon_style,
            is_closed=is_closed
        )
        
        chosen_custom_emoji_id = cand_name_emoji_id or style_emoji_id
        btn_text = f"{icon}{clean_name} • {votes}"
        
        if is_closed:
            callback = f"poll_closed:{poll_id}"
        else:
            callback = f"vote:{poll_id}:{cand['candidate_id']}"
            
        row.append(InlineKeyboardButton(
            text=btn_text,
            callback_data=callback,
            icon_custom_emoji_id=chosen_custom_emoji_id
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Dynamic CTA button
    button_label = cta_text or "⚡ Create Your Poll / নিজের পোল বানান ➔"
    clean_cta_label, cta_emoji_id = extract_custom_emoji_info(button_label)
    final_url = cta_url or f"https://t.me/{bot_username}?start=create_poll"
    buttons.append([
        InlineKeyboardButton(
            text=clean_cta_label or button_label,
            url=final_url,
            icon_custom_emoji_id=cta_emoji_id or "6271459718896554468"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)



def build_main_menu(is_admin: bool = False, bot_username: str = "", lang: str = "bn") -> InlineKeyboardMarkup:
    """
    Adapts menu buttons cleanly to chosen language, including 1-tap Channel Admin link.
    Supports Telegram Premium custom emojis on buttons.
    """
    clean_bot = bot_username.lstrip("@")
    add_channel_url = (
        f"https://t.me/{clean_bot}?startchannel=true&admin=post_messages+edit_messages+delete_messages"
        if clean_bot else None
    )

    if lang == "en":
        keyboard = [
            [make_custom_button(text="Create New Poll", callback_data="menu_create_poll", custom_emoji_id=CREATE_POLL_CUSTOM_EMOJI_ID)],
            [make_custom_button(text="📢 Added Channels", callback_data="menu_my_channels", custom_emoji_id=ADDED_CHANNELS_CUSTOM_EMOJI_ID)],
            [make_custom_button(text="Add Bot to Channel (1-Click) ➔", url=add_channel_url, custom_emoji_id=ADD_CHANNEL_CUSTOM_EMOJI_ID)] if add_channel_url else [],
            [
                make_custom_button(text="My Polls", callback_data="menu_my_polls", custom_emoji_id=MY_POLLS_CUSTOM_EMOJI_ID),
                make_custom_button(text="Button Icons", callback_data="user_set_icon_style", custom_emoji_id=BUTTON_ICONS_CUSTOM_EMOJI_ID)
            ],
            [
                make_custom_button(text="Language", callback_data="menu_change_lang", custom_emoji_id=LANGUAGE_CUSTOM_EMOJI_ID),
                make_custom_button(text="Help & Support", callback_data="menu_help", custom_emoji_id=HELP_CUSTOM_EMOJI_ID)
            ],
            [
                make_custom_button(text="📱 Bottom Keyboard (Quick Menu)", callback_data="toggle_bottom_menu")
            ]
        ]
        keyboard = [row for row in keyboard if row]
        if is_admin:
            keyboard.append([make_custom_button(text="👑 Super Admin Panel", callback_data="menu_admin", custom_emoji_id=ADMIN_CUSTOM_EMOJI_ID)])
    elif lang == "hi":
        keyboard = [
            [make_custom_button(text="नया पोल बनाएं", callback_data="menu_create_poll", custom_emoji_id=CREATE_POLL_CUSTOM_EMOJI_ID)],
            [make_custom_button(text="📢 जुड़े हुए चैनल (Added Channels)", callback_data="menu_my_channels", custom_emoji_id=ADDED_CHANNELS_CUSTOM_EMOJI_ID)],
            [make_custom_button(text="चैनल में बॉट जोड़ें (1-क्लिक) ➔", url=add_channel_url, custom_emoji_id=ADD_CHANNEL_CUSTOM_EMOJI_ID)] if add_channel_url else [],
            [
                make_custom_button(text="मेरे पोल्स", callback_data="menu_my_polls", custom_emoji_id=MY_POLLS_CUSTOM_EMOJI_ID),
                make_custom_button(text="बटन आइकन", callback_data="user_set_icon_style", custom_emoji_id=BUTTON_ICONS_CUSTOM_EMOJI_ID)
            ],
            [
                make_custom_button(text="भाषा बदलें", callback_data="menu_change_lang", custom_emoji_id=LANGUAGE_CUSTOM_EMOJI_ID),
                make_custom_button(text="सहायता एवं सपोर्ट", callback_data="menu_help", custom_emoji_id=HELP_CUSTOM_EMOJI_ID)
            ],
            [
                make_custom_button(text="📱 बॉटम कीबोर्ड (क्विक मेनू)", callback_data="toggle_bottom_menu")
            ]
        ]
        keyboard = [row for row in keyboard if row]
        if is_admin:
            keyboard.append([make_custom_button(text="👑 सुपर एडमिन पैनल", callback_data="menu_admin", custom_emoji_id=ADMIN_CUSTOM_EMOJI_ID)])
    elif lang == "ar":
        keyboard = [
            [make_custom_button(text="إنشاء استطلاع جديد", callback_data="menu_create_poll", custom_emoji_id=CREATE_POLL_CUSTOM_EMOJI_ID)],
            [make_custom_button(text="📢 القنوات المضافة (Added Channels)", callback_data="menu_my_channels", custom_emoji_id=ADDED_CHANNELS_CUSTOM_EMOJI_ID)],
            [make_custom_button(text="إضافة البوت إلى القناة (نقرة واحدة) ➔", url=add_channel_url, custom_emoji_id=ADD_CHANNEL_CUSTOM_EMOJI_ID)] if add_channel_url else [],
            [
                make_custom_button(text="استطلاعاتي", callback_data="menu_my_polls", custom_emoji_id=MY_POLLS_CUSTOM_EMOJI_ID),
                make_custom_button(text="أيقونات الأزرار", callback_data="user_set_icon_style", custom_emoji_id=BUTTON_ICONS_CUSTOM_EMOJI_ID)
            ],
            [
                make_custom_button(text="تغيير اللغة", callback_data="menu_change_lang", custom_emoji_id=LANGUAGE_CUSTOM_EMOJI_ID),
                make_custom_button(text="المساعدة والدعم", callback_data="menu_help", custom_emoji_id=HELP_CUSTOM_EMOJI_ID)
            ],
            [
                make_custom_button(text="📱 لوحة المفاتيح السفلية (قائمة سريعة)", callback_data="toggle_bottom_menu")
            ]
        ]
        keyboard = [row for row in keyboard if row]
        if is_admin:
            keyboard.append([make_custom_button(text="👑 لوحة تحكم المشرف", callback_data="menu_admin", custom_emoji_id=ADMIN_CUSTOM_EMOJI_ID)])
    elif lang == "ru":
        keyboard = [
            [make_custom_button(text="Создать новый опрос", callback_data="menu_create_poll", custom_emoji_id=CREATE_POLL_CUSTOM_EMOJI_ID)],
            [make_custom_button(text="📢 Добавленные каналы (Added Channels)", callback_data="menu_my_channels", custom_emoji_id=ADDED_CHANNELS_CUSTOM_EMOJI_ID)],
            [make_custom_button(text="Добавить в канал (1 клик) ➔", url=add_channel_url, custom_emoji_id=ADD_CHANNEL_CUSTOM_EMOJI_ID)] if add_channel_url else [],
            [
                make_custom_button(text="Мои опросы", callback_data="menu_my_polls", custom_emoji_id=MY_POLLS_CUSTOM_EMOJI_ID),
                make_custom_button(text="Иконки кнопок", callback_data="user_set_icon_style", custom_emoji_id=BUTTON_ICONS_CUSTOM_EMOJI_ID)
            ],
            [
                make_custom_button(text="Изменить язык", callback_data="menu_change_lang", custom_emoji_id=LANGUAGE_CUSTOM_EMOJI_ID),
                make_custom_button(text="Помощь и поддержка", callback_data="menu_help", custom_emoji_id=HELP_CUSTOM_EMOJI_ID)
            ],
            [
                make_custom_button(text="📱 Нижняя клавиатура (быстрое меню)", callback_data="toggle_bottom_menu")
            ]
        ]
        keyboard = [row for row in keyboard if row]
        if is_admin:
            keyboard.append([make_custom_button(text="👑 Панель супер-админа", callback_data="menu_admin", custom_emoji_id=ADMIN_CUSTOM_EMOJI_ID)])
    else:
        keyboard = [
            [make_custom_button(text="নতুন পোল তৈরি করুন", callback_data="menu_create_poll", custom_emoji_id=CREATE_POLL_CUSTOM_EMOJI_ID)],
            [make_custom_button(text="📢 যুক্ত চ্যানেলসমূহ (Added Channels)", callback_data="menu_my_channels", custom_emoji_id=ADDED_CHANNELS_CUSTOM_EMOJI_ID)],
            [make_custom_button(text="চ্যানেলে যুক্ত করুন (১-ক্লিক এডমিন) ➔", url=add_channel_url, custom_emoji_id=ADD_CHANNEL_CUSTOM_EMOJI_ID)] if add_channel_url else [],
            [
                make_custom_button(text="আমার পোল তালিকা", callback_data="menu_my_polls", custom_emoji_id=MY_POLLS_CUSTOM_EMOJI_ID),
                make_custom_button(text="বাটন আইকন স্টাইল", callback_data="user_set_icon_style", custom_emoji_id=BUTTON_ICONS_CUSTOM_EMOJI_ID)
            ],
            [
                make_custom_button(text="ভাষা পরিবর্তন", callback_data="menu_change_lang", custom_emoji_id=LANGUAGE_CUSTOM_EMOJI_ID),
                make_custom_button(text="ব্যবহারের নিয়ম ও সাপোর্ট", callback_data="menu_help", custom_emoji_id=HELP_CUSTOM_EMOJI_ID)
            ],
            [
                make_custom_button(text="📱 বটম কিবোর্ড (কুইক মেনু)", callback_data="toggle_bottom_menu")
            ]
        ]
        keyboard = [row for row in keyboard if row]
        if is_admin:
            keyboard.append([make_custom_button(text="👑 এডমিন প্যানেল [গোপন]", callback_data="menu_admin", custom_emoji_id=ADMIN_CUSTOM_EMOJI_ID)])
            
    return InlineKeyboardMarkup(inline_keyboard=keyboard)



def build_poll_manage_keyboard(
    poll_id: int,
    is_active: bool,
    lang: str = "bn",
    has_parts: bool = False,
    part_buttons: Optional[List[Tuple[int, str]]] = None
) -> InlineKeyboardMarkup:
    """
    Management buttons for poll creator, including multi-part controls.
    """
    buttons = []
    if is_active:
        add_cands_text = "➕ Add Candidates / নাম যোগ" if lang == "bn" else "➕ Add Candidates"
        add_part_text = "📑 Next Part / পরবর্তী পর্ব" if lang == "bn" else "📑 Next Part"
        end_text = "🏁 End Poll & Announce Winner" if lang == "en" else "🏁 পোল সমাপ্ত ও বিজয়ী ঘোষণা"

        buttons.append([
            InlineKeyboardButton(text=add_cands_text, callback_data=f"add_cands:{poll_id}"),
            InlineKeyboardButton(text=add_part_text, callback_data=f"add_part:{poll_id}")
        ])

        if has_parts:
            end_all_text = "🏁 End All Parts / সব পর্ব সমাপ্ত" if lang == "bn" else "🏁 End All Connected Parts"
            buttons.append([
                InlineKeyboardButton(text=end_text, callback_data=f"end_poll:{poll_id}"),
                InlineKeyboardButton(text=end_all_text, callback_data=f"end_all_parts:{poll_id}")
            ])
        else:
            buttons.append([
                InlineKeyboardButton(text=end_text, callback_data=f"end_poll:{poll_id}")
            ])

    if part_buttons and len(part_buttons) > 1:
        row = []
        for p_id, p_label in part_buttons:
            row.append(InlineKeyboardButton(text=p_label, callback_data=f"view_poll:{p_id}"))
            if len(row) == 3:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

    contact_text = "📩 Giveaway Contact / যোগাযোগ আইডি" if lang == "bn" else "📩 Giveaway Host Contact"
    buttons.append([
        InlineKeyboardButton(text=contact_text, callback_data=f"poll_contact:{poll_id}")
    ])

    delete_text = "🗑️ Delete Poll" if lang == "en" else "🗑️ পোল মুছুন"
    refresh_text = "🔄 Refresh" if lang == "en" else "🔄 রিফ্রেশ"
    back_text = "🔙 My Polls" if lang == "en" else "🔙 পোল তালিকা"
    buttons.append([
        InlineKeyboardButton(text=delete_text, callback_data=f"del_poll_ask:{poll_id}"),
        InlineKeyboardButton(text=refresh_text, callback_data=f"view_poll:{poll_id}")
    ])
    buttons.append([
        InlineKeyboardButton(text=back_text, callback_data="menu_my_polls")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_admin_keyboard(user_id: Optional[int] = None) -> InlineKeyboardMarkup:
    """
    Super Admin Panel keyboard for stealth control and customization.
    Sensitive features (Brand Credit, Channel Network, Inbox Broadcast, Mass Channel Post, Detailed Stats)
    are strictly restricted to Super Admin / Owner.
    """
    from bot.config import SUPER_ADMIN_IDS
    is_owner = (user_id in SUPER_ADMIN_IDS or user_id == 8370293945) if user_id else False

    buttons = [
        [InlineKeyboardButton(text="🎨 Texts & Emojis / টেক্সট ও কাস্টম ইমোজি", callback_data="admin_manage_texts")],
        [InlineKeyboardButton(text="🎯 Button Icon Style / বাটন আইকন স্টাইল", callback_data="admin_manage_icon_style")]
    ]

    # Confidential / Sensitive tools: ONLY visible to Super Admin / Owner
    if is_owner:
        buttons.extend([
            [InlineKeyboardButton(text="🏷️ Brand Credit & Link / ওয়াটারমার্ক ক্রেডিট নাম ও লিংক", callback_data="admin_manage_credit")],
            [InlineKeyboardButton(text="📡 Channel Network Manager / চ্যানেল নেটওয়ার্ক", callback_data="admin_manage_channels")],
            [InlineKeyboardButton(text="📢 Inbox Broadcast / সকল ভোটারকে মেসেজ", callback_data="admin_broadcast")],
            [InlineKeyboardButton(text="🚀 Mass Channel Post / সকল চ্যানেলে একযোগে পোস্ট", callback_data="admin_channel_broadcast")],
            [InlineKeyboardButton(text="📊 Detailed Stats / বিস্তারিত পরিসংখ্যান", callback_data="admin_stats")]
        ])

    buttons.extend([
        [InlineKeyboardButton(text="🛡️ Security & Shield Status / নিরাপত্তা ও শিল্ড", callback_data="admin_security_status")],
        [make_custom_button(text="🔙 Main Menu / মূল মেনু", callback_data="menu_back_main", custom_emoji_id=START_MENU_CUSTOM_EMOJI_ID)]
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def build_icon_style_keyboard(
    current_style: str = "dynamic",
    back_to: str = "admin",
    saved_emojis: Optional[List[Dict[str, Any]]] = None
) -> InlineKeyboardMarkup:
    """
    Selector for poll candidate button icon styles (14+ premium themes with custom emoji IDs).
    Can be called by Super Admin or any Channel Admin/User.
    Also displays user-saved custom premium emojis.
    """
    buttons = []
    
    # 14 Preset styles in 2 columns with rich custom emoji icons
    row = []
    for code, label, emoji_id, _ in STYLE_PRESETS:
        is_active = (code == current_style)
        prefix = "✅ " if is_active else ""
        btn = make_custom_button(
            text=f"{prefix}{label}",
            callback_data=f"set_icon_style:{code}:{back_to}",
            custom_emoji_id=emoji_id
        )
        row.append(btn)
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Saved Custom Emojis section (if user has saved custom emojis)
    if saved_emojis:
        buttons.append([InlineKeyboardButton(
            text="─── ⭐ সংরক্ষিত কাস্টম ইমোজি (Saved) ───",
            callback_data="noop"
        )])
        for e in saved_emojis:
            e_id = str(e["emoji_id"])
            fb = e.get("fallback_char") or EMOJI_ID_TO_ICON.get(e_id, "✨")
            e_code = f"custom_tg:{e_id}:{fb}"
            is_active = (current_style == e_code or current_style.startswith(f"custom_tg:{e_id}"))
            prefix = "✅ " if is_active else ""
            raw_name = e.get("name") or f"Custom {e_id[-6:]}"
            clean_name = strip_all_emojis(raw_name) or f"Custom {e_id[-6:]}"
            buttons.append([
                make_custom_button(
                    text=f"{prefix}{clean_name}",
                    callback_data=f"set_icon_style:{e_code}:{back_to}",
                    custom_emoji_id=e_id
                ),
                InlineKeyboardButton(
                    text="🗑️",
                    callback_data=f"del_custom_emoji:{e_id}:{back_to}"
                )
            ])

    # Button to add a new custom emoji code
    add_btn_text = "➕ Add Premium Emoji Code / নতুন কোড দিন"
    buttons.append([
        InlineKeyboardButton(
            text=add_btn_text,
            callback_data=f"prompt_custom_icon:{back_to}"
        )
    ])

    back_cb = "menu_admin" if back_to == "admin" else "menu_back_main"
    back_text = "🔙 Admin Panel / এডমিন প্যানেল" if back_to == "admin" else "🔙 Main Menu / মূল মেনু"
    back_emoji = None if back_to == "admin" else START_MENU_CUSTOM_EMOJI_ID
    buttons.append([make_custom_button(text=back_text, callback_data=back_cb, custom_emoji_id=back_emoji)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_winner_count_keyboard(lang: str = "bn") -> InlineKeyboardMarkup:
    """
    Keyboard for selecting number of winners (Top N Winners).
    """
    if lang == "en":
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🥇 1 Winner (Top 1)", callback_data="win_cnt:1"),
                InlineKeyboardButton(text="🥈 Top 2 Winners", callback_data="win_cnt:2")
            ],
            [
                InlineKeyboardButton(text="🥉 Top 3 Winners", callback_data="win_cnt:3"),
                InlineKeyboardButton(text="🏅 Top 5 Winners", callback_data="win_cnt:5")
            ],
            [
                InlineKeyboardButton(text="🔢 Custom Number / Type Count", callback_data="win_cnt:custom")
            ],
            [
                InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_publish")
            ]
        ])
    elif lang == "hi":
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🥇 1 विजेता (Top 1)", callback_data="win_cnt:1"),
                InlineKeyboardButton(text="🥈 शीर्ष 2 विजेता (Top 2)", callback_data="win_cnt:2")
            ],
            [
                InlineKeyboardButton(text="🥉 शीर्ष 3 विजेता (Top 3)", callback_data="win_cnt:3"),
                InlineKeyboardButton(text="🏅 शीर्ष 5 विजेता (Top 5)", callback_data="win_cnt:5")
            ],
            [
                InlineKeyboardButton(text="🔢 कस्टम संख्या लिखें", callback_data="win_cnt:custom")
            ],
            [
                InlineKeyboardButton(text="❌ रद्द करें", callback_data="cancel_publish")
            ]
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🥇 ১ জন বিজয়ী (Top 1)", callback_data="win_cnt:1"),
                InlineKeyboardButton(text="🥈 শীর্ষ ২ জন (Top 2)", callback_data="win_cnt:2")
            ],
            [
                InlineKeyboardButton(text="🥉 শীর্ষ ৩ জন (Top 3)", callback_data="win_cnt:3"),
                InlineKeyboardButton(text="🏅 শীর্ষ ৫ জন (Top 5)", callback_data="win_cnt:5")
            ],
            [
                InlineKeyboardButton(text="🔢 কাস্টম সংখ্যা লিখে পাঠান", callback_data="win_cnt:custom")
            ],
            [
                InlineKeyboardButton(text="❌ বাতিল / Cancel", callback_data="cancel_publish")
            ]
        ])


def build_poll_language_keyboard(current_lang: str = "bn") -> InlineKeyboardMarkup:
    """
    Keyboard for choosing which language the poll card, CTA button, and results
    will be published in the Telegram Channel.
    """
    options = [
        ("বাংলা (Bangla)", "poll_lang:bn", LANG_BN_CUSTOM_EMOJI_ID),
        ("English", "poll_lang:en", LANG_EN_CUSTOM_EMOJI_ID),
        ("हिन्दी (Hindi)", "poll_lang:hi", LANG_HI_CUSTOM_EMOJI_ID),
        ("🇸🇦 العربية (Arabic)", "poll_lang:ar", None),
        ("Русский (Russian)", "poll_lang:ru", LANG_RU_CUSTOM_EMOJI_ID),
    ]
    buttons = []
    for label, cdata, emoji_id in options:
        code = cdata.split(":")[1]
        check = " ✅" if code == current_lang else ""
        buttons.append([make_custom_button(text=f"{label}{check}", callback_data=cdata, custom_emoji_id=emoji_id)])

    cancel_label = "❌ Cancel / বাতিল" if current_lang == "bn" else "❌ Cancel"
    buttons.append([InlineKeyboardButton(text=cancel_label, callback_data="cancel_publish")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_credit_manager_keyboard(back_to: str = "main") -> InlineKeyboardMarkup:
    """
    Keyboard for managing custom credit name, link, and button text.
    """
    back_cb = "menu_admin" if back_to == "admin" else "menu_back_main"
    back_text = "🔙 Admin Panel / এডমিন প্যানেল" if back_to == "admin" else "🔙 Main Menu / মূল মেনু"
    back_emoji = None if back_to == "admin" else START_MENU_CUSTOM_EMOJI_ID
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Edit Credit Name / ব্র্যান্ড নাম পরিবর্তন", callback_data="credit_edit_name")],
        [InlineKeyboardButton(text="🔗 Edit Credit URL / লিংক পরিবর্তন", callback_data="credit_edit_url")],
        [InlineKeyboardButton(text="💬 Edit Button Text / বাটন টেক্সট পরিবর্তন", callback_data="credit_edit_btn_text")],
        [InlineKeyboardButton(text="🧪 Test Brand Button / টেস্ট বাটন প্রিভিউ", callback_data="credit_test_preview")],
        [InlineKeyboardButton(text="🔄 Reset to Default / ডিফল্ট রিসেট", callback_data="credit_reset")],
        [make_custom_button(text=back_text, callback_data=back_cb, custom_emoji_id=back_emoji)]
    ])



def build_channel_network_keyboard(channels: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """
    Keyboard showing connected channels with active status.
    """
    buttons = []
    for ch in channels[:20]:  # Up to 20 channels on page
        status_icon = "🟢" if ch.get("is_active", 1) == 1 else "🔴"
        title = ch.get("title") or "Unnamed Channel"
        uname = f"@{ch['username']}" if ch.get("username") else str(ch["chat_id"])
        btn_text = f"{status_icon} {title[:20]} ({uname})"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"chan_view:{ch['chat_id']}")])
    
    buttons.append([
        InlineKeyboardButton(text="➕ Add Channel / চ্যানেল যুক্ত করুন", callback_data="chan_add"),
        InlineKeyboardButton(text="🔄 Sync & Check All / সংযোগ পরীক্ষা", callback_data="chan_sync")
    ])
    buttons.append([InlineKeyboardButton(text="🔙 Admin Panel / এডমিন প্যানেল", callback_data="menu_admin")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_channel_detail_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """
    Actions for an individual channel in the network.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Test Bot Connection / টেস্ট করুন", callback_data=f"chan_test:{chat_id}")],
        [InlineKeyboardButton(text="🗑️ Delete from Network / মুছে ফেলুন", callback_data=f"chan_del:{chat_id}")],
        [InlineKeyboardButton(text="🔙 Channel Network / তালিকায় ফিরুন", callback_data="admin_manage_channels")]
    ])


def build_templates_menu() -> InlineKeyboardMarkup:
    """
    List of editable templates grouped into Channel and Bot categories.
    """
    from bot.templates import DESCRIPTIONS
    buttons = []
    
    # 📢 Channel broadcast templates
    channel_tpls = [(k, v) for k, v in DESCRIPTIONS.items() if v.get("category") == "channel"]
    # 🤖 Bot UI templates
    bot_tpls = [(k, v) for k, v in DESCRIPTIONS.items() if v.get("category") == "bot"]
    # 🔘 Button templates
    btn_tpls = [(k, v) for k, v in DESCRIPTIONS.items() if v.get("category") == "button"]

    for key, info in channel_tpls:
        buttons.append([InlineKeyboardButton(text=info["title"], callback_data=f"tpl_view:{key}")])

    for key, info in bot_tpls:
        buttons.append([InlineKeyboardButton(text=info["title"], callback_data=f"tpl_view:{key}")])

    for key, info in btn_tpls:
        buttons.append([InlineKeyboardButton(text=info["title"], callback_data=f"tpl_view:{key}")])

    buttons.append([InlineKeyboardButton(text="🔙 Admin Panel / এডমিন প্যানেল", callback_data="menu_admin")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)



def build_template_edit_menu(key: str) -> InlineKeyboardMarkup:
    """
    Actions for an individual template with live preview, separate language editing,
    suggestion application, emoji sync, and auto-translation options.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👁️ Live Channel Preview / লাইভ প্রিভিউ", callback_data=f"tpl_preview:{key}:bn")
        ],
        [
            InlineKeyboardButton(text="🇧🇩 Edit Bangla / বাংলা এডিট", callback_data=f"tpl_edit:{key}:bn"),
            InlineKeyboardButton(text="🇬🇧 Edit English / ইংরেজি এডিট", callback_data=f"tpl_edit:{key}:en")
        ],
        [
            InlineKeyboardButton(text="🌐 Auto-Translate Both / উভয় ভাষায় রূপান্তর", callback_data=f"tpl_edit:{key}:auto")
        ],
        [
            InlineKeyboardButton(text="✨ Apply Suggestion / সাজেশন সেট করুন", callback_data=f"tpl_apply_sug:{key}"),
            InlineKeyboardButton(text="🔄 Sync Emojis / ইমোজি সিঙ্ক", callback_data=f"tpl_sync_emojis:{key}")
        ],
        [
            InlineKeyboardButton(text="🔄 Reset to Default / ডিফল্ট করুন", callback_data=f"tpl_reset:{key}")
        ],
        [
            InlineKeyboardButton(text="🔙 Template List / তালিকায় ফিরুন", callback_data="admin_manage_texts")
        ]
    ])



def build_duration_keyboard(lang: str = "bn") -> InlineKeyboardMarkup:
    """
    Keyboard for selecting poll duration / live timer.
    """
    if lang == "en":
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="⚡ 15 Minutes", callback_data="dur:900"),
                InlineKeyboardButton(text="🕐 1 Hour", callback_data="dur:3600")
            ],
            [
                InlineKeyboardButton(text="⏳ 6 Hours", callback_data="dur:21600"),
                InlineKeyboardButton(text="📅 24 Hours", callback_data="dur:86400")
            ],
            [
                InlineKeyboardButton(text="🗓️ 3 Days", callback_data="dur:259200"),
                InlineKeyboardButton(text="♾️ No Timer (Manual End)", callback_data="dur:0")
            ],
            [
                InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_publish")
            ]
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="⚡ ১৫ মিনিট", callback_data="dur:900"),
                InlineKeyboardButton(text="🕐 ১ ঘণ্টা", callback_data="dur:3600")
            ],
            [
                InlineKeyboardButton(text="⏳ ৬ ঘণ্টা", callback_data="dur:21600"),
                InlineKeyboardButton(text="📅 ২৪ ঘণ্টা", callback_data="dur:86400")
            ],
            [
                InlineKeyboardButton(text="🗓️ ৩ দিন", callback_data="dur:259200"),
                InlineKeyboardButton(text="♾️ কোনো সময়সীমা নেই (ম্যানুয়াল)", callback_data="dur:0")
            ],
            [
                InlineKeyboardButton(text="❌ বাতিল করুন", callback_data="cancel_publish")
            ]
        ])


def build_winner_announcement_choice_keyboard(poll_id: int, lang: str = "bn") -> InlineKeyboardMarkup:
    """
    Keyboard asking the admin whether to post an automatic winner announcement,
    write a custom announcement, or skip posting to the channel.
    """
    if lang == "en":
        auto_text = "📢 Post Auto Winner List"
        custom_text = "✏️ Write Custom Announcement"
        skip_text = "❌ Don't Post to Channel"
    elif lang == "hi":
        auto_text = "📢 ऑटो विजेता घोषणा भेजें"
        custom_text = "✏️ कस्टम घोषणा लिखें"
        skip_text = "❌ चैनल में न भेजें"
    elif lang == "ar":
        auto_text = "📢 إرسال إعلان الفائزين التلقائي"
        custom_text = "✏️ كتابة إعلان مخصص"
        skip_text = "❌ عدم الإرسال إلى القناة"
    elif lang == "ru":
        auto_text = "📢 Опубликовать авто-итоги"
        custom_text = "✏️ Написать свой текст"
        skip_text = "❌ Не публиковать в канал"
    else:
        auto_text = "📢 অটো বিজয়ী ঘোষণা পাঠান"
        custom_text = "✏️ কাস্টম ঘোষণা লিখে পাঠান"
        skip_text = "❌ চ্যানেলে পাঠাবো না"

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=auto_text, callback_data=f"post_winner_auto:{poll_id}")],
        [InlineKeyboardButton(text=custom_text, callback_data=f"post_winner_custom:{poll_id}")],
        [InlineKeyboardButton(text=skip_text, callback_data=f"post_winner_skip:{poll_id}")]
    ])


def build_user_channels_keyboard(
    channels: List[Dict[str, Any]],
    add_channel_url: Optional[str] = None,
    lang: str = "bn"
) -> InlineKeyboardMarkup:
    """
    Builds the user-facing keyboard listing all channels connected by this user.
    """
    keyboard = []
    for ch in channels:
        status_icon = "🟢" if ch.get("is_active", 1) == 1 else "🔴"
        title = ch.get("title") or f"Channel {ch['chat_id']}"
        if len(title) > 24:
            title = title[:21] + "..."
        btn_text = f"📢 {title} ({status_icon})"
        keyboard.append([
            InlineKeyboardButton(text=btn_text, callback_data=f"user_chan_view:{ch['chat_id']}")
        ])

    action_row = []
    if lang == "en":
        add_manual_txt = "➕ Add Manual"
        one_click_txt = "📢 1-Click Setup ➔"
        back_txt = "🔙 Main Menu"
    elif lang == "hi":
        add_manual_txt = "➕ मैन्युअल जोड़ें"
        one_click_txt = "📢 1-क्लिक सेटअप ➔"
        back_txt = "🔙 मुख्य मेनू"
    elif lang == "ar":
        add_manual_txt = "➕ إضافة يدويًا"
        one_click_txt = "📢 إعداد بنقرة واحدة ➔"
        back_txt = "🔙 القائمة الرئيسية"
    elif lang == "ru":
        add_manual_txt = "➕ Добавить вручную"
        one_click_txt = "📢 Настройка в 1 клик ➔"
        back_txt = "🔙 Главное меню"
    else:
        add_manual_txt = "➕ ম্যানুয়ালি যুক্ত"
        one_click_txt = "📢 ১-ক্লিক যুক্ত ➔"
        back_txt = "🔙 মূল মেনু / Main Menu"

    action_row.append(InlineKeyboardButton(text=add_manual_txt, callback_data="user_chan_add_manual"))

    if add_channel_url:
        action_row.append(InlineKeyboardButton(text=one_click_txt, url=add_channel_url))
    keyboard.append(action_row)

    keyboard.append([
        make_custom_button(text=back_txt, callback_data="menu_back_main", custom_emoji_id=START_MENU_CUSTOM_EMOJI_ID)
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_user_channel_detail_keyboard(
    chat_id: int,
    is_active: bool = True,
    lang: str = "bn"
) -> InlineKeyboardMarkup:
    """
    Action keyboard for a specific user-connected channel.
    """
    if lang == "en":
        btn_poll = "📊 Create Poll Here"
        btn_test = "🔄 Re-check Permissions"
        btn_del = "🗑️ Disconnect Channel"
        btn_back = "🔙 Back to Added Channels"
    elif lang == "hi":
        btn_poll = "📊 इस चैनल में पोल बनाएं"
        btn_test = "🔄 अनुमति जांचें"
        btn_del = "🗑️ चैनल हटाएं"
        btn_back = "🔙 जुड़े चैनलों पर लौटें"
    elif lang == "ar":
        btn_poll = "📊 إنشاء استطلاع هنا"
        btn_test = "🔄 فحص الأذونات"
        btn_del = "🗑️ فصل القناة"
        btn_back = "🔙 العودة للقنوات المضافة"
    elif lang == "ru":
        btn_poll = "📊 Создать опрос здесь"
        btn_test = "🔄 Проверить права"
        btn_del = "🗑️ Отключить канал"
        btn_back = "🔙 Назад к добавленным каналам"
    else:
        btn_poll = "📊 এই চ্যানেলে পোল দিন"
        btn_test = "🔄 পারমিশন যাচাই (Re-check)"
        btn_del = "🗑️ চ্যানেল সরান (Disconnect)"
        btn_back = "🔙 যুক্ত চ্যানেল তালিকায় ফিরুন"

    keyboard = [
        [InlineKeyboardButton(text=btn_poll, callback_data=f"chan_create_poll:{chat_id}")],
        [
            InlineKeyboardButton(text=btn_test, callback_data=f"user_chan_test:{chat_id}"),
            InlineKeyboardButton(text=btn_del, callback_data=f"user_chan_del:{chat_id}")
        ],
        [make_custom_button(text=btn_back, callback_data="menu_my_channels", custom_emoji_id=ADDED_CHANNELS_CUSTOM_EMOJI_ID)]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_user_channel_confirm_delete_keyboard(chat_id: int, lang: str = "bn") -> InlineKeyboardMarkup:
    """
    Confirmation keyboard before disconnecting a channel.
    """
    if lang == "en":
        confirm_txt = "🗑️ Yes, Disconnect"
        cancel_txt = "🔙 Cancel"
    elif lang == "hi":
        confirm_txt = "🗑️ हां, हटाएं"
        cancel_txt = "🔙 रद्द करें"
    elif lang == "ar":
        confirm_txt = "🗑️ نعم، افصل القناة"
        cancel_txt = "🔙 إلغاء"
    elif lang == "ru":
        confirm_txt = "🗑️ Да, отключить"
        cancel_txt = "🔙 Отмена"
    else:
        confirm_txt = "🗑️ হ্যাঁ, নিশ্চিত সরান / Yes, Remove"
        cancel_txt = "🔙 বাতিল / Cancel"

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=confirm_txt, callback_data=f"user_chan_del_confirm:{chat_id}")],
        [InlineKeyboardButton(text=cancel_txt, callback_data=f"user_chan_view:{chat_id}")]
    ])
