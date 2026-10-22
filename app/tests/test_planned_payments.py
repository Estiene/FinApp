"""Stage 5A planned-payment and Cash Flow regression tests.

Run from app/: python -m unittest discover -s tests -v
"""
import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.utils.planned_payments import (
    planned_card_payments, planned_payments_for_account,
)


def bill(amount, day, credit_card_id=1):
    return SimpleNamespace(
        amount=Decimal(amount), due_day=day, frequency="monthly",
        next_due=None, credit_card_id=credit_card_id,
    )


def card(*, bills=None, statements=None, minimum="25", extra="50",
         account=1, close=15, due=10, card_id=1, **settings):
    return SimpleNamespace(
        id=card_id, payment_account_id=account,
        minimum_payment=Decimal(minimum),
        extra_payment=Decimal(extra),
        statement_close_day=close, payment_due_day=due,
        bills=bills or [], statements=statements or [],
        **settings,
    )


def statement(close, balance, due=None, payments=None):
    return SimpleNamespace(
        statement_close_date=close,
        payment_due_date=due or date(close.year + (close.month == 12),
                                      close.month % 12 + 1, 10),
        statement_balance=None if balance is None else Decimal(balance),
        payments=payments or [],
    )


class PlannedPaymentTests(unittest.TestCase):
    START = date(2026, 12, 1)
    END = date(2026, 12, 31)

    def events(self, item):
        return planned_card_payments(item, self.START, self.END)

    def test_estimated_cycle_uses_full_recurring_bill_total(self):
        item = card(bills=[bill("100", 2), bill("100", 12)])
        events = self.events(item)
        self.assertIn(dict(date=date(2026, 12, 10), kind="bill_related",
                           amount=Decimal("200.00"), card_id=1), events)

    def test_confirmed_statement_caps_bill_related_but_not_minimum(self):
        s = statement(date(2026, 11, 15), "150")
        item = card(bills=[bill("100", 2), bill("100", 12)], statements=[s])
        events = self.events(item)
        self.assertEqual(
            sum(e["amount"] for e in events if e["date"] == date(2026, 12, 10)),
            Decimal("225.00"),
        )  # 150 bill-related + 25 minimum + 50 extra

    def test_early_recorded_payment_does_not_reduce_conservative_plan(self):
        s = statement(date(2026, 11, 15), "150", payments=[
            SimpleNamespace(amount=Decimal("50"), payment_date=date(2026, 11, 20))
        ])
        item = card(bills=[bill("100", 2), bill("100", 12)], statements=[s])
        self.assertEqual(
            sum(e["amount"] for e in self.events(item)),
            Decimal("225.00"),
        )

    def test_estimated_statement_is_not_a_cap(self):
        s = statement(date(2026, 11, 15), None)
        item = card(bills=[bill("100", 2), bill("100", 12)], statements=[s])
        self.assertEqual(
            next(e["amount"] for e in self.events(item)
                 if e["kind"] == "bill_related"),
            Decimal("200.00"),
        )

    def test_extra_payment_can_be_on_earlier_fixed_day(self):
        item = card(minimum="25", extra="50", extra_payment_day=8)
        events = self.events(item)
        self.assertIn(dict(date=date(2026, 12, 8), kind="extra",
                           amount=Decimal("50.00"), card_id=1), events)
        self.assertIn(dict(date=date(2026, 12, 10), kind="minimum",
                           amount=Decimal("25.00"), card_id=1), events)

    def test_bill_payment_can_be_days_before_due_date(self):
        item = card(bills=[bill("100", 2)], minimum="0", extra="0",
                    bill_payment_timing="days_before_due",
                    bill_payment_days_before=3)
        self.assertEqual(self.events(item), [
            dict(date=date(2026, 12, 7), kind="bill_related",
                 amount=Decimal("100.00"), card_id=1)
        ])

    def test_account_filter_and_multiple_cards(self):
        first = card(minimum="25", extra="0", account=1, card_id=1)
        second = card(minimum="30", extra="0", account=1, card_id=2)
        other = card(minimum="100", extra="0", account=2, card_id=3)
        totals = planned_payments_for_account(
            [first, second, other], 1, self.START, self.END
        )
        self.assertEqual(totals, {date(2026, 12, 10): Decimal("55.00")})

    def test_no_events_outside_requested_window(self):
        self.assertEqual(planned_card_payments(
            card(), date(2026, 12, 12), date(2026, 12, 14)
        ), [])

    def test_february_due_day_clamps(self):
        item = card(minimum="25", extra="0", due=31)
        events = planned_card_payments(
            item, date(2027, 2, 1), date(2027, 2, 28)
        )
        self.assertIn(dict(date=date(2027, 2, 28), kind="minimum",
                           amount=Decimal("25.00"), card_id=1), events)


class CashFlowRouteTests(unittest.TestCase):
    def setUp(self):
        from flask import Flask
        from src.models import db
        from src.routes import bp

        self.db = db
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

    def tearDown(self):
        self.db.session.remove()
        self.db.drop_all()
        self.ctx.pop()

    def test_cash_flow_excludes_card_funded_bills_and_adds_planned_payments(self):
        from src.models import Account, Bill, CreditCard
        acct = Account(name="Checking")
        self.db.session.add(acct)
        self.db.session.flush()
        visa = CreditCard(
            name="Visa", balance=Decimal("500"), balance_as_of=date(2026, 11, 1),
            payment_account_id=acct.id, statement_close_day=15,
            payment_due_day=10, minimum_payment=Decimal("25"),
            extra_payment=Decimal("50"),
        )
        self.db.session.add(visa)
        self.db.session.flush()
        self.db.session.add_all([
            Bill(name="Electric", owner="Test", due_day=2,
                 amount=Decimal("100"), account_id=acct.id,
                 credit_card_id=visa.id),
            Bill(name="Rent", owner="Test", due_day=4,
                 amount=Decimal("300"), account_id=acct.id),
        ])
        self.db.session.commit()
        response = self.app.test_client().get(
            f"/report?year=2026&month=12&starting_balance_{acct.id}=1000"
        )
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Credit Card Payments", html)
        self.assertIn("Cash Flow", html)
        # Nov 2 card charge is paid in December; December 2 charge
        # belongs to the next statement and is not directly deducted.
        self.assertIn("Ending: $525.00", html)
        # 1000 - 300 rent - 100 planned bill payment - 25 minimum - 50 extra

    def test_new_card_scheduling_settings_are_saved(self):
        from src.models import Account, CreditCard
        acct = Account(name="Checking")
        self.db.session.add(acct)
        self.db.session.commit()
        response = self.app.test_client().post("/credit-cards", data={
            "name": "Visa", "payment_account_id": str(acct.id),
            "balance": "100", "balance_as_of": "2026-10-01",
            "minimum_payment": "25", "extra_payment": "50",
            "statement_close_day": "15", "payment_due_day": "10",
            "extra_payment_day": "8",
            "bill_payment_timing": "days_before_due",
            "bill_payment_days_before": "3",
        })
        self.assertEqual(response.status_code, 302)
        visa = CreditCard.query.filter_by(name="Visa").one()
        self.assertEqual(visa.extra_payment_day, 8)
        self.assertEqual(visa.bill_payment_timing, "days_before_due")
        self.assertEqual(visa.bill_payment_days_before, 3)
        self.assertIn("Extra Payment Day", self.app.test_client().get(
            f"/credit-cards/{visa.id}/edit"
        ).get_data(as_text=True))

    def test_invalid_scheduling_settings_do_not_save_card(self):
        from src.models import Account, CreditCard
        acct = Account(name="Checking")
        self.db.session.add(acct)
        self.db.session.commit()
        base = {
            "name": "Visa", "payment_account_id": str(acct.id),
            "balance": "100", "balance_as_of": "2026-10-01",
            "minimum_payment": "25", "extra_payment": "50",
            "statement_close_day": "15", "payment_due_day": "10",
            "extra_payment_day": "32",
            "bill_payment_timing": "days_before_due",
            "bill_payment_days_before": "3",
        }
        response = self.app.test_client().post("/credit-cards", data=base)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CreditCard.query.count(), 0)
        base["extra_payment_day"] = "8"
        base["bill_payment_days_before"] = "32"
        self.app.test_client().post("/credit-cards", data=base)
        self.assertEqual(CreditCard.query.count(), 0)

    def test_edit_card_scheduling_settings_updates_cash_flow(self):
        from src.models import Account, CreditCard, Bill
        acct = Account(name="Checking")
        self.db.session.add(acct)
        self.db.session.flush()
        visa = CreditCard(
            name="Visa", payment_account_id=acct.id,
            balance=Decimal("500"), balance_as_of=date(2026, 10, 1),
            statement_close_day=15, payment_due_day=10,
            minimum_payment=Decimal("25"), extra_payment=Decimal("50"),
        )
        self.db.session.add(visa)
        self.db.session.flush()
        self.db.session.add(Bill(
            name="Electric", owner="Test", due_day=2, amount=Decimal("100"),
            account_id=acct.id, credit_card_id=visa.id,
        ))
        self.db.session.commit()
        response = self.app.test_client().post(
            f"/credit-cards/{visa.id}/edit", data={
                "name": "Visa", "payment_account_id": str(acct.id),
                "balance": "500", "balance_as_of": "2026-10-01",
                "minimum_payment": "25", "extra_payment": "50",
                "statement_close_day": "15", "payment_due_day": "10",
                "extra_payment_day": "8",
                "bill_payment_timing": "days_before_due",
                "bill_payment_days_before": "3",
            }
        )
        self.assertEqual(response.status_code, 302)
        self.db.session.refresh(visa)
        events = planned_card_payments(
            visa, date(2026, 12, 1), date(2026, 12, 31)
        )
        self.assertEqual(
            {e["kind"]: e["date"] for e in events},
            {"extra": date(2026, 12, 8),
             "minimum": date(2026, 12, 10),
             "bill_related": date(2026, 12, 7)},
        )

    def test_bill_payment_method_card_create_edit_and_cash_flow(self):
        from src.models import Account, Bill, CreditCard
        checking = Account(name="Checking")
        savings = Account(name="Savings")
        self.db.session.add_all([checking, savings])
        self.db.session.flush()
        visa = CreditCard(
            name="Visa", payment_account_id=checking.id,
            balance=Decimal("500"), balance_as_of=date(2026, 10, 1),
            statement_close_day=15, payment_due_day=10,
            minimum_payment=Decimal("25"), extra_payment=Decimal("50"),
            extra_payment_day=8, bill_payment_timing="days_before_due",
            bill_payment_days_before=3,
        )
        self.db.session.add(visa)
        self.db.session.commit()
        form = {
            "name": "Electric", "owner": "Test", "amount": "100",
            "frequency": "monthly", "due_day": "2",
            "payment_method": f"card:{visa.id}",
        }
        self.assertIn('value="card:', self.app.test_client().get("/bills").get_data(as_text=True))
        self.assertEqual(self.app.test_client().post("/bills", data=form).status_code, 302)
        electric = Bill.query.filter_by(name="Electric").one()
        self.assertEqual(electric.credit_card_id, visa.id)
        self.assertEqual(electric.account_id, checking.id)
        edit_html = self.app.test_client().get(f"/bills/{electric.id}").get_data(as_text=True)
        self.assertIn(f'value="card:{visa.id}" selected', edit_html)
        cashflow = self.app.test_client().get(
            f"/report?year=2026&month=12&starting_balance_{checking.id}=1000"
        ).get_data(as_text=True)
        self.assertIn("Ending: $825.00", cashflow)
        # Switch to bank funding and confirm the card association clears.
        form["payment_method"] = f"account:{savings.id}"
        self.assertEqual(self.app.test_client().post(
            f"/bills/{electric.id}", data=form
        ).status_code, 302)
        self.db.session.refresh(electric)
        self.assertIsNone(electric.credit_card_id)
        self.assertEqual(electric.account_id, savings.id)

    def test_bill_payment_method_rejects_invalid_card(self):
        from src.models import Account, Bill
        checking = Account(name="Checking")
        self.db.session.add(checking)
        self.db.session.commit()
        response = self.app.test_client().post("/bills", data={
            "name": "Electric", "owner": "Test", "amount": "100",
            "frequency": "monthly", "due_day": "2",
            "payment_method": "card:999999",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Bill.query.count(), 0)

    def test_cash_flow_shows_card_charges_without_reducing_balance(self):
        from src.models import Account, Bill, CreditCard
        checking = Account(name="Checking")
        self.db.session.add(checking)
        self.db.session.flush()
        visa = CreditCard(
            name="Visa", payment_account_id=checking.id,
            balance=Decimal("500"), balance_as_of=date(2026, 10, 1),
            statement_close_day=15, payment_due_day=10,
            minimum_payment=Decimal("25"), extra_payment=Decimal("50"),
            extra_payment_day=8, bill_payment_timing="days_before_due",
            bill_payment_days_before=3,
        )
        self.db.session.add(visa)
        self.db.session.flush()
        self.db.session.add_all([
            Bill(name="Electric", owner="Test", due_day=2,
                 amount=Decimal("100"), account_id=checking.id,
                 credit_card_id=visa.id),
            Bill(name="Internet", owner="Test", due_day=2,
                 amount=Decimal("40"), account_id=checking.id,
                 credit_card_id=visa.id),
        ])
        self.db.session.commit()
        html = self.app.test_client().get(
            f"/report?year=2026&month=11&starting_balance_{checking.id}=2000"
        ).get_data(as_text=True)
        self.assertIn("Credit Card Charges", html)
        self.assertIn("View credit card charges for 2026-11-02", html)
        self.assertIn("Electric", html)
        self.assertIn("Internet", html)
        self.assertIn("Visa", html)
        self.assertIn("$140.00", html)
        self.assertIn("Total", html)
        self.assertIn("Ending: $1785.00", html)
        self.assertIn("$-215.00", html)

    def test_cash_flow_only_deducts_payments_from_linked_account(self):
        from src.models import Account, CreditCard
        checking = Account(name="Checking")
        savings = Account(name="Savings")
        self.db.session.add_all([checking, savings])
        self.db.session.flush()
        self.db.session.add(CreditCard(
            name="Visa", balance=Decimal("500"),
            balance_as_of=date(2026, 11, 1),
            payment_account_id=checking.id, statement_close_day=15,
            payment_due_day=10, minimum_payment=Decimal("25"),
            extra_payment=Decimal("50"),
        ))
        self.db.session.commit()
        response = self.app.test_client().get(
            f"/report?year=2026&month=12&starting_balance_{checking.id}=1000"
            f"&starting_balance_{savings.id}=1000"
        )
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Ending: $925.00", html)
        self.assertIn("Ending: $1000.00", html)


if __name__ == "__main__":
    unittest.main()
