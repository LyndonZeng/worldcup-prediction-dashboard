"""Legal sportsbook odds adapter placeholder for The Odds API-compatible feeds."""
from __future__ import annotations

import os
from typing import Any

import requests

BASE_URL = "https://api.the-odds-api.com/v4"
SPORT_KEYS = ("soccer_fifa_world_cup", "soccer_fifa_world_cup_2026")


def fetch_world_cup_odds(markets: str = "h2h,spreads,totals") -> list[dict[str, Any]]:
    api_key = os.environ.get("ODDS_API_KEY")
    if not api_key:
        return []
    events: list[dict[str, Any]] = []
    for sport_key in SPORT_KEYS:
        response = requests.get(
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
        if response.status_code == 404:
            continue
        response.raise_for_status()
        events.extend(response.json())
    return events

