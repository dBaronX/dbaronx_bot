from telegram.ext import Application

from src.config.settings import get_settings
from src.core.commands import register_handlers


def build_application() -> Application:
    settings = get_settings()

    app = Application.builder().token(settings.telegram_bot_token).build()
    register_handlers(app)
    return app