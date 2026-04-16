from telegram import Update
from telegram.ext import ContextTypes

from src.core.keyboards import language_keyboard, main_menu_keyboard
from src.services.auth_service import AuthService


auth_service = AuthService()


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return

    user = update.effective_user

    await auth_service.link_telegram_user(
        {
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "language_code": user.language_code,
        }
    )

    welcome = (
        f"Welcome to dBaronX, {user.first_name}.\n\n"
        "Your Telegram account is now connected.\n"
        "Next: choose your language."
    )

    await update.message.reply_text(welcome, reply_markup=language_keyboard())
    await update.message.reply_text(
        "Main menu activated.",
        reply_markup=main_menu_keyboard(),
    )