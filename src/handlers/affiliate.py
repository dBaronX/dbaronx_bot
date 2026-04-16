from telegram import Update
from telegram.ext import ContextTypes

from src.services.user_service import UserService


user_service = UserService()


async def affiliate_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user:
        return

    telegram_id = str(update.effective_user.id)

    try:
        dashboard = await user_service.get_dashboard(telegram_id)
        affiliate = dashboard.get("affiliate", {})
        text = (
            "Affiliate Dashboard\n\n"
            f"Status: {affiliate.get('status', 'not_registered')}\n"
            f"Referral Code: {affiliate.get('referral_code', '-')}\n"
            f"Clicks: {affiliate.get('clicks', 0)}\n"
            f"Conversions: {affiliate.get('conversions', 0)}\n"
            f"Earnings: {affiliate.get('earnings', '0.00')}\n"
        )
    except Exception:
        text = (
            "Affiliate Dashboard\n\n"
            "Affiliate data is temporarily unavailable from the API."
        )

    if update.message:
        await update.message.reply_text(text)