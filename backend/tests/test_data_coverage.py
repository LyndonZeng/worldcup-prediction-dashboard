import unittest

from app.services import data_store
from app.services.predictions import all_matches, tournament_probabilities


class DataCoverageTest(unittest.TestCase):
    def test_seed_dataset_contains_full_group_stage(self):
        teams = data_store.teams()
        fixtures = data_store.fixtures()
        self.assertEqual(len(teams), 48)
        self.assertEqual(len(fixtures), 72)
        self.assertEqual({team.group for team in teams.values()}, set("ABCDEFGHIJKL"))

    def test_every_fixture_references_known_teams(self):
        team_ids = set(data_store.teams())
        for fixture in data_store.fixtures():
            self.assertIn(fixture["home_team_id"], team_ids)
            self.assertIn(fixture["away_team_id"], team_ids)
            self.assertNotEqual(fixture["home_team_id"], fixture["away_team_id"])

    def test_predictions_and_tournament_cover_seed_dataset(self):
        matches = all_matches()
        tournament = tournament_probabilities()
        self.assertEqual(len(matches), 72)
        self.assertEqual(len(tournament["teams"]), 48)
        self.assertAlmostEqual(
            sum(row["title_probability"] for row in tournament["teams"]),
            1.0,
            places=5,
        )
        self.assertEqual(tournament["projected_matches_total"], 104)
        self.assertEqual(tournament["group_stage_matches"], 72)
        self.assertEqual(tournament["knockout_projected_matches"], 32)
        self.assertEqual(
            sum(len(round_row["matches"]) for round_row in tournament["bracket"]["rounds"]),
            32,
        )
        self.assertIn("raw_title_probability", tournament["teams"][0])
        self.assertIn("title_anchor", tournament)

    def test_prediction_factors_separate_real_inputs_from_proxies(self):
        match = all_matches()[0]
        used = [row for row in match["factor_breakdown"] if row["used_in_model"]]
        display_only = [row for row in match["factor_breakdown"] if not row["used_in_model"]]
        self.assertTrue(used)
        self.assertTrue(display_only)
        self.assertTrue(any(row["data_quality"] == "proxy" for row in display_only))
        self.assertTrue(any(row["category"] == "待接入" for row in display_only))

    def test_optional_public_snapshots_are_safe_to_read(self):
        self.assertIsInstance(data_store.prediction_markets(), list)
        self.assertIsInstance(data_store.live_weather(), dict)
        self.assertIn("teams", data_store.historical_results_summary())


if __name__ == "__main__":
    unittest.main()
