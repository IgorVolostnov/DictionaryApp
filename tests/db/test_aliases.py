from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.aliases import ACCESS, MANAGER, AliasImport, import_access_aliases
from app.db.imports import ImportRejectedError
from app.db.models import Alias, Product, SourceImport
from app.db.products import import_distr
from app.sources.access_catalog import AccessProduct
from app.sources.distr import DistrItem

pytestmark = [pytest.mark.db, pytest.mark.asyncio]


def product(article: str, code: str | None = None) -> DistrItem:
    return DistrItem(
        article=article,
        code_1c=code,
        name="Товар",
        barcode=None,
        quantity=Decimal(1),
        price_distr=None,
        price_dealer=None,
        price_retail=None,
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
        price_group=None,
    )


def access(code: str | None, article: str | None, *keys: str) -> AccessProduct:
    return AccessProduct(
        code_1c=code,
        article=article,
        name="Товар",
        price_group=None,
        subgroup=None,
        brand=None,
        keys=keys,
    )


async def aliases(session: AsyncSession) -> set[tuple[str, str, str]]:
    rows = await session.execute(
        select(Alias.key, Product.article, Alias.source).join(
            Product, Alias.product_id == Product.id
        )
    )
    return {(row.key, row.article, row.source) for row in rows}


async def test_import(pg_session: AsyncSession) -> None:
    items = [product("A1", "K1"), product("A2", "K2"), product("A3")]
    await import_distr(pg_session, items, "admin", "distr.xlsx")
    products = [
        access("K1", "OLD1", "KEY1", "SHARED"),  # по коду, хотя артикул другой
        access(None, "A2", "KEY2"),  # без кода, по артикулу
        access("K9", "A3", "KEY3", "X", "''"),  # кода нет в каталоге, по артикулу
        access("K8", None, "SHARED", "LOST"),  # не найден
        access(None, "Z9", "LOST2"),  # не найден
    ]
    result = await import_access_aliases(pg_session, products, "admin", "access.xlsx")
    assert result == AliasImport(3, 3, 0, 1, ("K8", "Z9"), 3, ("''", "X"))
    assert await aliases(pg_session) == {
        ("KEY1", "A1", ACCESS),
        ("KEY2", "A2", ACCESS),
        ("KEY3", "A3", ACCESS),
    }


async def test_reload_keeps_manager_keys(pg_session: AsyncSession) -> None:
    await import_distr(pg_session, [product("A1", "K1")], "admin", "distr.xlsx")
    a1 = await pg_session.scalar(select(Product.id).where(Product.article == "A1"))
    assert a1 is not None
    pg_session.add_all(
        [Alias(key=key, product_id=a1, source=MANAGER, author="Света") for key in ("KEY1", "MGR")]
    )
    await pg_session.flush()
    first = await import_access_aliases(
        pg_session, [access("K1", "A1", "KEY1", "OLD")], "admin", "1.xlsx"
    )
    assert (first.total, first.added, first.removed) == (1, 1, 0)
    second = await import_access_aliases(
        pg_session, [access("K1", "A1", "KEY1", "NEW")], "admin", "2.xlsx"
    )
    assert (second.total, second.added, second.removed) == (1, 1, 1)
    assert await aliases(pg_session) == {
        ("KEY1", "A1", MANAGER),
        ("MGR", "A1", MANAGER),
        ("NEW", "A1", ACCESS),
    }
    log = await pg_session.scalars(
        select(SourceImport).where(SourceImport.source == "aliases").order_by(SourceImport.id)
    )
    assert [(e.file_name, e.total, e.added, e.deactivated) for e in log] == [
        ("1.xlsx", 1, 1, 0),
        ("2.xlsx", 1, 1, 1),
    ]


async def test_aliases_follow_renamed_product(pg_session: AsyncSession) -> None:
    await import_distr(pg_session, [product("A1", "K1")], "admin", "1.xlsx")
    await import_access_aliases(pg_session, [access("K1", "A1", "KEY")], "admin", "access.xlsx")
    await import_distr(pg_session, [product("B1", "K1")], "admin", "2.xlsx")
    assert await aliases(pg_session) == {("KEY", "B1", ACCESS)}


async def test_nothing_found(pg_session: AsyncSession) -> None:
    await import_distr(pg_session, [product("A1")], "admin", "distr.xlsx")
    result = await import_access_aliases(
        pg_session, [access(None, "Z9", "KEY")], "admin", "access.xlsx"
    )
    assert (result.total, result.not_found, result.lost_keys) == (0, ("Z9",), 1)


async def test_rejected(pg_session: AsyncSession) -> None:
    with pytest.raises(ImportRejectedError, match="каталог пуст"):
        await import_access_aliases(pg_session, [access("K1", "A1", "KEY")], "admin", "a.xlsx")
    with pytest.raises(ImportRejectedError, match="нет ни одного товара"):
        await import_access_aliases(pg_session, [], "admin", "a.xlsx")
