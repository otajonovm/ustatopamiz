import html

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.constants import BTN_CANCEL, BTN_HELP
from bot.keyboards.reply import main_menu_kb, phone_request_kb
from bot.services.user_service import get_or_create_user

router = Router(name="common")

HELP_TEXT = (
    "<b>Usta Topamiz</b> — Beshariq tumanidagi mijozlar va ustalarni bog'laydi.\n\n"
    "📝 Buyurtma — soha, hudud, muammo. Avval admin tekshiradi, keyin ustalarga chiqadi.\n"
    "👷 Usta — ariza, ish rasmlari, tasdiq va ish olish.\n\n"
    "Jarayonni bekor qilish: xabardagi ❌ tugma yoki /cancel"
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, session: AsyncSession, settings: Settings) -> None:
    await state.clear()
    user = await get_or_create_user(session, message.from_user, settings)
    name = html.escape(user.full_name)
    if not user.phone_number:
        await message.answer(
            f"Assalomu alaykum, {name}!\n\nDavom etish uchun telefon raqamingizni yuboring.",
            reply_markup=phone_request_kb(),
        )
        return
    await message.answer(
        f"Assalomu alaykum, {name}!\nKerakli bo'limni tanlang.",
        reply_markup=main_menu_kb(user),
    )


@router.message(F.contact)
async def save_contact(message: Message, session: AsyncSession, settings: Settings) -> None:
    contact = message.contact
    if contact.user_id and contact.user_id != message.from_user.id:
        await message.answer("Iltimos, o'zingizning telefon raqamingizni yuboring.")
        return
    user = await get_or_create_user(session, message.from_user, settings)
    user.phone_number = (contact.phone_number or "")[:20]
    await message.answer("Telefon raqam saqlandi.", reply_markup=main_menu_kb(user))


@router.message(Command("help"))
@router.message(F.text == BTN_HELP)
async def cmd_help(message: Message, state: FSMContext, session: AsyncSession, settings: Settings) -> None:
    await state.clear()
    user = await get_or_create_user(session, message.from_user, settings)
    await message.answer(HELP_TEXT, reply_markup=main_menu_kb(user))


@router.callback_query(F.data == "flow:cancel")
async def cancel_flow(callback: CallbackQuery, state: FSMContext, session: AsyncSession, settings: Settings) -> None:
    await state.clear()
    user = await get_or_create_user(session, callback.from_user, settings)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramAPIError:
        pass
    await callback.message.answer("Bekor qilindi.", reply_markup=main_menu_kb(user))
    await callback.answer()


@router.message(Command("cancel"))
@router.message(F.text == BTN_CANCEL)
async def cmd_cancel(message: Message, state: FSMContext, session: AsyncSession, settings: Settings) -> None:
    await state.clear()
    user = await get_or_create_user(session, message.from_user, settings)
    await message.answer("Bekor qilindi.", reply_markup=main_menu_kb(user))
