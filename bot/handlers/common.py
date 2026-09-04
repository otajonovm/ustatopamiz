import html
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.constants import BTN_CANCEL, BTN_HELP
from bot.keyboards.reply import main_menu_kb, phone_request_kb
from bot.services.user_service import get_or_create_user

router = Router(name="common")

HELP_TEXT = (
    "<b>Usta Topamiz</b> — Beshariq tumanidagi mijozlar va ustalarni bog'laydi.\n\n"
    "📝 <b>Buyurtma berish</b> — soha, hudud va muammoni yuboring. "
    "Bot e'lonni tegishli ustalar guruhiga yo'naltiradi.\n\n"
    "👷 <b>Usta sifatida ishlash</b> — soha va hududingizni tanlang. "
    "Admin tasdiqlagach, yopiq guruhga bir martalik havola olasiz.\n\n"
    "Bekor qilish: /cancel"
)


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    await state.clear()
    user = await get_or_create_user(session, message.from_user, settings)
    name = html.escape(user.full_name)
    if not user.phone_number:
        await message.answer(
            f"Assalomu alaykum, {name}!\n\n"
            "Davom etish uchun telefon raqamingizni yuboring.",
            reply_markup=phone_request_kb(),
        )
        return
    await message.answer(
        f"Assalomu alaykum, {name}!\nKerakli bo'limni tanlang.",
        reply_markup=main_menu_kb(),
    )


@router.message(F.contact)
async def save_contact(
    message: Message,
    session: AsyncSession,
    settings: Settings,
) -> None:
    contact = message.contact
    if contact.user_id and contact.user_id != message.from_user.id:
        await message.answer("Iltimos, o'zingizning telefon raqamingizni yuboring.")
        return

    user = await get_or_create_user(session, message.from_user, settings)
    user.phone_number = (contact.phone_number or "")[:20]
    await message.answer(
        "Telefon raqam saqlandi. Endi xizmatdan foydalanishingiz mumkin.",
        reply_markup=main_menu_kb(),
    )


@router.message(Command("help"))
@router.message(F.text == BTN_HELP)
async def cmd_help(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(HELP_TEXT, reply_markup=main_menu_kb())


@router.message(Command("cancel"))
@router.message(F.text == BTN_CANCEL)
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    await state.clear()
    if current is None:
        await message.answer("Asosiy menyu.", reply_markup=main_menu_kb())
        return
    await message.answer("Amal bekor qilindi.", reply_markup=main_menu_kb())
