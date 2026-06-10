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

    def test_optional_public_snapshots_are_safe_to_read(self):
        self.assertIsInstance(data_store.prediction_markets(), list)
        self.assertIsInstance(data_store.live_weather(), dict)
        self.assertIn("teams", data_store.historical_results_summary())


if __name__ == "__main__":
    unittest.main()
