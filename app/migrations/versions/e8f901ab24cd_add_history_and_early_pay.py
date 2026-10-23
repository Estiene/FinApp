"""Preserve actual observations and forecast snapshots; account Early Pay."""
from alembic import op
import sqlalchemy as sa
revision = 'e8f901ab24cd'
down_revision = 'd7e8f901ab23'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('accounts') as batch:
        batch.add_column(sa.Column('early_pay_days', sa.Integer(), nullable=False, server_default='0'))
        batch.create_check_constraint('ck_account_early_pay_days', 'early_pay_days IN (0, 1, 2)')
    op.create_table('account_balance_observations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('accounts.id'), nullable=False),
        sa.Column('balance_date', sa.Date(), nullable=False),
        sa.Column('balance', sa.Numeric(12, 2), nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('source', sa.String(20), nullable=False))
    op.create_index('ix_account_balance_observations_account_id', 'account_balance_observations', ['account_id'])
    # Import only known dated observations, never fabricated earlier balances.
    op.execute(sa.text("INSERT INTO account_balance_observations (account_id, balance_date, balance, source) SELECT id, balance_as_of, starting_balance, 'imported' FROM accounts"))
    op.create_table('account_forecast_snapshots',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('accounts.id'), nullable=False),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('base_date', sa.Date(), nullable=False),
        sa.Column('base_balance', sa.Numeric(12, 2), nullable=False),
        sa.Column('horizon_days', sa.Integer(), nullable=False),
        sa.Column('early_pay_days', sa.Integer(), nullable=False))
    op.create_index('ix_account_forecast_snapshots_account_id', 'account_forecast_snapshots', ['account_id'])
    op.create_table('account_forecast_points',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('snapshot_id', sa.Integer(), sa.ForeignKey('account_forecast_snapshots.id'), nullable=False),
        sa.Column('balance_date', sa.Date(), nullable=False),
        sa.Column('balance', sa.Numeric(12, 2), nullable=False),
        sa.UniqueConstraint('snapshot_id', 'balance_date', name='uq_forecast_point_date'))


def downgrade():
    op.drop_table('account_forecast_points')
    op.drop_table('account_forecast_snapshots')
    op.drop_table('account_balance_observations')
    with op.batch_alter_table('accounts') as batch:
        batch.drop_constraint('ck_account_early_pay_days', type_='check')
        batch.drop_column('early_pay_days')
