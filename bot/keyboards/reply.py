from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from bot.keyboards.inline import (
    START_MENU_CUSTOM_EMOJI_ID,
    CREATE_POLL_CUSTOM_EMOJI_ID,
    MY_POLLS_CUSTOM_EMOJI_ID,
    ADD_CHANNEL_CUSTOM_EMOJI_ID,
    BUTTON_ICONS_CUSTOM_EMOJI_ID,
    LANGUAGE_CUSTOM_EMOJI_ID,
    HELP_CUSTOM_EMOJI_ID
)

def build_persistent_menu(lang: str = "bn", is_admin: bool = False) -> ReplyKeyboardMarkup:
    """
    Creates an always-visible, persistent Telegram reply keyboard pinned at the bottom of the chat.
    Users will never need to search for or type /start again.
    Uses matching Telegram Premium custom emoji IDs on both reply & inline buttons.
    """
    if lang == "en":
        btn_start = "Start / Main Menu"
        btn_create = "Create New Poll"
        btn_polls = "My Polls"
        btn_channel = "Add Bot to Channel"
        btn_brand = "🏷️ Brand & Link"
        btn_icons = "Button Icons"
        btn_lang = "Language"
        btn_help = "Help & Support"
    elif lang == "hi":
        btn_start = "Start / मुख्य मेनू"
        btn_create = "नया पोल बनाएं"
        btn_polls = "मेरे पोल्स"
        btn_channel = "चैनल में बॉट जोड़ें"
        btn_brand = "🏷️ ब्रांड और लिंक"
        btn_icons = "बटन आइकन"
        btn_lang = "भाषा"
        btn_help = "सहायता एवं सपोर्ट"
    elif lang == "ar":
        btn_start = "Start / القائمة الرئيسية"
        btn_create = "إنشاء استطلاع جديد"
        btn_polls = "استطلاعاتي"
        btn_channel = "إضافة البوت للقناة"
        btn_brand = "🏷️ العلامة والرابط"
        btn_icons = "نمط الأيقونات"
        btn_lang = "اللغة"
        btn_help = "المساعدة والدعم"
    elif lang == "ru":
        btn_start = "Start / Главное меню"
        btn_create = "Создать новый опрос"
        btn_polls = "Мои опросы"
        btn_channel = "Добавить в канал"
        btn_brand = "🏷️ Бренд и ссылка"
        btn_icons = "Иконки кнопок"
        btn_lang = "Язык"
        btn_help = "Помощь и поддержка"
    else:
        btn_start = "Start / মূল মেনু"
        btn_create = "নতুন পোল তৈরি করুন"
        btn_polls = "আমার পোল তালিকা"
        btn_channel = "চ্যানেলে যুক্ত করুন (১-ক্লিক)"
        btn_brand = "🏷️ ব্র্যান্ড ও লিংক"
        btn_icons = "বাটন আইকন স্টাইল"
        btn_lang = "ভাষা পরিবর্তন"
        btn_help = "ব্যবহারের নিয়ম ও সাপোর্ট"

    keyboard = [
        [KeyboardButton(text=btn_start, icon_custom_emoji_id=START_MENU_CUSTOM_EMOJI_ID)],
        [
            KeyboardButton(text=btn_create, icon_custom_emoji_id=CREATE_POLL_CUSTOM_EMOJI_ID),
            KeyboardButton(text=btn_polls, icon_custom_emoji_id=MY_POLLS_CUSTOM_EMOJI_ID)
        ],
        [
            KeyboardButton(text=btn_channel, icon_custom_emoji_id=ADD_CHANNEL_CUSTOM_EMOJI_ID),
            KeyboardButton(text=btn_icons, icon_custom_emoji_id=BUTTON_ICONS_CUSTOM_EMOJI_ID)
        ],
        [
            KeyboardButton(text=btn_lang, icon_custom_emoji_id=LANGUAGE_CUSTOM_EMOJI_ID),
            KeyboardButton(text=btn_help, icon_custom_emoji_id=HELP_CUSTOM_EMOJI_ID)
        ]
    ]

    if is_admin:
        admin_text = "👑 Admin Panel" if lang == "en" else "👑 এডমিন প্যানেল"
        keyboard.append([KeyboardButton(text=admin_text)])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        is_persistent=True
    )
