"""Покупатели из price_user.csv.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "customer",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("emails", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("price_type", sa.Text(), nullable=False),
        sa.Column("credit_limit", sa.Numeric(), nullable=True),
        sa.Column("deferral_days", sa.Integer(), nullable=True),
        sa.Column("debt", sa.Numeric(), nullable=True),
        sa.Column("group_emails", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customer")),
    )


def downgrade() -> None:
    op.drop_table("customer")
