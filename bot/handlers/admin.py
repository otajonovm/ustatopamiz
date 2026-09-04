import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, ChatMemberUpdated, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.config import Settings
from bot.database.models import Category, Master, MasterStatus, UserRole
from bot.database.seed import bind_all_categories_to_group
from bot.filters import IsAdmin
from bot.services.telegram_service import create_one_time_invite, notify_admins

EMPTY_INLINE = InlineKeyboardMarkup(inline_keyboard=[])

router = Router(name="admin")
logger = logging.getLogger(__name__)


@router.my_chat_member()
async def bot_membership_changed(
    event: ChatMemberUpdated,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if event.chat.type not in {"group", "supergroup"}:
        return
    status = event.new_chat_member.status
    if status not in {"member", "administrator"}:
        logger.info("Bot guruhdan chiqdi yoki cheklangan: %s", event.chat.id)
        return
    await bind_all_categories_to_group(session, event.chat.id)
    logger.info("Guruh avtomatik bog'landi: %s (%s)", event.chat.id, event.chat.title)
    await notify_admins(
        event.bot,
        settings,
        f"✅ Bot guruhga qo'shildi.\nNomi: {event.chat.title}\nID: <code>{event.chat.id}</code>",
    )


@router.message(Command("group_id"))
async def cmd_group_id(message: Message, session: AsyncSession, settings: Settings) -> None:
    await message.answer(f"Chat ID: <code>{message.chat.id}</code>\nTur: {message.chat.type}")
    if message.chat.type not in {"group", "supergroup"}:
        return
    if message.from_user and message.from_user.id in settings.ADMIN_IDS:
        await bind_all_categories_to_group(session, message.chat.id)
        await message.answer(f"Barcha sohalar shu guruhga bog'landi: <code>{message.chat.id}</code>")


@router.message(Command("categories"), IsAdmin())
async def cmd_categories(message: Message, session: AsyncSession) -> None:
    categories = list(await session.scalars(select(Category).order_by(Category.id)))
    if not categories:
        await message.answer("Kategoriyalar yo'q.")
        return

    lines = ["<b>Sohalar</b>:\n"]
    for category in categories:
        status = "✅" if category.group_id else "⚠️ group_id yo'q"
        active = "faol" if category.is_active else "o'chiq"
        lines.append(
            f"• <b>{category.name}</b> (<code>{category.slug}</code>)\n"
            f"  group_id: <code>{category.group_id}</code> — {status}, {active}"
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
        slugs = ", ".join(
            item.slug for item in await session.scalars(select(Category).order_by(Category.id))
        )
        await message.answer(f"Slug topilmadi. Mavjud: {slugs}")
        return

    category.group_id = group_id
    await message.answer(f"{category.name} guruhi yangilandi: <code>{group_id}</code>")


@router.callback_query(F.data.startswith("master:ok:"), IsAdmin())
async def approve_master(callback: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    master_id = int(callback.data.rsplit(":", maxsplit=1)[1])
    master = await session.scalar(
        select(Master)
        .where(Master.id == master_id)
        .options(selectinload(Master.user), selectinload(Master.category))
    )
    if master is None:
        await callback.answer("Ariza topilmadi.", show_alert=True)
        return
    if master.status == MasterStatus.APPROVED:
        link = await create_one_time_invite(
            callback.bot,
            master.category.group_id,
            master.user.full_name,
            fallback_link=settings.GROUP_INVITE_LINK,
        )
        if link:
            try:
                await callback.bot.send_message(
                    master.user.telegram_id,
                    f"Guruh havolasi:\n{link}",
                )
            except TelegramAPIError:
                logger.warning("Ustaga havola qayta yuborilmadi")
        await callback.answer("Allaqachon tasdiqlangan. Havola qayta yuborildi.")
        return

    master.status = MasterStatus.APPROVED
    master.user.role = UserRole.MASTER
    master.user.is_verified = True

    invite_link = None
    invite_error = None
    try:
        invite_link = await create_one_time_invite(
            callback.bot,
            master.category.group_id,
            master.user.full_name,
            fallback_link=settings.GROUP_INVITE_LINK,
        )
    except TelegramAPIError as error:
        logger.exception("Invite link yaratilmadi: %s", error)
        invite_error = str(error)

    user_text = (
        f"✅ Arizangiz tasdiqlandi!\nSoha: <b>{master.category.name}</b>\nHudud: {master.region}\n\n"
    )
    if invite_link:
        user_text += f"Yopiq guruhga kirish havolasi:\n{invite_link}"
    elif not master.category.group_id and not settings.GROUP_INVITE_LINK:
        user_text += "Guruh hali sozlanmagan. Admin havolani keyin yuboradi."
    else:
        user_text += "Havola yaratishda xatolik bo'ldi. Admin tez orada yuboradi."

    try:
        await callback.bot.send_message(master.user.telegram_id, user_text)
    except TelegramAPIError:
        logger.warning("Ustaga tasdiq xabari yuborilmadi: %s", master.user.telegram_id)

    extra = ""
    if invite_link:
        extra = "\nHavola ustaga yuborildi."
    elif invite_error:
        extra = f"\n⚠️ Havola: {invite_error}"
    elif not invite_link:
        extra = "\n⚠️ Guruh ID sozlanmagan, havola yuborilmadi."

    base = callback.message.html_text or callback.message.text or "Ariza"
    await callback.message.edit_text(f"{base}\n\n✅ Tasdiqlandi.{extra}", reply_markup=EMPTY_INLINE)
    await callback.answer("Tasdiqlandi.")


@router.callback_query(F.data.startswith("master:no:"), IsAdmin())
async def reject_master(callback: CallbackQuery, session: AsyncSession) -> None:
    master_id = int(callback.data.rsplit(":", maxsplit=1)[1])
    master = await session.scalar(
        select(Master)
        .where(Master.id == master_id)
        .options(selectinload(Master.user), selectinload(Master.category))
    )
    if master is None:
        await callback.answer("Ariza topilmadi.", show_alert=True)
        return

    master.status = MasterStatus.REJECTED
    try:
        await callback.bot.send_message(
            master.user.telegram_id,
            f"❌ {master.category.name} sohasi bo'yicha arizangiz rad etildi.",
        )
    except TelegramAPIError:
        logger.warning("Ustaga rad javobi yuborilmadi: %s", master.user.telegram_id)

    base = callback.message.html_text or callback.message.text or "Ariza"
    await callback.message.edit_text(f"{base}\n\n❌ Rad etildi.", reply_markup=EMPTY_INLINE)
    await callback.answer("Rad etildi.")
