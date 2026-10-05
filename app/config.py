"""Все настройки приложения. Единственное место, где читается окружение."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_SECRET_LENGTH = 32


class AppEnv(StrEnum):
    DEV = "dev"
    TEST = "test"
    PROD = "prod"


class AuthMode(StrEnum):
    OIDC = "oidc"
    DEV = "dev"


class DatabaseSettings(BaseSettings):
    """Только адрес базы: для миграций и инструментов, которым не нужен вход."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str


class SourceSettings(DatabaseSettings):
    """Выгрузки 1С для импорта по таймеру. На разработке — копии в input/."""

    distr_path: Path = Path("input/distr.xlsx")
    customers_path: Path = Path("input/price_user.csv")
    snapshot_dir: Path = Path("output/snapshots")
    # Файл, изменённый позже, возможно, ещё пишется 1С: его загрузит следующий запуск.
    quiet_seconds: int = Field(default=120, ge=0)
    # Сколько процентов активных товаров или покупателей может пропасть за одну загрузку.
    max_drop_percent: int = Field(default=20, ge=0, le=100)


class Settings(DatabaseSettings):
    # По умолчанию prod: забытая настройка не должна ослаблять защиту.
    app_env: AppEnv = AppEnv.PROD
    auth_mode: AuthMode = AuthMode.OIDC

    session_secret: SecretStr

    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: SecretStr = SecretStr("")

    yandex_vision_api_key: SecretStr = SecretStr("")
    yandex_folder_id: str = ""

    photo_base_url: str = "https://www.rossvik.moscow"
    max_rows_per_request: int = Field(default=2000, ge=1, le=10_000)
    stale_after_minutes: int = Field(default=120, ge=1)

    @property
    def ocr_enabled(self) -> bool:
        return bool(self.yandex_vision_api_key.get_secret_value() and self.yandex_folder_id)

    @model_validator(mode="after")
    def _check_security(self) -> Self:
        if len(self.session_secret.get_secret_value()) < MIN_SECRET_LENGTH:
            raise ValueError("SESSION_SECRET должен быть не короче 32 символов")
        if self.auth_mode is AuthMode.DEV:
            if self.app_env is not AppEnv.DEV:
                raise ValueError("AUTH_MODE=dev разрешён только при APP_ENV=dev")
        elif not (
            self.oidc_issuer and self.oidc_client_id and self.oidc_client_secret.get_secret_value()
        ):
            raise ValueError(
                "Для AUTH_MODE=oidc нужны OIDC_ISSUER, OIDC_CLIENT_ID и OIDC_CLIENT_SECRET"
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
