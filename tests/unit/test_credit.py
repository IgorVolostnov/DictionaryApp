from __future__ import annotations

from decimal import Decimal

from app.domain.credit import CreditCheck, CreditStatus, check_credit

D = Decimal


def test_zero_limit_is_prepayment_only() -> None:
    assert check_credit(D(0), D(500), D(100)) == CreditCheck(
        CreditStatus.PREPAYMENT_ONLY, None, D(0)
    )
    assert check_credit(D(0), D(-115), D(100)).overpayment == D(115)


def test_within_and_over_limit() -> None:
    assert check_credit(D(1000), D(300), D(700)) == CreditCheck(
        CreditStatus.WITHIN_LIMIT, D(700), D(0)
    )
    assert check_credit(D(1000), D(300), D(701)).status is CreditStatus.OVER_LIMIT


def test_overpayment_increases_available() -> None:
    assert check_credit(D(1000), D(-200), D(1100)) == CreditCheck(
        CreditStatus.WITHIN_LIMIT, D(1200), D(200)
    )
