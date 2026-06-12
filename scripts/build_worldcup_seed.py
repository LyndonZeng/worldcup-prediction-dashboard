"""Build the 2026 World Cup seed dataset and static dashboard payload.

The dataset is intentionally labeled as a seed/proxy layer. It gives the
dashboard a complete tournament shape while real provider feeds are wired in.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "backend" / "app" / "data"
STATIC_DATA = ROOT / "frontend" / "static-site" / "data.json"
ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

HOST_COUNTRY_BY_CITY = {
    "Mexico City": "mex",
    "Guadalajara": "mex",
    "Monterrey": "mex",
    "Toronto": "can",
    "Vancouver": "can",
    "Inglewood": "usa",
    "Santa Clara": "usa",
    "East Rutherford": "usa",
    "Houston": "usa",
    "Arlington": "usa",
    "Atlanta": "usa",
    "Seattle": "usa",
    "Philadelphia": "usa",
    "Boston": "usa",
    "Miami": "usa",
    "Kansas City": "usa",
}

INDOOR_WATCH_CITIES = {"Houston", "Arlington", "Atlanta", "Vancouver"}

TEAM_ROWS = [
    ("mex", "Mexico", "A", "MEX", "mx", 1775, 0.04, 0.03, 0.12, 0.01),
    ("rsa", "South Africa", "A", "RSA", "za", 1584, -0.10, -0.07, 0.06, 0.00),
    ("kor", "South Korea", "A", "KOR", "kr", 1718, 0.01, 0.02, 0.04, 0.00),
    ("cze", "Czechia", "A", "CZE", "cz", 1725, 0.03, 0.04, -0.02, 0.02),
    ("can", "Canada", "B", "CAN", "ca", 1662, 0.00, -0.02, 0.07, 0.01),
    ("bih", "Bosnia and Herzegovina", "B", "BIH", "ba", 1605, -0.04, -0.03, -0.01, 0.02),
    ("qat", "Qatar", "B", "QAT", "qa", 1610, -0.06, -0.02, 0.02, 0.00),
    ("sui", "Switzerland", "B", "SUI", "ch", 1788, 0.04, 0.08, 0.03, 0.01),
    ("bra", "Brazil", "C", "BRA", "br", 1918, 0.20, 0.12, 0.03, 0.01),
    ("mar", "Morocco", "C", "MAR", "ma", 1812, 0.09, 0.11, 0.06, 0.01),
    ("hai", "Haiti", "C", "HAI", "ht", 1455, -0.15, -0.12, 0.02, 0.00),
    ("sco", "Scotland", "C", "SCO", "gb-sct", 1707, -0.02, 0.03, -0.03, 0.02),
    ("usa", "United States", "D", "USA", "us", 1770, 0.07, 0.02, 0.08, 0.01),
    ("par", "Paraguay", "D", "PAR", "py", 1692, -0.03, 0.05, 0.03, 0.00),
    ("aus", "Australia", "D", "AUS", "au", 1664, -0.04, 0.01, -0.01, 0.00),
    ("tur", "Turkey", "D", "TUR", "tr", 1784, 0.08, -0.01, 0.07, 0.02),
    ("ger", "Germany", "E", "GER", "de", 1855, 0.13, 0.07, 0.05, 0.00),
    ("cur", "Curacao", "E", "CUW", "cw", 1430, -0.16, -0.14, 0.00, 0.00),
    ("civ", "Cote d'Ivoire", "E", "CIV", "ci", 1698, 0.02, -0.01, 0.09, 0.03),
    ("ecu", "Ecuador", "E", "ECU", "ec", 1765, 0.05, 0.08, 0.04, 0.01),
    ("ned", "Netherlands", "F", "NED", "nl", 1848, 0.12, 0.10, 0.04, 0.01),
    ("jpn", "Japan", "F", "JPN", "jp", 1778, 0.08, 0.06, 0.08, 0.00),
    ("swe", "Sweden", "F", "SWE", "se", 1720, 0.05, 0.03, 0.02, 0.02),
    ("tun", "Tunisia", "F", "TUN", "tn", 1658, -0.04, 0.02, 0.00, 0.01),
    ("bel", "Belgium", "G", "BEL", "be", 1838, 0.12, 0.04, 0.04, 0.02),
    ("egy", "Egypt", "G", "EGY", "eg", 1688, 0.03, -0.01, 0.05, 0.01),
    ("irn", "Iran", "G", "IRN", "ir", 1712, 0.01, 0.04, 0.02, 0.00),
    ("nzl", "New Zealand", "G", "NZL", "nz", 1500, -0.12, -0.08, 0.01, 0.00),
    ("esp", "Spain", "H", "ESP", "es", 1925, 0.18, 0.14, 0.10, 0.01),
    ("cpv", "Cabo Verde", "H", "CPV", "cv", 1558, -0.07, -0.03, 0.04, 0.01),
    ("ksa", "Saudi Arabia", "H", "KSA", "sa", 1632, -0.05, -0.02, 0.02, 0.01),
    ("uru", "Uruguay", "H", "URU", "uy", 1825, 0.08, 0.10, 0.06, 0.01),
    ("fra", "France", "I", "FRA", "fr", 1908, 0.18, 0.11, 0.06, 0.01),
    ("sen", "Senegal", "I", "SEN", "sn", 1768, 0.05, 0.08, 0.05, 0.01),
    ("irq", "Iraq", "I", "IRQ", "iq", 1580, -0.08, -0.04, 0.04, 0.00),
    ("nor", "Norway", "I", "NOR", "no", 1760, 0.11, 0.01, 0.03, 0.02),
    ("arg", "Argentina", "J", "ARG", "ar", 1935, 0.18, 0.12, 0.08, 0.01),
    ("alg", "Algeria", "J", "ALG", "dz", 1708, 0.03, 0.02, 0.05, 0.01),
    ("aut", "Austria", "J", "AUT", "at", 1780, 0.07, 0.07, 0.06, 0.02),
    ("jor", "Jordan", "J", "JOR", "jo", 1515, -0.11, -0.07, 0.07, 0.00),
    ("por", "Portugal", "K", "POR", "pt", 1875, 0.16, 0.09, 0.05, 0.01),
    ("cod", "DR Congo", "K", "COD", "cd", 1620, -0.03, -0.02, 0.04, 0.01),
    ("uzb", "Uzbekistan", "K", "UZB", "uz", 1598, -0.05, -0.02, 0.05, 0.00),
    ("col", "Colombia", "K", "COL", "co", 1800, 0.09, 0.07, 0.06, 0.01),
    ("eng", "England", "L", "ENG", "gb-eng", 1888, 0.16, 0.10, 0.05, 0.01),
    ("cro", "Croatia", "L", "CRO", "hr", 1810, 0.06, 0.09, 0.01, 0.02),
    ("gha", "Ghana", "L", "GHA", "gh", 1668, 0.00, -0.02, 0.04, 0.01),
    ("pan", "Panama", "L", "PAN", "pa", 1588, -0.08, -0.05, 0.03, 0.00),
]

MATCH_SPECS = [
    ("2026-06-11", "15:00", "A", "mex", "rsa", "Estadio Azteca", "Mexico City", ["host opener"]),
    ("2026-06-11", "22:00", "A", "kor", "cze", "AT&T Stadium", "Arlington", []),
    ("2026-06-12", "15:00", "B", "can", "bih", "BMO Field", "Toronto", ["Canada opener"]),
    ("2026-06-12", "21:00", "D", "usa", "par", "SoFi Stadium", "Inglewood", ["United States opener"]),
    ("2026-06-13", "15:00", "B", "qat", "sui", "Levi's Stadium", "Santa Clara", []),
    ("2026-06-13", "18:00", "C", "bra", "mar", "MetLife Stadium", "East Rutherford", []),
    ("2026-06-13", "21:00", "C", "hai", "sco", "Gillette Stadium", "Boston", []),
    ("2026-06-14", "00:00", "D", "aus", "tur", "BC Place", "Vancouver", ["travel load watch"]),
    ("2026-06-14", "13:00", "E", "ger", "cur", "NRG Stadium", "Houston", []),
    ("2026-06-14", "16:00", "F", "ned", "jpn", "AT&T Stadium", "Arlington", []),
    ("2026-06-14", "19:00", "E", "civ", "ecu", "Lincoln Financial Field", "Philadelphia", []),
    ("2026-06-14", "22:00", "F", "swe", "tun", "Estadio BBVA", "Monterrey", []),
    ("2026-06-15", "12:00", "H", "esp", "cpv", "Mercedes-Benz Stadium", "Atlanta", []),
    ("2026-06-15", "15:00", "G", "bel", "egy", "Lumen Field", "Seattle", []),
    ("2026-06-15", "18:00", "H", "ksa", "uru", "Hard Rock Stadium", "Miami", []),
    ("2026-06-15", "21:00", "G", "irn", "nzl", "SoFi Stadium", "Inglewood", []),
    ("2026-06-16", "15:00", "I", "fra", "sen", "MetLife Stadium", "East Rutherford", []),
    ("2026-06-16", "18:00", "I", "irq", "nor", "Gillette Stadium", "Boston", []),
    ("2026-06-16", "21:00", "J", "arg", "alg", "GEHA Field at Arrowhead Stadium", "Kansas City", []),
    ("2026-06-17", "00:00", "J", "aut", "jor", "Levi's Stadium", "Santa Clara", []),
    ("2026-06-17", "13:00", "K", "por", "cod", "NRG Stadium", "Houston", []),
    ("2026-06-17", "16:00", "L", "eng", "cro", "AT&T Stadium", "Arlington", []),
    ("2026-06-17", "19:00", "L", "gha", "pan", "BMO Field", "Toronto", []),
    ("2026-06-17", "22:00", "K", "uzb", "col", "Estadio Azteca", "Mexico City", []),
    ("2026-06-18", "12:00", "A", "cze", "rsa", "Mercedes-Benz Stadium", "Atlanta", []),
    ("2026-06-18", "15:00", "B", "sui", "bih", "SoFi Stadium", "Inglewood", []),
    ("2026-06-18", "18:00", "B", "can", "qat", "BC Place", "Vancouver", ["host crowd"]),
    ("2026-06-18", "21:00", "A", "mex", "kor", "Estadio Akron", "Guadalajara", ["host crowd"]),
    ("2026-06-19", "15:00", "D", "usa", "aus", "Lumen Field", "Seattle", ["host crowd"]),
    ("2026-06-19", "18:00", "C", "sco", "mar", "Gillette Stadium", "Boston", []),
    ("2026-06-19", "20:30", "C", "bra", "hai", "Lincoln Financial Field", "Philadelphia", []),
    ("2026-06-19", "23:00", "D", "tur", "par", "Levi's Stadium", "Santa Clara", []),
    ("2026-06-20", "13:00", "F", "ned", "swe", "NRG Stadium", "Houston", []),
    ("2026-06-20", "16:00", "E", "ger", "civ", "BMO Field", "Toronto", []),
    ("2026-06-20", "20:00", "E", "ecu", "cur", "GEHA Field at Arrowhead Stadium", "Kansas City", []),
    ("2026-06-21", "00:00", "F", "tun", "jpn", "Estadio BBVA", "Monterrey", []),
    ("2026-06-21", "12:00", "H", "esp", "ksa", "Mercedes-Benz Stadium", "Atlanta", []),
    ("2026-06-21", "15:00", "G", "bel", "irn", "SoFi Stadium", "Inglewood", []),
    ("2026-06-21", "18:00", "H", "uru", "cpv", "Hard Rock Stadium", "Miami", []),
    ("2026-06-21", "21:00", "G", "nzl", "egy", "BC Place", "Vancouver", []),
    ("2026-06-22", "13:00", "J", "arg", "aut", "AT&T Stadium", "Arlington", []),
    ("2026-06-22", "17:00", "I", "fra", "irq", "Lincoln Financial Field", "Philadelphia", []),
    ("2026-06-22", "20:00", "I", "nor", "sen", "MetLife Stadium", "East Rutherford", []),
    ("2026-06-22", "23:00", "J", "jor", "alg", "Levi's Stadium", "Santa Clara", []),
    ("2026-06-23", "13:00", "K", "por", "uzb", "NRG Stadium", "Houston", []),
    ("2026-06-23", "16:00", "L", "eng", "gha", "Gillette Stadium", "Boston", []),
    ("2026-06-23", "19:00", "L", "pan", "cro", "BMO Field", "Toronto", []),
    ("2026-06-23", "22:00", "K", "col", "cod", "Estadio Akron", "Guadalajara", []),
    ("2026-06-24", "15:00", "B", "sui", "can", "BC Place", "Vancouver", []),
    ("2026-06-24", "15:00", "B", "bih", "qat", "Lumen Field", "Seattle", []),
    ("2026-06-24", "18:00", "C", "mar", "hai", "Mercedes-Benz Stadium", "Atlanta", []),
    ("2026-06-24", "18:00", "C", "sco", "bra", "Hard Rock Stadium", "Miami", []),
    ("2026-06-24", "21:00", "A", "rsa", "kor", "Estadio BBVA", "Monterrey", []),
    ("2026-06-24", "21:00", "A", "cze", "mex", "Estadio Azteca", "Mexico City", []),
    ("2026-06-25", "16:00", "E", "cur", "civ", "Lincoln Financial Field", "Philadelphia", []),
    ("2026-06-25", "16:00", "E", "ecu", "ger", "MetLife Stadium", "East Rutherford", []),
    ("2026-06-25", "19:00", "F", "tun", "ned", "GEHA Field at Arrowhead Stadium", "Kansas City", []),
    ("2026-06-25", "19:00", "F", "jpn", "swe", "AT&T Stadium", "Arlington", []),
    ("2026-06-25", "22:00", "D", "tur", "usa", "SoFi Stadium", "Inglewood", []),
    ("2026-06-25", "22:00", "D", "par", "aus", "Levi's Stadium", "Santa Clara", []),
    ("2026-06-26", "15:00", "I", "nor", "fra", "Gillette Stadium", "Boston", []),
    ("2026-06-26", "15:00", "I", "sen", "irq", "BMO Field", "Toronto", []),
    ("2026-06-26", "20:00", "H", "cpv", "ksa", "NRG Stadium", "Houston", []),
    ("2026-06-26", "20:00", "H", "uru", "esp", "Estadio Akron", "Guadalajara", []),
    ("2026-06-26", "23:00", "G", "nzl", "bel", "BC Place", "Vancouver", []),
    ("2026-06-26", "23:00", "G", "egy", "irn", "Lumen Field", "Seattle", []),
    ("2026-06-27", "17:00", "L", "pan", "eng", "MetLife Stadium", "East Rutherford", []),
    ("2026-06-27", "17:00", "L", "cro", "gha", "Lincoln Financial Field", "Philadelphia", []),
    ("2026-06-27", "19:30", "K", "col", "por", "Hard Rock Stadium", "Miami", []),
    ("2026-06-27", "19:30", "K", "cod", "uzb", "Mercedes-Benz Stadium", "Atlanta", []),
    ("2026-06-27", "22:00", "J", "alg", "aut", "GEHA Field at Arrowhead Stadium", "Kansas City", []),
    ("2026-06-27", "22:00", "J", "jor", "arg", "AT&T Stadium", "Arlington", []),
]

SOURCE_HEALTH = [
    {
        "source": "FIFA / public match schedule",
        "status": "seeded",
        "freshness": "2026-06-10 public schedule snapshot",
        "purpose": "48-team groups and 72 group fixtures",
    },
    {
        "source": "football-data.org",
        "status": "configured_optional",
        "freshness": "pending_api_key",
        "purpose": "fixtures, scores and post-match validation",
    },
    {
        "source": "martj42 international_results",
        "status": "adapter_ready",
        "freshness": "historical_backfill_pending",
        "purpose": "historical international results for ELO calibration",
    },
    {
        "source": "StatsBomb / Opta event feed",
        "status": "schema_ready",
        "freshness": "proxy_until_provider",
        "purpose": "shots, possession, PPDA, xG, xGA and set pieces",
    },
    {
        "source": "Open-Meteo",
        "status": "adapter_ready",
        "freshness": "forecast_window_only",
        "purpose": "weather, wind and heat context",
    },
    {
        "source": "Lineup / injury feed",
        "status": "schema_ready",
        "freshness": "sample_until_provider",
        "purpose": "player availability, injury risk and minutes load",
    },
    {
        "source": "Club minutes tracker",
        "status": "schema_ready",
        "freshness": "sample_until_provider",
        "purpose": "player form, workload and role ratings",
    },
    {
        "source": "Polymarket Gamma",
        "status": "adapter_ready",
        "freshness": "public_no_key",
        "purpose": "prediction market prices",
    },
    {
        "source": "The Odds API / TheStatsAPI",
        "status": "configured_optional",
        "freshness": "sample_consensus_proxy_pending_api_key",
        "purpose": "legal sportsbook odds and Asian handicap lines",
    },
]


def main() -> None:
    teams = build_teams()
    fixtures = build_fixtures()
    odds = build_odds_snapshots(teams, fixtures)
    write_json(DATA_DIR / "teams.json", teams)
    write_json(DATA_DIR / "fixtures.json", fixtures)
    write_json(DATA_DIR / "odds_snapshots.json", odds)
    write_json(DATA_DIR / "source_health.json", SOURCE_HEALTH)
    write_static_payload()
    print(f"Built {len(teams)} teams, {len(fixtures)} fixtures and {len(odds)} odds snapshots.")


def build_teams() -> list[dict]:
    return [
        {
            "id": team_id,
            "name": name,
            "group": group,
            "fifa_code": fifa_code,
            "flag_code": flag_code,
            "elo": elo,
            "attack": attack,
            "defence": defence,
            "form_index": form_index,
            "injury_impact": injury_impact,
        }
        for team_id, name, group, fifa_code, flag_code, elo, attack, defence, form_index, injury_impact in TEAM_ROWS
    ]


def build_fixtures() -> list[dict]:
    fixtures = []
    for match_number, (date, time_et, group, home_id, away_id, venue, city, notes) in enumerate(MATCH_SPECS, start=1):
        context = fixture_context(home_id, away_id, city, list(notes))
        fixtures.append(
            {
                "id": f"wc26-{match_number:03d}",
                "match_number": match_number,
                "stage": "Group",
                "group": group,
                "kickoff_utc": to_utc(date, time_et),
                "venue": venue,
                "city": city,
                "home_team_id": home_id,
                "away_team_id": away_id,
                "source_quality": "public_schedule_seed",
                "context": context,
            }
        )
    return fixtures


def fixture_context(home_id: str, away_id: str, city: str, notes: list[str]) -> dict:
    home_mult = 1.0
    away_mult = 1.0
    city_host = HOST_COUNTRY_BY_CITY.get(city)
    if home_id == city_host:
        home_mult += 0.02
        notes.append("host crowd")
    if away_id == city_host:
        away_mult += 0.02
        notes.append("host crowd")
    if city == "Mexico City":
        away_mult -= 0.04
        if home_id != "mex":
            home_mult -= 0.02
        notes.append("altitude watch")
    elif city in {"Guadalajara", "Monterrey"}:
        away_mult -= 0.01
        notes.append("Mexico travel and climate watch")
    if city in INDOOR_WATCH_CITIES:
        notes.append("indoor or retractable-roof weather reduction")
    return {
        "home_mult": round(home_mult, 3),
        "away_mult": round(away_mult, 3),
        "notes": sorted(set(notes)),
    }


def build_odds_snapshots(teams: list[dict], fixtures: list[dict]) -> list[dict]:
    team_index = {team["id"]: team for team in teams}
    snapshots = []
    for fixture in fixtures:
        home = team_index[fixture["home_team_id"]]
        away = team_index[fixture["away_team_id"]]
        primary = handicap_line(strength(home) - strength(away))
        adjacent = adjacent_line(primary)
        for line_index, line in enumerate([primary, adjacent]):
            home_price, away_price = sample_prices(fixture["match_number"], line_index, primary, line)
            snapshots.append(
                {
                    "match_id": fixture["id"],
                    "bookmaker": "sample-consensus-proxy",
                    "market_type": "asian_handicap",
                    "line": line,
                    "price_home": home_price,
                    "price_away": away_price,
                    "captured_at": "2026-06-10T00:00:00Z",
                }
            )
    return snapshots


def strength(team: dict) -> float:
    return (
        float(team["elo"])
        + float(team["attack"]) * 420
        + float(team["defence"]) * 240
        + float(team["form_index"]) * 150
        - float(team["injury_impact"]) * 500
    )


def handicap_line(edge: float) -> float:
    if edge >= 330:
        return -1.5
    if edge >= 250:
        return -1.25
    if edge >= 180:
        return -1.0
    if edge >= 115:
        return -0.75
    if edge >= 55:
        return -0.5
    if edge >= 18:
        return -0.25
    if edge > -18:
        return 0.0
    if edge > -55:
        return 0.25
    if edge > -115:
        return 0.5
    if edge > -180:
        return 0.75
    if edge > -250:
        return 1.0
    if edge > -330:
        return 1.25
    return 1.5


def adjacent_line(line: float) -> float:
    if line == 0:
        return -0.25
    return round(line + (0.25 if line < 0 else -0.25), 2)


def sample_prices(match_number: int, line_index: int, primary: float, line: float) -> tuple[float, float]:
    wiggle = ((match_number % 7) - 3) * 0.015
    home_price = 1.91 + wiggle
    away_price = 1.93 - wiggle
    if line_index == 1:
        if line > primary:
            home_price -= 0.14
            away_price += 0.18
        else:
            home_price += 0.18
            away_price -= 0.14
    return round(clamp(home_price, 1.68, 2.20), 2), round(clamp(away_price, 1.68, 2.20), 2)


def to_utc(date: str, time_et: str) -> str:
    local = datetime.fromisoformat(f"{date}T{time_et}:00").replace(tzinfo=ET)
    return local.astimezone(UTC).isoformat().replace("+00:00", "Z")


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def write_static_payload() -> None:
    sys.path.insert(0, str(ROOT / "backend"))
    from app.services import data_store
    from app.services.predictions import all_matches, model_run, tournament_probabilities

    data_store.teams.cache_clear()
    data_store.fixtures.cache_clear()
    data_store.odds_snapshots.cache_clear()
    data_store.source_health.cache_clear()
    data_store.live_weather.cache_clear()
    data_store.live_matches.cache_clear()
    data_store.prediction_markets.cache_clear()
    data_store.historical_results_summary.cache_clear()
    payload = {
        "matches": [compact_match(match) for match in all_matches()],
        "tournament": compact_tournament(tournament_probabilities()),
        "sources": data_store.source_health(),
        "modelRun": model_run(),
    }
    STATIC_DATA.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")


def compact_match(match: dict) -> dict:
    return {
        "match_id": match["match_id"],
        "home_team": match["home_team"],
        "away_team": match["away_team"],
        "fixture": {
            key: match["fixture"][key]
            for key in ["id", "match_number", "stage", "group", "kickoff_utc", "venue", "city", "home_team_id", "away_team_id"]
        },
        "live_status": match["live_status"],
        "team_form": {
            "home": compact_form(match["team_form"]["home"]),
            "away": compact_form(match["team_form"]["away"]),
            "elo_gap": match["team_form"]["elo_gap"],
            "data_source": match["team_form"]["data_source"],
        },
        "tactical_profile": match["tactical_profile"],
        "availability": {
            "home": compact_availability(match["availability"]["home"]),
            "away": compact_availability(match["availability"]["away"]),
            "source": match["availability"]["source"],
            "updated_at": match["availability"]["updated_at"],
        },
        "weather": match["weather"],
        "factor_breakdown": match["factor_breakdown"],
        "model_inputs": match["model_inputs"],
        "probability_intervals": match["probability_intervals"],
        "matchup": match["matchup"],
        "event_predictions": match["event_predictions"],
        "risk_register": match["risk_register"],
        "lambda_home": match["lambda_home"],
        "lambda_away": match["lambda_away"],
        "p_home": match["p_home"],
        "p_draw": match["p_draw"],
        "p_away": match["p_away"],
        "p_over_2_5": match["p_over_2_5"],
        "p_btts": match["p_btts"],
        "top_scorelines": match["top_scorelines"],
        "handicap_preview": [compact_handicap(row) for row in match["handicap_preview"]],
    }


def compact_form(form: dict) -> dict:
    return {
        "elo": form["elo"],
        "form_index": form["form_index"],
        "last_10": form["last_10"],
        "goals_for": form["goals_for"],
        "goals_against": form["goals_against"],
        "xg_for": form["xg_for"],
        "xg_against": form["xg_against"],
        "clean_sheet_rate": form["clean_sheet_rate"],
        "latest_result_date": form["latest_result_date"],
        "source": form["source"],
    }


def compact_availability(profile: dict) -> dict:
    return {
        "risk": profile["risk"],
        "available_starters": profile["available_starters"],
        "minutes_load": profile["minutes_load"],
        "qdr_index": profile["qdr_index"],
        "key_dependency": profile["key_dependency"],
        "rotation_capacity": profile["rotation_capacity"],
        "source": profile["source"],
        "data_quality": profile["data_quality"],
        "used_in_core_prediction": profile["used_in_core_prediction"],
        "key_players": [
            {
                "name": player["name"],
                "role": player["role"],
                "rating": player["rating"],
            }
            for player in profile["key_players"]
        ],
    }


def compact_handicap(row: dict) -> dict:
    return {
        "line": row["line"],
        "home": compact_handicap_side(row["home"]),
        "away": compact_handicap_side(row["away"]),
        "source": row["source"],
        "captured_at": row["captured_at"],
        "market_status": row["market_status"],
        "closing_status": row["closing_status"],
        "clv": row["clv"],
        "backtest_sample": row["backtest_sample"],
        "lean": row["lean"],
    }


def compact_handicap_side(side: dict) -> dict:
    return {
        "positive_probability": side["positive_probability"],
        "half_win": side["half_win"],
        "push": side["push"],
        "half_loss": side["half_loss"],
        "fair_decimal_odds": side["fair_decimal_odds"],
        "market_decimal_odds": side["market_decimal_odds"],
    }


def compact_tournament(tournament: dict) -> dict:
    return {
        "model_version": tournament["model_version"],
        "n_simulations": tournament["n_simulations"],
        "format": tournament["format"],
        "data_quality": tournament["data_quality"],
        "generated_at": tournament["generated_at"],
        "title_anchor": tournament["title_anchor"],
        "projected_matches_total": tournament["projected_matches_total"],
        "group_stage_matches": tournament["group_stage_matches"],
        "knockout_projected_matches": tournament["knockout_projected_matches"],
        "group_table": tournament["group_table"],
        "qualified_thirds": tournament["qualified_thirds"],
        "bracket": tournament["bracket"],
        "monte_carlo": tournament["monte_carlo"],
        "market_validation": tournament["market_validation"],
        "goal_scale_sanity": tournament["goal_scale_sanity"],
        "sanity_checks": tournament["sanity_checks"],
        "teams": tournament["teams"],
    }


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


if __name__ == "__main__":
    main()
