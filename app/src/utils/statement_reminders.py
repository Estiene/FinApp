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

    latest = max(statements, key=lambda statement: statement.statement_close_date)
    days_old = (today - latest.statement_close_date).days
    if days_old > stale_after_days:
        return {
            "status": "stale",
            "message": f"Latest statement is {days_old} days old.",
            "statement_date": latest.statement_close_date,
        }

    due = latest.payment_due_date
    remaining = latest.statement_balance
    if remaining is not None:
        from decimal import Decimal
        remaining = max(Decimal("0"), Decimal(str(remaining)))
        remaining -= max(Decimal("0"), Decimal(str(getattr(latest, "actual_payment", None) or 0)))
        for payment in getattr(latest, "payments", ()):
            remaining -= max(Decimal("0"), Decimal(str(payment.amount)))
        remaining = max(Decimal("0"), remaining)

    if remaining is not None and remaining > 0:
        days_until_due = (due - today).days
        if days_until_due < 0:
            return {"status": "overdue", "message": f"Statement payment is {abs(days_until_due)} days past due."}
        if days_until_due <= upcoming_days:
            return {"status": "upcoming", "message": f"Statement payment due in {days_until_due} days."}

    return {"status": "current", "message": "Statement information is current."}
