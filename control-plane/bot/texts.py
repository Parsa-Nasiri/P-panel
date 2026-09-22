"""Verdent Platform — all customer/admin-facing Persian strings.

Two hard rules from the blueprint (Document 2 "honesty in copy", Document 4):
- Gaming plans are sold on Stability & DNS (Tier A) and WARP (Tier B) gains.
  NOTHING here may claim UDP support, lower ping, or jitter improvements —
  Workers cannot do real UDP.
- No "unlimited" phrasing where a quota exists.
"""

# ---------------------------------------------------------------------------
# Generic
# ---------------------------------------------------------------------------

APP_NAME = "وردنت"
BTN_BUY = "🛒 خرید اشتراک"
BTN_MY_CONFIGS = "📂 اشتراک‌های من"
BTN_TRIAL = "🧪 اشتراک آزمایشی رایگان"
BTN_SUPPORT = "🆘 پشتیبانی"
BTN_HELP = "📖 راهنما"
BTN_BACK = "↩️ بازگشت"
BTN_PAY_CARD = "💳 پرداخت ریالی (کارت به کارت)"
BTN_PAY_STARS = "⭐️ پرداخت با تلگرام استارز"
BTN_RENEW = "🔄 تمدید"
BTN_LINK = "🔗 لینک اشتراک"
BTN_CANCEL = "✖️ انصراف"

MSG_WELCOME = (
    "سلام {name} عزیز! 👋\n\n"
    "به {app} خوش آمدید.\n"
    "از منوی زیر انتخاب کنید:"
)

MSG_HELP = (
    "📖 <b>راهنما</b>\n\n"
    "۱. «خرید اشتراک» را بزنید و پلن موردنظر را انتخاب کنید.\n"
    "۲. یک <b>نام نمایشی</b> برای کانفیگ خود بنویسید (حداکثر ۲۰ حرف، فقط حروف و اعداد).\n"
    "۳. مبلغ را واریز و اسکرین‌شات رسید را بفرستید.\n"
    "۴. بعد از تأیید ادمین، لینک اشتراک برای شما ارسال می‌شود.\n\n"
    "لینک اشتراک را در برنامه‌ای مانند Hiddify ، Streisand یا v2rayNG وارد کنید و «به‌روزرسانی» بزنید."
)

MSG_SUPPORT = (
    "🆘 <b>پشتیبانی</b>\n\n"
    "برای پیگیری سفارش‌ها و سوالات، همین‌جا پیام بگذارید؛ "
    "در اولین فرصت پاسخ می‌دهیم."
)

MSG_ENTER_DISPLAY_NAME = (
    "📝 یک <b>نام نمایشی</b> برای کانفیگ خود بفرستید.\n\n"
    "قوانین: حداکثر ۲۰ حرف، فقط حروف انگلیسی/فارسی و اعداد.\n"
    "این نام در کنار یک پسوند تصادفی یکتا می‌نشیند "
    "(مثلاً <code>Parsa_A3F2K</code>) و باید در کل سیستم یکتا باشد."
)

MSG_NAME_INVALID = "❌ نام نامعتبر است. فقط حروف و اعداد، حداکثر ۲۰ حرف. دوباره بفرستید:"
MSG_NAME_TAKEN = "❌ این نام قبلاً استفاده شده است. لطفاً نام دیگری بفرستید:"

# Tier A/B honest pitch — stability & DNS, never UDP/ping claims (Document 2).
MSG_PLAN_DETAILS = (
    "📋 <b>{name}</b>\n"
    "{description}\n\n"
    "💰 قیمت: <b>{price}</b>\n"
    "⏳ مدت: <b>{duration}</b>\n"
    "📦 حجم: <b>{traffic}</b>\n"
    "📱 تعداد اتصال همزمان: <b>{devices}</b>\n\n"
    "این پلن روی زیرساخت Cloudflare اجرا می‌شود: اتصال پایدار، رفع تحریمِ "
    "DNS و عبور مطمئن از فیلترینگ. برای بازی‌های آنلاین، بهبود پایداری و "
    "جلوگیری از قطعی‌ها را ارائه می‌دهیم؛ وعدهٔ کاهش پینگ یا UDP نمی‌دهیم."
)

MSG_PAYMENT_INSTRUCTIONS = (
    "💳 <b>پرداخت</b>\n\n"
    "مبلغ: <b>{amount}</b>\n"
    "شماره کارت: <code>{card}</code>\n"
    "به نام: <b>{holder}</b>\n\n"
    "{instructions}\n\n"
    "پس از واریز، <b>اسکرین‌شات رسید</b> را همین‌جا بفرستید.\n"
    "شناسه سفارش شما: <code>{order_ref}</code>"
)

MSG_PROOF_RECEIVED = (
    "✅ رسید شما ثبت شد و در انتظار بررسی ادمین است.\n"
    "شناسه سفارش: <code>{order_ref}</code>\n"
    "نتیجه به‌زودی در همین چت اعلام می‌شود."
)

MSG_ORDER_APPROVED = (
    "🎉 پرداخت شما تأیید شد!\n\n"
    "کانفیگ <b>{display_name}</b> فعال شد.\n"
    "{link_block}"
)

MSG_ORDER_REJECTED = (
    "❌ پرداخت سفارش <code>{order_ref}</code> تأیید نشد.\n"
    "دلیل: {reason}\n\n"
    "در صورت اعتراض با پشتیبانی تماس بگیرید."
)

MSG_NO_CONFIGS = "هنوز اشتراکی ندارید. از «🛒 خرید اشتراک» شروع کنید!"

MSG_MY_CONFIGS_HEADER = "📂 <b>اشتراک‌های شما</b>\n"

MSG_CONFIG_ITEM = (
    "\n▫️ <b>{display_name}</b> — {status_fa}\n"
    "حجم مصرفی: {used} از {quota}\n"
    "انقضا: {expires}\n"
    "🔗 لینک: <code>{link}</code>"
)

MSG_TRIAL_OK = (
    "🎁 اشتراک آزمایشی شما فعال شد!\n\n"
    "نام: <b>{display_name}</b>\n"
    "حجم: {quota} (تست)\n"
    "اعتبار: ۲۴ ساعت\n\n"
    "{link_block}"
)

MSG_TRIAL_EXISTS = "شما یک اشتراک آزمایشی فعال دارید. هر مشتری فقط یک تست می‌تواند داشته باشد."

MSG_SUB_LINK = "🔗 لینک اشتراک شما:\n\n<code>{link}</code>\n\nاین لینک را در برنامه‌ی کلاینت وارد کنید."

# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

ADMIN_PREFIX = "/admin"

MSG_ADMIN_PANEL = (
    "🛠 <b>پنل مدیریت</b>\n\n"
    "دسترسی شما: <b>{role}</b>"
)

ADMIN_REVIEW_PAYMENT = (
    "🧾 <b>بررسی پرداخت</b>\n\n"
    "مشتری: {customer}\n"
    "شناسه تلگرام: <code>{tg_id}</code>\n"
    "پلن: {plan}\n"
    "مبلغ: {amount}\n"
    "نام درخواستی: <b>{display_name}</b>\n"
    "سفارش: <code>{order_ref}</code>"
)

MSG_ADMIN_NOTIFY_NEW_ORDER = "🔔 سفارش جدید در انتظار بررسی است."

MSG_ADMIN_FORBIDDEN = "⛔️ این عملیات برای نقش شما مجاز نیست."

MSG_ADMIN_REJECT_REASON = "دلیل رد را بنویسید (برای مشتری ارسال می‌شود):"

MSG_ADMIN_CONFIRM = "پرداخت تأیید شد و فرآیند فعال‌سازی آغاز شد."

MSG_ADMIN_REJECTED = "سفارش رد شد و به مشتری اطلاع داده شد."

# status → Persian
STATUS_FA = {
    "PENDING": "در انتظار پرداخت",
    "PROVISIONING": "در حال فعال‌سازی",
    "ACTIVE": "فعال ✅",
    "SUSPENDED": "معلق",
    "EXPIRED": "منقضی‌شده ⏰",
    "DELETED": "حذف‌شده",
    "CREATED": "ایجادشده",
    "AWAITING_PAYMENT": "در انتظار پرداخت",
    "PAID": "پرداخت‌شده",
    "FULFILLED": "تکمیل‌شده",
    "REJECTED": "ردشده",
    "CANCELLED": "لغوشده",
}

# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

MSG_EXPIRY_WARNING = (
    "⏰ اشتراک <b>{display_name}</b> تا {days} روز دیگر منقضی می‌شود.\n"
    "برای تمدید از «📂 اشتراک‌های من» اقدام کنید."
)

MSG_EXPIRED = (
    "⏰ اشتراک <b>{display_name}</b> منقضی شد.\n"
    "برای تمدید از «📂 اشتراک‌های من» اقدام کنید."
)

MSG_QUOTA_WARNING = (
    "⚠️ مصرف اشتراک <b>{display_name}</b> به {percent}٪ حجم رسیده است."
)

MSG_QUOTA_EXHAUSTED = (
    "📦 حجم اشتراک <b>{display_name}</b> تمام شد. برای شارژ مجدد تمدید کنید."
)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def format_traffic(quota_bytes: int | None) -> str:
    if quota_bytes is None:
        return "نامحدود"
    gb = quota_bytes / (1024 * 1024 * 1024)
    if gb >= 1:
        return f"{gb:.0f} گیگابایت"
    return f"{quota_bytes / (1024 * 1024):.0f} مگابایت"


def format_price(amount: int | float, currency: str) -> str:
    amount = int(amount)
    if currency == "XTR":
        return f"{amount:,} ⭐️"
    if currency in ("IRT", "Toman"):
        return f"{amount:,} تومان"
    return f"{amount:,} {currency} (ریال)"


def format_duration(days: int) -> str:
    if days >= 30 and days % 30 == 0:
        months = days // 30
        return f"{months} ماهه" if months > 1 else "یک‌ماهه"
    return f"{days} روزه"
