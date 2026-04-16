from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        ["🛍 Shop", "🤝 Affiliate"],
        ["👤 Account", "📦 Orders"],
        ["💬 Support", "🌍 Language"],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def language_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("English", callback_data="lang:en"),
            InlineKeyboardButton("العربية", callback_data="lang:ar"),
        ],
        [
            InlineKeyboardButton("Français", callback_data="lang:fr"),
            InlineKeyboardButton("Español", callback_data="lang:es"),
        ],
        [
            InlineKeyboardButton("Deutsch", callback_data="lang:de"),
            InlineKeyboardButton("Português", callback_data="lang:pt"),
        ],
        [
            InlineKeyboardButton("中文", callback_data="lang:zh"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def role_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("Customer", callback_data="role:customer")],
        [InlineKeyboardButton("Affiliate", callback_data="role:affiliate")],
        [InlineKeyboardButton("Supplier", callback_data="role:supplier")],
        [InlineKeyboardButton("Partner", callback_data="role:partner")],
        [InlineKeyboardButton("Contributor", callback_data="role:contributor")],
        [InlineKeyboardButton("Advertiser", callback_data="role:advertiser")],
    ]
    return InlineKeyboardMarkup(keyboard)