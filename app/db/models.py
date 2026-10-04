"""Таблицы базы. Схема меняется только миграциями (migrations/versions)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Identity,
    Integer,
    MetaData,
    Numeric,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
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


class Product(Base):
    """Товар из distr.xlsx. Поля как в DistrItem; active — товар есть в последней выгрузке."""

    __tablename__ = "product"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    article: Mapped[str] = mapped_column(Text, unique=True)
    code_1c: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    barcode: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric)
    price_distr: Mapped[Decimal | None] = mapped_column(Numeric)
    price_dealer: Mapped[Decimal | None] = mapped_column(Numeric)
    price_retail: Mapped[Decimal | None] = mapped_column(Numeric)
    price_min_retail: Mapped[Decimal | None] = mapped_column(Numeric)
    brand: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    photo: Mapped[str | None] = mapped_column(Text)
    extra_photos: Mapped[list[str]] = mapped_column(ARRAY(Text))
    weight_g: Mapped[Decimal | None] = mapped_column(Numeric)
    length_mm: Mapped[Decimal | None] = mapped_column(Numeric)
    width_mm: Mapped[Decimal | None] = mapped_column(Numeric)
    height_mm: Mapped[Decimal | None] = mapped_column(Numeric)
    volume_m3: Mapped[Decimal | None] = mapped_column(Numeric)
    package: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(Text)
    certificate_url: Mapped[str | None] = mapped_column(Text)
    certificate_until: Mapped[str | None] = mapped_column(Text)
    price_group: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean)


class SourceImport(Base):
    """Журнал загрузок выгрузок: какой файл, кто, когда, сколько строк."""

    __tablename__ = "source_import"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    source: Mapped[str] = mapped_column(Text)
    file_name: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(Text)
    total: Mapped[int] = mapped_column(Integer)
    added: Mapped[int] = mapped_column(Integer)
    deactivated: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Customer(Base):
    """Покупатель из price_user.csv. Поля как в CustomerRow; таблица заменяется каждой выгрузкой."""

    __tablename__ = "customer"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    emails: Mapped[list[str]] = mapped_column(ARRAY(Text))
    price_type: Mapped[str] = mapped_column(Text)
    credit_limit: Mapped[Decimal | None] = mapped_column(Numeric)
    deferral_days: Mapped[int | None] = mapped_column(Integer)
    debt: Mapped[Decimal | None] = mapped_column(Numeric)
    group_emails: Mapped[list[str]] = mapped_column(ARRAY(Text))
