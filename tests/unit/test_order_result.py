from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from app.domain.credit import CreditCheck, CreditStatus
from app.domain.order_match import MatchedRow
from app.domain.order_result import (
    AMBIGUOUS,
    INACTIVE,
    NOT_FOUND,
    OrderResult,
    RowResult,
    compute_order_result,
)
from app.domain.parse_input import InputRow
from app.domain.pricing import (
    BaseColumn,
    BasePrices,
    PriceIssue,
    PriceRule,
    PriceType,
)
from app.domain.search import (
    Candidate,
    CatalogItem,
    LineMatch,
    Status,
    Via,
)

D = Decimal


def _item(
    pid: int = 1,
    article: str = "A001",
    name: str = "Товар А",
    sort_order: int | None = None,
    active: bool = True,
    price_group: str = "РУБ",
) -> CatalogItem:
    return CatalogItem(pid, article, name, sort_order, active, price_group)


def _matched(
    text: str = "Товар А",
    quantity: Decimal | None = None,
    status: Status = Status.FOUND,
    item: CatalogItem | None = None,
) -> MatchedRow:
    if quantity is None and status is Status.FOUND:
        quantity = D(5)
    if item is None:
        item = _item()
    if status is Status.FOUND:
        candidates: tuple[Candidate, ...] = (Candidate(item, (Via.ARTICLE,)),)
    elif status is Status.AMBIGUOUS:
        item2 = _item(pid=2, article="A002", name="Товар Б")
        candidates = (Candidate(item, (Via.ARTICLE,)), Candidate(item2, (Via.NAME,)))
    elif status is Status.INACTIVE:
        inactive = _item(active=False)
        candidates = (Candidate(inactive, (Via.ARTICLE,)),)
    else:
        candidates = ()
    match = LineMatch(text, status, candidates)
    row = InputRow(line_no=1, name=text, quantity=quantity)
    return MatchedRow(row, match)


PRICES = BasePrices(distr=D(1000), dealer=D(1200), retail=D(1500))
PRICE_TYPE = PriceType("Дилер", PriceRule(BaseColumn.DEALER))
STOCK = {"A001": D(10)}


# ======================== RowResult ========================


class TestRowResult:
    def test_ready_found_with_quantity(self) -> None:
        row = RowResult(1, "A", "A", D(5), D(5), D(1000), None, Status.FOUND, "РУБ")
        assert row.ready is True

    def test_ready_not_found(self) -> None:
        row = RowResult(0, "", "", D(5), None, None, None, Status.NOT_FOUND, "")
        assert row.ready is False

    def test_ready_no_quantity(self) -> None:
        row = RowResult(1, "A", "A", None, None, D(1000), None, Status.FOUND, "РУБ")
        assert row.ready is False

    def test_warning_not_found(self) -> None:
        row = RowResult(0, "", "", D(5), None, None, None, Status.NOT_FOUND, "")
        assert row.warning == NOT_FOUND

    def test_warning_ambiguous(self) -> None:
        row = RowResult(1, "A", "A", D(5), D(5), D(1000), None, Status.AMBIGUOUS, "РУБ")
        assert row.warning == AMBIGUOUS

    def test_warning_inactive(self) -> None:
        row = RowResult(1, "A", "A", D(5), D(5), D(1000), None, Status.INACTIVE, "РУБ")
        assert row.warning == INACTIVE

    def test_warning_no_base_price(self) -> None:
        row = RowResult(
            1, "A", "A", D(5), D(5), None, PriceIssue.NO_BASE_PRICE, Status.FOUND, "РУБ"
        )
        assert row.warning == PriceIssue.NO_BASE_PRICE

    def test_warning_insufficient_stock(self) -> None:
        row = RowResult(1, "A", "A", D(10), D(5), D(1000), None, Status.FOUND, "РУБ")
        assert row.warning == "Недостаточно на складе"

    def test_no_warning(self) -> None:
        row = RowResult(1, "A", "A", D(5), D(5), D(1000), None, Status.FOUND, "РУБ")
        assert row.warning is None

    def test_warning_zero_quantity_no_warning(self) -> None:
        row = RowResult(1, "A", "A", D(0), D(0), D(1000), None, Status.FOUND, "РУБ")
        assert row.warning is None


# ======================== OrderResult ========================


class TestOrderResult:
    def test_ready_all_rows_ready(self) -> None:
        rows = (
            RowResult(1, "A", "A", D(5), D(5), D(1000), None, Status.FOUND, "РУБ"),
            RowResult(2, "B", "B", D(3), D(3), D(2000), None, Status.FOUND, "РУБ"),
        )
        result = OrderResult(
            rows=rows,
            credit=CreditCheck(CreditStatus.WITHIN_LIMIT, D(10000), D(0)),
            total_value=D(11000),
            total_quantity=D(8),
            warnings=(),
        )
        assert result.ready is True

    def test_ready_one_not_ready(self) -> None:
        rows = (
            RowResult(1, "A", "A", D(5), D(5), D(1000), None, Status.FOUND, "РУБ"),
            RowResult(0, "", "", D(3), None, None, None, Status.NOT_FOUND, ""),
        )
        result = OrderResult(
            rows=rows,
            credit=CreditCheck(CreditStatus.WITHIN_LIMIT, D(10000), D(0)),
            total_value=D(1000),
            total_quantity=D(8),
            warnings=(NOT_FOUND,),
        )
        assert result.ready is False

    def test_has_warnings_true(self) -> None:
        not_found = _matched(text="Неизвестный", quantity=D(1), status=Status.NOT_FOUND)
        result = compute_order_result(
            matched_rows=(not_found,),
            price_type=PRICE_TYPE,
            base_prices=PRICES,
            stock=STOCK,
        )
        assert result.has_warnings is True
        assert NOT_FOUND in result.warnings

    def test_has_warnings_false(self) -> None:
        result = OrderResult(
            rows=(
                RowResult(
                    1, "A", "A", D(5), D(5), D(1000), None, Status.FOUND, "РУБ"
                ),
            ),
            credit=CreditCheck(CreditStatus.WITHIN_LIMIT, D(10000), D(0)),
            total_value=D(1000),
            total_quantity=D(5),
            warnings=(),
        )
        assert result.has_warnings is False


# ======================== compute_order_result ========================


class TestComputeOrderResult:
    def test_empty_rows(self) -> None:
        result = compute_order_result(
            matched_rows=(),
            price_type=PRICE_TYPE,
            base_prices=PRICES,
            stock=STOCK,
        )
        assert result.rows == ()
        assert result.total_value == D(0)
        assert result.total_quantity == D(0)
        assert result.warnings == ()

    def test_single_found_row(self) -> None:
        matched = _matched(text="Товар А", quantity=D(5), status=Status.FOUND)
        result = compute_order_result(
            matched_rows=(matched,),
            price_type=PRICE_TYPE,
            base_prices=PRICES,
            stock=STOCK,
        )
        assert len(result.rows) == 1
        row = result.rows[0]
        assert row.product_id == 1
        assert row.article == "A001"
        assert row.name == "Товар А"
        assert row.quantity == D(5)
        assert row.reserve == D(5)
        assert row.price == D(1200)  # dealer price
        assert row.price_issue is None
        assert row.status is Status.FOUND
        assert row.price_group == "РУБ"
        assert row.ready is True
        assert row.warning is None
        assert result.total_value == D(6000)  # 1200 * 5
        assert result.total_quantity == D(5)
        assert result.ready is True

    def test_not_found_row(self) -> None:
        matched = _matched(text="Неизвестный", quantity=D(3), status=Status.NOT_FOUND)
        result = compute_order_result(
            matched_rows=(matched,),
            price_type=PRICE_TYPE,
            base_prices=PRICES,
            stock=STOCK,
        )
        assert len(result.rows) == 1
        row = result.rows[0]
        assert row.product_id == 0
        assert row.article == ""
        assert row.name == "Неизвестный"
        assert row.reserve is None
        assert row.price is None
        assert row.price_issue == PriceIssue.TYPE_NOT_CONFIGURED
        assert row.status is Status.NOT_FOUND
        assert row.ready is False
        assert row.warning == NOT_FOUND
        assert NOT_FOUND in result.warnings

    def test_ambiguous_row(self) -> None:
        item = _item()
        matched = _matched(
            text="Товар",
            quantity=D(5),
            status=Status.AMBIGUOUS,
            item=item,
        )
        result = compute_order_result(
            matched_rows=(matched,),
            price_type=PRICE_TYPE,
            base_prices=PRICES,
            stock=STOCK,
        )
        assert len(result.rows) == 1
        row = result.rows[0]
        assert row.status is Status.AMBIGUOUS
        assert row.warning == AMBIGUOUS
        assert AMBIGUOUS in result.warnings

    def test_inactive_row(self) -> None:
        inactive = _item(active=False)
        matched = _matched(
            text="Старый товар",
            quantity=D(2),
            status=Status.INACTIVE,
            item=inactive,
        )
        result = compute_order_result(
            matched_rows=(matched,),
            price_type=PRICE_TYPE,
            base_prices=PRICES,
            stock=STOCK,
        )
        assert len(result.rows) == 1
        row = result.rows[0]
        assert row.status is Status.INACTIVE
        assert row.warning == INACTIVE
        assert INACTIVE in result.warnings

    def test_no_quantity(self) -> None:
        matched_row = InputRow(line_no=1, name="Товар А", quantity=None)
        item = _item()
        match = LineMatch("Товар А", Status.FOUND, (Candidate(item, (Via.ARTICLE,)),))
        matched = MatchedRow(matched_row, match)
        result = compute_order_result(
            matched_rows=(matched,),
            price_type=PRICE_TYPE,
            base_prices=PRICES,
            stock=STOCK,
        )
        assert len(result.rows) == 1
        row = result.rows[0]
        assert row.quantity is None
        assert row.reserve is None
        assert row.ready is False

    def test_insufficient_stock(self) -> None:
        matched = _matched(text="Товар А", quantity=D(20), status=Status.FOUND)
        result = compute_order_result(
            matched_rows=(matched,),
            price_type=PRICE_TYPE,
            base_prices=PRICES,
            stock=STOCK,
        )
        row = result.rows[0]
        assert row.reserve == D(10)
        assert row.quantity == D(20)
        assert row.warning == "Недостаточно на складе"

    def test_duplicate_items_share_reserve(self) -> None:
        item = _item()
        matched1 = _matched(text="Товар А", quantity=D(5), status=Status.FOUND, item=item)
        matched2 = _matched(text="Товар А", quantity=D(5), status=Status.FOUND, item=item)
        result = compute_order_result(
            matched_rows=(matched1, matched2),
            price_type=PRICE_TYPE,
            base_prices=PRICES,
            stock=STOCK,
        )
        # Stock=10, first gets min(5,10)=5, second gets min(5,5)=5
        assert result.rows[0].reserve == D(5)
        assert result.rows[1].reserve == D(5)

    def test_no_price_type(self) -> None:
        matched = _matched(text="Товар А", quantity=D(5), status=Status.FOUND)
        result = compute_order_result(
            matched_rows=(matched,),
            price_type=None,
            base_prices=PRICES,
            stock=STOCK,
        )
        row = result.rows[0]
        assert row.price is None
        assert row.price_issue == PriceIssue.TYPE_NOT_CONFIGURED
        assert row.warning == PriceIssue.TYPE_NOT_CONFIGURED

    def test_zero_base_price(self) -> None:
        zero_prices = BasePrices(distr=D(0), dealer=D(0), retail=D(0))
        matched = _matched(text="Товар А", quantity=D(5), status=Status.FOUND)
        result = compute_order_result(
            matched_rows=(matched,),
            price_type=PRICE_TYPE,
            base_prices=zero_prices,
            stock=STOCK,
        )
        row = result.rows[0]
        assert row.price is None
        assert row.price_issue == PriceIssue.NO_BASE_PRICE

    def test_multiple_rows_mixed_status(self) -> None:
        found = _matched(text="Товар А", quantity=D(5), status=Status.FOUND)
        not_found = _matched(text="Неизвестный", quantity=D(3), status=Status.NOT_FOUND)
        ambiguous = _matched(
            text="Товар", quantity=D(2), status=Status.AMBIGUOUS, item=_item()
        )
        result = compute_order_result(
            matched_rows=(found, not_found, ambiguous),
            price_type=PRICE_TYPE,
            base_prices=PRICES,
            stock=STOCK,
        )
        assert len(result.rows) == 3
        assert result.rows[0].status is Status.FOUND
        assert result.rows[1].status is Status.NOT_FOUND
        assert result.rows[2].status is Status.AMBIGUOUS
        assert NOT_FOUND in result.warnings
        assert AMBIGUOUS in result.warnings
        assert result.ready is False

    def test_price_with_group_rules(self) -> None:
        """Цена зависит от группы товара."""
        price_type = PriceType(
            "Дилер",
            PriceRule(BaseColumn.DEALER),
            group_rules={"Расходка": PriceRule(BaseColumn.RETAIL)},
        )
        found = _matched(
            text="Товар А", quantity=D(5), status=Status.FOUND,
            item=_item(price_group="Расходка"),
        )
        result = compute_order_result(
            matched_rows=(found,),
            price_type=price_type,
            base_prices=PRICES,
            stock=STOCK,
        )
        # Retail price for "Расходка" group
        assert result.rows[0].price == D(1500)

    def test_total_value_excludes_not_found(self) -> None:
        found = _matched(text="Товар А", quantity=D(5), status=Status.FOUND)
        not_found = _matched(text="Неизвестный", quantity=D(100), status=Status.NOT_FOUND)
        result = compute_order_result(
            matched_rows=(found, not_found),
            price_type=PRICE_TYPE,
            base_prices=PRICES,
            stock=STOCK,
        )
        # Only found row contributes to total_value
        assert result.total_value == D(6000)  # 1200 * 5
        # But total_quantity includes not_found
        assert result.total_quantity == D(105)

    def test_total_quantity_excludes_none(self) -> None:
        found = _matched(text="Товар А", quantity=D(5), status=Status.FOUND)
        row_no_qty = InputRow(line_no=2, name="Товар Б", quantity=None)
        item2 = _item(pid=2)
        match_no_qty = LineMatch("Товар Б", Status.FOUND, (Candidate(item2, (Via.ARTICLE,)),))
        no_qty = MatchedRow(row_no_qty, match_no_qty)
        result = compute_order_result(
            matched_rows=(found, no_qty),
            price_type=PRICE_TYPE,
            base_prices=PRICES,
            stock=STOCK,
        )
        assert result.total_quantity == D(5)

    def test_stock_zero(self) -> None:
        matched = _matched(text="Товар А", quantity=D(5), status=Status.FOUND)
        result = compute_order_result(
            matched_rows=(matched,),
            price_type=PRICE_TYPE,
            base_prices=PRICES,
            stock={},
        )
        row = result.rows[0]
        assert row.reserve == D(0)

    def test_unrecognized_item_has_no_price(self) -> None:
        """Товар без CatalogItem (product_id=0) не имеет цены."""
        matched = _matched(text="Неизвестный", quantity=D(5), status=Status.NOT_FOUND)
        result = compute_order_result(
            matched_rows=(matched,),
            price_type=PRICE_TYPE,
            base_prices=PRICES,
            stock=STOCK,
        )
        row = result.rows[0]
        assert row.product_id == 0
        assert row.price is None
        assert row.price_issue == PriceIssue.TYPE_NOT_CONFIGURED

    def test_frozen_dataclasses(self) -> None:
        """Проверяем что RowResult и OrderResult — frozen dataclass."""
        row = RowResult(1, "A", "A", D(5), D(5), D(1000), None, Status.FOUND, "РУБ")
        with pytest.raises(FrozenInstanceError, match="cannot assign to field"):
            row.product_id = 2  # type: ignore[misc]

        result = OrderResult(
            rows=(row,),
            credit=CreditCheck(CreditStatus.WITHIN_LIMIT, D(10000), D(0)),
            total_value=D(1000),
            total_quantity=D(5),
            warnings=(),
        )
        with pytest.raises(FrozenInstanceError, match="cannot assign to field"):
            result.rows = ()  # type: ignore[misc]

    def test_warnings_sorted(self) -> None:
        """Предупреждения должны быть отсортированы."""
        not_found = _matched(text="Неизвестный", quantity=D(1), status=Status.NOT_FOUND)
        inactive = _matched(
            text="Старый", quantity=D(1), status=Status.INACTIVE, item=_item(active=False)
        )
        result = compute_order_result(
            matched_rows=(not_found, inactive),
            price_type=PRICE_TYPE,
            base_prices=PRICES,
            stock=STOCK,
        )
        # tuple should equal tuple(sorted(...))
        assert result.warnings == tuple(sorted(result.warnings))
