"""Add recurring bill active state and effective deactivation date."""
from alembic import op
import sqlalchemy as sa
revision = 'd7e8f901ab23'
down_revision = 'c5d5a9b2e781'
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table('bills') as batch:
        batch.add_column(sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch.add_column(sa.Column('inactive_from', sa.Date(), nullable=True))

    op.create_table('bill_pauses',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('bill_id', sa.Integer(), sa.ForeignKey('bills.id'), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False))

def downgrade():
    op.drop_table('bill_pauses')
    with op.batch_alter_table('bills') as batch:
        batch.drop_column('inactive_from')
        batch.drop_column('is_active')
