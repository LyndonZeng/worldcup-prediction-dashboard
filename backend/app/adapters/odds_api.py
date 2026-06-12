"""Legal sportsbook odds adapter placeholder for The Odds API-compatible feeds."""
from __future__ import annotations

import os
import unicodedata
from datetime import datetime, timezone
from typing import Any

from .http import HttpStatusError, get_json

BASE_URL = "https://api.the-odds-api.com/v4"
SPORT_KEYS = ("soccer_fifa_world_cup", "soccer_fifa_world_cup_2026")
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


def fetch_world_cup_odds(markets: str = "h2h,spreads,totals") -> list[dict[str, Any]]:
    api_key = os.environ.get("ODDS_API_KEY")
    if not api_key:
        return []
    events: list[dict[str, Any]] = []
    for sport_key in _candidate_sport_keys(api_key):
        events.extend(_fetch_sport_odds(api_key, sport_key, markets))
    return events


def _fetch_sport_odds(api_key: str, sport_key: str, markets: str) -> list[dict[str, Any]]:
    try:
        return _fetch_sport_market(api_key, sport_key, markets)
    except HttpStatusError as exc:
        if exc.status_code == 404:
            return []
        if exc.status_code != 422 or "," not in markets:
            raise
    events = []
    for market in markets.split(","):
        try:
            events.extend(_fetch_sport_market(api_key, sport_key, market))
        except HttpStatusError as exc:
            if exc.status_code in {404, 422}:
                continue
            raise
    return events


def _fetch_sport_market(api_key: str, sport_key: str, markets: str) -> list[dict[str, Any]]:
    return get_json(
        f"{BASE_URL}/sports/{sport_key}/odds",
        params={
            "apiKey": api_key,
            "regions": "eu,uk,us",
            "markets": markets,
            "oddsFormat": "decimal",
        },
        headers={"User-Agent": "wc26-dashboard/0.1"},
        timeout=30,
    )


def _candidate_sport_keys(api_key: str) -> list[str]:
    keys = list(SPORT_KEYS)
    try:
        sports = get_json(
            f"{BASE_URL}/sports",
            params={"apiKey": api_key, "all": "true"},
            headers={"User-Agent": "wc26-dashboard/0.1"},
            timeout=30,
        )
    except HttpStatusError:
        sports = []
    for sport in sports if isinstance(sports, list) else []:
        haystack = " ".join(str(sport.get(key) or "") for key in ["key", "group", "title", "description"]).lower()
        if "soccer" in haystack and "world cup" in haystack and sport.get("key"):
            keys.append(str(sport["key"]))
    return list(dict.fromkeys(keys))


def normalize_odds(events: list[dict], fixtures: list[dict], teams: list[dict], captured_at: str) -> list[dict]:
    aliases = _team_aliases(teams)
    rows = []
    for event in events:
        home_id = _team_id(event.get("home_team"), aliases)
        away_id = _team_id(event.get("away_team"), aliases)
        if not home_id or not away_id:
            continue
        fixture = _match_fixture(fixtures, home_id, away_id, event.get("commence_time"))
        if not fixture:
            continue
        for bookmaker in event.get("bookmakers") or []:
            for market in bookmaker.get("markets") or []:
                rows.extend(_normalize_market(fixture, event, bookmaker, market, captured_at))
    return sorted(rows, key=lambda row: (row["match_id"], row["market_type"], row.get("line") or 0, row["bookmaker"]))


def _normalize_market(fixture: dict, event: dict, bookmaker: dict, market: dict, captured_at: str) -> list[dict]:
    market_key = market.get("key")
    outcomes = market.get("outcomes") or []
    bookmaker_name = bookmaker.get("title") or bookmaker.get("key") or "unknown"
    market_captured_at = market.get("last_update") or bookmaker.get("last_update") or captured_at
    common = {
        "match_id": fixture["id"],
        "bookmaker": bookmaker_name,
        "captured_at": market_captured_at,
        "source": "The Odds API",
        "odds_event_id": event.get("id"),
    }
    if market_key == "h2h":
        home = _outcome_by_team(outcomes, event.get("home_team"))
        away = _outcome_by_team(outcomes, event.get("away_team"))
        draw = _outcome_by_name(outcomes, "Draw")
        if not home or not away:
            return []
        row = {
            **common,
            "market_type": "1x2",
            "line": None,
            "price_home": _price(home),
            "price_draw": _price(draw),
            "price_away": _price(away),
        }
        return [row] if row["price_home"] and row["price_away"] else []
    if market_key == "spreads":
        home = _outcome_by_team(outcomes, event.get("home_team"))
        away = _outcome_by_team(outcomes, event.get("away_team"))
        if not home or not away or home.get("point") is None:
            return []
        row = {
            **common,
            "market_type": "asian_handicap",
            "line": float(home["point"]),
            "price_home": _price(home),
            "price_away": _price(away),
        }
        return [row] if row["price_home"] and row["price_away"] else []
    if market_key == "totals":
        over = _outcome_by_name(outcomes, "Over")
        under = _outcome_by_name(outcomes, "Under")
        if not over or not under or over.get("point") is None:
            return []
        row = {
            **common,
            "market_type": "over_under",
            "line": float(over["point"]),
            "price_over": _price(over),
            "price_under": _price(under),
        }
        return [row] if row["price_over"] and row["price_under"] else []
    return []


def _team_aliases(teams: list[dict]) -> dict[str, str]:
    aliases = {}
    for team in teams:
        aliases[_key(team["name"])] = team["id"]
        aliases[_key(team["fifa_code"])] = team["id"]
    for name, team_id in TEAM_ALIASES.items():
        aliases[_key(name)] = team_id
    return aliases


def _team_id(value: str | None, aliases: dict[str, str]) -> str | None:
    return aliases.get(_key(value or ""))


def _match_fixture(fixtures: list[dict], home_id: str, away_id: str, commence_time: str | None) -> dict | None:
    candidates = [
        fixture
        for fixture in fixtures
        if fixture["home_team_id"] == home_id and fixture["away_team_id"] == away_id
    ]
    if not candidates:
        return None
    if len(candidates) == 1 or not commence_time:
        return candidates[0]
    event_at = _parse_utc(commence_time)
    return min(
        candidates,
        key=lambda fixture: abs((_parse_utc(fixture["kickoff_utc"]) - event_at).total_seconds()),
    )


def _outcome_by_team(outcomes: list[dict], team_name: str | None) -> dict | None:
    key = _key(team_name or "")
    for outcome in outcomes:
        if _key(outcome.get("name") or "") == key:
            return outcome
    return None


def _outcome_by_name(outcomes: list[dict], name: str) -> dict | None:
    key = _key(name)
    for outcome in outcomes:
        if _key(outcome.get("name") or "") == key:
            return outcome
    return None


def _price(outcome: dict | None) -> float | None:
    if not outcome:
        return None
    try:
        price = float(outcome["price"])
    except (KeyError, TypeError, ValueError):
        return None
    return price if price > 1 else None


def _key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(
        "".join(char.lower() if char.isalnum() else " " for char in normalized).split()
    )


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
