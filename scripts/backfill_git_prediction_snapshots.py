"""Recover immutable pre-kickoff predictions from published Git history."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "backend" / "app" / "data"
STATIC_PATH = "frontend/static-site/data.json"
LOCK_BUFFER = timedelta(minutes=5)
sys.path.insert(0, str(ROOT / "backend"))

from app.services.backtesting import merge_model_prediction_snapshots  # noqa: E402


def run_git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def published_commits() -> list[tuple[str, str]]:
    rows = []
    for line in run_git("log", "--format=%H%x09%cI", "--", STATIC_PATH).splitlines():
        commit, committed_at = line.split("\t", 1)
        rows.append((commit, committed_at))
    return list(reversed(rows))


def snapshot_from_match(match: dict, commit: str, committed_at: str) -> dict:
    return {
        "prediction_id": f'{match["match_id"]}-git-{commit[:12]}',
        "match_id": match["match_id"],
        "generated_at": committed_at,
        "model_version": match.get("model_version") or "published-static-model",
        "lock_status": "eligible_pre_kickoff",
        "kickoff_utc": match["fixture"]["kickoff_utc"],
        "p_home": match.get("p_home"),
        "p_draw": match.get("p_draw"),
        "p_away": match.get("p_away"),
        "p_over_2_5": match.get("p_over_2_5"),
        "p_btts": match.get("p_btts"),
        "handicap_probabilities": [_snapshot_handicap(row) for row in match.get("handicap_preview", [])],
        "event_probabilities": {
            "corners": (match.get("event_predictions") or {}).get("corners", {}),
            "cards": (match.get("event_predictions") or {}).get("cards", {}),
        },
        "data_source_versions": {"git_publication": commit},
        "lock_evidence": {
            "type": "git_commit_before_kickoff",
            "commit": commit,
            "committed_at": committed_at,
        },
    }


def _snapshot_handicap(row: dict) -> dict:
    return {
        "line": row.get("line"),
        "source": row.get("source"),
        "captured_at": row.get("captured_at"),
        "market_status": row.get("market_status"),
        "home": _snapshot_handicap_side(row.get("home") or {}),
        "away": _snapshot_handicap_side(row.get("away") or {}),
    }


def _snapshot_handicap_side(side: dict) -> dict:
    positive = float(side.get("positive_probability") or 0)
    half_win = float(side.get("half_win") or 0)
    push = float(side.get("push") or 0)
    half_loss = float(side.get("half_loss") or 0)
    win = max(0.0, positive - half_win)
    loss = max(0.0, 1 - win - half_win - push - half_loss)
    odds = side.get("market_decimal_odds")
    expected_return = None
    if odds is not None and float(odds) > 1:
        payout = float(odds) - 1
        expected_return = win * payout + half_win * payout * 0.5 - half_loss * 0.5 - loss
    return {
        "positive_probability": side.get("positive_probability"),
        "fair_decimal_odds": side.get("fair_decimal_odds"),
        "market_decimal_odds": odds,
        "expected_return": round(expected_return, 4) if expected_return is not None else None,
    }


def main() -> None:
    latest_by_match = {}
    for commit, committed_at in published_commits():
        try:
            payload = json.loads(run_git("show", f"{commit}:{STATIC_PATH}"))
        except (json.JSONDecodeError, subprocess.CalledProcessError):
            continue
        committed = parse_dt(committed_at)
        for match in payload.get("matches", []):
            probabilities = [match.get("p_home"), match.get("p_draw"), match.get("p_away")]
            if any(value is None for value in probabilities):
                continue
            kickoff = parse_dt(match["fixture"]["kickoff_utc"])
            if committed <= kickoff - LOCK_BUFFER:
                latest_by_match[match["match_id"]] = snapshot_from_match(match, commit, committed_at)

    output = DATA_DIR / "model_prediction_snapshots.json"
    existing = json.loads(output.read_text(encoding="utf-8")) if output.exists() else []
    merged = merge_model_prediction_snapshots(existing, list(latest_by_match.values()))
    output.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    print(f"Recovered {len(latest_by_match)} locked match snapshots; stored {len(merged)} total snapshots.")


if __name__ == "__main__":
    main()
