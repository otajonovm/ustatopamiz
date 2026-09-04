import html
import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.database.models import OrderStatus
from bot.filters import IsAdmin
from bot.services.order_service import load_order
from bot.services.telegram_helpers import notify_admins, publish_order_to_group

EMPTY_INLINE = InlineKeyboardMarkup(inline_keyboard=[])
router = Router(name="moderation")
logger = logging.getLogger(__name__)


@router.callback_query(F.data.startswith("mod:ok:"), IsAdmin())
async def approve_order(callback: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    order = await load_order(session, int(callback.data.rsplit(":", 1)[1]))
    if order is None or order.status != OrderStatus.PENDING_MODERATION:
        await callback.answer("E'lon topilmadi yoki allaqachon ko'rilgan.", show_alert=True)
        return
    try:
        posted = await publish_order_to_group(callback.bot, order, settings.DEFAULT_REGION)
    except TelegramAPIError as error:
        logger.exception("Guruhga chiqarilmadi")
        await callback.answer(f"Guruh xatosi: {error}", show_alert=True)
        await notify_admins(callback.bot, settings, f"⚠️ #{order.id} guruhga chiqmadi: {error}")
        return
    if posted is None:
        await callback.answer("Guruh ID sozlanmagan. /group_id yuboring.", show_alert=True)
        return
    order.status = OrderStatus.APPROVED_OPEN
    order.group_message_id = posted.message_id
    try:
        await callback.bot.send_message(
            order.client.telegram_id,
            "Buyurtmangiz tasdiqlandi va ustalarga yuborildi.",
        )
    except TelegramAPIError:
        logger.warning("Mijozga tasdiq yuborilmadi")
    base = callback.message.html_text or callback.message.caption or callback.message.text or "E'lon"
    try:
        await callback.message.edit_text(f"{base}\n\n✅ Guruhga chiqarildi.", reply_markup=EMPTY_INLINE)
    except TelegramAPIError:
        await callback.message.edit_reply_markup(reply_markup=EMPTY_INLINE)
    await callback.answer("Chiqarildi.")


@router.callback_query(F.data.startswith("mod:no:"), IsAdmin())
async def reject_order(callback: CallbackQuery, session: AsyncSession) -> None:
    order = await load_order(session, int(callback.data.rsplit(":", 1)[1]))
    if order is None or order.status != OrderStatus.PENDING_MODERATION:
        await callback.answer("E'lon topilmadi.", show_alert=True)
        return
    order.status = OrderStatus.CANCELLED
    try:
        await callback.bot.send_message(
            order.client.telegram_id,
            "Buyurtmangiz spam/nomaqbul deb rad etildi.",
        )
    except TelegramAPIError:
        logger.warning("Mijozga rad xabari yuborilmadi")
    try:
        await callback.message.edit_reply_markup(reply_markup=EMPTY_INLINE)
    except TelegramAPIError:
        pass
    await callback.answer("Rad etildi.")
