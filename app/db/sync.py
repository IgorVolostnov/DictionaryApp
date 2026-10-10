"""Импорт выгрузок 1С по таймеру: каталог (distr.xlsx) и покупатели (price_user.csv).

1С обновляет файлы примерно раз в час, но не в одно и то же время. Поэтому таймер
запускает импорт часто, а каждый запуск сам решает, есть ли что загружать:

* файл недоступен (сетевая папка не подключилась) — MISSING;
* время изменения то же, что у последней загрузки, — UNCHANGED, файл не читается;
* файл изменён меньше quiet_seconds назад или менялся во время копирования — NOT_READY:
  1С, возможно, ещё пишет его, загрузит следующий запуск;
* содержимое то же (sha256) — UNCHANGED, запоминается новое время файла;
* иначе загружается копия. Не загружается (REJECTED), если файл не читается
  или пропадает слишком много активных строк (ensure_small_drop).

Один источник загружается только одним процессом: блокировка PostgreSQL до конца
транзакции (lock_name). Транзакцией управляет вызывающий код: одна на источник.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Final

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import SourceSettings
from app.db.customers import CUSTOMERS, import_customers
from app.db.imports import FileStamp, ImportRejectedError, ensure_small_drop
from app.db.models import Customer, Product, SourceImport
from app.db.products import DISTR, import_distr
from app.sources.cells import SourceFormatError
from app.sources.customers import read_price_users
from app.sources.distr import read_distr
from app.sources.snapshot import file_state, take_snapshot

AUTHOR: Final = "таймер"
SOURCES: Final = (DISTR, CUSTOMERS)


class Outcome(StrEnum):
    IMPORTED = "загружен"
    UNCHANGED = "не изменился"
    NOT_READY = "1С ещё пишет файл"
    MISSING = "файл недоступен"
    BUSY = "уже загружается"
    REJECTED = "отклонён"


@dataclass(frozen=True, slots=True)
class SyncResult:
    outcome: Outcome
    message: str = ""


@dataclass(frozen=True, slots=True)
class _Change:
    before: int  # активных строк до загрузки
    lost: int  # из них пропало
    summary: str


_Loader = Callable[[AsyncSession, Path, FileStamp], Awaitable[_Change]]


def lock_name(source: str) -> str:
    """Имя блокировки. Загрузка из админки должна брать ту же."""
    return f"import:{source}"


async def _load_distr(session: AsyncSession, path: Path, stamp: FileStamp) -> _Change:
    loaded = read_distr(path)
    active = select(func.count()).select_from(Product).where(Product.active)
    before = await session.scalar(active) or 0
    result = await import_distr(session, loaded.items, AUTHOR, path.name, stamp=stamp)
    summary = (
        f"товаров {result.total}, новых {result.added}, снято {result.deactivated}, "
        f"строк с ошибками {len(loaded.problems)}"
    )
    return _Change(before, result.deactivated, summary)


async def _load_customers(session: AsyncSession, path: Path, stamp: FileStamp) -> _Change:
    loaded = read_price_users(path)
    before = await session.scalar(select(func.count()).select_from(Customer)) or 0
    result = await import_customers(session, loaded.items, AUTHOR, path.name, stamp=stamp)
    summary = (
        f"покупателей {result.total}, новых {result.added}, пропало {result.removed}, "
        f"строк с ошибками {len(loaded.problems)}"
    )
    return _Change(before, result.removed, summary)


_LOADERS: Final[dict[str, _Loader]] = {DISTR: _load_distr, CUSTOMERS: _load_customers}


async def sync_source(
    session: AsyncSession,
    source: str,
    settings: SourceSettings,
    now: datetime,
    *,
    force: bool = False,
) -> SyncResult:
    """force: загрузить, даже если пропадает много строк (решение администратора)."""
    path = {DISTR: settings.distr_path, CUSTOMERS: settings.customers_path}[source]
    lock = select(func.pg_try_advisory_xact_lock(func.hashtext(lock_name(source))))
    if not await session.scalar(lock):
        return SyncResult(Outcome.BUSY)
    last = await _last_import(session, source)
    try:
        state = file_state(path)
        if last is not None and last.source_mtime == state.mtime:
            return SyncResult(Outcome.UNCHANGED)
        quiet = timedelta(seconds=settings.quiet_seconds)
        snap = take_snapshot(path, settings.snapshot_dir / source, quiet=quiet, now=now)
    except OSError as exc:
        return SyncResult(Outcome.MISSING, str(exc))
    if snap is None:
        return SyncResult(Outcome.NOT_READY)
    if last is not None and last.sha256 == snap.sha256:
        last.source_mtime = snap.mtime
        await session.flush()
        return SyncResult(Outcome.UNCHANGED, "1С переписала файл без изменений")
    max_percent = 100 if force else settings.max_drop_percent
    try:
        async with session.begin_nested():
            change = await _LOADERS[source](session, snap.path, FileStamp(snap.sha256, snap.mtime))
            ensure_small_drop(change.before, change.lost, max_percent)
    except (SourceFormatError, ImportRejectedError) as exc:
        return SyncResult(Outcome.REJECTED, str(exc))
    return SyncResult(Outcome.IMPORTED, change.summary)


async def _last_import(session: AsyncSession, source: str) -> SourceImport | None:
    return await session.scalar(
        select(SourceImport)
        .where(SourceImport.source == source)
        .order_by(SourceImport.id.desc())
        .limit(1)
    )
