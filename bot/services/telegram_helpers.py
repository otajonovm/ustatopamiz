import html
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardMarkup, InputMediaPhoto, Message

from bot.config import Settings
from bot.database.models import Category, Master, Order, User
from bot.keyboards.inline import take_job_kb

logger = logging.getLogger(__name__)


def group_id_candidates(group_id: int) -> list[int]:
    ids = [group_id]
    digits = str(abs(group_id))
    if group_id < 0 and not digits.startswith("100"):
        ids.append(int(f"-100{digits}"))
    return ids


def format_order_group_post(order: Order, default_region: str) -> str:
    description = order.description or "Tavsif yo'q (media yuborilgan)."
    return (
        f"🚨 <b>Yangi buyurtma: #{html.escape(order.category.name)}</b>\n"
        f"📍 <b>Hudud:</b> {html.escape(default_region)}, {html.escape(order.region)}\n"
        f"📝 <b>Muammo:</b> {html.escape(description)}\n"
        f"#buyurtma_{order.id}"
    )


def format_order_taken(order: Order, master_name: str) -> str:
    return (
        f"❌ Buyurtma olindi. Usta: {html.escape(master_name)}\n"
        f"#{html.escape(order.category.name)} · {html.escape(order.region)}\n"
        f"#buyurtma_{order.id}"
    )


def format_master_application(master: Master, user: User, category: Category, photo_count: int = 0) -> str:
    experience = f"{master.experience_years} yil" if master.experience_years is not None else "Ko'rsatilmagan"
    phone = user.phone_number or "Ko'rsatilmagan"
    return (
        "👷 <b>Yangi usta arizasi</b>\n\n"
        f"👤 Ism: {html.escape(user.full_name)}\n"
        f"🆔 Telegram ID: <code>{user.telegram_id}</code>\n"
        f"📞 Telefon: <code>{html.escape(phone)}</code>\n"
        f"🔧 Soha: <b>{html.escape(category.name)}</b>\n"
        f"📍 Hudud: {html.escape(master.region)}\n"
        f"🛠 Tajriba: {html.escape(experience)}\n"
        f"🖼 Ish rasmlari: {photo_count} ta"
    )


async def send_photos_to_admins(bot: Bot, settings: Settings, photo_ids: list[str], caption: str) -> None:
    if not photo_ids:
        return
    for admin_id in settings.ADMIN_IDS:
        try:
            if len(photo_ids) == 1:
                await bot.send_photo(admin_id, photo=photo_ids[0], caption=caption)
                continue
            media = [InputMediaPhoto(media=photo_id) for photo_id in photo_ids[:10]]
            media[0].caption = caption
            await bot.send_media_group(admin_id, media=media)
        except TelegramBadRequest:
            logger.warning("Admin %s ga ish rasmlari yuborilmadi", admin_id)


async def notify_admins(
    bot: Bot,
    settings: Settings,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    for admin_id in settings.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, reply_markup=reply_markup)
        except TelegramBadRequest:
            logger.warning("Admin %s ga xabar yuborilmadi", admin_id)


async def _send_order_media(bot: Bot, chat_id: int, order: Order, caption: str, markup: InlineKeyboardMarkup | None):
    if order.photo_id:
        return await bot.send_photo(chat_id, photo=order.photo_id, caption=caption, reply_markup=markup)
    if order.voice_id:
        text_message = await bot.send_message(chat_id, caption, reply_markup=markup)
        await bot.send_voice(chat_id, voice=order.voice_id, reply_to_message_id=text_message.message_id)
        return text_message
    return await bot.send_message(chat_id, caption, reply_markup=markup)


async def publish_order_to_group(bot: Bot, order: Order, default_region: str) -> Message | None:
    if not order.category.group_id:
        return None
    caption = format_order_group_post(order, default_region)
    markup = take_job_kb(order.id)
    last_error: Exception | None = None
    for chat_id in group_id_candidates(order.category.group_id):
        try:
            return await _send_order_media(bot, chat_id, order, caption, markup)
        except TelegramBadRequest as error:
            last_error = error
            logger.warning("Guruhga yuborish xatosi (%s): %s", chat_id, error)
    if last_error:
        raise last_error
    return None


async def restore_order_in_group(bot: Bot, order: Order, default_region: str, group_id: int) -> Message | None:
    caption = format_order_group_post(order, default_region)
    markup = take_job_kb(order.id)
    for chat_id in group_id_candidates(group_id):
        try:
            if order.group_message_id:
                if order.photo_id:
                    await bot.edit_message_caption(
                        caption=caption,
                        chat_id=chat_id,
                        message_id=order.group_message_id,
                        reply_markup=markup,
                    )
                else:
                    await bot.edit_message_text(
                        caption,
                        chat_id=chat_id,
                        message_id=order.group_message_id,
                        reply_markup=markup,
                    )
                return None
        except TelegramBadRequest:
            pass
        try:
            return await _send_order_media(bot, chat_id, order, caption, markup)
        except TelegramBadRequest as error:
            logger.warning("Qayta e'lon xatosi (%s): %s", chat_id, error)
    return None


async def mark_group_order_taken(bot: Bot, order: Order, master_name: str, group_id: int) -> None:
    text = format_order_taken(order, master_name)
    if not order.group_message_id:
        return
    for chat_id in group_id_candidates(group_id):
        try:
            await bot.edit_message_caption(
                caption=text,
                chat_id=chat_id,
                message_id=order.group_message_id,
                reply_markup=None,
            )
            return
        except TelegramBadRequest:
            try:
                await bot.edit_message_text(
                    text,
                    chat_id=chat_id,
                    message_id=order.group_message_id,
                    reply_markup=None,
                )
                return
            except TelegramBadRequest:
                continue


async def create_one_time_invite(bot: Bot, group_id: int, master_name: str, fallback_link: str = "") -> str | None:
    if group_id:
        for chat_id in group_id_candidates(group_id):
            try:
                invite = await bot.create_chat_invite_link(
                    chat_id=chat_id,
                    name=f"Usta {master_name}"[:32],
                    member_limit=1,
                )
                return invite.invite_link
            except TelegramBadRequest as error:
                logger.warning("Invite link yaratilmadi (%s): %s", chat_id, error)
    return fallback_link or None


async def kick_from_group(bot: Bot, group_id: int, telegram_id: int) -> None:
    for chat_id in group_id_candidates(group_id):
        try:
            await bot.ban_chat_member(chat_id, telegram_id)
            await bot.unban_chat_member(chat_id, telegram_id)
            return
        except (TelegramBadRequest, TelegramForbiddenError) as error:
            logger.warning("Guruhdan chiqarib bo'lmadi (%s): %s", chat_id, error)


async def resolve_group_chat(bot: Bot, group_id: int):
    if not group_id:
        return None
    for chat_id in group_id_candidates(group_id):
        try:
            return await bot.get_chat(chat_id)
        except TelegramBadRequest:
            continue
    return None
