"""football-data.org adapter.

This module is intentionally small and side-effect free. It can be used by the
refresh flow once FOOTBALL_DATA_API_KEY is configured.
"""
from __future__ import annotations

import os
from typing import Any

from .http import get_json

BASE_URL = "https://api.football-data.org/v4"


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
