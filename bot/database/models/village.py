from __future__ import annotations

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.database.base import Base


class Village(Base):
    __tablename__ = "villages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    order_index: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    masters: Mapped[list["Master"]] = relationship(back_populates="village")
    orders: Mapped[list["Order"]] = relationship(back_populates="village")
