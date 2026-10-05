"""Справочник номенклатуры из 1С: ценовая группа товара по артикулу.

Нужен, пока в distr.xlsx нет колонки «ЦеноваяГруппа». Остальные колонки не читаются.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from app.domain.pricing import DEFAULT_GROUP
from app.sources.cells import Loaded, Record, load, xlsx_rows

COLUMNS: Final = ("Артикул", "ЦеноваяГруппа")


@dataclass(frozen=True, slots=True)
class NomenclatureRow:
    article: str
    price_group: str


def read_nomenclature(path: Path) -> Loaded[NomenclatureRow]:
    return load(xlsx_rows(path), COLUMNS, _row)


def _row(row: Record) -> NomenclatureRow:
    group = row.text("ЦеноваяГруппа")
    # Пустая группа в 1С — основная формула вида цены, то есть РУБ.
    return NomenclatureRow(
        row.required("Артикул"), " ".join(group.split()) if group else DEFAULT_GROUP
    )
