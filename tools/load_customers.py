"""Загрузка price_user.csv в базу из DATABASE_URL.

Запуск: uv run python -m tools.load_customers input/price_user.csv
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import DatabaseSettings
from app.db.customers import import_customers
from app.sources.customers import read_price_users


async def main(path: Path) -> None:
    loaded = read_price_users(path)
    print("строк с ошибками:", len(loaded.problems))
    for problem in loaded.problems[:10]:
        print("  ", problem)
    engine = create_async_engine(DatabaseSettings().database_url)
    try:
        async with AsyncSession(engine) as session, session.begin():
            result = await import_customers(session, loaded.items, "cli", path.name)
    finally:
        await engine.dispose()
    print(f"покупателей: {result.total}, новых: {result.added}, пропало: {result.removed}")
    print("неразличимые (одинаковые наименование и e-mail):", result.duplicates)
    print("виды цен без правила:", result.unknown_price_types)


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1])))
