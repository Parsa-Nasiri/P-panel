"""Verdent Platform — inline keyboards (aiogram 3)."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import texts


def main_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_BUY, callback_data="menu:buy")
    kb.button(text=texts.BTN_MY_CONFIGS, callback_data="menu:configs")
    kb.button(text=texts.BTN_TRIAL, callback_data="menu:trial")
    kb.button(text=texts.BTN_SUPPORT, callback_data="menu:support")
    kb.button(text=texts.BTN_HELP, callback_data="menu:help")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def plans_menu(plans: list) -> InlineKeyboardMarkup:
    """plans: list[Plan] — label = name + price."""
    kb = InlineKeyboardBuilder()
    for plan in plans:
        label = f"{plan.name} — {texts.format_price(plan.price_amount, plan.price_currency)}"
        kb.button(text=label, callback_data=f"plan:{plan.id}")
    kb.button(text=texts.BTN_BACK, callback_data="menu:main")
    kb.adjust(1)
    return kb.as_markup()


def payment_methods(plan_id: str, stars_available: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_PAY_CARD, callback_data=f"pay:card:{plan_id}")
    if stars_available:
        kb.button(text=texts.BTN_PAY_STARS, callback_data=f"pay:stars:{plan_id}")
    kb.button(text=texts.BTN_CANCEL, callback_data="menu:main")
    kb.adjust(1)
    return kb.as_markup()


def config_actions(config_id: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_LINK, callback_data=f"cfg:link:{config_id}")
    kb.button(text=texts.BTN_RENEW, callback_data=f"cfg:renew:{config_id}")
    kb.adjust(2)
    return kb.as_markup()


def review_buttons(order_id: str, attempt_id: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ تأیید", callback_data=f"rev:ok:{order_id}:{attempt_id}")
    kb.button(text="❌ رد", callback_data=f"rev:no:{order_id}:{attempt_id}")
    kb.adjust(2)
    return kb.as_markup()


def admin_panel(permissions: set[str]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    rows: list[list[InlineKeyboardButton]] = []

    def add(btn: InlineKeyboardButton, per_row: int = 2) -> None:
        rows.append([btn])

    if "payment.review" in permissions or "stats.view" in permissions:
        add(InlineKeyboardButton(text="🧾 سفارش‌های در انتظار", callback_data="adm:pending"))
    if "config.test" in permissions:
        add(InlineKeyboardButton(text="🧪 ساخت کانفیگ تستی", callback_data="adm:test"))
    if "admin.manage" in permissions:
        add(InlineKeyboardButton(text="👑 افزودن ادمین", callback_data="adm:addadmin"))
    if "node.manage" in permissions:
        add(InlineKeyboardButton(text="🖥 مدیریت نودها", callback_data="adm:nodes"))
        add(InlineKeyboardButton(text="➕ ساخت نود جدید", callback_data="adm:addnode"))
    add(InlineKeyboardButton(text="📊 وضعیت سیستم", callback_data="adm:stats"))

    kb.row(*[b for row in rows for b in row])
    kb.adjust(1)
    return kb.as_markup()


def back_to_main() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_BACK, callback_data="menu:main")
    return kb.as_markup()
