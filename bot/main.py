import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import ErrorEvent

from bot.config import get_settings
from bot.database.base import Base
from bot.database.models import Category, Master, Order, User  # noqa: F401
from bot.database.seed import seed_categories
from bot.database.session import create_engine_and_session
from bot.handlers.admin import router as admin_router
from bot.handlers.client import router as client_router
from bot.handlers.common import router as common_router
from bot.handlers.master import router as master_router
from bot.middlewares.db import DbSessionMiddleware
from bot.services.telegram_service import notify_admins, resolve_group_chat

logger = logging.getLogger(__name__)


async def main() -> None:
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        stream=sys.stdout,
    )
    settings = get_settings()
    engine, session_factory = create_engine_and_session(settings.DATABASE_URL)

    if settings.DATABASE_URL.startswith("sqlite"):
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        await seed_categories(session, settings.DEFAULT_GROUP_ID)
    if settings.DEFAULT_GROUP_ID:
        logger.info("Barcha sohalar guruhi: %s", settings.DEFAULT_GROUP_ID)

    if settings.REDIS_URL.startswith("redis://"):
        storage = RedisStorage.from_url(settings.REDIS_URL)
    else:
        storage = MemoryStorage()
        logger.info("FSM xotirada (Redis yo'q)")
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=storage)
    dp["settings"] = settings
    dp.update.middleware(DbSessionMiddleware(session_factory))
    dp.include_routers(admin_router, common_router, client_router, master_router)

    @dp.error()
    async def on_error(event: ErrorEvent) -> None:
        logger.exception("Xatolik: %s", event.exception)
        message = event.update.message or (event.update.callback_query and event.update.callback_query.message)
        if message:
            try:
                await message.answer("Xatolik yuz berdi. /start ni qayta yuboring.")
            except Exception:
                logger.warning("Foydalanuvchiga xato xabari yuborilmadi")

    logger.info("Usta Topamiz bot ishga tushmoqda")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        chat = await resolve_group_chat(bot, settings.DEFAULT_GROUP_ID)
        if chat:
            logger.info("Guruh topildi: %s (%s)", chat.id, chat.title)
        else:
            logger.warning(
                "Bot guruhni ko'rmayapti. @ustatopamiz_uzbot ni guruhga admin qilib qo'shing, "
                "keyin guruhda /group_id yuboring."
            )
            if settings.GROUP_INVITE_LINK:
                await notify_admins(
                    bot,
                    settings,
                    "⚠️ Bot hozircha guruhni topa olmayapti.\n\n"
                    "1) Guruhga @ustatopamiz_uzbot ni qo'shing\n"
                    "2) Uni administrator qiling (xabar yuborish + havola yaratish)\n"
                    "3) Guruhda /group_id yozing\n\n"
                    f"Guruh havolasi: {settings.GROUP_INVITE_LINK}",
                )
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        await storage.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
