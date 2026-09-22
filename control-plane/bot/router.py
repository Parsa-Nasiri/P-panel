"""Verdent Platform — Telegram routers (customer + admin), Persian UX.

Customer flow (Document 4): start/menu → buy (plan → display name → payment
method → proof) → review → fulfilled (link delivered). Plus my-configs,
trial, support, help.

Admin flow: role-gated panel — payment review with inline approve/reject,
test config issuance, admin management, node status. Every action RBAC-
checked and audit-logged.
"""

import logging
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    PreCheckoutQuery,
)
from sqlalchemy import select

from bot import keyboards, states, texts
from bot.webhook import bot_enabled, dp as router_dp  # noqa: F401 (handlers register onto router_dp via decorators below)
from db.base import SessionLocal
from db.models import (
    Admin,
    Configuration,
    ConfigurationNodeAssignment,
    Node,
    Order,
    PaymentAttempt,
    Plan,
)
from domain import fulfillment, naming, rbac
from domain.config import settings
from domain.orders import (
    attach_payment_proof,
    create_order,
    get_or_create_customer,
    get_order_attempts,
    mark_order_provisioning,
    reject_payment,
)
from domain.subscriptions import subscription_url

logger = logging.getLogger("verdent.bot")

router = Router()

MENU_BACK_KB = keyboards.back_to_main()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _customer_from_message(message: Message):
    async with SessionLocal() as db:
        return await get_or_create_customer(
            db,
            telegram_user_id=message.from_user.id,
            username=message.from_user.username,
            display_name=message.from_user.full_name,
        )


def _plan_is_stars(plan: Plan) -> bool:
    return plan.price_currency == "XTR"


# ---------------------------------------------------------------------------
# customer: start / menu
# ---------------------------------------------------------------------------


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, command: CommandObject | None = None):
    await state.clear()
    customer = await _customer_from_message(message)
    await message.answer(
        texts.MSG_WELCOME.format(
            name=message.from_user.first_name or "",
            app=texts.APP_NAME,
        ),
        reply_markup=keyboards.main_menu(),
    )


@router.callback_query(F.data == "menu:main")
async def cb_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_reply_markup(reply_markup=keyboards.main_menu())
    await call.answer()


@router.callback_query(F.data == "menu:help")
async def cb_help(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.answer(texts.MSG_HELP, reply_markup=MENU_BACK_KB)
    await call.answer()


@router.callback_query(F.data == "menu:support")
async def cb_support(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.answer(texts.MSG_SUPPORT, reply_markup=MENU_BACK_KB)
    await call.answer()


# ---------------------------------------------------------------------------
# customer: buy flow
# ---------------------------------------------------------------------------


@router.callback_query(F.data == "menu:buy")
async def cb_buy(call: CallbackQuery, state: FSMContext):
    await state.clear()
    async with SessionLocal() as db:
        plans = (
            await db.execute(
                select(Plan)
                .where(Plan.is_active.is_(True))
                .order_by(Plan.price_amount.asc())
            )
        ).scalars().all()

    if not bot_enabled() and not plans:
        await call.message.answer("پلنی موجود نیست.", reply_markup=MENU_BACK_KB)
        return

    visible = [p for p in plans if not _plan_is_stars(p) or settings.stars_enabled]
    await call.message.answer(
        "🛒 <b>انتخاب پلن</b>", reply_markup=keyboards.plans_menu(visible)
    )
    await call.answer()


@router.callback_query(F.data.startswith("plan:"))
async def cb_plan(call: CallbackQuery, state: FSMContext, ):
    plan_id = call.data.split(":")[1]
    async with SessionLocal() as db:
        plan = (await db.execute(select(Plan).where(Plan.id == plan_id))).scalar_one_or_none()

    if plan is None:
        await call.answer("پلن یافت نشد", show_alert=True)
        return

    await call.message.answer(
        texts.MSG_PLAN_DETAILS.format(
            name=plan.name,
            description=plan.description or "",
            price=texts.format_price(plan.price_amount, plan.price_currency),
            duration=texts.format_duration(plan.duration_days),
            traffic=texts.format_traffic(plan.traffic_quota_bytes),
            devices=plan.device_limit,
        ),
        reply_markup=keyboards.payment_methods(
            plan.id, stars_available=_plan_is_stars(plan) and settings.stars_enabled
        ),
    )
    await call.answer()


@router.callback_query(F.data.startswith("pay:card:"))
async def cb_pay_card(call: CallbackQuery, state: FSMContext):
    _, _, plan_id = call.data.split(":")
    async with SessionLocal() as db:
        plan = (await db.execute(select(Plan).where(Plan.id == plan_id))).scalar_one_or_none()
        if plan is None:
            await call.answer("پلن یافت نشد", show_alert=True)
            return
        customer = await get_or_create_customer(
            db,
            telegram_user_id=call.from_user.id,
            username=call.from_user.username,
            display_name=call.from_user.full_name,
        )

    await state.update_data(plan_id=plan.id)
    await state.set_state(states.Purchase.waiting_display_name)
    await call.message.answer(texts.MSG_ENTER_DISPLAY_NAME)
    await call.answer()


@router.message(states.Purchase.waiting_display_name)
async def on_display_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if not naming.validate_display_name(name):
        await message.answer(texts.MSG_NAME_INVALID)
        return

    data = await state.get_data()
    plan_id = data["plan_id"]

    async with SessionLocal() as db:
        plan = (await db.execute(select(Plan).where(Plan.id == plan_id))).scalar_one_or_none()
        if plan is None:
            await message.answer("پلن یافت نشد — دوباره تلاش کنید.", reply_markup=MENU_BACK_KB)
            await state.clear()
            return

        customer = await get_or_create_customer(
            db,
            telegram_user_id=message.from_user.id,
            username=message.from_user.username,
            display_name=message.from_user.full_name,
        )

        order = await create_order(
            db,
            customer,
            plan,
            requested_display_name=name,
            idempotency_suffix=str(int(datetime.now(timezone.utc).timestamp() // 60)),
        )

    await state.update_data(order_id=order.id, plan_id=plan.id, display_name=name)
    await state.set_state(states.Purchase.waiting_payment_proof)

    await message.answer(
        texts.MSG_PAYMENT_INSTRUCTIONS.format(
            amount=texts.format_price(plan.price_amount, plan.price_currency),
            card=settings.payment_card_number or "<تنظیم نشده — ادمین را خبر کنید>",
            holder=settings.payment_card_holder or "—",
            instructions=settings.payment_instructions,
            order_ref=order.id[:8],
        ),
        reply_markup=keyboards.back_to_main(),
    )


@router.message(states.Purchase.waiting_payment_proof, F.photo)
async def on_payment_proof(message: Message, state: FSMContext):
    data = await state.get_data()
    order_id = data.get("order_id")
    if not order_id:
        await state.clear()
        return

    photo = message.photo[-1]

    async with SessionLocal() as db:
        order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
        if order is None:
            await message.answer("سفارش یافت نشد.")
            await state.clear()
            return

        attempt = await attach_payment_proof(
            db,
            order,
            telegram_file_id=photo.file_id,
            mime_type=None,
            size_bytes=photo.file_size,
        )

        await _notify_admins_new_order(db, order, attempt, message)

    await state.clear()
    await message.answer(texts.MSG_PROOF_RECEIVED.format(order_ref=order_id[:8]))


@router.message(states.Purchase.waiting_payment_proof)
async def on_payment_proof_not_photo(message: Message, state: FSMContext):
    await message.answer("لطفاً <b>عکس</b> رسید واریز را بفرستید.")


@router.callback_query(F.data.startswith("pay:stars:"))
async def cb_pay_stars(call: CallbackQuery, state: FSMContext):
    """Stars invoice (Phase 5): XTR needs no provider token; the plan's
    price_amount IS the star count when price_currency == 'XTR'."""
    if not settings.stars_enabled:
        await call.answer("پرداخت با استارز فعلاً غیرفعال است.", show_alert=True)
        return

    _, _, plan_id = call.data.split(":")
    async with SessionLocal() as db:
        plan = (await db.execute(select(Plan).where(Plan.id == plan_id))).scalar_one_or_none()
        if plan is None or plan.price_currency != "XTR":
            await call.answer("این پلن با استارز قابل خرید نیست.", show_alert=True)
            return

        customer = await get_or_create_customer(
            db,
            telegram_user_id=call.from_user.id,
            username=call.from_user.username,
            display_name=call.from_user.full_name,
        )

        order = await create_order(
            db,
            customer,
            plan,
            requested_display_name=f"stars-{call.from_user.id}",
            idempotency_suffix=str(int(datetime.now(timezone.utc).timestamp() // 60)),
        )

    from bot.webhook import bot as current_bot

    if current_bot is None:
        await call.answer("پرداخت در دسترس نیست.", show_alert=True)
        return

    await current_bot.send_invoice(
        chat_id=call.from_user.id,
        title=plan.name,
        description=(plan.description or plan.name)[:255],
        payload=f"stars:{order.id}",
        currency="XTR",
        prices=[{"label": plan.name, "amount": int(plan.price_amount)}],
    )
    await call.answer()


# ---------------------------------------------------------------------------
# customer: my configs / link / trial
# ---------------------------------------------------------------------------


@router.callback_query(F.data == "menu:configs")
async def cb_my_configs(call: CallbackQuery, state: FSMContext):
    await state.clear()
    async with SessionLocal() as db:
        customer = await get_or_create_customer(
            db,
            telegram_user_id=call.from_user.id,
            username=call.from_user.username,
            display_name=call.from_user.full_name,
        )

        configs = (
            await db.execute(
                select(Configuration)
                .where(
                    Configuration.customer_id == customer.id,
                    Configuration.status != "DELETED",
                )
                .order_by(Configuration.created_at.desc())
            )
        ).scalars().all()

        if not configs:
            await call.message.answer(texts.MSG_NO_CONFIGS, reply_markup=MENU_BACK_KB)
            await call.answer()
            return

        from domain.subscriptions import usage_current_period

        chunks = [texts.MSG_MY_CONFIGS_HEADER]
        for config in configs:
            used, quota = await usage_current_period(db, config)
            link = subscription_url(config)
            chunks.append(
                texts.MSG_CONFIG_ITEM.format(
                    display_name=config.display_name,
                    status_fa=texts.STATUS_FA.get(config.status, config.status),
                    used=texts.format_traffic(used),
                    quota=texts.format_traffic(quota),
                    expires=config.expires_at.strftime("%Y-%m-%d") if config.expires_at else "—",
                    link=link,
                )
            )

        await call.message.answer("\n".join(chunks), reply_markup=MENU_BACK_KB, disable_web_page_preview=True)
    await call.answer()


@router.callback_query(F.data == "menu:trial")
async def cb_trial(call: CallbackQuery, state: FSMContext):
    await state.clear()
    from domain import test_configs
    from domain.pools import select_node_for_pool

    async with SessionLocal() as db:
        customer = await get_or_create_customer(
            db,
            telegram_user_id=call.from_user.id,
            username=call.from_user.username,
            display_name=call.from_user.full_name,
        )

        if await test_configs.has_active_test_config(db, customer.id):
            await call.message.answer(texts.MSG_TRIAL_EXISTS)
            await call.answer()
            return

        pool = (
            await db.execute(
                select(__import__("db.models", fromlist=["Pool"]).Pool).limit(1)
            )
        ).scalar_one_or_none()
        node = await select_node_for_pool(db, pool) if pool else None

        if node is None:
            await call.message.answer(
                "فعلاً ظرفیت تست در دسترس نیست — بعداً دوباره تلاش کنید.",
                reply_markup=MENU_BACK_KB,
            )
            await call.answer()
            return

        config = await test_configs.create_test_config(
            db,
            customer_id=customer.id,
            display_name=f"test-{call.from_user.username or call.from_user.id}",
            node=node,
        )

        await call.message.answer(
            texts.MSG_TRIAL_OK.format(
                display_name=config.display_name,
                quota=texts.format_traffic(config.test_quota_bytes),
                link_block=texts.MSG_SUB_LINK.format(link=subscription_url(config)),
            ),
            disable_web_page_preview=True,
        )
    await call.answer()


@router.callback_query(F.data.startswith("cfg:link:"))
async def cb_config_link(call: CallbackQuery, state: FSMContext):
    config_id = call.data.split(":")[2]
    async with SessionLocal() as db:
        config = (
            await db.execute(select(Configuration).where(Configuration.id == config_id))
        ).scalar_one_or_none()
    if config is None:
        await call.answer("یافت نشد", show_alert=True)
        return
    await call.message.answer(texts.MSG_SUB_LINK.format(link=subscription_url(config)))
    await call.answer()


# ---------------------------------------------------------------------------
# admin: panel + payment review
# ---------------------------------------------------------------------------


async def _get_admin_role(telegram_user_id: int) -> str | None:
    async with SessionLocal() as db:
        admins = (await db.execute(select(Admin))).scalars().all()
        return rbac.admin_role_for_telegram_id(telegram_user_id, admins)


def _is_admin_role(role: str | None) -> bool:
    return role is not None


@router.message(F.text.startswith(texts.ADMIN_PREFIX))
async def admin_panel_entry(message: Message, state: FSMContext):
    role = await _get_admin_role(message.from_user.id)
    if not _is_admin_role(role):
        return  # silent for non-admins
    await state.clear()
    await message.answer(
        texts.MSG_ADMIN_PANEL.format(role=role),
        reply_markup=keyboards.admin_panel(rbac.permissions_for(role)),
    )


@router.callback_query(F.data.startswith("adm:"))
async def cb_admin_panel(call: CallbackQuery, state: FSMContext):
    role = await _get_admin_role(call.from_user.id)
    perms = rbac.permissions_for(role) if role else set()

    action = call.data.split(":")[1]

    if action == "pending" and rbac.PERM_PAYMENT_REVIEW in perms:
        await _show_pending_orders(call)
    elif action == "stats" and rbac.PERM_STATS_VIEW in perms:
        await _show_stats(call)
    elif action == "addadmin" and rbac.PERM_ADMIN_MANAGE in perms:
        await state.set_state(states.AdminFlow.waiting_admin_telegram_id)
        await call.message.answer("شناسه عددی تلگرام ادمین جدید را بفرستید:")
    elif action == "test" and rbac.PERM_TEST_CONFIG in perms:
        await state.set_state(states.AdminFlow.waiting_reject_reason)
        await state.update_data(admin_action="test_config")
        await call.message.answer("شناسه عددی تلگرام مشتری را بفرستید:")
    elif action == "nodes" and rbac.PERM_NODE_MANAGE in perms:
        await _show_nodes(call)
    else:
        await call.answer(texts.MSG_ADMIN_FORBIDDEN, show_alert=True)
        return
    await call.answer()


async def _show_pending_orders(call: CallbackQuery):
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                select(PaymentAttempt, Order, Plan)
                .join(Order, Order.id == PaymentAttempt.order_id)
                .join(Plan, Plan.id == Order.plan_id)
                .where(
                    PaymentAttempt.status == "WAITING_REVIEW",
                    Order.status == "PAID",
                )
                .order_by(PaymentAttempt.created_at.desc())
                .limit(10)
            )
        ).all()

        if not rows:
            await call.message.answer("سفارش در انتظار بررسی وجود ندارد.")
            return

        for attempt, order, plan in rows:
            customer = (
                await db.execute(
                    select(__import__("db.models", fromlist=["Customer"]).Customer).where(
                        __import__("db.models", fromlist=["Customer"]).Customer.id == order.customer_id
                    )
                )
            ).scalar_one_or_none()

            await call.message.answer(
                texts.ADMIN_REVIEW_PAYMENT.format(
                    customer=customer.display_name if customer else "—",
                    tg_id=customer.telegram_user_id if customer else "—",
                    plan=f"{plan.name} ({texts.format_price(plan.price_amount, plan.price_currency)})",
                    amount=texts.format_price(attempt.amount or plan.price_amount, attempt.currency),
                    display_name=order.requested_display_name,
                    order_ref=order.id[:8],
                ),
                reply_markup=keyboards.review_buttons(order.id, attempt.id),
            )


async def _show_stats(call: CallbackQuery):
    from sqlalchemy import func

    async with SessionLocal() as db:
        n_configs = (
            await db.execute(select(func.count()).select_from(Configuration).where(Configuration.status == "ACTIVE"))
        ).scalar_one()
        n_pending = (
            await db.execute(
                select(func.count()).select_from(PaymentAttempt).where(PaymentAttempt.status == "WAITING_REVIEW")
            )
        ).scalar_one()
        n_nodes = (
            await db.execute(
                select(func.count()).select_from(Node).where(Node.state == "ONLINE")
            )
        ).scalar_one()

    await call.message.answer(
        f"📊 <b>وضعیت سیستم</b>\n\n"
        f"کانفیگ‌های فعال: {n_configs}\n"
        f"پرداخت‌های در انتظار: {n_pending}\n"
        f"نودهای آنلاین: {n_nodes}"
    )


async def _show_nodes(call: CallbackQuery):
    async with SessionLocal() as db:
        nodes = (await db.execute(select(Node))).scalars().all()

    if not nodes:
        await call.message.answer("هنوز نودی ثبت نشده. ابتدا زیرساخت اضافه کنید.")
        return

    lines = ["🖥 <b>نودها</b>\n"]
    for n in nodes:
        lines.append(
            f"▫️ <code>{(n.worker_script_name or n.id)[:24]}</code> — {n.state} "
            f"(سلامت: {n.health_score or 0}، ظرفیت: {n.current_assignment_count}/{n.max_assignment_count})"
        )
    await call.message.answer("\n".join(lines))


# ---------------------------------------------------------------------------
# admin: review actions
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith("rev:ok:"))
async def cb_review_approve(call: CallbackQuery, state: FSMContext):
    _, _, order_id, attempt_id = call.data.split(":")
    role = await _get_admin_role(call.from_user.id)

    if not role or rbac.PERM_PAYMENT_REVIEW not in rbac.permissions_for(role):
        await call.answer(texts.MSG_ADMIN_FORBIDDEN, show_alert=True)
        return

    async with SessionLocal() as db:
        order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
        attempt = (
            await db.execute(select(PaymentAttempt).where(PaymentAttempt.id == attempt_id))
        ).scalar_one_or_none()

        if order is None or attempt is None or attempt.status != "WAITING_REVIEW":
            await call.answer("این سفارش قبلاً بررسی شده است.", show_alert=True)
            return

        admin = (
            await db.execute(select(Admin).where(Admin.telegram_user_id == str(call.from_user.id)))
        ).scalar_one_or_none()
        admin_id = admin.id if admin else None

        await mark_order_provisioning(db, order, attempt, admin_id)

        try:
            config = await fulfillment.fulfill_order(db, order, attempt, admin_id)
        except fulfillment.FulfillmentError as exc:
            logger.error("fulfillment failed for order %s: %s", order.id, exc)
            await call.message.answer(
                f"⚠️ تأیید شد اما فعال‌سازی ناموفق بود:\n<code>{exc}</code>\n"
                "سفارش در حالت PROVISIONING ماند — بعد از رفع مشکل، دوباره تأیید کنید."
            )
            await call.answer()
            return

        customer = (
            await db.execute(
                select(__import__("db.models", fromlist=["Customer"]).Customer).where(
                    __import__("db.models", fromlist=["Customer"]).Customer.id == order.customer_id
                )
            )
        ).scalar_one_or_none()

        if customer is not None:
            from bot.webhook import send_message

            await send_message(
                customer.telegram_user_id,
                texts.MSG_ORDER_APPROVED.format(
                    display_name=config.display_name,
                    link_block=texts.MSG_SUB_LINK.format(link=subscription_url(config)),
                ),
            )

    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer(texts.MSG_ADMIN_CONFIRM)
    await call.answer()


@router.callback_query(F.data.startswith("rev:no:"))
async def cb_review_reject(call: CallbackQuery, state: FSMContext):
    _, _, order_id, attempt_id = call.data.split(":")
    role = await _get_admin_role(call.from_user.id)

    if not role or rbac.PERM_PAYMENT_REVIEW not in rbac.permissions_for(role):
        await call.answer(texts.MSG_ADMIN_FORBIDDEN, show_alert=True)
        return

    await state.set_state(states.AdminFlow.waiting_reject_reason)
    await state.update_data(reject_order_id=order_id, reject_attempt_id=attempt_id)
    await call.message.answer(texts.MSG_ADMIN_REJECT_REASON)
    await call.answer()


@router.message(states.AdminFlow.waiting_reject_reason)
async def on_reject_reason(message: Message, state: FSMContext):
    data = await state.get_data()

    if data.get("admin_action") == "test_config":
        # reuse of the state for admin-entered customer telegram id
        await state.clear()
        await _admin_create_test(message, (message.text or "").strip())
        return

    order_id = data.get("reject_order_id")
    attempt_id = data.get("reject_attempt_id")
    reason = (message.text or "—").strip()
    await state.clear()

    role = await _get_admin_role(message.from_user.id)
    if not role or rbac.PERM_PAYMENT_REVIEW not in rbac.permissions_for(role):
        return

    async with SessionLocal() as db:
        attempt = (
            await db.execute(select(PaymentAttempt).where(PaymentAttempt.id == attempt_id))
        ).scalar_one_or_none()
        if attempt is None or attempt.status != "WAITING_REVIEW":
            await message.answer("این سفارش قبلاً بررسی شده است.")
            return

        order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
        admin = (
            await db.execute(select(Admin).where(Admin.telegram_user_id == str(message.from_user.id)))
        ).scalar_one_or_none()

        customer = (
            await db.execute(
                select(__import__("db.models", fromlist=["Customer"]).Customer).where(
                    __import__("db.models", fromlist=["Customer"]).Customer.id == order.customer_id
                )
            )
        ).scalar_one_or_none()

        await reject_payment(db, attempt, admin.id if admin else None, reason)

        if customer is not None:
            from bot.webhook import send_message

            await send_message(
                customer.telegram_user_id,
                texts.MSG_ORDER_REJECTED.format(order_ref=order.id[:8], reason=reason),
            )

    await message.answer(texts.MSG_ADMIN_REJECTED)


async def _admin_create_test(message: Message, telegram_id: str):
    from domain import test_configs
    from domain.pools import select_node_for_pool

    if not telegram_id.isdigit():
        await message.answer("شناسه عددی نامعتبر است.")
        return

    async with SessionLocal() as db:
        customer = await get_or_create_customer(
            db,
            telegram_user_id=int(telegram_id),
            username=None,
            display_name=None,
        )
        pool = (
            await db.execute(select(__import__("db.models", fromlist=["Pool"]).Pool).limit(1))
        ).scalar_one_or_none()
        node = await select_node_for_pool(db, pool) if pool else None

        if node is None:
            await message.answer("نودی در دسترس نیست.")
            return

        try:
            config = await test_configs.create_test_config(
                db,
                customer_id=customer.id,
                display_name=f"test-{telegram_id}",
                node=node,
                actor_id=str(message.from_user.id),
            )
        except RuntimeError:
            await message.answer("این مشتری یک تست فعال دارد.")
            return

        await message.answer(
            f"🧪 کانفیگ تستی ساخته شد: <b>{config.display_name}</b>\n"
            + texts.MSG_SUB_LINK.format(link=subscription_url(config))
        )


# ---------------------------------------------------------------------------
# admin: add admin
# ---------------------------------------------------------------------------


@router.message(states.AdminFlow.waiting_admin_telegram_id)
async def on_admin_telegram_id(message: Message, state: FSMContext):
    tg_id = (message.text or "").strip()
    role = await _get_admin_role(message.from_user.id)

    if not role or rbac.PERM_ADMIN_MANAGE not in rbac.permissions_for(role):
        await state.clear()
        return

    if not tg_id.isdigit():
        await message.answer("شناسه عددی نامعتبر است. دوباره بفرستید:")
        return

    await state.update_data(new_admin_tg=tg_id)
    await state.set_state(states.AdminFlow.waiting_admin_role)

    roles_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=r, callback_data=f"admrole:{r}")] for r in rbac.ALL_ROLES
        ]
    )
    await message.answer("نقش ادمین جدید را انتخاب کنید:", reply_markup=roles_kb)


@router.callback_query(F.data.startswith("admrole:"))
async def on_admin_role(call: CallbackQuery, state: FSMContext):
    role = await _get_admin_role(call.from_user.id)
    if not role or rbac.PERM_ADMIN_MANAGE not in rbac.permissions_for(role):
        await call.answer(texts.MSG_ADMIN_FORBIDDEN, show_alert=True)
        return

    new_role = call.data.split(":")[1]
    data = await state.get_data()
    tg_id = data.get("new_admin_tg")
    await state.clear()

    if not tg_id:
        await call.answer("شناسه یافت نشد — دوباره شروع کنید.", show_alert=True)
        return

    async with SessionLocal() as db:
        exists = (
            await db.execute(select(Admin).where(Admin.telegram_user_id == tg_id))
        ).scalar_one_or_none()
        if exists is not None:
            await call.message.answer("این کاربر قبلاً ادمین شده است.")
            await call.answer()
            return

        admin = (
            await db.execute(select(Admin).where(Admin.telegram_user_id == str(call.from_user.id)))
        ).scalar_one_or_none()

        db.add(Admin(telegram_user_id=tg_id, role=new_role, created_by=admin.id if admin else None))
        await db.commit()

        from domain.audit import audit

        await audit(
            db,
            "admin.create",
            actor_id=admin.id if admin else None,
            target_type="admin",
            target_id=tg_id,
            details={"role": new_role},
        )

    await call.message.answer(f"✅ ادمین جدید ثبت شد: <code>{tg_id}</code> با نقش {new_role}")
    await call.answer()


# ---------------------------------------------------------------------------
# Stars payments (Phase 5)
# ---------------------------------------------------------------------------


@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message, state: FSMContext):
    payment = message.successful_payment
    payload = payment.invoice_payload  # format: stars:{order_id}

    if not payload.startswith("stars:"):
        return

    order_id = payload.split(":", 1)[1]

    async with SessionLocal() as db:
        order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
        if order is None:
            await message.answer("سفارش یافت نشد.")
            return

        customer = await get_or_create_customer(
            db,
            telegram_user_id=message.from_user.id,
            username=message.from_user.username,
            display_name=message.from_user.full_name,
        )

        attempt = await attach_payment_proof(
            db,
            order,
            telegram_file_id=f"stars:{payment.telegram_payment_charge_id}",
            mime_type=None,
            size_bytes=None,
        )
        attempt.external_reference = payment.telegram_payment_charge_id
        await db.commit()

        plan = (await db.execute(select(Plan).where(Plan.id == order.plan_id))).scalar_one_or_none()
        if plan is None:
            return

        admin = (
            await db.execute(select(Admin).where(Admin.role == "OWNER").limit(1))
        ).scalar_one_or_none()

        await mark_order_provisioning(db, order, attempt, admin.id if admin else None)

        try:
            config = await fulfillment.fulfill_order(db, order, attempt, admin.id if admin else None)
            await message.answer(
                texts.MSG_ORDER_APPROVED.format(
                    display_name=config.display_name,
                    link_block=texts.MSG_SUB_LINK.format(link=subscription_url(config)),
                )
            )
        except fulfillment.FulfillmentError as exc:
            logger.error("stars fulfillment failed: %s", exc)
            await message.answer(
                "پرداخت ثبت شد اما فعال‌سازی موقتاً ناموفق بود — به‌زودی دستی فعال می‌کنیم."
            )


# ---------------------------------------------------------------------------
# admin notification helper
# ---------------------------------------------------------------------------


async def _notify_admins_new_order(db, order: Order, attempt: PaymentAttempt, customer_message: Message):
    from bot.webhook import send_message

    plan = (await db.execute(select(Plan).where(Plan.id == order.plan_id))).scalar_one_or_none()
    admins = (await db.execute(select(Admin))).scalars().all()

    for admin in admins:
        if not rbac.PERM_PAYMENT_REVIEW in rbac.permissions_for(admin.role):
            continue

        await send_message(
            admin.telegram_user_id,
            texts.MSG_ADMIN_NOTIFY_NEW_ORDER
            + "\n\n"
            + texts.ADMIN_REVIEW_PAYMENT.format(
                customer=customer_message.from_user.full_name,
                tg_id=customer_message.from_user.id,
                plan=plan.name if plan else "—",
                amount=texts.format_price(plan.price_amount, plan.price_currency) if plan else "—",
                display_name=order.requested_display_name,
                order_ref=order.id[:8],
            ),
        )


# include into the webhook dispatcher (module-level, AFTER all handlers register)
from bot.webhook import dp as _dp  # noqa: E402

_dp.include_router(router)
