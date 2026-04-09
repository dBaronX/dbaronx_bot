import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
import stripe
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from supabase import Client, create_client

# =========================================================
# LOGGING
# =========================================================
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("dbaronx-bot")

# =========================================================
# ENV
# =========================================================
NODE_ENV = os.getenv("NODE_ENV", "development").strip().lower()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip()
PORT = int(os.getenv("PORT", "8080"))

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

FASTAPI_BASE_URL = os.getenv("FASTAPI_BASE_URL", "").strip().rstrip("/")
SITE_URL = os.getenv("SITE_URL_PROD", "https://dbaronx.com").strip()
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "@dBaronX_support").strip()

STRIPE_SECRET = (
    os.getenv("STRIPE_SECRET_KEY_LIVE", "").strip()
    if NODE_ENV == "production"
    else os.getenv("STRIPE_SECRET_KEY_TEST", "").strip()
)

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")

if not STRIPE_SECRET:
    logger.warning("Stripe key is missing. Checkout will fail until configured.")
else:
    stripe.api_key = STRIPE_SECRET

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

# =========================================================
# STATES
# =========================================================
(
    CHECKOUT_NAME,
    CHECKOUT_EMAIL,
    CHECKOUT_PHONE,
    CHECKOUT_ADDR1,
    CHECKOUT_ADDR2,
    CHECKOUT_CITY,
    CHECKOUT_STATE,
    CHECKOUT_POSTAL,
    CHECKOUT_COUNTRY,
    CHECKOUT_CONFIRM,
    PROFILE_NAME,
    PROFILE_EMAIL,
    PROFILE_PHONE,
    SEARCH_QUERY,
) = range(14)

# =========================================================
# CONSTANTS
# =========================================================
PRODUCTS_PAGE_SIZE = 6
MAX_ORDER_LIST = 8


# =========================================================
# HELPERS
# =========================================================
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def money(value: Any, currency: str = "USD") -> str:
    try:
        amount = float(value or 0)
    except Exception:
        amount = 0.0
    return f"{currency} {amount:,.2f}"


def clean_text(value: Optional[str], fallback: str = "—") -> str:
    return value.strip() if isinstance(value, str) and value.strip() else fallback


def is_valid_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()))


def tg_id(update: Update) -> str:
    if not update.effective_user:
        return ""
    return str(update.effective_user.id)


def user_full_name(update: Update) -> str:
    user = update.effective_user
    if not user:
        return "User"
    full = " ".join(
        x for x in [user.first_name or "", user.last_name or ""] if x.strip()
    ).strip()
    return full or user.username or "User"


async def answer_and_edit(query, text: str, reply_markup=None) -> None:
    await query.answer()
    try:
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception:
        await query.message.reply_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🛍 Shop", callback_data="menu:shop"),
                InlineKeyboardButton("🛒 Cart", callback_data="menu:cart"),
            ],
            [
                InlineKeyboardButton("📦 Orders", callback_data="menu:orders"),
                InlineKeyboardButton("💰 Wallet", callback_data="menu:wallet"),
            ],
            [
                InlineKeyboardButton("📣 Earn Ads", callback_data="menu:earn"),
                InlineKeyboardButton("👤 Profile", callback_data="menu:profile"),
            ],
            [
                InlineKeyboardButton("🤖 AI Stories", callback_data="menu:ai"),
                InlineKeyboardButton("🤝 Affiliate", callback_data="menu:affiliate"),
            ],
            [
                InlineKeyboardButton("🆘 Support", callback_data="menu:support"),
                InlineKeyboardButton("🌐 Website", url=SITE_URL),
            ],
        ]
    )


def back_home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅ Back to Menu", callback_data="menu:home")]]
    )


def product_actions_keyboard(product_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("➕ Add to Cart", callback_data=f"cart:add:{product_id}"),
                InlineKeyboardButton("⚡ Buy Now", callback_data=f"buy:{product_id}"),
            ],
            [
                InlineKeyboardButton("🛒 View Cart", callback_data="menu:cart"),
                InlineKeyboardButton("⬅ Shop", callback_data="menu:shop"),
            ],
        ]
    )


def cart_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Checkout", callback_data="checkout:start"),
                InlineKeyboardButton("🧹 Clear Cart", callback_data="cart:clear"),
            ],
            [InlineKeyboardButton("⬅ Shop", callback_data="menu:shop")],
        ]
    )


def orders_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅ Back", callback_data="menu:home")]]
    )


def earn_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔄 Refresh Ads", callback_data="earn:list")],
            [InlineKeyboardButton("⬅ Back", callback_data="menu:home")],
        ]
    )


async def api_get(url: str, headers: Optional[Dict[str, str]] = None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()


async def api_post(url: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()


def get_cart(context: ContextTypes.DEFAULT_TYPE) -> List[Dict[str, Any]]:
    return context.user_data.setdefault("cart", [])


def set_cart(context: ContextTypes.DEFAULT_TYPE, cart: List[Dict[str, Any]]) -> None:
    context.user_data["cart"] = cart


def get_checkout_draft(context: ContextTypes.DEFAULT_TYPE) -> Dict[str, Any]:
    return context.user_data.setdefault("checkout_draft", {})


def clear_checkout_draft(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("checkout_draft", None)


def get_shop_page(context: ContextTypes.DEFAULT_TYPE) -> int:
    return int(context.user_data.get("shop_page", 0))


def set_shop_page(context: ContextTypes.DEFAULT_TYPE, page: int) -> None:
    context.user_data["shop_page"] = max(0, page)


# =========================================================
# DB HELPERS
# =========================================================
def ensure_bot_user(update: Update) -> Dict[str, Any]:
    user = update.effective_user
    if not user:
        raise RuntimeError("Missing Telegram user")

    telegram_id = str(user.id)
    username = user.username or ""
    full_name = user_full_name(update)

    existing = (
        supabase.table("users")
        .select("*")
        .eq("telegram_id", telegram_id)
        .limit(1)
        .execute()
    )

    if existing.data:
        row = existing.data[0]
        supabase.table("users").update(
            {
                "username": username,
                "full_name": full_name,
                "updated_at": now_iso(),
            }
        ).eq("id", row["id"]).execute()

        refreshed = (
            supabase.table("users")
            .select("*")
            .eq("id", row["id"])
            .limit(1)
            .execute()
        )
        return refreshed.data[0]

    insert_payload = {
        "telegram_id": telegram_id,
        "username": username,
        "full_name": full_name,
        "role": "user",
        "status": "active",
        "is_active": True,
        "balance": 0,
        "metadata": {
            "telegram_username": username,
            "telegram_first_name": user.first_name,
            "telegram_last_name": user.last_name,
        },
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }

    created = supabase.table("users").insert(insert_payload).execute()
    if not created.data:
        raise RuntimeError("Failed to create bot user")
    return created.data[0]


def get_db_user_by_telegram_id(telegram_id: str) -> Dict[str, Any]:
    result = (
        supabase.table("users")
        .select("*")
        .eq("telegram_id", telegram_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise RuntimeError("User not found")
    return result.data[0]


def get_products(search: Optional[str] = None) -> List[Dict[str, Any]]:
    query = (
        supabase.table("products")
        .select("*")
        .eq("is_active", True)
        .order("is_featured", desc=True)
        .order("created_at", desc=True)
    )
    if search:
        query = query.or_(
            f"name.ilike.%{search}%,short_description.ilike.%{search}%,description.ilike.%{search}%"
        )
    result = query.execute()
    return result.data or []


def get_product_by_id(product_id: str) -> Optional[Dict[str, Any]]:
    result = (
        supabase.table("products")
        .select("*")
        .eq("id", product_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def get_orders_for_user(user_id: str, limit: int = MAX_ORDER_LIST) -> List[Dict[str, Any]]:
    result = (
        supabase.table("orders")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


def get_order_by_id(order_id: str) -> Optional[Dict[str, Any]]:
    result = (
        supabase.table("orders")
        .select("*")
        .eq("id", order_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def get_affiliate_by_user(user_id: str) -> Optional[Dict[str, Any]]:
    result = (
        supabase.table("affiliates")
        .select("*")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def update_user_profile(user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    updates["updated_at"] = now_iso()
    result = (
        supabase.table("users")
        .update(updates)
        .eq("id", user_id)
        .execute()
    )
    if result.data:
        return result.data[0]
    refreshed = (
        supabase.table("users")
        .select("*")
        .eq("id", user_id)
        .limit(1)
        .execute()
    )
    if not refreshed.data:
        raise RuntimeError("Failed to update user")
    return refreshed.data[0]


def create_order_from_cart(db_user: Dict[str, Any], checkout: Dict[str, Any], cart: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not cart:
        raise RuntimeError("Cart is empty")

    subtotal = 0.0
    items: List[Dict[str, Any]] = []
    currency = "USD"

    for item in cart:
        product = get_product_by_id(item["product_id"])
        if not product:
            raise RuntimeError(f"Product not found: {item['product_id']}")

        quantity = int(item["quantity"])
        unit_price = float(product.get("price", 0) or 0)
        subtotal += unit_price * quantity
        currency = product.get("currency", "USD") or "USD"

        items.append(
            {
                "product_id": product["id"],
                "product_name": product.get("name"),
                "slug": product.get("slug"),
                "sku": product.get("sku"),
                "quantity": quantity,
                "unit_price": unit_price,
                "supplier_source": product.get("supplier_source"),
                "supplier_product_id": product.get("cj_product_id")
                or product.get("supplier_product_id")
                or product.get("woocommerce_product_id")
                or product.get("aliexpress_product_id"),
            }
        )

    shipping_amount = 0.0
    tax_amount = 0.0
    total_amount = subtotal + shipping_amount + tax_amount

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    order_number = f"DBX-TG-{stamp}-{db_user['id'][:6]}"

    payload = {
        "user_id": db_user["id"],
        "order_number": order_number,
        "source": "telegram_bot",
        "status": "pending_payment",
        "fulfillment_status": "awaiting_supplier_order",
        "payment_status": "pending",
        "currency": currency,
        "subtotal": subtotal,
        "shipping_amount": shipping_amount,
        "tax_amount": tax_amount,
        "total_amount": total_amount,
        "customer_email": checkout["email"],
        "customer_phone": checkout["phone"],
        "customer_name": checkout["name"],
        "shipping_address_1": checkout["address1"],
        "shipping_address_2": checkout.get("address2"),
        "shipping_city": checkout["city"],
        "shipping_state": checkout["state"],
        "shipping_postal_code": checkout["postal"],
        "shipping_country": checkout["country"],
        "notes": checkout.get("notes"),
        "metadata": {
            "items": items,
            "channel": "telegram_bot",
            "telegram_id": db_user.get("telegram_id"),
        },
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }

    result = supabase.table("orders").insert(payload).execute()
    if not result.data:
        raise RuntimeError("Failed to create order")
    return result.data[0]


def create_stripe_checkout_for_order(order: Dict[str, Any]) -> str:
    if not stripe.api_key:
        raise RuntimeError("Stripe is not configured")

    amount = float(order.get("total_amount", 0) or 0)
    if amount <= 0:
        raise RuntimeError("Invalid order amount")

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        mode="payment",
        line_items=[
            {
                "price_data": {
                    "currency": str(order.get("currency", "usd")).lower(),
                    "product_data": {
                        "name": f"dBaronX Order {order.get('order_number') or order.get('id')}",
                    },
                    "unit_amount": int(round(amount * 100)),
                },
                "quantity": 1,
            }
        ],
        success_url=f"{SITE_URL}/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{SITE_URL}/cancel?order_id={order['id']}",
        metadata={
            "orderId": order["id"],
            "orderNumber": order.get("order_number", ""),
            "source": "telegram_bot",
        },
    )

    supabase.table("orders").update(
        {
            "metadata": {
                **(order.get("metadata") or {}),
                "stripe_session_id": session.id,
                "stripe_checkout_url": session.url,
            },
            "updated_at": now_iso(),
        }
    ).eq("id", order["id"]).execute()

    return session.url


async def fetch_ads_for_user(telegram_id: str) -> List[Dict[str, Any]]:
    if not FASTAPI_BASE_URL:
        return []
    data = await api_get(
        f"{FASTAPI_BASE_URL}/ads",
        headers={"telegram_id": telegram_id},
    )
    return data.get("ads", [])


async def start_ad_watch(telegram_id: str, ad_id: str) -> Dict[str, Any]:
    return await api_post(
        f"{FASTAPI_BASE_URL}/watch/start",
        {"ad_id": ad_id},
        headers={"telegram_id": telegram_id},
    )


async def confirm_ad_watch(telegram_id: str, ad_id: str) -> Dict[str, Any]:
    return await api_post(
        f"{FASTAPI_BASE_URL}/confirm",
        {"ad_id": ad_id},
        headers={"telegram_id": telegram_id},
    )


def cart_summary(cart: List[Dict[str, Any]]) -> Tuple[str, float, str]:
    if not cart:
        return "Your cart is empty.", 0.0, "USD"

    lines = ["<b>🛒 Your Cart</b>", ""]
    subtotal = 0.0
    currency = "USD"

    for i, item in enumerate(cart, start=1):
        product = get_product_by_id(item["product_id"])
        if not product:
            continue
        qty = int(item["quantity"])
        price = float(product.get("price", 0) or 0)
        currency = product.get("currency", "USD") or "USD"
        subtotal += price * qty
        lines.append(
            f"{i}. <b>{clean_text(product.get('name'))}</b>\n"
            f"   Qty: {qty} | Unit: {money(price, currency)} | Total: {money(price * qty, currency)}"
        )

    lines += ["", f"<b>Subtotal:</b> {money(subtotal, currency)}"]
    return "\n".join(lines), subtotal, currency


def profile_text(user: Dict[str, Any], affiliate: Optional[Dict[str, Any]]) -> str:
    return (
        "<b>👤 Your Profile</b>\n\n"
        f"<b>Name:</b> {clean_text(user.get('full_name'))}\n"
        f"<b>Email:</b> {clean_text(user.get('email'))}\n"
        f"<b>Phone:</b> {clean_text(user.get('phone'))}\n"
        f"<b>Telegram ID:</b> {clean_text(user.get('telegram_id'))}\n"
        f"<b>Balance:</b> {money(user.get('balance', 0), 'USD')}\n"
        f"<b>Referral Code:</b> {clean_text(affiliate.get('referral_code') if affiliate else None)}\n"
        f"<b>Status:</b> {clean_text(user.get('status'))}\n"
    )


# =========================================================
# MENUS
# =========================================================
async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, text: Optional[str] = None) -> None:
    db_user = ensure_bot_user(update)
    affiliate = get_affiliate_by_user(db_user["id"])
    body = text or (
        f"<b>Welcome to dBaronX, {clean_text(db_user.get('full_name'), 'User')}.</b>\n\n"
        f"Balance: <b>{money(db_user.get('balance', 0), 'USD')}</b>\n"
        f"Referral: <b>{clean_text(affiliate.get('referral_code') if affiliate else None, 'Not set')}</b>\n\n"
        "Choose what you want to do:"
    )

    if update.callback_query:
        await answer_and_edit(update.callback_query, body, main_menu_keyboard())
    else:
        await update.effective_message.reply_text(
            body,
            reply_markup=main_menu_keyboard(),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )


async def render_shop(update: Update, context: ContextTypes.DEFAULT_TYPE, page: Optional[int] = None, search: Optional[str] = None) -> None:
    if page is None:
        page = get_shop_page(context)
    set_shop_page(context, page)

    products = get_products(search=search)
    if not products:
        text = "<b>🛍 Shop</b>\n\nNo products available right now."
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🔍 Search", callback_data="shop:search")],
                [InlineKeyboardButton("⬅ Back", callback_data="menu:home")],
            ]
        )
        if update.callback_query:
            await answer_and_edit(update.callback_query, text, keyboard)
        else:
            await update.effective_message.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        return

    start = page * PRODUCTS_PAGE_SIZE
    end = start + PRODUCTS_PAGE_SIZE
    chunk = products[start:end]

    lines = ["<b>🛍 Shop</b>", ""]
    keyboard_rows: List[List[InlineKeyboardButton]] = []

    for product in chunk:
        lines.append(
            f"• <b>{clean_text(product.get('name'))}</b>\n"
            f"  {money(product.get('price', 0), product.get('currency', 'USD'))}\n"
            f"  {clean_text(product.get('short_description'))}\n"
        )
        keyboard_rows.append(
            [InlineKeyboardButton(
                f"View: {clean_text(product.get('name'))[:36]}",
                callback_data=f"product:{product['id']}",
            )]
        )

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅ Prev", callback_data=f"shop:page:{page-1}"))
    if end < len(products):
        nav_row.append(InlineKeyboardButton("Next ➡", callback_data=f"shop:page:{page+1}"))
    if nav_row:
        keyboard_rows.append(nav_row)

    keyboard_rows.append([InlineKeyboardButton("🔍 Search", callback_data="shop:search")])
    keyboard_rows.append([InlineKeyboardButton("🛒 Cart", callback_data="menu:cart"), InlineKeyboardButton("⬅ Menu", callback_data="menu:home")])

    markup = InlineKeyboardMarkup(keyboard_rows)

    if update.callback_query:
        await answer_and_edit(update.callback_query, "\n".join(lines), markup)
    else:
        await update.effective_message.reply_text(
            "\n".join(lines),
            reply_markup=markup,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )


async def render_product(update: Update, product_id: str) -> None:
    product = get_product_by_id(product_id)
    if not product:
        text = "❌ Product not found."
        if update.callback_query:
            await answer_and_edit(update.callback_query, text, back_home_keyboard())
        else:
            await update.effective_message.reply_text(text, reply_markup=back_home_keyboard())
        return

    text = (
        f"<b>{clean_text(product.get('name'))}</b>\n\n"
        f"<b>Price:</b> {money(product.get('price', 0), product.get('currency', 'USD'))}\n"
        f"<b>Category:</b> {clean_text(product.get('category'))}\n"
        f"<b>Stock:</b> {clean_text(product.get('stock_status'))}\n\n"
        f"{clean_text(product.get('description') or product.get('short_description'))}"
    )

    if update.callback_query:
        await answer_and_edit(update.callback_query, text, product_actions_keyboard(product_id))
    else:
        await update.effective_message.reply_text(
            text,
            reply_markup=product_actions_keyboard(product_id),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )


async def render_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text, _, _ = cart_summary(get_cart(context))
    markup = cart_keyboard() if get_cart(context) else back_home_keyboard()

    if update.callback_query:
        await answer_and_edit(update.callback_query, text, markup)
    else:
        await update.effective_message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)


async def render_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db_user = get_db_user_by_telegram_id(tg_id(update))
    orders = get_orders_for_user(db_user["id"], MAX_ORDER_LIST)

    if not orders:
        text = "<b>📦 Your Orders</b>\n\nNo orders yet."
        if update.callback_query:
            await answer_and_edit(update.callback_query, text, orders_keyboard())
        else:
            await update.effective_message.reply_text(text, reply_markup=orders_keyboard(), parse_mode=ParseMode.HTML)
        return

    lines = ["<b>📦 Your Recent Orders</b>", ""]
    rows: List[List[InlineKeyboardButton]] = []

    for order in orders:
        lines.append(
            f"• <b>{clean_text(order.get('order_number'))}</b>\n"
            f"  Amount: {money(order.get('total_amount', 0), order.get('currency', 'USD'))}\n"
            f"  Payment: {clean_text(order.get('payment_status'))}\n"
            f"  Fulfillment: {clean_text(order.get('fulfillment_status'))}\n"
        )
        rows.append(
            [InlineKeyboardButton(
                f"Details: {clean_text(order.get('order_number'))}",
                callback_data=f"order:{order['id']}",
            )]
        )

    rows.append([InlineKeyboardButton("⬅ Back", callback_data="menu:home")])
    markup = InlineKeyboardMarkup(rows)

    if update.callback_query:
        await answer_and_edit(update.callback_query, "\n".join(lines), markup)
    else:
        await update.effective_message.reply_text("\n".join(lines), reply_markup=markup, parse_mode=ParseMode.HTML)


async def render_order_detail(update: Update, order_id: str) -> None:
    order = get_order_by_id(order_id)
    if not order:
        await answer_and_edit(update.callback_query, "❌ Order not found.", back_home_keyboard())
        return

    tracking = clean_text(order.get("tracking_number"))
    supplier_order = clean_text(order.get("supplier_order_id"))
    text = (
        f"<b>📦 Order {clean_text(order.get('order_number'))}</b>\n\n"
        f"<b>Amount:</b> {money(order.get('total_amount', 0), order.get('currency', 'USD'))}\n"
        f"<b>Payment:</b> {clean_text(order.get('payment_status'))}\n"
        f"<b>Status:</b> {clean_text(order.get('status'))}\n"
        f"<b>Fulfillment:</b> {clean_text(order.get('fulfillment_status'))}\n"
        f"<b>Supplier Order:</b> {supplier_order}\n"
        f"<b>Tracking:</b> {tracking}\n"
        f"<b>Customer:</b> {clean_text(order.get('customer_name'))}\n"
        f"<b>Address:</b> {clean_text(order.get('shipping_address_1'))}, "
        f"{clean_text(order.get('shipping_city'))}, {clean_text(order.get('shipping_country'))}\n"
    )

    markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅ Orders", callback_data="menu:orders")]]
    )
    await answer_and_edit(update.callback_query, text, markup)


async def render_wallet(update: Update) -> None:
    db_user = get_db_user_by_telegram_id(tg_id(update))
    affiliate = get_affiliate_by_user(db_user["id"])

    text = (
        "<b>💰 Wallet</b>\n\n"
        f"<b>Balance:</b> {money(db_user.get('balance', 0), 'USD')}\n"
        f"<b>Affiliate Earnings:</b> {money(affiliate.get('total_earnings', 0), 'USD') if affiliate else 'USD 0.00'}\n"
        f"<b>Available Balance:</b> {money(affiliate.get('available_balance', 0), 'USD') if affiliate else 'USD 0.00'}\n"
        f"<b>Locked Balance:</b> {money(affiliate.get('locked_balance', 0), 'USD') if affiliate else 'USD 0.00'}\n\n"
        "Payout requests and advanced wallet actions can be enabled next."
    )

    markup = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📣 Earn More", callback_data="menu:earn")],
            [InlineKeyboardButton("⬅ Back", callback_data="menu:home")],
        ]
    )

    await answer_and_edit(update.callback_query, text, markup)


async def render_profile(update: Update) -> None:
    db_user = get_db_user_by_telegram_id(tg_id(update))
    affiliate = get_affiliate_by_user(db_user["id"])

    markup = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✏ Edit Name", callback_data="profile:edit:name")],
            [InlineKeyboardButton("✏ Edit Email", callback_data="profile:edit:email")],
            [InlineKeyboardButton("✏ Edit Phone", callback_data="profile:edit:phone")],
            [InlineKeyboardButton("⬅ Back", callback_data="menu:home")],
        ]
    )
    await answer_and_edit(update.callback_query, profile_text(db_user, affiliate), markup)


async def render_earn(update: Update) -> None:
    if not FASTAPI_BASE_URL:
        text = (
            "<b>📣 Earn With Ads</b>\n\n"
            "Watch-to-earn service is not connected yet.\n"
            "The bot UI is ready. Backend can be activated anytime."
        )
        await answer_and_edit(update.callback_query, text, back_home_keyboard())
        return

    ads = await fetch_ads_for_user(tg_id(update))

    if not ads:
        text = (
            "<b>📣 Earn With Ads</b>\n\n"
            "No eligible ads right now or you have exhausted your daily allocation."
        )
        await answer_and_edit(update.callback_query, text, earn_keyboard())
        return

    lines = ["<b>📣 Available Ads</b>", ""]
    rows: List[List[InlineKeyboardButton]] = []

    for ad in ads[:8]:
        lines.append(
            f"• <b>{clean_text(ad.get('title'))}</b>\n"
            f"  Reward: {money(ad.get('reward_amount', 0), ad.get('reward_currency', 'USD'))}\n"
            f"  Minimum watch: {ad.get('min_watch_seconds', 30)}s\n"
            f"  Category: {clean_text(ad.get('category'))}\n"
        )
        rows.append(
            [InlineKeyboardButton(
                f"Start: {clean_text(ad.get('title'))[:34]}",
                callback_data=f"earn:start:{ad['id']}",
            )]
        )

    rows.append([InlineKeyboardButton("⬅ Back", callback_data="menu:home")])
    await answer_and_edit(update.callback_query, "\n".join(lines), InlineKeyboardMarkup(rows))


# =========================================================
# COMMANDS
# =========================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_chat.send_action(ChatAction.TYPING)
    ensure_bot_user(update)
    await send_main_menu(update, context)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "<b>dBaronX Bot Help</b>\n\n"
        "/start - open main menu\n"
        "/help - show help\n"
        "/shop - browse products\n"
        "/cart - view cart\n"
        "/orders - view recent orders\n"
        "/wallet - view balance\n"
        "/earn - open ads/watch-to-earn\n"
        "/profile - view profile\n"
        "/cancel - cancel current flow\n\n"
        "Most actions can also be done from the menu buttons."
    )
    await update.effective_message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_keyboard(),
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    clear_checkout_draft(context)
    context.user_data.pop("profile_field", None)
    await update.effective_message.reply_text(
        "Cancelled.",
        reply_markup=main_menu_keyboard(),
    )
    return ConversationHandler.END


async def shop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    set_shop_page(context, 0)
    await render_shop(update, context, page=0)


async def cart_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await render_cart(update, context)


async def orders_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await render_orders(update, context)


async def wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    fake_update = update
    if update.callback_query:
        await render_wallet(fake_update)
    else:
        query = None
        db_user = get_db_user_by_telegram_id(tg_id(update))
        affiliate = get_affiliate_by_user(db_user["id"])
        text = (
            "<b>💰 Wallet</b>\n\n"
            f"<b>Balance:</b> {money(db_user.get('balance', 0), 'USD')}\n"
            f"<b>Affiliate Earnings:</b> {money(affiliate.get('total_earnings', 0), 'USD') if affiliate else 'USD 0.00'}\n"
        )
        await update.effective_message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=back_home_keyboard(),
        )


async def earn_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query:
        await render_earn(update)
    else:
        await update.effective_message.reply_text(
            "Open the Earn menu below.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("📣 Earn Ads", callback_data="menu:earn")]]
            ),
        )


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db_user = get_db_user_by_telegram_id(tg_id(update))
    affiliate = get_affiliate_by_user(db_user["id"])
    await update.effective_message.reply_text(
        profile_text(db_user, affiliate),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("👤 Open Profile Menu", callback_data="menu:profile")]]
        ),
    )


# =========================================================
# CALLBACKS
# =========================================================
async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data

    if data == "menu:home":
        await send_main_menu(update, context)
        return

    if data == "menu:shop":
        set_shop_page(context, 0)
        await render_shop(update, context, page=0)
        return

    if data == "menu:cart":
        await render_cart(update, context)
        return

    if data == "menu:orders":
        await render_orders(update, context)
        return

    if data == "menu:wallet":
        await render_wallet(update)
        return

    if data == "menu:earn":
        await render_earn(update)
        return

    if data == "menu:profile":
        await render_profile(update)
        return

    if data == "menu:ai":
        await answer_and_edit(
            query,
            "<b>🤖 AI Stories</b>\n\nThis module is preserved and ready for future activation.\nCurrent public priority is e-commerce.",
            back_home_keyboard(),
        )
        return

    if data == "menu:affiliate":
        await answer_and_edit(
            query,
            "<b>🤝 Affiliate</b>\n\nAffiliate tools are in controlled rollout.\nWatch-to-earn is the current visible entry point from the bot.",
            back_home_keyboard(),
        )
        return

    if data == "menu:support":
        await answer_and_edit(
            query,
            (
                "<b>🆘 Support</b>\n\n"
                f"Contact support: {SUPPORT_USERNAME}\n"
                f"Website: {SITE_URL}\n\n"
                "For payment issues, tracking, and order support, send your order number."
            ),
            back_home_keyboard(),
        )
        return


async def shop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    query = update.callback_query
    data = query.data

    if data.startswith("shop:page:"):
        page = int(data.split(":")[-1])
        await render_shop(update, context, page=page)
        return None

    if data == "shop:search":
        await answer_and_edit(
            query,
            "Send the product name or keyword you want to search.",
            InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅ Cancel", callback_data="menu:shop")]]
            ),
        )
        return SEARCH_QUERY

    if data.startswith("product:"):
        product_id = data.split(":")[1]
        await render_product(update, product_id)
        return None

    return None


async def add_to_cart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data

    if data.startswith("cart:add:"):
        product_id = data.split(":")[2]
        product = get_product_by_id(product_id)
        if not product:
            await answer_and_edit(query, "❌ Product not found.", back_home_keyboard())
            return

        cart = get_cart(context)
        existing = next((x for x in cart if x["product_id"] == product_id), None)
        if existing:
            existing["quantity"] += 1
        else:
            cart.append({"product_id": product_id, "quantity": 1})
        set_cart(context, cart)

        await answer_and_edit(
            query,
            f"✅ Added <b>{clean_text(product.get('name'))}</b> to cart.",
            InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("🛒 View Cart", callback_data="menu:cart"),
                        InlineKeyboardButton("⬅ Continue Shopping", callback_data="menu:shop"),
                    ]
                ]
            ),
        )
        return

    if data == "cart:clear":
        set_cart(context, [])
        await answer_and_edit(
            query,
            "🧹 Cart cleared.",
            InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅ Shop", callback_data="menu:shop")]]
            ),
        )


async def buy_now_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    product_id = query.data.split(":")[1]
    product = get_product_by_id(product_id)
    if not product:
        await answer_and_edit(query, "❌ Product not found.", back_home_keyboard())
        return

    set_cart(context, [{"product_id": product_id, "quantity": 1}])
    await answer_and_edit(
        query,
        f"⚡ <b>{clean_text(product.get('name'))}</b> is ready for checkout.\n\nPress continue to enter shipping details.",
        InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("✅ Continue Checkout", callback_data="checkout:start")],
                [InlineKeyboardButton("⬅ Back", callback_data="menu:shop")],
            ]
        ),
    )


async def search_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    search = update.effective_message.text.strip()
    await render_shop(update, context, page=0, search=search)
    return ConversationHandler.END


# =========================================================
# CHECKOUT FLOW
# =========================================================
async def checkout_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    cart = get_cart(context)
    if not cart:
        await answer_and_edit(query, "Your cart is empty.", back_home_keyboard())
        return ConversationHandler.END

    clear_checkout_draft(context)
    await answer_and_edit(query, "Enter full name for this order:")
    return CHECKOUT_NAME


async def checkout_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    get_checkout_draft(context)["name"] = update.effective_message.text.strip()
    await update.effective_message.reply_text("Enter email address:")
    return CHECKOUT_EMAIL


async def checkout_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    email = update.effective_message.text.strip()
    if not is_valid_email(email):
        await update.effective_message.reply_text("Invalid email. Enter a valid email:")
        return CHECKOUT_EMAIL

    draft = get_checkout_draft(context)
    draft["email"] = email
    await update.effective_message.reply_text("Enter phone number:")
    return CHECKOUT_PHONE


async def checkout_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    get_checkout_draft(context)["phone"] = update.effective_message.text.strip()
    await update.effective_message.reply_text("Enter shipping address line 1:")
    return CHECKOUT_ADDR1


async def checkout_addr1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    get_checkout_draft(context)["address1"] = update.effective_message.text.strip()
    await update.effective_message.reply_text("Enter shipping address line 2 or type SKIP:")
    return CHECKOUT_ADDR2


async def checkout_addr2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    value = update.effective_message.text.strip()
    get_checkout_draft(context)["address2"] = None if value.upper() == "SKIP" else value
    await update.effective_message.reply_text("Enter city:")
    return CHECKOUT_CITY


async def checkout_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    get_checkout_draft(context)["city"] = update.effective_message.text.strip()
    await update.effective_message.reply_text("Enter state/province:")
    return CHECKOUT_STATE


async def checkout_state(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    get_checkout_draft(context)["state"] = update.effective_message.text.strip()
    await update.effective_message.reply_text("Enter postal/ZIP code:")
    return CHECKOUT_POSTAL


async def checkout_postal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    get_checkout_draft(context)["postal"] = update.effective_message.text.strip()
    await update.effective_message.reply_text("Enter country:")
    return CHECKOUT_COUNTRY


async def checkout_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = get_checkout_draft(context)
    draft["country"] = update.effective_message.text.strip()

    cart_text, subtotal, currency = cart_summary(get_cart(context))
    summary = (
        "<b>Confirm Checkout</b>\n\n"
        f"{cart_text}\n\n"
        f"<b>Name:</b> {draft['name']}\n"
        f"<b>Email:</b> {draft['email']}\n"
        f"<b>Phone:</b> {draft['phone']}\n"
        f"<b>Address 1:</b> {draft['address1']}\n"
        f"<b>Address 2:</b> {clean_text(draft.get('address2'))}\n"
        f"<b>City:</b> {draft['city']}\n"
        f"<b>State:</b> {draft['state']}\n"
        f"<b>Postal:</b> {draft['postal']}\n"
        f"<b>Country:</b> {draft['country']}\n\n"
        f"<b>Total:</b> {money(subtotal, currency)}"
    )

    await update.effective_message.reply_text(
        summary,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("✅ Create Order & Pay", callback_data="checkout:confirm")],
                [InlineKeyboardButton("❌ Cancel", callback_data="menu:cart")],
            ]
        ),
    )
    return CHECKOUT_CONFIRM


async def checkout_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    db_user = get_db_user_by_telegram_id(tg_id(update))
    draft = get_checkout_draft(context)
    cart = get_cart(context)

    try:
        order = create_order_from_cart(db_user, draft, cart)
        checkout_url = create_stripe_checkout_for_order(order)

        set_cart(context, [])
        clear_checkout_draft(context)

        text = (
            f"<b>✅ Order Created</b>\n\n"
            f"<b>Order:</b> {clean_text(order.get('order_number'))}\n"
            f"<b>Amount:</b> {money(order.get('total_amount', 0), order.get('currency', 'USD'))}\n"
            f"<b>Payment Status:</b> {clean_text(order.get('payment_status'))}\n\n"
            "Tap below to complete payment."
        )

        markup = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("💳 Pay Now", url=checkout_url)],
                [InlineKeyboardButton("📦 View Orders", callback_data="menu:orders")],
                [InlineKeyboardButton("⬅ Menu", callback_data="menu:home")],
            ]
        )

        await answer_and_edit(query, text, markup)
        return ConversationHandler.END

    except Exception as exc:
        logger.exception("Checkout failed")
        await answer_and_edit(
            query,
            f"❌ Checkout failed.\n\nReason: {clean_text(str(exc))}",
            InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Cart", callback_data="menu:cart")]]),
        )
        return ConversationHandler.END


# =========================================================
# PROFILE EDIT FLOW
# =========================================================
async def profile_edit_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    field = query.data.split(":")[-1]
    context.user_data["profile_field"] = field

    prompts = {
        "name": "Enter your full name:",
        "email": "Enter your email:",
        "phone": "Enter your phone:",
    }

    await answer_and_edit(
        query,
        prompts[field],
        InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Cancel", callback_data="menu:profile")]]),
    )

    if field == "name":
        return PROFILE_NAME
    if field == "email":
        return PROFILE_EMAIL
    return PROFILE_PHONE


async def profile_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db_user = get_db_user_by_telegram_id(tg_id(update))
    update_user_profile(db_user["id"], {"full_name": update.effective_message.text.strip()})
    await update.effective_message.reply_text("✅ Name updated.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


async def profile_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    email = update.effective_message.text.strip()
    if not is_valid_email(email):
        await update.effective_message.reply_text("Invalid email. Enter a valid email:")
        return PROFILE_EMAIL

    db_user = get_db_user_by_telegram_id(tg_id(update))
    update_user_profile(db_user["id"], {"email": email})
    await update.effective_message.reply_text("✅ Email updated.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


async def profile_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db_user = get_db_user_by_telegram_id(tg_id(update))
    update_user_profile(db_user["id"], {"phone": update.effective_message.text.strip()})
    await update.effective_message.reply_text("✅ Phone updated.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


# =========================================================
# EARN FLOW
# =========================================================
async def earn_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data

    if data == "earn:list":
        await render_earn(update)
        return

    if data.startswith("earn:start:"):
        ad_id = data.split(":")[-1]
        try:
            result = await start_ad_watch(tg_id(update), ad_id)
            required_watch_seconds = result.get("required_watch_seconds", 30)

            await answer_and_edit(
                query,
                (
                    "<b>▶ Watch Started</b>\n\n"
                    f"Minimum watch time: <b>{required_watch_seconds}s</b>\n\n"
                    "After watching long enough, tap confirm."
                ),
                InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("✅ Confirm Reward", callback_data=f"earn:confirm:{ad_id}")],
                        [InlineKeyboardButton("⬅ Ads", callback_data="earn:list")],
                    ]
                ),
            )
        except Exception as exc:
            logger.exception("earn:start failed")
            await answer_and_edit(
                query,
                f"❌ Could not start ad watch.\n{clean_text(str(exc))}",
                earn_keyboard(),
            )
        return

    if data.startswith("earn:confirm:"):
        ad_id = data.split(":")[-1]
        try:
            result = await confirm_ad_watch(tg_id(update), ad_id)
            earned = result.get("earned", 0)
            currency = result.get("currency", "USD")

            db_user = get_db_user_by_telegram_id(tg_id(update))
            await answer_and_edit(
                query,
                (
                    "<b>✅ Reward Earned</b>\n\n"
                    f"You earned: <b>{money(earned, currency)}</b>\n"
                    f"New balance: <b>{money(db_user.get('balance', 0), 'USD')}</b>"
                ),
                InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("📣 More Ads", callback_data="earn:list")],
                        [InlineKeyboardButton("💰 Wallet", callback_data="menu:wallet")],
                    ]
                ),
            )
        except Exception as exc:
            logger.exception("earn:confirm failed")
            await answer_and_edit(
                query,
                f"❌ Reward confirmation failed.\n{clean_text(str(exc))}",
                earn_keyboard(),
            )
        return


# =========================================================
# FALLBACK TEXT
# =========================================================
async def text_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.effective_message.text or "").strip().lower()

    quick_map = {
        "shop": "/shop",
        "cart": "/cart",
        "orders": "/orders",
        "wallet": "/wallet",
        "earn": "/earn",
        "profile": "/profile",
        "help": "/help",
        "menu": "/start",
    }

    if text in quick_map:
        await update.effective_message.reply_text(
            f"Use {quick_map[text]} or the buttons below.",
            reply_markup=main_menu_keyboard(),
        )
        return

    await update.effective_message.reply_text(
        "Use the menu below to continue.",
        reply_markup=main_menu_keyboard(),
    )


# =========================================================
# ERROR HANDLER
# =========================================================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled bot error", exc_info=context.error)

    try:
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(
                "⚠ Something went wrong. Please try again.",
                reply_markup=main_menu_keyboard(),
            )
    except Exception:
        logger.exception("Failed to send error message to user")


# =========================================================
# APP BUILD
# =========================================================
def build_application() -> Application:
    app = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .concurrent_updates(False)
        .build()
    )

    checkout_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(checkout_entry, pattern=r"^checkout:start$")],
        states={
            CHECKOUT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, checkout_name)],
            CHECKOUT_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, checkout_email)],
            CHECKOUT_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, checkout_phone)],
            CHECKOUT_ADDR1: [MessageHandler(filters.TEXT & ~filters.COMMAND, checkout_addr1)],
            CHECKOUT_ADDR2: [MessageHandler(filters.TEXT & ~filters.COMMAND, checkout_addr2)],
            CHECKOUT_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, checkout_city)],
            CHECKOUT_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, checkout_state)],
            CHECKOUT_POSTAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, checkout_postal)],
            CHECKOUT_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, checkout_country)],
            CHECKOUT_CONFIRM: [
                CallbackQueryHandler(checkout_confirm_callback, pattern=r"^checkout:confirm$")
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    profile_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(profile_edit_entry, pattern=r"^profile:edit:(name|email|phone)$")],
        states={
            PROFILE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_name)],
            PROFILE_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_email)],
            PROFILE_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_phone)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    search_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(shop_callback, pattern=r"^shop:search$")],
        states={
            SEARCH_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_receive)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("shop", shop_command))
    app.add_handler(CommandHandler("cart", cart_command))
    app.add_handler(CommandHandler("orders", orders_command))
    app.add_handler(CommandHandler("wallet", wallet_command))
    app.add_handler(CommandHandler("earn", earn_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("cancel", cancel))

    app.add_handler(checkout_conv)
    app.add_handler(profile_conv)
    app.add_handler(search_conv)

    app.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^menu:"))
    app.add_handler(CallbackQueryHandler(shop_callback, pattern=r"^(shop:page:|product:|shop:search$)"))
    app.add_handler(CallbackQueryHandler(add_to_cart_callback, pattern=r"^(cart:add:|cart:clear$)"))
    app.add_handler(CallbackQueryHandler(buy_now_callback, pattern=r"^buy:"))
    app.add_handler(CallbackQueryHandler(earn_callback, pattern=r"^earn:"))

    app.add_handler(CallbackQueryHandler(lambda u, c: render_order_detail(u, u.callback_query.data.split(":")[1]), pattern=r"^order:"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_fallback))
    app.add_error_handler(error_handler)

    return app


# =========================================================
# MAIN
# =========================================================
if __name__ == "__main__":
    application = build_application()

    if WEBHOOK_URL:
        logger.info("Starting bot in webhook mode on port %s", PORT)
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=WEBHOOK_URL,
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )
    else:
        logger.info("WEBHOOK_URL missing. Falling back to polling mode.")
        application.run_polling(drop_pending_updates=True)