"""Таблицы базы. Схема меняется только миграциями (migrations/versions)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Identity, MetaData, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    # Постоянные имена ограничений: по ним миграции находят, что удалять при откате.
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class PriceDocument(Base):
    """Загрузка из админки: справочник групп (группа на строку) или описание видов цен."""

    __tablename__ = "price_document"
    __table_args__ = (CheckConstraint("kind IN ('groups', 'types')", name="kind"),)

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    kind: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
