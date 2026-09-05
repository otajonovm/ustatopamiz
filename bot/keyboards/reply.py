from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove

from bot.config import get_settings
from bot.constants import (
    BTN_BECOME_MASTER,
    BTN_HELP,
    BTN_NEW_ORDER,
    BTN_PAY,
    BTN_SHARE_PHONE,
)
from bot.database.models import User, UserRole


def main_menu_kb(user: User | None = None) -> ReplyKeyboardMarkup:
    if user and user.role == UserRole.MASTER:
        rows = [[KeyboardButton(text=BTN_NEW_ORDER)]]
        if get_settings().REQUIRE_SUBSCRIPTION:
            rows.append([KeyboardButton(text=BTN_PAY), KeyboardButton(text=BTN_HELP)])
        else:
            rows.append([KeyboardButton(text=BTN_HELP)])
        return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)
    rows = [
        [KeyboardButton(text=BTN_NEW_ORDER)],
        [KeyboardButton(text=BTN_BECOME_MASTER), KeyboardButton(text=BTN_HELP)],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def phone_request_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_SHARE_PHONE, request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def remove_kb() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()
