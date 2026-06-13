"""High-level prediction assembly for API responses."""
from __future__ import annotations

import math
import random
import unicodedata
from datetime import datetime, timezone

from . import data_store
from .handicap import asian_market_from_matrix
from .odds import model_lean
from .score_model import MatchAdjustments, MatchContext, poisson_pmf, predict_match

DEFAULT_HANDICAP_LINES = [-2.5, -2, -1.5, -1.25, -1, -0.75, -0.5, -0.25, 0, 0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 2.5]
MODEL_VERSION = "wc26-v0.5-monte-carlo-factor-tiers"
TITLE_MARKET_ANCHOR_WEIGHT = 0.55
MONTE_CARLO_RUNS = 4000
MONTE_CARLO_SEED = 20260612

R32_SLOTS = [
    (("RU", "A"), ("RU", "B")),
    (("W", "E"), ("3RD", "ABCDF")),
    (("W", "F"), ("RU", "C")),
    (("W", "C"), ("RU", "F")),
    (("W", "I"), ("3RD", "CDFGH")),
    (("RU", "E"), ("RU", "I")),
    (("W", "A"), ("3RD", "CEFHI")),
    (("W", "L"), ("3RD", "EHIJK")),
    (("W", "D"), ("3RD", "BEFIJ")),
    (("W", "G"), ("3RD", "AEHIJ")),
    (("RU", "K"), ("RU", "L")),
    (("W", "H"), ("RU", "J")),
    (("W", "B"), ("3RD", "EFGIJ")),
    (("W", "J"), ("RU", "H")),
    (("W", "K"), ("3RD", "DEIJL")),
    (("RU", "D"), ("RU", "G")),
]
R16_PAIRS = [(1, 4), (0, 2), (3, 5), (6, 7), (10, 11), (8, 9), (13, 15), (12, 14)]
QF_PAIRS = [(0, 1), (4, 5), (2, 3), (6, 7)]
SF_PAIRS = [(0, 1), (2, 3)]


def prediction_for_fixture(fixture: dict) -> dict:
    home = data_store.team_by_id(fixture["home_team_id"])
    away = data_store.team_by_id(fixture["away_team_id"])
    context = data_store.context_for_fixture(fixture)
    live_status = _live_status(fixture)
    factor_breakdown = _factor_breakdown(home, away, fixture, context)
    adjustments = _model_adjustments(home, away, fixture, context, factor_breakdown)
    prediction = predict_match(home, away, context, adjustments)
    matchup = _matchup_profile(home, away, fixture, context, prediction, factor_breakdown)
    event_predictions = _event_predictions(home, away, fixture, context, prediction, live_status)
    return {
        "match_id": fixture["id"],
        "model_version": MODEL_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "home_team": _team_summary(home),
        "away_team": _team_summary(away),
        "fixture": fixture,
        "context": {"notes": list(context.notes), "home_mult": context.home_mult, "away_mult": context.away_mult},
        "live_status": live_status,
        "team_form": _team_form(home, away),
        "tactical_profile": _tactical_match_profile(home, away, fixture, context, live_status),
        "availability": _availability(home, away),
        "weather": _weather_context(fixture),
        "factor_breakdown": factor_breakdown,
        "model_inputs": _model_input_summary(adjustments, factor_breakdown),
        "probability_intervals": _probability_intervals(prediction, factor_breakdown),
        "matchup": matchup,
        "event_predictions": event_predictions,
        "risk_register": _risk_register(home, away, fixture, prediction, factor_breakdown, matchup),
        **{key: value for key, value in prediction.items() if key != "scoreline_matrix"},
    }


def _live_status(fixture: dict) -> dict | None:
    live = data_store.live_match_for_fixture(fixture["id"])
    if not live:
        return None
    return {
        "source": live.get("source"),
        "source_quality": live.get("source_quality"),
        "captured_at": live.get("captured_at"),
        "status_state": live.get("status_state"),
        "status_description": live.get("status_description"),
        "status_detail": live.get("status_detail"),
        "completed": bool(live.get("completed")),
        "display_clock": live.get("display_clock"),
        "period": live.get("period"),
        "home_score": live.get("home_score"),
        "away_score": live.get("away_score"),
        "winner_team_id": live.get("winner_team_id"),
        "attendance": live.get("attendance"),
        "home_stats": live.get("home_stats") or {},
        "away_stats": live.get("away_stats") or {},
    }


def _completed_score(fixture: dict) -> tuple[int, int] | None:
    live = data_store.live_match_for_fixture(fixture["id"])
    if not live or not live.get("completed"):
        return None
    home_score = live.get("home_score")
    away_score = live.get("away_score")
    if home_score is None or away_score is None:
        return None
    return int(home_score), int(away_score)


def score_matrix_for_fixture(fixture: dict) -> list[list[float]]:
    home = data_store.team_by_id(fixture["home_team_id"])
    away = data_store.team_by_id(fixture["away_team_id"])
    context = data_store.context_for_fixture(fixture)
    factor_breakdown = _factor_breakdown(home, away, fixture, context)
    adjustments = _model_adjustments(home, away, fixture, context, factor_breakdown)
    return predict_match(home, away, context, adjustments)["scoreline_matrix"]


def handicaps_for_fixture(fixture: dict, lines: list[float] | None = None) -> dict:
    lines = lines or DEFAULT_HANDICAP_LINES
    matrix = score_matrix_for_fixture(fixture)
    rows = []
    for line in lines:
        market = _best_market(fixture["id"], line)
        market_is_legal = _is_legal_market(market)
        row = asian_market_from_matrix(
            matrix,
            line,
            market_home_odds=market.get("price_home") if market else None,
            market_away_odds=market.get("price_away") if market else None,
        )
        row["source"] = market["bookmaker"] if market else "model_fair_line"
        row["captured_at"] = market.get("captured_at") if market else None
        row["market_status"] = "available" if market_is_legal else ("proxy" if market else "missing")
        row["closing_status"] = "pending_closing_line" if market_is_legal else "pending_legal_odds_api"
        row["clv"] = None
        row["backtest_sample"] = 0
        row["lean"] = model_lean(row["home"]["expected_return"], row["away"]["expected_return"])
        rows.append(row)
    return {
        "match_id": fixture["id"],
        "home_team": _team_summary(data_store.team_by_id(fixture["home_team_id"])),
        "away_team": _team_summary(data_store.team_by_id(fixture["away_team_id"])),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "disclaimer": "Model probability display only; not betting advice.",
        "handicaps": rows,
    }


def all_matches() -> list[dict]:
    out = []
    for fixture in data_store.fixtures():
        base = prediction_for_fixture(fixture)
        base["handicap_preview"] = handicaps_for_fixture(fixture)["handicaps"]
        out.append(base)
    return out


def tournament_probabilities() -> dict:
    teams = data_store.teams()
    strengths = _team_strengths(teams)
    raw_market_probabilities = _polymarket_title_probabilities(teams)
    market_probabilities = _normalize_probabilities(raw_market_probabilities)
    projection = _tournament_projection(teams)
    simulation = _monte_carlo_tournament(teams, MONTE_CARLO_RUNS, MONTE_CARLO_SEED)
    raw_title_probabilities = {
        team_id: simulation["teams"][team_id]["title_probability"]
        for team_id in teams
    }
    group_ranks = projection["group_ranks"]
    anchor_weight = TITLE_MARKET_ANCHOR_WEIGHT if market_probabilities else 0.0
    anchored_scores = {}
    for team_id, raw_probability in raw_title_probabilities.items():
        market_probability = market_probabilities.get(team_id)
        anchored_scores[team_id] = (
            raw_probability
            if market_probability is None
            else raw_probability * (1 - anchor_weight) + market_probability * anchor_weight
        )
    title_probabilities = _normalize_probabilities(anchored_scores)
    rounded_title_probabilities = _rounded_probabilities(title_probabilities)
    title = []
    for team_id, strength in strengths.items():
        team = teams[team_id]
        group_rank = group_ranks[team_id]
        rank_base = {1: 0.88, 2: 0.70, 3: 0.44, 4: 0.19}[group_rank]
        group_avg = sum(value for value_id, value in strengths.items() if teams[value_id].group == team.group) / 4
        reach_r32 = _clamp(rank_base + (strength - group_avg) * 0.20, 0.08, 0.97)
        market_probability = market_probabilities.get(team_id)
        raw_market_probability = raw_market_probabilities.get(team_id)
        raw_title_probability = raw_title_probabilities[team_id]
        title_probability = rounded_title_probabilities[team_id]
        simulated = simulation["teams"][team_id]
        title.append(
            {
                "team_id": team_id,
                "team": team.name,
                "flag_code": team.flag_code,
                "group": team.group,
                "title_probability": title_probability,
                "raw_title_probability": round(raw_title_probability, 6),
                "market_probability": round(market_probability, 6) if market_probability is not None else None,
                "raw_market_probability": round(raw_market_probability, 6) if raw_market_probability is not None else None,
                "title_anchor_weight": anchor_weight if market_probability is not None else 0.0,
                "model_market_delta": (
                    round(raw_title_probability - market_probability, 6)
                    if market_probability is not None
                    else None
                ),
                "market_source": "Polymarket Gamma" if market_probability is not None else None,
                "reach_r32": round(simulated["reach_r32"], 6),
                "reach_r16": round(simulated["reach_r16"], 6),
                "reach_qf": round(simulated["reach_qf"], 6),
                "reach_sf": round(simulated["reach_sf"], 6),
                "reach_final": round(simulated["reach_final"], 6),
                "title_confidence_interval": simulated["title_confidence_interval"],
                "deterministic_reach_r32": round(reach_r32, 6),
                "projected_group_position": group_rank,
            }
        )
    return {
        "model_version": MODEL_VERSION,
        "n_simulations": simulation["n_simulations"],
        "format": "12 groups of four; top two plus eight best third-place teams reach the round of 32",
        "data_quality": "public snapshots plus transparent priors; event, live injury and sportsbook feeds still require provider backfill",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "title_anchor": {
            "source": "Polymarket Gamma",
            "coverage": len(market_probabilities),
            "weight": anchor_weight,
            "method": "normalize public Yes prices across matched teams, then blend with raw model title probability",
        },
        "projected_matches_total": 104,
        "group_stage_matches": 72,
        "knockout_projected_matches": 32,
        "group_table": projection["group_table"],
        "qualified_thirds": projection["qualified_thirds"],
        "bracket": projection["bracket"],
        "monte_carlo": {
            "n_simulations": simulation["n_simulations"],
            "seed": simulation["seed"],
            "source": simulation["source"],
            "round_probability_fields": ["reach_r32", "reach_r16", "reach_qf", "reach_sf", "reach_final", "title_probability"],
        },
        "market_validation": _market_validation_summary(),
        "goal_scale_sanity": _goal_scale_sanity(simulation),
        "sanity_checks": {
            "title_probability_sum": round(sum(title_probabilities.values()), 6),
            "raw_title_probability_sum": round(sum(raw_title_probabilities.values()), 6),
            "market_probability_sum": round(sum(market_probabilities.values()), 6) if market_probabilities else None,
            "projected_knockout_matches": sum(len(round_row["matches"]) for round_row in projection["bracket"]["rounds"]),
            "average_group_goals_per_match": simulation["average_group_goals_per_match"],
        },
        "teams": sorted(title, key=lambda row: row["title_probability"], reverse=True),
    }


def _goal_scale_sanity(simulation: dict) -> dict:
    goals_per_match = simulation["average_group_goals_per_match"]
    estimated_total_goals = goals_per_match * 104
    if estimated_total_goals >= 280:
        golden_boot_band = "7-10"
    elif estimated_total_goals >= 245:
        golden_boot_band = "6-8"
    else:
        golden_boot_band = "5-7"
    return {
        "average_goals_per_match": goals_per_match,
        "estimated_tournament_goals": round(estimated_total_goals, 1),
        "golden_boot_goal_band": golden_boot_band,
        "status": "sanity_check_only_pending_player_shot_model",
    }


def _team_strengths(teams: dict) -> dict[str, float]:
    return {
        team_id: max(0.02, team.elo / 1850 + team.attack + team.form_index * 0.22 - 0.35 * team.injury_impact)
        for team_id, team in teams.items()
    }


def _normalize_probabilities(values: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, value) for value in values.values())
    if total <= 0:
        return {}
    return {key: max(0.0, value) / total for key, value in values.items()}


def _rounded_probabilities(values: dict[str, float], places: int = 6) -> dict[str, float]:
    keys = list(values)
    if not keys:
        return {}
    rounded = {}
    running = 0.0
    for key in keys[:-1]:
        rounded[key] = round(values[key], places)
        running += rounded[key]
    rounded[keys[-1]] = round(_clamp(1.0 - running, 0.0, 1.0), places)
    return rounded


def _tournament_projection(teams: dict) -> dict:
    standings = _project_group_tables()
    group_table = []
    group_ranks = {}
    third_rows = []
    for group in sorted(standings):
        rows = standings[group]
        group_table.append({"group": group, "rows": rows})
        for row in rows:
            group_ranks[row["team_id"]] = row["position"]
        third_rows.append(rows[2])
    qualified_thirds = sorted(
        third_rows,
        key=lambda row: (row["expected_points"], row["expected_goal_difference"], row["expected_goals_for"], row["team"]),
        reverse=True,
    )[:8]
    bracket = _project_bracket(teams, standings, qualified_thirds)
    return {
        "group_table": group_table,
        "group_ranks": group_ranks,
        "qualified_thirds": qualified_thirds,
        "bracket": bracket,
    }


def _monte_carlo_tournament(teams: dict, n_simulations: int, seed: int) -> dict:
    rng = random.Random(seed)
    fixture_distributions = [
        (
            fixture,
            _matrix_cumulative(score_matrix_for_fixture(fixture)),
            _completed_score(fixture),
        )
        for fixture in data_store.fixtures()
    ]
    counts = {
        team_id: {
            "reach_r32": 0,
            "reach_r16": 0,
            "reach_qf": 0,
            "reach_sf": 0,
            "reach_final": 0,
            "title_probability": 0,
        }
        for team_id in teams
    }
    neutral_cache: dict[tuple[str, str], float] = {}
    total_group_goals = 0

    for _index in range(n_simulations):
        standings = _simulate_group_stage(teams, fixture_distributions, rng)
        total_group_goals += standings.pop("_total_goals")
        third_rows = [rows[2] for rows in standings.values()]
        qualified_thirds = sorted(
            third_rows,
            key=lambda row: (row["points"], row["goal_difference"], row["goals_for"], rng.random()),
            reverse=True,
        )[:8]
        third_assignment = _assign_third_place_slots({row["group"] for row in qualified_thirds})
        qualifiers = [row for rows in standings.values() for row in rows[:2]] + qualified_thirds
        for row in qualifiers:
            counts[row["team_id"]]["reach_r32"] += 1

        r32 = []
        for match_index, (home_slot, away_slot) in enumerate(R32_SLOTS):
            home = _resolve_sim_slot(home_slot, standings, third_assignment, match_index)
            away = _resolve_sim_slot(away_slot, standings, third_assignment, match_index)
            winner, loser = _sample_neutral_tie(home, away, neutral_cache, rng)
            counts[winner["team_id"]]["reach_r16"] += 1
            r32.append({"winner": winner, "loser": loser})

        r16 = _simulate_knockout_round(r32, R16_PAIRS, neutral_cache, rng, counts, "reach_qf")
        qf = _simulate_knockout_round(r16, QF_PAIRS, neutral_cache, rng, counts, "reach_sf")
        sf = _simulate_knockout_round(qf, SF_PAIRS, neutral_cache, rng, counts, "reach_final")
        final_winner, _final_loser = _sample_neutral_tie(sf[0]["winner"], sf[1]["winner"], neutral_cache, rng)
        counts[final_winner["team_id"]]["title_probability"] += 1

    team_probs = {}
    for team_id, row in counts.items():
        title_probability = row["title_probability"] / n_simulations
        team_probs[team_id] = {
            "reach_r32": row["reach_r32"] / n_simulations,
            "reach_r16": row["reach_r16"] / n_simulations,
            "reach_qf": row["reach_qf"] / n_simulations,
            "reach_sf": row["reach_sf"] / n_simulations,
            "reach_final": row["reach_final"] / n_simulations,
            "title_probability": title_probability,
            "title_confidence_interval": _binomial_interval(title_probability, n_simulations),
        }

    return {
        "n_simulations": n_simulations,
        "seed": seed,
        "source": "seeded Monte Carlo from group-stage scoreline matrices and official 32-team knockout path",
        "average_group_goals_per_match": round(total_group_goals / max(1, n_simulations * len(fixture_distributions)), 3),
        "teams": team_probs,
    }


def _simulate_group_stage(teams: dict, fixture_distributions: list[tuple[dict, list[tuple[float, int, int]], tuple[int, int] | None]], rng: random.Random) -> dict:
    stats = {
        team_id: {
            "team_id": team_id,
            "team": team.name,
            "flag_code": team.flag_code,
            "group": team.group,
            "points": 0,
            "goals_for": 0,
            "goals_against": 0,
            "wins": 0,
        }
        for team_id, team in teams.items()
    }
    total_goals = 0
    for fixture, cumulative, completed_score in fixture_distributions:
        home_id = fixture["home_team_id"]
        away_id = fixture["away_team_id"]
        home_goals, away_goals = completed_score if completed_score else _sample_score(cumulative, rng)
        total_goals += home_goals + away_goals
        stats[home_id]["goals_for"] += home_goals
        stats[home_id]["goals_against"] += away_goals
        stats[away_id]["goals_for"] += away_goals
        stats[away_id]["goals_against"] += home_goals
        if home_goals > away_goals:
            stats[home_id]["points"] += 3
            stats[home_id]["wins"] += 1
        elif away_goals > home_goals:
            stats[away_id]["points"] += 3
            stats[away_id]["wins"] += 1
        else:
            stats[home_id]["points"] += 1
            stats[away_id]["points"] += 1

    grouped: dict[str, list[dict]] = {}
    for row in stats.values():
        row["goal_difference"] = row["goals_for"] - row["goals_against"]
        grouped.setdefault(row["group"], []).append(row)

    ranked = {
        group: [
            {**row, "position": index}
            for index, row in enumerate(
                sorted(
                    rows,
                    key=lambda row: (
                        row["points"],
                        row["goal_difference"],
                        row["goals_for"],
                        row["wins"],
                        rng.random(),
                    ),
                    reverse=True,
                ),
                start=1,
            )
        ]
        for group, rows in grouped.items()
    }
    ranked["_total_goals"] = total_goals
    return ranked


def _matrix_cumulative(matrix: list[list[float]]) -> list[tuple[float, int, int]]:
    cumulative = []
    running = 0.0
    for home_goals, row in enumerate(matrix):
        for away_goals, probability in enumerate(row):
            running += probability
            cumulative.append((running, home_goals, away_goals))
    cumulative[-1] = (1.0, cumulative[-1][1], cumulative[-1][2])
    return cumulative


def _sample_score(cumulative: list[tuple[float, int, int]], rng: random.Random) -> tuple[int, int]:
    draw = rng.random()
    for threshold, home_goals, away_goals in cumulative:
        if draw <= threshold:
            return home_goals, away_goals
    return cumulative[-1][1], cumulative[-1][2]


def _resolve_sim_slot(slot: tuple[str, str], standings: dict[str, list[dict]], third_assignment: dict[int, str], match_index: int) -> dict:
    kind, group = slot
    if kind == "W":
        return standings[group][0]
    if kind == "RU":
        return standings[group][1]
    third_group = third_assignment.get(match_index)
    if third_group is None:
        third_group = sorted(set(group))[0]
    return standings[third_group][2]


def _simulate_knockout_round(
    previous: list[dict],
    pairs: list[tuple[int, int]],
    neutral_cache: dict[tuple[str, str], float],
    rng: random.Random,
    counts: dict[str, dict],
    reach_key: str,
) -> list[dict]:
    out = []
    for left, right in pairs:
        winner, loser = _sample_neutral_tie(previous[left]["winner"], previous[right]["winner"], neutral_cache, rng)
        counts[winner["team_id"]][reach_key] += 1
        out.append({"winner": winner, "loser": loser})
    return out


def _sample_neutral_tie(home: dict, away: dict, neutral_cache: dict[tuple[str, str], float], rng: random.Random) -> tuple[dict, dict]:
    key = (home["team_id"], away["team_id"])
    if key not in neutral_cache:
        neutral_cache[key] = _neutral_advancement_probability(
            data_store.team_by_id(home["team_id"]),
            data_store.team_by_id(away["team_id"]),
        )
    if rng.random() < neutral_cache[key]:
        return home, away
    return away, home


def _binomial_interval(probability: float, n: int) -> dict:
    margin = 1.96 * math.sqrt(max(0.0, probability * (1 - probability)) / max(1, n))
    return {
        "low": round(_clamp(probability - margin, 0.0, 1.0), 6),
        "high": round(_clamp(probability + margin, 0.0, 1.0), 6),
    }


def _project_group_tables() -> dict[str, list[dict]]:
    teams = data_store.teams()
    stats = {
        team_id: {
            "team_id": team_id,
            "team": team.name,
            "flag_code": team.flag_code,
            "group": team.group,
            "expected_points": 0.0,
            "expected_goals_for": 0.0,
            "expected_goals_against": 0.0,
            "win_probability_sum": 0.0,
        }
        for team_id, team in teams.items()
    }
    for fixture in data_store.fixtures():
        home_id = fixture["home_team_id"]
        away_id = fixture["away_team_id"]
        completed_score = _completed_score(fixture)
        if completed_score:
            home_goals, away_goals = completed_score
            stats[home_id]["expected_points"] += 3 if home_goals > away_goals else 1 if home_goals == away_goals else 0
            stats[away_id]["expected_points"] += 3 if away_goals > home_goals else 1 if home_goals == away_goals else 0
            stats[home_id]["expected_goals_for"] += home_goals
            stats[home_id]["expected_goals_against"] += away_goals
            stats[away_id]["expected_goals_for"] += away_goals
            stats[away_id]["expected_goals_against"] += home_goals
            stats[home_id]["win_probability_sum"] += 1 if home_goals > away_goals else 0
            stats[away_id]["win_probability_sum"] += 1 if away_goals > home_goals else 0
        else:
            prediction = prediction_for_fixture(fixture)
            stats[home_id]["expected_points"] += 3 * prediction["p_home"] + prediction["p_draw"]
            stats[away_id]["expected_points"] += 3 * prediction["p_away"] + prediction["p_draw"]
            stats[home_id]["expected_goals_for"] += prediction["lambda_home"]
            stats[home_id]["expected_goals_against"] += prediction["lambda_away"]
            stats[away_id]["expected_goals_for"] += prediction["lambda_away"]
            stats[away_id]["expected_goals_against"] += prediction["lambda_home"]
            stats[home_id]["win_probability_sum"] += prediction["p_home"]
            stats[away_id]["win_probability_sum"] += prediction["p_away"]

    groups: dict[str, list[dict]] = {}
    for team_id, row in stats.items():
        row["expected_goal_difference"] = row["expected_goals_for"] - row["expected_goals_against"]
        groups.setdefault(row["group"], []).append(row)

    out = {}
    for group, rows in groups.items():
        ranked = sorted(
            rows,
            key=lambda row: (
                row["expected_points"],
                row["expected_goal_difference"],
                row["expected_goals_for"],
                row["win_probability_sum"],
                row["team"],
            ),
            reverse=True,
        )
        out[group] = [
            {
                **row,
                "position": index,
                "expected_points": round(row["expected_points"], 3),
                "expected_goals_for": round(row["expected_goals_for"], 3),
                "expected_goals_against": round(row["expected_goals_against"], 3),
                "expected_goal_difference": round(row["expected_goal_difference"], 3),
                "win_probability_sum": round(row["win_probability_sum"], 3),
            }
            for index, row in enumerate(ranked, start=1)
        ]
    return out


def _project_bracket(teams: dict, standings: dict[str, list[dict]], qualified_thirds: list[dict]) -> dict:
    third_groups = {row["group"] for row in qualified_thirds}
    third_assignment = _assign_third_place_slots(third_groups)
    rounds = []

    r32_matches = []
    for index, (home_slot, away_slot) in enumerate(R32_SLOTS, start=73):
        match = _projected_tie(
            index,
            "R32",
            _resolve_bracket_slot(home_slot, standings, third_assignment, index - 73),
            _resolve_bracket_slot(away_slot, standings, third_assignment, index - 73),
            home_slot,
            away_slot,
        )
        r32_matches.append(match)
    rounds.append({"round": "R32", "label": "32 强", "matches": r32_matches})

    r16_matches = _round_from_previous(r32_matches, R16_PAIRS, 89, "R16", "16 强")
    rounds.append({"round": "R16", "label": "16 强", "matches": r16_matches})
    qf_matches = _round_from_previous(r16_matches, QF_PAIRS, 97, "QF", "1/4 决赛")
    rounds.append({"round": "QF", "label": "1/4 决赛", "matches": qf_matches})
    sf_matches = _round_from_previous(qf_matches, SF_PAIRS, 101, "SF", "半决赛")
    rounds.append({"round": "SF", "label": "半决赛", "matches": sf_matches})

    third_place = _projected_tie(103, "Third Place", sf_matches[0]["loser"], sf_matches[1]["loser"])
    final = _projected_tie(104, "Final", sf_matches[0]["winner"], sf_matches[1]["winner"])
    rounds.append({"round": "Third Place", "label": "三四名", "matches": [third_place]})
    rounds.append({"round": "Final", "label": "决赛", "matches": [final]})

    return {
        "source": "deterministic path from current match probabilities; not a Monte Carlo distribution",
        "third_place_assignment": third_assignment,
        "champion": final["winner"],
        "rounds": rounds,
    }


def _assign_third_place_slots(selected_groups: set[str]) -> dict[int, str]:
    slots = [
        (index, slot[1])
        for index, pair in enumerate(R32_SLOTS)
        for slot in pair
        if slot[0] == "3RD"
    ]

    def backtrack(position: int, remaining: set[str], assigned: dict[int, str]) -> dict[int, str] | None:
        if position == len(slots):
            return assigned
        slot_index, eligible = slots[position]
        for group in sorted(remaining):
            if group not in eligible:
                continue
            next_assigned = dict(assigned)
            next_assigned[slot_index] = group
            resolved = backtrack(position + 1, remaining - {group}, next_assigned)
            if resolved is not None:
                return resolved
        return None

    return backtrack(0, set(selected_groups), {}) or {}


def _resolve_bracket_slot(slot: tuple[str, str], standings: dict[str, list[dict]], third_assignment: dict[int, str], match_index: int) -> dict:
    kind, group = slot
    if kind == "W":
        return standings[group][0]
    if kind == "RU":
        return standings[group][1]
    third_group = third_assignment.get(match_index)
    if third_group is None:
        third_group = sorted(set(group))[0]
    return standings[third_group][2]


def _round_from_previous(previous: list[dict], pairs: list[tuple[int, int]], start_number: int, round_key: str, label: str) -> list[dict]:
    return [
        _projected_tie(start_number + index, round_key, previous[left]["winner"], previous[right]["winner"])
        for index, (left, right) in enumerate(pairs)
    ]


def _projected_tie(
    match_number: int,
    round_key: str,
    home: dict,
    away: dict,
    home_slot: tuple[str, str] | None = None,
    away_slot: tuple[str, str] | None = None,
) -> dict:
    home_team = data_store.team_by_id(home["team_id"])
    away_team = data_store.team_by_id(away["team_id"])
    home_advancement_probability = _neutral_advancement_probability(home_team, away_team)
    home_wins = home_advancement_probability >= 0.5
    winner = home if home_wins else away
    loser = away if home_wins else home
    return {
        "match_number": match_number,
        "round": round_key,
        "home": _bracket_team(home),
        "away": _bracket_team(away),
        "home_slot": _slot_label(home_slot),
        "away_slot": _slot_label(away_slot),
        "home_advancement_probability": round(home_advancement_probability, 6),
        "winner_probability": round(max(home_advancement_probability, 1 - home_advancement_probability), 6),
        "winner": _bracket_team(winner),
        "loser": _bracket_team(loser),
    }


def _neutral_advancement_probability(home, away) -> float:
    forward = predict_match(home, away, MatchContext(), MatchAdjustments())
    reverse = predict_match(away, home, MatchContext(), MatchAdjustments())
    forward_home = forward["p_home"] + forward["p_draw"] * 0.5
    reverse_away = 1 - (reverse["p_home"] + reverse["p_draw"] * 0.5)
    return _clamp((forward_home + reverse_away) / 2, 0.03, 0.97)


def _bracket_team(row: dict) -> dict:
    return {
        "team_id": row["team_id"],
        "team": row["team"],
        "flag_code": row["flag_code"],
        "group": row["group"],
        "group_position": row.get("position"),
        "expected_points": row.get("expected_points"),
    }


def _slot_label(slot: tuple[str, str] | None) -> str | None:
    if slot is None:
        return None
    kind, group = slot
    if kind == "W":
        return f"{group}组第1"
    if kind == "RU":
        return f"{group}组第2"
    return f"小组第3候选 {group}"


def _polymarket_title_probabilities(teams: dict) -> dict[str, float]:
    aliases = {}
    for team_id, team in teams.items():
        aliases[_market_key(team.name)] = team_id
        aliases[_market_key(team.fifa_code)] = team_id
    aliases.update(
        {
            "usa": "usa",
            "united states": "usa",
            "ivory coast": "civ",
            "cote d ivoire": "civ",
            "czech republic": "cze",
            "czechia": "cze",
            "curacao": "cur",
            "cape verde": "cpv",
            "cabo verde": "cpv",
            "dr congo": "cod",
            "congo dr": "cod",
            "democratic republic of congo": "cod",
            "bosnia herzegovina": "bih",
            "bosnia and herzegovina": "bih",
            "turkiye": "tur",
            "turkey": "tur",
        }
    )
    out: dict[str, float] = {}
    for market in data_store.prediction_markets():
        raw_question = str(market.get("question") or "")
        question = _market_key(raw_question)
        if "world cup" not in question or "win" not in question:
            continue
        subject = question
        if subject.startswith("will "):
            subject = subject[5:]
        if " win the " in subject:
            subject = subject.split(" win the ", 1)[0]
        team_id = aliases.get(subject)
        if team_id is None:
            team_id = next(
                (
                    candidate_id
                    for name, candidate_id in sorted(aliases.items(), key=lambda row: len(row[0]), reverse=True)
                    if len(name) > 3 and name in question
                ),
                None,
            )
        if not team_id:
            continue
        yes = next((row for row in market.get("outcomes", []) if str(row.get("name", "")).lower() == "yes"), None)
        if yes and yes.get("price") is not None:
            out[team_id] = float(yes["price"])
    return out


def _market_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(
        "".join(char.lower() if char.isalnum() else " " for char in normalized).split()
    )


def model_run() -> dict:
    return {
        "model_version": MODEL_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "score_model": "Poisson scoreline prior using public historical results, rating priors, fixture context, venue and travel; weather is display-only for 1X2",
        "handicap_engine": "Asian handicap probabilities derived from scoreline matrix",
        "calibration_status": "v0.5 seeded Monte Carlo public snapshot model; live event, injury and closing-line calibration remain pending provider access",
        "public_boundary": "Information display only; no staking or betting instruction.",
        "market_validation": _market_validation_summary(),
        "factor_policy": [
            {
                "name": "martj42 international results",
                "category": "透明先验",
                "status": "used_in_model_pending_walk_forward",
                "role": "recent form and goals-for/goals-against snapshot",
            },
            {
                "name": "Open-Meteo",
                "category": "仅展示",
                "status": "display_only_for_1x2",
                "role": "weather, wind and heat context; not promoted to win/loss model until backtested",
            },
            {
                "name": "Polymarket Gamma",
                "category": "透明先验",
                "status": "used_in_title_anchor",
                "role": "public title-market anchor after normalization",
            },
            {
                "name": "technical process metrics",
                "category": "仅展示",
                "status": "display_proxy_only",
                "role": "possession, shots, xG, PPDA and card rates are seed-derived until event data is connected",
            },
            {
                "name": "player availability",
                "category": "仅展示",
                "status": "qdr_proxy_pending_feed",
                "role": "QDR, dependency and rotation risk are shown as squad-depth proxies until lineup/injury provider is connected",
            },
            {
                "name": "Asian handicap closing line",
                "category": "待接入",
                "status": "blocked_without_legal_odds_api",
                "role": "true market line, closing line, CLV and ROI backtest require a licensed odds source",
            },
        ],
    }


def _market_validation_summary() -> dict:
    odds_rows = data_store.odds_snapshots()
    ah_rows = [row for row in odds_rows if row.get("market_type") == "asian_handicap"]
    legal_ah_rows = [row for row in ah_rows if _is_legal_market(row)]
    proxy_ah_rows = [row for row in ah_rows if not _is_legal_market(row)]
    return {
        "asian_handicap_rows": len(ah_rows),
        "legal_asian_handicap_rows": len(legal_ah_rows),
        "proxy_asian_handicap_rows": len(proxy_ah_rows),
        "true_market_line_status": "available" if legal_ah_rows else "pending_legal_odds_api",
        "closing_line_status": "pending_closing_snapshots",
        "clv_status": "not_computable_without_closing_line",
        "backtest_metrics_ready": False,
        "planned_metrics": ["Asian handicap hit rate", "CLV", "Brier", "log-loss", "ROI as research-only diagnostic"],
        "public_note": "No betting instruction is generated; market gaps stay visible instead of being filled with synthetic odds.",
    }


def _best_market(match_id: str, line: float) -> dict | None:
    markets = [
        row
        for row in data_store.odds_for_match(match_id, "asian_handicap")
        if float(row["line"]) == float(line)
    ]
    if not markets:
        return None
    return sorted(markets, key=lambda row: row["captured_at"], reverse=True)[0]


def _is_legal_market(market: dict | None) -> bool:
    if not market:
        return False
    bookmaker = str(market.get("bookmaker") or "").lower()
    return "proxy" not in bookmaker and "sample" not in bookmaker


def _team_summary(team) -> dict:
    return {
        "id": team.id,
        "name": team.name,
        "group": team.group,
        "fifa_code": team.fifa_code,
        "flag_code": team.flag_code,
        "elo": team.elo,
        "attack": team.attack,
        "defence": team.defence,
        "form_index": team.form_index,
        "injury_impact": team.injury_impact,
    }


def _team_form(home, away) -> dict:
    return {
        "home": _form_profile(home),
        "away": _form_profile(away),
        "elo_gap": round(home.elo - away.elo, 1),
        "data_source": "martj42 international_results when refreshed; seed profile fallback for missing teams",
    }


def _form_profile(team) -> dict:
    history = data_store.team_history(team.id)
    clean_sheet_rate = _clamp(0.34 + team.defence * 0.9, 0.18, 0.58)
    xg_for = _xg_for(team)
    xg_against = _xg_against(team)
    return {
        "elo": round(team.elo, 0),
        "form_index": round(team.form_index, 3),
        "last_10": history.get("last_10") if history else _last_10_record(team),
        "goals_for": round(history.get("goals_for", _goals_for_18m(team)), 1) if history else round(_goals_for_18m(team), 1),
        "goals_against": (
            round(history.get("goals_against", _goals_against_18m(team)), 1)
            if history
            else round(_goals_against_18m(team), 1)
        ),
        "xg_for": round(xg_for, 2),
        "xg_against": round(xg_against, 2),
        "clean_sheet_rate": round(clean_sheet_rate, 3),
        "latest_result_date": history.get("latest_date") if history else None,
        "source": "martj42 international_results" if history and history.get("matches") else "seed_proxy",
    }


def _last_10_record(team) -> str:
    wins = int(max(2, min(8, round(4.8 + team.form_index * 10 + team.attack * 7))))
    losses = int(max(1, min(5, round(3.0 - team.defence * 5 + team.injury_impact * 10))))
    losses = min(losses, 10 - wins)
    draws = max(0, 10 - wins - losses)
    return f"{wins}W-{draws}D-{losses}L"


def _availability(home, away) -> dict:
    return {
        "home": _availability_profile(home),
        "away": _availability_profile(away),
        "source": "lineup/injury adapter placeholder; player names are projected watchlist entries",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _availability_profile(team) -> dict:
    risk = "low"
    if team.injury_impact >= 0.025:
        risk = "elevated"
    elif team.injury_impact >= 0.015:
        risk = "medium"
    qdr_index = _clamp(0.62 + team.attack * 0.7 + team.defence * 0.45 + team.form_index * 0.5 - team.injury_impact * 4.5, 0.22, 0.92)
    key_dependency = _clamp(0.58 + team.attack * 0.45 - team.defence * 0.25 + team.injury_impact * 6, 0.28, 0.88)
    rotation_capacity = _clamp(0.58 + (team.elo - 1600) / 760 + team.defence * 0.35 - team.injury_impact * 3.2, 0.24, 0.9)
    return {
        "risk": risk,
        "available_starters": int(max(8, min(11, round(11 - team.injury_impact * 70)))),
        "minutes_load": round(max(0.18, min(0.82, 0.44 + team.form_index * 0.9 + team.injury_impact * 4)), 2),
        "qdr_index": round(qdr_index, 3),
        "key_dependency": round(key_dependency, 3),
        "rotation_capacity": round(rotation_capacity, 3),
        "source": "seed squad-depth proxy; connect injury/lineup API before using as live player status",
        "data_quality": "proxy_pending_player_feed",
        "used_in_core_prediction": False,
        "key_players": _key_players(team),
    }


def _key_players(team) -> list[dict]:
    player_names = {
        "mex": ["S. Gimenez", "E. Alvarez", "L. Chavez"],
        "rsa": ["P. Tau", "T. Mokoena", "R. Williams"],
        "kor": ["Son H-m", "Lee K-i", "Kim M-j"],
        "cze": ["P. Schick", "T. Soucek", "V. Coufal"],
        "can": ["A. Davies", "J. David", "S. Eustaquio"],
        "bih": ["E. Dzeko", "M. Pjanic", "S. Kolasinac"],
        "qat": ["A. Afif", "Almoez Ali", "A. Hassan"],
        "sui": ["G. Xhaka", "M. Akanji", "B. Embolo"],
        "usa": ["C. Pulisic", "T. Adams", "W. McKennie"],
        "par": ["M. Almiron", "G. Gomez", "J. Enciso"],
        "tur": ["H. Calhanoglu", "A. Guler", "K. Akturkoglu"],
        "aus": ["M. Ryan", "J. Irvine", "C. Goodwin"],
        "bra": ["Vinicius Jr", "Rodrygo", "Bruno G."],
        "sco": ["S. McTominay", "A. Robertson", "J. McGinn"],
        "hai": ["D. Nazon", "F. Pierrot", "J. Duverger"],
        "mar": ["A. Hakimi", "S. Amrabat", "Y. En-Nesyri"],
        "ger": ["J. Musiala", "F. Wirtz", "K. Havertz"],
        "ecu": ["M. Caicedo", "P. Estupinan", "E. Valencia"],
        "civ": ["S. Haller", "F. Kessie", "O. Diomande"],
        "cur": ["L. Bacuna", "J. Bacuna", "E. Room"],
        "ned": ["V. van Dijk", "F. de Jong", "C. Gakpo"],
        "jpn": ["T. Kubo", "K. Mitoma", "W. Endo"],
        "swe": ["A. Isak", "D. Kulusevski", "V. Gyokeres"],
        "tun": ["Y. Msakni", "E. Skhiri", "B. Dahmen"],
        "bel": ["K. De Bruyne", "J. Doku", "R. Lukaku"],
        "egy": ["M. Salah", "O. Marmoush", "M. Elneny"],
        "irn": ["M. Taremi", "S. Azmoun", "A. Jahanbakhsh"],
        "nzl": ["C. Wood", "S. Singh", "L. Cacace"],
        "esp": ["L. Yamal", "Pedri", "Rodri"],
        "cpv": ["R. Mendes", "G. Rodrigues", "Vozinha"],
        "ksa": ["S. Al-Dawsari", "M. Kanno", "A. Al-Bulaihi"],
        "uru": ["F. Valverde", "D. Nunez", "R. Araujo"],
        "fra": ["K. Mbappe", "A. Griezmann", "A. Tchouameni"],
        "sen": ["S. Mane", "K. Koulibaly", "E. Mendy"],
        "irq": ["A. Hussein", "Z. Iqbal", "I. Bayesh"],
        "nor": ["E. Haaland", "M. Odegaard", "A. Sorloth"],
        "arg": ["L. Messi", "J. Alvarez", "A. Mac Allister"],
        "alg": ["R. Mahrez", "I. Bennacer", "A. Gouiri"],
        "aut": ["M. Sabitzer", "D. Alaba", "K. Laimer"],
        "jor": ["Y. Al-Naimat", "M. Al-Taamari", "N. Al-Rawabdeh"],
        "por": ["C. Ronaldo", "B. Fernandes", "R. Leao"],
        "cod": ["C. Bakambu", "Y. Wissa", "C. Mbemba"],
        "uzb": ["E. Shomurodov", "J. Masharipov", "A. Fayzullaev"],
        "col": ["L. Diaz", "J. Rodriguez", "J. Lerma"],
        "eng": ["H. Kane", "J. Bellingham", "B. Saka"],
        "cro": ["L. Modric", "J. Gvardiol", "M. Kovacic"],
        "gha": ["M. Kudus", "T. Partey", "I. Williams"],
        "pan": ["A. Godoy", "I. Diaz", "M. Murillo"],
    }
    names = player_names.get(team.id, [f"{team.fifa_code} FW", f"{team.fifa_code} MID", f"{team.fifa_code} CB"])
    base = [
        ("attack", max(0.52, min(0.92, 0.72 + team.attack + team.form_index * 0.4))),
        ("control", max(0.50, min(0.9, 0.68 + team.form_index * 0.35 - team.injury_impact * 2))),
        ("defence", max(0.50, min(0.9, 0.69 + team.defence - team.injury_impact * 1.5))),
    ]
    return [
        {"name": name, "role": role, "status": "projected", "rating": round(rating, 2)}
        for name, (role, rating) in zip(names, base)
    ]


def _weather_context(fixture: dict) -> dict:
    live_weather = data_store.weather_for_fixture(fixture["id"])
    if live_weather:
        return {
            "temperature_c": live_weather["temperature_c"],
            "humidity_pct": live_weather["humidity_pct"],
            "wind_kph": live_weather["wind_kph"],
            "precipitation_mm": live_weather.get("precipitation_mm"),
            "condition": live_weather["condition"],
            "venue_effect": "reduced" if "indoor" in " ".join(fixture.get("context", {}).get("notes", [])) else "open-air",
            "source": live_weather["source"],
            "status": live_weather["status"],
            "captured_at": live_weather.get("captured_at"),
        }
    city_profiles = {
        "Mexico City": (22, 37, 8, "altitude"),
        "Inglewood": (20, 58, 11, "mild"),
        "East Rutherford": (24, 63, 13, "humid"),
        "Houston": (31, 72, 10, "indoor watch"),
        "Arlington": (29, 64, 12, "indoor watch"),
        "Atlanta": (28, 68, 9, "indoor watch"),
        "Toronto": (21, 55, 14, "cool"),
        "Vancouver": (19, 58, 12, "indoor watch"),
        "Santa Clara": (22, 52, 15, "dry"),
        "Seattle": (18, 62, 10, "cool"),
        "Philadelphia": (27, 66, 12, "humid"),
        "Boston": (23, 64, 13, "humid"),
        "Miami": (31, 74, 14, "heat"),
        "Kansas City": (29, 61, 16, "plains wind"),
        "Guadalajara": (27, 43, 10, "altitude-lite"),
        "Monterrey": (33, 58, 12, "heat"),
    }
    temperature, humidity, wind, tag = city_profiles.get(fixture["city"], (24, 58, 10, "normal"))
    return {
        "temperature_c": temperature,
        "humidity_pct": humidity,
        "wind_kph": wind,
        "precipitation_mm": None,
        "condition": tag,
        "venue_effect": "reduced" if "indoor" in " ".join(fixture.get("context", {}).get("notes", [])) else "open-air",
        "source": "climate seed fallback; refresh Open-Meteo for live forecast",
        "status": "fallback",
    }


def _tactical_match_profile(home, away, fixture: dict, context, live_status: dict | None = None) -> dict:
    home_profile = _tactical_profile(home, fixture, context.home_mult)
    away_profile = _tactical_profile(away, fixture, context.away_mult)
    if live_status:
        home_profile = _apply_live_stats(home_profile, live_status.get("home_stats") or {})
        away_profile = _apply_live_stats(away_profile, live_status.get("away_stats") or {})
    return {
        "home": home_profile,
        "away": away_profile,
        "source": (
            "ESPN public scoreboard basic stats + seed-derived xG/PPDA"
            if live_status and (live_status.get("home_stats") or live_status.get("away_stats"))
            else "48-team seed-derived process metrics; replace with event data backfill"
        ),
        "data_quality": (
            "mixed_live_public_proxy"
            if live_status and (live_status.get("home_stats") or live_status.get("away_stats"))
            else "proxy"
        ),
    }


def _event_predictions(home, away, fixture: dict, context, prediction: dict, live_status: dict | None) -> dict:
    home_profile = _tactical_profile(home, fixture, context.home_mult)
    away_profile = _tactical_profile(away, fixture, context.away_mult)
    has_live_stats = bool(live_status and (live_status.get("home_stats") or live_status.get("away_stats")))
    home_live_stats = (live_status or {}).get("home_stats") or {}
    away_live_stats = (live_status or {}).get("away_stats") or {}
    home_corners = _team_corner_expectation(home, away, home_profile, away_profile, context.home_mult)
    away_corners = _team_corner_expectation(away, home, away_profile, home_profile, context.away_mult)
    home_yellows = _team_yellow_expectation(home, away, home_profile, prediction["p_home"], prediction["p_away"])
    away_yellows = _team_yellow_expectation(away, home, away_profile, prediction["p_away"], prediction["p_home"])
    home_red = _red_card_probability(home_profile)
    away_red = _red_card_probability(away_profile)
    total_corners = home_corners + away_corners
    total_yellows = home_yellows + away_yellows
    return {
        "source": (
            "scoreline matrix + transparent cards/corners priors; ESPN public values when available"
        ),
        "data_quality": "mixed_live_public_proxy" if has_live_stats else "transparent_prior",
        "score": {
            "expected_home_goals": round(prediction["lambda_home"], 2),
            "expected_away_goals": round(prediction["lambda_away"], 2),
            "top_scorelines": prediction["top_scorelines"],
            "actual_home_score": (live_status or {}).get("home_score"),
            "actual_away_score": (live_status or {}).get("away_score"),
            "status": (live_status or {}).get("status_description") or (live_status or {}).get("status_state"),
        },
        "corners": {
            "home_expected": round(home_corners, 2),
            "away_expected": round(away_corners, 2),
            "total_expected": round(total_corners, 2),
            "over_8_5_probability": round(_poisson_over(total_corners, 8.5), 6),
            "over_9_5_probability": round(_poisson_over(total_corners, 9.5), 6),
            "live_home": home_live_stats.get("corners"),
            "live_away": away_live_stats.get("corners"),
        },
        "cards": {
            "home_yellow_expected": round(home_yellows, 2),
            "away_yellow_expected": round(away_yellows, 2),
            "total_yellow_expected": round(total_yellows, 2),
            "over_3_5_yellow_probability": round(_poisson_over(total_yellows, 3.5), 6),
            "over_4_5_yellow_probability": round(_poisson_over(total_yellows, 4.5), 6),
            "home_red_probability": round(home_red, 6),
            "away_red_probability": round(away_red, 6),
            "any_red_probability": round(1 - (1 - home_red) * (1 - away_red), 6),
            "live_home_yellow": home_live_stats.get("yellow_cards"),
            "live_away_yellow": away_live_stats.get("yellow_cards"),
            "live_home_red": home_live_stats.get("red_cards"),
            "live_away_red": away_live_stats.get("red_cards"),
        },
    }


def _team_corner_expectation(team, opponent, profile: dict, opponent_profile: dict, context_mult: float) -> float:
    attack_pressure = team.attack * 5.5 + team.form_index * 1.8
    shot_volume = (profile["shots_per_game"] - 10.5) * 0.18
    set_piece_bias = (profile["set_piece_xg_share"] - 0.22) * 5.0
    opponent_box_time = opponent.defence * -2.0 + opponent_profile["xga_per_game"] * 0.28
    context_edge = (context_mult - 1.0) * 7.0
    return _clamp(4.45 + attack_pressure + shot_volume + set_piece_bias + opponent_box_time + context_edge, 2.4, 8.4)


def _team_yellow_expectation(team, opponent, profile: dict, own_win_probability: float, opponent_win_probability: float) -> float:
    underdog_pressure = max(0.0, opponent_win_probability - own_win_probability) * 0.9
    defensive_load = opponent.attack * 1.3 - team.defence * 1.7
    fatigue = profile["environment_stress"] * 2.2
    return _clamp(profile["yellow_card_rate"] + underdog_pressure + defensive_load + fatigue, 0.8, 3.7)


def _red_card_probability(profile: dict) -> float:
    return _clamp(1 - math.exp(-profile["red_card_rate"]), 0.015, 0.24)


def _poisson_over(lam: float, line: float) -> float:
    threshold = math.floor(line) + 1
    return _clamp(1 - sum(poisson_pmf(k, lam) for k in range(threshold)), 0.0, 1.0)


def _tactical_profile(team, fixture: dict, context_mult: float) -> dict:
    xg = _xg_for(team)
    xga = _xg_against(team)
    possession = _clamp(50 + team.attack * 42 + team.defence * 12 + team.form_index * 28, 38, 67)
    shots = _clamp(10.8 + team.attack * 20 + team.form_index * 7, 7.2, 16.8)
    shot_accuracy = _clamp(0.34 + team.attack * 0.42 + team.form_index * 0.18, 0.25, 0.48)
    ppda = _clamp(12.8 - team.defence * 28 - team.form_index * 10 - team.attack * 6, 6.5, 18.0)
    press = _clamp(74 - ppda * 3.1 + team.form_index * 26 + team.defence * 80, 28, 92)
    set_piece_share = _clamp(0.22 + team.defence * 0.38 - team.attack * 0.08, 0.13, 0.34)
    travel_km = _projected_travel_km(team, fixture)
    return {
        "goals_scored_18m": round(_goals_for_18m(team), 1),
        "goals_conceded_18m": round(_goals_against_18m(team), 1),
        "xg_per_game": round(xg, 2),
        "xga_per_game": round(xga, 2),
        "shots_per_game": round(shots, 1),
        "shots_on_target_per_game": round(shots * shot_accuracy, 1),
        "shot_quality": round(xg / max(shots, 0.1), 3),
        "possession_pct": round(possession, 1),
        "ppda": round(ppda, 1),
        "press_intensity_idx": round(press, 1),
        "set_piece_xg_share": round(set_piece_share, 3),
        "yellow_card_rate": round(_clamp(1.65 - team.defence * 2.1 + max(0, -team.form_index) * 1.4, 0.8, 2.8), 2),
        "red_card_rate": round(_clamp(0.06 + max(0, -team.defence) * 0.22 + team.injury_impact * 1.1, 0.02, 0.22), 2),
        "squad_depth_score": round(_clamp(58 + (team.elo - 1600) / 9 + team.form_index * 45 - team.injury_impact * 360, 36, 92), 1),
        "projected_travel_km": travel_km,
        "travel_fatigue_level": _fatigue_level(travel_km),
        "environment_stress": round(_clamp(1 - context_mult, 0, 0.22), 3),
    }


def _apply_live_stats(profile: dict, stats: dict) -> dict:
    if not stats:
        return profile
    out = dict(profile)
    if stats.get("possession_pct") is not None:
        out["possession_pct"] = round(float(stats["possession_pct"]), 1)
    if stats.get("shots") is not None:
        out["shots_per_game"] = round(float(stats["shots"]), 1)
    if stats.get("shots_on_target") is not None:
        out["shots_on_target_per_game"] = round(float(stats["shots_on_target"]), 1)
    out["live_corners"] = stats.get("corners")
    out["live_fouls_committed"] = stats.get("fouls_committed")
    out["live_assists"] = stats.get("assists")
    out["live_goals"] = stats.get("goals")
    out["live_yellow_cards"] = stats.get("yellow_cards")
    out["live_red_cards"] = stats.get("red_cards")
    out["live_public_stats"] = True
    return out


def _matchup_profile(home, away, fixture: dict, context, prediction: dict, factor_breakdown: list[dict]) -> dict:
    home_tactical = _tactical_profile(home, fixture, context.home_mult)
    away_tactical = _tactical_profile(away, fixture, context.away_mult)
    favorite = home if prediction["p_home"] >= prediction["p_away"] else away
    underdog = away if favorite.id == home.id else home
    favorite_probability = max(prediction["p_home"], prediction["p_away"])
    underdog_probability = min(prediction["p_home"], prediction["p_away"])
    draw_pressure = prediction["p_draw"]
    set_piece_edge = home_tactical["set_piece_xg_share"] - away_tactical["set_piece_xg_share"]
    press_edge = home_tactical["press_intensity_idx"] - away_tactical["press_intensity_idx"]
    transition_edge = (home.attack - away.defence) - (away.attack - home.defence)
    rotation_gap = _availability_profile(home)["qdr_index"] - _availability_profile(away)["qdr_index"]
    upset_type = _upset_type(
        favorite,
        underdog,
        favorite_probability,
        underdog_probability,
        draw_pressure,
        set_piece_edge if underdog.id == home.id else -set_piece_edge,
        transition_edge if underdog.id == home.id else -transition_edge,
        fixture,
    )
    return {
        "style_clash": _style_clash(home_tactical, away_tactical),
        "tactical_edges": [
            {
                "name": "press_vs_buildup",
                "home_edge": round(_clamp(press_edge / 55, -1, 1), 3),
                "label": "高压对出球",
                "data_quality": "proxy",
                "category": "仅展示",
            },
            {
                "name": "set_piece_matchup",
                "home_edge": round(_clamp(set_piece_edge * 7, -1, 1), 3),
                "label": "定位球错位",
                "data_quality": "proxy",
                "category": "仅展示",
            },
            {
                "name": "transition_matchup",
                "home_edge": round(_clamp(transition_edge * 3.5, -1, 1), 3),
                "label": "转换进攻",
                "data_quality": "transparent_prior",
                "category": "透明先验",
            },
            {
                "name": "rotation_depth",
                "home_edge": round(_clamp(rotation_gap * 2, -1, 1), 3),
                "label": "轮换深度/QDR",
                "data_quality": "proxy_pending_player_feed",
                "category": "仅展示",
            },
        ],
        "upset_profile": upset_type,
        "favorite": favorite.name,
        "underdog": underdog.name,
        "favorite_probability": round(favorite_probability, 6),
        "underdog_probability": round(underdog_probability, 6),
        "draw_pressure": round(draw_pressure, 6),
        "model_dependency_note": "tactical edges are displayed as analysis until event data is connected; only transition prior overlaps with the score model inputs.",
    }


def _style_clash(home_profile: dict, away_profile: dict) -> str:
    if home_profile["press_intensity_idx"] - away_profile["press_intensity_idx"] > 12:
        return "主队高压压迫客队出球"
    if away_profile["press_intensity_idx"] - home_profile["press_intensity_idx"] > 12:
        return "客队高压压迫主队出球"
    if abs(home_profile["possession_pct"] - away_profile["possession_pct"]) >= 10:
        return "控球权倾斜，低控球方更依赖转换"
    if max(home_profile["set_piece_xg_share"], away_profile["set_piece_xg_share"]) >= 0.30:
        return "定位球权重偏高"
    return "风格接近，结果更依赖临场效率"


def _upset_type(
    favorite,
    underdog,
    favorite_probability: float,
    underdog_probability: float,
    draw_pressure: float,
    underdog_set_piece_edge: float,
    underdog_transition_edge: float,
    fixture: dict,
) -> dict:
    if favorite_probability < 0.42:
        label = "均势误差型"
        severity = "medium"
    elif underdog_probability >= 0.28:
        label = "实力接近型"
        severity = "medium"
    elif underdog_transition_edge > 0.06:
        label = "转换偷袭型"
        severity = "medium"
    elif underdog_set_piece_edge > 0.025:
        label = "定位球爆点型"
        severity = "medium"
    elif draw_pressure >= 0.30:
        label = "低比分拖入平局型"
        severity = "low"
    else:
        label = "低概率爆冷"
        severity = "low"
    if _projected_travel_km(favorite, fixture) - _projected_travel_km(underdog, fixture) > 1500:
        label = f"{label} / 旅程疲劳"
        severity = "medium"
    return {
        "label": label,
        "severity": severity,
        "favorite": favorite.name,
        "underdog": underdog.name,
        "upset_win_probability": round(underdog_probability, 6),
        "draw_probability": round(draw_pressure, 6),
    }


def _probability_intervals(prediction: dict, factor_breakdown: list[dict]) -> dict:
    proxy_count = sum(1 for row in factor_breakdown if row.get("category") in {"仅展示", "待接入"})
    pending_count = sum(1 for row in factor_breakdown if row.get("category") == "待接入")
    half_width = _clamp(0.035 + proxy_count * 0.009 + pending_count * 0.014, 0.04, 0.12)
    return {
        "method": "heuristic uncertainty band from missing live feeds and proxy inputs; not a calibrated Bayesian posterior yet",
        "home": _probability_band(prediction["p_home"], half_width),
        "draw": _probability_band(prediction["p_draw"], half_width * 0.8),
        "away": _probability_band(prediction["p_away"], half_width),
    }


def _probability_band(value: float, half_width: float) -> dict:
    return {
        "point": round(value, 6),
        "low": round(_clamp(value - half_width, 0.0, 1.0), 6),
        "high": round(_clamp(value + half_width, 0.0, 1.0), 6),
    }


def _risk_register(home, away, fixture: dict, prediction: dict, factor_breakdown: list[dict], matchup: dict) -> list[dict]:
    rows = []
    if any(row.get("category") == "待接入" for row in factor_breakdown):
        rows.append(
            {
                "key": "market_feed_missing",
                "severity": "high",
                "category": "待接入",
                "message": "真实亚洲让球盘口、closing line、CLV 仍需合法赔率 API。",
            }
        )
    if any(row.get("data_quality") == "proxy" for row in factor_breakdown):
        rows.append(
            {
                "key": "event_stats_proxy",
                "severity": "medium",
                "category": "仅展示",
                "message": "控球率、射门、PPDA、定位球和牌数目前是代理画像，不进入核心预测。",
            }
        )
    weather = _weather_context(fixture)
    if weather.get("status") == "forecast":
        rows.append(
            {
                "key": "weather_display_only",
                "severity": "low",
                "category": "仅展示",
                "message": "天气采用 Open-Meteo 快照展示；未作为 1X2 胜负因子。",
            }
        )
    if max(_projected_travel_km(home, fixture), _projected_travel_km(away, fixture)) >= 7000:
        rows.append(
            {
                "key": "travel_load",
                "severity": "medium",
                "category": "透明先验",
                "message": "存在较高旅程负荷，已用小权重进入进球修正。",
            }
        )
    if matchup["favorite_probability"] < 0.45 or prediction["p_draw"] > 0.31:
        rows.append(
            {
                "key": "wide_interval_match",
                "severity": "medium",
                "category": "透明先验",
                "message": "胜负分布较扁，爆冷/平局概率需要重点观察。",
            }
        )
    return rows


def _factor_breakdown(home, away, fixture: dict, context) -> list[dict]:
    elo_edge = max(-1, min(1, (home.elo - away.elo) / 240))
    attack_edge = max(-1, min(1, (home.attack - away.attack) * 4))
    defence_edge = max(-1, min(1, (home.defence - away.defence) * 4))
    form_edge = max(-1, min(1, (home.form_index - away.form_index) * 3))
    availability_edge = max(-1, min(1, (away.injury_impact - home.injury_impact) * 12))
    weather_edge = max(-1, min(1, (context.home_mult - context.away_mult) * 3))
    process_edge = max(-1, min(1, (_process_score(home) - _process_score(away)) / 24))
    history = data_store.historical_results_summary()
    weather = _weather_context(fixture)
    return [
        {
            "factor": "Rating prior",
            "home_edge": round(elo_edge, 3),
            "weight": 0.28,
            "used_in_model": True,
            "status": "rating_prior",
            "category": "透明先验",
            "backtest_status": "pending_walk_forward",
            "source": "team seed profile plus historical-form refresh",
            "data_quality": "transparent_prior",
        },
        {
            "factor": "Attack / defence prior",
            "home_edge": round((attack_edge + defence_edge) / 2, 3),
            "weight": 0.22,
            "used_in_model": True,
            "status": "rating_prior",
            "category": "透明先验",
            "backtest_status": "pending_walk_forward",
            "source": "team seed profile",
            "data_quality": "transparent_prior",
        },
        {
            "factor": "Recent results",
            "home_edge": round(form_edge, 3),
            "weight": 0.18,
            "used_in_model": True,
            "status": "verified_snapshot",
            "category": "透明先验",
            "backtest_status": "pending_walk_forward",
            "source": history.get("source", "martj42 international_results"),
            "data_quality": "public_results" if history.get("teams") else "seed_fallback",
        },
        {
            "factor": "Fixture / venue / travel",
            "home_edge": round(weather_edge, 3),
            "weight": 0.14,
            "used_in_model": True,
            "status": "used_in_context",
            "category": "透明先验",
            "backtest_status": "pending_walk_forward",
            "source": "public schedule, venue context and travel proxy",
            "data_quality": "public_schedule",
        },
        {
            "factor": "Weather forecast",
            "home_edge": 0.0,
            "weight": 0.0,
            "used_in_model": False,
            "status": weather["status"],
            "category": "仅展示",
            "backtest_status": "not_promoted_to_1x2",
            "source": weather["source"],
            "data_quality": "live_forecast" if weather["status"] == "forecast" else "fallback_climate",
        },
        {
            "factor": "Squad availability prior",
            "home_edge": round(availability_edge, 3),
            "weight": 0.10,
            "used_in_model": True,
            "status": "seed_prior_pending_injury_feed",
            "category": "透明先验",
            "backtest_status": "pending_live_injury_feed",
            "source": "seed injury-impact prior; live injury API not connected",
            "data_quality": "transparent_prior",
        },
        {
            "factor": "Technical process metrics",
            "home_edge": round(process_edge, 3),
            "weight": 0.0,
            "used_in_model": False,
            "status": "display_proxy_only",
            "category": "仅展示",
            "backtest_status": "pending_event_data",
            "source": "seed-derived possession, shots, xG, PPDA and card estimates",
            "data_quality": "proxy",
        },
        {
            "factor": "Legal AH market / closing line",
            "home_edge": 0.0,
            "weight": 0.0,
            "used_in_model": False,
            "status": "pending_legal_odds_api",
            "category": "待接入",
            "backtest_status": "blocked_without_closing_line",
            "source": "requires licensed sportsbook odds provider",
            "data_quality": "missing",
        },
    ]


def _model_adjustments(home, away, fixture: dict, context, factor_breakdown: list[dict]) -> MatchAdjustments:
    edges = {row["factor"]: row["home_edge"] for row in factor_breakdown}
    contextual_edge = (
        edges["Fixture / venue / travel"] * 0.55
        + edges["Squad availability prior"] * 0.25
        + edges["Recent results"] * 0.20
    )
    home_fatigue = _fatigue_goal_multiplier(home, fixture)
    away_fatigue = _fatigue_goal_multiplier(away, fixture)
    home_goal_mult = _clamp(math.exp(0.30 * contextual_edge) * home_fatigue, 0.78, 1.24)
    away_goal_mult = _clamp(math.exp(-0.30 * contextual_edge) * away_fatigue, 0.78, 1.24)
    total_goal_mult = 1.0
    return MatchAdjustments(
        home_goal_mult=home_goal_mult,
        away_goal_mult=away_goal_mult,
        total_goal_mult=total_goal_mult,
    )


def _model_input_summary(adjustments: MatchAdjustments, factor_breakdown: list[dict]) -> dict:
    weighted_context_edge = sum(
        row["home_edge"] * row["weight"]
        for row in factor_breakdown
        if row.get("used_in_model")
    )
    return {
        "weighted_context_edge": round(weighted_context_edge, 3),
        "home_goal_multiplier": round(adjustments.home_goal_mult, 3),
        "away_goal_multiplier": round(adjustments.away_goal_mult, 3),
        "total_goal_multiplier": round(adjustments.total_goal_mult, 3),
        "applied_to": "expected goals before scoreline and handicap probability generation",
        "proxy_metrics_policy": "technical process metrics are displayed but not used until event-data backfill is connected",
    }


def _xg_for(team) -> float:
    return _clamp(1.35 + team.attack * 2.4 + team.form_index * 0.5, 0.75, 2.35)


def _xg_against(team) -> float:
    return _clamp(1.18 - team.defence * 2.0 + team.injury_impact * 1.8, 0.65, 2.2)


def _goals_for_18m(team) -> float:
    return _clamp(13.2 + team.attack * 42 + team.form_index * 9, 5.5, 29.0)


def _goals_against_18m(team) -> float:
    return _clamp(10.8 - team.defence * 34 + team.injury_impact * 24, 4.5, 23.0)


def _process_score(team) -> float:
    return (
        _xg_for(team) * 7
        - _xg_against(team) * 5
        + (55 - _clamp(12.8 - team.defence * 28 - team.form_index * 10 - team.attack * 6, 6.5, 18.0)) * 0.22
        + team.form_index * 18
    )


def _press_score(team) -> float:
    return _clamp(74 - _ppda(team) * 3.1 + team.form_index * 26 + team.defence * 80, 28, 92)


def _ppda(team) -> float:
    return _clamp(12.8 - team.defence * 28 - team.form_index * 10 - team.attack * 6, 6.5, 18.0)


def _fatigue_goal_multiplier(team, fixture: dict) -> float:
    travel_km = _projected_travel_km(team, fixture)
    travel_drag = max(0, travel_km - 5200) / 36000
    injury_drag = team.injury_impact * 1.8
    return _clamp(1 - travel_drag - injury_drag, 0.86, 1.02)


def _projected_travel_km(team, fixture: dict) -> int:
    host_baseline = {"mex": 1400, "usa": 1800, "can": 2200}
    if team.id in host_baseline:
        return host_baseline[team.id]
    city_load = {
        "Mexico City": 7800,
        "Inglewood": 6100,
        "East Rutherford": 5200,
        "Houston": 5600,
        "Arlington": 5900,
        "Atlanta": 5400,
        "Toronto": 4700,
        "Vancouver": 6100,
        "Santa Clara": 6500,
        "Seattle": 5900,
        "Philadelphia": 5200,
        "Boston": 5000,
        "Miami": 5700,
        "Kansas City": 5900,
        "Guadalajara": 7600,
        "Monterrey": 7300,
    }
    return int(city_load.get(fixture["city"], 5600) + max(0, 1700 - team.elo) * 3)


def _fatigue_level(travel_km: int) -> str:
    if travel_km >= 7600:
        return "very_high"
    if travel_km >= 6000:
        return "high"
    if travel_km >= 3800:
        return "medium"
    return "low"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
