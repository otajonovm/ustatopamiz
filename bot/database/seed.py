from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.constants import CATEGORY_SEEDS
from bot.database.models import Category


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
    await session.commit()


async def bind_all_categories_to_group(session: AsyncSession, group_id: int) -> None:
    categories = list(await session.scalars(select(Category)))
    for category in categories:
        category.group_id = group_id
    await session.flush()
