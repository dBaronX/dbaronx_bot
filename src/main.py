from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
import uvicorn
from telegram import Update as TgUpdate

from src.config.settings import get_settings
from src.core.bot import build_application
from src.utils.logger import setup_logger


logger = setup_logger()
settings = get_settings()
telegram_app = build_application()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await telegram_app.initialize()

    if settings.bot_env.lower() == "development":
        if telegram_app.updater is None:
            raise RuntimeError("Telegram updater is not available for polling mode.")

        await telegram_app.start()
        await telegram_app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram bot started in polling mode (development).")
    else:
        await telegram_app.bot.set_webhook(
            url=settings.telegram_webhook_url,
            secret_token=settings.telegram_webhook_secret,
            allowed_updates=["message", "callback_query"],
        )
        await telegram_app.start()
        logger.info("Telegram bot started in webhook mode (production).")

    yield

    if settings.bot_env.lower() == "development":
        if telegram_app.updater is not None:
            await telegram_app.updater.stop()
    else:
        await telegram_app.bot.delete_webhook()

    await telegram_app.stop()
    await telegram_app.shutdown()
    logger.info("Telegram bot stopped cleanly.")


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root() -> dict:
    return {"ok": True, "message": "dBaronX Telegram bot is running"}


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "service": "dbaronx-telegram-bot"}


@app.post("/webhook")
async def webhook(request: Request) -> dict:
    if settings.bot_env.lower() == "development":
        raise HTTPException(status_code=400, detail="Webhook endpoint is disabled in development mode.")

    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret != settings.telegram_webhook_secret:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    data = await request.json()
    await telegram_app.update_queue.put(TgUpdate.de_json(data, telegram_app.bot))
    return {"ok": True}


if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host=settings.bot_host,
        port=settings.bot_port,
        reload=settings.bot_env.lower() == "development",
    )