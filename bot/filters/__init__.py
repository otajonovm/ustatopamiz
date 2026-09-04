from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.database.models import User, UserRole


class IsAdmin(BaseFilter):
    async def __call__(self, event: TelegramObject, settings: Settings) -> bool:
        user = getattr(event, "from_user", None)
        return bool(user and user.id in settings.ADMIN_IDS)


class IsMaster(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery, session: AsyncSession) -> bool:
        if event.from_user is None:
            return False
        user = await session.scalar(select(User).where(User.telegram_id == event.from_user.id))
        return bool(user and user.role == UserRole.MASTER and user.is_verified)
