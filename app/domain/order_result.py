"""Объединение цены, резерва и кредита в единый результат подбора.

Принимает MatchedRow (результат order_match) и возвращает полный результат
с ценами, доступным резервом и кредитным статусом — готовый для отображения
в веб-интерфейсе.

Функция compute_order_result() — единственный入口 point для получения
результата подбора. Все расчёты (цена, резерв, кредит) выполняются здесь,
а не в веб-роутерах, чтобы избежать дублирования логики.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from app.domain.credit import CreditCheck, CreditStatus, check_credit
from app.domain.order_match import MatchedRow
from app.domain.pricing import (
    BasePrices,
    PriceIssue,
    PriceResult,
    PriceType,
    calc_price,
)
from app.domain.reserve import ReserveLine, ReserveResult, allocate_reserve
from app.domain.search import CatalogItem, Status

NOT_FOUND: Final = "Не найдено"
AMBIGUOUS: Final = "Неоднозначно"
INACTIVE: Final = "Снят с продажи"


@dataclass(frozen=True, slots=True)
class RowResult:
    """Результат обработки одной строки заявки."""

    product_id: int
    article: str
    name: str
    quantity: Decimal | None
    reserve: Decimal | None
    price: Decimal | None
    price_issue: str | None
    status: Status
    price_group: str

    @property
    def ready(self) -> bool:
        """Можно выгружать в 1С: товар найден и количество известно."""
        return self.status is Status.FOUND and self.quantity is not None

    @property
    def warning(self) -> str | None:
        """Предупреждение для строки: None если всё в порядке."""
        if self.status is Status.NOT_FOUND:
            return NOT_FOUND
        if self.status is Status.AMBIGUOUS:
            return AMBIGUOUS
        if self.status is Status.INACTIVE:
            return INACTIVE
        if self.price_issue is not None:
            return self.price_issue
        if self.reserve is not None and self.quantity is not None and self.reserve < self.quantity:
            return "Недостаточно на складе"
        return None


@dataclass(frozen=True, slots=True)
class OrderResult:
    """Полный результат подбора заявки."""

    rows: tuple[RowResult, ...]
    credit: CreditCheck
    total_value: Decimal
    total_quantity: Decimal
    warnings: tuple[str, ...]

    @property
    def ready(self) -> bool:
        """Все строки готовы к выгрузке в 1С."""
        return all(row.ready for row in self.rows)

    @property
    def has_warnings(self) -> bool:
        """Есть ли предупреждения по строкам."""
        return bool(self.warnings)


def compute_order_result(
    matched_rows: tuple[MatchedRow, ...],
    price_type: PriceType | None,
    base_prices: BasePrices,
    stock: Mapping[str, Decimal],
) -> OrderResult:
    """Вычисляет полный результат подбора заявки.

    Для каждой строки MatchedRow:
    - Извлекает CatalogItem из LineMatch
    - Рассчитывает цену через calc_price()
    - Распределяет резерв через allocate_reserve()

    Затем проверяет кредитный лимит для всего заказа.

    Args:
        matched_rows: Результат order_match.match_rows().
        price_type: Тип цен клиента (PriceType или None).
        base_prices: Базовые цены из distr.xlsx (distr, dealer, retail).
        stock: Mapping article → количество на складе.

    Returns:
        OrderResult с ценами, резервом и кредитным статусом.
    """
    if not matched_rows:
        return OrderResult(
            rows=(),
            credit=CreditCheck(CreditStatus.PREPAYMENT_ONLY, None, Decimal(0)),
            total_value=Decimal(0),
            total_quantity=Decimal(0),
            warnings=(),
        )

    # Собираем данные для reserve и price расчётов
    reserve_lines: list[ReserveLine] = []
    row_data: list[tuple[MatchedRow, CatalogItem | None]] = []

    for matched in matched_rows:
        item = matched.match.product
        article = item.article if item is not None else None
        qty = matched.row.quantity
        reserve_lines.append(ReserveLine(article, qty))
        row_data.append((matched, item))

    # Распределяем резерв сверху вниз
    reserve_results: list[ReserveResult] = allocate_reserve(reserve_lines, stock)

    # Собираем RowResult для каждой строки
    rows: list[RowResult] = []
    total_value: Decimal = Decimal(0)
    total_quantity: Decimal = Decimal(0)
    warnings: set[str] = set()

    for (matched, item), reserve in zip(row_data, reserve_results, strict=True):
        text = matched.row.name
        status = matched.match.status
        quantity = matched.row.quantity

        if item is not None:
            product_id = item.product_id
            article = item.article
            name = item.name
            group = item.price_group
        else:
            product_id = 0
            article = ""
            name = text
            group = ""

        # Рассчитываем цену
        if item is not None:
            price_result: PriceResult = calc_price(price_type, base_prices, group)
        else:
            price_result = PriceResult(None, PriceIssue.TYPE_NOT_CONFIGURED)

        price: Decimal | None = price_result.value
        price_issue: str | None = price_result.issue

        # Суммируем стоимость
        if price is not None and quantity is not None:
            total_value += price * quantity
        if quantity is not None:
            total_quantity += quantity

        # Собираем предупреждения
        if status is Status.NOT_FOUND:
            warnings.add(NOT_FOUND)
        elif status is Status.AMBIGUOUS:
            warnings.add(AMBIGUOUS)
        elif status is Status.INACTIVE:
            warnings.add(INACTIVE)
        elif price_issue is not None:
            warnings.add(price_issue)

        rows.append(
            RowResult(
                product_id=product_id,
                article=article,
                name=name,
                quantity=quantity,
                reserve=reserve.reserve,
                price=price,
                price_issue=price_issue,
                status=status,
                price_group=group,
            )
        )

    # Проверяем кредит (credit_limit=0 или None = только предоплата)
    credit = check_credit(Decimal(0), Decimal(0), total_value)

    return OrderResult(
        rows=tuple(rows),
        credit=credit,
        total_value=total_value,
        total_quantity=total_quantity,
        warnings=tuple(sorted(warnings)),
    )
