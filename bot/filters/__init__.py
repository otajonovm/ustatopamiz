from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.database.models import Master, MasterStatus, User


class IsAdmin(BaseFilter):
    async def __call__(self, event: TelegramObject, settings: Settings) -> bool:
        user = getattr(event, "from_user", None)
        return bool(user and user.id in settings.ADMIN_IDS)


class IsMaster(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery, session: AsyncSession) -> bool:
        if event.from_user is None:
            return False
        master = await session.scalar(
            select(Master)
            .join(User)
            .where(User.telegram_id == event.from_user.id, Master.status == MasterStatus.APPROVED)
        )
        return master is not None
