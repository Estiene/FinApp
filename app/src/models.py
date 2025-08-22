from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Bill(db.Model):
    id       = db.Column(db.Integer, primary_key=True)
    name     = db.Column(db.String(100), nullable=False)
    owner    = db.Column(db.String(100), nullable=False)
    due_day  = db.Column(db.Integer, nullable=False)   # day of month 1–31
    amount   = db.Column(db.Numeric(10,2), nullable=False)

class Income(db.Model):
    id               = db.Column(db.Integer, primary_key=True)
    name             = db.Column(db.String(100), nullable=False)
    amount           = db.Column(db.Numeric(10,2), nullable=False)
    frequency        = db.Column(db.String(20), nullable=False)
    next_pay         = db.Column(db.Date)               # for weekly/biweekly
    day_of_month_1   = db.Column(db.Integer)            # for twice_monthly
    day_of_month_2   = db.Column(db.Integer)

