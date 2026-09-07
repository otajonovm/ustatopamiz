import re

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.constants import SUGGESTION_AUTO_THRESHOLD
from bot.database.models import Category, Suggestion, Village
from bot.keyboards.inline import suggestion_kb
from bot.services.telegram_helpers import notify_admins


def normalize_name(text: str) -> str:
    return " ".join((text or "").strip().split()).lower()[:100]


def display_name(text: str) -> str:
    cleaned = " ".join((text or "").strip().split())
    return cleaned[:100]


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", normalize_name(text))
    slug = slug.strip("-")[:50] or "boshqa"
    return slug


async def record_suggestion(
    session: AsyncSession,
    bot: Bot,
    settings: Settings,
    *,
    suggestion_type: str,
    raw_text: str,
) -> Suggestion:
    name = normalize_name(raw_text)
    shown = display_name(raw_text)
    if not name:
        raise ValueError("empty")

    suggestion = await session.scalar(
        select(Suggestion).where(Suggestion.type == suggestion_type, Suggestion.name == name)
    )
    if suggestion is None:
        suggestion = Suggestion(type=suggestion_type, name=name, display_name=shown, counter=1)
        session.add(suggestion)
        await session.flush()
        await notify_admins(
            bot,
            settings,
            f"✏️ Yangi taklif ({suggestion_type}): <b>{shown}</b>",
            reply_markup=suggestion_kb(suggestion.id),
        )
        return suggestion

    suggestion.counter += 1
    if not suggestion.display_name:
        suggestion.display_name = shown
    await session.flush()
    if suggestion.counter >= SUGGESTION_AUTO_THRESHOLD and not suggestion.is_approved:
        created = await approve_suggestion(session, suggestion)
        if created:
            await notify_admins(
                bot,
                settings,
                f"🤖 Yangi {suggestion_type} avtomatik qo'shildi: <b>{suggestion.display_name}</b>",
            )
    return suggestion


async def get_or_create_custom_category(session: AsyncSession, raw_text: str) -> Category:
    title = display_name(raw_text)
    slug = slugify(title)
    category = await session.scalar(select(Category).where(Category.slug == slug))
    if category is None:
        category = await session.scalar(select(Category).where(Category.name == title))
    if category is None:
        category = Category(name=title, slug=slug, group_id=0, is_active=False)
        session.add(category)
        await session.flush()
        return category
    if category.name != title:
        category.name = title
    await session.flush()
    return category


async def approve_suggestion(session: AsyncSession, suggestion: Suggestion) -> bool:
    if suggestion.is_approved:
        return False
    title = suggestion.display_name or suggestion.name
    if suggestion.type == "village":
        existing = await session.scalar(select(Village).where(Village.name == title))
        if existing is None:
            existing = await session.scalar(select(Village).where(Village.name == suggestion.name))
        if existing is None:
            session.add(Village(name=title, is_active=True, order_index=1000 + suggestion.id))
        else:
            existing.is_active = True
            existing.name = title
    else:
        category = await get_or_create_custom_category(session, title)
        category.is_active = True
        category.name = title
    suggestion.is_approved = True
    await session.flush()
    return True
