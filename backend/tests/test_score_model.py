import unittest

from app.services.score_model import (
    MatchAdjustments,
    MatchContext,
    TeamProfile,
    dixon_coles_scoreline_matrix,
    matrix_expected_goals,
    match_market_probabilities,
    predict_match,
    rake_scoreline_matrix,
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

    def test_neutral_venue_removes_designated_home_advantage(self):
        home = TeamProfile("h", "Home", "A", "HOM", "us", 1800, 0.05, 0.05)
        away = TeamProfile("a", "Away", "A", "AWY", "mx", 1800, 0.05, 0.05)
        prediction = predict_match(home, away, MatchContext(notes=("neutral venue",)))
        self.assertAlmostEqual(prediction["lambda_home"], prediction["lambda_away"], places=6)

    def test_market_raking_matches_requested_marginals(self):
        base = scoreline_matrix(1.4, 0.9)
        fitted = rake_scoreline_matrix(base, target_1x2=(0.55, 0.25, 0.20), target_over_2_5=0.48)
        probabilities = match_market_probabilities(fitted)
        self.assertAlmostEqual(sum(sum(row) for row in fitted), 1.0, places=9)
        self.assertAlmostEqual(probabilities["p_home"], 0.55, places=5)
        self.assertAlmostEqual(probabilities["p_draw"], 0.25, places=5)
        self.assertAlmostEqual(probabilities["p_away"], 0.20, places=5)
        self.assertAlmostEqual(probabilities["p_over_2_5"], 0.48, places=5)
        home_goals, away_goals = matrix_expected_goals(fitted)
        self.assertGreater(home_goals, away_goals)


if __name__ == "__main__":
    unittest.main()
