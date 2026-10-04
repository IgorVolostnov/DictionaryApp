from __future__ import annotations

import dataclasses
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.customers import CustomersImport, import_customers
from app.db.imports import ImportRejectedError
from app.db.models import Customer, SourceImport
from app.sources.customers import CustomerRow

pytestmark = [pytest.mark.db, pytest.mark.asyncio]

BASE = CustomerRow(
    name="",
    emails=(),
    price_type="Дилерская",
    credit_limit=None,
    deferral_days=None,
    debt=None,
    group_emails=(),
)


def row(name: str, *emails: str, **changes: Any) -> CustomerRow:
    return dataclasses.replace(BASE, name=name, emails=emails, **changes)


async def customers(session: AsyncSession) -> dict[str, Customer]:
    return {c.name: c for c in await session.scalars(select(Customer))}


async def test_first_import(pg_session: AsyncSession) -> None:
    rows = [
        row(
            "ООО Ромашка",
            "a@r.ru",
            "b@r.ru",
            credit_limit=Decimal(50000),
            deferral_days=14,
            debt=Decimal("-1200.50"),
            group_emails=("main@r.ru",),
        ),
        row("ИП Иванов", "i@i.ru", price_type="Холдинг"),
    ]
    result = await import_customers(pg_session, rows, "admin", "price_user.csv")
    assert result == CustomersImport(2, 2, 0, (), ("Холдинг",))
    saved = (await customers(pg_session))["ООО Ромашка"]
    assert (saved.emails, saved.group_emails) == (["a@r.ru", "b@r.ru"], ["main@r.ru"])
    assert saved.credit_limit == Decimal(50000)
    assert saved.deferral_days == 14
    assert saved.debt == Decimal("-1200.50")
    log = await pg_session.scalar(select(SourceImport))
    assert log is not None
    assert (log.source, log.total, log.added, log.deactivated) == ("customers", 2, 2, 0)


async def test_next_import_replaces_all(pg_session: AsyncSession) -> None:
    first = [row("А", "a@a.ru"), row("Б", "b@b.ru")]
    await import_customers(pg_session, first, "admin", "1.csv")
    second = [row("А", "a@a.ru", debt=Decimal(700)), row("В", "v@v.ru")]
    result = await import_customers(pg_session, second, "admin", "2.csv")
    assert result == CustomersImport(2, 1, 1, (), ())
    saved = await customers(pg_session)
    assert sorted(saved) == ["А", "В"]
    assert saved["А"].debt == Decimal(700)


async def test_indistinguishable_customers_kept(pg_session: AsyncSession) -> None:
    rows = [
        row("ООО  Ромашка", "a@r.ru"),
        row("ооо ромашка", "a@r.ru"),
        row("ООО Ромашка", "b@r.ru"),
    ]
    result = await import_customers(pg_session, rows, "admin", "price_user.csv")
    assert result.duplicates == ("ООО  Ромашка",)
    assert (result.total, result.added) == (3, 2)


async def test_empty_file_rejected(pg_session: AsyncSession) -> None:
    await import_customers(pg_session, [row("А", "a@a.ru")], "admin", "1.csv")
    with pytest.raises(ImportRejectedError, match="нет ни одного покупателя"):
        await import_customers(pg_session, [], "admin", "2.csv")
    assert list(await customers(pg_session)) == ["А"]
