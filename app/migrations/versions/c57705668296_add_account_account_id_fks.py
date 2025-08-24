"""add Account + account_id FKs

Revision ID: c57705668296
Revises: 2c4c88376851
Create Date: 2025-08-24 12:33:18.799815

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c57705668296'
down_revision = '2c4c88376851'
branch_labels = None
depends_on = None


def upgrade():
    # 1. create accounts table
    op.create_table(
        'accounts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False, unique=True),
    )

    # 2. add account_id columns as nullable
    with op.batch_alter_table('bills') as batch_op:
        batch_op.add_column(sa.Column('account_id', sa.Integer(), nullable=True))
    with op.batch_alter_table('incomes') as batch_op:
        batch_op.add_column(sa.Column('account_id', sa.Integer(), nullable=True))

    # 3. backfill existing rows onto a default account
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "INSERT INTO accounts (name) VALUES ('Default Account') RETURNING id"
    ))
    default_id = result.scalar()
    conn.execute(sa.text("UPDATE bills   SET account_id = :id"), {'id': default_id})
    conn.execute(sa.text("UPDATE incomes SET account_id = :id"), {'id': default_id})

    # 4. enforce NOT NULL + add foreign keys
    with op.batch_alter_table('bills') as batch_op:
        batch_op.alter_column('account_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key('fk_bills_account_id', 'accounts',
                                   ['account_id'], ['id'])
    with op.batch_alter_table('incomes') as batch_op:
        batch_op.alter_column('account_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key('fk_incomes_account_id', 'accounts',
                                   ['account_id'], ['id'])

def downgrade():
    with op.batch_alter_table('bills') as batch_op:
        batch_op.drop_constraint('fk_bills_account_id', type_='foreignkey')
        batch_op.drop_column('account_id')
    with op.batch_alter_table('incomes') as batch_op:
        batch_op.drop_constraint('fk_incomes_account_id', type_='foreignkey')
        batch_op.drop_column('account_id')
    op.drop_table('accounts')