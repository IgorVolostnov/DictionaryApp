from __future__ import annotations

import re
from decimal import Decimal

import pytest

from app.domain.errors import InvalidPriceRuleError
from app.domain.price_types import parse_price_types
from app.domain.pricing import BaseColumn, PriceRule, PriceType

RETAIL, DEALER, DISTR = BaseColumn.RETAIL, BaseColumn.DEALER, BaseColumn.DISTR
GROUPS = ("РУБ", "Расходка", "Инструменты", "Грузики CLIPPER")
BASE = {c.value: PriceType(c.value, PriceRule(c)) for c in BaseColumn}

SAMPLE = """\
1. Все_5, ք: [Розничные] * 0.95
Уточнение по ценовым группам: нет
11. Розница_20_Все_10_Груз_23, ք: [Розничные] * 0.9
Ценовая группа\tФормула
Расходка\t[Розничные] * 0.8
Грузики  CLIPPER\t[Розничные] * 0.77

13. Розница_0_Расходка + 5%, ք: [Розничные] * 1
Расходка\t[Розничные] * 1.05
17. Дилер_28: [Дилерская] * 1
23. Дистр_0_Инстр, ք: [Дистрибьюторская] * 1
Расходка\t[Розничные]
Инструменты\t[Дилерская] * 0.9
"""


def test_parse_price_types() -> None:
    assert parse_price_types(SAMPLE, GROUPS) == {
        "Все_5": PriceType("Все_5", PriceRule(RETAIL, Decimal("0.95"))),
        "Розница_20_Все_10_Груз_23": PriceType(
            "Розница_20_Все_10_Груз_23",
            PriceRule(RETAIL, Decimal("0.9")),
            {
                "Расходка": PriceRule(RETAIL, Decimal("0.8")),
                "Грузики CLIPPER": PriceRule(RETAIL, Decimal("0.77")),
            },
        ),
        "Розница_0_Расходка + 5%": PriceType(
            "Розница_0_Расходка + 5%",
            PriceRule(RETAIL),
            {"Расходка": PriceRule(RETAIL, Decimal("1.05"))},
        ),
        "Дилер_28": PriceType("Дилер_28", PriceRule(DEALER)),
        "Дистр_0_Инстр": PriceType(
            "Дистр_0_Инстр",
            PriceRule(DISTR),
            {"Расходка": PriceRule(RETAIL), "Инструменты": PriceRule(DEALER, Decimal("0.9"))},
        ),
        **BASE,
    }


def test_explicit_base_type_wins() -> None:
    types = parse_price_types("1. Дилерская: [Дилерская] * 0.5", GROUPS)
    assert types["Дилерская"].rule == PriceRule(DEALER, Decimal("0.5"))


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("Цена Дилерская", "не найдено ни одного вида цены"),
        ("1. А: [Розничные]\nЦена Дилерская", "строка 2: не удалось разобрать «Цена Дилерская»"),
        ("1. А: [Розничные]\n[Дилерская]", "строка 2: не удалось разобрать «[Дилерская]»"),
        ("1. А: [Розничные]\n2. А, ք: [Дилерская]", "строка 2: вид цены «А» описан дважды"),
        (
            "1. А: [Розничные]\nРасходка [Розничные]\nРасходка [Дилерская]",
            "строка 3: ценовая группа «Расходка» указана дважды",
        ),
        (
            "1. А: [Розничные]\nРасхдка [Розничные]",
            "строка 2: ценовой группы «Расхдка» нет в справочнике",
        ),
        ("1. А: [Закупочная]", "строка 1: Неизвестная колонка цены «Закупочная»."),
        ("1. А: [Розничные] * 0", "строка 1: Коэффициент должен быть больше нуля, указано 0."),
    ],
)
def test_parse_price_types_errors(text: str, message: str) -> None:
    with pytest.raises(InvalidPriceRuleError, match=re.escape(message)):
        parse_price_types(text, GROUPS)


def test_preamble_before_first_type_is_skipped() -> None:
    preamble = (
        "Как рассчитываются типы цен контрагентов:\n"
        "\n"
        "Базовые цены берем из выгрузки: \\192.168.0.251\ftp1\\distrib\\distr.xlsx\n"
        "Цена - [Дистрибьюторская]\n"
        "Цена Дилерская - [Дилерская]\n"
        "Цена Розничная - [Розничные]\n"
    )
    assert parse_price_types(preamble + SAMPLE, GROUPS) == parse_price_types(SAMPLE, GROUPS)
