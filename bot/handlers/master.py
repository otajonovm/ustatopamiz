import html
import json
import logging
from decimal import Decimal

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.constants import (
    BTN_BECOME_MASTER,
    BTN_PAY,
    BTN_SKIP_EXPERIENCE,
    MAX_PORTFOLIO_PHOTOS,
    MIN_PORTFOLIO_PHOTOS,
    REGIONS,
)
from bot.database.models import Category, Master, MasterStatus, OrderStatus, PaymentStatus, SubscriptionPayment
from bot.keyboards.inline import (
    cancel_inline_kb,
    categories_kb,
    client_job_kb,
    experience_inline_kb,
    master_review_kb,
    payment_review_kb,
    portfolio_kb,
    regions_kb,
)
from bot.keyboards.reply import main_menu_kb, phone_request_kb
from bot.services.order_service import load_order, utcnow
from bot.services.telegram_helpers import (
    format_master_application,
    mark_group_order_taken,
    notify_admins,
    send_photos_to_admins,
)
from bot.services.user_service import get_approved_master, get_or_create_user, has_active_subscription
from bot.states.master_states import MasterRegistration, SubscriptionPaymentState

router = Router(name="master")
logger = logging.getLogger(__name__)


async def _require_phone(message: Message, session: AsyncSession, settings: Settings):
    user = await get_or_create_user(session, message.from_user, settings)
    if user.phone_number:
        return user
    await message.answer("Avval telefon raqamingizni yuboring.", reply_markup=phone_request_kb())
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
    existing = await session.scalar(select(Master).where(Master.user_id == user.id))
    if existing and existing.status == MasterStatus.PENDING:
        await message.answer("Arizangiz ko'rib chiqilmoqda.", reply_markup=main_menu_kb(user))
        return
    if existing and existing.status == MasterStatus.APPROVED:
        await message.answer("Siz allaqachon tasdiqlangan ustasiz.", reply_markup=main_menu_kb(user))
        return

    categories = list(await session.scalars(select(Category).where(Category.is_active.is_(True)).order_by(Category.id)))
    await state.set_state(MasterRegistration.category)
    await message.answer("Qaysi soha ustasisiz?", reply_markup=main_menu_kb(user))
    await message.answer("Sohani tanlang:", reply_markup=categories_kb(categories, "mcat"))


@router.callback_query(MasterRegistration.category, F.data.startswith("mcat:"))
async def master_choose_category(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    category = await session.get(Category, int(callback.data.split(":", 1)[1]))
    if category is None or not category.is_active:
        await callback.answer("Bu soha mavjud emas.", show_alert=True)
        return
    await state.update_data(category_id=category.id, category_name=category.name)
    await state.set_state(MasterRegistration.region)
    await callback.message.edit_text(
        f"Soha: <b>{html.escape(category.name)}</b>\nQaysi hududda ishlaysiz?",
        reply_markup=regions_kb("mreg"),
    )
    await callback.answer()


@router.callback_query(MasterRegistration.region, F.data.startswith("mreg:"))
async def master_choose_region(callback: CallbackQuery, state: FSMContext) -> None:
    region = callback.data.split(":", 1)[1]
    if region not in REGIONS:
        await callback.answer("Noto'g'ri hudud.", show_alert=True)
        return
    data = await state.get_data()
    await state.update_data(region=region)
    await state.set_state(MasterRegistration.experience)
    await callback.message.edit_text(
        f"Soha: <b>{html.escape(data.get('category_name', ''))}</b>\nHudud: <b>{html.escape(region)}</b>\n\n"
        "Tajribangiz necha yil? Son yozing yoki o'tkazib yuboring.",
        reply_markup=experience_inline_kb(),
    )
    await callback.answer()


@router.callback_query(MasterRegistration.experience, F.data == "mexp:skip")
async def master_skip_experience_cb(callback: CallbackQuery, state: FSMContext) -> None:
    await _ask_portfolio(callback.message, state, None, edit=True)
    await callback.answer()


@router.message(MasterRegistration.experience, F.text == BTN_SKIP_EXPERIENCE)
async def master_skip_experience(message: Message, state: FSMContext) -> None:
    await _ask_portfolio(message, state, None)


@router.message(MasterRegistration.experience, F.text)
async def master_set_experience(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.isdigit() or int(text) > 80:
        await message.answer("0 dan 80 gacha son yuboring yoki o'tkazib yuboring.")
        return
    await _ask_portfolio(message, state, int(text))


async def _ask_portfolio(message: Message, state: FSMContext, experience_years: int | None, *, edit: bool = False) -> None:
    await state.update_data(experience_years=experience_years, portfolio_ids=[])
    await state.set_state(MasterRegistration.portfolio)
    text = (
        f"Qilgan ishlaringizdan kamida <b>{MIN_PORTFOLIO_PHOTOS}</b> ta rasm yuboring "
        f"(maksimal {MAX_PORTFOLIO_PHOTOS} ta).\n\n"
        "Rasm bo'lmasa ariza qabul qilinmaydi."
    )
    if edit:
        try:
            await message.edit_text(text, reply_markup=portfolio_kb(0, MIN_PORTFOLIO_PHOTOS))
            return
        except TelegramAPIError:
            pass
    await message.answer(text, reply_markup=portfolio_kb(0, MIN_PORTFOLIO_PHOTOS))


@router.message(MasterRegistration.portfolio, F.photo)
async def master_add_portfolio_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    photos: list[str] = list(data.get("portfolio_ids") or [])
    if len(photos) >= MAX_PORTFOLIO_PHOTOS:
        await message.answer(
            f"Yetarli: {MAX_PORTFOLIO_PHOTOS} ta rasm. Endi «Yuborish» ni bosing.",
            reply_markup=portfolio_kb(len(photos), MIN_PORTFOLIO_PHOTOS),
        )
        return
    photos.append(message.photo[-1].file_id)
    await state.update_data(portfolio_ids=photos)
    remaining = MAX_PORTFOLIO_PHOTOS - len(photos)
    if len(photos) < MIN_PORTFOLIO_PHOTOS:
        need = MIN_PORTFOLIO_PHOTOS - len(photos)
        await message.answer(
            f"Qabul qilindi: {len(photos)} ta. Yana kamida {need} ta rasm yuboring.",
            reply_markup=portfolio_kb(len(photos), MIN_PORTFOLIO_PHOTOS),
        )
        return
    extra = f" Yana {remaining} ta qo'shishingiz mumkin." if remaining else ""
    await message.answer(
        f"{len(photos)} ta rasm saqlandi.{extra}\nArizani yuborish uchun tugmani bosing.",
        reply_markup=portfolio_kb(len(photos), MIN_PORTFOLIO_PHOTOS),
    )


@router.message(MasterRegistration.portfolio)
async def master_portfolio_not_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    count = len(data.get("portfolio_ids") or [])
    await message.answer(
        f"Faqat rasm yuboring. Kamida {MIN_PORTFOLIO_PHOTOS} ta ish rasmi kerak.",
        reply_markup=portfolio_kb(count, MIN_PORTFOLIO_PHOTOS),
    )


@router.callback_query(MasterRegistration.portfolio, F.data == "mport:done")
async def master_submit_portfolio(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    data = await state.get_data()
    photos: list[str] = list(data.get("portfolio_ids") or [])
    if len(photos) < MIN_PORTFOLIO_PHOTOS:
        await callback.answer(f"Kamida {MIN_PORTFOLIO_PHOTOS} ta rasm yuboring.", show_alert=True)
        return
    await callback.answer()
    await _submit_master(
        callback.message,
        state,
        session,
        settings,
        data.get("experience_years"),
        telegram_user=callback.from_user,
        portfolio_ids=photos,
    )


async def _submit_master(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
    experience_years: int | None,
    telegram_user=None,
    portfolio_ids: list[str] | None = None,
) -> None:
    from_user = telegram_user or message.from_user
    user = await get_or_create_user(session, from_user, settings)
    if not user.phone_number:
        await state.clear()
        await message.answer("Avval telefon raqamingizni yuboring.", reply_markup=phone_request_kb())
        return
    data = await state.get_data()
    category = await session.get(Category, data.get("category_id"))
    region = data.get("region")
    photos = list(portfolio_ids or data.get("portfolio_ids") or [])
    if category is None or not region:
        await state.clear()
        await message.answer("Sessiya eskirgan.", reply_markup=main_menu_kb(user))
        return
    if len(photos) < MIN_PORTFOLIO_PHOTOS:
        await message.answer(
            f"Kamida {MIN_PORTFOLIO_PHOTOS} ta ish rasmi yuboring.",
            reply_markup=portfolio_kb(len(photos), MIN_PORTFOLIO_PHOTOS),
        )
        return

    master = await session.scalar(select(Master).where(Master.user_id == user.id))
    if master is None:
        master = Master(
            user_id=user.id,
            category_id=category.id,
            region=region,
            experience_years=experience_years,
            status=MasterStatus.PENDING,
            portfolio_photo_ids=json.dumps(photos),
        )
        session.add(master)
        await session.flush()
    else:
        master.category_id = category.id
        master.region = region
        master.experience_years = experience_years
        master.status = MasterStatus.PENDING
        master.portfolio_photo_ids = json.dumps(photos)

    caption = format_master_application(master, user, category, photo_count=len(photos))
    await send_photos_to_admins(message.bot, settings, photos, "🖼 Usta ishlaridan namunalar")
    await notify_admins(
        message.bot,
        settings,
        caption,
        reply_markup=master_review_kb(master.id),
    )
    await state.clear()
    await message.answer(
        "Ariza va ish rasmlari adminga yuborildi. Tasdiqni kuting.",
        reply_markup=main_menu_kb(user),
    )


@router.message(F.text == BTN_PAY)
async def start_payment(message: Message, state: FSMContext, session: AsyncSession, settings: Settings) -> None:
    user = await _require_phone(message, session, settings)
    if user is None:
        return
    master = await session.scalar(select(Master).where(Master.user_id == user.id, Master.status == MasterStatus.APPROVED))
    if master is None:
        await message.answer("Avval usta sifatida ro'yxatdan o'ting va tasdiq kuting.")
        return
    if not settings.REQUIRE_SUBSCRIPTION:
        await message.answer("Hozircha obuna talab qilinmaydi. Ishni to'g'ridan-to'g'ri olishingiz mumkin.")
        return
    await state.set_state(SubscriptionPaymentState.receipt)
    await message.answer(
        f"💳 <b>Obuna: {settings.SUBSCRIPTION_AMOUNT:,} so'm / {settings.SUBSCRIPTION_DAYS} kun</b>\n\n"
        f"Karta: <code>{html.escape(settings.PAYMENT_CARD)}</code>\n\n"
        "To'lov qilib, chek rasmini yuboring.",
        reply_markup=main_menu_kb(user),
    )
    await message.answer("Chek rasmini yuboring.", reply_markup=cancel_inline_kb())


@router.message(SubscriptionPaymentState.receipt, F.photo)
async def receive_receipt(message: Message, state: FSMContext, session: AsyncSession, settings: Settings) -> None:
    user = await get_or_create_user(session, message.from_user, settings)
    master = await session.scalar(select(Master).where(Master.user_id == user.id))
    if master is None:
        await state.clear()
        await message.answer("Usta profili topilmadi.")
        return
    pending = await session.scalar(
        select(SubscriptionPayment.id).where(
            SubscriptionPayment.master_id == master.id,
            SubscriptionPayment.status == PaymentStatus.PENDING,
        )
    )
    if pending:
        await message.answer("Sizda tekshiruvdagi chek bor. Admin javobini kuting.")
        return

    payment = SubscriptionPayment(
        master_id=master.id,
        receipt_photo_id=message.photo[-1].file_id,
        amount=Decimal(settings.SUBSCRIPTION_AMOUNT),
        days_added=settings.SUBSCRIPTION_DAYS,
        status=PaymentStatus.PENDING,
    )
    session.add(payment)
    await session.flush()
    caption = (
        f"💳 <b>To'lov cheki #{payment.id}</b>\n"
        f"Usta: {html.escape(user.full_name)}\n"
        f"Summa: {settings.SUBSCRIPTION_AMOUNT:,} so'm"
    )
    for admin_id in settings.ADMIN_IDS:
        try:
            await message.bot.send_photo(
                admin_id,
                photo=payment.receipt_photo_id,
                caption=caption,
                reply_markup=payment_review_kb(payment.id),
            )
        except Exception:
            logger.warning("Admin ga chek yuborilmadi")
    await state.clear()
    await message.answer("Chek adminga yuborildi. Tasdiqni kuting.", reply_markup=main_menu_kb(user))


@router.message(SubscriptionPaymentState.receipt)
async def receipt_not_photo(message: Message) -> None:
    await message.answer("Iltimos, to'lov chekining rasmini yuboring.")


@router.callback_query(F.data.startswith("take:"))
async def take_job(callback: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    order = await load_order(session, int(callback.data.split(":", 1)[1]), for_update=True)
    if order is None:
        await callback.answer("Buyurtma topilmadi.", show_alert=True)
        return
    master = await get_approved_master(session, callback.from_user.id)
    if master is None:
        await callback.answer("Avval usta sifatida tasdiqlaning.", show_alert=True)
        return
    if master.category_id != order.category_id:
        await callback.answer("Bu soha sizning profilingizga mos emas.", show_alert=True)
        return
    if settings.REQUIRE_SUBSCRIPTION and not has_active_subscription(master):
        await callback.answer("Obunangiz muddati tugagan. Bot orqali yangilang.", show_alert=True)
        return
    if order.status != OrderStatus.APPROVED_OPEN:
        await callback.answer("Bu buyurtma allaqachon olingan.", show_alert=True)
        return

    order.status = OrderStatus.TAKEN
    order.master_id = master.id
    order.taken_at = utcnow()
    await session.flush()
    await mark_group_order_taken(callback.bot, order, master.user.full_name, order.category.group_id)

    client = order.client
    try:
        await callback.bot.send_message(
            master.user.telegram_id,
            (
                f"✅ Siz #{order.id} buyurtmani oldingiz.\n"
                f"📍 {html.escape(settings.DEFAULT_REGION)}, {html.escape(order.region)}\n"
                f"📝 {html.escape(order.description or '-')}\n"
                f"👤 Mijoz: {html.escape(client.full_name)}\n"
                f"📞 Telefon: <code>{html.escape(client.phone_number or '-')}</code>"
            ),
        )
    except TelegramAPIError:
        logger.warning("Ustaga mijoz ma'lumoti yuborilmadi")
    try:
        await callback.bot.send_message(
            client.telegram_id,
            (
                f"👷 Usta buyurtmangizni oldi.\n"
                f"👤 {html.escape(master.user.full_name)}\n"
                f"📞 <code>{html.escape(master.user.phone_number or '-')}</code>\n"
                f"⭐ Reyting: {master.rating}"
            ),
            reply_markup=client_job_kb(order.id),
        )
    except TelegramAPIError:
        logger.warning("Mijozga usta ma'lumoti yuborilmadi")
    await callback.answer("Ish sizda.")
