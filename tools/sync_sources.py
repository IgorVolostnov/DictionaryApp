"""Импорт выгрузок 1С по таймеру (deploy/dictionary-sync.timer, каждые 5 минут).

Запуск:
  uv run python -m tools.sync_sources            каталог и покупатели
  uv run python -m tools.sync_sources --force    без защиты от массового снятия
Пути к файлам — в .env (DISTR_PATH, CUSTOMERS_PATH). Неизменившиеся файлы не печатаются.
Код выхода 1, если выгрузка отклонена или недоступна: systemd покажет сбой.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import SourceSettings
from app.db.sync import SOURCES, Outcome, sync_source

FAILED = (Outcome.REJECTED, Outcome.MISSING)


async def main(force: bool) -> int:
    settings = SourceSettings()
    engine = create_async_engine(settings.database_url)
    failed = False
    try:
        for source in SOURCES:
            async with AsyncSession(engine) as session, session.begin():
                now = datetime.now(UTC)
                result = await sync_source(session, source, settings, now, force=force)
            if result.outcome is not Outcome.UNCHANGED:
                details = f" — {result.message}" if result.message else ""
                print(f"{source}: {result.outcome}{details}")
            failed = failed or result.outcome in FAILED
    finally:
        await engine.dispose()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main("--force" in sys.argv[1:])))
