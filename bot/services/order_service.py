from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from bot.database.models import Order, OrderStatus


async def create_order(
    session: AsyncSession,
    *,
    client_id: int,
    category_id: int,
    region: str,
    description: str | None,
    voice_file_id: str | None,
    photo_file_id: str | None,
) -> Order:
    order = Order(
        client_id=client_id,
        category_id=category_id,
        region=region,
        description=description,
        voice_file_id=voice_file_id,
        photo_file_id=photo_file_id,
        status=OrderStatus.NEW,
    )
    session.add(order)
    await session.flush()
    result = await session.scalar(
        select(Order)
        .where(Order.id == order.id)
        .options(selectinload(Order.client), selectinload(Order.category))
    )
    return result


async def mark_order_sent(order: Order, message_id: int) -> None:
    order.status = OrderStatus.SENT_TO_GROUP
    order.group_message_id = message_id
