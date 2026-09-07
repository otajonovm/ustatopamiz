"""Villages, suggestions, master portfolio and order address fields.

Revision ID: 004_villages_suggestions
Revises: 003_master_portfolio
Create Date: 2026-09-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004_villages_suggestions"
down_revision: Union[str, Sequence[str], None] = "003_master_portfolio"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

VILLAGES = [
    "Beshariq markaz",
    "Sobirtepa",
    "Beshovul",
    "Qoraqo'yli",
    "Uzun",
    "Temiryo'lchi",
    "Do'stlik",
    "Paxtakor",
    "Rapqon",
    "Kichik Rapqon",
    "Oqtepa",
    "Tovul",
    "Nayman",
    "Qaqir",
    "Dasht Qaqir",
    "Zarqishloq",
    "Beshsart",
    "Yakkatut",
    "Vatan",
    "Qoraqum",
    "Yangiyer",
    "Sariqqamish",
    "Cho'liq",
    "Toshqo'rg'on",
]


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    tables = _tables()
    if "villages" not in tables:
        op.create_table(
            "villages",
            sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
            sa.UniqueConstraint("name", name="uq_villages_name"),
        )
    if "suggestions" not in tables:
        op.create_table(
            "suggestions",
            sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
            sa.Column("type", sa.String(length=20), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("display_name", sa.String(length=100), nullable=False),
            sa.Column("counter", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("is_approved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.UniqueConstraint("type", "name", name="uq_suggestions_type_name"),
        )

    villages = sa.table(
        "villages",
        sa.column("name", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("order_index", sa.Integer),
    )
    existing = {row[0] for row in op.get_bind().execute(sa.text("SELECT name FROM villages")).fetchall()}
    rows = [
        {"name": name, "is_active": True, "order_index": index}
        for index, name in enumerate(VILLAGES)
        if name not in existing
    ]
    if rows:
        op.bulk_insert(villages, rows)

    with op.batch_alter_table("categories") as batch:
        batch.alter_column("name", existing_type=sa.String(length=100), type_=sa.String(length=150), nullable=False)

    masters_cols = _columns("masters")
    with op.batch_alter_table("masters") as batch:
        if "sub_skills" not in masters_cols:
            batch.add_column(sa.Column("sub_skills", sa.String(length=255), nullable=True))
        if "village_id" not in masters_cols:
            batch.add_column(sa.Column("village_id", sa.Integer(), nullable=True))
            batch.create_foreign_key("fk_masters_village_id", "villages", ["village_id"], ["id"], ondelete="SET NULL")
        if "custom_village" not in masters_cols:
            batch.add_column(sa.Column("custom_village", sa.String(length=100), nullable=True))
        if "sample_photos" not in masters_cols:
            batch.add_column(sa.Column("sample_photos", sa.Text(), nullable=True))
        batch.alter_column(
            "experience_years",
            existing_type=sa.Integer(),
            type_=sa.String(length=50),
            nullable=True,
        )

    if "portfolio_photo_ids" in _columns("masters") and "sample_photos" in _columns("masters"):
        op.execute(
            "UPDATE masters SET sample_photos = portfolio_photo_ids "
            "WHERE (sample_photos IS NULL OR sample_photos = '') AND portfolio_photo_ids IS NOT NULL"
        )

    orders_cols = _columns("orders")
    with op.batch_alter_table("orders") as batch:
        if "village_id" not in orders_cols:
            batch.add_column(sa.Column("village_id", sa.Integer(), nullable=True))
            batch.create_foreign_key("fk_orders_village_id", "villages", ["village_id"], ["id"])
        if "custom_address" not in orders_cols:
            batch.add_column(sa.Column("custom_address", sa.Text(), nullable=True))

    if "custom_address" in _columns("orders") and "region" in _columns("orders"):
        op.execute(
            "UPDATE orders SET custom_address = region "
            "WHERE (custom_address IS NULL OR custom_address = '') AND region IS NOT NULL AND region != ''"
        )
    if "custom_village" in _columns("masters") and "region" in _columns("masters"):
        op.execute(
            "UPDATE masters SET custom_village = region "
            "WHERE (custom_village IS NULL OR custom_village = '') AND region IS NOT NULL AND region != ''"
        )


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch:
        batch.drop_constraint("fk_orders_village_id", type_="foreignkey")
        batch.drop_column("custom_address")
        batch.drop_column("village_id")
    with op.batch_alter_table("masters") as batch:
        batch.drop_constraint("fk_masters_village_id", type_="foreignkey")
        batch.drop_column("sample_photos")
        batch.drop_column("custom_village")
        batch.drop_column("village_id")
        batch.drop_column("sub_skills")
    op.drop_table("suggestions")
    op.drop_table("villages")
