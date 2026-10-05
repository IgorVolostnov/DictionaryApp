from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.aliases import MANAGER
from app.db.models import Alias, Product
from app.db.search import load_search_index
from app.domain.pricing import DEFAULT_GROUP
from app.domain.search import Candidate, CatalogItem, LineMatch, Status, Via

pytestmark = [pytest.mark.db, pytest.mark.asyncio]


def product(article: str, name: str, sort_order: int | None, active: bool) -> Product:
    return Product(
        article=article,
        name=name,
        extra_photos=[],
        price_group=DEFAULT_GROUP,
        sort_order=sort_order,
        active=active,
    )


async def test_load_search_index(pg_session: AsyncSession) -> None:
    a1, a2 = product("A1", "Насос", 10, True), product("A2", "Шланг", None, False)
    pg_session.add_all([a1, a2])
    await pg_session.flush()
    pg_session.add(Alias(key="SYNONYM", product_id=a1.id, source=MANAGER, author="Света"))
    await pg_session.flush()
    index = await load_search_index(pg_session)
    expected = Candidate(CatalogItem(a1.id, "A1", "Насос", 10, True), (Via.ALIAS,))
    assert index.find("SYNONYM") == LineMatch("SYNONYM", Status.FOUND, (expected,))
    assert index.find("a2").status is Status.INACTIVE
