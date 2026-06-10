"""martj42 international results adapter.

The raw CSV is public and does not require an API key. We summarize it into a
compact per-team recent-form snapshot so the model can move beyond static seed
form values when the refresh job has network access.
"""
from __future__ import annotations

import csv
import io
from collections import defaultdict
from typing import Any

from .http import get_text

RESULTS_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"

TEAM_ALIASES = {
    "Cote d'Ivoire": {"Cote d'Ivoire", "Ivory Coast", "Côte d'Ivoire"},
    "Curacao": {"Curacao", "Curaçao"},
    "Cabo Verde": {"Cabo Verde", "Cape Verde"},
    "DR Congo": {"DR Congo", "Democratic Republic of Congo", "Congo DR", "Zaire"},
    "United States": {"United States", "USA"},
    "South Korea": {"South Korea", "Korea Republic"},
    "Saudi Arabia": {"Saudi Arabia"},
    "Bosnia and Herzegovina": {"Bosnia and Herzegovina", "Bosnia-Herzegovina"},
    "Czechia": {"Czechia", "Czech Republic"},
}


def fetch_results_csv() -> str:
    return get_text(
        RESULTS_URL,
        headers={"User-Agent": "wc26-dashboard/0.1"},
        timeout=30,
    )


def parse_results(csv_text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(csv_text))
    return [row for row in reader if row.get("date") and row.get("home_team") and row.get("away_team")]


def summarize_team_results(
    teams: list[dict[str, Any]],
    results: list[dict[str, Any]],
    *,
    max_matches: int = 10,
) -> dict[str, Any]:
    aliases = _aliases_by_team(teams)
    by_team: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in sorted(results, key=lambda item: item["date"], reverse=True):
        home_score = _safe_int(row.get("home_score"))
        away_score = _safe_int(row.get("away_score"))
        if home_score is None or away_score is None:
            continue
        home_id = aliases.get(row.get("home_team", ""))
        away_id = aliases.get(row.get("away_team", ""))
        if home_id:
            by_team[home_id].append(_team_result(row, True, home_score, away_score))
        if away_id:
            by_team[away_id].append(_team_result(row, False, home_score, away_score))

    summaries = {}
    for team in teams:
        rows = by_team.get(team["id"], [])[:max_matches]
        summaries[team["id"]] = _summarize_rows(rows)
    return summaries


def _aliases_by_team(teams: list[dict[str, Any]]) -> dict[str, str]:
    aliases = {}
    for team in teams:
        names = {team["name"], team.get("fifa_code", "")}
        names.update(TEAM_ALIASES.get(team["name"], set()))
        for name in names:
            if name:
                aliases[name] = team["id"]
    return aliases


def _team_result(row: dict[str, Any], is_home: bool, home_score: int, away_score: int) -> dict[str, Any]:
    goals_for = home_score if is_home else away_score
    goals_against = away_score if is_home else home_score
    if goals_for > goals_against:
        result = "W"
    elif goals_for == goals_against:
        result = "D"
    else:
        result = "L"
    return {
        "date": row["date"],
        "opponent": row["away_team"] if is_home else row["home_team"],
        "goals_for": goals_for,
        "goals_against": goals_against,
        "result": result,
        "tournament": row.get("tournament"),
    }


def _summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    wins = sum(1 for row in rows if row["result"] == "W")
    draws = sum(1 for row in rows if row["result"] == "D")
    losses = sum(1 for row in rows if row["result"] == "L")
    goals_for = sum(row["goals_for"] for row in rows)
    goals_against = sum(row["goals_against"] for row in rows)
    matches = len(rows)
    ppg = (wins * 3 + draws) / max(matches, 1)
    form_index = _clamp((ppg / 3 - 0.5) * 0.36 + (goals_for - goals_against) / max(matches, 1) * 0.025, -0.18, 0.18)
    return {
        "matches": matches,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "last_10": f"{wins}W-{draws}D-{losses}L",
        "goals_for_per_match": round(goals_for / max(matches, 1), 2),
        "goals_against_per_match": round(goals_against / max(matches, 1), 2),
        "form_index": round(form_index, 3),
        "latest_date": rows[0]["date"] if rows else None,
        "recent": rows[:5],
    }


def _safe_int(value: str | None) -> int | None:
    try:
        return int(value) if value not in {None, ""} else None
    except ValueError:
        return None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
