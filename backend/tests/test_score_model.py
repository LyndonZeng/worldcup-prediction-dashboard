import unittest

from app.services.score_model import TeamProfile, match_market_probabilities, predict_match, scoreline_matrix


class ScoreModelTest(unittest.TestCase):
    def test_scoreline_matrix_is_normalized(self):
        matrix = scoreline_matrix(1.4, 0.9)
        self.assertAlmostEqual(sum(sum(row) for row in matrix), 1.0, places=9)

    def test_1x2_probabilities_sum_to_one(self):
        matrix = scoreline_matrix(1.4, 0.9)
        probs = match_market_probabilities(matrix)
        self.assertAlmostEqual(probs["p_home"] + probs["p_draw"] + probs["p_away"], 1.0, places=5)

    def test_prediction_contains_score_markets(self):
        home = TeamProfile("h", "Home", "A", "HOM", "us", 1800, 0.1, 0.04)
        away = TeamProfile("a", "Away", "A", "AWY", "mx", 1700, 0.02, 0.01)
        prediction = predict_match(home, away)
        self.assertGreater(prediction["lambda_home"], prediction["lambda_away"])
        self.assertIn("top_scorelines", prediction)


if __name__ == "__main__":
    unittest.main()

