"""Словарь синонимов; сортировка и ссылка на сайт у товаров; уникальный код 1С.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("product", sa.Column("sort_order", sa.Integer(), nullable=True))
    op.add_column("product", sa.Column("page_url", sa.Text(), nullable=True))
    op.create_unique_constraint(op.f("uq_product_code_1c"), "product", ["code_1c"])
    op.create_table(
        "alias",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("author", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("source IN ('access', 'manager')", name=op.f("ck_alias_source")),
        sa.ForeignKeyConstraint(
            ["product_id"], ["product.id"], name=op.f("fk_alias_product_id_product")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alias")),
        sa.UniqueConstraint("key", "product_id", name=op.f("uq_alias_key")),
    )
    op.create_index(op.f("ix_alias_product_id"), "alias", ["product_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_alias_product_id"), table_name="alias")
    op.drop_table("alias")
    op.drop_constraint(op.f("uq_product_code_1c"), "product", type_="unique")
    op.drop_column("product", "page_url")
    op.drop_column("product", "sort_order")
