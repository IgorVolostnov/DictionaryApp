"""Справочник ценовых групп номенклатуры: xlsx с колонкой «ЦеноваяГруппа»."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from app.domain.pricing import DEFAULT_GROUP
from app.sources.cells import Loaded, Record, load, xlsx_rows

COLUMNS: Final = ("ЦеноваяГруппа",)


def read_price_groups(path: Path) -> Loaded[str]:
    """Названия групп без повторов; РУБ есть всегда и идёт первым."""
    loaded = load(xlsx_rows(path), COLUMNS, _group)
    return Loaded(tuple(dict.fromkeys((DEFAULT_GROUP, *loaded.items))), loaded.problems)


def _group(row: Record) -> str:
    return " ".join(row.required("ЦеноваяГруппа").split())
