"""Поиск по заявке (только чтение).

Запуск:
  uv run python -m tools.find_lines input/заявка.txt     разбор заявки и поиск
  uv run python -m tools.find_lines > output/shared.tsv  все ключи, ведущие
                                                         к нескольким активным товарам
Заявка — как есть: текст письма или вставка из Excel (с табуляциями).
"""

from __future__ import annotations

import asyncio
import sys
from collections import Counter
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import DatabaseSettings
from app.db.search import load_search_index
from app.domain.order_match import MatchedRow, match_rows
from app.domain.parse_input import parse_input
from app.domain.search import Candidate, SearchIndex, Status

LABELS = {
    Status.FOUND: "найден",
    Status.AMBIGUOUS: "несколько",
    Status.INACTIVE: "снят",
    Status.NOT_FOUND: "не найден",
}


async def load_index() -> SearchIndex:
    engine = create_async_engine(DatabaseSettings().database_url)
    try:
        async with AsyncSession(engine) as session:
            return await load_search_index(session)
    finally:
        await engine.dispose()


def label(candidate: Candidate) -> str:
    return f"{candidate.item.article} ({', '.join(candidate.via)})"


def describe(matched: MatchedRow) -> str:
    row, match = matched.row, matched.match
    qty = "?" if row.quantity is None else str(row.quantity)
    found = "; ".join(label(c) for c in match.candidates) or "—"
    return f"{row.line_no:>3}. [{LABELS[match.status]}] {row.name} | {qty} → {found}"


def print_shared(index: SearchIndex) -> None:
    shared = index.shared_keys()
    for key, candidates in shared.items():
        print(key, *(label(c) for c in candidates), sep="\t")
    print(f"ключей, ведущих к нескольким активным товарам: {len(shared)}", file=sys.stderr)


def print_order(index: SearchIndex, path: Path) -> None:
    parsed = parse_input(path.read_text(encoding="utf-8-sig"))
    if parsed.column_count > 1:
        qty_col = "нет" if parsed.qty_col is None else f"№{parsed.qty_col + 1}"
        print(f"таблица: наименование — колонка №{parsed.name_col + 1}, количество — {qty_col}")
    rows = match_rows(parsed, index)
    for row in rows:
        print(describe(row))
    counts = Counter(row.match.status for row in rows)
    print(", ".join(f"{LABELS[status]}: {counts[status]}" for status in Status))
    ready = sum(row.ready for row in rows)
    print(f"готово к выгрузке (товар найден, количество есть): {ready} из {len(rows)}")


async def main(path: Path | None) -> None:
    index = await load_index()
    if path is None:
        print_shared(index)
    else:
        print_order(index, path)


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1]) if len(sys.argv) > 1 else None))
