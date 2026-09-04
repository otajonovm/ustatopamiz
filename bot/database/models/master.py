from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.database.base import Base


class MasterStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class Master(Base):
    __tablename__ = "masters"
    __table_args__ = (UniqueConstraint("user_id", name="uq_masters_user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    region: Mapped[str] = mapped_column(String(100))
    experience_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[MasterStatus] = mapped_column(
        Enum(
            MasterStatus,
            name="master_status",
            native_enum=False,
            values_callable=lambda items: [item.value for item in items],
        ),
        default=MasterStatus.PENDING,
        server_default=MasterStatus.PENDING.value,
    )
    subscription_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rating: Mapped[float] = mapped_column(Float, default=5.0, server_default="5.0")
    completed_orders_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    warnings_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    user: Mapped["User"] = relationship(back_populates="masters")
    category: Mapped["Category"] = relationship(back_populates="masters")
    payments: Mapped[list["SubscriptionPayment"]] = relationship(back_populates="master")
    orders: Mapped[list["Order"]] = relationship(back_populates="master")
