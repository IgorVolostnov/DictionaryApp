"""Отпечаток файла в журнале загрузок: таймер пропускает неизменившиеся выгрузки.

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("source_import", sa.Column("sha256", sa.Text(), nullable=True))
    op.add_column(
        "source_import", sa.Column("source_mtime", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("source_import", "source_mtime")
    op.drop_column("source_import", "sha256")
