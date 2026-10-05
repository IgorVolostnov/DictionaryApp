"""Общее для загрузки выгрузок в базу."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SourceImport


class ImportRejectedError(ValueError):
    """Выгрузка не загружена, данные в базе не изменились."""


@dataclass(frozen=True, slots=True)
class FileStamp:
    """Отпечаток загруженного файла: по нему таймер узнаёт, что выгрузка не менялась."""

    sha256: str
    mtime: datetime  # время изменения файла на сервере 1С


async def log_import(
    session: AsyncSession,
    *,
    source: str,
    file_name: str,
    author: str,
    total: int,
    added: int,
    deactivated: int,
    stamp: FileStamp | None = None,
) -> None:
    """Запись в журнал загрузок.

    deactivated: для товаров — снятые с каталога, для покупателей — пропавшие из выгрузки.
    """
    session.add(
        SourceImport(
            source=source,
            file_name=file_name,
            author=author,
            total=total,
            added=added,
            deactivated=deactivated,
            sha256=stamp.sha256 if stamp else None,
            source_mtime=stamp.mtime if stamp else None,
        )
    )
    await session.flush()


def ensure_small_drop(before: int, lost: int, max_percent: int) -> None:
    """Загрузка не должна за раз убрать больше max_percent процентов активных строк.

    Защита от пустого или урезанного файла из 1С: иначе с продажи снимется каталог
    или пропадут покупатели.
    """
    if lost * 100 > before * max_percent:
        raise ImportRejectedError(
            f"пропадает {lost} из {before} активных строк ({lost * 100 // max(before, 1)}%), "
            f"допустимо не больше {max_percent}%. Если выгрузка верна, загрузите её с --force"
        )
