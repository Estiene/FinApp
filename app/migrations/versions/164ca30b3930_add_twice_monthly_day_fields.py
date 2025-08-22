"""Add twice-monthly day fields

Revision ID: 164ca30b3930
Revises: 3cec62fbb3a2
Create Date: 2025-08-22 18:47:02.531459

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '164ca30b3930'
down_revision = '3cec62fbb3a2'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add due_day nullable
    with op.batch_alter_table('bill', schema=None) as batch_op:
        batch_op.add_column(sa.Column('due_day', sa.Integer(), nullable=True))

    # 2. Backfill existing rows from due_date
    op.execute(
        "UPDATE bill "
        "SET due_day = EXTRACT(DAY FROM due_date)::integer "
        "WHERE due_date IS NOT NULL"
    )

    # 3. Make due_day NOT NULL now that it’s populated
    with op.batch_alter_table('bill', schema=None) as batch_op:
        batch_op.alter_column(
            'due_day',
            existing_type=sa.Integer(),
            nullable=False
        )

    # 4. Drop the old due_date column
    with op.batch_alter_table('bill', schema=None) as batch_op:
        batch_op.drop_column('due_date')

    # 5. Add twice-monthly fields to income and allow next_pay to be nullable
    with op.batch_alter_table('income', schema=None) as batch_op:
        batch_op.add_column(sa.Column('day_of_month_1', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('day_of_month_2', sa.Integer(), nullable=True))
        batch_op.alter_column(
            'next_pay',
            existing_type=sa.DATE(),
            nullable=True
        )


def downgrade():
    # Revert income table
    with op.batch_alter_table('income', schema=None) as batch_op:
        batch_op.alter_column(
            'next_pay',
            existing_type=sa.DATE(),
            nullable=False
        )
        batch_op.drop_column('day_of_month_2')
        batch_op.drop_column('day_of_month_1')

    # Revert bill table: add due_date then drop due_day
    with op.batch_alter_table('bill', schema=None) as batch_op:
        batch_op.add_column(sa.Column('due_date', sa.DATE(), nullable=False))
        batch_op.drop_column('due_day')

