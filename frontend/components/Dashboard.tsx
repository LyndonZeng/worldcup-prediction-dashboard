"use client";

import {
  Activity,
  BarChart3,
  CalendarClock,
  CloudSun,
  Database,
  Gauge,
  LineChart,
  MapPin,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Thermometer,
  Trophy,
  UsersRound,
  Wind
} from "lucide-react";
import {useEffect, useMemo, useState} from "react";
import type {
  AvailabilityProfile,
  DashboardData,
  FactorBreakdown,
  HandicapRow,
  MatchPrediction,
  TacticalProfile,
  TeamFormProfile,
  TeamSummary,
  TournamentTeam
} from "../lib/types";

type DetailTab = "handicap" | "stats" | "model" | "history" | "players" | "sources";

export function Dashboard({initialData}: {initialData: DashboardData}) {
  const [data, setData] = useState(initialData);
  const [query, setQuery] = useState("");
  const [group, setGroup] = useState("ALL");
  const [selectedId, setSelectedId] = useState(initialData.matches[0]?.match_id ?? "");
  const [detailTab, setDetailTab] = useState<DetailTab>("handicap");

  useEffect(() => {
    let mounted = true;
    async function hydrateFromApi() {
      const apiBase = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";
      try {
        const [matches, tournament, health, modelRun] = await Promise.all([
          fetch(`${apiBase}/api/matches`).then((response) => response.ok ? response.json() : null),
          fetch(`${apiBase}/api/tournament/probabilities`).then((response) => response.ok ? response.json() : null),
          fetch(`${apiBase}/api/source-health`).then((response) => response.ok ? response.json() : null),
          fetch(`${apiBase}/api/model-runs/latest`).then((response) => response.ok ? response.json() : null)
        ]);
        if (mounted && matches?.matches && tournament?.teams && health?.sources && modelRun?.model_version) {
          setData({
            matches: matches.matches,
            tournament,
            sources: health.sources,
            modelRun
          });
        }
      } catch {
        // Keep the seed data visible when the API is not reachable.
      }
    }
    hydrateFromApi();
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (data.matches.length && !data.matches.some((match) => match.match_id === selectedId)) {
      setSelectedId(data.matches[0].match_id);
    }
  }, [data.matches, selectedId]);

  const groups = useMemo(
    () => ["ALL", ...Array.from(new Set(data.matches.map((match) => match.fixture.group))).sort()],
    [data.matches]
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return data.matches.filter((match) => {
      const inGroup = group === "ALL" || match.fixture.group === group;
      const inQuery =
        !q ||
        match.home_team.name.toLowerCase().includes(q) ||
        match.away_team.name.toLowerCase().includes(q) ||
        match.fixture.city.toLowerCase().includes(q) ||
        match.fixture.venue.toLowerCase().includes(q);
      return inGroup && inQuery;
    });
  }, [data.matches, group, query]);

  const selected = data.matches.find((match) => match.match_id === selectedId) ?? filtered[0] ?? data.matches[0];
  const topTitle = data.tournament.teams[0];
  const marketCount = data.matches.reduce(
    (count, match) => count + match.handicap_preview.filter((row) => row.market_status === "available").length,
    0
  );
  const averageConfidence = selected ? confidenceScore(selected) : 0;
  const liveSources = data.sources.filter((source) => source.status !== "planned").length;

  return (
    <main className="shell">
      <section className="commandDeck">
        <div className="brandBlock">
          <div className="brandMark">
            <Trophy size={22} />
          </div>
          <div>
            <p className="eyebrow">2026 WORLD CUP MODEL ROOM</p>
            <h1>预测数据控制台</h1>
            <p className="deckCopy">胜平负、比分分布、亚洲让球、球员健康、历史形态与天气因子统一展示。</p>
          </div>
        </div>
        <div className="heroTelemetry" aria-label="model telemetry">
          <div className="signalPlate">
            <span>MODEL</span>
            <strong>{pct(averageConfidence)}</strong>
            <em>confidence</em>
          </div>
          <div className="hostStrip" aria-label="world cup host cues">
            <HostChip label="USA" sub="11 venues" />
            <HostChip label="MEX" sub="3 venues" />
            <HostChip label="CAN" sub="2 venues" />
          </div>
          <div className="statusPills">
            <span>{marketCount} handicap markets</span>
            <span>{liveSources}/{data.sources.length} data sources</span>
          </div>
        </div>
      </section>

      <section className="controlSurface">
        <label className="searchBox">
          <Search size={17} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索球队、城市或球场"
          />
        </label>
        <div className="segments" aria-label="group filter">
          {groups.map((item) => (
            <button
              className={item === group ? "active" : ""}
              key={item}
              onClick={() => setGroup(item)}
              type="button"
            >
              {item === "ALL" ? "全部" : item}
            </button>
          ))}
        </div>
      </section>

      <section className="metrics">
        <Metric icon={<CalendarClock size={18} />} label="样例赛程" value={`${data.matches.length} 场`} sub="结构适配全量 104 场" />
        <Metric icon={<SlidersHorizontal size={18} />} label="亚洲盘口" value={`${marketCount} 条`} sub="含半赢、走盘、公平赔率" />
        <Metric icon={<Trophy size={18} />} label="最高夺冠" value={topTitle ? pct(topTitle.title_probability) : "-"} sub={topTitle?.team ?? "等待模拟"} />
        <Metric icon={<Gauge size={18} />} label="当前置信度" value={pct(averageConfidence)} sub="由市场、伤病、天气完整度估计" />
      </section>

      <section className="workspace">
        <aside className="matchList">
          <div className="sectionHead">
            <BarChart3 size={18} />
            <h2>比赛雷达</h2>
            <span>{filtered.length}</span>
          </div>
          <div className="matchStack">
            {filtered.map((match) => (
              <MatchButton
                key={match.match_id}
                match={match}
                selected={selected?.match_id === match.match_id}
                onClick={() => setSelectedId(match.match_id)}
              />
            ))}
          </div>
        </aside>

        {selected && (
          <article className="detail">
            <MatchHero match={selected} />
            <ProbabilityBars match={selected} />

            <div className="tabs">
              <TabButton active={detailTab === "handicap"} onClick={() => setDetailTab("handicap")} label="盘口矩阵" />
              <TabButton active={detailTab === "stats"} onClick={() => setDetailTab("stats")} label="技术统计" />
              <TabButton active={detailTab === "model"} onClick={() => setDetailTab("model")} label="模型因子" />
              <TabButton active={detailTab === "history"} onClick={() => setDetailTab("history")} label="球队历史" />
              <TabButton active={detailTab === "players"} onClick={() => setDetailTab("players")} label="球员天气" />
              <TabButton active={detailTab === "sources"} onClick={() => setDetailTab("sources")} label="数据源" />
            </div>

            {detailTab === "handicap" && <HandicapTable match={selected} />}
            {detailTab === "stats" && <TechnicalStatsPanel match={selected} />}
            {detailTab === "model" && <ModelPanel match={selected} modelRun={data.modelRun} />}
            {detailTab === "history" && <HistoryPanel match={selected} />}
            {detailTab === "players" && <PlayersWeatherPanel match={selected} />}
            {detailTab === "sources" && <SourcePanel sources={data.sources} />}
          </article>
        )}

        {selected && (
          <aside className="insightRail">
            <PanelTitle icon={<Sparkles size={17} />} title="赛前情报" value={selected.fixture.group + "组"} />
            <FactorPanel match={selected} compact />
            <WeatherCard match={selected} />
            <AvailabilityCard
              home={selected.home_team}
              away={selected.away_team}
              homeAvailability={selected.availability.home}
              awayAvailability={selected.availability.away}
            />
          </aside>
        )}
      </section>

      <section className="lowerGrid">
        <div className="panel">
          <PanelTitle icon={<LineChart size={18} />} title="夺冠概率" value={`${data.tournament.n_simulations.toLocaleString()} sims`} />
          <div className="titleTable">
            {data.tournament.teams.slice(0, 10).map((team, index) => (
              <TournamentRow key={team.team_id} team={team} rank={index + 1} />
            ))}
          </div>
        </div>
        <div className="panel">
          <PanelTitle icon={<Database size={18} />} title="数据源健康" value={`${data.sources.length} sources`} />
          <SourcePanel sources={data.sources} compact />
        </div>
      </section>
    </main>
  );
}

function HostChip({label, sub}: {label: string; sub: string}) {
  return (
    <div className="hostChip">
      <strong>{label}</strong>
      <span>{sub}</span>
    </div>
  );
}

function Metric({icon, label, value, sub}: {icon: React.ReactNode; label: string; value: string; sub: string}) {
  return (
    <div className="metric">
      <div className="metricIcon">{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{sub}</small>
    </div>
  );
}

function MatchButton({match, selected, onClick}: {match: MatchPrediction; selected: boolean; onClick: () => void}) {
  const marketRows = match.handicap_preview.filter((row) => row.market_status === "available").length;
  return (
    <button className={`matchRow ${selected ? "selected" : ""}`} onClick={onClick} type="button">
      <span className="matchMeta">#{match.fixture.match_number} · {match.fixture.group}组 · {formatDate(match.fixture.kickoff_utc)}</span>
      <span className="teamLine">
        <TeamInline team={match.home_team} />
        <strong>{pct(match.p_home)}</strong>
      </span>
      <span className="teamLine">
        <TeamInline team={match.away_team} />
        <strong>{pct(match.p_away)}</strong>
      </span>
      <span className="matchBadges">
        <em>{formatLine(bestMainLine(match))}</em>
        <em>{marketRows ? `${marketRows} 市场` : "模型公平盘"}</em>
        <em>{match.weather.condition}</em>
      </span>
    </button>
  );
}

function MatchHero({match}: {match: MatchPrediction}) {
  return (
    <header className="matchHero">
      <div className="heroMeta">
        <p className="eyebrow">MATCH #{match.fixture.match_number}</p>
        <h2>
          <span>{match.home_team.name}</span>
          <em>vs</em>
          <span>{match.away_team.name}</span>
        </h2>
        <div className="venueLine">
          <MapPin size={15} />
          <span>{formatDate(match.fixture.kickoff_utc)} · {match.fixture.venue} · {match.fixture.city}</span>
        </div>
      </div>
      <div className="scoreLens">
        <Flag code={match.home_team.flag_code} name={match.home_team.name} large />
        <div>
          <strong>{match.lambda_home.toFixed(2)} : {match.lambda_away.toFixed(2)}</strong>
          <span>预期进球</span>
        </div>
        <Flag code={match.away_team.flag_code} name={match.away_team.name} large />
      </div>
    </header>
  );
}

function ProbabilityBars({match}: {match: MatchPrediction}) {
  const home = Math.max(4, match.p_home * 100);
  const draw = Math.max(4, match.p_draw * 100);
  const away = Math.max(4, match.p_away * 100);
  return (
    <div className="probBlock">
      <div className="probLabels">
        <span>{match.home_team.name} {pct(match.p_home)}</span>
        <span>平局 {pct(match.p_draw)}</span>
        <span>{match.away_team.name} {pct(match.p_away)}</span>
      </div>
      <div className="probBar" aria-label="1X2 probabilities">
        <i className="home" style={{width: `${home}%`}} />
        <i className="draw" style={{width: `${draw}%`}} />
        <i className="away" style={{width: `${away}%`}} />
      </div>
    </div>
  );
}

function TabButton({active, onClick, label}: {active: boolean; onClick: () => void; label: string}) {
  return (
    <button className={active ? "active" : ""} onClick={onClick} type="button">
      {label}
    </button>
  );
}

function HandicapTable({match}: {match: MatchPrediction}) {
  return (
    <div className="tableWrap">
      <table className="handicapTable">
        <thead>
          <tr>
            <th>主队盘口</th>
            <th>{match.home_team.name}</th>
            <th>{match.away_team.name}</th>
            <th>走盘</th>
            <th>公平赔率</th>
            <th>市场赔率</th>
            <th>EV</th>
            <th>模型倾向</th>
          </tr>
        </thead>
        <tbody>
          {match.handicap_preview.map((row) => (
            <HandicapTableRow key={`${match.match_id}-${row.line}`} row={row} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function HandicapTableRow({row}: {row: HandicapRow}) {
  const lean = row.lean === "home" ? "主队" : row.lean === "away" ? "客队" : "观察";
  return (
    <tr>
      <td className="mono strongCell">{formatLine(row.line)}</td>
      <td>
        <strong>{pct(row.home.positive_probability)}</strong>
        <small>半赢 {pct(row.home.half_win)} · 半输 {pct(row.home.half_loss)}</small>
      </td>
      <td>
        <strong>{pct(row.away.positive_probability)}</strong>
        <small>半赢 {pct(row.away.half_win)} · 半输 {pct(row.away.half_loss)}</small>
      </td>
      <td>{pct(row.home.push)}</td>
      <td>
        <span className="mono">{odds(row.home.fair_decimal_odds)}</span>
        <small>客 {odds(row.away.fair_decimal_odds)}</small>
      </td>
      <td>
        <span className="mono">{row.market_status === "missing" ? "暂无市场" : odds(row.home.market_decimal_odds)}</span>
        <small>{row.market_status === "missing" ? row.source : `客 ${odds(row.away.market_decimal_odds)}`}</small>
      </td>
      <td>
        <span className={evClass(row.home.expected_return)}>{ev(row.home.expected_return)}</span>
        <small>客 {ev(row.away.expected_return)}</small>
      </td>
      <td>
        <span className={`lean ${row.lean}`}>{lean}</span>
      </td>
    </tr>
  );
}

function ModelPanel({match, modelRun}: {match: MatchPrediction; modelRun: DashboardData["modelRun"]}) {
  return (
    <div className="modelStack">
      <div className="modelGrid">
        <InfoTile label="预期进球" value={`${match.lambda_home.toFixed(2)} : ${match.lambda_away.toFixed(2)}`} />
        <InfoTile label="大 2.5" value={pct(match.p_over_2_5)} />
        <InfoTile label="双方进球" value={pct(match.p_btts)} />
        <InfoTile label="置信度" value={pct(confidenceScore(match))} />
        <InfoTile label="主队修正" value={multiplier(match.model_inputs.home_goal_multiplier)} />
        <InfoTile label="客队修正" value={multiplier(match.model_inputs.away_goal_multiplier)} />
        <InfoTile label="总进球修正" value={multiplier(match.model_inputs.total_goal_multiplier)} />
        <InfoTile label="综合边际" value={signed(match.model_inputs.weighted_context_edge)} />
        <InfoTile wide label="高概率比分" value={match.top_scorelines.map((item) => `${item.score} ${pct(item.probability)}`).join(" · ")} />
        <InfoTile wide label="模型版本" value={modelRun.model_version} />
      </div>
      <FactorPanel match={match} />
      <div className="noteBand">
        <ShieldCheck size={16} />
        <span>{modelRun.public_boundary}</span>
      </div>
    </div>
  );
}

function HistoryPanel({match}: {match: MatchPrediction}) {
  return (
    <div className="splitGrid">
      <TeamHistoryCard team={match.home_team} form={match.team_form.home} side="home" />
      <TeamHistoryCard team={match.away_team} form={match.team_form.away} side="away" />
    </div>
  );
}

function TeamHistoryCard({team, form, side}: {team: TeamSummary; form: TeamFormProfile; side: "home" | "away"}) {
  return (
    <div className={`teamCard ${side}`}>
      <div className="teamCardTop">
        <TeamInline team={team} />
        <strong>{form.last_10}</strong>
      </div>
      <div className="statGrid">
        <InfoTile label="ELO" value={String(Math.round(form.elo))} />
        <InfoTile label="状态指数" value={signed(form.form_index)} />
        <InfoTile label="近似 xG" value={form.xg_for.toFixed(2)} />
        <InfoTile label="近似 xGA" value={form.xg_against.toFixed(2)} />
        <InfoTile label="进球" value={form.goals_for.toFixed(1)} />
        <InfoTile label="失球" value={form.goals_against.toFixed(1)} />
      </div>
      <div className="meterLine">
        <span>零封率</span>
        <div className="miniBar">
          <i style={{width: `${Math.max(3, form.clean_sheet_rate * 100)}%`}} />
        </div>
        <em>{pct(form.clean_sheet_rate)}</em>
      </div>
    </div>
  );
}

function TechnicalStatsPanel({match}: {match: MatchPrediction}) {
  return (
    <div className="modelStack">
      <div className="splitGrid">
        <TechnicalSide team={match.home_team} profile={match.tactical_profile.home} />
        <TechnicalSide team={match.away_team} profile={match.tactical_profile.away} />
      </div>
      <div className="noteBand">
        <Activity size={16} />
        <span>{match.tactical_profile.source} · {match.tactical_profile.data_quality}</span>
      </div>
    </div>
  );
}

function TechnicalSide({team, profile}: {team: TeamSummary; profile: TacticalProfile}) {
  return (
    <div className="teamCard">
      <div className="teamCardTop">
        <TeamInline team={team} />
        <strong>{profile.possession_pct.toFixed(1)}%</strong>
      </div>
      <div className="statGrid">
        <InfoTile label="近18月进球" value={profile.goals_scored_18m.toFixed(1)} />
        <InfoTile label="近18月失球" value={profile.goals_conceded_18m.toFixed(1)} />
        <InfoTile label="控球率" value={`${profile.possession_pct.toFixed(1)}%`} />
        <InfoTile label="射门" value={profile.shots_per_game.toFixed(1)} />
        <InfoTile label="射正" value={profile.shots_on_target_per_game.toFixed(1)} />
        <InfoTile label="单脚射门质量" value={profile.shot_quality.toFixed(3)} />
        <InfoTile label="xG / xGA" value={`${profile.xg_per_game.toFixed(2)} / ${profile.xga_per_game.toFixed(2)}`} />
        <InfoTile label="PPDA" value={profile.ppda.toFixed(1)} />
        <InfoTile label="定位球xG占比" value={pct(profile.set_piece_xg_share)} />
        <InfoTile label="黄/红牌率" value={`${profile.yellow_card_rate.toFixed(2)} / ${profile.red_card_rate.toFixed(2)}`} />
        <InfoTile label="阵容深度" value={profile.squad_depth_score.toFixed(1)} />
        <InfoTile label="旅程疲劳" value={fatigueText(profile.travel_fatigue_level)} />
      </div>
      <div className="meterLine">
        <span>高压强度</span>
        <div className="miniBar">
          <i style={{width: `${Math.max(3, profile.press_intensity_idx)}%`}} />
        </div>
        <em>{profile.press_intensity_idx.toFixed(1)}</em>
      </div>
      <div className="meterLine">
        <span>环境压力</span>
        <div className="miniBar">
          <i style={{width: `${Math.max(3, profile.environment_stress * 100)}%`}} />
        </div>
        <em>{pct(profile.environment_stress)}</em>
      </div>
      <div className="contextNotes">
        <span>预测旅程 {profile.projected_travel_km.toLocaleString()} km</span>
      </div>
    </div>
  );
}

function PlayersWeatherPanel({match}: {match: MatchPrediction}) {
  return (
    <div className="splitGrid">
      <AvailabilityCard
        home={match.home_team}
        away={match.away_team}
        homeAvailability={match.availability.home}
        awayAvailability={match.availability.away}
        expanded
      />
      <WeatherCard match={match} expanded />
    </div>
  );
}

function AvailabilityCard({
  home,
  away,
  homeAvailability,
  awayAvailability,
  expanded = false
}: {
  home: TeamSummary;
  away: TeamSummary;
  homeAvailability: AvailabilityProfile;
  awayAvailability: AvailabilityProfile;
  expanded?: boolean;
}) {
  return (
    <div className="subPanel">
      <PanelTitle icon={<UsersRound size={17} />} title="球员状态" value="availability" />
      <AvailabilitySide team={home} profile={homeAvailability} expanded={expanded} />
      <AvailabilitySide team={away} profile={awayAvailability} expanded={expanded} />
    </div>
  );
}

function AvailabilitySide({team, profile, expanded}: {team: TeamSummary; profile: AvailabilityProfile; expanded: boolean}) {
  const players = expanded ? profile.key_players : profile.key_players.slice(0, 2);
  return (
    <div className="availabilitySide">
      <div className="availabilityHead">
        <TeamInline team={team} />
        <span className={`risk ${profile.risk}`}>{riskText(profile.risk)}</span>
      </div>
      <div className="availabilityStats">
        <span>{profile.available_starters}/11 首发可用</span>
        <span>负荷 {pct(profile.minutes_load)}</span>
      </div>
      <div className="playerList">
        {players.map((player) => (
          <div className="playerRow" key={`${team.id}-${player.name}`}>
            <span>{player.name}</span>
            <em>{player.role}</em>
            <strong>{pct(player.rating)}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}

function WeatherCard({match, expanded = false}: {match: MatchPrediction; expanded?: boolean}) {
  return (
    <div className="subPanel">
      <PanelTitle icon={<CloudSun size={17} />} title="天气与场地" value={match.weather.condition} />
      <div className="weatherGrid">
        <WeatherStat icon={<Thermometer size={16} />} label="温度" value={`${match.weather.temperature_c}°C`} />
        <WeatherStat icon={<Activity size={16} />} label="湿度" value={`${match.weather.humidity_pct}%`} />
        <WeatherStat icon={<Wind size={16} />} label="风速" value={`${match.weather.wind_kph} km/h`} />
        <WeatherStat icon={<MapPin size={16} />} label="场地" value={match.weather.venue_effect} />
      </div>
      {expanded && (
        <div className="contextNotes">
          {(match.context.notes.length ? match.context.notes : ["无特殊赛前修正"]).map((note) => (
            <span key={note}>{note}</span>
          ))}
        </div>
      )}
    </div>
  );
}

function WeatherStat({icon, label, value}: {icon: React.ReactNode; label: string; value: string}) {
  return (
    <div className="weatherStat">
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function FactorPanel({match, compact = false}: {match: MatchPrediction; compact?: boolean}) {
  return (
    <div className={compact ? "factorPanel compact" : "factorPanel"}>
      {!compact && <PanelTitle icon={<Gauge size={17} />} title="模型因子拆解" value="home edge" />}
      {match.factor_breakdown.map((factor) => (
        <FactorRow key={factor.factor} factor={factor} home={match.home_team.name} away={match.away_team.name} />
      ))}
    </div>
  );
}

function FactorRow({factor, home, away}: {factor: FactorBreakdown; home: string; away: string}) {
  const left = Math.max(0, -factor.home_edge) * 50;
  const right = Math.max(0, factor.home_edge) * 50;
  return (
    <div className="factorRow">
      <div>
        <span>{factor.factor}</span>
        <em>{factor.home_edge >= 0 ? home : away} · 权重 {pct(factor.weight)}</em>
      </div>
      <div className="factorTrack" aria-label={factor.factor}>
        <i className="awayEdge" style={{width: `${left}%`}} />
        <b />
        <i className="homeEdge" style={{width: `${right}%`}} />
      </div>
      <strong>{signed(factor.home_edge)}</strong>
    </div>
  );
}

function SourcePanel({sources, compact = false}: {sources: DashboardData["sources"]; compact?: boolean}) {
  return (
    <div className={compact ? "sourceList compact" : "sourceList"}>
      {sources.map((source) => (
        <div className="sourceRow" key={source.source}>
          <Activity size={15} />
          <div>
            <strong>{source.source}</strong>
            <span>{source.purpose}</span>
          </div>
          <em>{source.status}</em>
        </div>
      ))}
    </div>
  );
}

function PanelTitle({icon, title, value}: {icon: React.ReactNode; title: string; value: string}) {
  return (
    <div className="sectionHead">
      {icon}
      <h2>{title}</h2>
      <span>{value}</span>
    </div>
  );
}

function TournamentRow({team, rank}: {team: TournamentTeam; rank: number}) {
  const market = team.market_probability == null ? "暂无市场" : `市场 ${pct(team.market_probability)}`;
  const delta = team.model_market_delta == null ? "" : ` · 差异 ${signed(team.model_market_delta)}`;
  return (
    <div className="titleRow">
      <span className="rank">{rank}</span>
      <Flag code={team.flag_code} name={team.team} />
      <div className="titleTeamCell">
        <strong>{team.team}</strong>
        <em>{market}{delta}</em>
      </div>
      <div className="miniBar">
        <i style={{width: `${Math.max(2, team.title_probability * 100)}%`}} />
      </div>
      <span className="mono">{pct(team.title_probability)}</span>
    </div>
  );
}

function InfoTile({label, value, wide = false}: {label: string; value: string; wide?: boolean}) {
  return (
    <div className={wide ? "infoTile wide" : "infoTile"}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function TeamInline({team}: {team: TeamSummary}) {
  return (
    <span className="inlineTeam">
      <Flag code={team.flag_code} name={team.name} />
      <span>{team.name}</span>
    </span>
  );
}

function Flag({code, name, large = false}: {code: string; name: string; large?: boolean}) {
  return <img className={large ? "flag large" : "flag"} src={`https://flagcdn.com/w40/${code}.png`} alt={`${name} flag`} loading="lazy" />;
}

function confidenceScore(match: MatchPrediction) {
  if (match.confidence_profile?.score) return match.confidence_profile.score;
  const marketShare = match.handicap_preview.filter((row) => row.market_status === "available").length / Math.max(1, match.handicap_preview.length);
  const injuryPenalty = Math.min(0.14, match.home_team.injury_impact + match.away_team.injury_impact);
  const weatherBoost = match.weather ? 0.05 : 0;
  return Math.max(0.45, Math.min(0.91, 0.58 + marketShare * 0.22 + weatherBoost - injuryPenalty));
}

function bestMainLine(match: MatchPrediction) {
  const main = match.handicap_preview.find((row) => row.line === -0.5 || row.line === 0 || row.line === 0.5);
  return main?.line ?? match.handicap_preview[0]?.line ?? 0;
}

function riskText(value: string) {
  if (value === "elevated") return "偏高";
  if (value === "medium") return "中等";
  return "低风险";
}

function fatigueText(value: string) {
  if (value === "very_high") return "极高";
  if (value === "high") return "高";
  if (value === "medium") return "中";
  return "低";
}

function pct(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${(value * 100).toFixed(1)}%`;
}

function odds(value: number | null | undefined) {
  if (!value) return "-";
  return value.toFixed(2);
}

function ev(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)}%`;
}

function evClass(value: number | null | undefined) {
  if (value === null || value === undefined) return "ev";
  if (value >= 0.04) return "ev positive";
  if (value <= -0.04) return "ev negative";
  return "ev";
}

function signed(value: number) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}`;
}

function multiplier(value: number) {
  return `${value >= 1 ? "+" : ""}${((value - 1) * 100).toFixed(1)}%`;
}

function formatLine(value: number) {
  if (value > 0) return `+${value}`;
  return `${value}`;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Shanghai"
  }).format(new Date(value));
}
