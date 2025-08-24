from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Account(db.Model):
    __tablename__ = 'accounts'

    id       = db.Column(db.Integer, primary_key=True)
    name     = db.Column(db.String(100), nullable=False, unique=True)

    # relationships
    bills    = db.relationship('Bill',   back_populates='account', cascade='all, delete-orphan')
    incomes  = db.relationship('Income', back_populates='account', cascade='all, delete-orphan')

class Bill(db.Model):
    __tablename__ = 'bills'

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(100), nullable=False)
    owner      = db.Column(db.String(100), nullable=False)
    due_day    = db.Column(db.Integer, nullable=False)
    amount     = db.Column(db.Numeric(10,2), nullable=False)

    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=False)
    account    = db.relationship('Account', back_populates='bills')

class Income(db.Model):
    __tablename__ = 'incomes'

    id              = db.Column(db.Integer, primary_key=True)
    name            = db.Column(db.String(100), nullable=False)
    amount          = db.Column(db.Numeric(10,2), nullable=False)
    frequency       = db.Column(db.String(20), nullable=False)
    next_pay        = db.Column(db.Date, nullable=True)
    day_of_month_1  = db.Column(db.Integer, nullable=True)
    day_of_month_2  = db.Column(db.Integer, nullable=True)

    account_id      = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=False)
    account         = db.relationship('Account', back_populates='incomes')
