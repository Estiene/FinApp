"""Integration tests for recording credit card payments."""

import os
import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from src.app import create_app
from src.models import (
    db, Account, CreditCard, CreditCardStatement,
    CreditCardPayment,
)


class CreditCardPaymentRouteTests(unittest.TestCase):

    def setUp(self):
        with patch.dict(os.environ, {
            "DATABASE_URL": "sqlite:///:memory:",
            "SECRET_KEY": "payment-route-test-only",
        }):
            self.app = create_app()

        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

        account = Account(name="Test Checking")
        db.session.add(account)
        db.session.flush()

        card = CreditCard(
            name="Test Visa",
            statement_close_day=15,
            payment_due_day=10,
            payment_account_id=account.id,
        )
        db.session.add(card)
        db.session.flush()

        statement = CreditCardStatement(
            credit_card_id=card.id,
            statement_close_date=date(2026, 10, 15),
            payment_due_date=date(2026, 11, 10),
            statement_balance=Decimal("400.00"),
        )
        db.session.add(statement)
        db.session.commit()

        self.card_id = card.id
        self.statement_id = statement.id

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_reject_payment_for_wrong_card(self):
        response = self.client.post(
            f"/credit-cards/{self.card_id + 999}/statements/"
            f"{self.statement_id}/payments",
            data={
                "amount": "100.00",
                "payment_date": date.today().isoformat(),
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(CreditCardPayment.query.count(), 0)

    def test_reject_statement_belonging_to_another_card(self):
        original_card = CreditCard.query.get(self.card_id)

        other_card = CreditCard(
            name="Test Mastercard",
            statement_close_day=20,
            payment_due_day=15,
            payment_account_id=original_card.payment_account_id,
        )
        db.session.add(other_card)
        db.session.commit()

        response = self.client.post(
            f"/credit-cards/{other_card.id}/statements/"
            f"{self.statement_id}/payments",
            data={
                "amount": "100.00",
                "payment_date": date.today().isoformat(),
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(CreditCardPayment.query.count(), 0)

    def test_statement_page_displays_payment_totals(self):
        response = self.client.get(
            f"/credit-cards/{self.card_id}/statements"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Total Paid", response.data)
        self.assertIn(b"Remaining Balance", response.data)
        self.assertIn(b"$400.00", response.data)

    def test_statement_page_shows_payment_form(self):
        response = self.client.get(
            f"/credit-cards/{self.card_id}/statements"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Record Payment", response.data)
        self.assertIn(b"Payment History", response.data)
        self.assertIn(
            f"/credit-cards/{self.card_id}/statements/"
            f"{self.statement_id}/payments".encode(),
            response.data,
        )

    def test_remaining_balance_updates_after_payment(self):
        payment_response = self.client.post(
            f"/credit-cards/{self.card_id}/statements/"
            f"{self.statement_id}/payments",
            data={
                "amount": "100.00",
                "payment_date": date.today().isoformat(),
            },
        )
        self.assertEqual(payment_response.status_code, 302)

        response = self.client.get(
            f"/credit-cards/{self.card_id}/statements"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"$100.00", response.data)
        self.assertIn(b"$300.00", response.data)
        self.assertIn(date.today().isoformat().encode(), response.data)

    def test_record_partial_payment(self):
        response = self.client.post(
            f"/credit-cards/{self.card_id}/statements/"
            f"{self.statement_id}/payments",
            data={
                "amount": "100.00",
                "payment_date": date.today().isoformat(),
            },
        )

        self.assertEqual(response.status_code, 302)

        payments = CreditCardPayment.query.all()
        self.assertEqual(len(payments), 1)
        self.assertEqual(payments[0].statement_id, self.statement_id)
        self.assertEqual(payments[0].amount, Decimal("100.00"))
        self.assertEqual(payments[0].payment_date, date.today())


if __name__ == "__main__":
    unittest.main()
