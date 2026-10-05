from __future__ import annotations

import hashlib
import os
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.sources import snapshot
from app.sources.snapshot import FileState, Snapshot, file_state, take_snapshot

T0 = datetime(2026, 10, 5, 9, 0, 0, 123456, tzinfo=UTC)
QUIET = timedelta(minutes=2)


def set_mtime(path: Path, when: datetime) -> None:
    """Время изменения файла с точностью до микросекунды."""
    ns = int(when.replace(microsecond=0).timestamp()) * 10**9 + when.microsecond * 1000
    os.utime(path, ns=(ns, ns))


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "ftp" / "distr.xlsx"
    path.parent.mkdir()
    path.write_bytes(b"data")
    set_mtime(path, T0)
    return path


def test_file_state(source: Path) -> None:
    assert file_state(source) == FileState(4, T0)


def test_quiet_file_copied(source: Path, tmp_path: Path) -> None:
    result = take_snapshot(source, tmp_path / "snap", quiet=QUIET, now=T0 + QUIET)
    digest = hashlib.sha256(b"data").hexdigest()
    assert result == Snapshot(tmp_path / "snap" / "distr.xlsx", T0, digest)
    assert result is not None
    assert result.path.read_bytes() == b"data"


def test_fresh_file_not_copied(source: Path, tmp_path: Path) -> None:
    soon = T0 + QUIET - timedelta(seconds=1)
    assert take_snapshot(source, tmp_path / "snap", quiet=QUIET, now=soon) is None
    assert not (tmp_path / "snap").exists()


def test_changed_during_copy(source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def copy_while_1c_writes(src: Path, dst: Path) -> None:
        shutil.copyfile(src, dst)
        src.write_bytes(b"data and more")

    monkeypatch.setattr(snapshot, "copyfile", copy_while_1c_writes)
    assert take_snapshot(source, tmp_path / "snap", quiet=QUIET, now=T0 + QUIET) is None
    assert not (tmp_path / "snap" / "distr.xlsx").exists()
