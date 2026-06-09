"""Prefect refresh flow skeleton for production operation."""
from __future__ import annotations

from datetime import datetime, timezone

try:
    from prefect import flow, task
except ImportError:  # keeps local tests usable before optional deps are installed
    def flow(fn=None, **_kwargs):
        return fn if fn else lambda wrapped: wrapped

    def task(fn=None, **_kwargs):
        return fn if fn else lambda wrapped: wrapped

from app.adapters.football_data import fetch_world_cup_matches
from app.adapters.odds_api import fetch_world_cup_odds
from app.adapters.polymarket import search_world_cup_markets


@task
def refresh_fixtures():
    return {"source": "football-data.org", "rows": len(fetch_world_cup_matches())}


@task
def refresh_odds():
    return {"source": "odds_api", "rows": len(fetch_world_cup_odds(markets="h2h,spreads,totals"))}


@task
def refresh_prediction_markets():
    return {"source": "polymarket", "rows": len(search_world_cup_markets())}


@flow(name="wc26-refresh")
def refresh_all():
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fixtures": refresh_fixtures(),
        "odds": refresh_odds(),
        "prediction_markets": refresh_prediction_markets(),
    }


if __name__ == "__main__":
    print(refresh_all())

