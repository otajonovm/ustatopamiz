import html
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, Message

from bot.config import Settings
from bot.database.models import Category, Master, Order, User
from bot.keyboards.inline import order_contact_kb

logger = logging.getLogger(__name__)


def group_id_candidates(group_id: int) -> list[int]:
    ids = [group_id]
    digits = str(abs(group_id))
    if group_id < 0 and not digits.startswith("100"):
        ids.append(int(f"-100{digits}"))
    return ids


def format_order_post(order: Order, default_region: str, username: str | None) -> str:
    client = order.client
    phone = client.phone_number or "Ko'rsatilmagan"
    description = order.description or "Tavsif yo'q (media qo'shimcha yuborilgan)."
    username_line = f"\n👤 Username: @{html.escape(username)}" if username else ""
    return (
        "🆕 <b>Yangi buyurtma</b>\n\n"
        f"🔧 Soha: <b>{html.escape(order.category.name)}</b>\n"
        f"📍 Hudud: {html.escape(default_region)}, {html.escape(order.region)}\n"
        f"📝 Muammo:\n{html.escape(description)}\n\n"
        f"📞 Telefon: <code>{html.escape(phone)}</code>"
        f"{username_line}\n"
        f"#buyurtma_{order.id}"
    )


def format_master_application(master: Master, user: User, category: Category) -> str:
    experience = f"{master.experience_years} yil" if master.experience_years is not None else "Ko'rsatilmagan"
    phone = user.phone_number or "Ko'rsatilmagan"
    return (
        "👷 <b>Yangi usta arizasi</b>\n\n"
        f"👤 Ism: {html.escape(user.full_name)}\n"
        f"🆔 Telegram ID: <code>{user.telegram_id}</code>\n"
        f"📞 Telefon: <code>{html.escape(phone)}</code>\n"
        f"🔧 Soha: <b>{html.escape(category.name)}</b>\n"
        f"📍 Hudud: {html.escape(master.region)}\n"
        f"🛠 Tajriba: {html.escape(experience)}"
    )


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


async def _send_order(bot: Bot, chat_id: int, order: Order, caption: str, markup: InlineKeyboardMarkup | None):
    if order.photo_file_id:
        return await bot.send_photo(chat_id, photo=order.photo_file_id, caption=caption, reply_markup=markup)
    if order.voice_file_id:
        text_message = await bot.send_message(chat_id, caption, reply_markup=markup)
        await bot.send_voice(chat_id, voice=order.voice_file_id, reply_to_message_id=text_message.message_id)
        return text_message
    return await bot.send_message(chat_id, caption, reply_markup=markup)


async def publish_order_to_group(
    bot: Bot,
    order: Order,
    default_region: str,
    username: str | None,
) -> Message | None:
    if not order.category.group_id:
        return None

    caption = format_order_post(order, default_region, username)
    markup = order_contact_kb(order.client.telegram_id, username)
    last_error: Exception | None = None

    for chat_id in group_id_candidates(order.category.group_id):
        try:
            return await _send_order(bot, chat_id, order, caption, markup)
        except TelegramBadRequest as error:
            last_error = error
            message = str(error).lower()
            if "chat not found" in message:
                logger.warning("Guruh topilmadi: %s", chat_id)
                continue
            if "button" in message or "url" in message:
                try:
                    return await _send_order(bot, chat_id, order, caption, None)
                except TelegramBadRequest as retry_error:
                    last_error = retry_error
                    continue
            logger.warning("Guruhga yuborish xatosi (%s): %s", chat_id, error)

    if last_error:
        raise last_error
    return None


async def create_one_time_invite(
    bot: Bot,
    group_id: int,
    master_name: str,
    fallback_link: str = "",
) -> str | None:
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


async def resolve_group_chat(bot: Bot, group_id: int):
    if not group_id:
        return None
    for chat_id in group_id_candidates(group_id):
        try:
            return await bot.get_chat(chat_id)
        except TelegramBadRequest:
            continue
    return None
