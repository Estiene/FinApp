"""Unit tests for credit card statement calculations."""

import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.utils.credit_cards import (
    card_payment_reservation,
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

    def test_reserve_unpaid_statement_payment(self):
        statement = self.make_statement(date(2026, 11, 10))
        statement.statement_close_date = date(2026, 10, 15)
        statement.payment_date = None

        self.card.statements = [statement]

        result = card_payment_reservation(
            self.card,
            Decimal("860.00"),
            as_of=self.today,
        )

        self.assertEqual(result, Decimal("140.00"))

    def test_reserve_remaining_amount_after_partial_payment(self):
        statement = self.make_statement(
            date(2026, 11, 10), payment="50.00"
        )
        statement.statement_close_date = date(2026, 10, 15)
        statement.payment_date = date(2026, 10, 20)

        self.card.statements = [statement]

        result = card_payment_reservation(
            self.card,
            Decimal("860.00"),
            as_of=self.today,
        )

        self.assertEqual(result, Decimal("90.00"))

    def test_reservation_ignores_future_dated_payment(self):
        statement = self.make_statement(
            date(2026, 11, 10), payment="140.00"
        )
        statement.statement_close_date = date(2026, 10, 15)
        statement.payment_date = date(2026, 10, 25)

        self.card.statements = [statement]

        result = card_payment_reservation(
            self.card,
            Decimal("860.00"),
            as_of=self.today,
        )

        self.assertEqual(result, Decimal("140.00"))

    def test_multiple_statement_reservations_capped_at_debt(self):
        first = self.make_statement(date(2026, 10, 10))
        first.statement_close_date = date(2026, 9, 15)
        first.payment_date = None

        second = self.make_statement(date(2026, 11, 10))
        second.statement_close_date = date(2026, 10, 15)
        second.payment_date = None

        self.card.statements = [first, second]

        result = card_payment_reservation(
            self.card,
            Decimal("200.00"),
            as_of=self.today,
        )

        self.assertEqual(result, Decimal("200.00"))

    def test_future_dated_payment_does_not_reduce_reservation(self):
        statement = self.make_statement(
            date(2026, 11, 10), payment="140.00"
        )
        statement.payment_date = date(2026, 10, 25)

        result = remaining_planned_statement_payment(
            self.card,
            statement,
            Decimal("860.00"),
            as_of=self.today,
        )

        self.assertEqual(result, Decimal("140.00"))

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


class MultipleCreditCardPaymentTests(unittest.TestCase):
    def test_two_partial_payments_reduce_remaining_reservation(self):
        card = SimpleNamespace(
            minimum_payment=Decimal("45.00"),
            extra_payment=Decimal("25.00"),
        )
        statement = SimpleNamespace(
            statement_balance=Decimal("400.00"),
            planned_payment=None,
            actual_payment=None,
            payment_date=None,
            payments=[
                SimpleNamespace(amount=Decimal("20.00"), payment_date=date(2026, 10, 18)),
                SimpleNamespace(amount=Decimal("30.00"), payment_date=date(2026, 10, 20)),
            ],
        )

        result = remaining_planned_statement_payment(
            card,
            statement,
            Decimal("450.00"),
            as_of=date(2026, 10, 21),
        )

        self.assertEqual(result, Decimal("20.00"))

    def test_multiple_payments_from_checking_respect_snapshot(self):
        from src.utils.credit_cards import recorded_payments_for_account

        statement = SimpleNamespace(
            actual_payment=None,
            payment_date=None,
            payments=[
                SimpleNamespace(
                    amount=Decimal("20.00"),
                    payment_date=date(2026, 10, 18),
                ),
                SimpleNamespace(
                    amount=Decimal("30.00"),
                    payment_date=date(2026, 10, 20),
                ),
            ],
        )
        card = SimpleNamespace(
            payment_account_id=1,
            statements=[statement],
        )

        result = recorded_payments_for_account(
            credit_cards=[card],
            account_id=1,
            start_date=date(2026, 10, 19),
            end_date=date(2026, 10, 21),
        )

        self.assertEqual(result, Decimal("30.00"))

    def test_multiple_payments_reduce_projected_card_balance(self):
        from src.utils.credit_cards import projected_card_balance

        statement = SimpleNamespace(
            actual_payment=None,
            payment_date=None,
            payments=[
                SimpleNamespace(
                    amount=Decimal("20.00"),
                    payment_date=date(2026, 10, 18),
                ),
                SimpleNamespace(
                    amount=Decimal("30.00"),
                    payment_date=date(2026, 10, 20),
                ),
            ],
        )
        card = SimpleNamespace(
            balance=Decimal("500.00"),
            balance_as_of=date(2026, 10, 15),
            bills=[],
            statements=[statement],
        )

        result = projected_card_balance(card, date(2026, 10, 21))

        self.assertEqual(result, Decimal("450.00"))

    def test_multiple_payments_mark_statement_paid(self):
        statement = SimpleNamespace(
            statement_balance=Decimal("400.00"),
            actual_payment=None,
            payment_due_date=date(2026, 11, 10),
            payments=[
                SimpleNamespace(
                    amount=Decimal("150.00"),
                    payment_date=date(2026, 10, 18),
                ),
                SimpleNamespace(
                    amount=Decimal("250.00"),
                    payment_date=date(2026, 10, 20),
                ),
            ],
        )

        result = statement_payment_status(
            statement,
            Decimal("450.00"),
            date(2026, 10, 21),
        )

        self.assertEqual(result["status"], "paid")
        self.assertEqual(result["remaining_balance"], Decimal("0.00"))

    def test_future_payment_does_not_mark_statement_paid(self):
        statement = SimpleNamespace(
            statement_balance=Decimal("400.00"),
            actual_payment=None,
            payment_date=None,
            payment_due_date=date(2026, 11, 10),
            payments=[
                SimpleNamespace(
                    amount=Decimal("400.00"),
                    payment_date=date(2026, 10, 25),
                ),
            ],
        )

        result = statement_payment_status(
            statement,
            Decimal("450.00"),
            date(2026, 10, 21),
        )

        self.assertEqual(result["status"], "upcoming")
        self.assertEqual(result["remaining_balance"], Decimal("400.00"))
