"""Справочник ценовых групп и описание видов цен в базе.

Каждая загрузка из админки добавляет строку в price_document, действует последняя.
Прежние остаются историей. Транзакцией управляет вызывающий код.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PriceDocument
from app.domain.errors import InvalidPriceRuleError
from app.domain.price_types import base_price_types, parse_price_types
from app.domain.pricing import DEFAULT_GROUP, PriceType

GROUPS: Final = "groups"
TYPES: Final = "types"


@dataclass(frozen=True, slots=True)
class PriceSettings:
    groups: tuple[str, ...]
    types: Mapping[str, PriceType]
    types_text: str  # описание в том виде, как его вставили; пусто до первой загрузки


async def load_price_settings(session: AsyncSession) -> PriceSettings:
    groups = await _groups(session)
    text = await _latest(session, TYPES)
    if text is None:
        return PriceSettings(groups, base_price_types(), "")
    return PriceSettings(groups, parse_price_types(text, groups), text)


async def save_price_groups(
    session: AsyncSession, groups: Iterable[str], author: str
) -> tuple[str, ...]:
    """Новый справочник. Не сохраняется, если описание видов цен с ним не сходится."""
    names = tuple(dict.fromkeys((DEFAULT_GROUP, *groups)))
    text = await _latest(session, TYPES)
    if text is not None:
        try:
            parse_price_types(text, names)
        except InvalidPriceRuleError as exc:
            raise InvalidPriceRuleError(
                f"справочник не сохранён, описание видов цен с ним не сходится: {exc}"
            ) from None
    await _add(session, GROUPS, "\n".join(names), author)
    return names


async def save_price_types(
    session: AsyncSession, text: str, author: str
) -> dict[str, PriceType]:
    """Новое описание видов цен. С ошибкой не сохраняется."""
    types = parse_price_types(text, await _groups(session))
    await _add(session, TYPES, text, author)
    return types


async def _groups(session: AsyncSession) -> tuple[str, ...]:
    text = await _latest(session, GROUPS)
    return tuple(text.splitlines()) if text is not None else (DEFAULT_GROUP,)


async def _latest(session: AsyncSession, kind: str) -> str | None:
    return await session.scalar(
        select(PriceDocument.content)
        .where(PriceDocument.kind == kind)
        .order_by(PriceDocument.id.desc())
        .limit(1)
    )


async def _add(session: AsyncSession, kind: str, content: str, author: str) -> None:
    session.add(PriceDocument(kind=kind, content=content, author=author))
    await session.flush()
