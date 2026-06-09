"""Asian handicap settlement and fair-odds calculations.

All handicap probabilities are derived from the model scoreline distribution.
The input line is from the side being evaluated: home -0.5 means the home team
must win by one or more; away +0.5 means the away side can draw or win.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import isfinite
from typing import Iterable, Literal

Settlement = Literal["win", "half_win", "push", "half_loss", "loss"]


def _line_fraction(line: float | int | str) -> Fraction:
    value = Fraction(str(line)).limit_denominator(4)
    if value * 4 != int(value * 4):
        raise ValueError(f"Asian handicap line must be a quarter-goal increment: {line}")
    return value


def split_asian_line(line: float | int | str) -> tuple[Fraction, ...]:
    """Split quarter lines into two half-stake lines.

    Examples:
      -0.25 -> (0, -0.5)
      -0.75 -> (-0.5, -1)
      +0.25 -> (0, +0.5)
    """
    value = _line_fraction(line)
    if (value * 2).denominator == 1:
        return (value,)

    lower_half = Fraction((value * 2).numerator // (value * 2).denominator, 2)
    upper_half = lower_half + Fraction(1, 2)
    return tuple(sorted((lower_half, upper_half), reverse=True))


def settle_subline(margin: int, line: float | int | str | Fraction) -> Literal["win", "push", "loss"]:
    adjusted = Fraction(margin) + (line if isinstance(line, Fraction) else _line_fraction(line))
    if adjusted > 0:
        return "win"
    if adjusted == 0:
        return "push"
    return "loss"


def settle_asian_margin(margin: int, line: float | int | str) -> Settlement:
    results = [settle_subline(margin, subline) for subline in split_asian_line(line)]
    if len(results) == 1:
        return results[0]
    wins = results.count("win")
    pushes = results.count("push")
    losses = results.count("loss")
    if wins == 2:
        return "win"
    if losses == 2:
        return "loss"
    if pushes == 2:
        return "push"
    if wins and pushes:
        return "half_win"
    if losses and pushes:
        return "half_loss"
    return "push"


@dataclass(frozen=True)
class AsianHandicapProbabilities:
    win: float = 0.0
    half_win: float = 0.0
    push: float = 0.0
    half_loss: float = 0.0
    loss: float = 0.0

    @property
    def total(self) -> float:
        return self.win + self.half_win + self.push + self.half_loss + self.loss

    @property
    def positive_probability(self) -> float:
        return self.win + self.half_win

    @property
    def effective_win_probability(self) -> float:
        return self.win + 0.5 * self.half_win

    @property
    def effective_loss_probability(self) -> float:
        return self.loss + 0.5 * self.half_loss

    @property
    def fair_decimal_odds(self) -> float | None:
        """Fair decimal odds accounting for pushes and half settlements."""
        denom = self.effective_win_probability
        if denom <= 0:
            return None
        return 1.0 + self.effective_loss_probability / denom

    def expected_return(self, decimal_odds: float | None) -> float | None:
        if decimal_odds is None or decimal_odds <= 1 or not isfinite(decimal_odds):
            return None
        payout = decimal_odds - 1.0
        return (
            self.win * payout
            + self.half_win * payout * 0.5
            - self.half_loss * 0.5
            - self.loss
        )

    def as_dict(self) -> dict[str, float | None]:
        return {
            "win": round(self.win, 6),
            "half_win": round(self.half_win, 6),
            "push": round(self.push, 6),
            "half_loss": round(self.half_loss, 6),
            "loss": round(self.loss, 6),
            "positive_probability": round(self.positive_probability, 6),
            "effective_win_probability": round(self.effective_win_probability, 6),
            "fair_decimal_odds": (
                round(self.fair_decimal_odds, 4) if self.fair_decimal_odds is not None else None
            ),
        }


def _with(probabilities: AsianHandicapProbabilities, settlement: Settlement, amount: float):
    values = probabilities.__dict__.copy()
    values[settlement] += amount
    return AsianHandicapProbabilities(**values)


def asian_handicap_probabilities(
    scoreline_matrix: Iterable[Iterable[float]],
    line: float | int | str,
) -> AsianHandicapProbabilities:
    probs = AsianHandicapProbabilities()
    for home_goals, row in enumerate(scoreline_matrix):
        for away_goals, probability in enumerate(row):
            if probability <= 0:
                continue
            margin = home_goals - away_goals
            probs = _with(probs, settle_asian_margin(margin, line), float(probability))
    total = probs.total
    if total <= 0:
        return probs
    return AsianHandicapProbabilities(
        win=probs.win / total,
        half_win=probs.half_win / total,
        push=probs.push / total,
        half_loss=probs.half_loss / total,
        loss=probs.loss / total,
    )


def asian_market_from_matrix(
    scoreline_matrix: Iterable[Iterable[float]],
    home_line: float | int | str,
    market_home_odds: float | None = None,
    market_away_odds: float | None = None,
) -> dict:
    home_probs = asian_handicap_probabilities(scoreline_matrix, home_line)
    away_probs = asian_handicap_probabilities(
        _transpose_for_away(scoreline_matrix),
        -float(home_line),
    )
    home_return = home_probs.expected_return(market_home_odds)
    away_return = away_probs.expected_return(market_away_odds)
    return {
        "line": float(home_line),
        "home": {
            **home_probs.as_dict(),
            "market_decimal_odds": market_home_odds,
            "expected_return": round(home_return, 4) if home_return is not None else None,
        },
        "away": {
            **away_probs.as_dict(),
            "market_decimal_odds": market_away_odds,
            "expected_return": round(away_return, 4) if away_return is not None else None,
        },
    }


def _transpose_for_away(scoreline_matrix: Iterable[Iterable[float]]) -> list[list[float]]:
    matrix = [list(row) for row in scoreline_matrix]
    return [list(row) for row in zip(*matrix)]

