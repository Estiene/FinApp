"""Add saved starting balances for dashboard projections.

Revision ID: 7ab31d4e9c20
Revises: c57705668296
Create Date: 2026-10-20
"""
from alembic import op
import sqlalchemy as sa

revision = "7ab31d4e9c20"
down_revision = "c57705668296"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "accounts",
        sa.Column(
            "starting_balance",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default=sa.text("0.00"),
        ),
    )
    op.add_column(
        "accounts",
        sa.Column(
            "balance_as_of",
            sa.Date(),
            nullable=False,
            server_default=sa.text("CURRENT_DATE"),
        ),
    )
    # Keep defaults in the model/application rather than as permanent DB defaults.
    op.alter_column("accounts", "starting_balance", server_default=None)
    op.alter_column("accounts", "balance_as_of", server_default=None)


def downgrade():
    op.drop_column("accounts", "balance_as_of")
    op.drop_column("accounts", "starting_balance")
