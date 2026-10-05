from __future__ import annotations

import dataclasses
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.imports import ImportRejectedError
from app.db.models import Product, SourceImport
from app.db.prices import save_price_groups
from app.db.products import DistrImport, GroupsUpdate, import_distr, update_price_groups
from app.domain.pricing import DEFAULT_GROUP
from app.sources.distr import DistrItem
from app.sources.nomenclature import NomenclatureRow

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
    price_group=None,
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


async def test_site_fields(pg_session: AsyncSession) -> None:
    url = "https://www.rossvik.moscow/catalog/tovar/a1/"
    await import_distr(pg_session, [item("A1", sort_order=500, page_url=url)], "admin", "1.xlsx")
    product = (await catalog(pg_session))["A1"]
    assert (product.sort_order, product.page_url) == (500, url)


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


async def test_duplicate_codes_first_row_wins(pg_session: AsyncSession) -> None:
    items = [item("A1", code_1c="K1"), item("A2", code_1c="K1")]
    result = await import_distr(pg_session, items, "admin", "distr.xlsx")
    assert (result.total, result.duplicate_codes) == (2, ("K1",))
    products = await catalog(pg_session)
    assert (products["A1"].code_1c, products["A2"].code_1c) == ("K1", None)


async def test_rename_by_code(pg_session: AsyncSession) -> None:
    first = [item("A1", code_1c="K1"), item("A2", code_1c="K2")]
    await import_distr(pg_session, first, "admin", "1.xlsx")
    old_id = (await catalog(pg_session))["A1"].id
    second = [item("B1", code_1c="K1"), item("A2", code_1c="K2")]
    result = await import_distr(pg_session, second, "admin", "2.xlsx")
    assert result == DistrImport(2, 0, 0, (), (), renamed=(("A1", "B1"),))
    products = await catalog(pg_session)
    assert set(products) == {"B1", "A2"}
    assert products["B1"].id == old_id


async def test_rename_frees_old_article(pg_session: AsyncSession) -> None:
    # Код ушёл к новому артикулу, а старый артикул пришёл с новым кодом: это новый товар.
    await import_distr(pg_session, [item("A1", code_1c="K1")], "admin", "1.xlsx")
    old_id = (await catalog(pg_session))["A1"].id
    items = [item("A1", code_1c="K3"), item("B1", code_1c="K1")]
    result = await import_distr(pg_session, items, "admin", "2.xlsx")
    assert (result.added, result.deactivated, result.renamed) == (1, 0, (("A1", "B1"),))
    products = await catalog(pg_session)
    assert products["B1"].id == old_id
    assert products["A1"].code_1c == "K3"


async def test_rename_to_taken_article(pg_session: AsyncSession) -> None:
    await import_distr(pg_session, [item("A1", code_1c="K1"), item("B1")], "admin", "1.xlsx")
    result = await import_distr(pg_session, [item("B1", code_1c="K1")], "admin", "2.xlsx")
    assert result.rename_conflicts == (("K1", "A1", "B1"),)
    assert (result.added, result.deactivated, result.renamed) == (0, 1, ())
    products = await catalog(pg_session)
    assert (products["A1"].code_1c, products["A1"].active) == (None, False)
    assert products["B1"].code_1c == "K1"


async def test_codes_swapped(pg_session: AsyncSession) -> None:
    first = [item("A1", code_1c="K1"), item("A2", code_1c="K2")]
    await import_distr(pg_session, first, "admin", "1.xlsx")
    swapped = [item("A1", code_1c="K2"), item("A2", code_1c="K1")]
    result = await import_distr(pg_session, swapped, "admin", "2.xlsx")
    assert result.rename_conflicts == (("K2", "A2", "A1"), ("K1", "A1", "A2"))
    products = await catalog(pg_session)
    assert (products["A1"].code_1c, products["A2"].code_1c) == ("K2", "K1")


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


async def test_import_without_group_keeps_group(pg_session: AsyncSession) -> None:
    await import_distr(pg_session, [item("A1", price_group="Расходка")], "admin", "1.xlsx")
    items = [item("A1", price_group=None, price_retail=Decimal(300)), item("A2", price_group=None)]
    await import_distr(pg_session, items, "admin", "2.xlsx")
    products = await catalog(pg_session)
    assert products["A1"].price_group == "Расходка"
    assert products["A1"].price_retail == Decimal(300)
    assert products["A2"].price_group == DEFAULT_GROUP


async def test_update_price_groups(pg_session: AsyncSession) -> None:
    await save_price_groups(pg_session, ["Расходка"], "admin")
    items = [item(a, price_group=None) for a in ("A1", "A2", "A3", "A4", "A5")]
    await import_distr(pg_session, items, "admin", "distr.xlsx")
    rows = [
        NomenclatureRow("A1", "Расходка"),  # меняется
        NomenclatureRow("A2", DEFAULT_GROUP),  # в файле две разные группы
        NomenclatureRow("A2", "Расходка"),
        NomenclatureRow("A3", "Насосы"),  # нет в справочнике
        NomenclatureRow("A5", DEFAULT_GROUP),  # уже такая
        NomenclatureRow("A9", "Расходка"),  # нет в каталоге
    ]
    result = await update_price_groups(pg_session, rows)
    assert result == GroupsUpdate(1, ("A9",), ("A4",), ("Насосы",), ("A2",))
    groups = {a: p.price_group for a, p in (await catalog(pg_session)).items()}
    assert groups == {
        "A1": "Расходка",
        "A2": DEFAULT_GROUP,
        "A3": DEFAULT_GROUP,
        "A4": DEFAULT_GROUP,
        "A5": DEFAULT_GROUP,
    }
    assert (await update_price_groups(pg_session, rows)).changed == 0
