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


if __name__ == "__main__":
    unittest.main()
