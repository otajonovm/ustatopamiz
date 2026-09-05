import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import selectinload

from bot.config import Settings
from bot.database.models import Master, MasterStatus
from bot.services.telegram_helpers import kick_from_group

logger = logging.getLogger(__name__)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def check_subscriptions(bot: Bot, session_factory: async_sessionmaker, settings: Settings) -> None:
    if not settings.REQUIRE_SUBSCRIPTION:
        return
    now = datetime.now(timezone.utc)
    soon = now + timedelta(days=3)
    async with session_factory() as session:
        masters = list(
            await session.scalars(
                select(Master)
                .where(Master.status == MasterStatus.APPROVED)
                .options(selectinload(Master.user), selectinload(Master.category))
            )
        )
        for master in masters:
            until = master.subscription_until
            if until is None:
                continue
            until = _aware(until)
            chat_id = master.user.telegram_id
            group_id = master.category.group_id or settings.DEFAULT_GROUP_ID
            try:
                if now <= until <= soon:
                    days_left = max(1, (until - now).days)
                    await bot.send_message(
                        chat_id,
                        f"⏰ Obunangiz tugashiga {days_left} kun qoldi. "
                        "Botdagi «Obunani to'lash» orqali yangilang.",
                    )
                elif until < now:
                    await kick_from_group(bot, group_id, chat_id)
                    await bot.send_message(
                        chat_id,
                        "❌ Obuna muddati tugadi. Guruhdan chiqarildingiz. "
                        "Qayta kirish uchun bot orqali to'lov qiling.",
                    )
            except Exception:
                logger.exception("Obuna tekshiruvi xatosi: master_id=%s", master.id)
        await session.commit()


def setup_scheduler(bot: Bot, session_factory: async_sessionmaker, settings: Settings) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=ZoneInfo(settings.TIMEZONE))
    scheduler.add_job(
        check_subscriptions,
        "cron",
        hour=9,
        minute=0,
        kwargs={"bot": bot, "session_factory": session_factory, "settings": settings},
        id="daily_subscription_check",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Obuna scheduler 09:00 (%s) da ishga tushdi", settings.TIMEZONE)
    return scheduler
