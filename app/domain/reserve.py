"""Резерв: остаток распределяется по строкам заявки сверху вниз."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ReserveLine:
    product_key: str | None  # None — строка не распознана
    quantity: Decimal | None


@dataclass(frozen=True, slots=True)
class ReserveResult:
    reserve: Decimal | None
    duplicate: bool = False
    out_of_stock: bool = False


def allocate_reserve(
    lines: Sequence[ReserveLine], stock: Mapping[str, Decimal]
) -> list[ReserveResult]:
    counts = Counter(line.product_key for line in lines if line.product_key is not None)
    remaining: dict[str, Decimal] = {}
    results: list[ReserveResult] = []
    for line in lines:
        key = line.product_key
        if key is None:
            results.append(ReserveResult(None))
            continue
        initial = stock.get(key, Decimal(0))
        left = remaining.setdefault(key, max(initial, Decimal(0)))
        duplicate, out_of_stock = counts[key] > 1, initial <= 0
        if line.quantity is None:
            results.append(ReserveResult(None, duplicate, out_of_stock))
            continue
        reserve = min(line.quantity, left)
        remaining[key] = left - reserve
        results.append(ReserveResult(reserve, duplicate, out_of_stock))
    return results
