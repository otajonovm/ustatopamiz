from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.database.models import Master, MasterStatus, Order, OrderStatus, User, UserRole


async def get_or_create_user(session: AsyncSession, telegram_user, settings) -> User:
    user = await session.scalar(
        select(User).where(User.telegram_id == telegram_user.id).options(selectinload(User.masters))
    )
    full_name = (telegram_user.full_name or "Foydalanuvchi")[:150]
    is_admin = telegram_user.id in settings.ADMIN_IDS

    if user is None:
        user = User(
            telegram_id=telegram_user.id,
            full_name=full_name,
            role=UserRole.ADMIN if is_admin else UserRole.CLIENT,
        )
        session.add(user)
        await session.flush()
        return user

    user.full_name = full_name
    if is_admin:
        user.role = UserRole.ADMIN
    return user


async def get_approved_master(session: AsyncSession, telegram_id: int) -> Master | None:
    return await session.scalar(
        select(Master)
        .join(User)
        .where(User.telegram_id == telegram_id, Master.status == MasterStatus.APPROVED)
        .options(selectinload(Master.user), selectinload(Master.category))
    )


def has_active_subscription(master: Master) -> bool:
    if master.subscription_until is None:
        return False
    now = datetime.now(timezone.utc)
    until = master.subscription_until
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    return until >= now


async def client_has_open_order(session: AsyncSession, client_id: int) -> bool:
    existing = await session.scalar(
        select(Order.id).where(
            Order.client_id == client_id,
            Order.status.in_(
                [
                    OrderStatus.PENDING_MODERATION,
                    OrderStatus.APPROVED_OPEN,
                    OrderStatus.TAKEN,
                    OrderStatus.DISPUTED,
                ]
            ),
        )
    )
    return existing is not None
