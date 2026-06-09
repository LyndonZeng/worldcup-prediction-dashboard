import math
import unittest

from app.services.handicap import (
    asian_handicap_probabilities,
    asian_market_from_matrix,
    settle_asian_margin,
    split_asian_line,
)


class AsianHandicapTest(unittest.TestCase):
    def test_quarter_lines_split_into_half_stakes(self):
        self.assertEqual([float(x) for x in split_asian_line(-0.25)], [0.0, -0.5])
        self.assertEqual([float(x) for x in split_asian_line(-0.75)], [-0.5, -1.0])
        self.assertEqual([float(x) for x in split_asian_line(0.25)], [0.5, 0.0])
        self.assertEqual([float(x) for x in split_asian_line(0.75)], [1.0, 0.5])

    def test_settlement_examples(self):
        self.assertEqual(settle_asian_margin(0, -0.25), "half_loss")
        self.assertEqual(settle_asian_margin(1, -0.25), "win")
        self.assertEqual(settle_asian_margin(1, -0.75), "half_win")
        self.assertEqual(settle_asian_margin(0, -0.75), "loss")
        self.assertEqual(settle_asian_margin(1, -1), "push")
        self.assertEqual(settle_asian_margin(2, -1), "win")
        self.assertEqual(settle_asian_margin(-1, 1), "push")
        self.assertEqual(settle_asian_margin(-2, 1), "loss")

    def test_probabilities_sum_to_one(self):
        matrix = [
            [0.10, 0.08, 0.02],
            [0.11, 0.20, 0.07],
            [0.15, 0.17, 0.10],
        ]
        probs = asian_handicap_probabilities(matrix, -0.75)
        self.assertAlmostEqual(probs.total, 1.0, places=9)

    def test_probability_buckets_match_manual_matrix(self):
        matrix = [
            [0.10, 0.10],
            [0.30, 0.50],
        ]
        probs = asian_handicap_probabilities(matrix, -0.25)
        self.assertAlmostEqual(probs.win, 0.30)
        self.assertAlmostEqual(probs.half_loss, 0.60)
        self.assertAlmostEqual(probs.loss, 0.10)

    def test_fair_odds_break_even(self):
        matrix = [
            [0.10, 0.10],
            [0.30, 0.50],
        ]
        probs = asian_handicap_probabilities(matrix, -0.25)
        self.assertIsNotNone(probs.fair_decimal_odds)
        expected_return = probs.expected_return(probs.fair_decimal_odds)
        self.assertTrue(math.isclose(expected_return or 0, 0.0, abs_tol=1e-9))

    def test_two_sided_market_uses_opposite_line(self):
        matrix = [
            [0.20, 0.10],
            [0.30, 0.40],
        ]
        market = asian_market_from_matrix(matrix, -0.5, 2.1, 1.8)
        self.assertAlmostEqual(market["home"]["positive_probability"], 0.30)
        self.assertAlmostEqual(market["away"]["positive_probability"], 0.70)


if __name__ == "__main__":
    unittest.main()

