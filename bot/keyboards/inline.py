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
    builder.adjust(3)
    return builder.as_markup()


def master_review_kb(master_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Tasdiqlash", callback_data=f"master:ok:{master_id}")
    builder.button(text="❌ Rad etish", callback_data=f"master:no:{master_id}")
    builder.adjust(2)
    return builder.as_markup()


def moderation_kb(order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Kanalga chiqarish", callback_data=f"mod:ok:{order_id}")
    builder.button(text="❌ Spam/Rad etish", callback_data=f"mod:no:{order_id}")
    builder.adjust(1)
    return builder.as_markup()


def take_job_kb(order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🛠 Ishni olish", callback_data=f"take:{order_id}")
    return builder.as_markup()


def client_job_kb(order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Ish muvaffaqiyatli bajarildi", callback_data=f"done:{order_id}")
    builder.button(text="⚠️ Usta bog'lanmadi / Ish bekor", callback_data=f"reopen:{order_id}")
    builder.adjust(1)
    return builder.as_markup()


def rating_kb(order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for stars in range(1, 6):
        builder.button(text="⭐" * stars, callback_data=f"rate:{order_id}:{stars}")
    builder.adjust(5)
    return builder.as_markup()


def payment_review_kb(payment_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ To'lovni tasdiqlash", callback_data=f"pay:ok:{payment_id}")
    builder.button(text="❌ Chek xato", callback_data=f"pay:no:{payment_id}")
    builder.adjust(1)
    return builder.as_markup()
