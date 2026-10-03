from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.errors import InvalidInputError
from app.domain.parse_input import InputRow, parse_input, parse_quantity


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("10", Decimal(10)), ("1 000", Decimal(1000)), ("1\u00a0000", Decimal(1000)),
        ("10,5", Decimal("10.5")), ("10.5", Decimal("10.5")), ("10 шт.", Decimal(10)),
        ("10шт", Decimal(10)), ("x10", Decimal(10)), ("х10", Decimal(10)),
        ("× 3", Decimal(3)), ("5 компл", Decimal(5)), ("  7  ", Decimal(7)),
    ],
)  # fmt: skip
def test_quantity_accepted(cell: str, expected: Decimal) -> None:
    assert parse_quantity(cell) == expected


@pytest.mark.parametrize(
    "cell",
    ["", "0", "0,0", "-5", "abc", "R-10", "10 мм", "4657810321250", "100001", "1 00", "10,1234"],
)
def test_quantity_rejected(cell: str) -> None:
    assert parse_quantity(cell) is None


@pytest.mark.parametrize(
    ("line", "name", "qty"),
    [
        ("Ключ 17 мм 5 шт", "Ключ 17 мм", Decimal(5)),
        ("Насадка - 5", "Насадка", Decimal(5)),
        ("Насадка; 2,5", "Насадка", Decimal("2.5")),
        ("R-10 x10", "R-10", Decimal(10)),
        ("Ключ 5 шт\t", "Ключ", Decimal(5)),
        ("Головка 10", "Головка 10", None),  # голое число может быть размером
        ("Хомут 0 шт", "Хомут 0 шт", None),
        ("Ключ", "Ключ", None),
    ],
)
def test_free_text(line: str, name: str, qty: Decimal | None) -> None:
    parsed = parse_input(line)
    assert parsed.rows == (InputRow(1, name, qty),)
    assert parsed.column_count == 1


def test_free_text_header_skipped() -> None:
    parsed = parse_input("Наименование / Кол-во\nКлюч 5 шт")
    assert parsed.header_skipped
    assert parsed.rows == (InputRow(2, "Ключ", Decimal(5)),)


def test_table_guesses_columns() -> None:
    text = "№\tНаименование\tКол-во\tЦена\n1\tКлюч 17 мм\t5\t1 855\n2\tНасадка\t\t300\n"
    parsed = parse_input(text)
    assert parsed.header_skipped
    assert (parsed.name_col, parsed.qty_col) == (1, 2)
    assert parsed.rows == (InputRow(2, "Ключ 17 мм", Decimal(5)), InputRow(3, "Насадка", None))


def test_quantity_column_left_of_name() -> None:
    parsed = parse_input("5\tКлюч\n2\tНасадка")
    assert (parsed.name_col, parsed.qty_col) == (1, 0)


def test_barcode_column_is_not_quantity() -> None:
    parsed = parse_input("Ключ\t4657810321250\nНасадка\t4657810321251")
    assert (parsed.name_col, parsed.qty_col) == (0, None)
    assert parsed.rows[0] == InputRow(1, "Ключ", None)


def test_explicit_columns() -> None:
    parsed = parse_input("Ключ\t3\t5", name_col=0, qty_col=2)
    assert parsed.rows == (InputRow(1, "Ключ", Decimal(5)),)


def test_explicit_name_drops_conflicting_guess() -> None:
    assert parse_input("5\tКлюч", name_col=0).qty_col is None


def test_short_rows() -> None:
    assert parse_input("Ключ\t5\nНасадка").rows == (
        InputRow(1, "Ключ", Decimal(5)),
        InputRow(2, "Насадка", None),
    )
    assert parse_input("5\tКлюч\n3").rows == (InputRow(1, "Ключ", Decimal(5)),)


@pytest.mark.parametrize(
    "kwargs", [{"name_col": 5}, {"qty_col": -1}, {"name_col": 0, "qty_col": 0}]
)
def test_invalid_columns(kwargs: dict[str, int]) -> None:
    with pytest.raises(InvalidInputError):
        parse_input("Ключ\t5", **kwargs)


def test_empty_and_header_only() -> None:
    assert parse_input("\n  \n").rows == ()
    header_only = parse_input("Наименование\tКол-во")
    assert header_only.rows == ()
    assert header_only.header_skipped


def test_header_with_backslash_skipped() -> None:
    parsed = parse_input("Наименование" + chr(92) + "Кол-во\nКлюч 5 шт")
    assert parsed.header_skipped
    assert parsed.rows == (InputRow(2, "Ключ", Decimal(5)),)
