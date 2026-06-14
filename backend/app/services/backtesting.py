"""Prediction snapshot, closing-line, and MVP backtest helpers."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any

from .handicap import settle_asian_margin
from .score_model import dixon_coles_scoreline_matrix, match_market_probabilities

EDGE_THRESHOLD = 0.035
LOCK_BUFFER_MINUTES = 5
CLOSING_WINDOW_MINUTES = 10


def build_model_prediction_snapshots(matches: list[dict], sources: list[dict] | None = None) -> list[dict]:
    generated_at = datetime.now(timezone.utc).isoformat()
    source_versions = {
        row["source"]: row.get("freshness") or row.get("status")
        for row in (sources or [])
    }
    rows = []
    for match in matches:
        kickoff = _parse_dt(match["fixture"]["kickoff_utc"])
        lock_dt = _parse_dt(generated_at)
        is_pre_kickoff = lock_dt <= kickoff - timedelta(minutes=LOCK_BUFFER_MINUTES)
        lock_status = "eligible_pre_kickoff" if is_pre_kickoff else "excluded_post_kickoff"
        rows.append(
            {
                "prediction_id": f'{match["match_id"]}-{_compact_time(generated_at)}',
                "match_id": match["match_id"],
                "generated_at": generated_at,
                "model_version": match.get("model_version"),
                "lock_status": lock_status,
                "kickoff_utc": match["fixture"]["kickoff_utc"],
                "p_home": match["p_home"],
                "p_draw": match["p_draw"],
                "p_away": match["p_away"],
                "p_over_2_5": match["p_over_2_5"],
                "p_btts": match["p_btts"],
                "handicap_probabilities": _snapshot_handicaps(match),
                "event_probabilities": {
                    "corners": match.get("event_predictions", {}).get("corners", {}),
                    "cards": match.get("event_predictions", {}).get("cards", {}),
                },
                "data_source_versions": source_versions,
            }
        )
    return rows


def build_closing_line_snapshots(fixtures: list[dict], odds_rows: list[dict]) -> list[dict]:
    fixture_by_id = {fixture["id"]: fixture for fixture in fixtures}
    latest_by_key: dict[tuple[Any, ...], dict] = {}
    for row in odds_rows:
        key = (
            row.get("match_id"),
            row.get("bookmaker"),
            row.get("market_type"),
            row.get("line"),
        )
        previous = latest_by_key.get(key)
        if previous is None or str(row.get("captured_at") or "") > str(previous.get("captured_at") or ""):
            latest_by_key[key] = row

    snapshots = []
    for row in latest_by_key.values():
        fixture = fixture_by_id.get(row["match_id"])
        if not fixture:
            continue
        kickoff = _parse_dt(fixture["kickoff_utc"])
        captured = _parse_dt(row["captured_at"])
        minutes_to_kickoff = (kickoff - captured).total_seconds() / 60
        is_closing = 0 <= minutes_to_kickoff <= CLOSING_WINDOW_MINUTES
        snapshots.append(
            {
                **row,
                "snapshot_id": _snapshot_id(row),
                "kickoff_utc": fixture["kickoff_utc"],
                "minutes_to_kickoff": round(minutes_to_kickoff, 2),
                "is_closing_line": is_closing,
                "snapshot_role": "closing_line" if is_closing else "latest_market_snapshot",
                "closing_window_minutes": CLOSING_WINDOW_MINUTES,
            }
        )
    return sorted(
        snapshots,
        key=lambda row: (row["match_id"], row["market_type"], row.get("line") or 0, row["bookmaker"]),
    )


def build_backtest_report(
    matches: list[dict],
    model_snapshots: list[dict],
    closing_snapshots: list[dict],
) -> dict:
    completed = [match for match in matches if _completed_score(match) is not None]
    locked_by_match = {
        row["match_id"]: row
        for row in model_snapshots
        if row.get("lock_status") == "eligible_pre_kickoff"
    }
    closing_lines = [row for row in closing_snapshots if row.get("is_closing_line")]
    formal_matches = [
        match
        for match in completed
        if match["match_id"] in locked_by_match
    ]
    formal_1x2 = _one_x_two_metrics(formal_matches, locked_by_match)
    shadow_snapshots = {match["match_id"]: _shadow_snapshot(match) for match in completed}
    shadow_1x2 = _one_x_two_metrics(completed, shadow_snapshots)
    ah_report = _asian_handicap_report(formal_matches, locked_by_match, closing_snapshots)
    ou_report = _over_under_report(formal_matches, locked_by_match)
    corners_report = _corners_report(formal_matches, locked_by_match)
    shadow_ah_report = _asian_handicap_report(completed, shadow_snapshots, closing_snapshots)
    shadow_ou_report = _over_under_report(completed, shadow_snapshots)
    shadow_corners_report = _corners_report(completed, shadow_snapshots)
    model_comparison = _model_comparison_report(completed)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "mvp_shadow_until_locked_closing_samples",
        "method": "Formal samples require pre-kickoff model snapshots and closing lines; shadow audit is not leak-safe.",
        "snapshot_counts": {
            "model_prediction_snapshots": len(model_snapshots),
            "eligible_pre_kickoff_predictions": len(locked_by_match),
            "closing_line_snapshots": len(closing_snapshots),
            "true_closing_lines": len(closing_lines),
            "settled_matches": len(completed),
        },
        "formal": {
            "eligible_samples": len(formal_matches),
            "one_x_two": formal_1x2,
            "asian_handicap": ah_report,
            "over_under": ou_report,
            "corners": corners_report,
            "notes": [
                "No sample is counted unless the prediction was locked before kickoff.",
                "CLV is only calculated against a snapshot captured inside the configured closing window.",
            ],
        },
        "shadow": {
            "label": "公式烟测，不作为专业模型成绩",
            "one_x_two": shadow_1x2,
            "asian_handicap": shadow_ah_report,
            "over_under": shadow_ou_report,
            "corners": shadow_corners_report,
        },
        "model_comparison": model_comparison,
        "factor_gate": _factor_gate_summary(matches),
        "requirements_to_claim_professional": [
            "Hundreds of locked pre-match predictions",
            "Closing snapshots within 5-10 minutes of kickoff",
            "Positive CLV over meaningful samples",
            "Stable Brier/log-loss calibration by market type",
        ],
    }


def _model_comparison_report(matches: list[dict]) -> dict:
    if not matches:
        return {
            "status": "pending_settled_samples",
            "samples": 0,
            "baseline": _empty_probability_metrics(),
            "dixon_coles": _empty_probability_metrics(),
            "decision": "keep_poisson_baseline",
        }
    baseline_rows = []
    dixon_rows = []
    for match in matches:
        actual_index = _one_x_two_actual_index(match)
        baseline_rows.append(
            {
                "probs": [match["p_home"], match["p_draw"], match["p_away"]],
                "actual_index": actual_index,
            }
        )
        dc = match_market_probabilities(
            dixon_coles_scoreline_matrix(
                float(match["lambda_home"]),
                float(match["lambda_away"]),
                rho=-0.06,
            )
        )
        dixon_rows.append(
            {
                "probs": [dc["p_home"], dc["p_draw"], dc["p_away"]],
                "actual_index": actual_index,
            }
        )
    baseline = _probability_rows_metrics(baseline_rows)
    dixon_coles = _probability_rows_metrics(dixon_rows)
    delta_log_loss = None
    if baseline["log_loss"] is not None and dixon_coles["log_loss"] is not None:
        delta_log_loss = round(dixon_coles["log_loss"] - baseline["log_loss"], 6)
    decision = "promote_candidate_after_more_samples" if delta_log_loss is not None and delta_log_loss < -0.015 and len(matches) >= 40 else "keep_poisson_baseline"
    return {
        "status": "shadow_parallel_evaluation",
        "samples": len(matches),
        "baseline": {
            "name": "Poisson baseline",
            **baseline,
        },
        "dixon_coles": {
            "name": "Dixon-Coles low-score adjustment",
            "rho": -0.06,
            **dixon_coles,
        },
        "delta_log_loss": delta_log_loss,
        "decision": decision,
        "promotion_rule": "Only promote when walk-forward samples are meaningful and log-loss/Brier improve versus baseline.",
    }


def _factor_gate_summary(matches: list[dict]) -> dict:
    buckets: dict[str, dict] = {}
    for match in matches:
        for factor in match.get("factor_breakdown", []):
            category = factor.get("category") or "未分级"
            bucket = buckets.setdefault(
                category,
                {
                    "factors": set(),
                    "used_in_model": 0,
                    "display_only": 0,
                    "proxy": 0,
                },
            )
            bucket["factors"].add(factor.get("factor") or "unknown")
            if factor.get("used_in_model"):
                bucket["used_in_model"] += 1
            else:
                bucket["display_only"] += 1
            if factor.get("data_quality") == "proxy":
                bucket["proxy"] += 1
    return {
        "status": "active_transparency_gate",
        "policy": "Only backtested factors can raise core model weight; proxy factors stay display-only or receive a confidence penalty.",
        "categories": [
            {
                "category": category,
                "factor_count": len(bucket["factors"]),
                "used_in_model_rows": bucket["used_in_model"],
                "display_only_rows": bucket["display_only"],
                "proxy_rows": bucket["proxy"],
            }
            for category, bucket in sorted(buckets.items())
        ],
    }


def _shadow_snapshot(match: dict) -> dict:
    return {
        "match_id": match["match_id"],
        "p_home": match["p_home"],
        "p_draw": match["p_draw"],
        "p_away": match["p_away"],
        "p_over_2_5": match["p_over_2_5"],
        "handicap_probabilities": _snapshot_handicaps(match),
        "event_probabilities": {
            "corners": match.get("event_predictions", {}).get("corners", {}),
            "cards": match.get("event_predictions", {}).get("cards", {}),
        },
        "lock_status": "shadow_current_model",
    }


def _snapshot_handicaps(match: dict) -> list[dict]:
    rows = []
    for row in match.get("handicap_preview", []):
        rows.append(
            {
                "line": row["line"],
                "source": row.get("source"),
                "captured_at": row.get("captured_at"),
                "market_status": row.get("market_status"),
                "home": {
                    "positive_probability": row["home"].get("positive_probability"),
                    "fair_decimal_odds": row["home"].get("fair_decimal_odds"),
                    "market_decimal_odds": row["home"].get("market_decimal_odds"),
                    "expected_return": row["home"].get("expected_return"),
                },
                "away": {
                    "positive_probability": row["away"].get("positive_probability"),
                    "fair_decimal_odds": row["away"].get("fair_decimal_odds"),
                    "market_decimal_odds": row["away"].get("market_decimal_odds"),
                    "expected_return": row["away"].get("expected_return"),
                },
            }
        )
    return rows


def _one_x_two_metrics(matches: list[dict], snapshots: dict[str, dict]) -> dict:
    if not matches:
        return _empty_probability_metrics()
    hits = 0
    brier_values = []
    log_values = []
    for match in matches:
        snapshot = snapshots[match["match_id"]]
        probs = [snapshot["p_home"], snapshot["p_draw"], snapshot["p_away"]]
        actual_index = _one_x_two_actual_index(match)
        predicted_index = max(range(3), key=lambda index: probs[index])
        hits += int(predicted_index == actual_index)
        actual = [0.0, 0.0, 0.0]
        actual[actual_index] = 1.0
        brier_values.append(sum((prob - outcome) ** 2 for prob, outcome in zip(probs, actual)) / 3)
        log_values.append(-math.log(max(1e-12, probs[actual_index])))
    return {
        "samples": len(matches),
        "hit_rate": round(hits / len(matches), 6),
        "correct": hits,
        "brier": round(mean(brier_values), 6),
        "log_loss": round(mean(log_values), 6),
    }


def _probability_rows_metrics(rows: list[dict]) -> dict:
    if not rows:
        return _empty_probability_metrics()
    hits = 0
    brier_values = []
    log_values = []
    for row in rows:
        probs = row["probs"]
        actual_index = row["actual_index"]
        predicted_index = max(range(len(probs)), key=lambda index: probs[index])
        hits += int(predicted_index == actual_index)
        actual = [0.0 for _ in probs]
        actual[actual_index] = 1.0
        brier_values.append(sum((prob - outcome) ** 2 for prob, outcome in zip(probs, actual)) / len(probs))
        log_values.append(-math.log(max(1e-12, probs[actual_index])))
    return {
        "samples": len(rows),
        "hit_rate": round(hits / len(rows), 6),
        "correct": hits,
        "brier": round(mean(brier_values), 6),
        "log_loss": round(mean(log_values), 6),
    }


def _asian_handicap_report(
    matches: list[dict],
    snapshots: dict[str, dict],
    closing_snapshots: list[dict],
) -> dict:
    selections = []
    for match in matches:
        snapshot = snapshots[match["match_id"]]
        score = _completed_score(match)
        if score is None:
            continue
        for handicap in snapshot.get("handicap_probabilities", []):
            for side in ["home", "away"]:
                expected_return = handicap[side].get("expected_return")
                odds = handicap[side].get("market_decimal_odds")
                if expected_return is None or odds is None or expected_return < EDGE_THRESHOLD:
                    continue
                home_line = float(handicap["line"])
                side_line = home_line if side == "home" else -home_line
                margin = score[0] - score[1] if side == "home" else score[1] - score[0]
                settlement = settle_asian_margin(margin, side_line)
                profit = _asian_profit(settlement, odds)
                closing = _closing_for_selection(
                    closing_snapshots,
                    match["match_id"],
                    "asian_handicap",
                    home_line,
                    side,
                )
                closing_odds = closing.get("price_home" if side == "home" else "price_away") if closing else None
                selections.append(
                    {
                        "match_id": match["match_id"],
                        "side": side,
                        "line": side_line,
                        "entry_odds": odds,
                        "closing_odds": closing_odds,
                        "clv": _clv(odds, closing_odds),
                        "settlement": settlement,
                        "profit": profit,
                    }
                )
    if not selections:
        return {
            "selections": 0,
            "roi": None,
            "hit_rate": None,
            "average_clv": None,
            "unit_profit": 0,
            "correct": 0,
            "pushes": 0,
        }
    positive = [row for row in selections if row["settlement"] in {"win", "half_win"}]
    pushes = [row for row in selections if row["settlement"] == "push"]
    clv_values = [row["clv"] for row in selections if row["clv"] is not None]
    unit_profit = sum(row["profit"] for row in selections)
    return {
        "selections": len(selections),
        "roi": round(unit_profit / len(selections), 6),
        "hit_rate": round(len(positive) / len(selections), 6),
        "average_clv": round(mean(clv_values), 6) if clv_values else None,
        "unit_profit": round(unit_profit, 6),
        "correct": len(positive),
        "pushes": len(pushes),
    }


def _over_under_report(matches: list[dict], snapshots: dict[str, dict]) -> dict:
    if not matches:
        return _empty_probability_metrics()
    brier_values = []
    log_values = []
    hits = 0
    for match in matches:
        snapshot = snapshots[match["match_id"]]
        score = _completed_score(match)
        if score is None:
            continue
        over = float(snapshot["p_over_2_5"])
        actual_over = 1.0 if score[0] + score[1] > 2.5 else 0.0
        predicted_over = over >= 0.5
        hits += int(predicted_over == bool(actual_over))
        brier_values.append((over - actual_over) ** 2)
        log_values.append(-math.log(max(1e-12, over if actual_over else 1 - over)))
    samples = len(brier_values)
    if not samples:
        return _empty_probability_metrics()
    return {
        "samples": samples,
        "hit_rate": round(hits / samples, 6),
        "correct": hits,
        "brier": round(mean(brier_values), 6),
        "log_loss": round(mean(log_values), 6),
    }


def _corners_report(matches: list[dict], snapshots: dict[str, dict]) -> dict:
    selections = []
    actual_event_samples = 0
    for match in matches:
        actual_total = _actual_total_corners(match)
        if actual_total is None:
            continue
        actual_event_samples += 1
        snapshot = snapshots[match["match_id"]]
        selection = _corner_selection(snapshot.get("event_probabilities", {}).get("corners", {}))
        if selection is None:
            continue
        won = _corner_won(actual_total, selection["side"], selection["line"])
        selections.append(
            {
                "match_id": match["match_id"],
                "side": selection["side"],
                "line": selection["line"],
                "probability": selection["probability"],
                "actual_total": actual_total,
                "won": won,
            }
        )
    if not selections:
        return {
            "actual_event_samples": actual_event_samples,
            "selections": 0,
            "hit_rate": None,
            "correct": 0,
            "line_summary": {},
        }
    correct = sum(1 for row in selections if row["won"])
    return {
        "actual_event_samples": actual_event_samples,
        "selections": len(selections),
        "hit_rate": round(correct / len(selections), 6),
        "correct": correct,
        "line_summary": _corner_line_summary(selections),
    }


def _corner_selection(corners: dict) -> dict | None:
    over_85 = _safe_float(corners.get("over_8_5_probability"))
    over_95 = _safe_float(corners.get("over_9_5_probability"))
    if over_95 is not None and over_95 >= 0.56:
        return {"side": "over", "line": 9.5, "probability": over_95}
    if over_85 is not None and over_85 >= 0.56:
        return {"side": "over", "line": 8.5, "probability": over_85}
    if over_85 is not None and over_85 <= 0.44:
        return {"side": "under", "line": 8.5, "probability": 1 - over_85}
    return None


def _corner_won(total: int, side: str, line: float) -> bool:
    return total > line if side == "over" else total < line


def _corner_line_summary(selections: list[dict]) -> dict:
    summary: dict[str, dict] = {}
    for row in selections:
        key = f'{row["side"]}_{row["line"]}'
        bucket = summary.setdefault(key, {"selections": 0, "correct": 0, "hit_rate": None})
        bucket["selections"] += 1
        bucket["correct"] += int(row["won"])
    for bucket in summary.values():
        bucket["hit_rate"] = round(bucket["correct"] / bucket["selections"], 6)
    return summary


def _closing_for_selection(
    closing_snapshots: list[dict],
    match_id: str,
    market_type: str,
    home_line: float,
    side: str,
) -> dict | None:
    candidates = [
        row
        for row in closing_snapshots
        if row.get("is_closing_line")
        and row.get("match_id") == match_id
        and row.get("market_type") == market_type
        and float(row.get("line") or 0) == float(home_line)
        and row.get("price_home" if side == "home" else "price_away")
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda row: row.get("captured_at") or "", reverse=True)[0]


def _empty_probability_metrics() -> dict:
    return {
        "samples": 0,
        "hit_rate": None,
        "correct": 0,
        "brier": None,
        "log_loss": None,
    }


def _completed_score(match: dict) -> tuple[int, int] | None:
    live = match.get("live_status") or {}
    if not live.get("completed"):
        return None
    home = live.get("home_score")
    away = live.get("away_score")
    if home is None or away is None:
        return None
    return int(home), int(away)


def _actual_total_corners(match: dict) -> int | None:
    corners = match.get("event_predictions", {}).get("corners", {})
    home = corners.get("live_home")
    away = corners.get("live_away")
    if home is None or away is None:
        live = match.get("live_status") or {}
        home = (live.get("home_stats") or {}).get("corners")
        away = (live.get("away_stats") or {}).get("corners")
    if home is None or away is None:
        return None
    return int(home) + int(away)


def _one_x_two_actual_index(match: dict) -> int:
    home_score, away_score = _completed_score(match) or (0, 0)
    if home_score > away_score:
        return 0
    if home_score == away_score:
        return 1
    return 2


def _asian_profit(settlement: str, odds: float) -> float:
    if settlement == "win":
        return odds - 1
    if settlement == "half_win":
        return (odds - 1) * 0.5
    if settlement == "push":
        return 0.0
    if settlement == "half_loss":
        return -0.5
    return -1.0


def _clv(entry_odds: float | None, closing_odds: float | None) -> float | None:
    if not entry_odds or not closing_odds or entry_odds <= 1 or closing_odds <= 1:
        return None
    return round(entry_odds / closing_odds - 1, 6)


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _compact_time(value: str) -> str:
    return value.replace("-", "").replace(":", "").replace("+", "Z").split(".")[0]


def _snapshot_id(row: dict) -> str:
    line = "none" if row.get("line") is None else str(row.get("line")).replace(".", "_")
    bookmaker = str(row.get("bookmaker") or "book").lower().replace(" ", "-")
    return f'{row["match_id"]}-{row["market_type"]}-{line}-{bookmaker}-{_compact_time(row["captured_at"])}'
