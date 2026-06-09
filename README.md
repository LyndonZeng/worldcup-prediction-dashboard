# 2026 World Cup Prediction Dashboard

Production-oriented scaffold for an information-only World Cup 2026 prediction dashboard.

The first version focuses on the parts that are hardest to bolt on later:

- scoreline-derived 1X2, totals, BTTS, and Asian handicap probabilities
- exact Asian handicap settlement, including quarter-goal half-win and half-loss cases
- legal-data-source adapters for football-data.org, Open-Meteo, Polymarket, and sportsbook APIs
- API contracts for matches, handicaps, tournament probabilities, model runs, and source health
- a Next.js dashboard that presents model probability, fair odds, market odds, and confidence context

## Strategy Upgrade

The dashboard now follows a richer football-analysis strategy inspired by the reviewed Kimi report:

- add match-process stats users expect in football products: possession, shots, shots on target, goals for/against, xG/xGA, PPDA, pressing, set pieces, and card risk
- separate model inputs from public explanation: Asian handicap probabilities still come from the scoreline matrix, while process stats explain why the model leans a certain way
- label proxy metrics until event-data providers are connected
- track 2026-specific context: travel fatigue, venue/weather stress, altitude, and host familiarity
- keep market data as a model-market divergence layer, not a staking recommendation layer

See `docs/kimi_strategy_upgrade.md` for the V2 product and modeling roadmap.

## Local Development

Backend:

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Full stack:

```bash
docker compose up --build
```

## API Surface

- `GET /api/matches`
- `GET /api/matches/{match_id}/prediction`
- `GET /api/matches/{match_id}/handicaps`
- `GET /api/tournament/probabilities`
- `GET /api/teams/{team_id}`
- `GET /api/model-runs/latest`
- `GET /api/source-health`

## Handicap Rules

The handicap engine treats the line as the handicap applied to the selected side:

- `0`: push on draw
- `-0.25`: split into `0` and `-0.5`
- `-0.75`: split into `-0.5` and `-1`
- integer lines: support win, push, and loss
- positive lines mirror the same logic for underdogs

Fair decimal odds account for pushes and half settlements:

```text
fair_odds = 1 + (loss + 0.5 * half_loss) / (win + 0.5 * half_win)
```

The public product displays probability and model-market difference only. It does not provide staking, bankroll, or betting instructions.

## Verification

```bash
PYTHONPATH=backend python3 -m unittest discover backend/tests
```
