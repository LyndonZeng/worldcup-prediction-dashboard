"""Polymarket Gamma market-data adapter."""
from __future__ import annotations

from typing import Any

import requests

BASE_URL = "https://gamma-api.polymarket.com"


def search_world_cup_markets(limit: int = 100) -> list[dict[str, Any]]:
    response = requests.get(
        f"{BASE_URL}/markets",
        params={"closed": "false", "limit": limit, "search": "2026 FIFA World Cup"},
        headers={"User-Agent": "wc26-dashboard/0.1"},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, list) else data.get("data", [])

