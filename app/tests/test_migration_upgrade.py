"""Integration smoke test: upgrade an existing Stage 5A database to Stage 5D.

Requires DATABASE_URL pointing to a disposable PostgreSQL database.
Run from app/: python -m unittest tests.test_migration_upgrade -v
"""
import os
import unittest
from datetime import date
from decimal import Decimal

from flask_migrate import downgrade, upgrade, stamp
from sqlalchemy import inspect, text

from src.app import create_app
from src.models import db, Account, CreditCard


@unittest.skipUnless(os.environ.get("FINAPP_MIGRATION_TEST") == "1",
                     "Only run against a disposable migration-test database")
class ForecastMigrationTests(unittest.TestCase):
    def test_upgrade_existing_card_preserves_data_and_is_reversible(self):
        app = create_app()
        with app.app_context():
            # Disposable CI database only; never run against production.
            # The repository's initial migration assumes legacy tables already
            # exist. Build an equivalent pre-Stage-5D schema in disposable CI.
            db.create_all()
            with db.engine.begin() as connection:
                for column in (
                    "annual_percentage_rate", "credit_limit",
                    "promotional_apr", "promotional_apr_end_date", "is_active",
                ):
                    connection.execute(text(
                        f'ALTER TABLE credit_cards DROP COLUMN "{column}"'
                    ))
            stamp(revision="a5c0e2d7b914")
            account = Account(name="Migration Test Checking")
            db.session.add(account)
            db.session.flush()
            card = CreditCard(
                name="Existing Visa", payment_account_id=account.id,
                balance=Decimal("125.50"), balance_as_of=date(2026, 10, 1),
                statement_close_day=15, payment_due_day=10,
                minimum_payment=Decimal("25.00"),
                extra_payment=Decimal("10.00"),
            )
            db.session.add(card)
            db.session.commit()
            card_id = card.id

            upgrade(revision="c5d5a9b2e781")
            db.session.expire_all()
            upgraded = db.session.get(CreditCard, card_id)
            self.assertEqual(upgraded.name, "Existing Visa")
            self.assertEqual(upgraded.balance, Decimal("125.50"))
            self.assertTrue(upgraded.is_active)
            self.assertIsNone(upgraded.credit_limit)

            upgraded.annual_percentage_rate = Decimal("19.99")
            upgraded.credit_limit = Decimal("2000.00")
            upgraded.promotional_apr = Decimal("0.00")
            upgraded.promotional_apr_end_date = date(2027, 1, 1)
            db.session.commit()
            db.session.expire_all()
            self.assertEqual(db.session.get(CreditCard, card_id).credit_limit,
                             Decimal("2000.00"))

            db.session.remove()
            downgrade(revision="a5c0e2d7b914")
            columns = {c["name"] for c in inspect(db.engine).get_columns("credit_cards")}
            self.assertNotIn("credit_limit", columns)
            with db.engine.connect() as connection:
                name = connection.execute(
                    text("SELECT name FROM credit_cards WHERE id=:id"),
                    {"id": card_id}).scalar_one()
            self.assertEqual(name, "Existing Visa")

            upgrade(revision="c5d5a9b2e781")
            db.session.expire_all()
            self.assertEqual(db.session.get(CreditCard, card_id).name, "Existing Visa")
            self.assertTrue(db.session.get(CreditCard, card_id).is_active)


if __name__ == "__main__":
    unittest.main()
