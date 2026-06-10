"""Polymarket Gamma market-data adapter."""
from __future__ import annotations

import json
from typing import Any

from .http import get_json

BASE_URL = "https://gamma-api.polymarket.com"
WORLD_CUP_TERMS = ("world cup", "fifa world cup", "soccer world cup", "football world cup")


def search_world_cup_markets(limit: int = 100) -> list[dict[str, Any]]:
    events = get_json(
        f"{BASE_URL}/events",
        params={
            "active": "true",
            "closed": "false",
            "limit": limit,
            "order": "volume_24hr",
            "ascending": "false",
        },
        headers={"User-Agent": "wc26-dashboard/0.1"},
        timeout=30,
    )
    rows = events if isinstance(events, list) else events.get("data", [])
    markets: list[dict[str, Any]] = []
    for event in rows:
        if not is_world_cup_event(event):
            continue
        for market in event.get("markets") or []:
            market.setdefault("eventSlug", event.get("slug"))
            market.setdefault("eventTitle", event.get("title"))
            markets.append(market)
    return markets


def is_world_cup_event(event: dict[str, Any]) -> bool:
    haystack = " ".join(
        str(event.get(key) or "")
        for key in ("title", "question", "slug", "description", "category")
    ).lower()
    return any(term in haystack for term in WORLD_CUP_TERMS)


def normalize_markets(markets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for market in markets:
        question = str(market.get("question") or market.get("title") or "")
        slug = str(market.get("slug") or "")
        normalized.append(
            {
                "source": "Polymarket Gamma",
                "market_id": str(market.get("id") or market.get("conditionId") or ""),
                "question": question or str(market.get("eventTitle") or ""),
                "slug": slug or str(market.get("eventSlug") or ""),
                "url": _market_url(slug, market),
                "category": market.get("category"),
                "volume": _float_or_none(market.get("volume") or market.get("volumeNum")),
                "liquidity": _float_or_none(market.get("liquidity") or market.get("liquidityNum")),
                "end_date": market.get("endDate") or market.get("end_date_iso"),
                "updated_at": market.get("updatedAt") or market.get("updated_at"),
                "outcomes": _outcomes(market),
            }
        )
    return normalized


def _market_url(slug: str, market: dict[str, Any]) -> str | None:
    event_slug = market.get("eventSlug")
    if event_slug:
        return f"https://polymarket.com/event/{event_slug}"
    if slug:
        return f"https://polymarket.com/event/{slug}"
    return None


def _outcomes(market: dict[str, Any]) -> list[dict[str, Any]]:
    outcomes = _jsonish(market.get("outcomes")) or []
    prices = _jsonish(market.get("outcomePrices")) or _jsonish(market.get("outcome_prices")) or []
    rows = []
    for index, outcome in enumerate(outcomes):
        price = prices[index] if index < len(prices) else None
        rows.append({"name": str(outcome), "price": _float_or_none(price)})
    return rows


def _jsonish(value):
    if isinstance(value, (list, dict)):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _float_or_none(value) -> float | None:
    try:
        return round(float(value), 6) if value not in {None, ""} else None
    except (TypeError, ValueError):
        return None
