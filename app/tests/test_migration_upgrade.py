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
from src.models import db, Account, Bill, CreditCard, AccountBalanceObservation, AccountForecastSnapshot


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
            bill = Bill(name="Existing bill", owner="Test", amount=Decimal("30"), due_day=20, account_id=account.id)
            db.session.add(bill)
            db.session.add(card)
            db.session.commit()
            account_id = account.id
            card_id = card.id
            bill_id = bill.id
            db.session.remove()
            with db.engine.begin() as connection:
                for table in ("account_forecast_points", "account_forecast_snapshots", "account_balance_observations"):
                    connection.execute(text("DROP TABLE " + table))
                connection.execute(text("ALTER TABLE accounts DROP CONSTRAINT ck_account_early_pay_days"))
                connection.execute(text("ALTER TABLE accounts DROP COLUMN early_pay_days"))
                connection.execute(text("DROP TABLE bill_pauses"))
                connection.execute(text("ALTER TABLE bills DROP COLUMN is_active"))
                connection.execute(text("ALTER TABLE bills DROP COLUMN inactive_from"))
                for column in (
                    "annual_percentage_rate", "credit_limit",
                    "promotional_apr", "promotional_apr_end_date", "is_active",
                ):
                    connection.execute(text(
                        f'ALTER TABLE credit_cards DROP COLUMN "{column}"'
                    ))
            stamp(revision="a5c0e2d7b914")


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
            db.session.remove()
            upgrade(revision="d7e8f901ab23")
            existing_bill = db.session.get(Bill, bill_id)
            self.assertTrue(existing_bill.is_active)
            self.assertEqual(existing_bill.amount, Decimal("30"))
            self.assertIsNone(existing_bill.inactive_from)
            db.session.remove()
            downgrade(revision="c5d5a9b2e781")
            self.assertNotIn("is_active", {c["name"] for c in inspect(db.engine).get_columns("bills")})
            upgrade(revision="d7e8f901ab23")
            self.assertTrue(db.session.get(Bill, bill_id).is_active)
            db.session.remove()
            upgrade(revision="e8f901ab24cd")
            migrated_account = db.session.get(Account, account_id)
            self.assertEqual(migrated_account.early_pay_days, 0)
            observation = AccountBalanceObservation.query.filter_by(account_id=account_id).one()
            self.assertEqual(observation.balance, migrated_account.starting_balance)
            self.assertEqual(observation.balance_date, migrated_account.balance_as_of)
            self.assertIsNone(observation.recorded_at)
            self.assertEqual(observation.source, "imported")
            self.assertEqual(AccountForecastSnapshot.query.count(), 0)
            db.session.remove()
            downgrade(revision="d7e8f901ab23")
            self.assertNotIn("early_pay_days", {c["name"] for c in inspect(db.engine).get_columns("accounts")})
            upgrade(revision="e8f901ab24cd")
            self.assertEqual(AccountBalanceObservation.query.count(), 1)


if __name__ == "__main__":
    unittest.main()
