"""Сопоставление разобранной заявки с каталогом."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.parse_input import InputRow, ParsedInput
from app.domain.search import LineMatch, SearchIndex, Status


@dataclass(frozen=True, slots=True)
class MatchedRow:
    row: InputRow
    match: LineMatch

    @property
    def ready(self) -> bool:
        """Можно выгружать в 1С: товар найден однозначно и количество известно."""
        return self.match.status is Status.FOUND and self.row.quantity is not None


def match_rows(parsed: ParsedInput, index: SearchIndex) -> tuple[MatchedRow, ...]:
    return tuple(MatchedRow(row, index.find(row.name)) for row in parsed.rows)
