"""Conservative credit-card utilization and payoff estimates.

These are planning estimates, not issuer statement or interest calculations.
They assume a constant APR, no new charges or fees, and monthly payments.
"""
from decimal import Decimal, ROUND_HALF_UP

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
                    max_months=600):
    """Estimate payoff with monthly compounding, no new charges or fees.

    Returns months, interest and total paid, or None when the monthly
    payment cannot overcome the accruing interest.
    """
    debt = money(balance)
    apr = Decimal(str(annual_percentage_rate))
    payment = money(monthly_payment)
    if debt < ZERO or not apr.is_finite() or apr < ZERO or apr > Decimal("100"):
        raise ValueError("Invalid balance or APR")
    if payment < ZERO or max_months < 1:
        raise ValueError("Invalid payment or horizon")
    if debt == ZERO:
        return {"months": 0, "interest": ZERO, "total_paid": ZERO}
    if payment == ZERO:
        return None

    monthly_rate = apr / Decimal("1200")
    total_interest = ZERO
    total_paid = ZERO
    for month in range(1, max_months + 1):
        interest = (debt * monthly_rate).quantize(CENT, rounding=ROUND_HALF_UP)
        if payment <= interest:
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
