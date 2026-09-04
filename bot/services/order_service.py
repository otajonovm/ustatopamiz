from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.database.models import Master, Order, OrderStatus


async def create_order(
    session: AsyncSession,
    *,
    client_id: int,
    category_id: int,
    region: str,
    description: str | None,
    voice_id: str | None,
    photo_id: str | None,
) -> Order:
    order = Order(
        client_id=client_id,
        category_id=category_id,
        region=region,
        description=description,
        voice_id=voice_id,
        photo_id=photo_id,
        status=OrderStatus.PENDING_MODERATION,
    )
    session.add(order)
    await session.flush()
    return await session.scalar(
        select(Order)
        .where(Order.id == order.id)
        .options(selectinload(Order.client), selectinload(Order.category), selectinload(Order.master))
    )


async def load_order(session: AsyncSession, order_id: int, *, for_update: bool = False) -> Order | None:
    stmt = (
        select(Order)
        .where(Order.id == order_id)
        .options(
            selectinload(Order.client),
            selectinload(Order.category),
            selectinload(Order.master).selectinload(Master.user),
        )
    )
    if for_update:
        stmt = stmt.with_for_update()
    return await session.scalar(stmt)


def apply_rating(master, stars: int) -> None:
    count = master.completed_orders_count
    if count <= 1:
        master.rating = float(stars)
        return
    master.rating = round(((master.rating * (count - 1)) + stars) / count, 2)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
