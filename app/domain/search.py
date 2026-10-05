"""Поиск товаров по строке заявки.

Ключи строки (lookup_keys) ищутся в словаре синонимов, среди артикулов и среди
наименований каталога. Артикул и наименование нужны для товаров без синонимов:
в словаре Access их нет у трети каталога.
Найденные товары из всех источников объединяются. Если активных несколько, строка
неоднозначная, и менеджер выбирает сам. Снятые с продажи показываются, только если
активных не нашлось.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from app.domain.errors import InvalidAliasKeyError
from app.domain.normalize import ensure_storable_key, lookup_keys


class Via(StrEnum):
    """Где нашёлся товар."""

    ALIAS = "словарь"
    ARTICLE = "артикул"
    NAME = "наименование"


class Status(StrEnum):
    FOUND = "found"  # ровно один активный товар
    AMBIGUOUS = "ambiguous"  # несколько активных
    INACTIVE = "inactive"  # только снятые с продажи
    NOT_FOUND = "not_found"


@dataclass(frozen=True, slots=True)
class CatalogItem:
    product_id: int
    article: str
    name: str
    sort_order: int | None
    active: bool


@dataclass(frozen=True, slots=True)
class Candidate:
    item: CatalogItem
    via: tuple[Via, ...]  # в порядке Via


@dataclass(frozen=True, slots=True)
class LineMatch:
    text: str
    status: Status
    candidates: tuple[Candidate, ...]  # в порядке сайта

    @property
    def product(self) -> CatalogItem | None:
        return self.candidates[0].item if self.status is Status.FOUND else None


def site_order(item: CatalogItem) -> tuple[bool, int, str, str]:
    """Как на сайте: меньшая «Сортировка на сайте» выше, без сортировки — в конце."""
    return (item.sort_order is None, item.sort_order or 0, item.name, item.article)


class SearchIndex:
    def __init__(self, items: Iterable[CatalogItem], aliases: Iterable[tuple[str, int]]) -> None:
        self._items = {item.product_id: item for item in items}
        self._found: dict[str, dict[int, set[Via]]] = {}
        for key, product_id in aliases:
            self._add(key, product_id, Via.ALIAS)
        for item in self._items.values():
            for via, text in ((Via.ARTICLE, item.article), (Via.NAME, item.name)):
                for key in lookup_keys(text):
                    if _searchable(key):
                        self._add(key, item.product_id, via)

    def _add(self, key: str, product_id: int, via: Via) -> None:
        self._found.setdefault(key, {}).setdefault(product_id, set()).add(via)

    def find(self, text: str) -> LineMatch:
        found: dict[int, set[Via]] = {}
        for key in lookup_keys(text):
            for product_id, via in self._found.get(key, {}).items():
                found.setdefault(product_id, set()).update(via)
        candidates = sorted(
            (
                Candidate(self._items[i], tuple(v for v in Via if v in via))
                for i, via in found.items()
            ),
            key=lambda candidate: site_order(candidate.item),
        )
        active = tuple(c for c in candidates if c.item.active)
        if len(active) == 1:
            return LineMatch(text, Status.FOUND, active)
        if active:
            return LineMatch(text, Status.AMBIGUOUS, active)
        if candidates:
            return LineMatch(text, Status.INACTIVE, tuple(candidates))
        return LineMatch(text, Status.NOT_FOUND, ())

    def shared_keys(self) -> dict[str, tuple[str, ...]]:
        """Ключи, ведущие к нескольким активным товарам: такие строки всегда неоднозначны."""
        result: dict[str, tuple[str, ...]] = {}
        for key in sorted(self._found):
            items = (self._items[i] for i in self._found[key])
            articles = sorted(item.article for item in items if item.active)
            if len(articles) > 1:
                result[key] = tuple(articles)
        return result


def _searchable(key: str) -> bool:
    try:
        ensure_storable_key(key)
    except InvalidAliasKeyError:
        return False
    return True
