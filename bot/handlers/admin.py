import html
import logging
from datetime import timedelta

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, ChatMemberUpdated, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.config import Settings
from bot.database.models import Category, Master, MasterStatus, PaymentStatus, SubscriptionPayment, User, UserRole
from bot.database.seed import bind_all_categories_to_group
from bot.filters import IsAdmin
from bot.services.order_service import utcnow
from bot.services.telegram_helpers import create_one_time_invite, notify_admins

EMPTY_INLINE = InlineKeyboardMarkup(inline_keyboard=[])

router = Router(name="admin")
logger = logging.getLogger(__name__)


@router.my_chat_member()
async def bot_membership_changed(event: ChatMemberUpdated, session: AsyncSession, settings: Settings) -> None:
    if event.chat.type not in {"group", "supergroup"}:
        return
    if event.new_chat_member.status not in {"member", "administrator"}:
        return
    await bind_all_categories_to_group(session, event.chat.id)
    await notify_admins(
        event.bot,
        settings,
        f"✅ Bot guruhga qo'shildi.\nNomi: {html.escape(event.chat.title or '-')}\nID: <code>{event.chat.id}</code>",
    )


@router.message(Command("group_id"))
async def cmd_group_id(message: Message, session: AsyncSession, settings: Settings) -> None:
    await message.answer(f"Chat ID: <code>{message.chat.id}</code>\nTur: {message.chat.type}")
    if message.chat.type in {"group", "supergroup"} and message.from_user and message.from_user.id in settings.ADMIN_IDS:
        await bind_all_categories_to_group(session, message.chat.id)
        await message.answer(f"Barcha sohalar shu guruhga bog'landi: <code>{message.chat.id}</code>")


@router.message(Command("categories"), IsAdmin())
async def cmd_categories(message: Message, session: AsyncSession) -> None:
    categories = list(await session.scalars(select(Category).order_by(Category.id)))
    lines = ["<b>Sohalar</b>:\n"]
    for category in categories:
        status = "✅" if category.group_id else "⚠️ group_id yo'q"
        lines.append(
            f"• <b>{html.escape(category.name)}</b> (<code>{category.slug}</code>)\n"
            f"  group_id: <code>{category.group_id}</code> — {status}"
        )
    await message.answer("\n".join(lines))


@router.message(Command("set_group"), IsAdmin())
async def cmd_set_group(message: Message, command: CommandObject, session: AsyncSession) -> None:
    parts = (command.args or "").split()
    if len(parts) != 2:
        await message.answer("Format: <code>/set_group santexnika -1001234567890</code>")
        return
    slug, group_id_raw = parts[0].lower(), parts[1]
    try:
        group_id = int(group_id_raw)
    except ValueError:
        await message.answer("group_id butun son bo'lishi kerak.")
        return
    category = await session.scalar(select(Category).where(Category.slug == slug))
    if category is None:
        await message.answer("Slug topilmadi. /categories")
        return
    category.group_id = group_id
    await message.answer(f"{html.escape(category.name)} guruhi: <code>{group_id}</code>")


@router.message(Command("ban"), IsAdmin())
async def cmd_ban(message: Message, command: CommandObject, session: AsyncSession) -> None:
    if not command.args or not command.args.strip().isdigit():
        await message.answer("Format: <code>/ban 123456789</code>")
        return
    telegram_id = int(command.args.strip())
    user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is None:
        await message.answer("Foydalanuvchi topilmadi.")
        return
    user.is_banned = True
    await message.answer(f"Bloklandi: <code>{telegram_id}</code>")


@router.message(Command("unban"), IsAdmin())
async def cmd_unban(message: Message, command: CommandObject, session: AsyncSession) -> None:
    if not command.args or not command.args.strip().isdigit():
        await message.answer("Format: <code>/unban 123456789</code>")
        return
    telegram_id = int(command.args.strip())
    user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is None:
        await message.answer("Foydalanuvchi topilmadi.")
        return
    user.is_banned = False
    await message.answer(f"Blokdan chiqarildi: <code>{telegram_id}</code>")


@router.callback_query(F.data.startswith("master:ok:"), IsAdmin())
async def approve_master(callback: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    master = await session.scalar(
        select(Master)
        .where(Master.id == int(callback.data.rsplit(":", 1)[1]))
        .options(selectinload(Master.user), selectinload(Master.category))
    )
    if master is None:
        await callback.answer("Ariza topilmadi.", show_alert=True)
        return
    master.status = MasterStatus.APPROVED
    master.user.role = UserRole.MASTER
    invite_link = await create_one_time_invite(
        callback.bot,
        master.category.group_id,
        master.user.full_name,
        fallback_link=settings.GROUP_INVITE_LINK,
    )
    text = (
        f"✅ Arizangiz tasdiqlandi!\nSoha: <b>{html.escape(master.category.name)}</b>\n"
        f"Hudud: {html.escape(master.region)}\n\n"
        "Endi guruhdagi buyurtmalarni olishingiz mumkin.\n"
    )
    if invite_link:
        text += f"\nGuruh havolasi:\n{invite_link}"
    try:
        await callback.bot.send_message(master.user.telegram_id, text)
    except TelegramAPIError:
        logger.warning("Ustaga tasdiq yuborilmadi")
    base = callback.message.html_text or callback.message.caption or callback.message.text or "Ariza"
    try:
        await callback.message.edit_text(f"{base}\n\n✅ Tasdiqlandi.", reply_markup=EMPTY_INLINE)
    except TelegramAPIError:
        await callback.message.edit_caption(caption=f"{base}\n\n✅ Tasdiqlandi.", reply_markup=EMPTY_INLINE)
    await callback.answer("Tasdiqlandi.")


@router.callback_query(F.data.startswith("master:no:"), IsAdmin())
async def reject_master(callback: CallbackQuery, session: AsyncSession) -> None:
    master = await session.scalar(
        select(Master)
        .where(Master.id == int(callback.data.rsplit(":", 1)[1]))
        .options(selectinload(Master.user), selectinload(Master.category))
    )
    if master is None:
        await callback.answer("Ariza topilmadi.", show_alert=True)
        return
    master.status = MasterStatus.REJECTED
    try:
        await callback.bot.send_message(
            master.user.telegram_id,
            f"❌ {html.escape(master.category.name)} sohasi bo'yicha ariza rad etildi.",
        )
    except TelegramAPIError:
        logger.warning("Ustaga rad javobi yuborilmadi")
    base = callback.message.html_text or callback.message.caption or callback.message.text or "Ariza"
    try:
        await callback.message.edit_text(f"{base}\n\n❌ Rad etildi.", reply_markup=EMPTY_INLINE)
    except TelegramAPIError:
        await callback.message.edit_caption(caption=f"{base}\n\n❌ Rad etildi.", reply_markup=EMPTY_INLINE)
    await callback.answer("Rad etildi.")


@router.callback_query(F.data.startswith("pay:ok:"), IsAdmin())
async def confirm_payment(callback: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    payment = await session.scalar(
        select(SubscriptionPayment)
        .where(SubscriptionPayment.id == int(callback.data.rsplit(":", 1)[1]))
        .options(selectinload(SubscriptionPayment.master).selectinload(Master.user))
    )
    if payment is None or payment.status != PaymentStatus.PENDING:
        await callback.answer("To'lov topilmadi yoki allaqachon ko'rilgan.", show_alert=True)
        return
    payment.status = PaymentStatus.CONFIRMED
    master = payment.master
    start = utcnow()
    until = master.subscription_until
    if until is not None:
        if until.tzinfo is None:
            until = until.replace(tzinfo=start.tzinfo)
        if until > start:
            start = until
    master.subscription_until = start + timedelta(days=payment.days_added or settings.SUBSCRIPTION_DAYS)
    try:
        await callback.bot.send_message(
            master.user.telegram_id,
            f"✅ To'lov tasdiqlandi. Obuna: {master.subscription_until:%Y-%m-%d %H:%M} UTC gacha.",
        )
    except TelegramAPIError:
        logger.warning("Ustaga to'lov xabari yuborilmadi")
    try:
        await callback.message.edit_caption(
            caption=(callback.message.caption or "Chek") + "\n\n✅ Tasdiqlandi",
            reply_markup=EMPTY_INLINE,
        )
    except TelegramAPIError:
        await callback.message.edit_reply_markup(reply_markup=EMPTY_INLINE)
    await callback.answer("To'lov tasdiqlandi.")


@router.callback_query(F.data.startswith("pay:no:"), IsAdmin())
async def reject_payment(callback: CallbackQuery, session: AsyncSession) -> None:
    payment = await session.scalar(
        select(SubscriptionPayment)
        .where(SubscriptionPayment.id == int(callback.data.rsplit(":", 1)[1]))
        .options(selectinload(SubscriptionPayment.master).selectinload(Master.user))
    )
    if payment is None or payment.status != PaymentStatus.PENDING:
        await callback.answer("To'lov topilmadi.", show_alert=True)
        return
    payment.status = PaymentStatus.REJECTED
    try:
        await callback.bot.send_message(
            payment.master.user.telegram_id,
            "❌ Chek qabul qilinmadi. To'g'ri chek yuboring.",
        )
    except TelegramAPIError:
        logger.warning("Ustaga rad to'lov xabari yuborilmadi")
    try:
        await callback.message.edit_caption(
            caption=(callback.message.caption or "Chek") + "\n\n❌ Rad etildi",
            reply_markup=EMPTY_INLINE,
        )
    except TelegramAPIError:
        await callback.message.edit_reply_markup(reply_markup=EMPTY_INLINE)
    await callback.answer("Chek rad etildi.")
