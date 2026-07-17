"""Prefect refresh flow skeleton for production operation."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from prefect import flow, task
except ImportError:  # keeps local tests usable before optional deps are installed
    def flow(fn=None, **_kwargs):
        return fn if fn else lambda wrapped: wrapped

    def task(fn=None, **_kwargs):
        return fn if fn else lambda wrapped: wrapped

from app.adapters.football_data import fetch_world_cup_matches, normalize_matches as normalize_football_data_matches
from app.adapters.espn_live import fetch_knockout_fixtures, fetch_live_match_statuses
from app.adapters.espn_summary import fetch_match_summaries
from app.adapters.international_results import fetch_results_csv, parse_results, summarize_team_results
from app.adapters.odds_api import fetch_world_cup_odds, normalize_odds
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


def _read_json_optional(name: str, fallback):
    path = DATA_DIR / name
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(name: str, value) -> None:
    (DATA_DIR / name).write_text(json.dumps(value, indent=2, sort_keys=False) + "\n", encoding="utf-8")


@task
def refresh_fixtures():
    captured_at = datetime.now(timezone.utc).isoformat()
    fixtures = _read_json("fixtures.json")
    teams = _read_json("teams.json")
    knockout_fixtures = fetch_knockout_fixtures(teams)
    if knockout_fixtures:
        fixtures_by_id = {row["id"]: row for row in fixtures}
        fixtures_by_id.update({row["id"]: row for row in knockout_fixtures})
        fixtures = sorted(fixtures_by_id.values(), key=lambda row: row["match_number"])
        _write_json("fixtures.json", fixtures)
    raw_rows = fetch_world_cup_matches()
    rows = normalize_football_data_matches(fixtures, teams, raw_rows, captured_at)
    if rows:
        _write_json("football_data_matches.json", rows)
    return {
        "source": "football-data.org",
        "raw_rows": len(raw_rows),
        "rows": len(rows),
        "knockout_rows": len(knockout_fixtures),
        "fixture_rows": len(fixtures),
        "captured_at": captured_at,
        "written": bool(rows),
    }


@task
def refresh_odds():
    captured_at = datetime.now(timezone.utc).isoformat()
    fixtures = _read_json("fixtures.json")
    teams = _read_json("teams.json")
    raw_rows = fetch_world_cup_odds(markets="h2h,spreads,totals")
    rows = normalize_odds(raw_rows, fixtures, teams, captured_at)
    existing_rows = _read_json_optional("odds_snapshots.json", [])
    merged_rows = merge_odds_snapshots(existing_rows, rows)
    if rows:
        _write_json("odds_snapshots.json", merged_rows)
    return {
        "source": "odds_api",
        "raw_rows": len(raw_rows),
        "rows": len(rows),
        "stored_rows": len(merged_rows),
        "captured_at": captured_at,
        "written": bool(rows),
    }


@task
def refresh_live_matches():
    captured_at = datetime.now(timezone.utc).isoformat()
    fixtures = _read_json("fixtures.json")
    teams = _read_json("teams.json")
    football_data_rows = _read_json_optional("football_data_matches.json", [])
    espn_rows = fetch_live_match_statuses(fixtures, teams)
    rows = merge_live_rows(football_data_rows, espn_rows)
    _write_json("live_matches.json", rows)
    completed = sum(1 for row in rows if row["completed"])
    in_play = sum(1 for row in rows if row["status_state"] == "in")
    return {
        "source": "espn_public_scoreboard+football_data",
        "rows": len(rows),
        "espn_rows": len(espn_rows),
        "football_data_rows": len(football_data_rows),
        "completed_rows": completed,
        "in_play_rows": in_play,
        "captured_at": rows[0]["captured_at"] if rows else captured_at,
    }


@task
def refresh_espn_summaries():
    live_rows = _read_json_optional("live_matches.json", [])
    existing_rows = _read_json_optional("espn_match_summaries.json", [])
    existing_by_id = {row["match_id"]: row for row in existing_rows if row.get("match_id")}
    rows_by_id = {}
    rows_to_fetch = []
    for live_row in live_rows:
        if not (live_row.get("completed") or live_row.get("status_state") == "in"):
            continue
        existing = existing_by_id.get(live_row["match_id"])
        if existing and existing.get("status") == "available" and live_row.get("completed"):
            rows_by_id[live_row["match_id"]] = existing
        else:
            rows_to_fetch.append(live_row)
    for row in fetch_match_summaries(rows_to_fetch):
        rows_by_id[row["match_id"]] = row
    rows = sorted(rows_by_id.values(), key=lambda row: row["match_number"])
    _write_json("espn_match_summaries.json", rows)
    available = [row for row in rows if row.get("status") == "available"]
    formations = sum(
        1
        for row in available
        for team in (row.get("teams") or {}).values()
        if team.get("formation")
    )
    starters = sum(
        int(team.get("starter_count") or 0)
        for row in available
        for team in (row.get("teams") or {}).values()
    )
    captured_at = rows[0]["captured_at"] if rows else datetime.now(timezone.utc).isoformat()
    return {
        "source": "espn_public_summary",
        "rows": len(rows),
        "available_rows": len(available),
        "formations": formations,
        "starters": starters,
        "captured_at": captured_at,
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
    now = datetime.now(timezone.utc)
    captured_at = now.isoformat()
    live_by_id = {
        row["match_id"]: row
        for row in _read_json_optional("live_matches.json", [])
        if row.get("match_id")
    }
    existing_by_id = {
        row["match_id"]: row
        for row in _read_json_optional("live_weather.json", [])
        if row.get("match_id")
    }
    rows = []
    cache = {}
    for fixture in _read_json("fixtures.json"):
        kickoff_at = _parse_utc_datetime(fixture["kickoff_utc"])
        live_row = live_by_id.get(fixture["id"], {})
        existing_row = existing_by_id.get(fixture["id"])
        completed_or_old = bool(live_row.get("completed")) or kickoff_at < now - timedelta(hours=3)
        near_forecast_window = now - timedelta(hours=3) <= kickoff_at <= now + timedelta(days=4)
        if existing_row and (completed_or_old or not near_forecast_window):
            rows.append(existing_row)
            continue
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


def _parse_utc_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


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
        "espn_summaries": refresh_espn_summaries(),
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

    fixtures = report["fixtures"]
    set_row(
        "football-data.org",
        "live" if fixtures["rows"] else ("configured_empty" if fixtures["raw_rows"] == 0 else "unmatched"),
        f'{fixtures["rows"]}/{fixtures["raw_rows"]} matched World Cup rows at {fixtures["captured_at"]}',
        "fixtures, scores and post-match validation",
    )
    if "FIFA / public match schedule" in by_name:
        by_name["FIFA / public match schedule"] = {
            **by_name["FIFA / public match schedule"],
            "status": "live_public",
            "freshness": f'{fixtures["fixture_rows"]}/104 fixtures; ESPN knockout rows {fixtures["knockout_rows"]} at {fixtures["captured_at"]}',
            "purpose": "48-team groups and complete 104-match fixture path",
        }
    odds = report["odds"]
    set_row(
        "The Odds API / TheStatsAPI",
        "live_snapshot" if odds["stored_rows"] else ("configured_empty" if odds["raw_rows"] == 0 else "unmatched"),
        f'{odds["rows"]}/{odds["raw_rows"]} normalized odds rows at {odds["captured_at"]}; stored snapshots {odds["stored_rows"]}; written={odds["written"]}',
        "legal sportsbook odds and Asian handicap lines",
    )
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
        f'{live_matches["rows"]} matched events; ESPN {live_matches["espn_rows"]}; football-data {live_matches["football_data_rows"]}; {live_matches["completed_rows"]} completed; {live_matches["in_play_rows"]} in-play at {live_matches["captured_at"]}',
        "no-key live score, official score fallback and basic public match stats",
    )
    summaries = report["espn_summaries"]
    set_row(
        "ESPN public match summary",
        "live_public" if summaries["available_rows"] else "empty",
        f'{summaries["available_rows"]}/{summaries["rows"]} match summaries; {summaries["formations"]} formations; {summaries["starters"]} starters at {summaries["captured_at"]}',
        "public formations, starters, substitutions, player event stats and expanded team stats",
    )
    _write_json("source_health.json", list(by_name.values()))


def merge_live_rows(football_data_rows: list[dict], espn_rows: list[dict]) -> list[dict]:
    merged = {row["match_id"]: dict(row) for row in football_data_rows}
    for row in espn_rows:
        existing = merged.get(row["match_id"])
        if not existing:
            merged[row["match_id"]] = dict(row)
            continue
        combined = dict(existing)
        keep_completed_result = bool(existing.get("completed")) and not bool(row.get("completed"))
        for key, value in row.items():
            if keep_completed_result and key in COMPLETED_RESULT_KEYS:
                continue
            if value not in (None, {}, []):
                combined[key] = value
        combined["source"] = "ESPN public scoreboard + football-data.org"
        combined["source_quality"] = "mixed_public_official"
        merged[row["match_id"]] = combined
    return sorted(merged.values(), key=lambda row: row["match_number"])


COMPLETED_RESULT_KEYS = {
    "status_state",
    "status_name",
    "status_description",
    "status_detail",
    "completed",
    "clock",
    "display_clock",
    "period",
    "home_score",
    "away_score",
    "winner_team_id",
}


def merge_odds_snapshots(existing_rows: list[dict], new_rows: list[dict]) -> list[dict]:
    rows_by_key = {}
    for row in [*existing_rows, *new_rows]:
        key = (
            row.get("match_id"),
            row.get("bookmaker"),
            row.get("market_type"),
            row.get("line"),
            row.get("captured_at"),
            row.get("price_home"),
            row.get("price_draw"),
            row.get("price_away"),
            row.get("price_over"),
            row.get("price_under"),
        )
        rows_by_key[key] = row
    return sorted(
        rows_by_key.values(),
        key=lambda row: (
            row.get("match_id") or "",
            row.get("market_type") or "",
            row.get("line") if row.get("line") is not None else -999,
            row.get("bookmaker") or "",
            row.get("captured_at") or "",
        ),
    )


if __name__ == "__main__":
    print(refresh_all())
