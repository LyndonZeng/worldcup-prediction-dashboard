import unittest

from app.adapters.espn_live import normalize_events
from app.adapters.international_results import parse_results, summarize_team_results
from app.adapters.open_meteo import normalize_daily_weather
from app.adapters.polymarket import is_world_cup_event, normalize_markets


class PublicDataAdaptersTest(unittest.TestCase):
    def test_international_results_summary_handles_team_aliases(self):
        teams = [
            {"id": "usa", "name": "United States", "fifa_code": "USA"},
            {"id": "civ", "name": "Cote d'Ivoire", "fifa_code": "CIV"},
        ]
        rows = parse_results(
            "date,home_team,away_team,home_score,away_score,tournament,city,country,neutral\n"
            "2026-01-01,USA,Ivory Coast,2,1,Friendly,Austin,United States,FALSE\n"
            "2025-12-01,Côte d'Ivoire,USA,0,0,Friendly,Paris,France,TRUE\n"
        )
        summary = summarize_team_results(teams, rows)
        self.assertEqual(summary["usa"]["matches"], 2)
        self.assertEqual(summary["usa"]["last_10"], "1W-1D-0L")
        self.assertEqual(summary["civ"]["matches"], 2)

    def test_open_meteo_daily_weather_normalization(self):
        daily = {
            "time": ["2026-06-11"],
            "temperature_2m_max": [26.2],
            "temperature_2m_min": [18.4],
            "temperature_2m_mean": [22.1],
            "relative_humidity_2m_mean": [61],
            "precipitation_sum": [0.0],
            "weather_code": [1],
            "wind_speed_10m_max": [12.6],
        }
        normalized = normalize_daily_weather(daily, "2026-06-11")
        self.assertEqual(normalized["temperature_c"], 22.1)
        self.assertEqual(normalized["humidity_pct"], 61.0)
        self.assertEqual(normalized["condition"], "clear")

    def test_polymarket_normalization_parses_stringified_outcomes(self):
        rows = normalize_markets(
            [
                {
                    "id": "123",
                    "question": "Who will win the 2026 FIFA World Cup?",
                    "slug": "2026-world-cup-winner",
                    "outcomes": '["Yes","No"]',
                    "outcomePrices": '["0.31","0.69"]',
                    "volume": "1000.5",
                }
            ]
        )
        self.assertEqual(rows[0]["market_id"], "123")
        self.assertEqual(rows[0]["outcomes"][0]["price"], 0.31)
        self.assertEqual(rows[0]["volume"], 1000.5)

    def test_polymarket_world_cup_filter_rejects_unrelated_events(self):
        self.assertTrue(is_world_cup_event({"title": "2026 FIFA World Cup winner"}))
        self.assertFalse(is_world_cup_event({"title": "New Rihanna Album before GTA VI?"}))

    def test_espn_live_normalization_matches_aliases_and_stats(self):
        fixtures = [
            {
                "id": "wc26-003",
                "match_number": 3,
                "kickoff_utc": "2026-06-12T19:00:00Z",
                "home_team_id": "can",
                "away_team_id": "bih",
            }
        ]
        teams = [
            {"id": "can", "name": "Canada", "fifa_code": "CAN"},
            {"id": "bih", "name": "Bosnia and Herzegovina", "fifa_code": "BIH"},
        ]
        events = [
            {
                "id": "760416",
                "date": "2026-06-12T19:00Z",
                "status": {
                    "clock": 5400.0,
                    "displayClock": "90'",
                    "period": 2,
                    "type": {"state": "post", "completed": True, "description": "Full Time", "detail": "FT"},
                },
                "competitions": [
                    {
                        "competitors": [
                            {
                                "homeAway": "home",
                                "score": "1",
                                "winner": True,
                                "team": {"displayName": "Canada", "abbreviation": "CAN"},
                                "statistics": [{"name": "totalShots", "displayValue": "14"}],
                            },
                            {
                                "homeAway": "away",
                                "score": "0",
                                "team": {"displayName": "Bosnia-Herzegovina", "abbreviation": "BIH"},
                                "statistics": [{"name": "possessionPct", "displayValue": "47.2"}],
                            },
                        ]
                    }
                ],
            }
        ]
        rows = normalize_events(fixtures, teams, events, "2026-06-13T00:00:00+00:00")
        self.assertEqual(rows[0]["match_id"], "wc26-003")
        self.assertTrue(rows[0]["completed"])
        self.assertEqual(rows[0]["home_score"], 1)
        self.assertEqual(rows[0]["away_team_id"], "bih")
        self.assertEqual(rows[0]["home_stats"]["shots"], 14)
        self.assertEqual(rows[0]["away_stats"]["possession_pct"], 47.2)


if __name__ == "__main__":
    unittest.main()
