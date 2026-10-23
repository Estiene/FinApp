"""Credit card payment and cash reserve calculations."""

from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def money(value):
    """Convert a value to a two-decimal-place Decimal."""
    return Decimal(str(value if value is not None else 0)).quantize(
        CENT, rounding=ROUND_HALF_UP
    )


def suggested_payment(
    outstanding_balance,
    cycle_charges,
    minimum_payment,
    extra_payment=0,
):
    """Suggest a payment without exceeding the outstanding balance.

    outstanding_balance already includes cycle_charges.
    """
    balance = max(ZERO, money(outstanding_balance))
    charges = max(ZERO, money(cycle_charges))
    minimum = max(ZERO, money(minimum_payment))
    extra = max(ZERO, money(extra_payment))

    suggestion = max(minimum, charges + extra)
    return min(balance, suggestion)

def available_cash(checking_balance, planned_payment, already_reserved=0):
    """Calculate spendable cash after reserving for a card payment.

    already_reserved is the amount previously earmarked toward this payment.
    """
    balance = money(checking_balance)
    payment = max(ZERO, money(planned_payment))
    reserved = max(ZERO, money(already_reserved))

    additional_reserve = max(ZERO, payment - reserved)
    return balance - additional_reserve

def spendable_balance(checking_balance, total_reserved):
    """Available cash based on checking balance and total reserved funds."""
    balance = money(checking_balance)
    reserved = max(ZERO, money(total_reserved))
    return balance - reserved

def apply_card_activity(
    checking_balance,
    card_balance,
    charges=0,
    payment=0,
):
    """Calculate balances after card charges and a payment.

    card_balance is the debt before these new charges.
    Payment cannot exceed the resulting card debt.
    """
    checking = money(checking_balance)
    debt = max(ZERO, money(card_balance))
    new_charges = max(ZERO, money(charges))
    requested_payment = max(ZERO, money(payment))

    debt += new_charges
    actual_payment = min(requested_payment, debt)

    checking -= actual_payment
    debt -= actual_payment

    return checking, debt

def monthly_date(year, month, requested_day):
    """Return a valid date for a configured monthly statement or payment day."""
    from calendar import monthrange
    from datetime import date

    day = int(requested_day)

    if not 1 <= day <= 31:
        raise ValueError("Monthly day must be between 1 and 31")

    last_day = monthrange(year, month)[1]
    return date(year, month, min(day, last_day))

def statement_payment_due_date(statement_close_date, payment_due_day):
    """Calculate the payment due date in the month after statement closing."""
    from dateutil.relativedelta import relativedelta

    next_month = statement_close_date + relativedelta(
        day=1, months=1
    )

    return monthly_date(
        next_month.year,
        next_month.month,
        payment_due_day,
    )

def statement_close_for_charge(charge_date, statement_close_day):
    """Find the statement closing date for a credit card charge."""
    from dateutil.relativedelta import relativedelta

    closing_date = monthly_date(
        charge_date.year,
        charge_date.month,
        statement_close_day,
    )

    if charge_date <= closing_date:
        return closing_date

    next_month = charge_date + relativedelta(day=1, months=1)

    return monthly_date(
        next_month.year,
        next_month.month,
        statement_close_day,
    )

def charges_by_statement(bills, start_date, end_date, statement_close_day):
    """Group scheduled credit card charges by statement closing date."""
    from collections import defaultdict
    from .dashboard import bill_dates

    totals = defaultdict(lambda: ZERO)

    for bill in bills:
        amount = money(bill.amount)

        for charge_date in bill_dates(bill, start_date, end_date):
            closing_date = statement_close_for_charge(
                charge_date, statement_close_day
            )
            totals[closing_date] += amount

    return dict(sorted(totals.items()))

def suggested_statement_payment(
    outstanding_balance,
    statement_charges,
    minimum_payment,
    extra_payment=0,
    confirmed_statement_balance=None,
):
    """Suggest a payment using confirmed statement data when available.

    outstanding_balance includes the statement charges.
    """
    charges = (
        money(confirmed_statement_balance)
        if confirmed_statement_balance is not None
        else money(statement_charges)
    )

    return suggested_payment(
        outstanding_balance=outstanding_balance,
        cycle_charges=charges,
        minimum_payment=minimum_payment,
        extra_payment=extra_payment,
    )

def statement_amount_due(
    outstanding_balance,
    confirmed_statement_balance,
    payments_since_statement=0,
):
    """Calculate the unpaid portion of a confirmed statement.

    Never return more than the current outstanding card debt.
    """
    debt = max(ZERO, money(outstanding_balance))
    statement = max(ZERO, money(confirmed_statement_balance))
    payments = max(ZERO, money(payments_since_statement))

    unpaid_statement = max(ZERO, statement - payments)

    return min(debt, unpaid_statement)

def minimum_plus_extra_payment(
    outstanding_balance,
    minimum_payment,
    extra_payment=0,
    remaining_statement_balance=None,
):
    """Suggest the minimum plus extra, capped at outstanding debt.

    A fully paid statement requires no additional scheduled payment.
    """
    debt = max(ZERO, money(outstanding_balance))
    minimum = max(ZERO, money(minimum_payment))
    extra = max(ZERO, money(extra_payment))

    if remaining_statement_balance is not None:
        remaining = max(ZERO, money(remaining_statement_balance))
        if remaining == ZERO:
            return ZERO

    return min(debt, minimum + extra)

def recorded_payments_for_account(
    credit_cards,
    account_id,
    start_date,
    end_date,
):
    """Total completed card payments from an account within a date range."""
    total = ZERO
    if account_id is None:
        return ZERO

    for card in credit_cards:
        if card.payment_account_id != account_id:
            continue

        for statement in card.statements:
            if (
                statement.payment_date is not None
                and statement.actual_payment is not None
                and start_date <= statement.payment_date <= end_date
            ):
                total += max(ZERO, money(statement.actual_payment))

            for payment in getattr(statement, "payments", []):
                if start_date <= payment.payment_date <= end_date:
                    total += max(ZERO, money(payment.amount))

    return total.quantize(CENT)

def projected_card_balance(card, today):
    """Project card debt from its saved balance snapshot through today."""
    from datetime import timedelta
    from .dashboard import bill_dates

    balance = max(ZERO, money(card.balance))
    snapshot_date = card.balance_as_of

    if snapshot_date >= today:
        return balance

    start_date = snapshot_date + timedelta(days=1)

    # Scheduled purchases increase card debt.
    for bill in card.bills:
        charge_count = len(bill_dates(bill, start_date, today))
        balance += money(bill.amount) * charge_count

    # Completed payments reduce card debt.
    for statement in card.statements:
        if (
            statement.payment_date is not None
            and statement.actual_payment is not None
            and start_date <= statement.payment_date <= today
        ):
            balance -= max(ZERO, money(statement.actual_payment))

        for payment in getattr(statement, "payments", []):
            if start_date <= payment.payment_date <= today:
                balance -= max(ZERO, money(payment.amount))

    return max(ZERO, balance).quantize(CENT)

def remaining_planned_statement_payment(
    card, statement, outstanding_balance, as_of=None
):
    """Calculate the remaining planned payment for a statement.

    When as_of is supplied, only payments completed by that date count.
    """
    paid = max(ZERO, money(statement.actual_payment))

    if as_of is not None:
        payment_date = getattr(statement, "payment_date", None)
        if payment_date is None or payment_date > as_of:
            paid = ZERO

    for payment in getattr(statement, "payments", []):
        if as_of is None or payment.payment_date <= as_of:
            paid += max(ZERO, money(payment.amount))

    if statement.statement_balance is not None:
        unpaid_statement = max(
            ZERO,
            money(statement.statement_balance) - paid,
        )
    else:
        unpaid_statement = None

    if statement.planned_payment is not None:
        original_plan = max(ZERO, money(statement.planned_payment))
    else:
        original_plan = (
            max(ZERO, money(card.minimum_payment))
            + max(ZERO, money(card.extra_payment))
        )

    remaining_plan = max(ZERO, original_plan - paid)
    remaining_debt = max(ZERO, money(outstanding_balance))

    if unpaid_statement is not None:
        return min(remaining_plan, unpaid_statement, remaining_debt)

    return min(remaining_plan, remaining_debt)
def statement_payment_status(statement, outstanding_balance, today):
    """Return payment status for a confirmed credit card statement."""
    if statement.statement_balance is None:
        return {
            "status": "unconfirmed",
            "remaining_balance": None,
            "days_overdue": 0,
        }

    paid = ZERO

    legacy_date = getattr(statement, "payment_date", None)
    if (
        legacy_date is None or legacy_date <= today
    ):
        paid += max(ZERO, money(statement.actual_payment))

    for payment in getattr(statement, "payments", []):
        if payment.payment_date <= today:
            paid += max(ZERO, money(payment.amount))

    remaining = statement_amount_due(
        outstanding_balance,
        statement.statement_balance,
        paid,
    )

    if remaining == ZERO:
        status = "paid"
        days_overdue = 0
    elif today > statement.payment_due_date:
        status = "overdue"
        days_overdue = (today - statement.payment_due_date).days
    elif today == statement.payment_due_date:
        status = "due_today"
        days_overdue = 0
    else:
        status = "upcoming"
        days_overdue = 0

    return {
        "status": status,
        "remaining_balance": remaining,
        "days_overdue": days_overdue,
    }

def card_payment_reservation(card, outstanding_balance, as_of):
    """Reserve remaining planned payments from confirmed, closed statements.

    Reservations are capped at the card's remaining projected debt.
    """
    remaining_debt = max(ZERO, money(outstanding_balance))
    total_reserved = ZERO

    statements = sorted(
        card.statements,
        key=lambda statement: statement.statement_close_date,
    )

    for statement in statements:
        if statement.statement_close_date > as_of:
            continue

        if statement.statement_balance is None:
            continue

        available_debt = max(ZERO, remaining_debt - total_reserved)

        if available_debt == ZERO:
            break

        reservation = remaining_planned_statement_payment(
            card,
            statement,
            available_debt,
            as_of=as_of,
        )

        total_reserved += reservation

    return total_reserved.quantize(CENT)
