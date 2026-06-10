export type TeamSummary = {
  id: string;
  name: string;
  group: string;
  fifa_code: string;
  flag_code: string;
  elo: number;
  attack: number;
  defence: number;
  form_index: number;
  injury_impact: number;
};

export type HandicapSide = {
  win: number;
  half_win: number;
  push: number;
  half_loss: number;
  loss: number;
  positive_probability: number;
  effective_win_probability: number;
  fair_decimal_odds: number | null;
  market_decimal_odds: number | null;
  expected_return: number | null;
};

export type HandicapRow = {
  line: number;
  home: HandicapSide;
  away: HandicapSide;
  source: string;
  captured_at: string | null;
  market_status: "available" | "missing";
  lean: "home" | "away" | "none";
};

export type MatchPrediction = {
  match_id: string;
  model_version: string;
  generated_at: string;
  home_team: TeamSummary;
  away_team: TeamSummary;
  fixture: {
    id: string;
    match_number: number;
    stage: string;
    group: string;
    kickoff_utc: string;
    venue: string;
    city: string;
  };
  context: {
    notes: string[];
    home_mult: number;
    away_mult: number;
  };
  team_form: {
    home: TeamFormProfile;
    away: TeamFormProfile;
    elo_gap: number;
    data_source: string;
  };
  tactical_profile: {
    home: TacticalProfile;
    away: TacticalProfile;
    source: string;
    data_quality: string;
  };
  availability: {
    home: AvailabilityProfile;
    away: AvailabilityProfile;
    source: string;
    updated_at: string;
  };
  weather: {
    temperature_c: number;
    humidity_pct: number;
    wind_kph: number;
    condition: string;
    venue_effect: string;
    source: string;
  };
  factor_breakdown: FactorBreakdown[];
  model_inputs: {
    weighted_context_edge: number;
    home_goal_multiplier: number;
    away_goal_multiplier: number;
    total_goal_multiplier: number;
    applied_to: string;
  };
  lambda_home: number;
  lambda_away: number;
  p_home: number;
  p_draw: number;
  p_away: number;
  p_over_2_5: number;
  p_under_2_5: number;
  p_btts: number;
  top_scorelines: Array<{score: string; probability: number}>;
  handicap_preview: HandicapRow[];
};

export type TeamFormProfile = {
  elo: number;
  form_index: number;
  last_10: string;
  goals_for: number;
  goals_against: number;
  xg_for: number;
  xg_against: number;
  clean_sheet_rate: number;
};

export type TacticalProfile = {
  goals_scored_18m: number;
  goals_conceded_18m: number;
  xg_per_game: number;
  xga_per_game: number;
  shots_per_game: number;
  shots_on_target_per_game: number;
  shot_quality: number;
  possession_pct: number;
  ppda: number;
  press_intensity_idx: number;
  set_piece_xg_share: number;
  yellow_card_rate: number;
  red_card_rate: number;
  squad_depth_score: number;
  projected_travel_km: number;
  travel_fatigue_level: string;
  environment_stress: number;
};

export type AvailabilityProfile = {
  risk: "low" | "medium" | "elevated" | string;
  available_starters: number;
  minutes_load: number;
  key_players: Array<{
    name: string;
    role: string;
    status: string;
    rating: number;
  }>;
};

export type FactorBreakdown = {
  factor: string;
  home_edge: number;
  weight: number;
};

export type TournamentTeam = {
  team_id: string;
  team: string;
  flag_code: string;
  group: string;
  title_probability: number;
  market_probability?: number | null;
  model_market_delta?: number | null;
  market_source?: string | null;
  reach_final: number;
  reach_r32: number;
};

export type SourceHealth = {
  source: string;
  status: string;
  freshness: string;
  purpose: string;
};

export type ModelRun = {
  model_version: string;
  generated_at: string;
  score_model: string;
  handicap_engine: string;
  calibration_status: string;
  public_boundary: string;
};

export type DashboardData = {
  matches: MatchPrediction[];
  tournament: {teams: TournamentTeam[]; n_simulations: number; generated_at: string};
  sources: SourceHealth[];
  modelRun: ModelRun;
};
