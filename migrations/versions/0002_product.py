"""Товары из distr.xlsx и журнал загрузок.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "product",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("article", sa.Text(), nullable=False),
        sa.Column("code_1c", sa.Text(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("barcode", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Numeric(), nullable=True),
        sa.Column("price_distr", sa.Numeric(), nullable=True),
        sa.Column("price_dealer", sa.Numeric(), nullable=True),
        sa.Column("price_retail", sa.Numeric(), nullable=True),
        sa.Column("price_min_retail", sa.Numeric(), nullable=True),
        sa.Column("brand", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("photo", sa.Text(), nullable=True),
        sa.Column("extra_photos", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("weight_g", sa.Numeric(), nullable=True),
        sa.Column("length_mm", sa.Numeric(), nullable=True),
        sa.Column("width_mm", sa.Numeric(), nullable=True),
        sa.Column("height_mm", sa.Numeric(), nullable=True),
        sa.Column("volume_m3", sa.Numeric(), nullable=True),
        sa.Column("package", sa.Text(), nullable=True),
        sa.Column("country", sa.Text(), nullable=True),
        sa.Column("certificate_url", sa.Text(), nullable=True),
        sa.Column("certificate_until", sa.Text(), nullable=True),
        sa.Column("price_group", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product")),
        sa.UniqueConstraint("article", name=op.f("uq_product_article")),
    )
    op.create_table(
        "source_import",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("author", sa.Text(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("added", sa.Integer(), nullable=False),
        sa.Column("deactivated", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_import")),
    )


def downgrade() -> None:
    op.drop_table("source_import")
    op.drop_table("product")
