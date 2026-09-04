from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.constants import BTN_BECOME_MASTER, BTN_SKIP_EXPERIENCE, REGIONS
from bot.database.models import Category, Master, MasterStatus, User
from bot.keyboards.inline import categories_kb, master_review_kb, regions_kb
from bot.keyboards.reply import cancel_kb, experience_kb, main_menu_kb, phone_request_kb
from bot.services.telegram_service import format_master_application, notify_admins
from bot.services.user_service import get_or_create_user
from bot.states.master_states import MasterRegistration

router = Router(name="master")


async def _require_phone(message: Message, session: AsyncSession, settings: Settings):
    user = await get_or_create_user(session, message.from_user, settings)
    if user.phone_number:
        return user
    await message.answer(
        "Avval telefon raqamingizni yuboring.",
        reply_markup=phone_request_kb(),
    )
    return None


@router.message(F.text == BTN_BECOME_MASTER)
async def start_master_registration(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    user = await _require_phone(message, session, settings)
    if user is None:
        return

    await state.clear()
    categories = list(await session.scalars(select(Category).where(Category.is_active.is_(True)).order_by(Category.id)))
    if not categories:
        await message.answer("Hozircha sohalar mavjud emas.")
        return

    await state.set_state(MasterRegistration.category)
    await message.answer("Qaysi soha ustasisiz?", reply_markup=categories_kb(categories, "mcat"))
    await message.answer("Bekor qilish uchun tugmani bosing.", reply_markup=cancel_kb())


@router.callback_query(MasterRegistration.category, F.data.startswith("mcat:"))
async def master_choose_category(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    category_id = int(callback.data.split(":", maxsplit=1)[1])
    category = await session.get(Category, category_id)
    if category is None or not category.is_active:
        await callback.answer("Bu soha mavjud emas.", show_alert=True)
        return

    db_user = await session.scalar(select(User).where(User.telegram_id == callback.from_user.id))
    if db_user:
        existing = await session.scalar(
            select(Master).where(Master.user_id == db_user.id, Master.category_id == category.id)
        )
        if existing and existing.status == MasterStatus.PENDING:
            await callback.answer("Bu soha bo'yicha arizangiz ko'rib chiqilmoqda.", show_alert=True)
            await state.clear()
            await callback.message.edit_text("Arizangiz allaqachon yuborilgan. Admin javobini kuting.")
            await callback.message.answer("Asosiy menyu.", reply_markup=main_menu_kb())
            return
        if existing and existing.status == MasterStatus.APPROVED:
            await callback.answer()
            await state.clear()
            await callback.message.edit_text("Siz bu soha bo'yicha allaqachon tasdiqlangansiz.")
            await callback.message.answer("Asosiy menyu.", reply_markup=main_menu_kb())
            return

    await state.update_data(category_id=category.id, category_name=category.name)
    await state.set_state(MasterRegistration.region)
    await callback.message.edit_text(
        f"Soha: <b>{category.name}</b>\nQaysi hududda ishlaysiz?",
        reply_markup=regions_kb("mreg"),
    )
    await callback.answer()


@router.callback_query(MasterRegistration.region, F.data.startswith("mreg:"))
async def master_choose_region(callback: CallbackQuery, state: FSMContext) -> None:
    region = callback.data.split(":", maxsplit=1)[1]
    if region not in REGIONS:
        await callback.answer("Noto'g'ri hudud.", show_alert=True)
        return

    data = await state.get_data()
    await state.update_data(region=region)
    await state.set_state(MasterRegistration.experience)
    await callback.message.edit_text(
        f"Soha: <b>{data.get('category_name')}</b>\n"
        f"Hudud: <b>{region}</b>\n\n"
        "Tajribangiz necha yil? Raqam yuboring yoki o'tkazib yuboring."
    )
    await callback.message.answer("Tajribani kiriting:", reply_markup=experience_kb())
    await callback.answer()


@router.message(MasterRegistration.experience, F.text == BTN_SKIP_EXPERIENCE)
async def master_skip_experience(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    await _submit_master_application(message, state, session, settings, experience_years=None)


@router.message(MasterRegistration.experience, F.text)
async def master_set_experience(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    text = (message.text or "").strip()
    if not text.isdigit() or int(text) < 0 or int(text) > 80:
        await message.answer("Iltimos, 0 dan 80 gacha butun son yuboring yoki o'tkazib yuboring.")
        return
    await _submit_master_application(message, state, session, settings, experience_years=int(text))


async def _submit_master_application(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
    experience_years: int | None,
) -> None:
    user = await _require_phone(message, session, settings)
    if user is None:
        await state.clear()
        return

    data = await state.get_data()
    category_id = data.get("category_id")
    region = data.get("region")
    if not category_id or not region:
        await state.clear()
        await message.answer("Sessiya eskirgan. Qaytadan urinib ko'ring.", reply_markup=main_menu_kb())
        return

    category = await session.get(Category, category_id)
    if category is None:
        await state.clear()
        await message.answer("Soha topilmadi.", reply_markup=main_menu_kb())
        return

    master = await session.scalar(
        select(Master).where(Master.user_id == user.id, Master.category_id == category.id)
    )
    if master is None:
        master = Master(
            user_id=user.id,
            category_id=category.id,
            region=region,
            experience_years=experience_years,
            status=MasterStatus.PENDING,
        )
        session.add(master)
        await session.flush()
    else:
        master.region = region
        master.experience_years = experience_years
        master.status = MasterStatus.PENDING

    await notify_admins(
        message.bot,
        settings,
        format_master_application(master, user, category),
        reply_markup=master_review_kb(master.id),
    )
    await state.clear()
    await message.answer(
        "Arizangiz adminga yuborildi. Tasdiqlangach, soha guruhiga taklif havolasini olasiz.",
        reply_markup=main_menu_kb(),
    )
