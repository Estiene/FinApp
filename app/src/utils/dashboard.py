"""Live dashboard calculations based on scheduled income and bills."""

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from dateutil.relativedelta import relativedelta
from .credit_cards import (
    recorded_payments_for_account,
    projected_card_balance,
    minimum_plus_extra_payment,
    card_payment_reservation,
)


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
    """Inclusive occurrences for monthly or anchored interval-based bills."""
    if start_date > end_date:
        return []
    frequency = getattr(bill, "frequency", None) or "monthly"
    if frequency in ("weekly", "biweekly", "every_three_weeks"):
        anchor = getattr(bill, "next_due", None)
        if anchor is None:
            return []
        interval = {"weekly": 7, "biweekly": 14, "every_three_weeks": 21}[frequency]
        # Never create occurrences before the first scheduled due date.
        first = max(start_date, anchor)
        offset = (first - anchor).days
        occurrence = anchor + timedelta(days=((offset + interval - 1) // interval) * interval)
        result = []
        while occurrence <= end_date:
            result.append(occurrence)
            occurrence += timedelta(days=interval)
        return result
    if frequency != "monthly":
        return []
    dates = []
    for month_start in _month_starts(start_date, end_date):
        last_day = monthrange(month_start.year, month_start.month)[1]
        due_day = min(max(int(bill.due_day), 1), last_day)
        due_date = date(month_start.year, month_start.month, due_day)
        if start_date <= due_date <= end_date:
            dates.append(due_date)
    return dates


def build_dashboard_data(accounts, today=None, credit_cards=None):
    """Calculate current-month totals and each account's projected balance.

    Account starting balances are snapshots at the end of balance_as_of. Events
    after that date through today are applied. The calculation is live.
    """
    today = today or date.today()
    month_start = date(today.year, today.month, 1)
    month_end = month_start + relativedelta(months=1) - timedelta(days=1)

    total_income = ZERO
    total_bills = ZERO
    account_summaries = []
    credit_cards = credit_cards or []

    for account in accounts:
        for income in account.incomes:
            amount = _money(income.amount)
            total_income += amount * len(
                income_dates(income, month_start, month_end)
            )

        for bill in account.bills:
            amount = _money(bill.amount)
            total_bills += amount * len(
                bill_dates(bill, month_start, month_end)
            )

        balance_as_of = account.balance_as_of or today
        projected_balance = _money(account.starting_balance)

        if balance_as_of < today:
            projection_start = balance_as_of + timedelta(days=1)

            for income in account.incomes:
                count = len(
                    income_dates(income, projection_start, today)
                )
                projected_balance += _money(income.amount) * count

            for bill in account.bills:
                # Card purchases do not directly reduce checking.
                if getattr(bill, "credit_card_id", None) is not None:
                    continue

                count = len(
                    bill_dates(bill, projection_start, today)
                )
                projected_balance -= _money(bill.amount) * count
                        # Subtract completed credit card payments after the balance snapshot.
            # Subtract completed card payments after the balance snapshot.
            if credit_cards:
                projected_balance -= recorded_payments_for_account(
                    credit_cards=credit_cards,
                    account_id=account.id,
                    start_date=projection_start,
                    end_date=today,
                )

        reserved = ZERO

        for card in credit_cards:
            if card.payment_account_id != getattr(account, "id", None):
                continue

            projected_debt = projected_card_balance(card, today)
            reserved += card_payment_reservation(
                card,
                projected_debt,
                as_of=today,
            )

        account_summaries.append({
            "account": account,
            "balance_as_of": balance_as_of,
            "projected_balance": projected_balance.quantize(CENT),
            "reserved_for_credit_cards": reserved.quantize(CENT),
            "spendable_balance": (projected_balance - reserved).quantize(CENT),
        })

    from .cash_flow_projection import daily_account_projection
    for summary in account_summaries:
        # Anchor the forward-looking forecast to today's displayed balance.
        # Past planned card payments are not actual bank transactions and must
        # not be replayed from the older account snapshot.
        account = summary["account"]
        forecast_account = SimpleNamespace(
            id=getattr(account, "id", None),
            starting_balance=summary["projected_balance"],
            balance_as_of=today,
            incomes=account.incomes,
            bills=account.bills,
        )
        future = daily_account_projection(
            forecast_account, today, today + timedelta(days=30), credit_cards
        )
        negative = [row for row in future if row["negative"]]
        summary["next_30_days_low"] = min(
            (row["balance"] for row in future), default=None
        )
        summary["first_negative_date"] = negative[0]["date"] if negative else None
        summary["next_30_days"] = future

    credit_card_summaries = []

    from .card_forecast import utilization, payoff_estimate
    from .statement_reminders import statement_reminder
    for card in credit_cards:
        projected_debt = projected_card_balance(card, today)

        credit_limit = getattr(card, "credit_limit", None)
        utilization_pct = utilization(projected_debt, credit_limit)
        standard_apr = getattr(card, "annual_percentage_rate", None)
        promo_apr = getattr(card, "promotional_apr", None)
        promo_end = getattr(card, "promotional_apr_end_date", None)
        # A promotional rate is only applied while it is currently valid.
        # The payoff estimate below uses a fixed rate and is therefore
        # suppressed when a promotion will expire before payoff.
        effective_apr = (
            promo_apr if promo_apr is not None and promo_end is not None
            and today <= promo_end else standard_apr
        )

        suggested = minimum_plus_extra_payment(
            outstanding_balance=projected_debt,
            minimum_payment=card.minimum_payment,
            extra_payment=card.extra_payment,
        )

        payoff = None
        if effective_apr is not None:
            payoff = payoff_estimate(projected_debt, effective_apr, suggested)
            if promo_apr is not None and promo_end is not None and today <= promo_end:
                # Do not project a fixed promo APR beyond its expiration.
                from dateutil.relativedelta import relativedelta as _rd
                if payoff is None or today + _rd(months=payoff["months"]) > promo_end:
                    payoff = None

        credit_card_summaries.append({
            "card": card,
            "projected_balance": projected_debt,
            "suggested_payment": suggested,
            "utilization_pct": utilization_pct,
            "effective_apr": effective_apr,
            "payoff_estimate": payoff,
            "statement_reminder": statement_reminder(card, today),
        })

    return {
        "today": today,
        "month_start": month_start,
        "month_end": month_end,
        "total_income": total_income.quantize(CENT),
        "total_bills": total_bills.quantize(CENT),
        "account_summaries": account_summaries,
        "credit_card_summaries": credit_card_summaries,
    }
