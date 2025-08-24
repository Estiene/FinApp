# src/routes.py

from flask import (
    Blueprint, render_template, request,
    redirect, url_for, flash
)
from datetime import date
from dateutil import parser
from dateutil.relativedelta import relativedelta

from .models import db, Bill, Income
from .utils.pay_periods import generate_pay_periods

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    return render_template('index.html')

@bp.route('/bills', methods=['GET', 'POST'])
def bills():
    if request.method == 'POST':
        b = Bill(
            name    = request.form['name'],
            owner   = request.form['owner'],
            amount  = request.form['amount'],
            due_day = int(request.form['due_day'])
        )
        db.session.add(b)
        db.session.commit()
        return redirect(url_for('main.bills'))

    items = Bill.query.order_by(Bill.due_day).all()
    return render_template('bills.html', bills=items)

@bp.route('/bills/<int:bill_id>/delete', methods=['POST'])
def delete_bill(bill_id):
    bill = Bill.query.get_or_404(bill_id)
    db.session.delete(bill)
    db.session.commit()
    flash(f"Deleted bill '{bill.name}'.", 'success')
    return redirect(url_for('main.bills'))

@bp.route('/incomes', methods=['GET', 'POST'])
def incomes():
    if request.method == 'POST':
        name      = request.form['name']
        amount    = request.form['amount']
        frequency = request.form['frequency']

        if frequency == 'twice_monthly':
            # Only use the two day fields; clear any hidden date
            d1 = int(request.form['day1'])
            d2 = int(request.form['day2'])
            inc = Income(
                name             = name,
                amount           = amount,
                frequency        = frequency,
                next_pay         = None,
                day_of_month_1   = d1,
                day_of_month_2   = d2
            )
        else:
            # Parse the date from the visible date input
            raw_date = request.form.get('next_pay') or ''
            try:
                pay_date = parser.parse(raw_date).date()
            except Exception as e:
                flash(f"Invalid date: {e}", 'danger')
                return redirect(url_for('main.incomes'))

            inc = Income(
                name             = name,
                amount           = amount,
                frequency        = frequency,
                next_pay         = pay_date,
                day_of_month_1   = None,
                day_of_month_2   = None
            )

        db.session.add(inc)
        db.session.commit()
        return redirect(url_for('main.incomes'))

    items = Income.query.order_by(Income.next_pay).all()
    freqs = ['weekly', 'biweekly', 'monthly', 'twice_monthly']
    return render_template('incomes.html', incomes=items, freqs=freqs)

@bp.route('/incomes/<int:income_id>/delete', methods=['POST'])
def delete_income(income_id):
    inc = Income.query.get_or_404(income_id)
    db.session.delete(inc)
    db.session.commit()
    flash(f"Deleted income '{inc.name}'.", 'success')
    return redirect(url_for('main.incomes'))

@bp.route('/report')
def report():
    # 1. Read year/month from querystring (default = today)
    today = date.today()
    year  = int(request.args.get('year', today.year))
    month = int(request.args.get('month', today.month))

    # 2. Read starting balance from querystring
    raw_start = request.args.get('starting_balance', '0')
    try:
        starting_balance = float(raw_start)
    except ValueError:
        flash(f"Invalid starting balance '{raw_start}', defaulting to 0", 'danger')
        starting_balance = 0.0

    # 3. Build the month’s date range
    first_day = date(year, month, 1)
    next_month = first_day + relativedelta(months=1)
    last_day = next_month - relativedelta(days=1)
    num_days = (last_day - first_day).days + 1

    # 4. Preload bills and incomes
    bills   = Bill.query.all()
    incomes = Income.query.all()

    # 5. Helper: for each income, find pay dates in this month
    def income_dates_for_month(inc):
        dates = []
        if inc.frequency == 'weekly':
            # step = 7 days
            delta = relativedelta(weeks=1)
            # seed = next_pay or first occurrence >= first_day
            seed = inc.next_pay
            while seed < first_day:
                seed += delta
            while seed <= last_day:
                dates.append(seed)
                seed += delta

        elif inc.frequency == 'biweekly':
            delta = relativedelta(weeks=2)
            seed = inc.next_pay
            while seed < first_day:
                seed += delta
            while seed <= last_day:
                dates.append(seed)
                seed += delta

        elif inc.frequency == 'monthly':
            day = inc.next_pay.day
            try:
                pay = date(year, month, day)
            except ValueError:
                return []
            if first_day <= pay <= last_day:
                dates.append(pay)

        elif inc.frequency == 'twice_monthly':
            d1, d2 = inc.day_of_month_1, inc.day_of_month_2
            for d in (d1, d2):
                try:
                    pay = date(year, month, d)
                except ValueError:
                    continue
                if first_day <= pay <= last_day:
                    dates.append(pay)

        return dates

    # 6. Build daily rows
    days = []
    # Pre-calc a mapping of date -> total income
    income_map = {}
    for inc in incomes:
        for pd in income_dates_for_month(inc):
            income_map.setdefault(pd, 0.0)
            income_map[pd] += float(inc.amount)

    # Pre-calc a mapping of date -> total bills
    bill_map = {}
    for b in bills:
        day = b.due_day
        try:
            due = date(year, month, day)
        except ValueError:
            continue
        if first_day <= due <= last_day:
            bill_map[due] = bill_map.get(due, 0.0) + float(b.amount)

    # Iterate each day in the month
    balance = starting_balance
    for i in range(num_days):
        current = first_day + relativedelta(days=i)
        inc_amt  = income_map.get(current, 0.0)
        bill_amt = bill_map.get(current, 0.0)
        net      = inc_amt - bill_amt
        balance += net

        days.append({
            'date':    current,
            'income':  inc_amt,
            'bills':   bill_amt,
            'net':     net,
            'balance': balance
        })

    # 7. Prev/Next month links
    prev_month_dt = first_day - relativedelta(months=1)
    next_month_dt = first_day + relativedelta(months=1)

    return render_template('report.html',
        days=days,
        starting_balance=round(starting_balance, 2),
        year=year, month=month,
        prev_year=prev_month_dt.year,
        prev_month=prev_month_dt.month,
        next_year=next_month_dt.year,
        next_month=next_month_dt.month,
    )
