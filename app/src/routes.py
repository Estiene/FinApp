# src/routes.py

from flask import (
    Blueprint, render_template, request,
    redirect, url_for, flash
)
from datetime import date
from dateutil import parser
from dateutil.relativedelta import relativedelta

from .models import db, Account, Bill, Income

bp = Blueprint('main', __name__)


@bp.route('/')
def index():
    return render_template('index.html')


@bp.route('/accounts', methods=['GET', 'POST'])
def accounts():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash("Account name required.", 'danger')
        else:
            acct = Account(name=name)
            db.session.add(acct)
            db.session.commit()
            flash(f"Added account '{acct.name}'.", 'success')
        return redirect(url_for('main.accounts'))

    accounts = Account.query.order_by(Account.name).all()
    return render_template('accounts.html', accounts=accounts)


@bp.route('/accounts/<int:account_id>/delete', methods=['POST'])
def delete_account(account_id):
    acct = Account.query.get_or_404(account_id)
    db.session.delete(acct)
    db.session.commit()
    flash(f"Deleted account '{acct.name}'.", 'success')
    return redirect(url_for('main.accounts'))


@bp.route('/bills', methods=['GET', 'POST'])
def bills():
    accounts = Account.query.order_by(Account.name).all()

    if request.method == 'POST':
        b = Bill(
            name       = request.form['name'],
            owner      = request.form['owner'],
            amount     = request.form['amount'],
            due_day    = int(request.form['due_day']),
            account_id = int(request.form['account_id'])
        )
        db.session.add(b)
        db.session.commit()
        flash(f"Added bill '{b.name}'.", 'success')
        return redirect(url_for('main.bills'))

    bills = Bill.query.order_by(Bill.due_day).all()
    return render_template('bills.html', bills=bills, accounts=accounts)


@bp.route('/bills/<int:bill_id>/delete', methods=['POST'])
def delete_bill(bill_id):
    bill = Bill.query.get_or_404(bill_id)
    db.session.delete(bill)
    db.session.commit()
    flash(f"Deleted bill '{bill.name}'.", 'success')
    return redirect(url_for('main.bills'))


@bp.route('/incomes', methods=['GET', 'POST'])
def incomes():
    accounts = Account.query.order_by(Account.name).all()

    if request.method == 'POST':
        name       = request.form['name']
        amount     = request.form['amount']
        frequency  = request.form['frequency']
        account_id = int(request.form['account_id'])

        if frequency == 'twice_monthly':
            d1 = int(request.form['day1'])
            d2 = int(request.form['day2'])
            inc = Income(
                name            = name,
                amount          = amount,
                frequency       = frequency,
                next_pay        = None,
                day_of_month_1  = d1,
                day_of_month_2  = d2,
                account_id      = account_id
            )
        else:
            raw_date = request.form.get('next_pay', '')
            try:
                pay_date = parser.parse(raw_date).date()
            except Exception as e:
                flash(f"Invalid date: {e}", 'danger')
                return redirect(url_for('main.incomes'))

            inc = Income(
                name            = name,
                amount          = amount,
                frequency       = frequency,
                next_pay        = pay_date,
                day_of_month_1  = None,
                day_of_month_2  = None,
                account_id      = account_id
            )

        db.session.add(inc)
        db.session.commit()
        flash(f"Added income '{inc.name}'.", 'success')
        return redirect(url_for('main.incomes'))

    incomes = Income.query.order_by(Income.next_pay).all()
    freqs   = ['weekly', 'biweekly', 'monthly', 'twice_monthly']
    return render_template(
        'incomes.html',
        incomes=incomes,
        freqs=freqs,
        accounts=accounts
    )


@bp.route('/incomes/<int:income_id>/delete', methods=['POST'])
def delete_income(income_id):
    inc = Income.query.get_or_404(income_id)
    db.session.delete(inc)
    db.session.commit()
    flash(f"Deleted income '{inc.name}'.", 'success')
    return redirect(url_for('main.incomes'))


@bp.route('/report')
def report():
    today     = date.today()
    year      = int(request.args.get('year', today.year))
    month     = int(request.args.get('month', today.month))
    acct_id   = request.args.get('account_id', 'all')
    raw_start = request.args.get('starting_balance', '0')

    try:
        starting_balance = float(raw_start)
    except ValueError:
        flash(
            f"Invalid starting balance '{raw_start}', defaulting to 0",
            'danger'
        )
        starting_balance = 0.0

    first_day  = date(year, month, 1)
    next_month = first_day + relativedelta(months=1)
    last_day   = next_month - relativedelta(days=1)

    accounts = Account.query.order_by(Account.name).all()
    if acct_id == 'all':
        target_accounts = accounts
    else:
        target_accounts = [Account.query.get_or_404(int(acct_id))]

    def income_dates_for_month(inc):
        dates = []
        if inc.frequency == 'weekly':
            delta = relativedelta(weeks=1)
            seed  = inc.next_pay
            while seed < first_day:
                seed += delta
            while seed <= last_day:
                dates.append(seed)
                seed += delta

        elif inc.frequency == 'biweekly':
            delta = relativedelta(weeks=2)
            seed  = inc.next_pay
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
            for d in (inc.day_of_month_1, inc.day_of_month_2):
                try:
                    pay = date(year, month, d)
                except ValueError:
                    continue
                if first_day <= pay <= last_day:
                    dates.append(pay)

        return dates

    report_data = []
    for acct in target_accounts:
        # build income map for this account
        income_map = {}
        for inc in acct.incomes:
            for pd in income_dates_for_month(inc):
                income_map.setdefault(pd, 0.0)
                income_map[pd] += float(inc.amount)

        # build bill map for this account
        bill_map = {}
        for b in acct.bills:
            try:
                due = date(year, month, b.due_day)
            except ValueError:
                continue
            if first_day <= due <= last_day:
                bill_map.setdefault(due, 0.0)
                bill_map[due] += float(b.amount)

        # assemble daily rows
        days = []
        bal  = starting_balance
        total_days = (last_day - first_day).days + 1

        for i in range(total_days):
            current = first_day + relativedelta(days=i)
            inc_amt = income_map.get(current, 0.0)
            bill_amt= bill_map.get(current, 0.0)
            net     = inc_amt - bill_amt
            bal    += net

            days.append({
                'date':    current,
                'income':  inc_amt,
                'bills':   bill_amt,
                'net':     net,
                'balance': round(bal, 2)
            })

        report_data.append({
            'account': acct,
            'days':    days
        })

    prev_dt = first_day - relativedelta(months=1)
    next_dt = first_day + relativedelta(months=1)

    return render_template(
        'report.html',
        report_data      = report_data,
        accounts         = accounts,
        selected_account = acct_id,
        starting_balance = starting_balance,
        year             = year,
        month            = month,
        prev_year        = prev_dt.year,
        prev_month       = prev_dt.month,
        next_year        = next_dt.year,
        next_month       = next_dt.month
    )
