"""Разбор вставленной заявки: строки «наименование + количество».

Два режима:
* таблица (есть табуляции, то есть вставка из Excel): колонки угадываются,
  менеджер может указать их вручную;
* свободный текст (письмо, мессенджер): количество берётся из конца строки,
  только если оно явно помечено: «5 шт», «x5», «- 5», «; 5». Голое число
  в конце («Головка 10») считается частью наименования: лучше переспросить,
  чем отправить в 1С размер вместо количества.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from app.domain.errors import InvalidInputError

QTY_MAX: Final = Decimal(100_000)  # больше — почти наверняка штрихкод или цена

_UNIT: Final = r"(?:шт|штук[аи]?|ед|компл|pcs|pc)\.?"
_MULT: Final = r"[xх×*]"  # латинская x, кириллическая х, знак умножения, звёздочка
_CELL_QTY: Final = re.compile(
    rf"(?:{_MULT}\s*)?"
    r"(?P<num>(?:[0-9]{1,3}(?:[ \u00a0\u202f][0-9]{3})+|[0-9]+)(?:[.,][0-9]{1,3})?)"
    rf"\s*(?:{_UNIT})?",
    re.IGNORECASE,
)
_TAIL_QTY: Final = re.compile(
    r"(?P<name>.*?\S)"
    r"(?P<sep>\s*;\s*|\s+[-–—]\s+|\s+)"
    rf"(?P<mult>{_MULT}\s*)?"
    r"(?P<num>[0-9]+(?:[.,][0-9]{1,3})?)"
    rf"\s*(?P<unit>{_UNIT})?",
    re.IGNORECASE,
)
_GROUP_SEPARATORS: Final = re.compile(r"[ \u00a0\u202f]")
_NUMBERISH: Final = re.compile(r"[0-9\s.,+\-]+")
_HEADER_SPLIT: Final = re.compile(r"[\s/|\x5c]+")
_NON_LETTERS: Final = re.compile(r"[^a-zа-яё]")
_HEADER_WORDS: Final = frozenset({
    "наименование", "наим", "номенклатура", "товар", "товара", "товары", "позиция",
    "описание", "артикул", "код", "п", "пп", "колво", "кол", "количество", "ед", "изм",
    "едизм", "шт", "цена", "руб", "сумма", "стоимость",
    "name", "item", "article", "qty", "quantity", "price", "no",
})  # fmt: skip


@dataclass(frozen=True, slots=True)
class InputRow:
    line_no: int  # номер строки во вставленном тексте, с 1
    name: str
    quantity: Decimal | None  # None — количество не найдено, экспорт заблокирован


@dataclass(frozen=True, slots=True)
class ParsedInput:
    rows: tuple[InputRow, ...]
    column_count: int
    name_col: int
    qty_col: int | None
    header_skipped: bool


def _make_quantity(number: str) -> Decimal | None:
    value = Decimal(number.replace(",", "."))
    return value if 0 < value <= QTY_MAX else None


def parse_quantity(cell: str) -> Decimal | None:
    match = _CELL_QTY.fullmatch(cell.strip())
    if match is None:
        return None
    return _make_quantity(_GROUP_SEPARATORS.sub("", match["num"]))


def _cells(line: str) -> list[str]:
    cells = [cell.strip() for cell in line.split("\t")]
    while cells and not cells[-1]:
        cells.pop()
    return cells


def _is_header(cells: list[str]) -> bool:
    words = [
        word
        for cell in cells
        for token in _HEADER_SPLIT.split(cell.casefold())
        if (word := _NON_LETTERS.sub("", token))
    ]
    return bool(words) and all(word in _HEADER_WORDS for word in words)


def _free_text_row(line_no: int, line: str) -> InputRow:
    match = _TAIL_QTY.fullmatch(line)
    if match is not None and (match["mult"] or match["unit"] or match["sep"].strip()):
        qty = _make_quantity(match["num"])
        if qty is not None:
            return InputRow(line_no, match["name"], qty)
    return InputRow(line_no, line, None)


def _guess_columns(table: list[list[str]]) -> tuple[int, int | None]:
    count = max(len(cells) for cells in table)
    text_len, filled, qty_hits = [0] * count, [0] * count, [0] * count
    for cells in table:
        for i, cell in enumerate(cells):
            if not cell:
                continue
            filled[i] += 1
            if parse_quantity(cell) is not None:
                qty_hits[i] += 1
            elif not _NUMBERISH.fullmatch(cell):
                text_len[i] += len(cell)
    # Наименование — колонка с самым длинным текстом (артикулы короче названий).
    name_col = max(range(count), key=lambda i: (text_len[i], -i))
    candidates = [
        i for i in range(count) if i != name_col and filled[i] and 2 * qty_hits[i] >= filled[i]
    ]
    right = [i for i in candidates if i > name_col]
    if right:  # обычно «Наименование | Кол-во | Цена»: берём ближайшую справа
        return name_col, right[0]
    return name_col, (candidates[-1] if candidates else None)


def _check_columns(name_col: int | None, qty_col: int | None, count: int) -> None:
    for label, col in (("наименования", name_col), ("количества", qty_col)):
        if col is not None and not 0 <= col < count:
            raise InvalidInputError(
                f"Колонка {label} №{col + 1} вне таблицы: в ней {count} колонок."
            )
    if name_col is not None and name_col == qty_col:
        raise InvalidInputError("Наименование и количество не могут быть в одной колонке.")


def _qty_at(cells: list[str], col: int | None) -> Decimal | None:
    if col is None or col >= len(cells):
        return None
    return parse_quantity(cells[col])


def parse_input(
    text: str, *, name_col: int | None = None, qty_col: int | None = None
) -> ParsedInput:
    table = [
        (no, _cells(line)) for no, line in enumerate(text.splitlines(), start=1) if line.strip()
    ]
    header_skipped = bool(table) and _is_header(table[0][1])
    if header_skipped:
        table = table[1:]
    if not table:
        return ParsedInput((), 0, 0, None, header_skipped)

    column_count = max(len(cells) for _, cells in table)
    _check_columns(name_col, qty_col, column_count)
    if column_count == 1:
        rows = tuple(_free_text_row(no, cells[0]) for no, cells in table)
        return ParsedInput(rows, 1, 0, None, header_skipped)

    guessed_name, guessed_qty = _guess_columns([cells for _, cells in table])
    n = guessed_name if name_col is None else name_col
    q = qty_col if qty_col is not None else (guessed_qty if guessed_qty != n else None)
    rows = tuple(
        InputRow(no, cells[n], _qty_at(cells, q))
        for no, cells in table
        if n < len(cells) and cells[n]
    )
    return ParsedInput(rows, column_count, n, q, header_skipped)
