from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import SourceSettings
from app.db.customers import CUSTOMERS
from app.db.models import Customer, Product, SourceImport
from app.db.products import DISTR
from app.db.sync import Outcome, SyncResult, lock_name, sync_source
from tests.unit.test_snapshot import set_mtime
from tests.unit.test_sources import DISTR_HEADER, distr_row, write_csv, write_xlsx

pytestmark = [pytest.mark.db, pytest.mark.asyncio]

T0 = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)
CHECK = T0 + timedelta(minutes=10)  # файл уже давно не менялся


def make_settings(tmp_path: Path) -> SourceSettings:
    values: dict[str, Any] = {
        "database_url": "postgresql+psycopg://unused@localhost/unused",
        "distr_path": tmp_path / "distr.xlsx",
        "customers_path": tmp_path / "price_user.csv",
        "snapshot_dir": tmp_path / "snapshots",
    }
    return SourceSettings(_env_file=None, **values)


def write_distr(path: Path, articles: Sequence[str], mtime: datetime = T0) -> None:
    rows: list[Sequence[object]] = [
        DISTR_HEADER,
        *(distr_row({"Артикул": a, "Код в 1С": f"К-{a}"}) for a in articles),
    ]
    write_xlsx(path, rows)
    set_mtime(path, mtime)


async def active(session: AsyncSession) -> set[str]:
    return set(await session.scalars(select(Product.article).where(Product.active)))


async def imports(session: AsyncSession, source: str) -> list[SourceImport]:
    query = select(SourceImport).where(SourceImport.source == source).order_by(SourceImport.id)
    return list(await session.scalars(query))


async def test_import_then_unchanged(pg_session: AsyncSession, tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_distr(settings.distr_path, ["A1", "A2"])
    result = await sync_source(pg_session, DISTR, settings, CHECK)
    assert result.outcome is Outcome.IMPORTED
    assert "товаров 2, новых 2" in result.message
    assert await active(pg_session) == {"A1", "A2"}
    assert await sync_source(pg_session, DISTR, settings, CHECK) == SyncResult(Outcome.UNCHANGED)
    # 1С переписала файл тем же содержимым: загрузки нет, новое время запомнено.
    rewritten = T0 + timedelta(hours=1)
    set_mtime(settings.distr_path, rewritten)
    again = await sync_source(pg_session, DISTR, settings, rewritten + timedelta(minutes=10))
    assert again.outcome is Outcome.UNCHANGED
    (log,) = await imports(pg_session, DISTR)
    assert (log.author, log.source_mtime) == ("таймер", rewritten)
    assert log.sha256 is not None
    assert len(log.sha256) == 64


async def test_fresh_file_waits(pg_session: AsyncSession, tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_distr(settings.distr_path, ["A1"])
    soon = T0 + timedelta(seconds=30)
    assert await sync_source(pg_session, DISTR, settings, soon) == SyncResult(Outcome.NOT_READY)
    assert await active(pg_session) == set()


async def test_missing_file(pg_session: AsyncSession, tmp_path: Path) -> None:
    result = await sync_source(pg_session, DISTR, make_settings(tmp_path), CHECK)
    assert result.outcome is Outcome.MISSING
    assert "distr.xlsx" in result.message


async def test_unreadable_file_rejected(pg_session: AsyncSession, tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    settings.distr_path.write_text("не xlsx", encoding="utf-8")
    set_mtime(settings.distr_path, T0)
    result = await sync_source(pg_session, DISTR, settings, CHECK)
    assert result.outcome is Outcome.REJECTED
    assert "ошибка открытия xlsx" in result.message
    assert await imports(pg_session, DISTR) == []


async def test_mass_deactivation_needs_force(pg_session: AsyncSession, tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    articles = [f"A{i}" for i in range(10)]
    write_distr(settings.distr_path, articles)
    await sync_source(pg_session, DISTR, settings, CHECK)
    later = T0 + timedelta(hours=1)
    write_distr(settings.distr_path, articles[:7], later)
    check = later + timedelta(minutes=10)
    result = await sync_source(pg_session, DISTR, settings, check)
    assert result.outcome is Outcome.REJECTED
    assert "пропадает 3 из 10" in result.message
    assert await active(pg_session) == set(articles)
    assert len(await imports(pg_session, DISTR)) == 1
    forced = await sync_source(pg_session, DISTR, settings, check, force=True)
    assert forced.outcome is Outcome.IMPORTED
    assert await active(pg_session) == set(articles[:7])


async def test_customers(pg_session: AsyncSession, tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_csv(settings.customers_path, "ИП Иванов;a@b.ru;Дилерская;0;7;;;end;")
    set_mtime(settings.customers_path, T0)
    result = await sync_source(pg_session, CUSTOMERS, settings, CHECK)
    assert result.outcome is Outcome.IMPORTED
    assert "покупателей 1, новых 1" in result.message
    assert list(await pg_session.scalars(select(Customer.name))) == ["ИП Иванов"]


async def test_busy(pg_session: AsyncSession, pg_url: str, tmp_path: Path) -> None:
    engine = create_async_engine(pg_url, poolclass=NullPool)
    try:
        async with engine.connect() as other, other.begin():
            name = func.hashtext(lock_name(DISTR))
            await other.execute(select(func.pg_advisory_xact_lock(name)))
            result = await sync_source(pg_session, DISTR, make_settings(tmp_path), CHECK)
    finally:
        await engine.dispose()
    assert result == SyncResult(Outcome.BUSY)
