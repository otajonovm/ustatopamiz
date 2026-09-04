import logging

from aiogram import F, Router
from aiogram.enums import ContentType
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.constants import BTN_NEW_ORDER, REGIONS
from bot.database.models import Category
from bot.keyboards.inline import categories_kb, regions_kb
from bot.keyboards.reply import cancel_kb, main_menu_kb, phone_request_kb
from bot.services.order_service import create_order, mark_order_sent
from bot.services.telegram_service import notify_admins, publish_order_to_group
from bot.services.user_service import get_or_create_user
from bot.states.client_states import OrderCreation

router = Router(name="client")
logger = logging.getLogger(__name__)


async def _require_phone(message: Message, session: AsyncSession, settings: Settings):
    user = await get_or_create_user(session, message.from_user, settings)
    if user.phone_number:
        return user
    await message.answer(
        "Avval telefon raqamingizni yuboring.",
        reply_markup=phone_request_kb(),
    )
    return None


@router.message(F.text == BTN_NEW_ORDER)
async def start_order(
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
        await message.answer("Hozircha sohalar mavjud emas. Keyinroq urinib ko'ring.")
        return

    await state.set_state(OrderCreation.category)
    await message.answer("Qaysi soha bo'yicha usta kerak?", reply_markup=categories_kb(categories, "cat"))
    await message.answer("Bekor qilish uchun tugmani bosing.", reply_markup=cancel_kb())


@router.callback_query(OrderCreation.category, F.data.startswith("cat:"))
async def choose_category(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    category_id = int(callback.data.split(":", maxsplit=1)[1])
    category = await session.get(Category, category_id)
    if category is None or not category.is_active:
        await callback.answer("Bu soha mavjud emas.", show_alert=True)
        return

    await state.update_data(category_id=category.id, category_name=category.name)
    await state.set_state(OrderCreation.region)
    await callback.message.edit_text(
        f"Soha: <b>{category.name}</b>\nHududni tanlang:",
        reply_markup=regions_kb("reg"),
    )
    await callback.answer()


@router.callback_query(OrderCreation.region, F.data.startswith("reg:"))
async def choose_region(callback: CallbackQuery, state: FSMContext) -> None:
    region = callback.data.split(":", maxsplit=1)[1]
    if region not in REGIONS:
        await callback.answer("Noto'g'ri hudud.", show_alert=True)
        return

    data = await state.get_data()
    await state.update_data(region=region)
    await state.set_state(OrderCreation.description)
    await callback.message.edit_text(
        f"Soha: <b>{data.get('category_name')}</b>\n"
        f"Hudud: <b>{region}</b>\n\n"
        "Muammoni matn, rasm yoki ovozli xabar sifatida yuboring."
    )
    await callback.answer()


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
        await message.answer("Sessiya eskirgan. Qaytadan buyurtma bering.", reply_markup=main_menu_kb())
        return

    description = None
    photo_file_id = None
    voice_file_id = None

    if message.photo:
        photo_file_id = message.photo[-1].file_id
        description = message.caption or "Rasm yuborildi."
    elif message.voice:
        voice_file_id = message.voice.file_id
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
        description=description,
        voice_file_id=voice_file_id,
        photo_file_id=photo_file_id,
    )

    username = message.from_user.username if message.from_user else None
    posted = None
    try:
        posted = await publish_order_to_group(message.bot, order, settings.DEFAULT_REGION, username)
    except TelegramAPIError as error:
        logger.exception("Buyurtma guruhga yuborilmadi: %s", error)
        await notify_admins(
            message.bot,
            settings,
            f"⚠️ Buyurtma #{order.id} guruhga yuborilmadi.\nSoha: {order.category.name}\nXato: {error}",
        )

    if posted:
        mark_order_sent(order, posted.message_id)
        await message.answer(
            "Buyurtmangiz ustalarga yuborildi. Tez orada siz bilan bog'lanishadi.",
            reply_markup=main_menu_kb(),
        )
    elif not order.category.group_id:
        await notify_admins(
            message.bot,
            settings,
            f"⚠️ {order.category.name} guruhi sozlanmagan. Buyurtma #{order.id} guruhga ketmadi.\n"
            f"/set_group {order.category.slug} &lt;group_id&gt;",
        )
        await message.answer(
            "Buyurtma qabul qilindi. Guruh hali sozlanmagan, adminlar tez orada ko'rib chiqadi.",
            reply_markup=main_menu_kb(),
        )
    else:
        await message.answer(
            "Buyurtma saqlandi, lekin guruhga yuborishda xatolik bo'ldi. Adminlar xabardor.",
            reply_markup=main_menu_kb(),
        )

    await state.clear()


@router.message(OrderCreation.description)
async def invalid_description(message: Message) -> None:
    await message.answer("Faqat matn, rasm yoki ovozli xabar yuboring.")
