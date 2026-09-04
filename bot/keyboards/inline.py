from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.constants import REGIONS
from bot.database.models import Category


def categories_kb(categories: list[Category], prefix: str = "cat") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category in categories:
        builder.button(text=category.name, callback_data=f"{prefix}:{category.id}")
    builder.adjust(2)
    return builder.as_markup()


def regions_kb(prefix: str = "reg") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for region in REGIONS:
        builder.button(text=region, callback_data=f"{prefix}:{region}")
    builder.adjust(2)
    return builder.as_markup()


def master_review_kb(master_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Tasdiqlash", callback_data=f"master:ok:{master_id}")
    builder.button(text="❌ Rad etish", callback_data=f"master:no:{master_id}")
    builder.adjust(2)
    return builder.as_markup()


def order_contact_kb(telegram_id: int, username: str | None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if username:
        builder.button(text="📞 Bog'lanish", url=f"https://t.me/{username}")
    else:
        builder.button(text="📞 Bog'lanish", url=f"tg://user?id={telegram_id}")
    return builder.as_markup()
