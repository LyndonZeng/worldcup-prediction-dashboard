"""Prefect refresh flow skeleton for production operation."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

try:
    from prefect import flow, task
except ImportError:  # keeps local tests usable before optional deps are installed
    def flow(fn=None, **_kwargs):
        return fn if fn else lambda wrapped: wrapped

    def task(fn=None, **_kwargs):
        return fn if fn else lambda wrapped: wrapped

from app.adapters.football_data import fetch_world_cup_matches
from app.adapters.espn_live import fetch_live_match_statuses
from app.adapters.international_results import fetch_results_csv, parse_results, summarize_team_results
from app.adapters.odds_api import fetch_world_cup_odds
from app.adapters.open_meteo import (
    climate_fallback_for_city,
    coordinates_for_city,
    fetch_daily_weather,
    normalize_daily_weather,
)
from app.adapters.polymarket import normalize_markets, search_world_cup_markets

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _read_json(name: str):
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def _write_json(name: str, value) -> None:
    (DATA_DIR / name).write_text(json.dumps(value, indent=2, sort_keys=False) + "\n", encoding="utf-8")


@task
def refresh_fixtures():
    return {"source": "football-data.org", "rows": len(fetch_world_cup_matches())}


@task
def refresh_odds():
    return {"source": "odds_api", "rows": len(fetch_world_cup_odds(markets="h2h,spreads,totals"))}


@task
def refresh_live_matches():
    captured_at = datetime.now(timezone.utc).isoformat()
    fixtures = _read_json("fixtures.json")
    teams = _read_json("teams.json")
    rows = fetch_live_match_statuses(fixtures, teams)
    _write_json("live_matches.json", rows)
    completed = sum(1 for row in rows if row["completed"])
    in_play = sum(1 for row in rows if row["status_state"] == "in")
    return {
        "source": "espn_public_scoreboard",
        "rows": len(rows),
        "completed_rows": completed,
        "in_play_rows": in_play,
        "captured_at": rows[0]["captured_at"] if rows else captured_at,
    }


@task
def refresh_prediction_markets():
    captured_at = datetime.now(timezone.utc).isoformat()
    rows = normalize_markets(search_world_cup_markets())
    for row in rows:
        row["captured_at"] = captured_at
    _write_json("prediction_markets.json", rows)
    return {"source": "polymarket", "rows": len(rows), "captured_at": captured_at}


@task
def refresh_weather():
    captured_at = datetime.now(timezone.utc).isoformat()
    rows = []
    cache = {}
    for fixture in _read_json("fixtures.json"):
        date = fixture["kickoff_utc"][:10]
        city = fixture["city"]
        key = (city, date)
        normalized = None
        status = "fallback"
        source = "Open-Meteo climate fallback"
        if key not in cache:
            coordinates = coordinates_for_city(city)
            if coordinates:
                try:
                    daily = fetch_daily_weather(coordinates[0], coordinates[1], date)
                    normalized = normalize_daily_weather(daily, date)
                    if normalized:
                        status = "forecast"
                        source = "Open-Meteo Forecast API"
                except Exception:
                    normalized = None
            cache[key] = (normalized, status, source)
        normalized, status, source = cache[key]
        if normalized is None:
            normalized = climate_fallback_for_city(city)
        rows.append(
            {
                "match_id": fixture["id"],
                "match_number": fixture["match_number"],
                "city": city,
                "venue": fixture["venue"],
                "forecast_date": date,
                "source": source,
                "status": status,
                "captured_at": captured_at,
                **normalized,
            }
        )
    _write_json("live_weather.json", rows)
    live_rows = sum(1 for row in rows if row["status"] == "forecast")
    return {"source": "open_meteo", "rows": len(rows), "forecast_rows": live_rows, "captured_at": captured_at}


@task
def refresh_historical_results():
    captured_at = datetime.now(timezone.utc).isoformat()
    teams = _read_json("teams.json")
    results = parse_results(fetch_results_csv())
    summary = {
        "source": "martj42/international_results",
        "captured_at": captured_at,
        "result_rows": len(results),
        "teams": summarize_team_results(teams, results),
    }
    _write_json("historical_results_summary.json", summary)
    covered = sum(1 for row in summary["teams"].values() if row["matches"])
    return {"source": "martj42", "rows": len(results), "teams_covered": covered, "captured_at": captured_at}

@flow(name="wc26-refresh")
def refresh_all():
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fixtures": refresh_fixtures(),
        "odds": refresh_odds(),
        "live_matches": refresh_live_matches(),
        "weather": refresh_weather(),
        "prediction_markets": refresh_prediction_markets(),
        "historical_results": refresh_historical_results(),
    }
    update_source_health(report)
    return report


def update_source_health(report: dict) -> None:
    sources = _read_json("source_health.json")
    by_name = {row["source"]: dict(row) for row in sources}

    def set_row(name: str, status: str, freshness: str, purpose: str) -> None:
        by_name[name] = {
            "source": name,
            "status": status,
            "freshness": freshness,
            "purpose": purpose,
        }

    weather = report["weather"]
    set_row(
        "Open-Meteo",
        "live" if weather["forecast_rows"] else "fallback",
        f'{weather["forecast_rows"]}/{weather["rows"]} forecast rows at {weather["captured_at"]}',
        "weather, wind and heat context",
    )
    markets = report["prediction_markets"]
    set_row(
        "Polymarket Gamma",
        "live" if markets["rows"] else "empty",
        f'{markets["rows"]} markets at {markets["captured_at"]}',
        "prediction market prices",
    )
    history = report["historical_results"]
    set_row(
        "martj42 international_results",
        "live" if history["rows"] else "empty",
        f'{history["rows"]} historical rows; {history["teams_covered"]} teams covered at {history["captured_at"]}',
        "historical international results for form calibration",
    )
    live_matches = report["live_matches"]
    set_row(
        "ESPN public scoreboard",
        "live_public" if live_matches["rows"] else "empty",
        f'{live_matches["rows"]} matched events; {live_matches["completed_rows"]} completed; {live_matches["in_play_rows"]} in-play at {live_matches["captured_at"]}',
        "no-key live score, status and basic public match stats",
    )
    _write_json("source_health.json", list(by_name.values()))


if __name__ == "__main__":
    print(refresh_all())
