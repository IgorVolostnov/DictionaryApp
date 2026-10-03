"""Ожидаемые ошибки предметной области.

Текст показывается пользователю как есть, поэтому он по-русски и объясняет,
что делать. Обработчик в api/ превращает эти ошибки в ответ 4xx.
"""


class DomainError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidInputError(DomainError):
    """Неверные параметры разбора заявки."""


class InvalidAliasKeyError(DomainError):
    """Синоним нельзя сохранить."""


class InvalidPriceRuleError(DomainError):
    """Неверная настройка типа цен."""
