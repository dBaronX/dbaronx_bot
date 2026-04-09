import os
import httpx
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

load_dotenv()

FASTAPI_URL = os.getenv("FASTAPI_URL", "").rstrip("/")
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

if not FASTAPI_URL:
    raise RuntimeError("FASTAPI_URL is required")

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is required")


async def safe_api_get(path: str, telegram_id: str):
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            f"{FASTAPI_URL}{path}",
            headers={"telegram_id": telegram_id},
        )
        response.raise_for_status()
        return response.json()


async def safe_api_post(path: str, telegram_id: str, payload: dict):
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            f"{FASTAPI_URL}{path}",
            json=payload,
            headers={"telegram_id": telegram_id},
        )
        response.raise_for_status()
        return response.json()


def main_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("💰 Watch & Earn", callback_data="watch_earn")],
            [InlineKeyboardButton("🛍 Shop", callback_data="shop")],
            [InlineKeyboardButton("💼 Balance", callback_data="balance")],
            [InlineKeyboardButton("🤖 AI Stories", callback_data="ai_stories")],
            [InlineKeyboardButton("🤝 Affiliate", callback_data="affiliate")],
        ]
    )


async def send_or_edit(update: Update, text: str, reply_markup=None):
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
        )
    else:
        await update.message.reply_text(
            text=text,
            reply_markup=reply_markup,
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🚀 dBaronX Ecosystem\n\n"
        "Choose an option below."
    )
    await send_or_edit(update, text, main_keyboard())


async def handle_watch_earn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    telegram_id = str(query.from_user.id)

    try:
        data = await safe_api_get("/ads", telegram_id)
        ads = data.get("ads", [])

        if not ads:
            await query.edit_message_text(
                "No ads available right now.\nTry again later.",
                reply_markup=main_keyboard(),
            )
            return

        ad = ads[0]

        start_response = await safe_api_post(
            "/watch/start",
            telegram_id,
            {"ad_id": ad["id"]},
        )

        text = (
            f"📺 {ad['title']}\n\n"
            f"Reward: {ad['reward_amount']} {ad['reward_currency']}\n"
            f"Minimum watch: {ad['min_watch_seconds']} seconds\n"
            f"Ads remaining today: {ad['ads_remaining_today']}\n\n"
            f"Wait for the required time, then confirm."
        )

        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("✅ Confirm Reward", callback_data=f"confirm_{ad['id']}")],
                [InlineKeyboardButton("🔙 Back", callback_data="home")],
            ]
        )

        await query.edit_message_text(text=text, reply_markup=keyboard)

    except httpx.HTTPStatusError as e:
        await query.edit_message_text(
            f"Could not fetch ads.\nAPI error: {e.response.text}",
            reply_markup=main_keyboard(),
        )
    except Exception as e:
        await query.edit_message_text(
            f"Could not fetch ads.\nError: {str(e)}",
            reply_markup=main_keyboard(),
        )


async def handle_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE, ad_id: str):
    query = update.callback_query
    telegram_id = str(query.from_user.id)

    try:
        result = await safe_api_post(
            "/confirm",
            telegram_id,
            {"ad_id": ad_id},
        )

        text = (
            f"✅ Reward confirmed\n\n"
            f"Earned: {result.get('earned', 0)} {result.get('currency', 'USD')}"
        )
        await query.edit_message_text(text=text, reply_markup=main_keyboard())

    except httpx.HTTPStatusError as e:
        await query.edit_message_text(
            f"Confirmation failed.\nAPI error: {e.response.text}",
            reply_markup=main_keyboard(),
        )
    except Exception as e:
        await query.edit_message_text(
            f"Confirmation failed.\nError: {str(e)}",
            reply_markup=main_keyboard(),
        )


async def handle_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    telegram_id = str(query.from_user.id)

    try:
        data = await safe_api_get("/products", telegram_id)
        products = data.get("products", [])

        if not products:
            await query.edit_message_text(
                "No products available right now.",
                reply_markup=main_keyboard(),
            )
            return

        lines = ["🛍 Available Products\n"]
        for product in products[:5]:
            lines.append(
                f"- {product.get('name')} | {product.get('price')} {product.get('currency', 'USD')}"
            )

        lines.append("\nFull shop is available on the website.")

        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=main_keyboard(),
        )

    except Exception as e:
        await query.edit_message_text(
            f"Could not fetch products.\nError: {str(e)}",
            reply_markup=main_keyboard(),
        )


async def handle_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    telegram_id = str(query.from_user.id)

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            user_res = await client.get(
                f"{FASTAPI_URL}/health",
                headers={"telegram_id": telegram_id},
            )
            user_res.raise_for_status()

        await query.edit_message_text(
            "💼 Balance module is active but full wallet view is coming next.\n"
            "Your backend is responding correctly.",
            reply_markup=main_keyboard(),
        )

    except Exception as e:
        await query.edit_message_text(
            f"Balance check failed.\nError: {str(e)}",
            reply_markup=main_keyboard(),
        )


async def handle_static_page(update: Update, context: ContextTypes.DEFAULT_TYPE, key: str):
    query = update.callback_query
    messages = {
        "affiliate": "🤝 Affiliate module is present and will be expanded further.",
        "ai_stories": "🤖 AI Stories module is present and will be expanded further.",
        "home": "🏠 Home",
    }
    await query.edit_message_text(messages.get(key, "Coming soon"), reply_markup=main_keyboard())


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "watch_earn":
        await handle_watch_earn(update, context)
        return

    if data.startswith("confirm_"):
        ad_id = data.split("_", 1)[1]
        await handle_confirm(update, context, ad_id)
        return

    if data == "shop":
        await handle_shop(update, context)
        return

    if data == "balance":
        await handle_balance(update, context)
        return

    if data in ["affiliate", "ai_stories", "home"]:
        await handle_static_page(update, context, data)
        return

    await query.edit_message_text("Unknown action.", reply_markup=main_keyboard())


def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()


if __name__ == "__main__":
    main()