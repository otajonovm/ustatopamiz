import html
import logging

from aiogram import F, Router
from aiogram.enums import ContentType
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.constants import BTN_NEW_ORDER
from bot.database.models import Category, OrderStatus, Village
from bot.keyboards.inline import cancel_inline_kb, categories_kb, moderation_kb, rating_kb, villages_kb
from bot.keyboards.reply import main_menu_kb, phone_request_kb
from bot.services.order_service import apply_rating, create_order, load_order
from bot.services.suggestion_service import get_or_create_custom_category, record_suggestion
from bot.services.telegram_helpers import notify_admins, restore_order_in_group
from bot.services.user_service import client_has_open_order, get_or_create_user
from bot.states.client_states import OrderCreation

router = Router(name="client")
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


async def _ask_village(callback: CallbackQuery, state: FSMContext, session: AsyncSession, page: int = 0) -> None:
    data = await state.get_data()
    villages = await _active_villages(session)
    await state.set_state(OrderCreation.village)
    await callback.message.edit_text(
        f"Soha: <b>{html.escape(data.get('category_name', ''))}</b>\nHududni tanlang:",
        reply_markup=villages_kb(villages, page, "c"),
    )


@router.message(F.text == BTN_NEW_ORDER)
async def start_order(message: Message, state: FSMContext, session: AsyncSession, settings: Settings) -> None:
    user = await _require_phone(message, session, settings)
    if user is None:
        return
    if await client_has_open_order(session, user.id):
        await message.answer(
            "Sizda hozir ochiq buyurtma bor. Avval uni yakunlang yoki admin tasdiqini kuting.",
            reply_markup=main_menu_kb(user),
        )
        return

    await state.clear()
    categories = await _active_categories(session)
    await state.set_state(OrderCreation.category)
    await message.answer("Qaysi soha bo'yicha usta kerak?", reply_markup=main_menu_kb(user))
    await message.answer("Sohani tanlang:", reply_markup=categories_kb(categories, "cat"))


@router.callback_query(OrderCreation.category, F.data == "cat:other")
async def client_other_category(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(OrderCreation.custom_category)
    await callback.message.edit_text("Kerakli sohani yozing:", reply_markup=cancel_inline_kb())
    await callback.answer()


@router.message(OrderCreation.custom_category, F.text)
async def client_save_custom_category(
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
    await state.update_data(category_id=category.id, category_name=category.name)
    villages = await _active_villages(session)
    await state.set_state(OrderCreation.village)
    await message.answer(
        f"Soha: <b>{html.escape(category.name)}</b>\nHududni tanlang:",
        reply_markup=villages_kb(villages, 0, "c"),
    )


@router.callback_query(OrderCreation.category, F.data.startswith("cat:"))
async def choose_category(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    category = await session.get(Category, int(callback.data.split(":", 1)[1]))
    if category is None or not category.is_active:
        await callback.answer("Bu soha mavjud emas.", show_alert=True)
        return
    await state.update_data(category_id=category.id, category_name=category.name)
    await _ask_village(callback, state, session)
    await callback.answer()


@router.callback_query(OrderCreation.village, F.data.startswith("vpg:c:"))
async def client_village_page(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await _ask_village(callback, state, session, int(callback.data.rsplit(":", 1)[1]))
    await callback.answer()


@router.callback_query(OrderCreation.village, F.data.startswith("vid:c:"))
async def client_choose_village(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    village = await session.get(Village, int(callback.data.rsplit(":", 1)[1]))
    if village is None or not village.is_active:
        await callback.answer("Hudud topilmadi.", show_alert=True)
        return
    data = await state.get_data()
    await state.update_data(village_id=village.id, custom_address=None, region=village.name)
    await state.set_state(OrderCreation.description)
    await callback.message.edit_text(
        f"Soha: <b>{html.escape(data.get('category_name', ''))}</b>\n"
        f"Hudud: <b>{html.escape(village.name)}</b>\n\n"
        "Muammoni matn, rasm yoki ovozli xabar sifatida yuboring.",
        reply_markup=cancel_inline_kb(),
    )
    await callback.answer()


@router.callback_query(OrderCreation.village, F.data == "voth:c")
async def client_other_village(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(OrderCreation.custom_village)
    await callback.message.edit_text("Hududingizni yozing:", reply_markup=cancel_inline_kb())
    await callback.answer()


@router.message(OrderCreation.custom_village, F.text)
async def client_save_custom_village(
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
    data = await state.get_data()
    await state.update_data(village_id=None, custom_address=text, region=text)
    await state.set_state(OrderCreation.description)
    await message.answer(
        f"Soha: <b>{html.escape(data.get('category_name', ''))}</b>\n"
        f"Hudud: <b>{html.escape(text)}</b>\n\n"
        "Muammoni matn, rasm yoki ovozli xabar sifatida yuboring.",
        reply_markup=cancel_inline_kb(),
    )


@router.message(
    OrderCreation.description,
    F.content_type.in_({ContentType.TEXT, ContentType.PHOTO, ContentType.VOICE}),
)
async def save_description(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
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
        await message.answer("Sessiya eskirgan. Qaytadan buyurtma bering.", reply_markup=main_menu_kb(user))
        return

    description = None
    photo_id = None
    voice_id = None
    if message.photo:
        photo_id = message.photo[-1].file_id
        description = message.caption or "Rasm yuborildi."
    elif message.voice:
        voice_id = message.voice.file_id
        description = message.caption or "Ovozli xabar yuborildi."
    elif message.text:
        description = message.text.strip()
        if not description:
            await message.answer("Iltimos, muammoni qisqacha yozing.")
            return

    order = await create_order(
        session,
        client_id=user.id,
        category_id=category_id,
        region=region,
        village_id=data.get("village_id"),
        custom_address=data.get("custom_address"),
        description=description,
        voice_id=voice_id,
        photo_id=photo_id,
    )
    await notify_admins(
        message.bot,
        settings,
        (
            f"🛡 <b>Moderatsiya: #{order.id}</b>\n"
            f"👤 {html.escape(user.full_name)} · <code>{user.phone_number}</code>\n"
            f"🔧 {html.escape(order.category.name)}\n"
            f"📍 {html.escape(settings.DEFAULT_REGION)}, {html.escape(region)}\n"
            f"📝 {html.escape(description or '-')}"
        ),
        reply_markup=moderation_kb(order.id),
    )
    if photo_id:
        for admin_id in settings.ADMIN_IDS:
            try:
                await message.bot.send_photo(admin_id, photo_id)
            except Exception:
                logger.warning("Admin ga rasm yuborilmadi")
    if voice_id:
        for admin_id in settings.ADMIN_IDS:
            try:
                await message.bot.send_voice(admin_id, voice_id)
            except Exception:
                logger.warning("Admin ga ovoz yuborilmadi")

    await state.clear()
    await message.answer(
        "Buyurtma moderatsiyaga yuborildi. Tasdiqlangach ustalarga chiqadi.",
        reply_markup=main_menu_kb(user),
    )


@router.message(OrderCreation.description)
async def invalid_description(message: Message) -> None:
    await message.answer("Faqat matn, rasm yoki ovozli xabar yuboring.")


@router.callback_query(F.data.startswith("done:"))
async def complete_job(callback: CallbackQuery, session: AsyncSession) -> None:
    order = await load_order(session, int(callback.data.split(":", 1)[1]))
    if order is None or order.client.telegram_id != callback.from_user.id:
        await callback.answer("Buyurtma topilmadi.", show_alert=True)
        return
    if order.status != OrderStatus.TAKEN:
        await callback.answer("Bu buyurtma yakunlanmaydi.", show_alert=True)
        return
    order.status = OrderStatus.COMPLETED
    if order.master:
        order.master.completed_orders_count += 1
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Ishni baholang (1-5):", reply_markup=rating_kb(order.id))
    await callback.answer("Rahmat!")


@router.callback_query(F.data.startswith("reopen:"))
async def reopen_job(callback: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    order = await load_order(session, int(callback.data.split(":", 1)[1]))
    if order is None or order.client.telegram_id != callback.from_user.id:
        await callback.answer("Buyurtma topilmadi.", show_alert=True)
        return
    if order.status != OrderStatus.TAKEN:
        await callback.answer("Bu buyurtma qayta ochilmaydi.", show_alert=True)
        return
    previous_master = order.master
    order.status = OrderStatus.APPROVED_OPEN
    order.master_id = None
    order.taken_at = None
    if previous_master:
        previous_master.warnings_count += 1
        try:
            await callback.bot.send_message(
                previous_master.user.telegram_id,
                f"⚠️ Mijoz #{order.id} buyurtmasini bekor qildi (bog'lanmadi). Ogohlantirish qayd etildi.",
            )
        except Exception:
            logger.warning("Ustaga ogohlantirish yuborilmadi")
        await notify_admins(
            callback.bot,
            settings,
            f"⚠️ #{order.id} qayta ochildi. Usta: {html.escape(previous_master.user.full_name)} "
            f"(ogohlantirish: {previous_master.warnings_count})",
        )
    posted = await restore_order_in_group(callback.bot, order, settings.DEFAULT_REGION, order.category.group_id)
    if posted:
        order.group_message_id = posted.message_id
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Buyurtma qayta e'longa chiqarildi. Boshqa usta olishi mumkin.")
    await callback.answer()


@router.callback_query(F.data.startswith("rate:"))
async def rate_master(callback: CallbackQuery, session: AsyncSession) -> None:
    _, order_id, stars_raw = callback.data.split(":")
    order = await load_order(session, int(order_id))
    if order is None or order.client.telegram_id != callback.from_user.id:
        await callback.answer("Buyurtma topilmadi.", show_alert=True)
        return
    if order.status != OrderStatus.COMPLETED or order.client_rating is not None:
        await callback.answer("Baho allaqachon qabul qilingan.", show_alert=True)
        return
    stars = int(stars_raw)
    order.client_rating = stars
    if order.master:
        apply_rating(order.master, stars)
        try:
            await callback.bot.send_message(
                order.master.user.telegram_id,
                f"⭐ Mijoz sizga {stars}/5 baho qo'ydi. Reyting: {order.master.rating}",
            )
        except Exception:
            logger.warning("Ustaga baho yuborilmadi")
    await callback.message.edit_text(f"Baho qabul qilindi: {'⭐' * stars}")
    await callback.answer("Rahmat!")
