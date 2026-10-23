"""Conservative credit-card utilization and payoff estimates.

These are planning estimates, not issuer statement or interest calculations.
They assume no new charges or fees and fixed monthly payments, with an optional
promotional APR followed by the regular APR.
"""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from dateutil.relativedelta import relativedelta

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def money(value):
    result = Decimal(str(value or 0))
    if not result.is_finite():
        raise ValueError("Amounts must be finite")
    return result.quantize(CENT, rounding=ROUND_HALF_UP)


def utilization(balance, credit_limit):
    """Return percentage utilization, or None if limit is not provided."""
    if credit_limit is None:
        return None
    limit = money(credit_limit)
    if limit <= ZERO:
        raise ValueError("Credit limit must be positive")
    return (max(ZERO, money(balance)) / limit * 100).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP)


def payoff_estimate(balance, annual_percentage_rate, monthly_payment,
                    max_months=600, *, promotional_apr=None,
                    promotional_end=None, as_of=None):
    """Estimate payoff with monthly compounding, no new charges or fees.

    Returns months, interest and total paid, or None when the monthly
    payment cannot overcome the accruing interest.
    """
    debt = money(balance)
    apr = Decimal(str(annual_percentage_rate)) if annual_percentage_rate is not None else None
    payment = money(monthly_payment)
    if debt < ZERO or (apr is not None and (not apr.is_finite() or apr < ZERO or apr > Decimal("100"))):
        raise ValueError("Invalid balance or APR")
    if payment < ZERO or max_months < 1:
        raise ValueError("Invalid payment or horizon")
    if debt == ZERO:
        return {"months": 0, "interest": ZERO, "total_paid": ZERO}
    if payment == ZERO:
        return None

    as_of = as_of or date.today()
    promo = Decimal(str(promotional_apr)) if promotional_apr is not None else None
    if promo is not None and (not promo.is_finite() or promo < 0 or promo > 100):
        raise ValueError("Invalid promotional APR")
    total_interest = ZERO
    total_paid = ZERO
    for month in range(1, max_months + 1):
        # Each monthly period starts at the corresponding snapshot anniversary.
        period_start = as_of + relativedelta(months=month - 1)
        rate = promo if promo is not None and promotional_end is not None and period_start <= promotional_end else apr
        if rate is None:
            return None
        monthly_rate = rate / Decimal("1200")
        interest = (debt * monthly_rate).quantize(CENT, rounding=ROUND_HALF_UP)
        if payment <= interest and not (promo is not None and promotional_end is not None and period_start <= promotional_end):
            return None
        total_interest += interest
        debt += interest
        paid = min(debt, payment)
        debt -= paid
        total_paid += paid
        if debt == ZERO:
            return {"months": month, "interest": total_interest,
                    "total_paid": total_paid}
    return None
