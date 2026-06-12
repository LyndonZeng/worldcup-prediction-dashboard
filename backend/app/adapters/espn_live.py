"""No-key ESPN public scoreboard adapter for live World Cup status.

This uses ESPN's public site JSON, not a contracted data feed. Treat it as a
best-effort live/public source: good for score, status and basic match stats,
but not a substitute for licensed event data.
"""
from __future__ import annotations

import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from .http import get_json

BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
ET = ZoneInfo("America/New_York")

TEAM_ALIASES = {
    "bosnia herzegovina": "bih",
    "bosnia and herzegovina": "bih",
    "bosnia-herzegovina": "bih",
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

STAT_MAP = {
    "possessionPct": "possession_pct",
    "totalShots": "shots",
    "shotsOnTarget": "shots_on_target",
    "wonCorners": "corners",
    "foulsCommitted": "fouls_committed",
    "goalAssists": "assists",
    "totalGoals": "goals",
}


def date_keys_for_fixtures(fixtures: list[dict]) -> list[str]:
    keys: set[str] = set()
    for fixture in fixtures:
        kickoff = _parse_utc(fixture["kickoff_utc"]).astimezone(ET)
        # ESPN groups late ET matches under the local match date; include a
        # small cushion so cross-midnight UTC fixtures are still found.
        for offset in (-1, 0, 1):
            keys.add((kickoff + timedelta(days=offset)).strftime("%Y%m%d"))
    return sorted(keys)


def fetch_scoreboard(date_key: str) -> dict[str, Any]:
    return get_json(
        BASE_URL,
        params={"dates": date_key},
        headers={"User-Agent": "wc26-dashboard/0.1"},
        timeout=30,
    )


def fetch_live_match_statuses(fixtures: list[dict], teams: list[dict]) -> list[dict]:
    captured_at = datetime.now(timezone.utc).isoformat()
    events = []
    for date_key in date_keys_for_fixtures(fixtures):
        payload = fetch_scoreboard(date_key)
        events.extend(payload.get("events", []))
    return normalize_events(fixtures, teams, events, captured_at)


def normalize_events(fixtures: list[dict], teams: list[dict], events: list[dict], captured_at: str) -> list[dict]:
    aliases = _team_aliases(teams)
    rows = []
    seen: set[str] = set()
    for event in events:
        row = _normalize_event(event, fixtures, aliases, captured_at)
        if not row or row["match_id"] in seen:
            continue
        seen.add(row["match_id"])
        rows.append(row)
    return sorted(rows, key=lambda row: row["match_number"])


def _normalize_event(event: dict, fixtures: list[dict], aliases: dict[str, str], captured_at: str) -> dict | None:
    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors") or []
    if len(competitors) < 2:
        return None
    by_side = {row.get("homeAway"): row for row in competitors}
    if "home" not in by_side or "away" not in by_side:
        return None
    home_id = _team_id_for_competitor(by_side["home"], aliases)
    away_id = _team_id_for_competitor(by_side["away"], aliases)
    if not home_id or not away_id:
        return None
    fixture = _match_fixture(fixtures, home_id, away_id, event.get("date") or competition.get("date"))
    if not fixture:
        return None
    status = event.get("status") or competition.get("status") or {}
    status_type = status.get("type") or {}
    status_state = status_type.get("state")
    completed = bool(status_type.get("completed"))
    score_is_meaningful = completed or status_state == "in"
    home_score = _score(by_side["home"].get("score")) if score_is_meaningful else None
    away_score = _score(by_side["away"].get("score")) if score_is_meaningful else None
    include_stats = completed or status_state == "in"
    return {
        "match_id": fixture["id"],
        "match_number": fixture["match_number"],
        "espn_event_id": event.get("id"),
        "source": "ESPN public scoreboard",
        "source_quality": "live_public_unofficial",
        "captured_at": captured_at,
        "status_state": status_state,
        "status_name": status_type.get("name"),
        "status_description": status_type.get("description"),
        "status_detail": status_type.get("detail") or status_type.get("shortDetail"),
        "completed": completed,
        "clock": status.get("clock"),
        "display_clock": status.get("displayClock"),
        "period": status.get("period"),
        "home_team_id": home_id,
        "away_team_id": away_id,
        "home_score": home_score,
        "away_score": away_score,
        "winner_team_id": _winner_team_id(home_id, away_id, by_side),
        "attendance": competition.get("attendance") if include_stats else None,
        "neutral_site": competition.get("neutralSite"),
        "home_stats": _stats(by_side["home"]) if include_stats else {},
        "away_stats": _stats(by_side["away"]) if include_stats else {},
    }


def _team_aliases(teams: list[dict]) -> dict[str, str]:
    aliases = {}
    for team in teams:
        aliases[_key(team["name"])] = team["id"]
        aliases[_key(team["fifa_code"])] = team["id"]
    for name, team_id in TEAM_ALIASES.items():
        aliases[_key(name)] = team_id
    return aliases


def _team_id_for_competitor(competitor: dict, aliases: dict[str, str]) -> str | None:
    team = competitor.get("team") or {}
    candidates = [
        team.get("displayName"),
        team.get("shortDisplayName"),
        team.get("name"),
        team.get("location"),
        team.get("abbreviation"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        team_id = aliases.get(_key(str(candidate)))
        if team_id:
            return team_id
    return None


def _match_fixture(fixtures: list[dict], home_id: str, away_id: str, event_date: str | None) -> dict | None:
    candidates = [
        fixture
        for fixture in fixtures
        if fixture["home_team_id"] == home_id and fixture["away_team_id"] == away_id
    ]
    if not candidates:
        return None
    if len(candidates) == 1 or not event_date:
        return candidates[0]
    event_at = _parse_utc(event_date)
    return min(
        candidates,
        key=lambda fixture: abs((_parse_utc(fixture["kickoff_utc"]) - event_at).total_seconds()),
    )


def _stats(competitor: dict) -> dict:
    out = {}
    for stat in competitor.get("statistics") or []:
        key = STAT_MAP.get(stat.get("name"))
        if not key:
            continue
        out[key] = _number(stat.get("displayValue"))
    return out


def _winner_team_id(home_id: str, away_id: str, by_side: dict[str, dict]) -> str | None:
    if by_side["home"].get("winner"):
        return home_id
    if by_side["away"].get("winner"):
        return away_id
    return None


def _score(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _number(value) -> float | int | None:
    if value is None:
        return None
    try:
        number = float(str(value).replace("%", ""))
    except ValueError:
        return None
    return int(number) if number.is_integer() else number


def _key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(
        "".join(char.lower() if char.isalnum() else " " for char in normalized).split()
    )


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
