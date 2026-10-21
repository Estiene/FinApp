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
