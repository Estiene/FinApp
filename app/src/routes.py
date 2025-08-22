from flask import Blueprint, render_template, request, redirect, url_for
from .models import db, Bill, Income
from dateutil.relativedelta import relativedelta
from datetime import date

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    return render_template('index.html')

@bp.route('/bills', methods=['GET','POST'])
def bills():
    if request.method == 'POST':
        day = int(request.form['due_day'])
        b = Bill(
          name     = request.form['name'],
          owner    = request.form['owner'],
          due_day  = day,
          amount   = request.form['amount']
        )
        db.session.add(b); db.session.commit()
        return redirect(url_for('main.bills'))
    items = Bill.query.order_by(Bill.due_day).all()
    return render_template('bills.html', bills=items)

@bp.route('/incomes', methods=['GET','POST'])
def incomes():
    if request.method == 'POST':
        freq = request.form['frequency']
        if freq == 'twice_monthly':
            d1 = int(request.form['day1']); d2 = int(request.form['day2'])
            inc = Income(name=request.form['name'],
                         amount=request.form['amount'],
                         frequency=freq,
                         day_of_month_1=d1,
                         day_of_month_2=d2)
        else:
            inc = Income(name=request.form['name'],
                         amount=request.form['amount'],
                         frequency=freq,
                         next_pay=request.form['next_pay'])
        db.session.add(inc); db.session.commit()
        return redirect(url_for('main.incomes'))

    items = Income.query.order_by(Income.next_pay).all()
    freqs = ['weekly', 'biweekly', 'twice_monthly']
    return render_template('incomes.html', incomes=items, freqs=freqs)

@bp.route('/report')
def report():
    incomes = Income.query.all()
    bills   = Bill.query.all()
    periods = []

    for inc in incomes:
        # determine start/end per pay period (placeholder logic)
        # ... your existing logic to calculate start/end …

        # sum bills whose due_day falls in [start, end]
        total_due = 0
        for b in bills:
            # build actual due date for the month
            dt = date(start.year, start.month, b.due_day)
            if start <= dt <= end:
                total_due += b.amount

        periods.append({
            'start':     start,
            'end':       end,
            'income':    inc.amount,
            'bills_due': total_due,
            'net':       inc.amount - total_due
        })

    return render_template('report.html', periods=periods)
