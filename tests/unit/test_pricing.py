from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.errors import InvalidPriceRuleError
from app.domain.pricing import (
    BaseColumn,
    BasePrices,
    PriceIssue,
    PriceResult,
    PriceRule,
    PriceType,
    calc_price,
    parse_formula,
    prices_ordered,
)

PRICES = BasePrices(distr=Decimal(1000), dealer=Decimal(1200), retail=Decimal("1500.10"))


def test_factor_and_half_up_rounding() -> None:
    retail_95 = PriceType("Розница_5", PriceRule(BaseColumn.RETAIL, Decimal("0.95")))
    assert calc_price(retail_95, PRICES) == PriceResult(Decimal("1425.10"))  # 1425.095


def test_zero_decimals_rounds_half_up() -> None:
    half = PriceType("Опт", PriceRule(BaseColumn.DISTR, Decimal("0.5")), decimals=0)
    assert calc_price(half, BasePrices(Decimal(1001), None, None)).value == Decimal(501)


def test_group_rules() -> None:
    dealer = PriceType(
        "Дилер",
        PriceRule(BaseColumn.DEALER),
        group_rules={
            "РУБ": PriceRule(BaseColumn.DISTR, Decimal("1.1")),
            "Расходка": PriceRule(BaseColumn.RETAIL),
        },
    )
    assert calc_price(dealer, PRICES, "Расходка").value == Decimal("1500.10")
    assert calc_price(dealer, PRICES, None).value == Decimal("1100.00")  # нет группы → РУБ
    assert calc_price(dealer, PRICES, "Другая").value == Decimal("1200.00")


def test_missing_base_and_type() -> None:
    prices = BasePrices(None, Decimal(0), Decimal(10))
    no_price = PriceResult(None, PriceIssue.NO_BASE_PRICE)
    assert calc_price(PriceType("Д", PriceRule(BaseColumn.DEALER)), prices) == no_price
    assert calc_price(PriceType("Р", PriceRule(BaseColumn.DISTR)), prices) == no_price
    assert calc_price(None, prices) == PriceResult(None, PriceIssue.TYPE_NOT_CONFIGURED)


@pytest.mark.parametrize("factor", ["0", "-1", "NaN"])
def test_invalid_factor(factor: str) -> None:
    with pytest.raises(InvalidPriceRuleError):
        PriceRule(BaseColumn.RETAIL, Decimal(factor))


@pytest.mark.parametrize("decimals", [-1, 5])
def test_invalid_decimals(decimals: int) -> None:
    with pytest.raises(InvalidPriceRuleError):
        PriceType("t", PriceRule(BaseColumn.RETAIL), decimals=decimals)


@pytest.mark.parametrize(
    ("text", "label", "base", "factor"),
    [
        ("[Розничные] * 0.95", None, BaseColumn.RETAIL, Decimal("0.95")),
        ("[Дилерская]", None, BaseColumn.DEALER, Decimal(1)),
        ("Расходка: [Розничные]", "Расходка", BaseColumn.RETAIL, Decimal(1)),
        ("[Дистрибьюторская]*1,1", None, BaseColumn.DISTR, Decimal("1.1")),
    ],
)
def test_parse_formula(text: str, label: str | None, base: BaseColumn, factor: Decimal) -> None:
    part = parse_formula(text)
    assert part.label == label
    assert part.rule == PriceRule(base, factor)


@pytest.mark.parametrize(
    "text", ["[Оптовая] * 2", "Розничные * 2", "[Розничные] + 100", "[Розничные] * 0"]
)
def test_parse_formula_rejects(text: str) -> None:
    with pytest.raises(InvalidPriceRuleError):
        parse_formula(text)


def test_prices_ordered() -> None:
    assert prices_ordered(PRICES)
    assert prices_ordered(BasePrices(None, Decimal(5), Decimal(20)))
    assert not prices_ordered(BasePrices(Decimal(10), Decimal(5), Decimal(20)))


@given(
    base=st.decimals(min_value=Decimal("0.01"), max_value=Decimal(10**7), places=2),
    factor=st.decimals(min_value=Decimal("0.01"), max_value=Decimal(10), places=4),
    decimals=st.integers(min_value=0, max_value=4),
)
def test_price_is_non_negative_and_rounded(base: Decimal, factor: Decimal, decimals: int) -> None:
    price_type = PriceType("t", PriceRule(BaseColumn.RETAIL, factor), decimals=decimals)
    value = calc_price(price_type, BasePrices(None, None, base)).value
    quantum = Decimal(1).scaleb(-decimals)
    assert value is not None
    assert value >= 0
    assert value == value.quantize(quantum)
    assert abs(value - base * factor) <= quantum / 2
