import unittest

from app.services.odds import devig_three_way, devig_two_way, model_lean


class OddsTest(unittest.TestCase):
    def test_two_way_devig_sums_to_one(self):
        home, away = devig_two_way(1.91, 1.91)
        self.assertAlmostEqual(home + away, 1.0)
        self.assertAlmostEqual(home, 0.5)

    def test_three_way_devig_sums_to_one(self):
        probs = devig_three_way(2.1, 3.2, 3.6)
        self.assertAlmostEqual(sum(probs), 1.0)

    def test_model_lean_threshold(self):
        self.assertEqual(model_lean(0.041, 0.01), "home")
        self.assertEqual(model_lean(0.0, 0.05), "away")
        self.assertEqual(model_lean(0.02, 0.01), "none")


if __name__ == "__main__":
    unittest.main()

