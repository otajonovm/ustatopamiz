"""Master work portfolio photos.

Revision ID: 003_master_portfolio
Revises: 002_production
Create Date: 2026-09-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_master_portfolio"
down_revision: Union[str, Sequence[str], None] = "002_production"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("masters")}
    if "portfolio_photo_ids" not in columns:
        op.add_column(
            "masters",
            sa.Column("portfolio_photo_ids", sa.Text(), nullable=False, server_default="[]"),
        )


def downgrade() -> None:
    op.drop_column("masters", "portfolio_photo_ids")
