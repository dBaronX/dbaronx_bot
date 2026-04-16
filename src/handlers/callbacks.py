from telegram import Update
from telegram.ext import ContextTypes

from src.core.session import session_store
from src.core.keyboards import role_keyboard
from src.services.user_service import UserService


user_service = UserService()


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not update.effective_user:
        return

    await query.answer()

    telegram_id = str(update.effective_user.id)
    data = query.data or ""

    session = session_store.get(telegram_id)

    if data.startswith("lang:"):
        language = data.split(":", 1)[1]
        session["language"] = language
        session_store.set(telegram_id, session)
        await query.edit_message_text(
            f"Language set to: {language}\n\nNow choose your role.",
            reply_markup=role_keyboard(),
        )
        return

    if data.startswith("role:"):
        role = data.split(":", 1)[1]
        session["role"] = role

        payload = {
            "telegram_id": telegram_id,
            "language": session.get("language", "en"),
            "role": role,
        }
        await user_service.upsert_profile(payload)

        await query.edit_message_text(
            f"Role set to: {role}\n\nProfile saved successfully."
        )
        return