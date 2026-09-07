from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.constants import BESHARIQ_VILLAGES, CATEGORY_SEEDS
from bot.database.models import Category, Village


async def seed_categories(session: AsyncSession, default_group_id: int = 0) -> None:
    for name, slug in CATEGORY_SEEDS:
        category = await session.scalar(select(Category).where(Category.slug == slug))
        if category is None:
            session.add(
                Category(
                    name=name,
                    slug=slug,
                    group_id=default_group_id,
                    is_active=True,
                )
            )
            continue
        if default_group_id:
            category.group_id = default_group_id
        if category.name != name:
            category.name = name
    await session.commit()


async def seed_villages(session: AsyncSession) -> None:
    for index, name in enumerate(BESHARIQ_VILLAGES):
        village = await session.scalar(select(Village).where(Village.name == name))
        if village is None:
            session.add(Village(name=name, is_active=True, order_index=index))
            continue
        village.order_index = index
        village.is_active = True
    await session.commit()


async def seed_initial_data(session: AsyncSession, default_group_id: int = 0) -> None:
    await seed_categories(session, default_group_id)
    await seed_villages(session)


async def bind_all_categories_to_group(session: AsyncSession, group_id: int) -> None:
    categories = list(await session.scalars(select(Category)))
    for category in categories:
        category.group_id = group_id
    await session.flush()
