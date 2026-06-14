import unittest

from app.services.score_model import (
    MatchAdjustments,
    TeamProfile,
    dixon_coles_scoreline_matrix,
    match_market_probabilities,
    predict_match,
    scoreline_matrix,
)


class ScoreModelTest(unittest.TestCase):
    def test_scoreline_matrix_is_normalized(self):
        matrix = scoreline_matrix(1.4, 0.9)
        self.assertAlmostEqual(sum(sum(row) for row in matrix), 1.0, places=9)

    def test_1x2_probabilities_sum_to_one(self):
        matrix = scoreline_matrix(1.4, 0.9)
        probs = match_market_probabilities(matrix)
        self.assertAlmostEqual(probs["p_home"] + probs["p_draw"] + probs["p_away"], 1.0, places=5)

    def test_dixon_coles_matrix_is_normalized_and_low_score_adjusted(self):
        poisson = scoreline_matrix(1.4, 0.9)
        dixon_coles = dixon_coles_scoreline_matrix(1.4, 0.9, rho=-0.06)
        self.assertAlmostEqual(sum(sum(row) for row in dixon_coles), 1.0, places=9)
        self.assertNotAlmostEqual(poisson[1][1], dixon_coles[1][1], places=6)

    def test_prediction_contains_score_markets(self):
        home = TeamProfile("h", "Home", "A", "HOM", "us", 1800, 0.1, 0.04)
        away = TeamProfile("a", "Away", "A", "AWY", "mx", 1700, 0.02, 0.01)
        prediction = predict_match(home, away)
        self.assertGreater(prediction["lambda_home"], prediction["lambda_away"])
        self.assertIn("top_scorelines", prediction)

    def test_adjustments_change_expected_goals(self):
        home = TeamProfile("h", "Home", "A", "HOM", "us", 1800, 0.1, 0.04)
        away = TeamProfile("a", "Away", "A", "AWY", "mx", 1700, 0.02, 0.01)
        base = predict_match(home, away)
        adjusted = predict_match(
            home,
            away,
            adjustments=MatchAdjustments(home_goal_mult=1.08, away_goal_mult=0.94, total_goal_mult=0.98),
        )
        self.assertGreater(adjusted["lambda_home"], base["lambda_home"])
        self.assertLess(adjusted["lambda_away"], base["lambda_away"])


if __name__ == "__main__":
    unittest.main()
