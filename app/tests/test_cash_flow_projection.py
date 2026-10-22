"""Regression tests for dated daily account cash-flow projections."""
import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.utils.cash_flow_projection import daily_account_projection


def account(**kwargs):
    values = dict(id=1, starting_balance=Decimal("100.00"),
                  balance_as_of=date(2026, 11, 1), incomes=[], bills=[])
    values.update(kwargs)
    return SimpleNamespace(**values)


class DailyAccountProjectionTests(unittest.TestCase):
    def test_snapshot_day_is_not_replayed(self):
        inc = SimpleNamespace(frequency="monthly", next_pay=date(2026, 10, 1),
                              amount=Decimal("50"))
        rows = daily_account_projection(account(incomes=[inc]),
                                        date(2026, 11, 1), date(2026, 11, 3))
        self.assertEqual([r["date"] for r in rows],
                         [date(2026, 11, 2), date(2026, 11, 3)])
        self.assertEqual(rows[-1]["balance"], Decimal("100.00"))

    def test_negative_balance_warning_and_card_bill_exclusion(self):
        bills = [
            SimpleNamespace(frequency="monthly", due_day=2, next_due=None,
                            amount=Decimal("120"), credit_card_id=None),
            SimpleNamespace(frequency="monthly", due_day=2, next_due=None,
                            amount=Decimal("500"), credit_card_id=7),
        ]
        rows = daily_account_projection(account(bills=bills),
                                        date(2026, 11, 2), date(2026, 11, 3))
        self.assertEqual(rows[0]["balance"], Decimal("-20.00"))
        self.assertTrue(rows[0]["negative"])
        self.assertEqual(rows[1]["balance"], Decimal("-20.00"))

    def test_later_report_window_includes_prior_changes(self):
        inc = SimpleNamespace(frequency="monthly", next_pay=date(2026, 10, 3),
                              amount=Decimal("25"))
        rows = daily_account_projection(account(incomes=[inc]),
                                        date(2026, 11, 5), date(2026, 11, 5))
        self.assertEqual(rows[0]["balance"], Decimal("125.00"))
        self.assertEqual(rows[0]["change"], Decimal("0.00"))

    def test_window_before_snapshot_is_empty(self):
        self.assertEqual(daily_account_projection(
            account(), date(2026, 10, 1), date(2026, 10, 31)), [])

    def test_planned_card_payments_reduce_linked_account_only(self):
        card = SimpleNamespace(id=3, payment_account_id=1, minimum_payment=Decimal("25"),
                               extra_payment=Decimal("0"), statement_close_day=15,
                               payment_due_day=10, bills=[], statements=[])
        rows = daily_account_projection(account(),
                                        date(2026, 11, 10), date(2026, 11, 10),
                                        [card])
        self.assertEqual(rows[0]["balance"], Decimal("75.00"))


if __name__ == "__main__":
    unittest.main()
