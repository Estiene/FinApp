"""Add credit card forecasting settings and active state.

Revision ID: c5d5a9b2e781
Revises: a5c0e2d7b914
"""
from alembic import op
import sqlalchemy as sa

revision = 'c5d5a9b2e781'
down_revision = 'a5c0e2d7b914'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('credit_cards') as batch_op:
        batch_op.add_column(sa.Column('annual_percentage_rate', sa.Numeric(5, 2), nullable=True))
        batch_op.add_column(sa.Column('credit_limit', sa.Numeric(12, 2), nullable=True))
        batch_op.add_column(sa.Column('promotional_apr', sa.Numeric(5, 2), nullable=True))
        batch_op.add_column(sa.Column('promotional_apr_end_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():
    with op.batch_alter_table('credit_cards') as batch_op:
        batch_op.drop_column('is_active')
        batch_op.drop_column('promotional_apr_end_date')
        batch_op.drop_column('promotional_apr')
        batch_op.drop_column('credit_limit')
        batch_op.drop_column('annual_percentage_rate')
