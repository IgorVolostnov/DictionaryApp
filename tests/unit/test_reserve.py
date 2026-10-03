from __future__ import annotations

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from app.domain.reserve import ReserveLine, ReserveResult, allocate_reserve

D = Decimal


def test_duplicates_share_stock_top_down() -> None:
    lines = [ReserveLine("A", D(10)), ReserveLine("A", D(10))]
    assert allocate_reserve(lines, {"A": D(10)}) == [
        ReserveResult(D(10), duplicate=True),
        ReserveResult(D(0), duplicate=True),
    ]


def test_unrecognized_missing_quantity_and_out_of_stock() -> None:
    lines = [
        ReserveLine(None, D(5)),
        ReserveLine("B", None),
        ReserveLine("B", D(3)),
        ReserveLine("C", D(2)),
        ReserveLine("D", D(1)),
    ]
    assert allocate_reserve(lines, {"B": D(2), "C": D(-4)}) == [
        ReserveResult(None),
        ReserveResult(None, duplicate=True),
        ReserveResult(D(2), duplicate=True),
        ReserveResult(D(0), out_of_stock=True),
        ReserveResult(D(0), out_of_stock=True),  # D нет в остатках
    ]


lines_st = st.lists(
    st.builds(
        ReserveLine,
        st.sampled_from(["A", "B", None]),
        st.none() | st.decimals(min_value=D("0.001"), max_value=D(1000), places=3),
    ),
    max_size=20,
)
stock_st = st.dictionaries(
    st.sampled_from(["A", "B"]), st.decimals(min_value=-100, max_value=1000, places=3)
)


@given(lines_st, stock_st)
def test_reserve_never_exceeds_stock_or_quantity(
    lines: list[ReserveLine], stock: dict[str, Decimal]
) -> None:
    results = allocate_reserve(lines, stock)
    pairs = list(zip(lines, results, strict=True))
    for key in ("A", "B"):
        total = sum(
            (r.reserve for line, r in pairs if line.product_key == key and r.reserve is not None),
            D(0),
        )
        assert total <= max(stock.get(key, D(0)), D(0))
    for line, r in pairs:
        if r.reserve is not None:
            assert line.quantity is not None
            assert D(0) <= r.reserve <= line.quantity
