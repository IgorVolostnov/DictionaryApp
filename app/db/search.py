"""Индекс поиска из каталога и словаря. Только чтение."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Alias, Product
from app.domain.search import CatalogItem, SearchIndex


async def load_search_index(session: AsyncSession) -> SearchIndex:
    connection = await session.connection()
    products = await connection.execute(
        select(Product.id, Product.article, Product.name, Product.sort_order, Product.active)
    )
    items = [CatalogItem(r.id, r.article, r.name, r.sort_order, r.active) for r in products]
    aliases = await connection.execute(select(Alias.key, Alias.product_id))
    return SearchIndex(items, [(r.key, r.product_id) for r in aliases])
