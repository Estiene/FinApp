# src/routes.py

from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, abort)
from datetime import date
from decimal import Decimal, InvalidOperation
from dateutil import parser
from dateutil.relativedelta import relativedelta

from .models import db, Account, Bill, BillPause, Income, CreditCard, CreditCardStatement, CreditCardPayment
from .utils.dashboard import build_dashboard_data, bill_dates, income_dates
from .utils.credit_cards import projected_card_balance
from .utils.planned_payments import planned_card_payments
from calendar import monthrange

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


BILL_FREQUENCIES = ("monthly", "weekly", "biweekly", "every_three_weeks")


def build_bill(form, existing=None):
    """Validate schedule before modifying an existing or new bill."""
    frequency = form.get("frequency", "monthly")
    if frequency not in BILL_FREQUENCIES:
        raise ValueError("Choose a valid bill frequency.")
    try:
        method = form.get("payment_method", "").strip()
        card_id = None
        if method:
            kind, separator, raw_id = method.partition(":")
            if not separator:
                raise ValueError
            selected_id = int(raw_id)
            if kind == "account":
                account_id = selected_id
            elif kind == "card":
                selected_card = CreditCard.query.get(selected_id)
                if selected_card is None:
                    raise ValueError
                card_id = selected_card.id
                account_id = selected_card.payment_account_id
            else:
                raise ValueError
        else:
            # Backwards-compatible with existing bill form submissions.
            account_id = int(form["account_id"])
        amount = Decimal(form["amount"])
        if not amount.is_finite() or amount <= 0 or amount.as_tuple().exponent < -2:
            raise ValueError
        if not Account.query.get(account_id):
            raise ValueError
    except (KeyError, ValueError, InvalidOperation):
        raise ValueError("Enter a valid account and positive amount (up to two decimals).")

    if card_id is not None and not selected_card.is_active:
        raise ValueError("Inactive credit cards cannot receive recurring bills. Choose an active card or bank account.")

    name = form.get("name", "").strip()
    owner = form.get("owner", "").strip()
    if not name or not owner:
        raise ValueError("Bill name and owner are required.")

    if frequency == "monthly":
        try:
            due_day = int(form["due_day"])
        except (KeyError, ValueError):
            raise ValueError("Enter a monthly due day from 1 to 31.")
        if not 1 <= due_day <= 31:
            raise ValueError("Enter a monthly due day from 1 to 31.")
        next_due = None
    else:
        try:
            next_due = date.fromisoformat(form["next_due"])
        except (KeyError, ValueError):
            raise ValueError("Enter a valid first due date.")
        due_day = next_due.day

    bill = existing if existing is not None else Bill()
    bill.name = name
    bill.owner = owner
    bill.amount = amount
    bill.due_day = due_day
    bill.frequency = frequency
    bill.next_due = next_due
    bill.account_id = account_id
    bill.credit_card_id = card_id
    return bill


def build_income(form, existing=None):
    """Fill an Income instance (new or existing) from form data."""
    try:
        amount = Decimal(form.get('amount', ''))
        if not amount.is_finite() or amount < 0 or amount.as_tuple().exponent < -2:
            raise ValueError
    except (InvalidOperation, ValueError):
        flash('Enter a nonnegative income amount with up to two decimals.', 'danger')
        return None
    inc = existing or Income()
    inc.name       = form['name']
    inc.amount     = amount
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


#
# ––– ROUTES –––
#

@bp.route('/')
def index():
    accounts = Account.query.order_by(Account.name).all()
    credit_cards = CreditCard.query.order_by(CreditCard.name).all()

    dashboard = build_dashboard_data(
        accounts,
        credit_cards=credit_cards,
    )

    return render_template('index.html', **dashboard)

def validate_credit_card_form(card_id=None):
    name = request.form.get('name', '').strip()

    if not name or len(name) > 100:
        raise ValueError("Enter a card name (maximum 100 characters).")

    existing = CreditCard.query.filter_by(name=name).first()
    if existing and existing.id != card_id:
        raise ValueError("A credit card with that name already exists.")

    account_id = int(request.form.get('payment_account_id', ''))
    account = db.session.get(Account, account_id)
    if account is None:
        raise ValueError("Select a valid payment account.")

    amounts = {}
    for field in ('balance', 'minimum_payment', 'extra_payment'):
        raw = request.form.get(field, '').strip()
        amount = Decimal(raw or '0')
        if (not amount.is_finite() or amount < 0
                or amount != amount.quantize(Decimal('0.01'))
                or amount > Decimal('9999999999.99')):
            raise ValueError(f"Invalid amount for {field}.")
        amounts[field] = amount

    close_day = int(request.form.get('statement_close_day', ''))
    due_day = int(request.form.get('payment_due_day', ''))
    if not (1 <= close_day <= 31 and 1 <= due_day <= 31):
        raise ValueError("Statement and payment days must be between 1 and 31.")

    # Preserve the existing due-date behavior when older forms omit these.
    extra_day_raw = request.form.get('extra_payment_day', '').strip()
    extra_day = int(extra_day_raw) if extra_day_raw else None
    if extra_day is not None and not 1 <= extra_day <= 31:
        raise ValueError("Extra payment day must be between 1 and 31.")

    timing = request.form.get('bill_payment_timing', 'due_date')
    if timing not in ('due_date', 'days_before_due'):
        raise ValueError("Select a valid bill-related payment schedule.")
    days_raw = request.form.get('bill_payment_days_before', '0').strip()
    days_before = int(days_raw or '0')
    if not 0 <= days_before <= 31:
        raise ValueError("Days before due must be between 0 and 31.")
    if timing == 'due_date':
        days_before = 0

    balance_as_of = date.fromisoformat(
        request.form.get('balance_as_of', '')
    )
    if balance_as_of > date.today():
        raise ValueError("Balance date cannot be in the future.")

    optional_amounts = {}
    for field in ('annual_percentage_rate', 'credit_limit', 'promotional_apr'):
        raw = request.form.get(field, '').strip()
        if not raw:
            optional_amounts[field] = None
            continue
        value = Decimal(raw)
        ceiling = Decimal('100') if field != 'credit_limit' else Decimal('9999999999.99')
        if (not value.is_finite() or value < 0 or value > ceiling
                or value != value.quantize(Decimal('0.01'))
                or (field == 'credit_limit' and value == 0)):
            raise ValueError(f"Invalid value for {field}.")
        optional_amounts[field] = value

    promo_end_raw = request.form.get('promotional_apr_end_date', '').strip()
    promo_end = date.fromisoformat(promo_end_raw) if promo_end_raw else None
    if (optional_amounts['promotional_apr'] is None) != (promo_end is None):
        raise ValueError("Promotional APR and expiration date must be provided together.")

    return dict(
        name=name,
        payment_account_id=account.id,
        balance_as_of=balance_as_of,
        statement_close_day=close_day,
        payment_due_day=due_day,
        extra_payment_day=extra_day,
        bill_payment_timing=timing,
        bill_payment_days_before=days_before,
        promotional_apr_end_date=promo_end,
        **optional_amounts,
        **amounts
    )


@bp.route('/credit-cards', methods=['GET', 'POST'])
def credit_cards():
    if request.method == 'POST':
        try:
            card_data = validate_credit_card_form()
            card = CreditCard(**card_data)
            db.session.add(card)
            db.session.commit()
            flash(f"Credit card '{card.name}' added successfully.", 'success')
        except (ValueError, InvalidOperation) as error:
            db.session.rollback()
            flash(str(error) or "Invalid credit card details.", 'danger')
        return redirect(url_for('main.credit_cards'))

    cards = CreditCard.query.order_by(CreditCard.name).all()
    accounts = Account.query.order_by(Account.name).all()
    return render_template(
        'credit_cards.html',
        cards=cards,
        accounts=accounts,
        today=date.today()
    )


@bp.route('/credit-cards/<int:card_id>/active', methods=['POST'])
def set_credit_card_active(card_id):
    """Archive a paid-off card without deleting its financial history."""
    card = CreditCard.query.get_or_404(card_id)
    action = request.form.get('action', '')
    if action not in ('activate', 'deactivate'):
        abort(400)
    if action == 'deactivate':
        if projected_card_balance(card, date.today()) != Decimal('0') or card.bills:
            flash("Pay off the card and move its recurring bills before deactivating it.", "danger")
            return redirect(url_for('main.credit_cards'))
        card.is_active = False
        flash(f"Credit card '{card.name}' deactivated; history was preserved.", "success")
    else:
        card.is_active = True
        flash(f"Credit card '{card.name}' reactivated.", "success")
    db.session.commit()
    return redirect(url_for('main.credit_cards'))


@bp.route('/credit-cards/<int:card_id>/edit', methods=['GET', 'POST'])
def edit_credit_card(card_id):
    card = CreditCard.query.get_or_404(card_id)

    if request.method == 'POST':
        try:
            changes = validate_credit_card_form(card_id=card.id)
            for field, value in changes.items():
                setattr(card, field, value)
            db.session.commit()
            flash("Credit card updated successfully.", "success")
            if request.form.get('save_action') == 'stay':
                return redirect(url_for('main.edit_credit_card', card_id=card.id))
            return redirect(url_for('main.credit_cards'))
        except (ValueError, InvalidOperation) as error:
            db.session.rollback()
            flash(str(error) or "Invalid card details.", "danger")

    accounts = Account.query.order_by(Account.name).all()

    return render_template(
        'edit_credit_card.html',
        card=card,
        accounts=accounts
    )


def validate_credit_card_statement(card):
    try:
        close_date = date.fromisoformat(
            request.form.get('statement_close_date', '')
        )
        due_date = date.fromisoformat(
            request.form.get('payment_due_date', '')
        )
        balance = Decimal(
            request.form.get('statement_balance', '')
        )
    except (ValueError, InvalidOperation):
        raise ValueError("Enter valid dates and a statement balance.")

    if due_date <= close_date:
        raise ValueError("Payment due date must follow the closing date.")

    if close_date > date.today():
        raise ValueError("Statement closing date cannot be in the future.")

    if (not balance.is_finite() or balance < 0
            or balance > Decimal('9999999999.99')
            or balance != balance.quantize(Decimal('0.01'))):
        raise ValueError("Enter a valid nonnegative statement balance.")

    existing = CreditCardStatement.query.filter_by(
        credit_card_id=card.id,
        statement_close_date=close_date
    ).first()

    if existing:
        raise ValueError("A statement already exists for that closing date.")

    return dict(
        credit_card_id=card.id,
        statement_close_date=close_date,
        payment_due_date=due_date,
        statement_balance=balance
    )


def validate_credit_card_payment(statement, form):
    """Validate an individual payment against the statement balance."""
    try:
        amount = Decimal(form.get('amount', ''))
        payment_date = date.fromisoformat(form.get('payment_date', ''))
    except (ValueError, InvalidOperation, TypeError):
        raise ValueError("Enter a valid payment amount and date.")

    if (not amount.is_finite()
            or amount <= 0
            or amount > Decimal('9999999999.99')
            or amount != amount.quantize(Decimal('0.01'))):
        raise ValueError("Enter a positive payment amount with up to two decimals.")

    if payment_date > date.today():
        raise ValueError("Payment date cannot be in the future.")

    if statement.statement_balance is None:
        raise ValueError("Confirm the statement balance before recording payments.")

    paid = max(Decimal('0'), statement.actual_payment or Decimal('0'))

    for payment in statement.payments:
        paid += max(Decimal('0'), payment.amount)

    remaining = max(Decimal('0'), statement.statement_balance - paid)

    if amount > remaining:
        raise ValueError(
            f"Payment exceeds the remaining statement balance of ${remaining:.2f}."
        )

    return dict(
        statement_id=statement.id,
        amount=amount,
        payment_date=payment_date,
    )


@bp.route('/credit-cards/<int:card_id>/statements', methods=['GET', 'POST'])
def credit_card_statements(card_id):
    card = CreditCard.query.get_or_404(card_id)

    if request.method == 'POST':
        try:
            data = validate_credit_card_statement(card)
            statement = CreditCardStatement(**data)
            db.session.add(statement)
            db.session.commit()
            flash("Credit card statement recorded successfully.", "success")
            return redirect(url_for('main.credit_card_statements', card_id=card.id))
        except (ValueError, InvalidOperation) as error:
            db.session.rollback()
            flash(str(error) or "Invalid statement details.", "danger")

    statements = (
        CreditCardStatement.query
        .filter_by(credit_card_id=card.id)
        .order_by(CreditCardStatement.statement_close_date.desc())
        .all()
    )

    payment_totals = {}
    remaining_balances = {}

    for statement in statements:
        total_paid = max(
            Decimal('0'),
            statement.actual_payment or Decimal('0')
        )

        for payment in statement.payments:
            total_paid += max(Decimal('0'), payment.amount)

        payment_totals[statement.id] = total_paid

        if statement.statement_balance is not None:
            remaining_balances[statement.id] = max(
                Decimal('0'),
                statement.statement_balance - total_paid
            )
        else:
            remaining_balances[statement.id] = None

    return render_template(
        'credit_card_statements.html',
        card=card,
        statements=statements,
        payment_totals=payment_totals,
        remaining_balances=remaining_balances,
        today=date.today()
    )


@bp.route(
    '/credit-cards/<int:card_id>/statements/<int:statement_id>/payments',
    methods=['POST']
)
def record_credit_card_payment(card_id, statement_id):
    card = CreditCard.query.get_or_404(card_id)

    statement = CreditCardStatement.query.filter_by(
        id=statement_id,
        credit_card_id=card.id,
    ).first_or_404()

    try:
        data = validate_credit_card_payment(statement, request.form)
        db.session.add(CreditCardPayment(**data))
        db.session.commit()
        flash("Credit card payment recorded successfully.", "success")
    except (ValueError, InvalidOperation) as error:
        db.session.rollback()
        flash(str(error), "danger")

    return redirect(
        url_for('main.credit_card_statements', card_id=card.id)
    )


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



@bp.route('/accounts/<int:account_id>/balance', methods=['POST'])
def update_account_balance(account_id):
    """Save the account's actual balance snapshot and its effective date."""
    account = Account.query.get_or_404(account_id)
    raw_balance = request.form.get('starting_balance', '').strip()
    raw_date = request.form.get('balance_as_of', '').strip()

    try:
        balance = Decimal(raw_balance)
        if not balance.is_finite():
            raise InvalidOperation
        rounded_balance = balance.quantize(Decimal("0.01"))
        if balance != rounded_balance:
            raise InvalidOperation
        balance = rounded_balance
    except (InvalidOperation, ValueError):
        flash("Enter a valid balance with no more than two decimal places.", 'danger')
        return redirect(url_for('main.index'))

    try:
        balance_date = parser.isoparse(raw_date).date()
    except (ValueError, TypeError):
        flash("Enter a valid balance date.", 'danger')
        return redirect(url_for('main.index'))

    if balance_date > date.today():
        flash("The balance date cannot be in the future.", 'danger')
        return redirect(url_for('main.index'))

    from .models import AccountBalanceObservation
    db.session.add(AccountBalanceObservation(account_id=account.id, balance_date=balance_date, balance=balance))
    account.starting_balance = balance
    account.balance_as_of = balance_date
    db.session.commit()
    flash(f"Saved starting balance for '{account.name}'.", 'success')
    return redirect(url_for('main.index'))

@bp.route('/accounts/<int:account_id>/early-pay', methods=['POST'])
def update_early_pay(account_id):
    account = Account.query.get_or_404(account_id)
    try:
        days = int(request.form.get('early_pay_days', ''))
        if days not in (0, 1, 2):
            raise ValueError
    except ValueError:
        flash('Choose Off, 1-day early or 2-day early.', 'danger')
        return redirect(url_for('main.accounts'))
    account.early_pay_days = days
    db.session.commit()
    flash('Early Pay saved. Weekday mapping only; bank holidays are not adjusted. Income schedules are unchanged.', 'success')
    return redirect(url_for('main.accounts'))


@bp.route('/accounts/<int:account_id>/delete', methods=['POST'])
def delete_account(account_id):
    return do_delete(Account, account_id, 'main.accounts')


@bp.route('/bills', defaults={'bill_id': None}, methods=['GET', 'POST'])
@bp.route('/bills/<int:bill_id>', methods=['GET', 'POST'])
def bills(bill_id):
    accounts = Account.query.order_by(Account.name).all()
    cards = CreditCard.query.filter_by(is_active=True).order_by(CreditCard.name).all()

    if request.method == 'POST':
        existing = Bill.query.get_or_404(bill_id) if bill_id else None
        try:
            b = build_bill(request.form, existing)
        except ValueError as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('main.bills', bill_id=bill_id) if bill_id else url_for('main.bills'))
        db.session.add(b)
        db.session.commit()
        action = 'Updated' if bill_id else 'Added'
        flash(f"{action} bill '{b.name}'.", 'success')
        if bill_id and request.form.get('save_action') == 'stay':
            return redirect(url_for('main.bills', bill_id=bill_id))
        return redirect(url_for('main.bills'))

    if bill_id:
        bill = Bill.query.get_or_404(bill_id)
        return render_template('edit_bill.html', bill=bill, accounts=accounts, cards=cards)

    all_bills = Bill.query.order_by(Bill.due_day).all()
    return render_template('bills.html', bills=all_bills, accounts=accounts, cards=cards)


@bp.route('/bills/<int:bill_id>/active', methods=['POST'])
def set_bill_active(bill_id):
    bill = Bill.query.get_or_404(bill_id)
    action = request.form.get('action')
    if action not in ('activate', 'deactivate'):
        abort(400)
    if action == 'activate':
        if bill.credit_card and not bill.credit_card.is_active:
            flash('Choose an active payment method before reactivating this bill.', 'danger')
            return redirect(url_for('main.bills', bill_id=bill.id))
        if not bill.is_active and bill.inactive_from:
            bill.pauses.append(BillPause(start_date=bill.inactive_from, end_date=date.today()))
        bill.is_active = True
        bill.inactive_from = None
    elif bill.is_active:
        bill.is_active = False
        bill.inactive_from = date.today()
    db.session.commit()
    flash('Bill reactivated.' if bill.is_active else 'Bill deactivated from today; earlier scheduled occurrences are preserved.', 'success')
    return redirect(url_for('main.bills'))


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
            # Invalid income inputs leave the previously saved entry unchanged.
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
    Generate and display a cash-flow report for every account,
    each with its own starting balance, from an optional start date
    through the end of the selected month. Any start_date outside the
    month will fall back to the 1st.
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

    # 4. Compute this month’s first day, last day, and last valid DOM
    first_of_month = date(year, month, 1)
    _, last_dom   = monthrange(year, month)
    last_day      = first_of_month + relativedelta(months=1) - relativedelta(days=1)

    # 4a. Clamp start_date into [first_of_month, last_day]
    if start_date < first_of_month or start_date > last_day:
        start_date = first_of_month

    # 6. Build report_data per account. Cash Flow uses planned card payments,
    # not completed payment history. Card-funded bills are not bank outflows.
    cards = CreditCard.query.all()
    report_bills = Bill.query.all()
    report_data = []
    for acct in accounts:
        sb = starting_balances[acct.id]

        # map each date → total incomes
        income_map = {}
        income_details = {}
        for inc in acct.incomes:
            for dt in income_dates(inc, start_date, last_day):
                amount = float(inc.amount)
                income_map[dt] = income_map.get(dt, 0.0) + amount
                income_details.setdefault(dt, []).append({
                    'name': inc.name, 'amount': amount,
                })

        # Reuse the same recurring bill engine as the dashboard.
        bill_map = {}
        bill_details = {}
        card_charge_map = {}
        # Resolve future card purchases through the card's current payment account.
        # The stored bill account may predate a card payment-account change.
        for b in report_bills:
            target_account = b.credit_card.payment_account_id if b.credit_card_id else b.account_id
            if target_account != acct.id:
                continue
            if b.credit_card_id and not b.credit_card.is_active:
                flash(f"Bill '{b.name}' references inactive card '{b.credit_card.name}'; move it to an active payment method. Card payments are not projected.", 'warning')
            for due in bill_dates(b, start_date, last_day):
                if b.credit_card_id is not None:
                    # Display the charge, but do not subtract it from checking.
                    card_charge_map.setdefault(due, []).append({
                        'bill': b.name,
                        'card': b.credit_card.name,
                        'amount': float(b.amount),
                    })
                else:
                    bill_map[due] = bill_map.get(due, 0.0) + float(b.amount)
                    bill_details.setdefault(due, []).append({
                        'name': b.name, 'amount': float(b.amount),
                    })

        card_payment_map = {}
        card_payment_details = {}
        payment_labels = {
            'bill_related': 'Bill-related',
            'extra': 'Extra',
            'minimum': 'Minimum',
        }
        for card in cards:
            if card.payment_account_id != acct.id:
                continue
            for payment in planned_card_payments(card, start_date, last_day):
                dt = payment['date']
                amount = float(payment['amount'])
                card_payment_map[dt] = card_payment_map.get(dt, 0.0) + amount
                card_payment_details.setdefault(dt, []).append({
                    'card': card.name,
                    'kind': payment_labels.get(payment['kind'], payment['kind']),
                    'amount': amount,
                })

        # walk from start_date through end of month
        days, bal = [], sb
        total_days = (last_day - start_date).days + 1
        for i in range(total_days):
            current = start_date + relativedelta(days=i)
            inc_amt  = income_map.get(current, 0.0)
            bill_amt = bill_map.get(current,  0.0)
            card_amt = float(card_payment_map.get(current, 0))
            charges = card_charge_map.get(current, [])
            charge_amt = sum(item['amount'] for item in charges)
            net      = inc_amt - bill_amt - card_amt
            bal     += net

            days.append({
                'date':    current,
                'income':  inc_amt,
                'income_details': income_details.get(current, []),
                'bills':   bill_amt,
                'bill_details': bill_details.get(current, []),
                'card_payment_details': card_payment_details.get(current, []),
                'credit_card_payments': card_amt,
                'credit_card_charges': charge_amt,
                'charge_details': charges,
                'net':     net,
                'balance': round(bal, 2)
            })

        report_data.append({
            'account':          acct,
            'starting_balance': sb,
            'days':             days,
            'totals': {
                'income': round(sum(day['income'] for day in days), 2),
                'bills': round(sum(day['bills'] for day in days), 2),
                'credit_card_payments': round(sum(day['credit_card_payments'] for day in days), 2),
                'credit_card_charges': round(sum(day['credit_card_charges'] for day in days), 2),
                'net': round(sum(day['net'] for day in days), 2),
            }
        })

    # 7. Prev/Next month for header navigation
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


@bp.route('/balance-history', methods=['GET'])
def balance_history():
    from datetime import timedelta
    from .models import AccountBalanceObservation, AccountForecastSnapshot
    from .utils.balance_history import chart_geometry
    accounts = Account.query.order_by(Account.name).all()
    if not accounts:
        return render_template('balance_history.html', accounts=[], account=None)
    account_id = request.args.get('account_id', type=int)
    account = Account.query.get_or_404(account_id) if account_id else accounts[0]
    today = date.today()
    try:
        start = date.fromisoformat(request.args.get('from', (today-timedelta(days=90)).isoformat()))
        end = date.fromisoformat(request.args.get('to', (today+timedelta(days=90)).isoformat()))
        if start > end or (end-start).days > 730:
            raise ValueError
    except ValueError:
        flash('Choose an ordered date range of at most 730 days.', 'danger')
        start, end = today-timedelta(days=90), today+timedelta(days=90)
    records = AccountBalanceObservation.query.filter_by(account_id=account.id).filter(
        AccountBalanceObservation.balance_date.between(start, end)).order_by(AccountBalanceObservation.id).all()
    # Corrections of a given date keep their audit records; the chart uses the latest save.
    latest = {record.balance_date: record for record in records}
    observations = [latest[key] for key in sorted(latest)]
    available = AccountForecastSnapshot.query.filter_by(account_id=account.id).filter(
        AccountForecastSnapshot.base_date.between(start-timedelta(days=min(180, (start-date.min).days)), end)
    ).order_by(AccountForecastSnapshot.id.desc()).limit(100).all()
    requested = request.args.getlist('forecast_id', type=int)
    if 'selection' in request.args:
        selected = [snapshot for snapshot in available if snapshot.id in requested][:3]
        if len(requested) > 3:
            flash('Up to three forecasts can be compared at once.', 'warning')
    else:
        selected = available[:3]
    chart = chart_geometry(observations, selected, start, end)
    return render_template('balance_history.html', accounts=accounts, account=account,
        start=start, end=end, observations=observations, available=available,
        selected_ids=[s.id for s in selected], chart=chart)


@bp.route('/accounts/<int:account_id>/forecasts', methods=['POST'])
def save_account_forecast(account_id):
    from .utils.balance_history import capture_forecast
    account = Account.query.get_or_404(account_id)
    try:
        horizon = int(request.form.get('horizon', '90'))
        forecast = capture_forecast(account, CreditCard.query.all(), date.today(), horizon)
    except ValueError as error:
        flash(str(error), 'danger')
        return redirect(url_for('main.balance_history', account_id=account.id))
    db.session.add(forecast)
    db.session.commit()
    flash('Forecast saved. Later schedule edits will not rewrite this snapshot.', 'success')
    return redirect(url_for('main.balance_history', account_id=account.id))
