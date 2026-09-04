"""Initial schema and category seeds.

Revision ID: 001_initial
Revises:
Create Date: 2026-09-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("full_name", sa.String(length=150), nullable=False),
        sa.Column("phone_number", sa.String(length=20), nullable=True),
        sa.Column(
            "role",
            sa.Enum("client", "master", "admin", name="user_role"),
            nullable=False,
            server_default="client",
        ),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=50), nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint("slug", name="uq_categories_slug"),
    )

    op.create_table(
        "masters",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("region", sa.String(length=100), nullable=False),
        sa.Column("experience_years", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "approved", "rejected", name="master_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("subscription_until", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "category_id", name="uq_master_user_category"),
    )

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("region", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("voice_file_id", sa.String(length=255), nullable=True),
        sa.Column("photo_file_id", sa.String(length=255), nullable=True),
        sa.Column(
            "status",
            sa.Enum("new", "sent_to_group", "taken", "completed", "cancelled", name="order_status"),
            nullable=False,
            server_default="new",
        ),
        sa.Column("group_message_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["client_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
    )

    categories = sa.table(
        "categories",
        sa.column("name", sa.String),
        sa.column("slug", sa.String),
        sa.column("group_id", sa.BigInteger),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(
        categories,
        [
            {"name": "Santexnika", "slug": "santexnika", "group_id": 0, "is_active": True},
            {"name": "Elektr", "slug": "elektr", "group_id": 0, "is_active": True},
            {"name": "Muzlatgich/Konditsioner", "slug": "maishiy", "group_id": 0, "is_active": True},
            {"name": "Qurilish", "slug": "qurilish", "group_id": 0, "is_active": True},
        ],
    )


def downgrade() -> None:
    op.drop_table("orders")
    op.drop_table("masters")
    op.drop_table("categories")
    op.drop_index("ix_users_telegram_id", table_name="users")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS order_status")
    op.execute("DROP TYPE IF EXISTS master_status")
    op.execute("DROP TYPE IF EXISTS user_role")
