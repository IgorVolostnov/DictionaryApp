"""Таблица «ОбщаяНоменклатура» из НоменклатураАлькар.accdb, выгруженная в xlsx.

Нужна для переноса словаря и сверки правил видов цен с готовыми колонками.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from app.domain.normalize import strip_invisible
from app.sources.cells import Loaded, Record, load, xlsx_rows

COLUMNS: Final = (
    "КодВ1С",
    "Артикул",
    "Наименование",
    "НаименованиеПрайса",
    "Подгруппа",
    "Бренд",
    "Словарь",
)


@dataclass(frozen=True, slots=True)
class AccessProduct:
    code_1c: str | None
    article: str | None
    name: str
    price_group: str | None
    subgroup: str | None
    brand: str | None
    keys: tuple[str, ...]


def read_access_catalog(path: Path) -> Loaded[AccessProduct]:
    return load(xlsx_rows(path), COLUMNS, _product)


def _product(row: Record) -> AccessProduct:
    code_1c, article = row.text("КодВ1С"), row.text("Артикул")
    if code_1c is None and article is None:
        raise ValueError("пустые «КодВ1С» и «Артикул»")
    # Ключи берутся как есть, только без невидимых символов: повторное Преобразование
    # испортило бы их (удалило бы апостроф от мягкого знака).
    pieces = (strip_invisible(piece) for piece in (row.text("Словарь") or "").split())
    return AccessProduct(
        code_1c=code_1c,
        article=article,
        name=row.required("Наименование"),
        price_group=row.text("НаименованиеПрайса"),
        subgroup=row.text("Подгруппа"),
        brand=row.text("Бренд"),
        keys=tuple(dict.fromkeys(key for key in pieces if key)),
    )
