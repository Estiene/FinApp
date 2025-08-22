from flask import Blueprint, render_template, request, redirect, url_for
from .models import db, Bill, Income
from dateutil.relativedelta import relativedelta
from datetime import date

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    return render_template('index.html')

@bp.route('/bills', methods=['GET', 'POST'])
def bills():
    if request.method == 'POST':
        b = Bill(
            name=request.form['name'],
            owner=request.form['owner'],
            due_date=request.form['due_date'],
            amount=request.form['amount']
        )
        db.session.add(b)
        db.session.commit()
        return redirect(url_for('main.bills'))
    items = Bill.query.order_by(Bill.due_date).all()
    return render_template('bills.html', bills=items)

@bp.route('/incomes', methods=['GET', 'POST'])
def incomes():
    if request.method == 'POST':
        inc = Income(
            name=request.form['name'],
            amount=request.form['amount'],
            frequency=request.form['frequency'],
            next_pay=request.form['next_pay']
        )
        db.session.add(inc)
        db.session.commit()
        return redirect(url_for('main.incomes'))
    items = Income.query.order_by(Income.next_pay).all()
    freqs = ['weekly','biweekly','twice_monthly']
    return render_template('incomes.html', incomes=items, freqs=freqs)

@bp.route('/report')
def report():
    incomes = Income.query.all()
    bills = Bill.query.all()
    periods = []
    for inc in incomes:
        start = inc.next_pay - relativedelta(days=inc.amount)  # placeholder logic
        end = inc.next_pay
        due = [b.amount for b in bills if start <= b.due_date <= end]
        periods.append({
            'income': inc.amount,
            'start': start,
            'end': end,
            'bills_due': sum(due),
            'net': inc.amount - sum(due)
        })
    return render_template('report.html', periods=periods)

