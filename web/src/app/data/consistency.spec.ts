import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { Draft, Metrics, Mvp, Prediction, ShapData } from './models';
import { ELO } from '../shared/model-facts';

// Comprueba que los JSON que lee la web (src/assets/data) son coherentes entre sí,
// para que ninguna sección muestre un % distinto de otra.

const load = <T>(file: string): T =>
  JSON.parse(readFileSync(resolve(process.cwd(), 'src/assets/data', file), 'utf8')) as T;

const pred = load<Prediction>('prediction.json');
const metrics = load<Metrics>('metrics.json');
const shap = load<ShapData>('shap.json');
const mvp = load<Mvp>('mvp.json');
const draft = load<Draft>('draft.json');
// Tipos sueltos: solo se leen unos campos.
const topElo = load<{ teamname: string; elo: number }[] | { teams: { teamname: string; elo: number }[] }>('top_elo.json');
const board = load<{ maps: { map: number; p_played: number; p_a_win_if_played: number }[] }>('scoreboard.json');

const score = (list: { score: string; p: number }[], s: string) => list.find((x) => x.score === s)?.p ?? NaN;
const aWins = (list: { score: string; p: number }[]) =>
  list.filter((x) => Number(x.score[0]) > Number(x.score[2])).reduce((a, x) => a + x.p, 0);
const mapP = (blue: boolean, fp: boolean) =>
  pred.maps.find((m) => m.a_blue === blue && m.a_first_pick === fp)!.p_a;
const eloOf = (team: string) => {
  const rows = Array.isArray(topElo) ? topElo : topElo.teams;
  return rows.find((r) => r.teamname === team)!.elo;
};

describe('prediction.json', () => {
  it('los marcadores suman 1 y cuadran con P(serie)', () => {
    for (const [list, p] of [
      [pred.scores, pred.p_series_a],
      [pred.scores_static, pred.p_series_a_static],
    ] as const) {
      expect(list).toHaveLength(6);
      expect(list.reduce((a, x) => a + x.p, 0)).toBeCloseTo(1, 3);
      expect(Math.abs(aWins(list) - p)).toBeLessThan(0.002);
    }
  });

  it('el intervalo contiene la probabilidad y está en [0, 1]', () => {
    const [lo, hi] = pred.ci;
    expect(lo).toBeLessThanOrEqual(pred.p_series_a);
    expect(hi).toBeGreaterThanOrEqual(pred.p_series_a);
    expect(lo).toBeGreaterThanOrEqual(0);
    expect(hi).toBeLessThanOrEqual(1);
  });

  it('el día sin ajustar es la P(serie) estática', () => {
    expect(pred.day_form?.p_series_a_raw).toBeCloseTo(pred.p_series_a_static, 4);
    expect(pred.day_form?.sigma).toBeCloseTo(pred.sigma ?? NaN, 4);
  });

  it('P(mapa) sale de la fórmula del Elo con los parámetros publicados', () => {
    const a = eloOf(pred.team_a);
    const b = eloOf(pred.team_b);
    const exp = (d: number) => 1 / (1 + 10 ** (-d / 400));
    expect(mapP(true, false)).toBeCloseTo(exp(a + ELO.blueBonus - b), 3);
    expect(mapP(false, false)).toBeCloseTo(exp(a - ELO.blueBonus - b), 3);
  });
});

describe('scoreboard.json', () => {
  it('P(se juega el mapa 4 y 5) cuadra con los marcadores', () => {
    const s = pred.scores;
    const m4 = board.maps.find((m) => m.map === 4)!.p_played;
    const m5 = board.maps.find((m) => m.map === 5)!.p_played;
    expect(m4).toBeCloseTo(1 - score(s, '3-0') - score(s, '0-3'), 3);
    expect(m5).toBeCloseTo(score(s, '3-2') + score(s, '2-3'), 3);
  });
});

describe('metrics.json', () => {
  it('el modelo elegido es el de menor log-loss en el Mundial de validación (2025)', () => {
    const val = metrics.modelos_mapa.filter((r) => r.mundial.includes('2025'));
    const best = val.reduce((a, r) => (r.log_loss < a.log_loss ? r : a));
    expect(best.modelo.startsWith('(a)')).toBe(true);
    expect(metrics.mejor_modelo).toBe(pred.model);
  });

  it('ningún accuracy de mapa supera el 72 % (señal de leakage)', () => {
    for (const r of metrics.modelos_mapa) expect(r.accuracy).toBeLessThan(0.72);
  });

  it('las series de la forma del día son las mismas que cita la nota de la predicción', () => {
    const n = metrics.variantes_series.find((r) => r.grupo.includes('previos'))!.n_series;
    expect(pred.day_form?.nota).toContain(`${n} Bo5`);
  });
});

describe('shap.json', () => {
  it('escenarios del enfrentamiento: azul sin primer pick, rojo con primer pick', () => {
    const blue = shap.matchup.find((m) => m.team_a_blue)!;
    const red = shap.matchup.find((m) => !m.team_a_blue)!;
    expect(blue.team_a_first_pick).toBe(false);
    expect(red.team_a_first_pick).toBe(true);
    expect(blue.p).toBeGreaterThan(red.p);
  });
});

describe('mvp.json y draft.json', () => {
  it('un solo ★ MVP por equipo y es el de mayor puntaje', () => {
    const teams = [...new Set(mvp.players.map((p) => p.team))];
    for (const t of teams) {
      const ps = mvp.players.filter((p) => p.team === t);
      const cands = ps.filter((p) => p.mvp_candidate);
      expect(cands).toHaveLength(1);
      expect(cands[0].mvp_score).toBe(Math.max(...ps.map((p) => p.mvp_score ?? -Infinity)));
    }
  });

  it('% de pick y de ban dentro de [0, 1]', () => {
    for (const c of draft.crossovers) {
      expect(c.p_pick).toBeGreaterThan(0);
      expect(c.p_pick).toBeLessThanOrEqual(1);
      expect(c.rival_ban_rate).toBeLessThanOrEqual(1);
    }
  });
});
