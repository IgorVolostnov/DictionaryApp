"""Кредитный лимит юрлица из price_user.csv."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class CreditStatus(StrEnum):
    PREPAYMENT_ONLY = "Только предоплата"
    WITHIN_LIMIT = "В пределах лимита"
    OVER_LIMIT = "Превышен лимит"


@dataclass(frozen=True, slots=True)
class CreditCheck:
    status: CreditStatus
    available: Decimal | None  # None при предоплате
    overpayment: Decimal  # > 0, если долг отрицательный


def check_credit(limit: Decimal, debt: Decimal, order_total: Decimal) -> CreditCheck:
    """Только предупреждение: решение остаётся за менеджером."""
    overpayment = -debt if debt < 0 else Decimal(0)
    if limit <= 0:
        return CreditCheck(CreditStatus.PREPAYMENT_ONLY, None, overpayment)
    available = limit - debt
    status = CreditStatus.OVER_LIMIT if order_total > available else CreditStatus.WITHIN_LIMIT
    return CreditCheck(status, available, overpayment)
