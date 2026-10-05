"""Загрузка distr.xlsx в базу из DATABASE_URL.

Запуск: uv run python -m tools.load_distr input/distr.xlsx
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import DatabaseSettings
from app.db.products import import_distr
from app.sources.distr import read_distr


async def main(path: Path) -> None:
    loaded = read_distr(path)
    print("строк с ошибками:", len(loaded.problems))
    for problem in loaded.problems[:10]:
        print("  ", problem)
    engine = create_async_engine(DatabaseSettings().database_url)
    try:
        async with AsyncSession(engine) as session, session.begin():
            result = await import_distr(session, loaded.items, "cli", path.name)
    finally:
        await engine.dispose()
    print(f"товаров: {result.total}, новых: {result.added}, снято: {result.deactivated}")
    print("повторы артикулов:", result.duplicates)
    print("повторы кодов 1С (код оставлен у первого товара):", result.duplicate_codes)
    print("ценовые группы не из справочника:", result.unknown_groups)
    print("переименовано по коду 1С:", len(result.renamed))
    for old, new in result.renamed:
        print(f"   {old} → {new}")
    print("конфликты переименования:", len(result.rename_conflicts))
    for code, old, new in result.rename_conflicts:
        print(f"   {code}: был у {old}, в файле у {new} (занят); синонимы остались у {old}")


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1])))
