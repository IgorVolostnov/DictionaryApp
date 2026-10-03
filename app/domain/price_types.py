"""Виды цен покупателей: разбор описания, скопированного из 1С.

    5. Розница_5_Все_0, ք: [Розничные] * 1
    Ценовая группа	Формула
    Расходка	[Розничные] * 0.95
"""

from __future__ import annotations

import re
from collections.abc import Collection
from typing import Final

from app.domain.errors import InvalidPriceRuleError
from app.domain.pricing import BaseColumn, PriceRule, PriceType, parse_formula

# «17. Дилер_28: …» и «1. Все_5, ք: …»: после запятой идёт знак валюты, он отбрасывается.
_TYPE_LINE: Final = re.compile(r"\d+\.\s*(?P<name>[^:]+?)(?:,\s*[^\s,:]+)?\s*:\s*(?P<formula>.+)")
_SERVICE_LINES: Final = frozenset({"ценовая группа формула", "уточнение по ценовым группам: нет"})


def parse_price_types(text: str, groups: Collection[str]) -> dict[str, PriceType]:
    """Виды цен по описанию. groups — справочник ценовых групп для проверки названий.

    Текст до первого вида цены («N. Название: формула») считается вступлением
    и пропускается. Базовые виды цен (Дилерская и др.) добавляются сами,
    если их нет в описании. Пробелы и табуляции внутри строки не важны.
    """
    main: dict[str, PriceRule] = {}
    extra: dict[str, dict[str, PriceRule]] = {}
    current: str | None = None
    for n, raw in enumerate(text.splitlines(), start=1):
        line = " ".join(raw.split())
        if not line or line.casefold() in _SERVICE_LINES:
            continue
        if current is None and not _TYPE_LINE.fullmatch(line):
            continue  # вступление до первого вида цены
        try:
            current = _read_line(line, current, main, extra, groups)
        except InvalidPriceRuleError as exc:
            raise InvalidPriceRuleError(f"строка {n}: {exc}") from None
    if not main:
        raise InvalidPriceRuleError(
            "не найдено ни одного вида цены вида «1. Все_5: [Розничные] * 0.95»"
        )
    types = {name: PriceType(name, rule, extra[name]) for name, rule in main.items()}
    for column in BaseColumn:
        types.setdefault(column.value, PriceType(column.value, PriceRule(column)))
    return types


def _read_line(
    line: str,
    current: str | None,
    main: dict[str, PriceRule],
    extra: dict[str, dict[str, PriceRule]],
    groups: Collection[str],
) -> str:
    """Разбирает строку; возвращает вид цены, к которому относятся следующие строки."""
    if m := _TYPE_LINE.fullmatch(line):
        name = m["name"]
        if name in main:
            raise InvalidPriceRuleError(f"вид цены «{name}» описан дважды")
        main[name] = parse_formula(m["formula"]).rule
        extra[name] = {}
        return name
    # Строка группы: «Расходка [Розничные] * 0.95». Формула начинается с первой «[».
    group, bracket, rest = line.partition("[")
    group = group.strip()
    if not bracket or not group or current is None:
        raise InvalidPriceRuleError(f"не удалось разобрать «{line}»")
    if group not in groups:
        raise InvalidPriceRuleError(f"ценовой группы «{group}» нет в справочнике")
    if group in extra[current]:
        raise InvalidPriceRuleError(f"ценовая группа «{group}» указана дважды")
    extra[current][group] = parse_formula(bracket + rest).rule
    return current
