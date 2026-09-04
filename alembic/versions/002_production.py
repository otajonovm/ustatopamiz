"""Production schema: bans, payments, order lifecycle, extra categories.

Revision ID: 002_production
Revises: 001_initial
Create Date: 2026-09-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_production"
down_revision: Union[str, Sequence[str], None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    users_cols = _columns("users")
    if "is_banned" not in users_cols:
        op.add_column(
            "users",
            sa.Column("is_banned", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )

    masters_cols = _columns("masters")
    if "rating" not in masters_cols:
        op.add_column("masters", sa.Column("rating", sa.Float(), nullable=False, server_default="5.0"))
    if "completed_orders_count" not in masters_cols:
        op.add_column(
            "masters",
            sa.Column("completed_orders_count", sa.Integer(), nullable=False, server_default="0"),
        )
    if "warnings_count" not in masters_cols:
        op.add_column("masters", sa.Column("warnings_count", sa.Integer(), nullable=False, server_default="0"))

    inspector = sa.inspect(op.get_bind())
    unique_names = {item["name"] for item in inspector.get_unique_constraints("masters")}
    if "uq_master_user_category" in unique_names or "uq_masters_user_id" not in unique_names:
        with op.batch_alter_table("masters") as batch:
            if "uq_master_user_category" in unique_names:
                batch.drop_constraint("uq_master_user_category", type_="unique")
            if "uq_masters_user_id" not in unique_names:
                batch.create_unique_constraint("uq_masters_user_id", ["user_id"])

    orders_cols = _columns("orders")
    inspector = sa.inspect(op.get_bind())
    fk_names = {fk.get("name") for fk in inspector.get_foreign_keys("orders") if fk.get("name")}
    if "master_id" not in orders_cols:
        with op.batch_alter_table("orders") as batch:
            batch.add_column(sa.Column("master_id", sa.Integer(), nullable=True))
            batch.create_foreign_key("fk_orders_master_id", "masters", ["master_id"], ["id"])
    elif "fk_orders_master_id" not in fk_names:
        with op.batch_alter_table("orders") as batch:
            batch.create_foreign_key("fk_orders_master_id", "masters", ["master_id"], ["id"])
    if "client_rating" not in orders_cols:
        op.add_column("orders", sa.Column("client_rating", sa.Integer(), nullable=True))
    if "taken_at" not in orders_cols:
        op.add_column("orders", sa.Column("taken_at", sa.DateTime(timezone=True), nullable=True))
    if "voice_id" not in orders_cols and "voice_file_id" in orders_cols:
        with op.batch_alter_table("orders") as batch:
            batch.alter_column("voice_file_id", new_column_name="voice_id")
    elif "voice_id" not in orders_cols:
        op.add_column("orders", sa.Column("voice_id", sa.String(length=255), nullable=True))
    if "photo_id" not in orders_cols and "photo_file_id" in orders_cols:
        with op.batch_alter_table("orders") as batch:
            batch.alter_column("photo_file_id", new_column_name="photo_id")
    elif "photo_id" not in orders_cols:
        op.add_column("orders", sa.Column("photo_id", sa.String(length=255), nullable=True))

    op.execute("UPDATE orders SET status = 'pending_moderation' WHERE status IN ('new')")
    op.execute("UPDATE orders SET status = 'approved_open' WHERE status IN ('sent_to_group')")

    inspector = sa.inspect(op.get_bind())
    if "subscription_payments" not in inspector.get_table_names():
        op.create_table(
            "subscription_payments",
            sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
            sa.Column("master_id", sa.Integer(), nullable=False),
            sa.Column("receipt_photo_id", sa.String(length=255), nullable=False),
            sa.Column("amount", sa.Numeric(10, 2), nullable=False, server_default="30000.00"),
            sa.Column("days_added", sa.Integer(), nullable=False, server_default="30"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.ForeignKeyConstraint(["master_id"], ["masters.id"]),
        )

    categories = sa.table(
        "categories",
        sa.column("name", sa.String),
        sa.column("slug", sa.String),
        sa.column("group_id", sa.BigInteger),
        sa.column("is_active", sa.Boolean),
    )
    extra = [
        {"name": "Payvandchi", "slug": "payvandchi", "group_id": 0, "is_active": True},
        {"name": "Mebel/Duradgor", "slug": "mebel", "group_id": 0, "is_active": True},
        {"name": "Gaz/Kotyol", "slug": "gaz", "group_id": 0, "is_active": True},
        {"name": "Avtoservis", "slug": "avtoservis", "group_id": 0, "is_active": True},
    ]
    existing_slugs = {
        row[0] for row in op.get_bind().execute(sa.text("SELECT slug FROM categories")).fetchall()
    }
    op.bulk_insert(categories, [item for item in extra if item["slug"] not in existing_slugs])
    op.execute("UPDATE categories SET name = 'Maishiy texnika' WHERE slug = 'maishiy'")


def downgrade() -> None:
    op.drop_table("subscription_payments")
    with op.batch_alter_table("orders") as batch:
        batch.drop_constraint("fk_orders_master_id", type_="foreignkey")
        batch.drop_column("taken_at")
        batch.drop_column("client_rating")
        batch.drop_column("master_id")
    op.drop_column("masters", "warnings_count")
    op.drop_column("masters", "completed_orders_count")
    op.drop_column("masters", "rating")
    op.drop_column("users", "is_banned")
