from telegram import Update
from telegram.ext import ContextTypes


async def support_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(
            "Support is active.\n"
            "Next step: connect AI/helpdesk escalation through NestJS."
        )