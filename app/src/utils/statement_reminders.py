"""Credit-card statement freshness and upcoming payment reminders."""
from datetime import date


def statement_reminder(card, today=None, stale_after_days=45, upcoming_days=7):
    """Return a display-only reminder; never infer an issuer statement balance."""
    today = today or date.today()
    if not getattr(card, "is_active", True):
        return {"status": "inactive", "message": "Card is inactive."}

    statements = [
        statement for statement in getattr(card, "statements", ())
        if statement.statement_close_date <= today
    ]
    if not statements:
        return {"status": "missing", "message": "No confirmed statement recorded."}

    from decimal import Decimal

    def unpaid_balance(statement):
        if statement.statement_balance is None:
            return None
        remaining = max(Decimal("0"), Decimal(str(statement.statement_balance)))
        legacy_date = getattr(statement, "payment_date", None)
        if legacy_date is None or legacy_date <= today:
            remaining -= max(
                Decimal("0"), Decimal(str(getattr(statement, "actual_payment", None) or 0))
            )
        for payment in getattr(statement, "payments", ()):
            if payment.payment_date <= today:
                remaining -= max(Decimal("0"), Decimal(str(payment.amount)))
        return max(Decimal("0"), remaining)

    # A newer confirmed statement must not conceal an older unpaid one.
    overdue = [
        statement for statement in statements
        if statement.payment_due_date < today
        and (unpaid_balance(statement) or 0) > 0
    ]
    if overdue:
        earliest = min(overdue, key=lambda s: s.payment_due_date)
        days_overdue = (today - earliest.payment_due_date).days
        return {
            "status": "overdue",
            "message": f"Statement payment is {days_overdue} days past due.",
        }

    latest = max(statements, key=lambda statement: statement.statement_close_date)
    days_old = (today - latest.statement_close_date).days
    due = latest.payment_due_date
    remaining = unpaid_balance(latest)
    if remaining is not None and remaining > 0:
        days_until_due = (due - today).days
        if days_until_due <= upcoming_days:
            return {"status": "upcoming", "message": f"Statement payment due in {days_until_due} days."}

    if days_old > stale_after_days:
        return {
            "status": "stale",
            "message": f"Latest statement is {days_old} days old.",
            "statement_date": latest.statement_close_date,
        }

    return {"status": "current", "message": "Statement information is current."}
