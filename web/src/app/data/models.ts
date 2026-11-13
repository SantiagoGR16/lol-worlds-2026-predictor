// Tipos de los JSON que genera el pipeline de Python (scripts/export_web.py y lolpred.scouting).
// La web solo LEE estos archivos: ningún número se escribe a mano en el código.

export interface ScoreProb {
  score: string;
  p: number;
}

export interface MapProb {
  a_blue: boolean;
  a_first_pick: boolean;
  p_a: number;
}

export interface Prediction {
  team_a: string;
  team_b: string;
  model: string;
  adjustment: string;
  data_date: string;
  generated_at: string;
  p_series_a: number;
  p_series_a_static: number;
  ci: [number, number];
  ci_level: number;
  sigma: number | null;
  n_series_montecarlo: number;
  scores: ScoreProb[];
  scores_static: ScoreProb[];
  maps: MapProb[];
  nota: string;
  day_form?: { sigma: number; sigma_ci: [number, number]; p_series_a_raw: number; nota: string };
}

export interface EloPoint {
  date: string;
  elo: number;
  league: string;
  rival: string;
  result: number;
}

export interface EloHistory {
  nota: string;
  teams: Record<string, { teamid: string; points: EloPoint[]; elo_actual: number; fecha_actual: string }>;
}

export interface TopElo {
  fecha_corte: string;
  nota: string;
  teams: { rank: number; teamname: string; region: string | null; elo: number }[];
}

export interface ShapData {
  modelo: string;
  unidad: string;
  team_a: string;
  team_b: string;
  global: { grupo: string; importancia: number; features: string }[];
  matchup: {
    escenario: string;
    team_a_blue: boolean;
    team_a_first_pick: boolean;
    base_logit: number;
    p: number;
    contribuciones: { grupo: string; shap: number }[];
  }[];
}

export interface ModelRow {
  mundial: string;
  modelo: string;
  calibration: string;
  n_train: number;
  n: number;
  log_loss: number;
  brier: number;
  accuracy: number;
}

export interface BacktestRow {
  grupo: string;
  n: number;
  log_loss: number;
  brier: number;
  accuracy: number;
  p_media_fav: number;
  fav_gana: number;
  barridas_pred: number;
  barridas_real: number;
}

export interface VariantRow {
  grupo: string;
  variante: string;
  n_series: number;
  log_loss: number;
  brier: number;
  nll_marcador: number;
  dif_vs_estatico: number;
  se_dif: number;
}

/** Fila de barridas: las claves de las predicciones llevan acentos y espacios (vienen de pandas). */
export interface SweepRow {
  grupo: string;
  n_series: number;
  barridas_real: number;
  se_real: number;
  [pred: string]: string | number;
}

export interface Metrics {
  mejor_modelo: string;
  regla: string;
  modelos_mapa: ModelRow[];
  backtest_series: BacktestRow[];
  variantes_series: VariantRow[];
  barridas: SweepRow[];
  momentum_bo5: Record<string, string | number>[];
}

export interface MvpPlayer {
  team: string;
  player: string;
  role: Role;
  maps: number;
  kda: number;
  kp: number;
  dpm: number;
  gd15: number | null;
  dmg_share: number;
  mvp_score: number | null;
  mvp_candidate: boolean;
}

export interface Mvp {
  meta: { league: string; year: number; patches: string[]; maps: number; nota: string };
  players: MvpPlayer[];
}

export interface Draft {
  meta: { league: string; year: number; patches: string[]; maps: number; prior_weight: number; prior_patches?: string[]; nota: string };
  players: Record<string, { team: string; role: Role }>;
  picks: Record<string, { champion: string; p: number; n: number; n_year: number }[]>;
  bans_by: Record<string, { champion: string; rate: number; n: number }[]>;
  bans_against: Record<string, { champion: string; rate: number; n: number }[]>;
  presence: { champion: string; presence: number; picks: number; bans: number; maps: number }[];
  crossovers: { team: string; player: string; role: Role; champion: string; p_pick: number; rival: string; rival_ban_rate: number }[];
}

export type Role = 'top' | 'jng' | 'mid' | 'bot' | 'sup';

/** scoreboard.json (lolpred.scoreboard): previa de la final con promedios reales del torneo. */
export interface ScoreboardPlayer {
  player: string;
  role: Role;
  maps: number;
  wins: number;
  kills: number;
  deaths: number;
  assists: number;
  kda: number;
  kp: number | null;
  dmg: number;
  gold: number;
  gpm: number;
  cs: number;
  cs15: number | null;
  vspm: number;
  wards_placed: number;
  wards_killed: number;
  starter: boolean;
  champions: { champion: string; n: number; wins: number }[];
}

export interface ScoreboardTeam {
  teamid: string;
  maps: number;
  wins: number;
  losses: number;
  avg_length_s: number;
  first_blood: number;
  per_game: Record<'kills' | 'deaths' | 'towers' | 'dragons' | 'barons' | 'void_grubs' | 'totalgold', number>;
  players: ScoreboardPlayer[];
}

export interface Scoreboard {
  meta: { league: string; year: number; data_date: string; ref_length_s: number; sigma: number; nota: string };
  team_a: string;
  team_b: string;
  maps: { map: number; p_played: number; p_a_win_if_played: number | null }[];
  teams: Record<string, ScoreboardTeam>;
}

export interface AllData {
  prediction: Prediction;
  elo: EloHistory;
  topElo: TopElo;
  shap: ShapData;
  metrics: Metrics;
  mvp: Mvp;
  draft: Draft;
  scoreboard: Scoreboard;
}
