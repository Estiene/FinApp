import unittest
from decimal import Decimal
from src.utils.card_forecast import payoff_estimate, utilization


class CardForecastTests(unittest.TestCase):
    def test_utilization_and_missing_limit(self):
        self.assertEqual(utilization("250", "1000"), Decimal("25.0"))
        self.assertIsNone(utilization("250", None))

    def test_over_limit_utilization(self):
        self.assertEqual(utilization("1200", "1000"), Decimal("120.0"))

    def test_zero_apr_payoff(self):
        self.assertEqual(payoff_estimate("100", "0", "30"), {
            "months": 4, "interest": Decimal("0.00"),
            "total_paid": Decimal("100.00")})

    def test_interest_exceeds_payment(self):
        self.assertIsNone(payoff_estimate("1000", "24", "10"))

    def test_monthly_interest_and_last_payment(self):
        self.assertEqual(payoff_estimate("100", "12", "60"), {
            "months": 2, "interest": Decimal("1.41"),
            "total_paid": Decimal("101.41")})

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            utilization("100", "0")
        with self.assertRaises(ValueError):
            payoff_estimate("100", "-1", "10")
        with self.assertRaises(ValueError):
            payoff_estimate("100", "101", "10")


    def test_dashboard_card_forecast(self):
        from datetime import date
        from types import SimpleNamespace
        from src.utils.dashboard import build_dashboard_data
        card = SimpleNamespace(
            id=7, name="Visa", balance=Decimal("100.00"),
            balance_as_of=date(2026, 11, 1), bills=[], statements=[],
            payments=[], minimum_payment=Decimal("60"),
            extra_payment=Decimal("0"), payment_account_id=1,
            annual_percentage_rate=Decimal("12"),
            credit_limit=Decimal("1000"),
            promotional_apr=None, promotional_apr_end_date=None,
        )
        result = build_dashboard_data([], today=date(2026, 11, 1),
                                      credit_cards=[card])
        summary = result["credit_card_summaries"][0]
        self.assertEqual(summary["utilization_pct"], Decimal("10.0"))
        self.assertEqual(summary["effective_apr"], Decimal("12"))
        self.assertEqual(summary["payoff_estimate"]["months"], 2)

if __name__ == "__main__":
    unittest.main()
