from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.database.base import Base


class OrderStatus(str, enum.Enum):
    PENDING_MODERATION = "pending_moderation"
    APPROVED_OPEN = "approved_open"
    TAKEN = "taken"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    DISPUTED = "disputed"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    master_id: Mapped[int | None] = mapped_column(ForeignKey("masters.id"), nullable=True)
    village_id: Mapped[int | None] = mapped_column(ForeignKey("villages.id"), nullable=True)
    custom_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    region: Mapped[str] = mapped_column(String(100), default="", server_default="")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    voice_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    photo_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(
            OrderStatus,
            name="order_status",
            native_enum=False,
            values_callable=lambda items: [item.value for item in items],
        ),
        default=OrderStatus.PENDING_MODERATION,
        server_default=OrderStatus.PENDING_MODERATION.value,
    )
    group_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    client_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    client: Mapped["User"] = relationship(back_populates="orders")
    category: Mapped["Category"] = relationship(back_populates="orders")
    master: Mapped["Master | None"] = relationship(back_populates="orders")
    village: Mapped["Village | None"] = relationship(back_populates="orders")

    def location_label(self) -> str:
        if self.village is not None:
            return self.village.name
        return self.custom_address or self.region or "Ko'rsatilmagan"
