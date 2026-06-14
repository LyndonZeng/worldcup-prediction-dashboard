"""Read seed data and produce normalized domain objects."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .score_model import MatchContext, TeamProfile

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _read_json(name: str):
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def _read_json_optional(name: str, fallback):
    path = DATA_DIR / name
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def teams() -> dict[str, TeamProfile]:
    history = historical_results_summary().get("teams", {})
    return {
        row["id"]: TeamProfile(
            id=row["id"],
            name=row["name"],
            group=row["group"],
            fifa_code=row["fifa_code"],
            flag_code=row["flag_code"],
            elo=float(row["elo"]),
            attack=float(row["attack"]),
            defence=float(row["defence"]),
            form_index=float(history.get(row["id"], {}).get("form_index", row.get("form_index", 0.0))),
            injury_impact=float(row.get("injury_impact", 0.0)),
        )
        for row in _read_json("teams.json")
    }


@lru_cache(maxsize=1)
def fixtures() -> list[dict]:
    return _read_json("fixtures.json")


@lru_cache(maxsize=1)
def odds_snapshots() -> list[dict]:
    return _read_json("odds_snapshots.json")


@lru_cache(maxsize=1)
def source_health() -> list[dict]:
    return _read_json("source_health.json")


@lru_cache(maxsize=1)
def live_weather() -> dict[str, dict]:
    rows = _read_json_optional("live_weather.json", [])
    return {row["match_id"]: row for row in rows}


@lru_cache(maxsize=1)
def live_matches() -> dict[str, dict]:
    rows = _read_json_optional("live_matches.json", [])
    return {row["match_id"]: row for row in rows}


@lru_cache(maxsize=1)
def prediction_markets() -> list[dict]:
    return _read_json_optional("prediction_markets.json", [])


@lru_cache(maxsize=1)
def model_prediction_snapshots() -> list[dict]:
    return _read_json_optional("model_prediction_snapshots.json", [])


@lru_cache(maxsize=1)
def closing_line_snapshots() -> list[dict]:
    return _read_json_optional("closing_line_snapshots.json", [])


@lru_cache(maxsize=1)
def backtest_report() -> dict:
    return _read_json_optional(
        "backtest_report.json",
        {
            "status": "missing",
            "snapshot_counts": {},
            "formal": {},
            "shadow": {},
        },
    )


@lru_cache(maxsize=1)
def historical_results_summary() -> dict:
    return _read_json_optional("historical_results_summary.json", {"teams": {}})


def fixture_by_id(match_id: str) -> dict:
    for fixture in fixtures():
        if fixture["id"] == match_id:
            return fixture
    raise KeyError(match_id)


def team_by_id(team_id: str) -> TeamProfile:
    return teams()[team_id]


def context_for_fixture(fixture: dict) -> MatchContext:
    context = fixture.get("context", {})
    return MatchContext(
        home_mult=float(context.get("home_mult", 1.0)),
        away_mult=float(context.get("away_mult", 1.0)),
        notes=tuple(context.get("notes", [])),
    )


def odds_for_match(match_id: str, market_type: str | None = None) -> list[dict]:
    rows = [row for row in odds_snapshots() if row["match_id"] == match_id]
    if market_type:
        rows = [row for row in rows if row["market_type"] == market_type]
    return rows


def weather_for_fixture(match_id: str) -> dict | None:
    return live_weather().get(match_id)


def live_match_for_fixture(match_id: str) -> dict | None:
    return live_matches().get(match_id)


def team_history(team_id: str) -> dict | None:
    return historical_results_summary().get("teams", {}).get(team_id)
