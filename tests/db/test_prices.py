from __future__ import annotations

import re
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import prices
from app.db.models import PriceDocument
from app.domain.errors import InvalidPriceRuleError
from app.domain.price_types import base_price_types
from app.domain.pricing import BaseColumn, PriceRule

pytestmark = [pytest.mark.db, pytest.mark.asyncio]

TYPES = "Как считаются цены:\n1. Дилер_15, ք: [Дилерская] * 1\nРасходка\t[Розничные] * 0.85\n"


async def uploads(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(PriceDocument)) or 0


async def test_defaults_before_first_upload(pg_session: AsyncSession) -> None:
    assert await prices.load_price_settings(pg_session) == prices.PriceSettings(
        ("РУБ",), base_price_types(), ""
    )


async def test_save_and_load(pg_session: AsyncSession) -> None:
    groups = await prices.save_price_groups(pg_session, ["Расходка", "РУБ", "Расходка"], "admin")
    assert groups == ("РУБ", "Расходка")
    types = await prices.save_price_types(pg_session, TYPES, "admin")
    loaded = await prices.load_price_settings(pg_session)
    assert loaded == prices.PriceSettings(groups, types, TYPES)
    assert loaded.types["Дилер_15"].group_rules == {
        "Расходка": PriceRule(BaseColumn.RETAIL, Decimal("0.85"))
    }


async def test_latest_upload_wins(pg_session: AsyncSession) -> None:
    await prices.save_price_groups(pg_session, ["Расходка"], "admin")
    await prices.save_price_types(pg_session, TYPES, "admin")
    await prices.save_price_groups(pg_session, ["Расходка", "Инструменты"], "manager")
    loaded = await prices.load_price_settings(pg_session)
    assert loaded.groups == ("РУБ", "Расходка", "Инструменты")
    assert await uploads(pg_session) == 3


async def test_invalid_types_not_saved(pg_session: AsyncSession) -> None:
    with pytest.raises(InvalidPriceRuleError, match="ценовой группы «Расходка» нет в справочнике"):
        await prices.save_price_types(pg_session, TYPES, "admin")
    assert await uploads(pg_session) == 0


async def test_groups_breaking_types_not_saved(pg_session: AsyncSession) -> None:
    await prices.save_price_groups(pg_session, ["Расходка"], "admin")
    await prices.save_price_types(pg_session, TYPES, "admin")
    message = (
        "справочник не сохранён, описание видов цен с ним не сходится: "
        "строка 3: ценовой группы «Расходка» нет в справочнике"
    )
    with pytest.raises(InvalidPriceRuleError, match=re.escape(message)):
        await prices.save_price_groups(pg_session, ["Инструменты"], "admin")
    assert (await prices.load_price_settings(pg_session)).groups == ("РУБ", "Расходка")
