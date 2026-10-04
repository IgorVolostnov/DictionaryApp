"""Покупатели из price_user.csv в базе.

Каждая выгрузка заменяет таблицу целиком: устойчивого кода покупателя в выгрузке нет,
наименование и e-mail меняются. Поэтому заявки хранят копию данных покупателя,
а не ссылку на строку таблицы. Транзакцией управляет вызывающий код.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.imports import ImportRejectedError, log_import
from app.db.models import Customer
from app.db.prices import load_price_settings
from app.sources.customers import CustomerRow, customer_key, find_duplicates

CUSTOMERS: Final = "customers"


@dataclass(frozen=True, slots=True)
class CustomersImport:
    total: int
    added: int  # таких наименования и набора e-mail в прошлой выгрузке не было
    removed: int  # были в прошлой выгрузке, в этой нет
    duplicates: tuple[str, ...]  # неразличимы: одинаковые наименование и e-mail
    unknown_price_types: tuple[str, ...]  # нет правила: цена для них не считается


async def import_customers(
    session: AsyncSession, rows: Sequence[CustomerRow], author: str, file_name: str
) -> CustomersImport:
    if not rows:
        raise ImportRejectedError("в файле нет ни одного покупателя, список не изменён")
    connection = await session.connection()
    old = await connection.execute(select(Customer.name, Customer.emails))
    before = {customer_key(row.name, row.emails) for row in old}
    after = {customer_key(row.name, row.emails) for row in rows}
    await connection.execute(delete(Customer))
    await connection.execute(insert(Customer), [_values(row) for row in rows])

    known = set((await load_price_settings(session)).types)
    result = CustomersImport(
        total=len(rows),
        added=len(after - before),
        removed=len(before - after),
        duplicates=tuple(group[0].name for group in find_duplicates(rows)),
        unknown_price_types=tuple(sorted({row.price_type for row in rows} - known)),
    )
    await log_import(
        session,
        source=CUSTOMERS,
        file_name=file_name,
        author=author,
        total=result.total,
        added=result.added,
        deactivated=result.removed,
    )
    return result


def _values(row: CustomerRow) -> dict[str, Any]:
    # psycopg превращает в массив PostgreSQL только list, не tuple.
    lists = {"emails": list(row.emails), "group_emails": list(row.group_emails)}
    return dataclasses.asdict(row) | lists
