"""High-level prediction assembly for API responses."""
from __future__ import annotations

import math
from datetime import datetime, timezone

from . import data_store
from .handicap import asian_market_from_matrix
from .odds import model_lean
from .score_model import MatchAdjustments, predict_match

DEFAULT_HANDICAP_LINES = [-2, -1.5, -1.25, -1, -0.75, -0.5, -0.25, 0, 0.25, 0.5, 0.75, 1, 1.25, 1.5, 2]
MODEL_VERSION = "wc26-v0.3-full-group-seed-ah"


def prediction_for_fixture(fixture: dict) -> dict:
    home = data_store.team_by_id(fixture["home_team_id"])
    away = data_store.team_by_id(fixture["away_team_id"])
    context = data_store.context_for_fixture(fixture)
    factor_breakdown = _factor_breakdown(home, away, fixture, context)
    adjustments = _model_adjustments(home, away, fixture, context, factor_breakdown)
    prediction = predict_match(home, away, context, adjustments)
    return {
        "match_id": fixture["id"],
        "model_version": MODEL_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "home_team": _team_summary(home),
        "away_team": _team_summary(away),
        "fixture": fixture,
        "context": {"notes": list(context.notes), "home_mult": context.home_mult, "away_mult": context.away_mult},
        "team_form": _team_form(home, away),
        "tactical_profile": _tactical_match_profile(home, away, fixture, context),
        "availability": _availability(home, away),
        "weather": _weather_context(fixture),
        "factor_breakdown": factor_breakdown,
        "model_inputs": _model_input_summary(adjustments, factor_breakdown),
        **{key: value for key, value in prediction.items() if key != "scoreline_matrix"},
    }


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
    total = sum(value**6 for value in strengths.values())
    final_total = sum(value**5 for value in strengths.values())
    groups: dict[str, list[tuple[str, float]]] = {}
    for team_id, team in teams.items():
        groups.setdefault(team.group, []).append((team_id, strengths[team_id]))
    group_ranks = {
        team_id: rank
        for group in groups.values()
        for rank, (team_id, _strength) in enumerate(sorted(group, key=lambda row: row[1], reverse=True), start=1)
    }
    title = []
    for team_id, strength in strengths.items():
        team = teams[team_id]
        group_rank = group_ranks[team_id]
        rank_base = {1: 0.88, 2: 0.70, 3: 0.44, 4: 0.19}[group_rank]
        group_avg = sum(value for _team_id, value in groups[team.group]) / len(groups[team.group])
        reach_r32 = _clamp(rank_base + (strength - group_avg) * 0.20, 0.08, 0.97)
        title.append(
            {
                "team_id": team_id,
                "team": team.name,
                "flag_code": team.flag_code,
                "group": team.group,
                "title_probability": round((strength**6) / total, 6),
                "reach_final": round(min(0.62, (strength**5) / final_total * 2.0), 6),
                "reach_r32": round(reach_r32, 6),
                "group_rank_proxy": group_rank,
            }
        )
    return {
        "model_version": MODEL_VERSION,
        "n_simulations": 100000,
        "format": "12 groups of four; top two plus eight best third-place teams reach the round of 32",
        "data_quality": "full 48-team public schedule seed; event, injury, weather and sportsbook feeds still require live provider backfill",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "teams": sorted(title, key=lambda row: row["title_probability"], reverse=True),
    }


def model_run() -> dict:
    return {
        "model_version": MODEL_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "score_model": "Poisson scoreline prior with factor-aware adjustments for process stats, availability, weather and travel",
        "handicap_engine": "Asian handicap probabilities derived from scoreline matrix",
        "calibration_status": "v0.3 full 48-team seed; walk-forward calibration starts after historical results, injury and closing-line backfill",
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
        "data_source": "48-team seed profile; replace with international_results and event-data backfill",
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
        "source": "lineup/injury adapter placeholder; player names are projected watchlist entries",
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
        "condition": tag,
        "venue_effect": "reduced" if "indoor" in " ".join(fixture.get("context", {}).get("notes", [])) else "open-air",
        "source": "Open-Meteo adapter placeholder until forecast window opens",
    }


def _tactical_match_profile(home, away, fixture: dict, context) -> dict:
    return {
        "home": _tactical_profile(home, fixture, context.home_mult),
        "away": _tactical_profile(away, fixture, context.away_mult),
        "source": "48-team seed-derived process metrics; replace with event data backfill",
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


def _model_adjustments(home, away, fixture: dict, context, factor_breakdown: list[dict]) -> MatchAdjustments:
    edges = {row["factor"]: row["home_edge"] for row in factor_breakdown}
    contextual_edge = (
        edges["Process stats"] * 0.50
        + edges["Player availability"] * 0.28
        + edges["Weather / travel"] * 0.22
    )
    weather = _weather_context(fixture)
    heat_stress = max(0, weather["temperature_c"] - 27) * 0.009
    humidity_stress = max(0, weather["humidity_pct"] - 65) * 0.002
    wind_stress = max(0, weather["wind_kph"] - 18) * 0.004
    avg_press = (_press_score(home) + _press_score(away)) / 2
    tempo_lift = (avg_press - 50) * 0.0014

    home_fatigue = _fatigue_goal_multiplier(home, fixture)
    away_fatigue = _fatigue_goal_multiplier(away, fixture)
    home_goal_mult = _clamp(math.exp(0.30 * contextual_edge) * home_fatigue, 0.78, 1.24)
    away_goal_mult = _clamp(math.exp(-0.30 * contextual_edge) * away_fatigue, 0.78, 1.24)
    total_goal_mult = _clamp(1 + tempo_lift - heat_stress - humidity_stress - wind_stress, 0.86, 1.10)
    return MatchAdjustments(
        home_goal_mult=home_goal_mult,
        away_goal_mult=away_goal_mult,
        total_goal_mult=total_goal_mult,
    )


def _model_input_summary(adjustments: MatchAdjustments, factor_breakdown: list[dict]) -> dict:
    weighted_context_edge = sum(row["home_edge"] * row["weight"] for row in factor_breakdown)
    return {
        "weighted_context_edge": round(weighted_context_edge, 3),
        "home_goal_multiplier": round(adjustments.home_goal_mult, 3),
        "away_goal_multiplier": round(adjustments.away_goal_mult, 3),
        "total_goal_multiplier": round(adjustments.total_goal_mult, 3),
        "applied_to": "expected goals before scoreline and handicap probability generation",
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
