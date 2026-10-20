"""Live dashboard calculations based on scheduled income and bills."""

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal
from dateutil.relativedelta import relativedelta

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def _money(value):
    """Convert database numeric values to Decimal without float artifacts."""
    return Decimal(str(value or 0))


def _month_starts(start_date, end_date):
    """Yield the first day of each month intersecting a date range."""
    if start_date > end_date:
        return
    current = date(start_date.year, start_date.month, 1)
    while current <= end_date:
        yield current
        current += relativedelta(months=1)


def income_dates(income, start_date, end_date):
    """Return scheduled pay dates within an inclusive date range."""
    if start_date > end_date:
        return []

    dates = []
    if income.frequency in ("weekly", "biweekly"):
        seed = income.next_pay
        if seed is None:
            return []
        interval_days = 7 if income.frequency == "weekly" else 14
        step = timedelta(days=interval_days)
        if seed < start_date:
            elapsed_days = (start_date - seed).days
            seed += step * (elapsed_days // interval_days)
            while seed < start_date:
                seed += step
        while seed <= end_date:
            dates.append(seed)
            seed += step

    elif income.frequency == "monthly":
        if income.next_pay is None:
            return []
        requested_day = income.next_pay.day
        for month_start in _month_starts(start_date, end_date):
            last_day = monthrange(month_start.year, month_start.month)[1]
            pay_date = date(
                month_start.year, month_start.month, min(requested_day, last_day)
            )
            if start_date <= pay_date <= end_date:
                dates.append(pay_date)

    elif income.frequency == "twice_monthly":
        for month_start in _month_starts(start_date, end_date):
            last_day = monthrange(month_start.year, month_start.month)[1]
            for requested_day in (income.day_of_month_1, income.day_of_month_2):
                if requested_day is None:
                    continue
                pay_date = date(
                    month_start.year,
                    month_start.month,
                    min(max(int(requested_day), 1), last_day),
                )
                if start_date <= pay_date <= end_date:
                    dates.append(pay_date)

    # A malformed twice-monthly schedule with the same day twice should not
    # double-count the same calendar occurrence.
    return sorted(set(dates))


def bill_dates(bill, start_date, end_date):
    """Return monthly bill due dates within an inclusive date range."""
    dates = []
    if start_date > end_date:
        return dates
    for month_start in _month_starts(start_date, end_date):
        last_day = monthrange(month_start.year, month_start.month)[1]
        due_day = min(max(int(bill.due_day), 1), last_day)
        due_date = date(month_start.year, month_start.month, due_day)
        if start_date <= due_date <= end_date:
            dates.append(due_date)
    return dates


def build_dashboard_data(accounts, today=None):
    """Calculate current-month totals and each account's projected balance.

    Account starting balances are interpreted as the balance at the beginning
    of the balance_as_of date. Scheduled events on that date are included.
    The calculation is live and is not persisted.
    """
    today = today or date.today()
    month_start = date(today.year, today.month, 1)
    month_end = month_start + relativedelta(months=1) - timedelta(days=1)

    total_income = ZERO
    total_bills = ZERO
    account_summaries = []

    for account in accounts:
        for income in account.incomes:
            amount = _money(income.amount)
            total_income += amount * len(income_dates(income, month_start, month_end))
        for bill in account.bills:
            amount = _money(bill.amount)
            total_bills += amount * len(bill_dates(bill, month_start, month_end))

        balance_as_of = account.balance_as_of or today
        projected_balance = _money(account.starting_balance)
        if balance_as_of <= today:
            for income in account.incomes:
                count = len(income_dates(income, balance_as_of, today))
                projected_balance += _money(income.amount) * count
            for bill in account.bills:
                count = len(bill_dates(bill, balance_as_of, today))
                projected_balance -= _money(bill.amount) * count

        account_summaries.append({
            "account": account,
            "balance_as_of": balance_as_of,
            "projected_balance": projected_balance.quantize(CENT),
        })

    return {
        "today": today,
        "month_start": month_start,
        "month_end": month_end,
        "total_income": total_income.quantize(CENT),
        "total_bills": total_bills.quantize(CENT),
        "account_summaries": account_summaries,
    }
