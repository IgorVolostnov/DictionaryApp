"""Расчёт цены по типу цен клиента и ценовой группе товара."""

from __future__ import annotations

import itertools
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Final

from app.domain.errors import InvalidPriceRuleError

DEFAULT_GROUP: Final = "РУБ"
MAX_DECIMALS: Final = 4


class BaseColumn(StrEnum):
    DISTR = "Дистрибьюторская"  # distr.xlsx: «Цена Дистрибьюторская»
    DEALER = "Дилерская"  # distr.xlsx: «Цена Дилерская»
    RETAIL = "Розничные"  # distr.xlsx: «Цена Розничная»


class PriceIssue(StrEnum):
    TYPE_NOT_CONFIGURED = "Тип цен не настроен"
    NO_BASE_PRICE = "Нет цены"


@dataclass(frozen=True, slots=True)
class PriceRule:
    base: BaseColumn
    factor: Decimal = Decimal(1)

    def __post_init__(self) -> None:
        if not self.factor.is_finite() or self.factor <= 0:
            raise InvalidPriceRuleError(
                f"Коэффициент должен быть больше нуля, указано {self.factor}."
            )


@dataclass(frozen=True, slots=True)
class PriceType:
    name: str
    rule: PriceRule
    group_rules: Mapping[str, PriceRule] = field(default_factory=dict)
    decimals: int = 2

    def __post_init__(self) -> None:
        if not 0 <= self.decimals <= MAX_DECIMALS:
            raise InvalidPriceRuleError(f"Знаков после запятой: от 0 до {MAX_DECIMALS}.")

    def rule_for(self, group: str | None) -> PriceRule:
        return self.group_rules.get(group or DEFAULT_GROUP, self.rule)


@dataclass(frozen=True, slots=True)
class BasePrices:
    distr: Decimal | None
    dealer: Decimal | None
    retail: Decimal | None

    def get(self, column: BaseColumn) -> Decimal | None:
        return {
            BaseColumn.DISTR: self.distr,
            BaseColumn.DEALER: self.dealer,
            BaseColumn.RETAIL: self.retail,
        }[column]


@dataclass(frozen=True, slots=True)
class PriceResult:
    value: Decimal | None
    issue: PriceIssue | None = None


def calc_price(
    price_type: PriceType | None, prices: BasePrices, group: str | None = None
) -> PriceResult:
    if price_type is None:
        return PriceResult(None, PriceIssue.TYPE_NOT_CONFIGURED)
    rule = price_type.rule_for(group)
    base = prices.get(rule.base)
    if base is None or base <= 0:  # нулевая цена не должна уйти в 1С
        return PriceResult(None, PriceIssue.NO_BASE_PRICE)
    quantum = Decimal(1).scaleb(-price_type.decimals)
    return PriceResult((base * rule.factor).quantize(quantum, rounding=ROUND_HALF_UP))


def prices_ordered(prices: BasePrices) -> bool:
    """Розничная ≥ дилерской ≥ дистрибьюторской; пустые значения пропускаются."""
    values = [v for v in (prices.distr, prices.dealer, prices.retail) if v is not None]
    return all(a <= b for a, b in itertools.pairwise(values))


@dataclass(frozen=True, slots=True)
class FormulaPart:
    label: str | None  # «Расходка» из «Расходка: [Розничные]»
    rule: PriceRule


_FORMULA: Final = re.compile(
    r"\s*(?:(?P<label>[^:\x5b\x5d]+?)\s*:\s*)?"
    r"\x5b(?P<base>[^\x5d]+)\x5d"
    r"\s*(?:[*]\s*(?P<factor>[0-9]+(?:[.,][0-9]+)?))?\s*"
)


def parse_formula(text: str) -> FormulaPart:
    """Старая формула из Access: «[Розничные] * 0.95», «Расходка: [Розничные]»."""
    match = _FORMULA.fullmatch(text)
    if match is None:
        raise InvalidPriceRuleError(f"Не удалось разобрать формулу «{text}».")
    try:
        base = BaseColumn(match["base"].strip())
    except ValueError:
        raise InvalidPriceRuleError(f"Неизвестная колонка цены «{match['base']}».") from None
    factor = Decimal(match["factor"].replace(",", ".")) if match["factor"] else Decimal(1)
    return FormulaPart(match["label"], PriceRule(base, factor))
