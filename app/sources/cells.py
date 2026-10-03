"""Общее для чтения выгрузок: колонки по заголовкам, текст и числа из ячеек."""

from __future__ import annotations

import zipfile
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Final

import openpyxl
from openpyxl.utils.exceptions import InvalidFileException

from app.domain.normalize import normalize_key

# Access при экспорте в Excel пишет пустое текстовое поле строкой «None».
_EMPTY: Final = frozenset({"", "None"})
# Разделители тысяч: обычный, неразрывный и узкий неразрывный пробелы.
_THOUSANDS: Final = str.maketrans("", "", " \u00a0\u202f")


class SourceFormatError(ValueError):
    """Файл не похож на ожидаемую выгрузку: не открывается, пустой, нет колонок."""


@dataclass(frozen=True)
class Loaded[T]:
    """Прочитанные строки и замечания по строкам, которые пришлось пропустить."""

    items: tuple[T, ...]
    problems: tuple[str, ...]


def cell_text(value: object) -> str | None:
    """Текст ячейки без пробелов по краям; пустая ячейка → None."""
    if value is None:
        return None
    text = str(value).strip()
    return None if text in _EMPTY else text


def cell_decimal(value: object) -> Decimal | None:
    """Число из ячейки: 1855, «1855», «0.0018», «12 345,67». Пустая ячейка → None."""
    text = cell_text(value)
    if text is None:
        return None
    try:
        number = Decimal(text.translate(_THOUSANDS).replace(",", "."))
    except InvalidOperation:
        number = Decimal("NaN")
    if not number.is_finite():
        raise ValueError(f"«{text}»: ожидалось число")
    return number


class Record:
    """Строка выгрузки: значения по именам колонок и номер строки в файле."""

    __slots__ = ("_columns", "_values", "line")

    def __init__(self, line: int, columns: dict[str, int], values: Sequence[object]) -> None:
        self.line = line
        self._columns = columns
        self._values = values

    def __getitem__(self, column: str) -> object:
        i = self._columns[column]
        return self._values[i] if 0 <= i < len(self._values) else None

    def text(self, column: str) -> str | None:
        return cell_text(self[column])

    def required(self, column: str) -> str:
        value = self.text(column)
        if value is None:
            raise ValueError(f"пустая колонка «{column}»")
        return value

    def number(self, column: str) -> Decimal | None:
        try:
            return cell_decimal(self[column])
        except ValueError as exc:
            raise ValueError(f"«{column}»: {exc}") from None


def find_columns(
    header: Sequence[object], names: Iterable[str], optional: Iterable[str] = ()
) -> dict[str, int]:
    """Номера колонок по заголовкам; необязательным, которых нет в файле, достаётся -1.

    Заголовки сравниваются через normalize_key: пробелы, знаки и латинские
    буквы-двойники не важны (в distr.xlsx в заголовке «Бренд» стоит латинская e).
    """
    positions: dict[str, int] = {}
    for i, cell in enumerate(header):
        title = cell_text(cell)
        if title is not None:
            positions.setdefault(normalize_key(title), i)
    columns = {name: positions.get(normalize_key(name), -1) for name in names}
    missing = [name for name, i in columns.items() if i < 0]
    if missing:
        raise SourceFormatError("Отсутствуют колонки: " + ", ".join(missing))
    return columns | {name: positions.get(normalize_key(name), -1) for name in optional}


def _records(
    rows: Iterable[Sequence[object]], names: Iterable[str], optional: Iterable[str]
) -> Iterator[Record]:
    """Строки данных; первая строка — заголовки, пустые строки пропускаются."""
    it = iter(rows)
    header = next(it, None)
    if header is None:
        raise SourceFormatError("Файл пустой: нет строки заголовков.")
    columns = find_columns(header, names, optional)
    for line, values in enumerate(it, start=2):
        if any(cell_text(value) is not None for value in values):
            yield Record(line, columns, values)


def load[T](
    rows: Iterable[Sequence[object]],
    names: Iterable[str],
    parse: Callable[[Record], T],
    optional: Iterable[str] = (),
) -> Loaded[T]:
    """Разбирает строки: ошибочные попадают в problems, остальные — в items."""
    items: list[T] = []
    problems: list[str] = []
    for row in _records(rows, names, optional):
        try:
            items.append(parse(row))
        except ValueError as exc:
            problems.append(f"строка {row.line}: {exc}")
    return Loaded(tuple(items), tuple(problems))


def xlsx_rows(path: Path) -> list[tuple[object, ...]]:
    """Все строки первого листа. Файл закрывается сразу после чтения."""
    try:
        book: Any = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except (zipfile.BadZipFile, InvalidFileException) as exc:
        raise SourceFormatError(f"{path.name}: ошибка открытия xlsx ({exc})") from exc
    try:
        sheet = book.worksheets[0]
        sheet.reset_dimensions()
        return [tuple(row) for row in sheet.iter_rows(values_only=True)]
    finally:
        book.close()
