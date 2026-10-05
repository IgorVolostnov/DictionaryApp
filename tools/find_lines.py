"""Поиск наименований по каталогу и словарю (только чтение).

Запуск: uv run python -m tools.find_lines [input/строки.txt]
В файле одно наименование на строку, без количества. Без файла выводятся только
ключи, которые ведут к нескольким активным товарам.
"""

from __future__ import annotations

import asyncio
import sys
from collections import Counter
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import DatabaseSettings
from app.db.search import load_search_index
from app.domain.search import LineMatch, Status

LABELS = {
    Status.FOUND: "найден",
    Status.AMBIGUOUS: "несколько",
    Status.INACTIVE: "снят",
    Status.NOT_FOUND: "не найден",
}


def describe(match: LineMatch) -> str:
    found = "; ".join(f"{c.item.article} ({', '.join(c.via)})" for c in match.candidates)
    return f"[{LABELS[match.status]}] {match.text} → {found or '—'}"


async def main(path: Path | None) -> None:
    engine = create_async_engine(DatabaseSettings().database_url)
    try:
        async with AsyncSession(engine) as session:
            index = await load_search_index(session)
    finally:
        await engine.dispose()
    shared = index.shared_keys()
    print(f"ключей, ведущих к нескольким активным товарам: {len(shared)}")
    for key, articles in list(shared.items())[:20]:
        print(f"   {key}: {', '.join(articles)}")
    if path is None:
        return
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    matches = [index.find(line.strip()) for line in lines if line.strip()]
    for match in matches:
        print(describe(match))
    counts = Counter(match.status for match in matches)
    print(", ".join(f"{LABELS[status]}: {counts[status]}" for status in Status))


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1]) if len(sys.argv) > 1 else None))
