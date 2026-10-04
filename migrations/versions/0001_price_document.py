"""Загрузки справочника ценовых групп и описания видов цен.

Revision ID: 0001
Revises:
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "price_document",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("author", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("kind IN ('groups', 'types')", name=op.f("ck_price_document_kind")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_price_document")),
    )


def downgrade() -> None:
    op.drop_table("price_document")
