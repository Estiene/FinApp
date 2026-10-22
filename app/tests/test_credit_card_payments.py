"""Tests for individual credit card payment validation."""

import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from src.routes import validate_credit_card_payment


class CreditCardPaymentValidationTests(unittest.TestCase):

    def make_statement(self, existing_payments=None):
        return SimpleNamespace(
            id=1,
            statement_balance=Decimal("400.00"),
            actual_payment=None,
            payments=existing_payments or [],
        )

    def test_invalid_payment_amounts(self):
        statement = self.make_statement()

        for amount in ("0", "-25.00", "10.999", "abc"):
            with self.subTest(amount=amount):
                form = {
                    "amount": amount,
                    "payment_date": date.today().isoformat(),
                }

                with self.assertRaises(ValueError):
                    validate_credit_card_payment(statement, form)

    def test_invalid_payment_dates(self):
        statement = self.make_statement()

        for payment_date in ("not-a-date", "2099-01-01", ""):
            with self.subTest(payment_date=payment_date):
                form = {
                    "amount": "50.00",
                    "payment_date": payment_date,
                }

                with self.assertRaises(ValueError):
                    validate_credit_card_payment(statement, form)

    def test_legacy_and_individual_payments(self):
        statement = self.make_statement([
            SimpleNamespace(amount=Decimal("150.00"))
        ])
        statement.actual_payment = Decimal("100.00")

        valid_form = {
            "amount": "150.00",
            "payment_date": date.today().isoformat(),
        }
        result = validate_credit_card_payment(statement, valid_form)
        self.assertEqual(result["amount"], Decimal("150.00"))

        excessive_form = {
            "amount": "150.01",
            "payment_date": date.today().isoformat(),
        }
        with self.assertRaisesRegex(
            ValueError, "remaining statement balance"
        ):
            validate_credit_card_payment(statement, excessive_form)

    def test_valid_partial_payment(self):
        statement = self.make_statement()
        form = {
            "amount": "100.00",
            "payment_date": date.today().isoformat(),
        }

        result = validate_credit_card_payment(statement, form)

        self.assertEqual(result["statement_id"], 1)
        self.assertEqual(result["amount"], Decimal("100.00"))
        self.assertEqual(result["payment_date"], date.today())

    def test_payment_exceeding_remaining_balance(self):
        previous_payment = SimpleNamespace(amount=Decimal("150.00"))
        statement = self.make_statement([previous_payment])
        form = {
            "amount": "300.00",
            "payment_date": date.today().isoformat(),
        }

        with self.assertRaisesRegex(
            ValueError, "remaining statement balance"
        ):
            validate_credit_card_payment(statement, form)


if __name__ == "__main__":
    unittest.main()
