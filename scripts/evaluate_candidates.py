"""Compare score-model candidates on settled matches with pre-kickoff markets."""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean

from app.services.odds import devig_three_way, devig_two_way
from app.services.score_model import dixon_coles_scoreline_matrix, match_market_probabilities, scoreline_matrix


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "backend" / "app" / "data"
STATIC_DATA = ROOT / "frontend" / "static-site" / "data.json"
LOCK_BUFFER = timedelta(minutes=5)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def latest_pre_kickoff_markets(fixtures: dict[str, dict], odds: list[dict]) -> list[dict]:
    latest = {}
    for row in odds:
        fixture = fixtures.get(row.get("match_id"))
        if not fixture or not row.get("captured_at"):
            continue
        if parse_dt(row["captured_at"]) > parse_dt(fixture["kickoff_utc"]) - LOCK_BUFFER:
            continue
        key = (row["match_id"], row["bookmaker"], row["market_type"], row.get("line"))
        previous = latest.get(key)
        if previous is None or row["captured_at"] > previous["captured_at"]:
            latest[key] = row
    return list(latest.values())


def market_consensus(rows: list[dict]) -> dict[str, dict]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["match_id"], row["market_type"], row.get("line"))].append(row)
    consensus = {}
    for (match_id, market_type, line), markets in grouped.items():
        probabilities = []
        for row in markets:
            try:
                if market_type == "1x2":
                    probabilities.append(devig_three_way(row["price_home"], row["price_draw"], row["price_away"]))
                elif market_type == "over_under":
                    probabilities.append(devig_two_way(row["price_over"], row["price_under"]))
            except (KeyError, TypeError, ValueError):
                continue
        if probabilities:
            consensus[(match_id, market_type, line)] = {
                "probabilities": tuple(mean(row[index] for row in probabilities) for index in range(len(probabilities[0]))),
                "books": len(probabilities),
            }
    return consensus


def blend(model: tuple[float, ...], market: tuple[float, ...], weight: float) -> tuple[float, ...]:
    values = tuple((1 - weight) * left + weight * right for left, right in zip(model, market))
    total = sum(values)
    return tuple(value / total for value in values)


def categorical_metrics(rows: list[tuple[tuple[float, ...], int]]) -> dict:
    if not rows:
        return {"samples": 0, "hits": 0, "hit_rate": None, "brier": None, "log_loss": None}
    hits = 0
    briers = []
    losses = []
    for probabilities, actual in rows:
        hits += int(max(range(len(probabilities)), key=probabilities.__getitem__) == actual)
        outcomes = [int(index == actual) for index in range(len(probabilities))]
        briers.append(sum((probability - outcome) ** 2 for probability, outcome in zip(probabilities, outcomes)) / len(probabilities))
        losses.append(-math.log(max(1e-12, probabilities[actual])))
    return {
        "samples": len(rows),
        "hits": hits,
        "hit_rate": round(hits / len(rows), 6),
        "brier": round(mean(briers), 6),
        "log_loss": round(mean(losses), 6),
    }


def binary_metrics(rows: list[tuple[float, int]]) -> dict:
    return categorical_metrics([((1 - probability, probability), actual) for probability, actual in rows])


def split_metrics(rows: list, metric) -> dict:
    split = len(rows) // 2
    return {
        "all": metric(rows),
        "early_half": metric(rows[:split]),
        "late_half": metric(rows[split:]),
    }


def actual_index(match: dict) -> int:
    home = int(match["live_status"]["home_score"])
    away = int(match["live_status"]["away_score"])
    return 0 if home > away else 1 if home == away else 2


def main() -> None:
    payload = load_json(STATIC_DATA)
    fixtures = {row["id"]: row for row in load_json(DATA_DIR / "fixtures.json")}
    odds = latest_pre_kickoff_markets(fixtures, load_json(DATA_DIR / "odds_snapshots.json"))
    consensus = market_consensus(odds)
    completed = [row for row in payload["matches"] if (row.get("live_status") or {}).get("completed")]
    candidates_1x2 = defaultdict(list)
    candidates_ou = defaultdict(list)
    corner_rows = []
    for match in completed:
        match_id = match["match_id"]
        market_1x2 = consensus.get((match_id, "1x2", None))
        market_ou = consensus.get((match_id, "over_under", 2.5))
        raw = match.get("raw_model") or {}
        raw_lambda_home = raw.get("lambda_home", match["lambda_home"])
        raw_lambda_away = raw.get("lambda_away", match["lambda_away"])
        dc_markets = match_market_probabilities(
            dixon_coles_scoreline_matrix(raw_lambda_home, raw_lambda_away, rho=-0.06)
        )
        neutral_markets = match_market_probabilities(
            scoreline_matrix(
                raw_lambda_home * math.sqrt(1.05 / 1.26),
                raw_lambda_away * math.sqrt(1.26 / 1.05),
            )
        )
        model_1x2 = (
            raw.get("p_home", match["p_home"]),
            raw.get("p_draw", match["p_draw"]),
            raw.get("p_away", match["p_away"]),
        )
        production_1x2 = (match["p_home"], match["p_draw"], match["p_away"])
        dc_1x2 = (dc_markets["p_home"], dc_markets["p_draw"], dc_markets["p_away"])
        outcome = actual_index(match)
        candidates_1x2["poisson"].append((model_1x2, outcome))
        candidates_1x2["production_ensemble"].append((production_1x2, outcome))
        candidates_1x2["dixon_coles"].append((dc_1x2, outcome))
        candidates_1x2["neutral_venue"].append(((neutral_markets["p_home"], neutral_markets["p_draw"], neutral_markets["p_away"]), outcome))
        if market_1x2:
            market_probs = market_1x2["probabilities"]
            candidates_1x2["market"].append((market_probs, outcome))
            for weight in (0.25, 0.5, 0.75):
                candidates_1x2[f"dc_market_{weight:.2f}"].append((blend(dc_1x2, market_probs, weight), outcome))

        total_goals = int(match["live_status"]["home_score"]) + int(match["live_status"]["away_score"])
        actual_over = int(total_goals > 2.5)
        raw_over = raw.get("p_over_2_5", match["p_over_2_5"])
        candidates_ou["poisson"].append((raw_over, actual_over))
        candidates_ou["production_ensemble"].append((match["p_over_2_5"], actual_over))
        candidates_ou["dixon_coles"].append((dc_markets["p_over_2_5"], actual_over))
        candidates_ou["neutral_venue"].append((neutral_markets["p_over_2_5"], actual_over))
        if market_ou:
            market_over = market_ou["probabilities"][0]
            candidates_ou["market"].append((market_over, actual_over))
            for weight in (0.25, 0.5, 0.75):
                probability = (1 - weight) * dc_markets["p_over_2_5"] + weight * market_over
                candidates_ou[f"dc_market_{weight:.2f}"].append((probability, actual_over))

        corners = match.get("event_predictions", {}).get("corners", {})
        if corners.get("live_home") is not None and corners.get("live_away") is not None:
            corner_rows.append((float(corners["total_expected"]), int(corners["live_home"]) + int(corners["live_away"])))

    report = {
        "settled_matches": len(completed),
        "deduplicated_pre_match_odds_rows": len(odds),
        "one_x_two": {name: split_metrics(rows, categorical_metrics) for name, rows in candidates_1x2.items()},
        "over_under_2_5": {name: split_metrics(rows, binary_metrics) for name, rows in candidates_ou.items()},
        "corners": {
            "samples": len(corner_rows),
            "predicted_mean": round(mean(row[0] for row in corner_rows), 4) if corner_rows else None,
            "actual_mean": round(mean(row[1] for row in corner_rows), 4) if corner_rows else None,
            "mean_bias": round(mean(row[0] - row[1] for row in corner_rows), 4) if corner_rows else None,
        },
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
