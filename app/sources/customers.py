"""price_user.csv — выгрузка покупателей из 1C: вид цен, кредит, отсрочка, долг."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Final

from app.sources.cells import Loaded, Record, SourceFormatError, load

COLUMNS: Final = (
    "Покупатель",
    "e-mail",
    "ВидЦены",
    "МаксимальнаяСуммаКредитаОтгрузки",
    "МаксимальнаяОтсрочкаОплаты",
    "СуммаДолга",
    "emailОсновногоКонтрагента",
    "end",
)
# Строка заканчивается меткой «end». Если метка не на своём месте, поля сдвинулись.
END_MARK: Final = "end"
# Лимит 0 или 1 в 1С означает работу только по предоплате.
PREPAYMENT_LIMIT: Final = Decimal(1)
_EMAIL_SEPARATORS: Final = re.compile(r"[\s,;]+")


@dataclass(frozen=True, slots=True)
class CustomerRow:
    name: str
    emails: tuple[str, ...]
    price_type: str
    credit_limit: Decimal | None
    deferral_days: int | None
    debt: Decimal | None
    group_emails: tuple[str, ...]

    @property
    def prepayment_only(self) -> bool:
        """Только предоплата: лимит пустой, 0 или 1."""
        return self.credit_limit is None or self.credit_limit <= PREPAYMENT_LIMIT


def read_price_users(path: Path) -> Loaded[CustomerRow]:
    try:
        content = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SourceFormatError(f"{path.name}: ожидалась кодировка UTF-8 ({exc.reason})") from exc
    return load((split_fields(line) for line in content.splitlines()), COLUMNS, _customer)


def split_fields(line: str) -> list[str]:
    """Поля строки.

    Поля 1С разделяет «;» без пробела, а адреса в списке e-mail — «; » с пробелом.
    Кусок, который начинается с пробела, — продолжение списка адресов, но только если
    в предыдущем поле уже есть адрес. Иначе это новое поле: в 1С e-mail бывает записан
    с пробелом в начале («Ушаков; exalex@bk.ru ;Дилерская;...»).
    """
    fields: list[str] = []
    for piece in line.split(";"):
        if fields and piece.startswith(" ") and "@" in fields[-1]:
            fields[-1] += ";" + piece
        else:
            fields.append(piece)
    return fields



def customer_key(name: str, emails: Iterable[str]) -> tuple[str, frozenset[str]]:
    """Наименование без учёта регистра и лишних пробелов плюс набор e-mail."""
    return " ".join(name.split()).casefold(), frozenset(emails)


def find_duplicates(rows: Iterable[CustomerRow]) -> list[tuple[CustomerRow, ...]]:
    """Покупатели, которых нельзя различить: совпадают наименование и набор e-mail."""
    groups: defaultdict[tuple[str, frozenset[str]], list[CustomerRow]] = defaultdict(list)
    for row in rows:
        groups[customer_key(row.name, row.emails)].append(row)
    return [tuple(group) for group in groups.values() if len(group) > 1]



def _customer(row: Record) -> CustomerRow:
    if row.text("end") != END_MARK:
        raise ValueError("сдвиг полей: лишняя или потерянная «;»")
    return CustomerRow(
        name=row.required("Покупатель"),
        emails=_emails(row.text("e-mail")),
        price_type=row.required("ВидЦены"),
        credit_limit=row.number("МаксимальнаяСуммаКредитаОтгрузки"),
        deferral_days=_days(row, "МаксимальнаяОтсрочкаОплаты"),
        debt=row.number("СуммаДолга"),
        group_emails=_emails(row.text("emailОсновногоКонтрагента")),
    )


def _emails(value: str | None) -> tuple[str, ...]:
    """Адреса в нижнем регистре и без повторов. Куски без «@» отбрасываются."""
    tokens = _EMAIL_SEPARATORS.split(value or "")
    return tuple(dict.fromkeys(token.lower() for token in tokens if "@" in token))


def _days(row: Record, column: str) -> int | None:
    value = row.number(column)
    if value is None:
        return None
    if value < 0 or value != value.to_integral_value():
        raise ValueError(f"«{column}»: {value} — нужно целое число дней")
    return int(value)
