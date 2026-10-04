"""Загрузка справочника ценовых групп и описания видов цен в базу из DATABASE_URL.

Запуск: uv run python -m tools.load_prices input/ЦеновыеГруппы.xlsx input/price_types.txt
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import DatabaseSettings
from app.db.prices import save_price_groups, save_price_types
from app.domain.errors import InvalidPriceRuleError
from app.sources.price_groups import read_price_groups


async def main(groups_path: Path, types_path: Path) -> None:
    groups = read_price_groups(groups_path)
    for problem in groups.problems:
        print("  ", problem)
    text = types_path.read_text(encoding="utf-8-sig")
    engine = create_async_engine(DatabaseSettings().database_url)
    try:
        # Одна транзакция: при ошибке в описании не сохранится и справочник.
        async with AsyncSession(engine) as session, session.begin():
            names = await save_price_groups(session, groups.items, "cli")
            types = await save_price_types(session, text, "cli")
    except InvalidPriceRuleError as exc:
        sys.exit(f"не сохранено: {exc}")
    finally:
        await engine.dispose()
    print(f"ценовых групп: {len(names)}, замечаний: {len(groups.problems)}")
    print("видов цен:", len(types))
    for t in types.values():
        extra = {g: f"[{r.base}] * {r.factor}" for g, r in t.group_rules.items()}
        print(f"  {t.name}: [{t.rule.base}] * {t.rule.factor}", extra or "")


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1]), Path(sys.argv[2])))
