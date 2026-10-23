from datetime import date
from decimal import Decimal

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Account(db.Model):
    __tablename__ = 'accounts'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    starting_balance = db.Column(
        db.Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    # Snapshot balance at the end of this date; later scheduled events are projected.
    balance_as_of = db.Column(db.Date, nullable=False, default=date.today)

    # relationships
    bills = db.relationship(
        'Bill', back_populates='account', cascade='all, delete-orphan'
    )
    incomes = db.relationship(
        'Income', back_populates='account', cascade='all, delete-orphan'
    )


class Bill(db.Model):
    __tablename__ = 'bills'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    owner = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default='true')
    inactive_from = db.Column(db.Date, nullable=True)
    pauses = db.relationship('BillPause', cascade='all, delete-orphan')
    due_day = db.Column(db.Integer, nullable=False)
    # Existing records default to monthly; interval schedules use next_due as anchor.
    frequency = db.Column(db.String(20), nullable=False, default="monthly")
    next_due = db.Column(db.Date, nullable=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)

    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=False)
    account = db.relationship('Account', back_populates='bills')
    # Optional credit card used to pay this recurring bill.
    # NULL means the bill is paid directly from its assigned bank account.
    credit_card_id = db.Column(
        db.Integer,
        db.ForeignKey('credit_cards.id'),
        nullable=True,
    )
    credit_card = db.relationship(
        'CreditCard',
        back_populates='bills',
    )

class BillPause(db.Model):
    __tablename__ = 'bill_pauses'
    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(db.Integer, db.ForeignKey('bills.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)


class Income(db.Model):
    __tablename__ = 'incomes'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    frequency = db.Column(db.String(20), nullable=False)
    next_pay = db.Column(db.Date, nullable=True)
    day_of_month_1 = db.Column(db.Integer, nullable=True)
    day_of_month_2 = db.Column(db.Integer, nullable=True)

    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=False)
    account = db.relationship('Account', back_populates='incomes')

class CreditCard(db.Model):
    __tablename__ = 'credit_cards'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)

    # Outstanding card debt as of the snapshot date.
    balance = db.Column(
        db.Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    balance_as_of = db.Column(
        db.Date, nullable=False, default=date.today
    )

    statement_close_day = db.Column(db.Integer, nullable=False)
    payment_due_day = db.Column(db.Integer, nullable=False)

    minimum_payment = db.Column(
        db.Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    extra_payment = db.Column(
        db.Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )

    # Stage 5A: independent recurring extra-payment date; NULL means due day.
    extra_payment_day = db.Column(db.Integer, nullable=True)
    # Bill-related payments may be due on the statement due date or earlier.
    bill_payment_timing = db.Column(
        db.String(20), nullable=False, default="due_date",
        server_default="due_date",
    )
    bill_payment_days_before = db.Column(
        db.Integer, nullable=False, default=0, server_default="0",
    )

    # Optional forecasting inputs. NULL means not supplied by the user.
    annual_percentage_rate = db.Column(db.Numeric(5, 2), nullable=True)
    credit_limit = db.Column(db.Numeric(12, 2), nullable=True)
    promotional_apr = db.Column(db.Numeric(5, 2), nullable=True)
    promotional_apr_end_date = db.Column(db.Date, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default='true')

    payment_account_id = db.Column(
        db.Integer,
        db.ForeignKey('accounts.id'),
        nullable=False,
    )
    payment_account = db.relationship('Account')
    statements = db.relationship(
        'CreditCardStatement',
        back_populates='credit_card',
        cascade='all, delete-orphan',
    )
    bills = db.relationship(
        'Bill',
        back_populates='credit_card',
    )
class CreditCardStatement(db.Model):
    __tablename__ = 'credit_card_statements'

    id = db.Column(db.Integer, primary_key=True)

    credit_card_id = db.Column(
        db.Integer,
        db.ForeignKey('credit_cards.id'),
        nullable=False,
    )

    statement_close_date = db.Column(db.Date, nullable=False)
    payment_due_date = db.Column(db.Date, nullable=False)

    # Confirmed balance from the card issuer.
    statement_balance = db.Column(db.Numeric(12, 2), nullable=True)

    # Optional override of the automatically suggested payment.
    planned_payment = db.Column(db.Numeric(12, 2), nullable=True)

    # Completed payment information.
    actual_payment = db.Column(db.Numeric(12, 2), nullable=True)
    payment_date = db.Column(db.Date, nullable=True)

    credit_card = db.relationship(
        'CreditCard',
        back_populates='statements',
    )

    payments = db.relationship(
        'CreditCardPayment',
        back_populates='statement',
        cascade='all, delete-orphan',
    )

    __table_args__ = (
        db.UniqueConstraint(
            'credit_card_id',
            'statement_close_date',
            name='uq_credit_card_statement_cycle',
        ),
    )


class CreditCardPayment(db.Model):
    __tablename__ = 'credit_card_payments'

    id = db.Column(db.Integer, primary_key=True)

    statement_id = db.Column(
        db.Integer,
        db.ForeignKey('credit_card_statements.id'),
        nullable=False,
    )

    amount = db.Column(db.Numeric(12, 2), nullable=False)
    payment_date = db.Column(db.Date, nullable=False)

    statement = db.relationship(
        'CreditCardStatement',
        back_populates='payments',
    )
