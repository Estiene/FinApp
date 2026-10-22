"""Add Stage 5A credit card payment scheduling settings.

Revision ID: a5c0e2d7b914
Revises: 8f1c2d3e4a5b
"""
from alembic import op
import sqlalchemy as sa

revision = 'a5c0e2d7b914'
down_revision = '8f1c2d3e4a5b'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('credit_cards', sa.Column('extra_payment_day', sa.Integer(), nullable=True))
    op.add_column('credit_cards', sa.Column(
        'bill_payment_timing', sa.String(length=20), nullable=False,
        server_default='due_date',
    ))
    op.add_column('credit_cards', sa.Column(
        'bill_payment_days_before', sa.Integer(), nullable=False,
        server_default='0',
    ))
    op.create_check_constraint(
        'ck_card_extra_payment_day', 'credit_cards',
        'extra_payment_day IS NULL OR extra_payment_day BETWEEN 1 AND 31',
    )
    op.create_check_constraint(
        'ck_card_bill_payment_timing', 'credit_cards',
        "bill_payment_timing IN ('due_date', 'days_before_due')",
    )
    op.create_check_constraint(
        'ck_card_bill_days_before', 'credit_cards',
        'bill_payment_days_before BETWEEN 0 AND 31',
    )


def downgrade():
    op.drop_constraint('ck_card_bill_days_before', 'credit_cards', type_='check')
    op.drop_constraint('ck_card_bill_payment_timing', 'credit_cards', type_='check')
    op.drop_constraint('ck_card_extra_payment_day', 'credit_cards', type_='check')
    op.drop_column('credit_cards', 'bill_payment_days_before')
    op.drop_column('credit_cards', 'bill_payment_timing')
    op.drop_column('credit_cards', 'extra_payment_day')
