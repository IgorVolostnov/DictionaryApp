from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.config import AppEnv, AuthMode, Settings, get_settings

BASE: dict[str, Any] = {
    "database_url": "postgresql+psycopg://app:pw@127.0.0.1/dictionary",
    "session_secret": "s" * 32,
}
OIDC: dict[str, Any] = {
    "oidc_issuer": "https://auth.example.ru/application/o/dictionary/",
    "oidc_client_id": "dictionary",
    "oidc_client_secret": "secret",
}
ENV_NAMES = (
    "APP_ENV", "AUTH_MODE", "OIDC_ISSUER", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET",
    "YANDEX_VISION_API_KEY", "YANDEX_FOLDER_ID", "DATABASE_URL", "SESSION_SECRET",
)  # fmt: skip


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def make(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **{**BASE, **overrides})


def test_prod_with_oidc() -> None:
    settings = make(**OIDC)
    assert settings.app_env is AppEnv.PROD
    assert settings.auth_mode is AuthMode.OIDC
    assert not settings.ocr_enabled


def test_dev_auth_forbidden_outside_dev() -> None:
    with pytest.raises(ValidationError, match="APP_ENV=dev"):
        make(auth_mode="dev", app_env="prod")


def test_dev_auth_allowed_in_dev() -> None:
    assert make(auth_mode="dev", app_env="dev").auth_mode is AuthMode.DEV


def test_oidc_requires_credentials() -> None:
    with pytest.raises(ValidationError, match="OIDC_ISSUER"):
        make()


def test_short_session_secret() -> None:
    with pytest.raises(ValidationError, match="SESSION_SECRET"):
        make(session_secret="short", **OIDC)


def test_ocr_enabled() -> None:
    assert make(**OIDC, yandex_vision_api_key="key", yandex_folder_id="folder").ocr_enabled


def test_get_settings_reads_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)  # чтобы не подхватился локальный .env
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("DATABASE_URL", BASE["database_url"])
    monkeypatch.setenv("SESSION_SECRET", BASE["session_secret"])
    get_settings.cache_clear()
    try:
        assert get_settings().app_env is AppEnv.DEV
    finally:
        get_settings.cache_clear()
