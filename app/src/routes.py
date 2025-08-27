# src/routes.py

from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, abort)
from datetime import date
from dateutil import parser
from dateutil.relativedelta import relativedelta

from .models import db, Account, Bill, Income

bp = Blueprint('main', __name__)

#
# ––– HELPERS –––
#

def do_delete(model, obj_id, redirect_endpoint):
    """Fetch + delete a single object, commit, flash, and redirect."""
    obj = model.query.get_or_404(obj_id)
    db.session.delete(obj)
    db.session.commit()
    flash(f"Deleted {model.__name__.lower()} '{getattr(obj, 'name', obj_id)}'.", 'success')
    return redirect(url_for(redirect_endpoint))


def parse_int_arg(name, default):
    """Safely parse request.args[name] into int, fallback on default."""
    try:
        return int(request.args.get(name) or default)
    except (ValueError, TypeError):
        return default


def parse_float_arg(name, default, label):
    """
    Safely parse request.args[name] into float.
    On failure, flash, then fallback on default.
    """
    raw = request.args.get(name)
    if not raw:
        return default

    try:
        return float(raw)
    except ValueError:
        flash(f"Invalid {label} '{raw}', defaulting to {default}", 'danger')
        return default


def build_bill(form, existing=None):
    """Fill a Bill instance (new or existing) from form data."""
    bill = existing or Bill()
    bill.name       = form['name']
    bill.owner      = form['owner']
    bill.amount     = form['amount']
    bill.due_day    = int(form['due_day'])
    bill.account_id = int(form['account_id'])
    return bill


def build_income(form, existing=None):
    """Fill an Income instance (new or existing) from form data."""
    inc = existing or Income()
    inc.name       = form['name']
    inc.amount     = form['amount']
    inc.frequency  = form['frequency']
    inc.account_id = int(form['account_id'])

    if inc.frequency == 'twice_monthly':
        inc.next_pay       = None
        inc.day_of_month_1 = int(form['day1'])
        inc.day_of_month_2 = int(form['day2'])
    else:
        try:
            inc.next_pay = parser.parse(form.get('next_pay', '')).date()
        except Exception as e:
            flash(f"Invalid date: {e}", 'danger')
            return None
        inc.day_of_month_1 = None
        inc.day_of_month_2 = None

    return inc


def income_dates_for_month(inc, first_day, last_day):
    """
    Given one Income and a date range, return the list of pay-dates
    that fall within that month.
    """
    dates = []
    freq = inc.frequency

    if freq in ('weekly', 'biweekly'):
        weeks = 1 if freq == 'weekly' else 2
        delta = relativedelta(weeks=weeks)
        seed  = inc.next_pay

        while seed < first_day:
            seed += delta
        while seed <= last_day:
            dates.append(seed)
            seed += delta

    elif freq == 'monthly':
        try:
            pay = date(first_day.year, first_day.month, inc.next_pay.day)
        except ValueError:
            return []
        if first_day <= pay <= last_day:
            dates.append(pay)

    else:  # twice_monthly
        for d in (inc.day_of_month_1, inc.day_of_month_2):
            try:
                pay = date(first_day.year, first_day.month, d)
            except ValueError:
                continue
            if first_day <= pay <= last_day:
                dates.append(pay)

    return dates


#
# ––– ROUTES –––
#

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

    accts = Account.query.order_by(Account.name).all()
    return render_template('accounts.html', accounts=accts)


@bp.route('/accounts/<int:account_id>/delete', methods=['POST'])
def delete_account(account_id):
    return do_delete(Account, account_id, 'main.accounts')


@bp.route('/bills', defaults={'bill_id': None}, methods=['GET', 'POST'])
@bp.route('/bills/<int:bill_id>', methods=['GET', 'POST'])
def bills(bill_id):
    accounts = Account.query.order_by(Account.name).all()

    if request.method == 'POST':
        existing = Bill.query.get(bill_id) if bill_id else None
        b = build_bill(request.form, existing)
        db.session.add(b)
        db.session.commit()
        action = 'Updated' if bill_id else 'Added'
        flash(f"{action} bill '{b.name}'.", 'success')
        return redirect(url_for('main.bills'))

    if bill_id:
        bill = Bill.query.get_or_404(bill_id)
        return render_template('edit_bill.html', bill=bill, accounts=accounts)

    all_bills = Bill.query.order_by(Bill.due_day).all()
    return render_template('bills.html', bills=all_bills, accounts=accounts)


@bp.route('/bills/<int:bill_id>/delete', methods=['POST'])
def delete_bill(bill_id):
    return do_delete(Bill, bill_id, 'main.bills')


@bp.route('/incomes', defaults={'income_id': None}, methods=['GET', 'POST'])
@bp.route('/incomes/<int:income_id>', methods=['GET', 'POST'])
def incomes(income_id):
    accounts = Account.query.order_by(Account.name).all()
    freqs    = ['weekly', 'biweekly', 'monthly', 'twice_monthly']

    if request.method == 'POST':
        existing = Income.query.get(income_id) if income_id else None
        inc = build_income(request.form, existing)
        if not inc:
            # if build_income returned None, date parse failed
            route = ('main.incomes' if not income_id
                     else 'main.incomes')  # or 'main.edit_income'
            return redirect(url_for(route))

        db.session.add(inc)
        db.session.commit()
        action = 'Updated' if income_id else 'Added'
        flash(f"{action} income '{inc.name}'.", 'success')
        return redirect(url_for('main.incomes'))

    if income_id:
        inc = Income.query.get_or_404(income_id)
        return render_template(
            'edit_income.html',
            income   = inc,
            freqs    = freqs,
            accounts = accounts
        )

    all_incomes = Income.query.order_by(Income.next_pay).all()
    return render_template(
        'incomes.html',
        incomes  = all_incomes,
        freqs    = freqs,
        accounts = accounts
    )


@bp.route('/incomes/<int:income_id>/delete', methods=['POST'])
def delete_income(income_id):
    return do_delete(Income, income_id, 'main.incomes')


@bp.route('/report')
def report():
    """
    Generate and display a cash‐flow report for every account,
    each with its own starting balance, and from a customizable start date
    through the end of the selected month.
    """
    # 1. Parse year/month (defaults to today)
    today = date.today()
    year  = request.args.get('year',  default=today.year,  type=int)
    month = request.args.get('month', default=today.month, type=int)

    # 2. Parse optional start_date (YYYY-MM-DD), fallback to first of month
    raw_start = request.args.get('start_date', '')
    if raw_start:
        try:
            start_date = parser.parse(raw_start).date()
        except Exception:
            flash(f"Invalid start date '{raw_start}', using first of month", 'warning')
            start_date = date(year, month, 1)
    else:
        start_date = date(year, month, 1)

    # 3. Load accounts and their per-account starting balances
    accounts = Account.query.order_by(Account.name).all()
    starting_balances = {}
    for acct in accounts:
        raw_sb = request.args.get(f'starting_balance_{acct.id}', '0')
        try:
            sb = float(raw_sb)
        except ValueError:
            flash(f"Invalid start for '{acct.name}': {raw_sb}. Using 0.", 'danger')
            sb = 0.0
        starting_balances[acct.id] = sb

    # 4. Compute month’s end
    first_of_month = date(year, month, 1)
    last_day       = first_of_month + relativedelta(months=1) - relativedelta(days=1)

    # 5. Helper: all pay‐dates of one Income within [start_date, last_day]
    def income_dates_for_month(inc):
        dates, freq = [], inc.frequency

        if freq in ('weekly', 'biweekly'):
            step = relativedelta(weeks=(1 if freq=='weekly' else 2))
            seed = inc.next_pay
            while seed < start_date:
                seed += step
            while seed <= last_day:
                dates.append(seed)
                seed += step

        elif freq == 'monthly':
            try:
                pay = date(year, month, inc.next_pay.day)
            except ValueError:
                return []
            if start_date <= pay <= last_day:
                dates.append(pay)

        else:  # twice_monthly
            for d in (inc.day_of_month_1, inc.day_of_month_2):
                try:
                    pay = date(year, month, d)
                except ValueError:
                    continue
                if start_date <= pay <= last_day:
                    dates.append(pay)

        return dates

    # 6. Build report_data per account
    report_data = []
    for acct in accounts:
        sb = starting_balances[acct.id]

        # map each date → total incomes
        income_map = {}
        for inc in acct.incomes:
            for dt in income_dates_for_month(inc):
                income_map[dt] = income_map.get(dt, 0.0) + float(inc.amount)

        # map each date → total bills
        bill_map = {}
        for b in acct.bills:
            try:
                due = date(year, month, b.due_day)
            except ValueError:
                continue
            if start_date <= due <= last_day:
                bill_map[due] = bill_map.get(due, 0.0) + float(b.amount)

        # walk from start_date through end of month
        days, bal = [], sb
        total_days = (last_day - start_date).days + 1
        for i in range(total_days):
            current = start_date + relativedelta(days=i)
            inc_amt  = income_map.get(current, 0.0)
            bill_amt = bill_map.get(current,  0.0)
            net      = inc_amt - bill_amt
            bal     += net

            days.append({
                'date':    current,
                'income':  inc_amt,
                'bills':   bill_amt,
                'net':     net,
                'balance': round(bal, 2)
            })

        report_data.append({
            'account':          acct,
            'starting_balance': sb,
            'days':             days
        })

    # 7. Prev/Next month for header navigation (preserve start_date)
    prev_dt = first_of_month - relativedelta(months=1)
    next_dt = first_of_month + relativedelta(months=1)

    return render_template(
        'report.html',
        year               = year,
        month              = month,
        start_date         = start_date,
        accounts           = accounts,
        starting_balances  = starting_balances,
        report_data        = report_data,
        prev_year          = prev_dt.year,
        prev_month         = prev_dt.month,
        next_year          = next_dt.year,
        next_month         = next_dt.month,
    )



@bp.route('/manage')
def manage():
    return render_template('manage.html')
