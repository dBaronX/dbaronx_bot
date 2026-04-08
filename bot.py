# bot.py
import os
from dotenv import load_dotenv
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

load_dotenv()

FASTAPI_URL = os.getenv("FASTAPI_URL")
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, edit=False):
    keyboard = [
        [InlineKeyboardButton("🏠 Home", callback_data="home")],
        [InlineKeyboardButton("🛍️ Shop", callback_data="shop")],
        [InlineKeyboardButton("🌟 Dreams", callback_data="dreams")],
        [InlineKeyboardButton("📖 AI Stories", callback_data="ai_stories")],
        [InlineKeyboardButton("📺 Watch & Earn", callback_data="watch_earn")],
        [InlineKeyboardButton("🤝 Affiliate", callback_data="affiliate")],
        [InlineKeyboardButton("🪙 DBX Token", callback_data="dbx_token")],
        [InlineKeyboardButton("🌍 Impact", callback_data="impact")],
        [InlineKeyboardButton("📝 Blog", callback_data="blog")],
        [InlineKeyboardButton("🆔 ID Card", callback_data="id_card")],
        [InlineKeyboardButton("💰 Balance", callback_data="balance")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "🚀 dBaronX Ecosystem – Everything inside this bot."
    
    if edit:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    telegram_id = str(query.from_user.id)

    if data == "watch_earn":
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{FASTAPI_URL}/ads", headers={"telegram_id": telegram_id})
                ads_text = resp.json()
        except Exception:
            ads_text = "⚠️ Could not fetch ads. FastAPI might be down."

        text = (
            "📺 Watch & Earn\n\n"
            + str(ads_text)
            + "\n\nReply /confirm <ad_id> after watching full ad (30s minimum enforced)."
        )
        await query.edit_message_text(text)
        return

    responses = {
        "home": "🏠 Home – Welcome to dBaronX!",
        "shop": "🛍️ Shop – Products fetched internally. Reply /shop to browse.",
        "dreams": "🌟 Dreams – Generate dreams internally. Reply /dream to start.",
        "ai_stories": "📖 AI Stories – Generate stories internally. Reply /story to start.",
        "affiliate": "🤝 Affiliate – Internal affiliate program info.",
        "dbx_token": "🪙 DBX Token – Internal DBX info.",
        "impact": "🌍 Impact – Track your ecosystem impact here.",
        "blog": "📝 Blog – Internal blog posts.",
        "id_card": "🆔 ID Card – Your internal ID card info.",
        "balance": "💰 Balance – Check your internal balance here.",
    }

    if data in responses:
        await query.edit_message_text(responses[data])
        return


def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", main_menu))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()


if __name__ == "__main__":
    main()