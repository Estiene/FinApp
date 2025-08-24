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
    bills   = Bill.query.all()
    periods = []
    today   = date.today()

    for inc in Income.query.all():
        # Determine semimonthly days tuple if needed
        semis = None
        if inc.frequency == 'twice_monthly':
            semis = (inc.day_of_month_1, inc.day_of_month_2)

            # Pick a non-None seed date for semimonthly
            if inc.next_pay:
                seed = inc.next_pay
            else:
                d1, d2 = semis
                if d1 >= today.day:
                    seed = date(today.year, today.month, d1)
                elif d2 >= today.day:
                    seed = date(today.year, today.month, d2)
                else:
                    nxt = today + relativedelta(months=1)
                    seed = date(nxt.year, nxt.month, d1)
        else:
            # weekly, biweekly, monthly all require next_pay
            seed = inc.next_pay

        # Generate pay-period spans using that seed
        spans = generate_pay_periods(
            first_pay_date   = seed,
            frequency        = inc.frequency,
            semimonthly_days = semis,
            horizon_months   = 12
        )

        # Sum bills due in each span
        for start, end in spans:
            total_due = 0
            for b in bills:
                try:
                    due_dt = date(start.year, start.month, b.due_day)
                except ValueError:
                    continue
                if start <= due_dt <= end:
                    total_due += float(b.amount)

            periods.append({
                'start':     start,
                'end':       end,
                'income':    float(inc.amount),
                'bills_due': total_due,
                'net':       float(inc.amount) - total_due
            })

    # Sort all periods by their start date
    periods.sort(key=lambda p: p['start'])
    return render_template('report.html', periods=periods)
