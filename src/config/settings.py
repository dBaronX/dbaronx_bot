from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_webhook_secret: str
    telegram_webhook_url: str
    bot_port: int
    bot_host: str
    bot_env: str

    nest_api_base_url: str
    nest_internal_api_key: str

    default_language: str
    default_currency: str
    request_timeout: int


def get_settings() -> Settings:
    return Settings(
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_webhook_secret=os.getenv("TELEGRAM_WEBHOOK_SECRET", ""),
        telegram_webhook_url=os.getenv("TELEGRAM_WEBHOOK_URL", ""),
        bot_port=int(os.getenv("BOT_PORT", "8080")),
        bot_host=os.getenv("BOT_HOST", "0.0.0.0"),
        bot_env=os.getenv("BOT_ENV", "development"),
        nest_api_base_url=os.getenv("NEST_API_BASE_URL", "").rstrip("/"),
        nest_internal_api_key=os.getenv("NEST_INTERNAL_API_KEY", ""),
        default_language=os.getenv("DEFAULT_LANGUAGE", "en"),
        default_currency=os.getenv("DEFAULT_CURRENCY", "USD"),
        request_timeout=int(os.getenv("REQUEST_TIMEOUT", "20")),
    )