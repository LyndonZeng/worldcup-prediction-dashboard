"""football-data.org adapter.

This module is intentionally small and side-effect free. It can be used by the
refresh flow once FOOTBALL_DATA_API_KEY is configured.
"""
from __future__ import annotations

import os
import unicodedata
from datetime import datetime, timezone
from typing import Any

from .http import get_json

BASE_URL = "https://api.football-data.org/v4"
TEAM_ALIASES = {
    "bosnia herzegovina": "bih",
    "bosnia and herzegovina": "bih",
    "czech republic": "cze",
    "czechia": "cze",
    "cote d ivoire": "civ",
    "ivory coast": "civ",
    "curacao": "cur",
    "curaçao": "cur",
    "turkiye": "tur",
    "turkey": "tur",
    "usa": "usa",
    "united states": "usa",
    "cape verde": "cpv",
    "cabo verde": "cpv",
    "congo dr": "cod",
    "dr congo": "cod",
    "democratic republic of congo": "cod",
}


def fetch_world_cup_matches() -> list[dict[str, Any]]:
    api_key = os.environ.get("FOOTBALL_DATA_API_KEY")
    if not api_key:
        return []
    data = get_json(
        f"{BASE_URL}/competitions/WC/matches",
        headers={"X-Auth-Token": api_key, "User-Agent": "wc26-dashboard/0.1"},
        timeout=30,
    )
    return data.get("matches", [])


def normalize_matches(fixtures: list[dict], teams: list[dict], matches: list[dict], captured_at: str) -> list[dict]:
    aliases = _team_aliases(teams)
    rows = []
    seen: set[str] = set()
    for match in matches:
        row = _normalize_match(fixtures, aliases, match, captured_at)
        if not row or row["match_id"] in seen:
            continue
        seen.add(row["match_id"])
        rows.append(row)
    return sorted(rows, key=lambda row: row["match_number"])


def _normalize_match(fixtures: list[dict], aliases: dict[str, str], match: dict, captured_at: str) -> dict | None:
    home_id = _team_id(match.get("homeTeam") or {}, aliases)
    away_id = _team_id(match.get("awayTeam") or {}, aliases)
    if not home_id or not away_id:
        return None
    fixture = _match_fixture(fixtures, home_id, away_id, match.get("utcDate"))
    if not fixture:
        return None
    status = match.get("status")
    completed = status == "FINISHED"
    score_is_meaningful = completed or status in {"IN_PLAY", "PAUSED"}
    full_time = ((match.get("score") or {}).get("fullTime") or {})
    return {
        "match_id": fixture["id"],
        "match_number": fixture["match_number"],
        "football_data_match_id": match.get("id"),
        "source": "football-data.org",
        "source_quality": "official_api_score_status",
        "captured_at": captured_at,
        "status_state": _status_state(status),
        "status_name": status,
        "status_description": _status_description(status),
        "status_detail": match.get("stage") or status,
        "completed": completed,
        "clock": None,
        "display_clock": None,
        "period": None,
        "home_team_id": home_id,
        "away_team_id": away_id,
        "home_score": _score(full_time.get("home")) if score_is_meaningful else None,
        "away_score": _score(full_time.get("away")) if score_is_meaningful else None,
        "winner_team_id": _winner_team_id(home_id, away_id, (match.get("score") or {}).get("winner")),
        "attendance": None,
        "neutral_site": None,
        "home_stats": {},
        "away_stats": {},
    }


def _team_aliases(teams: list[dict]) -> dict[str, str]:
    aliases = {}
    for team in teams:
        aliases[_key(team["name"])] = team["id"]
        aliases[_key(team["fifa_code"])] = team["id"]
    for name, team_id in TEAM_ALIASES.items():
        aliases[_key(name)] = team_id
    return aliases


def _team_id(team: dict, aliases: dict[str, str]) -> str | None:
    for value in [team.get("name"), team.get("shortName"), team.get("tla")]:
        team_id = aliases.get(_key(str(value or "")))
        if team_id:
            return team_id
    return None


def _match_fixture(fixtures: list[dict], home_id: str, away_id: str, utc_date: str | None) -> dict | None:
    candidates = [
        fixture
        for fixture in fixtures
        if fixture["home_team_id"] == home_id and fixture["away_team_id"] == away_id
    ]
    if not candidates:
        return None
    if len(candidates) == 1 or not utc_date:
        return candidates[0]
    event_at = _parse_utc(utc_date)
    return min(
        candidates,
        key=lambda fixture: abs((_parse_utc(fixture["kickoff_utc"]) - event_at).total_seconds()),
    )


def _winner_team_id(home_id: str, away_id: str, winner: str | None) -> str | None:
    if winner == "HOME_TEAM":
        return home_id
    if winner == "AWAY_TEAM":
        return away_id
    return None


def _status_state(status: str | None) -> str:
    if status == "FINISHED":
        return "post"
    if status in {"IN_PLAY", "PAUSED"}:
        return "in"
    return "pre"


def _status_description(status: str | None) -> str:
    return {
        "FINISHED": "Full Time",
        "IN_PLAY": "In Play",
        "PAUSED": "Half Time",
        "TIMED": "Scheduled",
        "SCHEDULED": "Scheduled",
    }.get(status or "", status or "Scheduled")


def _score(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(
        "".join(char.lower() if char.isalnum() else " " for char in normalized).split()
    )


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
