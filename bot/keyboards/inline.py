from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.constants import EXPERIENCE_OPTIONS, QURILISH_SKILLS, VILLAGE_PAGE_SIZE
from bot.database.models import Category, Village


def cancel_inline_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Bekor qilish", callback_data="flow:cancel")
    return builder.as_markup()


def _cancel_row() -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="flow:cancel")]


def categories_kb(categories: list[Category], prefix: str = "cat", *, include_other: bool = True) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category in categories:
        builder.button(text=category.name, callback_data=f"{prefix}:{category.id}")
    builder.adjust(1)
    if include_other:
        builder.row(InlineKeyboardButton(text="✏️ Boshqa soha", callback_data=f"{prefix}:other"))
    builder.row(*_cancel_row())
    return builder.as_markup()


def villages_kb(villages: list[Village], page: int, kind: str) -> InlineKeyboardMarkup:
    total = max(1, (len(villages) + VILLAGE_PAGE_SIZE - 1) // VILLAGE_PAGE_SIZE)
    page = max(0, min(page, total - 1))
    start = page * VILLAGE_PAGE_SIZE
    chunk = villages[start : start + VILLAGE_PAGE_SIZE]
    builder = InlineKeyboardBuilder()
    for village in chunk:
        builder.button(text=village.name, callback_data=f"vid:{kind}:{village.id}")
    builder.adjust(2)
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"vpg:{kind}:{page - 1}"))
    if page < total - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"vpg:{kind}:{page + 1}"))
    if nav:
        builder.row(*nav)
    builder.row(InlineKeyboardButton(text="✏️ Boshqa hudud", callback_data=f"voth:{kind}"))
    builder.row(*_cancel_row())
    return builder.as_markup()


def skills_kb(selected: list[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for skill in QURILISH_SKILLS:
        mark = "✅ " if skill in selected else ""
        builder.button(text=f"{mark}{skill}", callback_data=f"skill:{skill}")
    builder.adjust(2)
    if selected:
        builder.row(InlineKeyboardButton(text="Davom etish ➡️", callback_data="skill:done"))
    builder.row(*_cancel_row())
    return builder.as_markup()


def experience_inline_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for option in EXPERIENCE_OPTIONS:
        builder.button(text=option, callback_data=f"mexp:{option}")
    builder.adjust(1)
    builder.row(*_cancel_row())
    return builder.as_markup()


def portfolio_kb(count: int, minimum: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if count >= minimum:
        builder.button(text=f"✅ Davom etish ({count} ta rasm)", callback_data="mport:done")
    builder.row(*_cancel_row())
    return builder.as_markup()


def confirm_master_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Hammasi to'g'ri", callback_data="mconf:ok")
    builder.button(text="🔄 Boshidan boshlash", callback_data="mconf:restart")
    builder.adjust(1)
    return builder.as_markup()


def master_review_kb(master_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Tasdiqlash", callback_data=f"master:ok:{master_id}")
    builder.button(text="❌ Rad etish", callback_data=f"master:no:{master_id}")
    builder.button(text="🔄 Sohani o'zgartirish", callback_data=f"master:recat:{master_id}")
    builder.adjust(2, 1)
    return builder.as_markup()


def recat_kb(master_id: int, categories: list[Category]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category in categories:
        builder.button(text=category.name, callback_data=f"master:setcat:{master_id}:{category.id}")
    builder.adjust(1)
    return builder.as_markup()


def suggestion_kb(suggestion_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Darhol menyuga qo'shish", callback_data=f"sug:ok:{suggestion_id}")
    builder.button(text="🗑 Spam/O'chirish", callback_data=f"sug:no:{suggestion_id}")
    builder.adjust(1)
    return builder.as_markup()


def moderation_kb(order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Guruhga chiqarish", callback_data=f"mod:ok:{order_id}")
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
