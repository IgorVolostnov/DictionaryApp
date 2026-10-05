"""Словарь синонимов: ключ → товар.

Ключ — результат Преобразование (app.domain.normalize), как в Access; поиск сравнивает
с ним lookup_keys строки заявки. Ключи из Access переносит import_access_aliases,
менеджеры добавляют свои в админке. Повторный перенос заменяет только ключи из Access.
Транзакцией управляет вызывающий код.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.imports import ImportRejectedError, log_import
from app.db.models import Alias, Product
from app.domain.errors import InvalidAliasKeyError
from app.domain.normalize import ensure_storable_key
from app.sources.access_catalog import AccessProduct

ACCESS: Final = "access"
MANAGER: Final = "manager"
SOURCE: Final = "aliases"


@dataclass(frozen=True, slots=True)
class AliasImport:
    total: int  # ключей из Access в базе после загрузки
    added: int
    removed: int  # были в прошлой загрузке, в этой нет
    shared: int  # ключ у нескольких товаров Access: не перенесён
    not_found: tuple[str, ...]  # товары Access, которых нет в каталоге (код 1С или артикул)
    lost_keys: int  # ключей у ненайденных товаров
    invalid: tuple[str, ...]  # ключи, которые нельзя сохранить (ensure_storable_key)


async def import_access_aliases(
    session: AsyncSession, products: Sequence[AccessProduct], author: str, file_name: str
) -> AliasImport:
    if not products:
        raise ImportRejectedError("в файле нет ни одного товара, словарь не изменён")
    connection = await session.connection()
    catalog = (await connection.execute(select(Product.id, Product.article, Product.code_1c))).all()
    if not catalog:
        raise ImportRejectedError("каталог пуст: сначала загрузите distr.xlsx")
    by_code = {row.code_1c: row.id for row in catalog if row.code_1c is not None}
    by_article = {row.article: row.id for row in catalog}

    # Владелец ключа: id товара в каталоге или код/артикул ненайденного товара Access.
    owners: defaultdict[str, set[int | str]] = defaultdict(set)
    not_found: list[str] = []
    lost_keys = 0
    for product in products:
        found = _find(product, by_code, by_article)
        owner: int | str
        if found is None:
            owner = product.code_1c or product.article or product.name
            not_found.append(owner)
            lost_keys += len(product.keys)
        else:
            owner = found
        for key in product.keys:
            owners[key].add(owner)

    wanted: set[tuple[str, int]] = set()
    shared = 0
    invalid: list[str] = []
    for key, who in owners.items():
        if len(who) > 1:
            shared += 1
        elif not _storable(key):
            invalid.append(key)
        else:
            (only,) = who
            if isinstance(only, int):
                wanted.add((key, only))

    rows = (await connection.execute(select(Alias.key, Alias.product_id, Alias.source))).all()
    before = {(row.key, row.product_id) for row in rows if row.source == ACCESS}
    wanted -= {(row.key, row.product_id) for row in rows if row.source != ACCESS}
    await connection.execute(delete(Alias).where(Alias.source == ACCESS))
    if wanted:
        await connection.execute(
            insert(Alias),
            [
                {"key": key, "product_id": product_id, "source": ACCESS, "author": author}
                for key, product_id in sorted(wanted)
            ],
        )
    result = AliasImport(
        total=len(wanted),
        added=len(wanted - before),
        removed=len(before - wanted),
        shared=shared,
        not_found=tuple(sorted(not_found)),
        lost_keys=lost_keys,
        invalid=tuple(sorted(invalid)),
    )
    await log_import(
        session,
        source=SOURCE,
        file_name=file_name,
        author=author,
        total=result.total,
        added=result.added,
        deactivated=result.removed,
    )
    return result


def _find(
    product: AccessProduct, by_code: Mapping[str, int], by_article: Mapping[str, int]
) -> int | None:
    """Сначала по коду 1С (не меняется при переименовании), потом по артикулу."""
    found = by_code.get(product.code_1c) if product.code_1c is not None else None
    if found is None and product.article is not None:
        found = by_article.get(product.article)
    return found


def _storable(key: str) -> bool:
    try:
        ensure_storable_key(key)
    except InvalidAliasKeyError:
        return False
    return True
