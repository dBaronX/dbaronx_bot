from telegram import Update
from telegram.ext import ContextTypes

from src.services.user_service import UserService


user_service = UserService()


async def account_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return

    telegram_id = str(update.effective_user.id)

    try:
        dashboard = await user_service.get_dashboard(telegram_id)
        profile = dashboard.get("profile", {})
        text = (
            "Account\n\n"
            f"Name: {profile.get('name', '-')}\n"
            f"Language: {profile.get('language', '-')}\n"
            f"Country: {profile.get('country', '-')}\n"
            f"Role: {profile.get('role', '-')}\n"
        )
    except Exception:
        text = "Account data is temporarily unavailable from the API."

    await update.message.reply_text(text)