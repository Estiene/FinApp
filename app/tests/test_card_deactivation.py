"""Route regression tests for reversible credit card deactivation."""
import unittest
from datetime import date
from decimal import Decimal
from flask import Flask
from src.models import db, Account, Bill, CreditCard
from src.routes import bp


class CreditCardDeactivationRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__, template_folder="../src/templates")
        self.app.config.update(
            TESTING=True, SECRET_KEY="test-only",
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        db.init_app(self.app)
        self.app.register_blueprint(bp)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        account = Account(name="Checking")
        db.session.add(account)
        db.session.flush()
        self.card = CreditCard(
            name="Visa", payment_account_id=account.id,
            balance=Decimal("0"), balance_as_of=date.today(),
            statement_close_day=15, payment_due_day=10,
            minimum_payment=Decimal("25"), extra_payment=Decimal("0"),
        )
        db.session.add(self.card)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def post(self, action):
        return self.app.test_client().post(
            f"/credit-cards/{self.card.id}/active",
            data={"action": action})

    def test_deactivate_and_reactivate_preserve_card(self):
        self.assertEqual(self.post("deactivate").status_code, 302)
        self.assertFalse(db.session.get(CreditCard, self.card.id).is_active)
        self.assertEqual(self.post("activate").status_code, 302)
        self.assertTrue(db.session.get(CreditCard, self.card.id).is_active)

    def test_deactivate_refuses_outstanding_balance(self):
        self.card.balance = Decimal("20")
        db.session.commit()
        self.post("deactivate")
        self.assertTrue(self.card.is_active)

    def test_deactivate_refuses_linked_bills(self):
        db.session.add(Bill(
            name="Utility", owner="Test", due_day=5,
            amount=Decimal("20"), account_id=self.card.payment_account_id,
            credit_card_id=self.card.id))
        db.session.commit()
        self.post("deactivate")
        self.assertTrue(self.card.is_active)

    def test_unknown_action_is_rejected(self):
        self.assertEqual(self.post("delete").status_code, 400)


if __name__ == "__main__":
    unittest.main()
