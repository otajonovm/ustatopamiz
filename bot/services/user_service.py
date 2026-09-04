from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.config import Settings
from bot.database.models import User, UserRole


async def get_or_create_user(session: AsyncSession, telegram_user, settings: Settings) -> User:
    user = await session.scalar(
        select(User)
        .where(User.telegram_id == telegram_user.id)
        .options(selectinload(User.masters))
    )
    full_name = (telegram_user.full_name or "Foydalanuvchi")[:150]
    is_admin = telegram_user.id in settings.ADMIN_IDS

    if user is None:
        user = User(
            telegram_id=telegram_user.id,
            full_name=full_name,
            role=UserRole.ADMIN if is_admin else UserRole.CLIENT,
            is_verified=is_admin,
        )
        session.add(user)
        await session.flush()
        return user

    user.full_name = full_name
    if is_admin:
        user.role = UserRole.ADMIN
        user.is_verified = True
    return user
