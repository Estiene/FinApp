import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from src.utils.statement_reminders import statement_reminder


def statement(closed, due, balance="100", paid="0"):
    return SimpleNamespace(
        statement_close_date=closed, payment_due_date=due,
        statement_balance=Decimal(balance), actual_payment=Decimal(paid),
        payments=[])


class StatementReminderTests(unittest.TestCase):
    TODAY = date(2026, 11, 10)

    def card(self, statements=None, active=True):
        return SimpleNamespace(statements=statements or [], is_active=active)

    def test_missing(self):
        self.assertEqual(statement_reminder(self.card(), self.TODAY)["status"], "missing")

    def test_stale(self):
        s = statement(date(2026, 9, 1), date(2026, 10, 1), paid="100")
        self.assertEqual(statement_reminder(self.card([s]), self.TODAY)["status"], "stale")

    def test_old_unpaid_statement_is_overdue_not_merely_stale(self):
        s = statement(date(2026, 9, 1), date(2026, 10, 1))
        self.assertEqual(
            statement_reminder(self.card([s]), self.TODAY)["status"], "overdue")

    def test_newer_statement_does_not_hide_older_overdue_balance(self):
        old = statement(date(2026, 9, 15), date(2026, 10, 10))
        recent = statement(date(2026, 11, 1), date(2026, 11, 20))
        self.assertEqual(
            statement_reminder(self.card([old, recent]), self.TODAY)["status"],
            "overdue",
        )

    def test_paid_older_statement_does_not_hide_new_upcoming_payment(self):
        old = statement(date(2026, 9, 15), date(2026, 10, 10), paid="100")
        recent = statement(date(2026, 11, 1), date(2026, 11, 15))
        self.assertEqual(
            statement_reminder(self.card([old, recent]), self.TODAY)["status"],
            "upcoming",
        )

    def test_upcoming(self):
        s = statement(date(2026, 11, 1), date(2026, 11, 15))
        self.assertEqual(statement_reminder(self.card([s]), self.TODAY)["status"], "upcoming")

    def test_overdue(self):
        s = statement(date(2026, 11, 1), date(2026, 11, 5))
        self.assertEqual(statement_reminder(self.card([s]), self.TODAY)["status"], "overdue")

    def test_paid(self):
        s = statement(date(2026, 11, 1), date(2026, 11, 5), paid="100")
        self.assertEqual(statement_reminder(self.card([s]), self.TODAY)["status"], "current")

    def test_future_itemized_payment_does_not_hide_due_reminder(self):
        s = statement(date(2026, 11, 1), date(2026, 11, 15))
        s.payments = [SimpleNamespace(
            amount=Decimal("100"), payment_date=date(2026, 11, 20))]
        self.assertEqual(
            statement_reminder(self.card([s]), self.TODAY)["status"], "upcoming")

    def test_future_legacy_payment_does_not_hide_due_reminder(self):
        s = statement(date(2026, 11, 1), date(2026, 11, 15), paid="100")
        s.payment_date = date(2026, 11, 20)
        self.assertEqual(
            statement_reminder(self.card([s]), self.TODAY)["status"], "upcoming")

    def test_completed_itemized_payment_clears_due_reminder(self):
        s = statement(date(2026, 11, 1), date(2026, 11, 15))
        s.payments = [SimpleNamespace(
            amount=Decimal("100"), payment_date=date(2026, 11, 9))]
        self.assertEqual(
            statement_reminder(self.card([s]), self.TODAY)["status"], "current")

    def test_inactive(self):
        self.assertEqual(statement_reminder(self.card(active=False), self.TODAY)["status"], "inactive")


if __name__ == "__main__":
    unittest.main()
