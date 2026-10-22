"""Add individual credit card payment history.

Revision ID: 8f1c2d3e4a5b
Revises: 36d73aff7c0a
"""

from alembic import op
import sqlalchemy as sa


revision = '8f1c2d3e4a5b'
down_revision = '36d73aff7c0a'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'credit_card_payments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('statement_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('payment_date', sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(
            ['statement_id'],
            ['credit_card_statements.id'],
        ),
    )


def downgrade():
    op.drop_table('credit_card_payments')
