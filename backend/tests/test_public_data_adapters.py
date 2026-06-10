import unittest

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


if __name__ == "__main__":
    unittest.main()
