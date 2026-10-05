from __future__ import annotations

import pytest

from app.db.imports import ImportRejectedError, ensure_small_drop


@pytest.mark.parametrize(("before", "lost", "limit"), [(0, 0, 20), (10, 2, 20), (10, 10, 100)])
def test_small_drop_allowed(before: int, lost: int, limit: int) -> None:
    ensure_small_drop(before, lost, limit)


def test_large_drop_rejected() -> None:
    with pytest.raises(ImportRejectedError) as error:
        ensure_small_drop(10, 3, 20)
    assert "пропадает 3 из 10 активных строк (30%)" in str(error.value)
