"""Unit tests for credit card statement calculations."""

import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.utils.credit_cards import (
    remaining_planned_statement_payment,
    statement_payment_status,
)


class CreditCardStatementTests(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 10, 21)
        self.card = SimpleNamespace(
            minimum_payment=Decimal("40.00"),
            extra_payment=Decimal("100.00"),
        )

    def make_statement(
        self,
        due_date,
        balance="500.00",
        payment=None,
        planned_payment=None,
    ):
        return SimpleNamespace(
            payment_due_date=due_date,
            statement_balance=(
                Decimal(balance) if balance is not None else None
            ),
            actual_payment=(
                Decimal(payment) if payment is not None else None
            ),
            planned_payment=(
                Decimal(planned_payment)
                if planned_payment is not None else None
            ),
        )

    def test_upcoming_statement(self):
        statement = self.make_statement(date(2026, 11, 10))
        result = statement_payment_status(
            statement, Decimal("860.00"), self.today
        )
        self.assertEqual(result["status"], "upcoming")
        self.assertEqual(result["remaining_balance"], Decimal("500.00"))

    def test_statement_due_today(self):
        statement = self.make_statement(self.today)
        result = statement_payment_status(
            statement, Decimal("860.00"), self.today
        )
        self.assertEqual(result["status"], "due_today")

    def test_unpaid_statement_past_due_date(self):
        statement = self.make_statement(
            date(2026, 10, 10), payment="140.00"
        )
        result = statement_payment_status(
            statement, Decimal("860.00"), self.today
        )
        self.assertEqual(result["status"], "overdue")
        self.assertEqual(result["remaining_balance"], Decimal("360.00"))
        self.assertEqual(result["days_overdue"], 11)

    def test_fully_paid_statement(self):
        statement = self.make_statement(
            date(2026, 10, 10), payment="500.00"
        )
        result = statement_payment_status(
            statement, Decimal("860.00"), self.today
        )
        self.assertEqual(result["status"], "paid")

    def test_unconfirmed_statement(self):
        statement = self.make_statement(
            date(2026, 11, 10), balance=None
        )
        result = statement_payment_status(
            statement, Decimal("860.00"), self.today
        )
        self.assertEqual(result["status"], "unconfirmed")
        self.assertIsNone(result["remaining_balance"])

    def test_recorded_payment_satisfies_plan(self):
        statement = self.make_statement(
            date(2026, 10, 10), payment="140.00"
        )
        result = remaining_planned_statement_payment(
            self.card, statement, Decimal("860.00")
        )
        self.assertEqual(result, Decimal("0.00"))

    def test_partial_payment_reduces_remaining_plan(self):
        statement = self.make_statement(
            date(2026, 11, 10), payment="50.00"
        )
        result = remaining_planned_statement_payment(
            self.card, statement, Decimal("860.00")
        )
        self.assertEqual(result, Decimal("90.00"))

    def test_manual_payment_plan_override(self):
        statement = self.make_statement(
            date(2026, 11, 10),
            payment="50.00",
            planned_payment="200.00",
        )
        result = remaining_planned_statement_payment(
            self.card, statement, Decimal("860.00")
        )
        self.assertEqual(result, Decimal("150.00"))


if __name__ == "__main__":
    unittest.main()
