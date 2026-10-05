"""Снимок выгрузки 1С перед чтением.

1С перезаписывает файлы примерно раз в час. Если читать файл прямо в сетевой папке,
можно попасть на запись и получить обрезанный xlsx или половину csv. Поэтому читается
копия файла, который давно не менялся и не менялся, пока его копировали.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from shutil import copyfile
from typing import Final

_NS: Final = 1_000_000_000


@dataclass(frozen=True, slots=True)
class FileState:
    size: int
    mtime: datetime  # UTC, с точностью до микросекунды, как хранит PostgreSQL


@dataclass(frozen=True, slots=True)
class Snapshot:
    path: Path
    mtime: datetime  # время изменения исходного файла
    sha256: str


def file_state(path: Path) -> FileState:
    stat = path.stat()
    seconds, ns = divmod(stat.st_mtime_ns, _NS)
    mtime = datetime.fromtimestamp(seconds, UTC) + timedelta(microseconds=ns // 1000)
    return FileState(stat.st_size, mtime)


def take_snapshot(src: Path, dest_dir: Path, *, quiet: timedelta, now: datetime) -> Snapshot | None:
    """Копия src в dest_dir или None, если 1С, возможно, ещё пишет файл."""
    before = file_state(src)
    if now - before.mtime < quiet:
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    copyfile(src, dest)
    if file_state(src) != before:
        dest.unlink()
        return None
    with dest.open("rb") as f:
        digest = hashlib.file_digest(f, "sha256").hexdigest()
    return Snapshot(dest, before.mtime, digest)
