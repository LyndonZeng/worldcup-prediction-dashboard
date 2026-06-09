from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .services import data_store
from .services.predictions import (
    all_matches,
    handicaps_for_fixture,
    model_run,
    prediction_for_fixture,
    tournament_probabilities,
)

app = FastAPI(
    title="World Cup 2026 Prediction Dashboard API",
    version="0.1.0",
    description="Information-only football predictions with Asian handicap probabilities.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/matches")
def matches():
    return {"matches": all_matches()}


@app.get("/api/matches/{match_id}/prediction")
def match_prediction(match_id: str):
    try:
        fixture = data_store.fixture_by_id(match_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="match not found") from exc
    return prediction_for_fixture(fixture)


@app.get("/api/matches/{match_id}/handicaps")
def match_handicaps(
    match_id: str,
    lines: Optional[list[float]] = Query(default=None, description="Home-team Asian handicap lines"),
):
    try:
        fixture = data_store.fixture_by_id(match_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="match not found") from exc
    return handicaps_for_fixture(fixture, lines=lines)


@app.get("/api/tournament/probabilities")
def tournament():
    return tournament_probabilities()


@app.get("/api/teams/{team_id}")
def team(team_id: str):
    try:
        profile = data_store.team_by_id(team_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="team not found") from exc
    return {
        "id": profile.id,
        "name": profile.name,
        "group": profile.group,
        "fifa_code": profile.fifa_code,
        "flag_code": profile.flag_code,
        "elo": profile.elo,
        "attack": profile.attack,
        "defence": profile.defence,
        "form_index": profile.form_index,
        "injury_impact": profile.injury_impact,
    }


@app.get("/api/model-runs/latest")
def latest_model_run():
    return model_run()


@app.get("/api/source-health")
def source_health():
    return {"sources": data_store.source_health()}
