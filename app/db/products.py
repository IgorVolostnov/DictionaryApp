"""Товары из distr.xlsx в базе.

Каждая выгрузка заменяет каталог: товары из файла добавляются или обновляются, остальные
помечаются неактивными. Они не удаляются: на них ссылаются словарь и прошлые заявки.
Транзакцией управляет вызывающий код.
"""

from __future__ import annotations

import dataclasses
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Product, SourceImport
from app.db.prices import load_price_settings
from app.sources.distr import DistrItem

DISTR: Final = "distr"
# Обновляются при каждой выгрузке: все поля DistrItem, кроме артикула, и признак активности.
_UPDATED: Final = (
    *(field.name for field in dataclasses.fields(DistrItem) if field.name != "article"),
    "active",
)


class ImportRejectedError(ValueError):
    """Выгрузка не загружена, данные в базе не изменились."""


@dataclass(frozen=True, slots=True)
class DistrImport:
    total: int  # товаров без повторов
    added: int
    deactivated: int
    duplicates: tuple[str, ...]  # артикулы, встретившиеся несколько раз: взята первая строка
    unknown_groups: tuple[str, ...]  # нет в справочнике: действует основная формула вида цены


async def import_distr(
    session: AsyncSession, items: Sequence[DistrItem], author: str, file_name: str
) -> DistrImport:
    if not items:
        raise ImportRejectedError("в файле нет ни одного товара, каталог не изменён")
    unique: dict[str, DistrItem] = {}
    for item in items:
        unique.setdefault(item.article, item)
    counts = Counter(item.article for item in items)

    connection = await session.connection()
    rows = await connection.execute(select(Product.article, Product.active))
    before: dict[str, bool] = {row.article: row.active for row in rows}
    await connection.execute(update(Product).values(active=False))
    stmt = insert(Product)
    upsert = stmt.on_conflict_do_update(
        index_elements=[Product.article],
        set_={name: stmt.excluded[name] for name in _UPDATED},
    )
    await connection.execute(upsert, [_values(item) for item in unique.values()])

    known = set((await load_price_settings(session)).groups)
    result = DistrImport(
        total=len(unique),
        added=len(unique.keys() - before.keys()),
        deactivated=sum(1 for a, active in before.items() if active and a not in unique),
        duplicates=tuple(article for article, n in counts.items() if n > 1),
        unknown_groups=tuple(sorted({i.price_group for i in unique.values()} - known)),
    )
    session.add(
        SourceImport(
            source=DISTR,
            file_name=file_name,
            author=author,
            total=result.total,
            added=result.added,
            deactivated=result.deactivated,
        )
    )
    await session.flush()
    return result


def _values(item: DistrItem) -> dict[str, Any]:
    # psycopg превращает в массив PostgreSQL только list, не tuple.
    return dataclasses.asdict(item) | {"extra_photos": list(item.extra_photos), "active": True}
