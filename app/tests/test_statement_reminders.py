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
        s = statement(date(2026, 9, 1), date(2026, 10, 1))
        self.assertEqual(statement_reminder(self.card([s]), self.TODAY)["status"], "stale")

    def test_upcoming(self):
        s = statement(date(2026, 11, 1), date(2026, 11, 15))
        self.assertEqual(statement_reminder(self.card([s]), self.TODAY)["status"], "upcoming")

    def test_overdue(self):
        s = statement(date(2026, 11, 1), date(2026, 11, 5))
        self.assertEqual(statement_reminder(self.card([s]), self.TODAY)["status"], "overdue")

    def test_paid(self):
        s = statement(date(2026, 11, 1), date(2026, 11, 5), paid="100")
        self.assertEqual(statement_reminder(self.card([s]), self.TODAY)["status"], "current")

    def test_inactive(self):
        self.assertEqual(statement_reminder(self.card(active=False), self.TODAY)["status"], "inactive")


if __name__ == "__main__":
    unittest.main()
