"""Товары из distr.xlsx в базе.

Каждая выгрузка заменяет каталог: товары из файла добавляются или обновляются, остальные
помечаются неактивными. Они не удаляются: на них ссылаются словарь и прошлые заявки.
Код 1С — постоянный номер товара: если товар с тем же кодом пришёл под новым артикулом,
строка переименовывается, и синонимы остаются при ней.
Если в выгрузке нет ценовой группы, группа товара не меняется: её ставит
update_price_groups из справочника номенклатуры 1С.
Транзакцией управляет вызывающий код.
"""

from __future__ import annotations

import dataclasses
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Final

from sqlalchemy import bindparam, select, update
from sqlalchemy.dialects.postgresql import Insert, insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.db.imports import FileStamp, ImportRejectedError, log_import
from app.db.models import Product
from app.db.prices import load_price_settings
from app.domain.pricing import DEFAULT_GROUP
from app.sources.distr import DistrItem
from app.sources.nomenclature import NomenclatureRow

DISTR: Final = "distr"
# Обновляются при каждой выгрузке: все поля DistrItem, кроме артикула, и признак активности.
_UPDATED: Final = (
    *(field.name for field in dataclasses.fields(DistrItem) if field.name != "article"),
    "active",
)
# Если в выгрузке нет группы, она у товара не меняется.
_KEEP_GROUP: Final = tuple(name for name in _UPDATED if name != "price_group")


@dataclass(frozen=True, slots=True)
class DistrImport:
    total: int  # товаров без повторов
    added: int
    deactivated: int
    duplicates: tuple[str, ...]  # артикулы, встретившиеся несколько раз: взята первая строка
    unknown_groups: tuple[str, ...]  # нет в справочнике: действует основная формула вида цены
    renamed: tuple[tuple[str, str], ...] = ()  # (старый артикул, новый), код 1С тот же
    # (код 1С, артикул в базе, артикул в файле): новый артикул занят другой строкой,
    # код перешёл к ней, синонимы остались у старой. Разобрать вручную.
    rename_conflicts: tuple[tuple[str, str, str], ...] = ()
    duplicate_codes: tuple[str, ...] = ()  # код у нескольких товаров: оставлен у первого


@dataclass(frozen=True, slots=True)
class GroupsUpdate:
    changed: int  # товаров, у которых группа изменилась
    not_in_catalog: tuple[str, ...]  # артикулы из файла, которых нет в каталоге
    not_in_file: tuple[str, ...]  # активные товары, которых нет в файле: группа прежняя
    unknown_groups: tuple[str, ...]  # нет в справочнике: такие строки пропущены
    conflicts: tuple[str, ...]  # артикулы с разными группами в файле: пропущены


@dataclass(frozen=True, slots=True)
class _Stored:
    row_id: int
    article: str
    code_1c: str | None
    active: bool


@dataclass(slots=True)
class _Renames:
    articles: dict[int, str] = dataclasses.field(default_factory=dict)  # id строки → артикул
    renamed: list[tuple[str, str]] = dataclasses.field(default_factory=list)
    cleared: list[int] = dataclasses.field(default_factory=list)  # id строк, где стереть код
    conflicts: list[tuple[str, str, str]] = dataclasses.field(default_factory=list)


async def import_distr(
    session: AsyncSession,
    items: Sequence[DistrItem],
    author: str,
    file_name: str,
    *,
    stamp: FileStamp | None = None,
) -> DistrImport:
    if not items:
        raise ImportRejectedError("в файле нет ни одного товара, каталог не изменён")
    by_article: dict[str, DistrItem] = {}
    for item in items:
        by_article.setdefault(item.article, item)
    unique, duplicate_codes = _first_code_wins(by_article.values())
    counts = Counter(item.article for item in items)

    connection = await session.connection()
    query = select(Product.id, Product.article, Product.code_1c, Product.active)
    stored = [
        _Stored(row.id, row.article, row.code_1c, row.active)
        for row in await connection.execute(query)
    ]
    plan = _plan_renames(stored, unique)
    await _apply_renames(connection, plan)
    await connection.execute(update(Product).values(active=False))
    for has_group, updated in ((True, _UPDATED), (False, _KEEP_GROUP)):
        chosen = [_values(i) for i in unique if (i.price_group is not None) == has_group]
        if chosen:
            await connection.execute(_upsert(updated), chosen)

    # Артикулы строк до загрузки, но уже с учётом переименований.
    before = {plan.articles.get(s.row_id, s.article): s.active for s in stored}
    articles = {item.article for item in unique}
    known = set((await load_price_settings(session)).groups)
    result = DistrImport(
        total=len(unique),
        added=len(articles - before.keys()),
        deactivated=sum(1 for a, active in before.items() if active and a not in articles),
        duplicates=tuple(article for article, n in counts.items() if n > 1),
        unknown_groups=tuple(
            sorted({i.price_group for i in unique if i.price_group is not None} - known)
        ),
        renamed=tuple(plan.renamed),
        rename_conflicts=tuple(plan.conflicts),
        duplicate_codes=duplicate_codes,
    )
    await log_import(
        session,
        source=DISTR,
        file_name=file_name,
        author=author,
        total=result.total,
        added=result.added,
        deactivated=result.deactivated,
        stamp=stamp,
    )
    return result


async def update_price_groups(
    session: AsyncSession, rows: Sequence[NomenclatureRow]
) -> GroupsUpdate:
    """Ценовые группы товаров из справочника номенклатуры 1С. Меняется только price_group."""
    found: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        found[row.article].add(row.price_group)
    known = set((await load_price_settings(session)).groups)
    wanted = {a: next(iter(g)) for a, g in found.items() if len(g) == 1 and g <= known}

    connection = await session.connection()
    result = await connection.execute(select(Product.article, Product.price_group, Product.active))
    catalog = {row.article: row for row in result}
    changes = [
        {"b_article": a, "b_group": g}
        for a, g in wanted.items()
        if a in catalog and catalog[a].price_group != g
    ]
    if changes:
        await connection.execute(
            update(Product)
            .where(Product.article == bindparam("b_article"))
            .values(price_group=bindparam("b_group")),
            changes,
        )
    return GroupsUpdate(
        changed=len(changes),
        not_in_catalog=tuple(sorted(found.keys() - catalog.keys())),
        not_in_file=tuple(sorted(a for a, r in catalog.items() if r.active and a not in found)),
        unknown_groups=tuple(sorted({g for gs in found.values() for g in gs} - known)),
        conflicts=tuple(sorted(a for a, g in found.items() if len(g) > 1)),
    )


def _first_code_wins(items: Iterable[DistrItem]) -> tuple[list[DistrItem], tuple[str, ...]]:
    """Код 1С уникален: при повторе он остаётся у первого товара, у остальных код пустой."""
    result: list[DistrItem] = []
    seen: set[str] = set()
    repeated: dict[str, None] = {}
    for item in items:
        if item.code_1c is not None and item.code_1c in seen:
            repeated[item.code_1c] = None
            result.append(dataclasses.replace(item, code_1c=None))
            continue
        if item.code_1c is not None:
            seen.add(item.code_1c)
        result.append(item)
    return result, tuple(repeated)


def _plan_renames(stored: Sequence[_Stored], items: Iterable[DistrItem]) -> _Renames:
    by_code = {s.code_1c: s for s in stored if s.code_1c is not None}
    taken = {s.article for s in stored}
    plan = _Renames()
    for item in items:
        code = item.code_1c
        if code is None:
            continue
        row = by_code.get(code)
        if row is None or row.article == item.article:
            continue
        if item.article in taken:
            plan.cleared.append(row.row_id)
            plan.conflicts.append((code, row.article, item.article))
        else:
            plan.articles[row.row_id] = item.article
            plan.renamed.append((row.article, item.article))
    return plan


async def _apply_renames(connection: AsyncConnection, plan: _Renames) -> None:
    """До загрузки товаров: иначе код 1С или артикул на время окажется у двух строк."""
    if plan.cleared:
        await connection.execute(
            update(Product).where(Product.id.in_(plan.cleared)).values(code_1c=None)
        )
    if plan.articles:
        await connection.execute(
            update(Product)
            .where(Product.id == bindparam("b_id"))
            .values(article=bindparam("b_article")),
            [{"b_id": i, "b_article": a} for i, a in plan.articles.items()],
        )


def _upsert(updated: Sequence[str]) -> Insert:
    stmt = insert(Product)
    return stmt.on_conflict_do_update(
        index_elements=[Product.article],
        set_={name: stmt.excluded[name] for name in updated},
    )


def _values(item: DistrItem) -> dict[str, Any]:
    # psycopg превращает в массив PostgreSQL только list, не tuple.
    return dataclasses.asdict(item) | {
        "extra_photos": list(item.extra_photos),
        "price_group": item.price_group or DEFAULT_GROUP,
        "active": True,
    }
