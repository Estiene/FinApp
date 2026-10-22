"""Daily bank-account cash-flow projections from a dated balance snapshot.

Snapshots represent the end-of-day actual balance. Events on or before the
snapshot date must not be replayed. Card-funded bills are not bank outflows;
planned card payments are separate outflows.
"""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from .dashboard import income_dates, bill_dates
from .planned_payments import planned_card_payments

ZERO = Decimal("0.00")
CENT = Decimal("0.01")


def daily_account_projection(account, start_date, end_date, credit_cards=()):
    """Return daily projected balances and warnings, or [] for an empty range.

    Dates preceding the account's snapshot are intentionally excluded: an
    end-of-day snapshot cannot reconstruct earlier balances.
    """
    if start_date > end_date:
        return []
    snapshot = getattr(account, "balance_as_of", None)
    if snapshot is None:
        raise ValueError("Account requires a dated balance snapshot")
    first = max(start_date, snapshot + timedelta(days=1))
    if first > end_date:
        return []

    balance = Decimal(str(account.starting_balance or 0))
    # Advance through earlier days if the requested window starts later than
    # the snapshot. Never treat the report start as a new balance snapshot.
    changes = defaultdict(lambda: ZERO)
    for income in getattr(account, "incomes", ()):
        for day in income_dates(income, snapshot + timedelta(days=1), end_date):
            changes[day] += Decimal(str(income.amount))
    for bill in getattr(account, "bills", ()):
        if getattr(bill, "credit_card_id", None) is not None:
            continue
        for day in bill_dates(bill, snapshot + timedelta(days=1), end_date):
            changes[day] -= Decimal(str(bill.amount))
    for card in credit_cards:
        if getattr(card, "payment_account_id", None) != getattr(account, "id", None):
            continue
        for payment in planned_card_payments(card, snapshot + timedelta(days=1), end_date):
            changes[payment["date"]] -= payment["amount"]

    rows = []
    day = snapshot + timedelta(days=1)
    while day <= end_date:
        change = changes[day].quantize(CENT)
        balance = (balance + change).quantize(CENT)
        if day >= first:
            rows.append({
                "date": day,
                "change": change,
                "balance": balance,
                "negative": balance < ZERO,
            })
        day += timedelta(days=1)
    return rows
