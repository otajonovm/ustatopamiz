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
from sqlalchemy.orm import selectinload

from bot.config import Settings
from bot.constants import (
    BTN_BECOME_MASTER,
    BTN_PAY,
    EXPERIENCE_OPTIONS,
    MAX_PORTFOLIO_PHOTOS,
    MIN_PORTFOLIO_PHOTOS,
    QURILISH_SKILLS,
    QURILISH_SLUG,
)
from bot.database.models import Category, Master, MasterStatus, OrderStatus, PaymentStatus, SubscriptionPayment, Village
from bot.keyboards.inline import (
    cancel_inline_kb,
    categories_kb,
    client_job_kb,
    confirm_master_kb,
    experience_inline_kb,
    master_review_kb,
    payment_review_kb,
    portfolio_kb,
    skills_kb,
    villages_kb,
)
from bot.keyboards.reply import main_menu_kb, phone_request_kb
from bot.services.order_service import load_order, utcnow
from bot.services.suggestion_service import get_or_create_custom_category, record_suggestion
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


async def _active_villages(session: AsyncSession) -> list[Village]:
    return list(await session.scalars(select(Village).where(Village.is_active.is_(True)).order_by(Village.order_index, Village.id)))


async def _active_categories(session: AsyncSession) -> list[Category]:
    return list(await session.scalars(select(Category).where(Category.is_active.is_(True)).order_by(Category.id)))


def _summary_text(data: dict) -> str:
    photos = data.get("portfolio_ids") or []
    return (
        "<b>Arizani tekshiring:</b>\n\n"
        f"🔧 Soha: <b>{html.escape(data.get('category_name', '-'))}</b>\n"
        f"🧩 Mutaxassislik: {html.escape(data.get('sub_skills') or '-')}\n"
        f"📍 Hudud: <b>{html.escape(data.get('region', '-'))}</b>\n"
        f"🛠 Tajriba: {html.escape(str(data.get('experience_years') or '-'))}\n"
        f"🖼 Ish rasmlari: {len(photos)} ta"
    )


async def _goto_village(message: Message, state: FSMContext, session: AsyncSession, *, edit: bool = False) -> None:
    data = await state.get_data()
    villages = await _active_villages(session)
    await state.set_state(MasterRegistration.village)
    text = f"Soha: <b>{html.escape(data.get('category_name', ''))}</b>\nQaysi hududda ishlaysiz?"
    markup = villages_kb(villages, 0, "m")
    if edit:
        try:
            await message.edit_text(text, reply_markup=markup)
            return
        except TelegramAPIError:
            pass
    await message.answer(text, reply_markup=markup)


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

    categories = await _active_categories(session)
    await state.clear()
    await state.set_state(MasterRegistration.category)
    await message.answer("Qaysi soha ustasisiz?", reply_markup=main_menu_kb(user))
    await message.answer("Sohani tanlang:", reply_markup=categories_kb(categories, "mcat"))


@router.callback_query(MasterRegistration.category, F.data == "mcat:other")
async def master_other_category(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(MasterRegistration.custom_category)
    await callback.message.edit_text("Sohangizni yozing:", reply_markup=cancel_inline_kb())
    await callback.answer()


@router.message(MasterRegistration.custom_category, F.text)
async def master_save_custom_category(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    text = (message.text or "").strip()
    if len(text) < 3:
        await message.answer("Kamida 3 ta harf yozing.")
        return
    try:
        await record_suggestion(session, message.bot, settings, suggestion_type="category", raw_text=text)
        category = await get_or_create_custom_category(session, text)
    except ValueError:
        await message.answer("Noto'g'ri nom.")
        return
    await state.update_data(category_id=category.id, category_name=category.name, category_slug=category.slug, sub_skills=None)
    await _goto_village(message, state, session)


@router.callback_query(MasterRegistration.category, F.data.startswith("mcat:"))
async def master_choose_category(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    category = await session.get(Category, int(callback.data.split(":", 1)[1]))
    if category is None or not category.is_active:
        await callback.answer("Bu soha mavjud emas.", show_alert=True)
        return
    await state.update_data(
        category_id=category.id,
        category_name=category.name,
        category_slug=category.slug,
        sub_skills=None,
        selected_skills=[],
    )
    if category.slug == QURILISH_SLUG:
        await state.set_state(MasterRegistration.skills)
        await callback.message.edit_text(
            "Qurilish bo'yicha mutaxassislikni tanlang (bir nechtasini belgilash mumkin):",
            reply_markup=skills_kb([]),
        )
        await callback.answer()
        return
    await _goto_village(callback.message, state, session, edit=True)
    await callback.answer()


@router.callback_query(MasterRegistration.skills, F.data == "skill:done")
async def master_skills_done(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    selected = list(data.get("selected_skills") or [])
    if not selected:
        await callback.answer("Kamida bitta mutaxassislik tanlang.", show_alert=True)
        return
    await state.update_data(sub_skills=", ".join(selected))
    await _goto_village(callback.message, state, session, edit=True)
    await callback.answer()


@router.callback_query(MasterRegistration.skills, F.data.startswith("skill:"))
async def master_toggle_skill(callback: CallbackQuery, state: FSMContext) -> None:
    skill = callback.data.split(":", 1)[1]
    if skill not in QURILISH_SKILLS:
        await callback.answer()
        return
    data = await state.get_data()
    selected = list(data.get("selected_skills") or [])
    if skill == "Hammasi":
        selected = list(QURILISH_SKILLS)
    elif skill in selected:
        selected.remove(skill)
        if "Hammasi" in selected:
            selected.remove("Hammasi")
    else:
        selected.append(skill)
    await state.update_data(selected_skills=selected)
    await callback.message.edit_reply_markup(reply_markup=skills_kb(selected))
    await callback.answer()


@router.callback_query(MasterRegistration.village, F.data.startswith("vpg:m:"))
async def master_village_page(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    villages = await _active_villages(session)
    page = int(callback.data.rsplit(":", 1)[1])
    await callback.message.edit_text(
        f"Soha: <b>{html.escape(data.get('category_name', ''))}</b>\nQaysi hududda ishlaysiz?",
        reply_markup=villages_kb(villages, page, "m"),
    )
    await callback.answer()


@router.callback_query(MasterRegistration.village, F.data.startswith("vid:m:"))
async def master_choose_village(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    village = await session.get(Village, int(callback.data.rsplit(":", 1)[1]))
    if village is None or not village.is_active:
        await callback.answer("Hudud topilmadi.", show_alert=True)
        return
    await state.update_data(village_id=village.id, custom_village=None, region=village.name)
    await state.set_state(MasterRegistration.experience)
    await callback.message.edit_text("Tajribangiz qancha?", reply_markup=experience_inline_kb())
    await callback.answer()


@router.callback_query(MasterRegistration.village, F.data == "voth:m")
async def master_other_village(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(MasterRegistration.custom_village)
    await callback.message.edit_text("Hududingizni yozing:", reply_markup=cancel_inline_kb())
    await callback.answer()


@router.message(MasterRegistration.custom_village, F.text)
async def master_save_custom_village(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    text = (message.text or "").strip()
    if len(text) < 3:
        await message.answer("Kamida 3 ta harf yozing.")
        return
    try:
        await record_suggestion(session, message.bot, settings, suggestion_type="village", raw_text=text)
    except ValueError:
        await message.answer("Noto'g'ri nom.")
        return
    await state.update_data(village_id=None, custom_village=text, region=text)
    await state.set_state(MasterRegistration.experience)
    await message.answer("Tajribangiz qancha?", reply_markup=experience_inline_kb())


@router.callback_query(MasterRegistration.experience, F.data.startswith("mexp:"))
async def master_set_experience(callback: CallbackQuery, state: FSMContext) -> None:
    option = callback.data.split(":", 1)[1]
    if option not in EXPERIENCE_OPTIONS:
        await callback.answer("Noto'g'ri tanlov.", show_alert=True)
        return
    await state.update_data(experience_years=option, portfolio_ids=[])
    await state.set_state(MasterRegistration.portfolio)
    await callback.message.edit_text(
        f"Qilgan ishlaringizdan <b>{MIN_PORTFOLIO_PHOTOS}–{MAX_PORTFOLIO_PHOTOS}</b> ta rasm yuboring.",
        reply_markup=portfolio_kb(0, MIN_PORTFOLIO_PHOTOS),
    )
    await callback.answer()


@router.message(MasterRegistration.portfolio, F.photo)
async def master_add_portfolio_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    photos: list[str] = list(data.get("portfolio_ids") or [])
    if len(photos) >= MAX_PORTFOLIO_PHOTOS:
        await message.answer("Yetarli rasm yuborildi. Davom etish tugmasini bosing.")
        return
    photos.append(message.photo[-1].file_id)
    await state.update_data(portfolio_ids=photos)
    remaining = MAX_PORTFOLIO_PHOTOS - len(photos)
    if len(photos) < MIN_PORTFOLIO_PHOTOS:
        text = f"Qabul qilindi: {len(photos)} ta. Yana kamida {MIN_PORTFOLIO_PHOTOS - len(photos)} ta yuboring."
    else:
        extra = f" Yana {remaining} ta qo'shishingiz mumkin." if remaining else ""
        text = f"{len(photos)} ta rasm saqlandi.{extra}"
    status_id = data.get("portfolio_status_id")
    markup = portfolio_kb(len(photos), MIN_PORTFOLIO_PHOTOS)
    if status_id:
        try:
            await message.bot.edit_message_text(
                text,
                chat_id=message.chat.id,
                message_id=status_id,
                reply_markup=markup,
            )
            return
        except TelegramAPIError:
            pass
    sent = await message.answer(text, reply_markup=markup)
    await state.update_data(portfolio_status_id=sent.message_id)


@router.message(MasterRegistration.portfolio)
async def master_portfolio_not_photo(message: Message) -> None:
    await message.answer("Faqat rasm yuboring.")


@router.callback_query(MasterRegistration.portfolio, F.data == "mport:done")
async def master_portfolio_done(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    photos: list[str] = list(data.get("portfolio_ids") or [])
    if len(photos) < MIN_PORTFOLIO_PHOTOS:
        await callback.answer(f"Kamida {MIN_PORTFOLIO_PHOTOS} ta rasm yuboring.", show_alert=True)
        return
    await state.set_state(MasterRegistration.confirm)
    await callback.message.edit_text(_summary_text(data), reply_markup=confirm_master_kb())
    await callback.answer()


@router.callback_query(MasterRegistration.confirm, F.data == "mconf:restart")
async def master_restart(callback: CallbackQuery, state: FSMContext, session: AsyncSession, settings: Settings) -> None:
    await state.clear()
    user = await get_or_create_user(session, callback.from_user, settings)
    categories = await _active_categories(session)
    await state.set_state(MasterRegistration.category)
    await callback.message.edit_text("Sohani tanlang:", reply_markup=categories_kb(categories, "mcat"))
    await callback.answer()
    await callback.message.answer("Boshidan boshladik.", reply_markup=main_menu_kb(user))


@router.callback_query(MasterRegistration.confirm, F.data == "mconf:ok")
async def master_confirm_ok(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    await callback.answer()
    await _submit_master(callback.message, state, session, settings, telegram_user=callback.from_user)


async def _submit_master(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
    telegram_user=None,
) -> None:
    from_user = telegram_user or message.from_user
    user = await get_or_create_user(session, from_user, settings)
    if not user.phone_number:
        await state.clear()
        await message.answer("Avval telefon raqamingizni yuboring.", reply_markup=phone_request_kb())
        return
    data = await state.get_data()
    category = await session.get(Category, data.get("category_id"))
    photos = list(data.get("portfolio_ids") or [])
    region = data.get("region")
    if category is None or not region or len(photos) < MIN_PORTFOLIO_PHOTOS:
        await state.clear()
        await message.answer("Sessiya eskirgan. Qaytadan boshlang.", reply_markup=main_menu_kb(user))
        return

    master = await session.scalar(select(Master).where(Master.user_id == user.id))
    payload = {
        "category_id": category.id,
        "sub_skills": data.get("sub_skills"),
        "village_id": data.get("village_id"),
        "custom_village": data.get("custom_village"),
        "region": region,
        "experience_years": data.get("experience_years"),
        "sample_photos": json.dumps(photos),
        "status": MasterStatus.PENDING,
    }
    if master is None:
        master = Master(user_id=user.id, **payload)
        session.add(master)
        await session.flush()
    else:
        for key, value in payload.items():
            setattr(master, key, value)
        await session.flush()

    master = await session.scalar(
        select(Master)
        .where(Master.id == master.id)
        .options(selectinload(Master.village), selectinload(Master.category), selectinload(Master.user))
    )
    caption = format_master_application(master, user, category, photo_count=len(photos))
    try:
        await send_photos_to_admins(message.bot, settings, photos, "🖼 Usta ishlaridan namunalar")
        await notify_admins(message.bot, settings, caption, reply_markup=master_review_kb(master.id))
    except TelegramAPIError:
        logger.exception("Adminga usta arizasi yuborilmadi")
    await state.clear()
    await message.answer("Ariza adminga yuborildi. Tasdiqni kuting.", reply_markup=main_menu_kb(user))


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
    place = order.location_label()
    try:
        await callback.bot.send_message(
            master.user.telegram_id,
            (
                f"✅ Siz #{order.id} buyurtmani oldingiz.\n"
                f"📍 {html.escape(settings.DEFAULT_REGION)}, {html.escape(place)}\n"
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
