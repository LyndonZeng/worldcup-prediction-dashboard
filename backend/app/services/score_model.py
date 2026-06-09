"""Small, transparent football score model used by the API and dashboard.

This is intentionally modest for v1: team priors generate expected goals, then
every downstream market is derived from the scoreline distribution.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class TeamProfile:
    id: str
    name: str
    group: str
    fifa_code: str
    flag_code: str
    elo: float
    attack: float
    defence: float
    form_index: float = 0.0
    injury_impact: float = 0.0


@dataclass(frozen=True)
class MatchContext:
    home_mult: float = 1.0
    away_mult: float = 1.0
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class MatchAdjustments:
    home_goal_mult: float = 1.0
    away_goal_mult: float = 1.0
    total_goal_mult: float = 1.0


def poisson_pmf(k: int, lam: float) -> float:
    return math.exp(-lam) * (lam**k) / math.factorial(k)


def expected_goals(
    home: TeamProfile,
    away: TeamProfile,
    context: MatchContext | None = None,
    adjustments: MatchAdjustments | None = None,
) -> tuple[float, float]:
    context = context or MatchContext()
    adjustments = adjustments or MatchAdjustments()
    elo_term = (home.elo - away.elo) / 720.0
    home_quality = home.attack - away.defence + 0.11 * home.form_index - home.injury_impact
    away_quality = away.attack - home.defence + 0.11 * away.form_index - away.injury_impact
    lambda_home = math.exp(math.log(1.26) + 0.34 * elo_term + home_quality) * context.home_mult
    lambda_away = math.exp(math.log(1.05) - 0.34 * elo_term + away_quality) * context.away_mult
    lambda_home *= adjustments.home_goal_mult * adjustments.total_goal_mult
    lambda_away *= adjustments.away_goal_mult * adjustments.total_goal_mult
    return max(0.08, min(lambda_home, 4.5)), max(0.08, min(lambda_away, 4.5))


def scoreline_matrix(lambda_home: float, lambda_away: float, max_goals: int = 8) -> list[list[float]]:
    home_probs = [poisson_pmf(i, lambda_home) for i in range(max_goals + 1)]
    away_probs = [poisson_pmf(i, lambda_away) for i in range(max_goals + 1)]
    matrix = [[h * a for a in away_probs] for h in home_probs]
    total = sum(sum(row) for row in matrix)
    return [[p / total for p in row] for row in matrix]


def match_market_probabilities(matrix: Iterable[Iterable[float]]) -> dict:
    rows = [list(row) for row in matrix]
    p_home = p_draw = p_away = p_over_25 = p_btts = 0.0
    top_scores: list[tuple[str, float]] = []
    for home_goals, row in enumerate(rows):
        for away_goals, probability in enumerate(row):
            if home_goals > away_goals:
                p_home += probability
            elif home_goals == away_goals:
                p_draw += probability
            else:
                p_away += probability
            if home_goals + away_goals >= 3:
                p_over_25 += probability
            if home_goals > 0 and away_goals > 0:
                p_btts += probability
            top_scores.append((f"{home_goals}-{away_goals}", probability))
    top_scores.sort(key=lambda item: item[1], reverse=True)
    return {
        "p_home": round(p_home, 6),
        "p_draw": round(p_draw, 6),
        "p_away": round(p_away, 6),
        "p_over_2_5": round(p_over_25, 6),
        "p_under_2_5": round(1 - p_over_25, 6),
        "p_btts": round(p_btts, 6),
        "top_scorelines": [
            {"score": score, "probability": round(probability, 6)}
            for score, probability in top_scores[:6]
        ],
    }


def predict_match(
    home: TeamProfile,
    away: TeamProfile,
    context: MatchContext | None = None,
    adjustments: MatchAdjustments | None = None,
) -> dict:
    lambda_home, lambda_away = expected_goals(home, away, context, adjustments)
    matrix = scoreline_matrix(lambda_home, lambda_away)
    markets = match_market_probabilities(matrix)
    return {
        "lambda_home": round(lambda_home, 4),
        "lambda_away": round(lambda_away, 4),
        "scoreline_matrix": matrix,
        **markets,
    }
