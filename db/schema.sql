CREATE TABLE IF NOT EXISTS raw_snapshots (
  id BIGSERIAL PRIMARY KEY,
  source TEXT NOT NULL,
  endpoint TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  payload JSONB NOT NULL,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source, endpoint, payload_hash)
);

CREATE TABLE IF NOT EXISTS teams (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  group_code TEXT,
  fifa_code TEXT,
  flag_code TEXT,
  elo NUMERIC,
  attack NUMERIC,
  defence NUMERIC,
  form_index NUMERIC,
  injury_impact NUMERIC,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fixtures (
  id TEXT PRIMARY KEY,
  match_number INTEGER UNIQUE,
  stage TEXT NOT NULL,
  group_code TEXT,
  kickoff_utc TIMESTAMPTZ NOT NULL,
  venue TEXT,
  city TEXT,
  home_team_id TEXT REFERENCES teams(id),
  away_team_id TEXT REFERENCES teams(id),
  status TEXT NOT NULL DEFAULT 'scheduled',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS odds_snapshots (
  id BIGSERIAL PRIMARY KEY,
  match_id TEXT NOT NULL REFERENCES fixtures(id),
  bookmaker TEXT NOT NULL,
  market_type TEXT NOT NULL,
  line NUMERIC,
  price_home NUMERIC,
  price_draw NUMERIC,
  price_away NUMERIC,
  captured_at TIMESTAMPTZ NOT NULL,
  source_payload_id BIGINT REFERENCES raw_snapshots(id)
);

CREATE INDEX IF NOT EXISTS idx_odds_match_market_line
  ON odds_snapshots(match_id, market_type, line, captured_at DESC);

CREATE TABLE IF NOT EXISTS model_runs (
  id BIGSERIAL PRIMARY KEY,
  model_version TEXT NOT NULL,
  generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  as_of TIMESTAMPTZ NOT NULL,
  config JSONB NOT NULL,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS match_predictions (
  id BIGSERIAL PRIMARY KEY,
  model_run_id BIGINT NOT NULL REFERENCES model_runs(id),
  match_id TEXT NOT NULL REFERENCES fixtures(id),
  lambda_home NUMERIC NOT NULL,
  lambda_away NUMERIC NOT NULL,
  p_home NUMERIC NOT NULL,
  p_draw NUMERIC NOT NULL,
  p_away NUMERIC NOT NULL,
  p_over_2_5 NUMERIC NOT NULL,
  p_btts NUMERIC NOT NULL,
  scoreline_matrix JSONB NOT NULL,
  UNIQUE (model_run_id, match_id)
);

CREATE TABLE IF NOT EXISTS handicap_predictions (
  id BIGSERIAL PRIMARY KEY,
  model_run_id BIGINT NOT NULL REFERENCES model_runs(id),
  match_id TEXT NOT NULL REFERENCES fixtures(id),
  line NUMERIC NOT NULL,
  side TEXT NOT NULL CHECK (side IN ('home', 'away')),
  win NUMERIC NOT NULL,
  half_win NUMERIC NOT NULL,
  push NUMERIC NOT NULL,
  half_loss NUMERIC NOT NULL,
  loss NUMERIC NOT NULL,
  fair_decimal_odds NUMERIC,
  market_decimal_odds NUMERIC,
  expected_return NUMERIC,
  UNIQUE (model_run_id, match_id, line, side)
);

