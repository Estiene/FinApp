"""Unit tests for live dashboard scheduling and projections."""

import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.utils.dashboard import bill_dates, build_dashboard_data, income_dates


def income(frequency, amount="100.00", next_pay=None, day1=None, day2=None):
    return SimpleNamespace(
        frequency=frequency,
        amount=Decimal(amount),
        next_pay=next_pay,
        day_of_month_1=day1,
        day_of_month_2=day2,
    )


def bill(amount="50.00", due_day=15):
    return SimpleNamespace(amount=Decimal(amount), due_day=due_day)


def account(name, starting_balance="1000.00", balance_as_of=None, incomes=None, bills=None):
    return SimpleNamespace(
        name=name,
        starting_balance=Decimal(starting_balance),
        balance_as_of=balance_as_of,
        incomes=incomes or [],
        bills=bills or [],
    )


def card_fixture(**values):
    defaults = dict(
        id=1, statement_close_day=15, payment_due_day=10,
        extra_payment_day=None, bill_payment_timing="due_date",
        bill_payment_days_before=0,
    )
    defaults.update(values)
    return SimpleNamespace(**defaults)


class DashboardDateTests(unittest.TestCase):
    def test_weekly_dates_follow_original_payday_anchor(self):
        item = income("weekly", next_pay=date(2026, 10, 5))
        self.assertEqual(
            income_dates(item, date(2026, 10, 1), date(2026, 10, 31)),
            [
                date(2026, 10, 5),
                date(2026, 10, 12),
                date(2026, 10, 19),
                date(2026, 10, 26),
            ],
        )

    def test_biweekly_dates_follow_original_payday_anchor(self):
        item = income("biweekly", next_pay=date(2026, 9, 25))
        self.assertEqual(
            income_dates(item, date(2026, 10, 1), date(2026, 10, 31)),
            [date(2026, 10, 9), date(2026, 10, 23)],
        )

    def test_monthly_income_clamps_day_31_in_february(self):
        item = income("monthly", next_pay=date(2026, 1, 31))
        self.assertEqual(
            income_dates(item, date(2027, 2, 1), date(2027, 2, 28)),
            [date(2027, 2, 28)],
        )

    def test_twice_monthly_income_clamps_and_deduplicates_dates(self):
        item = income("twice_monthly", day1=30, day2=31)
        self.assertEqual(
            income_dates(item, date(2027, 2, 1), date(2027, 2, 28)),
            [date(2027, 2, 28)],
        )

    def test_monthly_bill_clamps_day_31_in_february(self):
        item = bill(due_day=31)
        self.assertEqual(
            bill_dates(item, date(2027, 2, 1), date(2027, 2, 28)),
            [date(2027, 2, 28)],
        )


class DashboardProjectionTests(unittest.TestCase):
    def test_current_month_totals_and_projection_are_calculated_live(self):
        acct = account(
            "Checking",
            starting_balance="1000.00",
            balance_as_of=date(2026, 10, 18),
            incomes=[income("weekly", amount="1000.00", next_pay=date(2026, 10, 5))],
            bills=[bill(amount="100.00", due_day=20)],
        )

        result = build_dashboard_data([acct], today=date(2026, 10, 20))

        self.assertEqual(result["total_income"], Decimal("4000.00"))
        self.assertEqual(result["total_bills"], Decimal("100.00"))
        self.assertEqual(
            result["account_summaries"][0]["projected_balance"],
            Decimal("1900.00"),
        )

    def test_unlinked_card_does_not_reserve_from_account_without_id(self):
        today = date(2026, 10, 21)
        acct = account("Checking", starting_balance="1000.00", balance_as_of=today)
        unlinked = card_fixture(
            balance=Decimal("500"), balance_as_of=today,
            minimum_payment=Decimal("25"), extra_payment=Decimal("50"),
            payment_account_id=None, statements=[], bills=[],
        )
        result = build_dashboard_data([acct], today=today, credit_cards=[unlinked])
        summary = result["account_summaries"][0]
        self.assertEqual(summary["reserved_for_credit_cards"], Decimal("0.00"))
        self.assertEqual(summary["spendable_balance"], Decimal("1000.00"))

    def test_credit_card_reservation_reduces_spendable_not_projected_balance(self):
        today = date(2026, 10, 21)

        acct = account(
            "Checking",
            starting_balance="2500.00",
            balance_as_of=today,
        )
        acct.id = 1

        statement = SimpleNamespace(
            statement_close_date=date(2026, 10, 15),
            payment_due_date=date(2026, 11, 10),
            statement_balance=Decimal("500.00"),
            planned_payment=None,
            actual_payment=None,
            payment_date=None,
        )

        card = card_fixture(
            balance=Decimal("860.00"),
            balance_as_of=today,
            minimum_payment=Decimal("40.00"),
            extra_payment=Decimal("100.00"),
            payment_account_id=1,
            statements=[statement],
            bills=[],
        )

        result = build_dashboard_data(
            [acct], today=today, credit_cards=[card]
        )
        summary = result["account_summaries"][0]

        self.assertEqual(
            summary["projected_balance"], Decimal("2500.00")
        )
        self.assertEqual(
            summary["reserved_for_credit_cards"], Decimal("140.00")
        )
        self.assertEqual(
            summary["spendable_balance"], Decimal("2360.00")
        )

    def test_multiple_cards_reserve_from_same_checking_account(self):
        today = date(2026, 10, 21)

        acct = account(
            "Checking",
            starting_balance="2500.00",
            balance_as_of=today,
        )
        acct.id = 1

        def make_card(balance, minimum, extra):
            statement = SimpleNamespace(
                statement_close_date=date(2026, 10, 15),
                payment_due_date=date(2026, 11, 10),
                statement_balance=Decimal(balance),
                planned_payment=None,
                actual_payment=None,
                payment_date=None,
            )
            return card_fixture(
                balance=Decimal(balance),
                balance_as_of=today,
                minimum_payment=Decimal(minimum),
                extra_payment=Decimal(extra),
                payment_account_id=1,
                statements=[statement],
                bills=[],
            )

        cards = [
            make_card("860.00", "40.00", "100.00"),
            make_card("300.00", "25.00", "50.00"),
        ]

        result = build_dashboard_data(
            [acct], today=today, credit_cards=cards
        )
        summary = result["account_summaries"][0]

        self.assertEqual(
            summary["projected_balance"], Decimal("2500.00")
        )
        self.assertEqual(
            summary["reserved_for_credit_cards"], Decimal("215.00")
        )
        self.assertEqual(
            summary["spendable_balance"], Decimal("2285.00")
        )

    def test_reservation_only_affects_designated_account(self):
        today = date(2026, 10, 21)
        checking = account("Checking", starting_balance="2500.00", balance_as_of=today)
        savings = account("Savings", starting_balance="1000.00", balance_as_of=today)
        checking.id = 1
        savings.id = 2

        statement = SimpleNamespace(
            statement_close_date=date(2026, 10, 15),
            payment_due_date=date(2026, 11, 10),
            statement_balance=Decimal("500.00"),
            planned_payment=None,
            actual_payment=None,
            payment_date=None,
        )
        card = card_fixture(
            balance=Decimal("860.00"),
            balance_as_of=today,
            minimum_payment=Decimal("40.00"),
            extra_payment=Decimal("100.00"),
            payment_account_id=1,
            statements=[statement],
            bills=[],
        )

        result = build_dashboard_data(
            [checking, savings], today=today, credit_cards=[card]
        )
        first, second = result["account_summaries"]

        self.assertEqual(first["reserved_for_credit_cards"], Decimal("140.00"))
        self.assertEqual(first["spendable_balance"], Decimal("2360.00"))
        self.assertEqual(second["reserved_for_credit_cards"], Decimal("0.00"))
        self.assertEqual(second["spendable_balance"], Decimal("1000.00"))

    def test_completed_statement_payment_is_not_reserved_again(self):
        today = date(2026, 10, 21)
        checking = account(
            "Checking",
            starting_balance="2500.00",
            balance_as_of=date(2026, 10, 1),
        )
        checking.id = 1

        statement = SimpleNamespace(
            statement_close_date=date(2026, 9, 15),
            payment_due_date=date(2026, 10, 10),
            statement_balance=Decimal("500.00"),
            planned_payment=None,
            actual_payment=Decimal("140.00"),
            payment_date=date(2026, 10, 15),
        )
        card = card_fixture(
            balance=Decimal("1000.00"),
            balance_as_of=date(2026, 10, 1),
            minimum_payment=Decimal("40.00"),
            extra_payment=Decimal("100.00"),
            payment_account_id=1,
            statements=[statement],
            bills=[],
        )

        result = build_dashboard_data(
            [checking], today=today, credit_cards=[card]
        )
        summary = result["account_summaries"][0]

        self.assertEqual(summary["projected_balance"], Decimal("2360.00"))
        self.assertEqual(summary["reserved_for_credit_cards"], Decimal("0.00"))
        self.assertEqual(summary["spendable_balance"], Decimal("2360.00"))

    def test_balance_snapshot_date_is_not_counted_twice(self):
        acct = account(
            "Checking",
            starting_balance="1000.00",
            balance_as_of=date(2026, 10, 20),
            incomes=[income("weekly", amount="500.00", next_pay=date(2026, 10, 20))],
            bills=[bill(amount="100.00", due_day=20)],
        )

        result = build_dashboard_data([acct], today=date(2026, 10, 20))

        self.assertEqual(
            result["account_summaries"][0]["projected_balance"],
            Decimal("1000.00"),
        )


if __name__ == "__main__":
    unittest.main()
