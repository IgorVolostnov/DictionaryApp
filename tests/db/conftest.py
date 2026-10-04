"""Тесты с PostgreSQL. База: TEST_DATABASE_URL из окружения или .env."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


class _TestDatabase(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    test_database_url: str = ""


@pytest.fixture(scope="session")
def pg_url() -> str:
    """Тестовая база со схемой из миграций. Миграции проверяются в обе стороны."""
    url = _TestDatabase().test_database_url
    if not url:
        pytest.skip("TEST_DATABASE_URL не задан")
    if not (make_url(url).database or "").endswith("_test"):
        pytest.fail("Имя базы в TEST_DATABASE_URL должно оканчиваться на _test")
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    for step in (command.downgrade, command.upgrade, command.downgrade, command.upgrade):
        step(config, "base" if step is command.downgrade else "head")
    return url


@pytest_asyncio.fixture
async def pg_session(pg_url: str) -> AsyncIterator[AsyncSession]:
    """Сессия в транзакции, которая откатывается после теста."""
    engine = create_async_engine(pg_url, poolclass=NullPool)
    async with engine.connect() as connection:
        await connection.begin()
        session = AsyncSession(bind=connection, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            await session.close()
            await connection.rollback()
    await engine.dispose()
