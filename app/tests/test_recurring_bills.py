"""Regression coverage for Stage 2 recurring bills."""
import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.utils.dashboard import bill_dates, build_dashboard_data


def bill(frequency="monthly", due_day=15, next_due=None, amount="50.00"):
    return SimpleNamespace(frequency=frequency, due_day=due_day, next_due=next_due, amount=Decimal(amount))


class RecurringBillTests(unittest.TestCase):
    def test_existing_monthly_bill_still_recurs(self):
        self.assertEqual(bill_dates(bill(due_day=31), date(2027, 2, 1), date(2027, 3, 31)), [date(2027, 2, 28), date(2027, 3, 31)])

    def test_weekly_schedule(self):
        self.assertEqual(bill_dates(bill("weekly", next_due=date(2026, 10, 2)), date(2026, 10, 1), date(2026, 10, 31)), [date(2026, 10, 2), date(2026, 10, 9), date(2026, 10, 16), date(2026, 10, 23), date(2026, 10, 30)])

    def test_biweekly_schedule(self):
        self.assertEqual(bill_dates(bill("biweekly", next_due=date(2026, 9, 25)), date(2026, 10, 1), date(2026, 10, 31)), [date(2026, 10, 9), date(2026, 10, 23)])

    def test_every_three_weeks_can_occur_twice_in_month(self):
        self.assertEqual(bill_dates(bill("every_three_weeks", next_due=date(2026, 10, 1)), date(2026, 10, 1), date(2026, 10, 31)), [date(2026, 10, 1), date(2026, 10, 22)])

    def test_interval_schedule_never_backdates_before_anchor(self):
        self.assertEqual(bill_dates(bill("weekly", next_due=date(2026, 10, 20)), date(2026, 10, 1), date(2026, 10, 19)), [])

    def test_dashboard_counts_multiple_bill_occurrences(self):
        account = SimpleNamespace(
            starting_balance=Decimal("1000.00"), balance_as_of=date(2026, 10, 1),
            incomes=[], bills=[bill("every_three_weeks", next_due=date(2026, 10, 1), amount="75.00")])
        result = build_dashboard_data([account], today=date(2026, 10, 25))
        self.assertEqual(result["total_bills"], Decimal("150.00"))
        self.assertEqual(result["account_summaries"][0]["projected_balance"], Decimal("925.00"))


if __name__ == "__main__":
    unittest.main()
