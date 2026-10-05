from __future__ import annotations

from app.domain.order_match import match_rows
from app.domain.parse_input import parse_input
from app.domain.search import CatalogItem, SearchIndex, Status

A1 = CatalogItem(1, "R.10.B.20.", "Пластырь R-10", 100, True)
A2 = CatalogItem(2, "P07", "Пистолет продувочный", 200, True)
INDEX = SearchIndex([A1, A2], [])


def test_match_rows() -> None:
    rows = match_rows(parse_input("R.10.B.20. 5 шт\nP07\nнет такого - 3"), INDEX)
    assert [(r.row.name, r.match.status, r.ready) for r in rows] == [
        ("R.10.B.20.", Status.FOUND, True),
        ("P07", Status.FOUND, False),  # количества нет — выгружать нельзя
        ("нет такого", Status.NOT_FOUND, False),
    ]
    assert rows[0].match.product == A1
