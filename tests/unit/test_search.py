from __future__ import annotations

import pytest

from app.domain.search import (
    Candidate,
    CatalogItem,
    LineMatch,
    SearchIndex,
    Status,
    Via,
    site_order,
)


def item(
    product_id: int, article: str, name: str, sort_order: int | None, active: bool = True
) -> CatalogItem:
    return CatalogItem(product_id, article, name, sort_order, active)


A1 = item(1, "CA102150150", "(CA102150150) Насадка на выхлопную трубу 102мм", 500)
A2 = item(2, "TR-415.EPDM.100", "Мембрана EPDM", 100)
A3 = item(3, "TR-415.100", "Мембрана", None, active=False)
A4 = item(4, "P07", "Пистолет продувочный", 300)
A5 = item(5, "Z", "Ключ", 10)  # артикул из одной буквы: по нему не ищем
INDEX = SearchIndex(
    [A1, A2, A3, A4, A5],
    [
        ("NASADKA", 1),
        ("SHARED", 1),
        ("SHARED", 2),
        ("SHARED", 4),
        ("OLDKEY", 3),
        ("MIXED", 2),
        ("MIXED", 3),
        ("P07", 4),
    ],
)


def test_found_by_alias() -> None:
    match = INDEX.find("nasadka")
    assert match == LineMatch("nasadka", Status.FOUND, (Candidate(A1, (Via.ALIAS,)),))
    assert match.product == A1


@pytest.mark.parametrize(("text", "product"), [("ca102150150", A1), ("tr-415.epdm.100", A2)])
def test_found_by_article(text: str, product: CatalogItem) -> None:
    assert INDEX.find(text).candidates == (Candidate(product, (Via.ARTICLE,)),)


def test_found_by_name() -> None:
    assert INDEX.find(A1.name).candidates == (Candidate(A1, (Via.NAME,)),)


def test_alias_and_article() -> None:
    assert INDEX.find("p07").candidates == (Candidate(A4, (Via.ALIAS, Via.ARTICLE)),)


def test_ambiguous_in_site_order() -> None:
    match = INDEX.find("shared")
    assert match.status is Status.AMBIGUOUS
    assert [c.item for c in match.candidates] == [A2, A4, A1]
    assert match.product is None


def test_inactive() -> None:
    assert INDEX.find("OLDKEY") == LineMatch(
        "OLDKEY", Status.INACTIVE, (Candidate(A3, (Via.ALIAS,)),)
    )
    assert INDEX.find("TR-415.100").candidates == (Candidate(A3, (Via.ARTICLE,)),)


def test_active_wins_over_inactive() -> None:
    assert INDEX.find("MIXED") == LineMatch("MIXED", Status.FOUND, (Candidate(A2, (Via.ALIAS,)),))


@pytest.mark.parametrize("text", ["нет такого", "", "Z"])
def test_not_found(text: str) -> None:
    assert INDEX.find(text) == LineMatch(text, Status.NOT_FOUND, ())


def test_site_order() -> None:
    items = [
        item(1, "A", "Б", None),
        item(2, "B", "В", 5),
        item(3, "C", "А", 5),
        item(4, "D", "Я", 1),
    ]
    assert [i.article for i in sorted(items, key=site_order)] == ["D", "C", "B", "A"]


def test_shared_keys() -> None:
    assert INDEX.shared_keys() == {"SHARED": ("CA102150150", "P07", "TR-415.EPDM.100")}
