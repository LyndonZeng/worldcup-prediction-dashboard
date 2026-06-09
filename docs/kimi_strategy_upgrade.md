# Kimi Report Strategy Upgrade

This note translates the useful parts of `Kimi_2026_World_Cup_Report.pdf` into the dashboard roadmap. The goal is not to copy its heavy multi-agent format, but to adopt the dimensions that make the product feel credible to football users.

## What To Borrow

1. Data quality first
   - Track provenance, granularity, sample size, and freshness for every metric.
   - Mark proxy data separately from provider-backed data.
   - Trigger graceful degradation when event data, injury data, or odds data is missing.

2. Add readable match-process stats
   - Users expect possession, shots, shots on target, goals scored, goals conceded, xG, and xGA.
   - Add PPDA and press intensity for tactical texture, but keep labels simple.
   - Add set-piece share and cards because they explain upset and handicap risk.

3. Model from score distribution, explain with factors
   - Keep Asian handicap probabilities derived from the scoreline matrix.
   - Use process metrics as explanatory inputs around the score model, not as a separate hand-picked handicap model.
   - Show when data is proxy-derived versus provider-backed.

4. Context matters more in 2026
   - Add travel distance, time-zone/fatigue level, venue altitude, heat/humidity, and host familiarity.
   - Use WBGT or an equivalent heat-stress index once forecast data is available.

5. Player-level risk should be explicit
   - Track key-player dependency, available starters, minutes load, and squad depth.
   - Eventually compute injury impact from player xG/xT, minutes, role, and replacement quality.

6. Market disagreement is a research layer
   - Keep model probability, fair odds, market odds, and model-market divergence.
   - Add calibration and closing-line tracking for research, but do not show staking instructions in the public dashboard.

## V2 Dashboard Modules

- Match radar: 1X2, expected goals, best handicap line, weather tag, confidence.
- Handicap matrix: Asian line, cover probability, half-win/loss, push, fair odds, market odds, edge.
- Technical stats: possession, shots, shots on target, shot quality, xG/xGA, PPDA, press intensity, set-piece xG share.
- Team history: ELO, form, near-term goals for/against, clean-sheet rate, recent record, ELO change.
- Player state: availability, key-player ratings, minutes load, injury risk, squad depth.
- Environment: temperature, humidity, wind, altitude/venue effect, travel fatigue, environment stress.
- Market lab: model-market divergence, source freshness, odds snapshots, closing-line backtest.
- Model health: Brier/log-loss/RPS, calibration curve, data freshness, model disagreement alerts.

## Implementation Boundary

Current seed data is not a real event feed. The dashboard must label process metrics as `proxy` until a real provider is connected. The first implementation adds the schema and UI so the product looks and behaves like a serious football analytics surface while preserving honest data provenance.
