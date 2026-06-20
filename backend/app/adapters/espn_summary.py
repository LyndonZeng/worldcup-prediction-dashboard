"""ESPN public match-summary adapter.

The summary endpoint is a best-effort public source. It gives real match
materials after lineups are published: formations, starters, substitutions,
team stats and player event stats. It does not provide licensed player ratings.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .http import get_json

BASE_URL = "https://site.web.api.espn.com/apis/site/v2/sports/soccer/fifa.world/summary"

TEAM_STAT_MAP = {
    "foulsCommitted": "fouls_committed",
    "yellowCards": "yellow_cards",
    "redCards": "red_cards",
    "offsides": "offsides",
    "wonCorners": "corners",
    "saves": "saves",
    "possessionPct": "possession_pct",
    "totalShots": "shots",
    "shotsOnTarget": "shots_on_target",
    "shotPct": "shot_pct",
    "penaltyKickGoals": "penalty_goals",
    "penaltyKickShots": "penalty_shots",
    "accuratePasses": "accurate_passes",
    "totalPasses": "total_passes",
    "passPct": "pass_pct",
    "accurateCrosses": "accurate_crosses",
    "totalCrosses": "total_crosses",
    "crossPct": "cross_pct",
    "totalLongBalls": "total_long_balls",
    "accurateLongBalls": "accurate_long_balls",
    "longballPct": "longball_pct",
    "blockedShots": "blocked_shots",
    "effectiveTackles": "effective_tackles",
    "totalTackles": "total_tackles",
    "tacklePct": "tackle_pct",
    "interceptions": "interceptions",
    "effectiveClearance": "effective_clearances",
    "totalClearance": "clearances",
}

PLAYER_STAT_MAP = {
    "totalGoals": "goals",
    "goalAssists": "assists",
    "totalShots": "shots",
    "shotsOnTarget": "shots_on_target",
    "yellowCards": "yellow_cards",
    "redCards": "red_cards",
    "foulsCommitted": "fouls_committed",
    "foulsSuffered": "fouls_suffered",
    "saves": "saves",
    "goalsConceded": "goals_conceded",
    "offsides": "offsides",
    "subIns": "sub_ins",
    "ownGoals": "own_goals",
    "expectedGoals": "expected_goals",
    "expectedGoalsConceded": "expected_goals_conceded",
    "accuratePasses": "accurate_passes",
    "totalPasses": "total_passes",
    "defensiveInterventions": "defensive_interventions",
    "effectiveTackles": "effective_tackles",
    "duelsWon": "duels_won",
}

PERCENT_STATS = {"shot_pct", "pass_pct", "cross_pct", "longball_pct", "tackle_pct"}


def fetch_match_summary(event_id: str) -> dict[str, Any]:
    return get_json(
        BASE_URL,
        params={"event": event_id},
        headers={"User-Agent": "wc26-dashboard/0.1"},
        timeout=10,
    )


def fetch_match_summaries(live_rows: list[dict]) -> list[dict]:
    captured_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for live_row in live_rows:
        event_id = live_row.get("espn_event_id")
        if not event_id or not _summary_is_useful(live_row):
            continue
        try:
            payload = fetch_match_summary(str(event_id))
            row = normalize_summary(live_row, payload, captured_at)
        except Exception as exc:
            row = _error_row(live_row, captured_at, exc)
        rows.append(row)
    return sorted(rows, key=lambda row: row["match_number"])


def normalize_summary(live_row: dict, payload: dict, captured_at: str) -> dict:
    game_info = payload.get("gameInfo") or {}
    venue = game_info.get("venue") or {}
    teams = {
        "home": _team_material(payload, "home"),
        "away": _team_material(payload, "away"),
    }
    return {
        "match_id": live_row["match_id"],
        "match_number": live_row["match_number"],
        "espn_event_id": live_row.get("espn_event_id"),
        "source": "ESPN public match summary",
        "source_quality": "live_public_summary",
        "captured_at": captured_at,
        "status": "available" if _has_materials(teams) else "empty_summary",
        "note": "Public roster, formation and team-stat feed; no licensed player-rating field.",
        "attendance": game_info.get("attendance") or live_row.get("attendance"),
        "venue_name": venue.get("fullName") or venue.get("shortName"),
        "officials": [
            official.get("displayName") or official.get("fullName")
            for official in game_info.get("officials") or []
            if official.get("displayName") or official.get("fullName")
        ],
        "injury_status": {
            "status": "not_available_from_public_summary",
            "source": "ESPN public match summary",
            "note": "This public endpoint exposes rosters and active flags, but no confirmed injury list.",
        },
        "teams": teams,
    }


def _summary_is_useful(live_row: dict) -> bool:
    return bool(live_row.get("completed") or live_row.get("status_state") == "in")


def _error_row(live_row: dict, captured_at: str, exc: Exception) -> dict:
    return {
        "match_id": live_row["match_id"],
        "match_number": live_row["match_number"],
        "espn_event_id": live_row.get("espn_event_id"),
        "source": "ESPN public match summary",
        "source_quality": "live_public_summary",
        "captured_at": captured_at,
        "status": "fetch_error",
        "note": str(exc)[:160],
        "teams": {"home": {}, "away": {}},
    }


def _team_material(payload: dict, side: str) -> dict:
    roster_block = _side_block(payload.get("rosters") or [], side)
    box_block = _side_block((payload.get("boxscore") or {}).get("teams") or [], side)
    team = (roster_block or box_block or {}).get("team") or {}
    roster = [_player(row) for row in (roster_block or {}).get("roster") or []]
    starters = [row for row in roster if row.get("starter")]
    substitutes = [row for row in roster if not row.get("starter")]
    leaders = _leaders_for_team(payload, team)
    return {
        "team_name": team.get("displayName") or team.get("name") or team.get("shortDisplayName"),
        "team_abbreviation": team.get("abbreviation"),
        "formation": (roster_block or {}).get("formation"),
        "roster_count": len(roster),
        "starter_count": len(starters),
        "subbed_in_count": sum(1 for row in roster if row.get("subbed_in")),
        "inactive_count": sum(1 for row in roster if not row.get("active")),
        "team_stats": _stats((box_block or {}).get("statistics") or [], TEAM_STAT_MAP),
        "starters": starters,
        "substitutes": substitutes,
        "impact_players": _impact_players(roster, leaders),
        "leaders": leaders,
    }


def _side_block(blocks: list[dict], side: str) -> dict | None:
    return next((row for row in blocks if row.get("homeAway") == side), None)


def _player(row: dict) -> dict:
    athlete = row.get("athlete") or {}
    position = row.get("position") or {}
    stats = _stats(row.get("stats") or [], PLAYER_STAT_MAP)
    rating = _performance_rating(stats)
    return {
        "name": athlete.get("displayName") or athlete.get("fullName") or athlete.get("shortName"),
        "short_name": athlete.get("shortName"),
        "jersey": row.get("jersey"),
        "position": position.get("abbreviation") or position.get("displayName"),
        "starter": bool(row.get("starter")),
        "active": bool(row.get("active")),
        "subbed_in": bool(row.get("subbedIn")),
        "subbed_out": bool(row.get("subbedOut")),
        "formation_place": row.get("formationPlace"),
        "stats": stats,
        "performance_rating": rating,
        "rating_source": "derived_from_public_event_stats" if rating is not None else None,
    }


def _stats(stats: list[dict], key_map: dict[str, str]) -> dict:
    out = {}
    for stat in stats:
        key = key_map.get(stat.get("name"))
        if not key:
            continue
        value = _number(stat.get("value", stat.get("displayValue")))
        if value is None:
            continue
        if key in PERCENT_STATS and 0 <= value <= 1:
            value *= 100
        out[key] = round(value, 3) if isinstance(value, float) and not value.is_integer() else int(value)
    return out


def _leaders_for_team(payload: dict, team: dict) -> list[dict]:
    team_name = team.get("displayName") or team.get("name")
    abbreviation = team.get("abbreviation")
    if not team_name and not abbreviation:
        return []
    out = []
    for block in payload.get("leaders") or []:
        leader_team = block.get("team") or {}
        if leader_team.get("displayName") != team_name and leader_team.get("abbreviation") != abbreviation:
            continue
        for category in block.get("leaders") or []:
            leader = ((category.get("leaders") or [])[:1] or [{}])[0]
            athlete = leader.get("athlete") or {}
            if not athlete:
                continue
            out.append(
                {
                    "category": category.get("displayName") or category.get("name"),
                    "name": athlete.get("displayName") or athlete.get("shortName"),
                    "short_name": athlete.get("shortName"),
                    "position": (athlete.get("position") or {}).get("abbreviation"),
                    "value": leader.get("displayValue"),
                    "summary": leader.get("summary"),
                    "stats": _stats(leader.get("statistics") or [], PLAYER_STAT_MAP),
                }
            )
    return out[:6]


def _impact_players(roster: list[dict], leaders: list[dict]) -> list[dict]:
    by_name = {row.get("name"): dict(row) for row in roster if row.get("name")}
    for leader in leaders:
        if not leader.get("name"):
            continue
        if leader["name"] not in by_name:
            by_name[leader["name"]] = {
                "name": leader["name"],
                "short_name": leader.get("short_name"),
                "position": leader.get("position"),
                "starter": False,
                "active": True,
                "subbed_in": False,
                "subbed_out": False,
                "stats": {},
            }
        merged = dict(by_name[leader["name"]])
        merged_stats = dict(merged.get("stats") or {})
        merged_stats.update(leader.get("stats") or {})
        merged["stats"] = merged_stats
        merged["performance_rating"] = _performance_rating(merged_stats)
        merged["rating_source"] = "derived_from_public_event_stats"
        by_name[leader["name"]] = merged
    ranked = sorted(by_name.values(), key=_impact_score, reverse=True)
    meaningful = [row for row in ranked if _impact_score(row) > 0]
    return (meaningful or [row for row in roster if row.get("starter")])[:5]


def _impact_score(player: dict) -> float:
    stats = player.get("stats") or {}
    return (
        float(stats.get("goals") or 0) * 5
        + float(stats.get("assists") or 0) * 4
        + float(stats.get("shots_on_target") or 0) * 2
        + float(stats.get("shots") or 0)
        + float(stats.get("expected_goals") or 0) * 2
        + float(stats.get("saves") or 0)
        + float(stats.get("defensive_interventions") or 0) * 0.5
        + float(stats.get("yellow_cards") or 0) * 0.2
        + float(stats.get("red_cards") or 0) * 0.3
    )


def _performance_rating(stats: dict) -> float | None:
    if not stats:
        return None
    score = (
        6.0
        + float(stats.get("goals") or 0) * 0.9
        + float(stats.get("assists") or 0) * 0.55
        + float(stats.get("shots_on_target") or 0) * 0.12
        + float(stats.get("expected_goals") or 0) * 0.35
        + float(stats.get("saves") or 0) * 0.16
        + float(stats.get("defensive_interventions") or 0) * 0.05
        + float(stats.get("duels_won") or 0) * 0.04
        - float(stats.get("yellow_cards") or 0) * 0.18
        - float(stats.get("red_cards") or 0) * 0.75
        - float(stats.get("own_goals") or 0) * 0.8
    )
    return round(max(4.0, min(10.0, score)), 1)


def _has_materials(teams: dict[str, dict]) -> bool:
    return any(team.get("starter_count") or team.get("team_stats") for team in teams.values())


def _number(value) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace("%", "").replace(",", ""))
    except ValueError:
        return None
