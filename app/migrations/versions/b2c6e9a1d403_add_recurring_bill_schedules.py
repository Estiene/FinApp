"""Add recurring bill frequencies while preserving existing monthly schedules.

Revision ID: b2c6e9a1d403
Revises: 7ab31d4e9c20
"""
from alembic import op
import sqlalchemy as sa

revision = "b2c6e9a1d403"
down_revision = "7ab31d4e9c20"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("bills", sa.Column("frequency", sa.String(length=20), nullable=False, server_default="monthly"))
    op.add_column("bills", sa.Column("next_due", sa.Date(), nullable=True))
    op.alter_column("bills", "frequency", server_default=None)


def downgrade():
    op.drop_column("bills", "next_due")
    op.drop_column("bills", "frequency")
