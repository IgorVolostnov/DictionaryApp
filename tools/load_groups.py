"""Ценовые группы товаров из справочника номенклатуры 1С (пока их нет в distr.xlsx).

Запуск: uv run python -m tools.load_groups input/Номенклатура.xlsx
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import DatabaseSettings
from app.db.products import update_price_groups
from app.sources.nomenclature import read_nomenclature


async def main(path: Path) -> None:
    loaded = read_nomenclature(path)
    for problem in loaded.problems:
        print("  ", problem)
    engine = create_async_engine(DatabaseSettings().database_url)
    try:
        async with AsyncSession(engine) as session, session.begin():
            result = await update_price_groups(session, loaded.items)
    finally:
        await engine.dispose()
    print(f"строк: {len(loaded.items)}, с ошибками: {len(loaded.problems)}")
    print("группа изменилась у товаров:", result.changed)
    for title, values in (
        ("нет в каталоге", result.not_in_catalog),
        ("активные товары, которых нет в файле", result.not_in_file),
        ("группы не из справочника (строки пропущены)", result.unknown_groups),
        ("артикулы с разными группами (пропущены)", result.conflicts),
    ):
        if values:
            print(f"{title} ({len(values)}):", values[:20])


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1])))
