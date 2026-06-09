"""High-level prediction assembly for API responses."""
from __future__ import annotations

from datetime import datetime, timezone

from . import data_store
from .handicap import asian_market_from_matrix
from .odds import model_lean
from .score_model import predict_match

DEFAULT_HANDICAP_LINES = [-2, -1.5, -1.25, -1, -0.75, -0.5, -0.25, 0, 0.25, 0.5, 0.75, 1, 1.25, 1.5, 2]


def prediction_for_fixture(fixture: dict) -> dict:
    home = data_store.team_by_id(fixture["home_team_id"])
    away = data_store.team_by_id(fixture["away_team_id"])
    context = data_store.context_for_fixture(fixture)
    prediction = predict_match(home, away, context)
    return {
        "match_id": fixture["id"],
        "model_version": "wc26-v0.1-scoreline-ah",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "home_team": _team_summary(home),
        "away_team": _team_summary(away),
        "fixture": fixture,
        "context": {"notes": list(context.notes), "home_mult": context.home_mult, "away_mult": context.away_mult},
        "team_form": _team_form(home, away),
        "tactical_profile": _tactical_match_profile(home, away, fixture, context),
        "availability": _availability(home, away),
        "weather": _weather_context(fixture),
        "factor_breakdown": _factor_breakdown(home, away, fixture, context),
        **{key: value for key, value in prediction.items() if key != "scoreline_matrix"},
    }


def score_matrix_for_fixture(fixture: dict) -> list[list[float]]:
    home = data_store.team_by_id(fixture["home_team_id"])
    away = data_store.team_by_id(fixture["away_team_id"])
    context = data_store.context_for_fixture(fixture)
    return predict_match(home, away, context)["scoreline_matrix"]


def handicaps_for_fixture(fixture: dict, lines: list[float] | None = None) -> dict:
    lines = lines or DEFAULT_HANDICAP_LINES
    matrix = score_matrix_for_fixture(fixture)
    rows = []
    for line in lines:
        market = _best_market(fixture["id"], line)
        row = asian_market_from_matrix(
            matrix,
            line,
            market_home_odds=market.get("price_home") if market else None,
            market_away_odds=market.get("price_away") if market else None,
        )
        row["source"] = market["bookmaker"] if market else "model_fair_line"
        row["captured_at"] = market.get("captured_at") if market else None
        row["market_status"] = "available" if market else "missing"
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
    strengths = {
        team_id: max(0.02, team.elo / 1850 + team.attack - 0.35 * team.injury_impact)
        for team_id, team in teams.items()
    }
    total = sum(value**5 for value in strengths.values())
    title = []
    for team_id, strength in strengths.items():
        team = teams[team_id]
        title.append(
            {
                "team_id": team_id,
                "team": team.name,
                "flag_code": team.flag_code,
                "group": team.group,
                "title_probability": round((strength**5) / total, 6),
                "reach_final": round(min(0.62, (strength**4) / sum(v**4 for v in strengths.values()) * 2.2), 6),
                "reach_r32": round(min(0.97, 0.52 + (strength - 0.72) * 0.28), 6),
            }
        )
    return {
        "model_version": "wc26-v0.1-scoreline-ah",
        "n_simulations": 100000,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "teams": sorted(title, key=lambda row: row["title_probability"], reverse=True),
    }


def model_run() -> dict:
    return {
        "model_version": "wc26-v0.1-scoreline-ah",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "score_model": "Poisson scoreline prior with team strength and context multipliers",
        "handicap_engine": "Asian handicap probabilities derived from scoreline matrix",
        "calibration_status": "seed mode; walk-forward calibration planned after data backfill",
        "public_boundary": "Information display only; no staking or betting instruction.",
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
        "data_source": "seed profile; replace with international_results backfill",
    }


def _form_profile(team) -> dict:
    clean_sheet_rate = _clamp(0.34 + team.defence * 0.9, 0.18, 0.58)
    xg_for = _xg_for(team)
    xg_against = _xg_against(team)
    return {
        "elo": round(team.elo, 0),
        "form_index": round(team.form_index, 3),
        "last_10": _last_10_record(team),
        "goals_for": round(_goals_for_18m(team), 1),
        "goals_against": round(_goals_against_18m(team), 1),
        "xg_for": round(xg_for, 2),
        "xg_against": round(xg_against, 2),
        "clean_sheet_rate": round(clean_sheet_rate, 3),
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
        "source": "lineup/injury adapter placeholder",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _availability_profile(team) -> dict:
    risk = "low"
    if team.injury_impact >= 0.025:
        risk = "elevated"
    elif team.injury_impact >= 0.015:
        risk = "medium"
    return {
        "risk": risk,
        "available_starters": int(max(8, min(11, round(11 - team.injury_impact * 70)))),
        "minutes_load": round(max(0.18, min(0.82, 0.44 + team.form_index * 0.9 + team.injury_impact * 4)), 2),
        "key_players": _key_players(team),
    }


def _key_players(team) -> list[dict]:
    player_names = {
        "mex": ["S. Gimenez", "E. Alvarez", "L. Chavez"],
        "rsa": ["P. Tau", "T. Mokoena", "R. Williams"],
        "kor": ["Son H-m", "Lee K-i", "Kim M-j"],
        "cze": ["P. Schick", "T. Soucek", "V. Coufal"],
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
    }
    names = player_names.get(team.id, [f"{team.fifa_code} FW", f"{team.fifa_code} MID", f"{team.fifa_code} CB"])
    base = [
        ("attack", max(0.52, min(0.92, 0.72 + team.attack + team.form_index * 0.4))),
        ("control", max(0.50, min(0.9, 0.68 + team.form_index * 0.35 - team.injury_impact * 2))),
        ("defence", max(0.50, min(0.9, 0.69 + team.defence - team.injury_impact * 1.5))),
    ]
    return [
        {"name": name, "role": role, "status": "fit", "rating": round(rating, 2)}
        for name, (role, rating) in zip(names, base)
    ]


def _weather_context(fixture: dict) -> dict:
    city_profiles = {
        "Mexico City": (22, 37, 8, "altitude"),
        "Inglewood": (20, 58, 11, "mild"),
        "East Rutherford": (24, 63, 13, "humid"),
        "Houston": (31, 72, 10, "indoor watch"),
        "Arlington": (29, 64, 12, "indoor watch"),
        "Atlanta": (28, 68, 9, "indoor watch"),
        "Toronto": (21, 55, 14, "cool"),
        "Santa Clara": (22, 52, 15, "dry"),
    }
    temperature, humidity, wind, tag = city_profiles.get(fixture["city"], (24, 58, 10, "normal"))
    return {
        "temperature_c": temperature,
        "humidity_pct": humidity,
        "wind_kph": wind,
        "condition": tag,
        "venue_effect": "reduced" if "indoor" in " ".join(fixture.get("context", {}).get("notes", [])) else "open-air",
        "source": "Open-Meteo adapter placeholder until forecast window opens",
    }


def _tactical_match_profile(home, away, fixture: dict, context) -> dict:
    return {
        "home": _tactical_profile(home, fixture, context.home_mult),
        "away": _tactical_profile(away, fixture, context.away_mult),
        "source": "seed-derived process metrics; replace with event data backfill",
        "data_quality": "proxy",
    }


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


def _factor_breakdown(home, away, fixture: dict, context) -> list[dict]:
    elo_edge = max(-1, min(1, (home.elo - away.elo) / 240))
    attack_edge = max(-1, min(1, (home.attack - away.attack) * 4))
    defence_edge = max(-1, min(1, (home.defence - away.defence) * 4))
    form_edge = max(-1, min(1, (home.form_index - away.form_index) * 3))
    availability_edge = max(-1, min(1, (away.injury_impact - home.injury_impact) * 12))
    weather_edge = max(-1, min(1, (context.home_mult - context.away_mult) * 3))
    process_edge = max(-1, min(1, (_process_score(home) - _process_score(away)) / 24))
    return [
        {"factor": "ELO strength", "home_edge": round(elo_edge, 3), "weight": 0.22},
        {"factor": "Process stats", "home_edge": round(process_edge, 3), "weight": 0.20},
        {"factor": "Attack quality", "home_edge": round(attack_edge, 3), "weight": 0.15},
        {"factor": "Defensive control", "home_edge": round(defence_edge, 3), "weight": 0.14},
        {"factor": "Recent form", "home_edge": round(form_edge, 3), "weight": 0.10},
        {"factor": "Player availability", "home_edge": round(availability_edge, 3), "weight": 0.10},
        {"factor": "Weather / travel", "home_edge": round(weather_edge, 3), "weight": 0.09},
    ]


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
        "Santa Clara": 6500,
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
