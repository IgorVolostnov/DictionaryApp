"""Общее для загрузки выгрузок в базу."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SourceImport


class ImportRejectedError(ValueError):
    """Выгрузка не загружена, данные в базе не изменились."""


async def log_import(
    session: AsyncSession,
    *,
    source: str,
    file_name: str,
    author: str,
    total: int,
    added: int,
    deactivated: int,
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
        )
    )
    await session.flush()
