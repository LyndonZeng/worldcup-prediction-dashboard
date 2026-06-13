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
        self.assertIn("top_scorelines", matches[0])
        self.assertIn("event_predictions", matches[0])
        self.assertIn("market_summary", matches[0])
        self.assertIn("one_x_two", matches[0]["market_summary"])
        self.assertIn("over_under_2_5", matches[0]["market_summary"])
        lines = {row["line"] for row in matches[0]["handicap_preview"]}
        self.assertIn(-2.5, lines)
        self.assertIn(2.5, lines)

    def test_market_summary_devig_probabilities_are_bounded(self):
        matches = all_matches()
        available = [
            match["market_summary"]["one_x_two"]
            for match in matches
            if match["market_summary"]["one_x_two"]["status"] == "available"
        ]
        if not available:
            self.skipTest("No live 1X2 market snapshot available")
        probs = available[0]["market_probabilities"]
        self.assertAlmostEqual(probs["home"] + probs["draw"] + probs["away"], 1.0, places=5)
        for value in probs.values():
            self.assertGreaterEqual(value, 0)
            self.assertLessEqual(value, 1)

    def test_event_predictions_are_bounded_and_complete(self):
        match = all_matches()[0]
        events = match["event_predictions"]
        self.assertEqual(events["score"]["top_scorelines"], match["top_scorelines"])
        self.assertGreater(events["corners"]["total_expected"], 0)
        self.assertGreater(events["cards"]["total_yellow_expected"], 0)
        for key in ["over_8_5_probability", "over_9_5_probability"]:
            self.assertGreaterEqual(events["corners"][key], 0)
            self.assertLessEqual(events["corners"][key], 1)
        for key in ["over_3_5_yellow_probability", "over_4_5_yellow_probability", "any_red_probability"]:
            self.assertGreaterEqual(events["cards"][key], 0)
            self.assertLessEqual(events["cards"][key], 1)

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
        self.assertIsInstance(data_store.live_matches(), dict)
        self.assertIn("teams", data_store.historical_results_summary())


if __name__ == "__main__":
    unittest.main()
