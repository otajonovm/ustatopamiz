from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.database.models import User


class BanCheckMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        session: AsyncSession | None = data.get("session")
        settings: Settings | None = data.get("settings")
        if user is None or session is None:
            return await handler(event, data)
        if settings and user.id in settings.ADMIN_IDS:
            return await handler(event, data)

        db_user = await session.scalar(select(User).where(User.telegram_id == user.id))
        if db_user and db_user.is_banned:
            text = "Sizning profilingiz bloklangan. Admin bilan bog'laning."
            if isinstance(event, Message):
                await event.answer(text)
            elif isinstance(event, CallbackQuery):
                await event.answer(text, show_alert=True)
            return None
        return await handler(event, data)
