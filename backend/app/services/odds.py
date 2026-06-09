"""Odds normalization, de-vigging, and market edge helpers."""
from __future__ import annotations

from statistics import mean


def devig_two_way(price_a: float, price_b: float) -> tuple[float, float]:
    if price_a <= 1 or price_b <= 1:
        raise ValueError("Decimal odds must be greater than 1")
    inverse_a = 1.0 / price_a
    inverse_b = 1.0 / price_b
    total = inverse_a + inverse_b
    return inverse_a / total, inverse_b / total


def devig_three_way(price_home: float, price_draw: float, price_away: float) -> tuple[float, float, float]:
    prices = (price_home, price_draw, price_away)
    if any(price <= 1 for price in prices):
        raise ValueError("Decimal odds must be greater than 1")
    inverse = [1.0 / price for price in prices]
    total = sum(inverse)
    return tuple(value / total for value in inverse)


def consensus_two_way(markets: list[dict]) -> dict | None:
    valid = [
        devig_two_way(market["price_home"], market["price_away"])
        for market in markets
        if market.get("price_home") and market.get("price_away")
    ]
    if not valid:
        return None
    return {
        "home": round(mean(pair[0] for pair in valid), 6),
        "away": round(mean(pair[1] for pair in valid), 6),
        "n_books": len(valid),
    }


def model_lean(home_expected_return: float | None, away_expected_return: float | None, threshold: float = 0.035) -> str:
    if home_expected_return is not None and home_expected_return >= threshold:
        return "home"
    if away_expected_return is not None and away_expected_return >= threshold:
        return "away"
    return "none"

