from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from src.handlers.account import account_handler
from src.handlers.affiliate import affiliate_handler
from src.handlers.callbacks import callback_handler
from src.handlers.shop import shop_handler
from src.handlers.start import start_handler
from src.handlers.support import support_handler


def register_handlers(app: Application) -> None:
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("register", start_handler))
    app.add_handler(CommandHandler("affiliate", affiliate_handler))
    app.add_handler(CommandHandler("shop", shop_handler))
    app.add_handler(CommandHandler("account", account_handler))
    app.add_handler(CommandHandler("help", support_handler))

    app.add_handler(CallbackQueryHandler(callback_handler))

    app.add_handler(
        MessageHandler(filters.Regex("^🤝 Affiliate$"), affiliate_handler)
    )
    app.add_handler(
        MessageHandler(filters.Regex("^🛍 Shop$"), shop_handler)
    )
    app.add_handler(
        MessageHandler(filters.Regex("^👤 Account$"), account_handler)
    )
    app.add_handler(
        MessageHandler(filters.Regex("^💬 Support$"), support_handler)
    )