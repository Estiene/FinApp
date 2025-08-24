from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Bill(db.Model):
    __tablename__ = 'bills'

    id       = db.Column(db.Integer, primary_key=True)
    name     = db.Column(db.String(100), nullable=False)
    owner    = db.Column(db.String(100), nullable=False)
    due_day  = db.Column(db.Integer, nullable=False)     # day of month 1–31
    amount   = db.Column(db.Numeric(10, 2), nullable=False)

class Income(db.Model):
    __tablename__ = 'incomes'

    id               = db.Column(db.Integer, primary_key=True)
    name             = db.Column(db.String(100), nullable=False)
    amount           = db.Column(db.Numeric(10, 2), nullable=False)
    frequency        = db.Column(db.String(20), nullable=False)  # 'weekly', 'biweekly', 'twice_monthly'
    next_pay         = db.Column(db.Date, nullable=True)         # seed date for weekly/biweekly/semimonthly
    day_of_month_1   = db.Column(db.Integer, nullable=True)      # first pay-day for twice_monthly
    day_of_month_2   = db.Column(db.Integer, nullable=True)      # second pay-day for twice_monthly
