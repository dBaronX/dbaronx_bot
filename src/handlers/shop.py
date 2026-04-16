from telegram import Update
from telegram.ext import ContextTypes


async def shop_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(
            "Shop module connected.\n"
            "Next step: pull categories/products from NestJS API."
        )