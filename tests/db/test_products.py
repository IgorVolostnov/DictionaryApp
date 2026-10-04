from __future__ import annotations

import dataclasses
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Product, SourceImport
from app.db.prices import save_price_groups
from app.db.products import DistrImport, ImportRejectedError, import_distr
from app.domain.pricing import DEFAULT_GROUP
from app.sources.distr import DistrItem

pytestmark = [pytest.mark.db, pytest.mark.asyncio]

BASE = DistrItem(
    article="",
    code_1c=None,
    name="Товар",
    barcode=None,
    quantity=Decimal(5),
    price_distr=Decimal("100.50"),
    price_dealer=None,
    price_retail=Decimal(200),
    price_min_retail=None,
    brand=None,
    description=None,
    photo=None,
    extra_photos=(),
    weight_g=None,
    length_mm=None,
    width_mm=None,
    height_mm=None,
    volume_m3=None,
    package=None,
    country=None,
    certificate_url=None,
    certificate_until=None,
    price_group=DEFAULT_GROUP,
)


def item(article: str, **changes: Any) -> DistrItem:
    return dataclasses.replace(BASE, article=article, **changes)


async def catalog(session: AsyncSession) -> dict[str, Product]:
    # populate_existing: загрузка меняет строки мимо сессии, поэтому объекты перечитываются из базы.
    products = await session.scalars(select(Product).execution_options(populate_existing=True))
    return {product.article: product for product in products}


async def test_first_import(pg_session: AsyncSession) -> None:
    items = [item("A1", extra_photos=("1.jpg", "2.jpg")), item("A2")]
    result = await import_distr(pg_session, items, "admin", "distr.xlsx")
    assert result == DistrImport(2, 2, 0, (), ())
    products = await catalog(pg_session)
    assert products["A1"].extra_photos == ["1.jpg", "2.jpg"]
    assert products["A1"].price_distr == Decimal("100.50")
    assert all(product.active for product in products.values())
    log = await pg_session.scalar(select(SourceImport))
    assert log is not None
    assert (log.source, log.file_name, log.author, log.total) == ("distr", "distr.xlsx", "admin", 2)


async def test_next_import_updates_and_deactivates(pg_session: AsyncSession) -> None:
    await import_distr(pg_session, [item("A1"), item("A2")], "admin", "1.xlsx")
    changed = [item("A1", price_retail=Decimal(250)), item("A3")]
    assert await import_distr(pg_session, changed, "admin", "2.xlsx") == DistrImport(
        2, 1, 1, (), ()
    )
    products = await catalog(pg_session)
    assert products["A1"].price_retail == Decimal(250)
    assert {a: p.active for a, p in products.items()} == {"A1": True, "A2": False, "A3": True}
    # Вернувшийся товар снова активен, остальные сняты.
    assert await import_distr(pg_session, [item("A2")], "admin", "3.xlsx") == DistrImport(
        1, 0, 2, (), ()
    )
    assert (await catalog(pg_session))["A2"].active


async def test_duplicates_first_row_wins(pg_session: AsyncSession) -> None:
    items = [item("A1", name="Первый"), item("A2"), item("A1", name="Второй")]
    result = await import_distr(pg_session, items, "admin", "distr.xlsx")
    assert result.duplicates == ("A1",)
    assert result.total == 2
    assert (await catalog(pg_session))["A1"].name == "Первый"


async def test_unknown_price_groups(pg_session: AsyncSession) -> None:
    await save_price_groups(pg_session, ["Расходка"], "admin")
    items = [item("A1", price_group="Расходка"), item("A2", price_group="Насосы"), item("A3")]
    result = await import_distr(pg_session, items, "admin", "distr.xlsx")
    assert result.unknown_groups == ("Насосы",)


async def test_empty_file_rejected(pg_session: AsyncSession) -> None:
    await import_distr(pg_session, [item("A1")], "admin", "1.xlsx")
    with pytest.raises(ImportRejectedError, match="нет ни одного товара"):
        await import_distr(pg_session, [], "admin", "2.xlsx")
    assert (await catalog(pg_session))["A1"].active
