"""Pure planned credit-card cash-flow scheduling for Stage 5A.

This module intentionally does not use recorded payments as cash-flow events.
It calculates conservative planned outflows, separately from card debt.
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from .credit_cards import (
    money, monthly_date, statement_close_for_charge,
    statement_payment_due_date,
)
from .dashboard import bill_dates

ZERO = Decimal("0.00")


def statement_cycle_charges(card, first_charge_date, last_charge_date):
    """Map each statement closing date to the total scheduled card-funded bills."""
    charges = defaultdict(lambda: ZERO)
    if first_charge_date > last_charge_date:
        return {}
    for bill in getattr(card, "bills", ()):
        for charge_date in bill_dates(bill, first_charge_date, last_charge_date):
            close_date = statement_close_for_charge(
                charge_date, card.statement_close_day
            )
            charges[close_date] += money(bill.amount)
    return dict(charges)


def _payment_date(card, close_date):
    """Return bill-related payment date for a statement cycle."""
    actual = next(
        (s for s in getattr(card, "statements", ())
         if s.statement_close_date == close_date),
        None,
    )
    due = (
        actual.payment_due_date if actual is not None
        else statement_payment_due_date(close_date, card.payment_due_day)
    )
    mode = getattr(card, "bill_payment_timing", "due_date") or "due_date"
    if mode == "due_date":
        return due
    if mode == "days_before_due":
        days = int(getattr(card, "bill_payment_days_before", 0) or 0)
        if not 0 <= days <= 31:
            raise ValueError("Days before due must be between 0 and 31")
        return due - timedelta(days=days)
    raise ValueError("Unknown bill-related payment timing mode")


def planned_card_payments(card, start_date, end_date):
    """Return dated payment components, including conservative minimum reserves.

    Each item has date, kind, amount, card_id. This is a planning schedule:
    actual recorded payments are never included as separate events.

    The lookback allows statement-cycle bills charged before the report
    window to contribute to payments due within the report window.
    """
    if start_date > end_date:
        return []
    events = []
    # Covers bills in the preceding statement cycle for due dates early
    # in the requested window, including an early-payment offset.
    charge_start = start_date - timedelta(days=100)
    charges = statement_cycle_charges(card, charge_start, end_date)
    statements = {
        s.statement_close_date: s
        for s in getattr(card, "statements", ())
    }
    # Include empty cycles: minimum and extra payments are still scheduled.
    first_month = date(charge_start.year, charge_start.month, 1)
    last_month = date(end_date.year, end_date.month, 1)
    year, month = first_month.year, first_month.month
    while (year, month) <= (last_month.year, last_month.month):
        close = monthly_date(year, month, card.statement_close_day)
        due = (
            statements[close].payment_due_date if close in statements
            else statement_payment_due_date(close, card.payment_due_day)
        )
        bill_date = _payment_date(card, close)
        recurring_charges = charges.get(close, ZERO)
        statement = statements.get(close)
        bill_amount = recurring_charges
        if statement is not None and statement.statement_balance is not None:
            bill_amount = min(
                recurring_charges, max(ZERO, money(statement.statement_balance))
            )
        if start_date <= bill_date <= end_date and bill_amount > ZERO:
            events.append(dict(date=bill_date, kind="bill_related",
                               amount=bill_amount, card_id=card.id))
        minimum = max(ZERO, money(card.minimum_payment))
        if start_date <= due <= end_date and minimum > ZERO:
            events.append(dict(date=due, kind="minimum",
                               amount=minimum, card_id=card.id))
        extra = max(ZERO, money(card.extra_payment))
        extra_day = getattr(card, "extra_payment_day", None)
        if extra_day is None:
            extra_date = due
        else:
            # Extra payoff uses its own fixed monthly calendar day.
            extra_date = monthly_date(due.year, due.month, extra_day)
        if start_date <= extra_date <= end_date and extra > ZERO:
            events.append(dict(date=extra_date, kind="extra",
                               amount=extra, card_id=card.id))
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    # One cycle per month. Avoid generating a duplicate extra payment
    # if an unusual due-date override puts two cycles in one month.
    deduped = {}
    for event in events:
        key = (event["date"], event["kind"], event["card_id"])
        if event["kind"] == "extra" and key in deduped:
            continue
        deduped[key] = event
    return sorted(deduped.values(), key=lambda x: (x["date"], x["kind"]))


def planned_payments_for_account(cards, account_id, start_date, end_date):
    """Aggregate planned card outflows by day for a bank account."""
    totals = defaultdict(lambda: ZERO)
    for card in cards:
        if card.payment_account_id != account_id:
            continue
        for event in planned_card_payments(card, start_date, end_date):
            totals[event["date"]] += event["amount"]
    return dict(totals)
