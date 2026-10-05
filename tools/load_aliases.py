"""Перенос словаря из Access в базу из DATABASE_URL.

Запуск: uv run python -m tools.load_aliases input/ОбщаяНоменклатура.xlsx
Повторный запуск заменяет ключи из Access, ключи менеджеров не трогает.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import DatabaseSettings
from app.db.aliases import import_access_aliases
from app.db.imports import ImportRejectedError
from app.sources.access_catalog import read_access_catalog


async def main(path: Path) -> None:
    loaded = read_access_catalog(path)
    print("строк с ошибками:", len(loaded.problems))
    for problem in loaded.problems[:10]:
        print("  ", problem)
    engine = create_async_engine(DatabaseSettings().database_url)
    try:
        async with AsyncSession(engine) as session, session.begin():
            result = await import_access_aliases(session, loaded.items, "cli", path.name)
    except ImportRejectedError as exc:
        sys.exit(f"не загружено: {exc}")
    finally:
        await engine.dispose()
    print(f"ключей в базе: {result.total}, новых: {result.added}, удалено: {result.removed}")
    print("общих ключей (не перенесены):", result.shared)
    print(
        f"товаров Access нет в каталоге: {len(result.not_found)}, их ключей: {result.lost_keys}",
        result.not_found[:20],
    )
    print(f"ключей нельзя сохранить: {len(result.invalid)}", result.invalid[:20])


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1])))
