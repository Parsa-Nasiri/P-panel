"""Verdent Platform — Telegram FSM states (aiogram 3)."""

from aiogram.fsm.state import State, StatesGroup


class Purchase(StatesGroup):
    waiting_display_name = State()
    waiting_payment_proof = State()


class AdminFlow(StatesGroup):
    waiting_reject_reason = State()
    waiting_admin_telegram_id = State()
    waiting_admin_role = State()


class Support(StatesGroup):
    waiting_user_message = State()
