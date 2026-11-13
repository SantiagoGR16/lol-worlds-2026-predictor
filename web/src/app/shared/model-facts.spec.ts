import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { ELO, LOSER_CHOICE, SIM, loserFirstPick, loserRed } from './model-facts';

// Los tests se ejecutan desde web/: config.yaml está un nivel arriba.
const config = readFileSync(resolve(process.cwd(), '../config.yaml'), 'utf8');

/** Valor numérico de `clave:` dentro de la sección de primer nivel `seccion:` (YAML simple). */
function yamlNum(seccion: string, clave: string): number {
  const ini = config.search(new RegExp(`^${seccion}:`, 'm'));
  expect(ini, `sección ${seccion}`).toBeGreaterThanOrEqual(0);
  const resto = config.slice(ini + seccion.length + 1);
  const fin = resto.search(/^\S/m);
  const bloque = fin === -1 ? resto : resto.slice(0, fin);
  const m = bloque.match(new RegExp(`^\\s+${clave}:\\s*([-0-9.]+)`, 'm'));
  expect(m, `${seccion}.${clave}`).not.toBeNull();
  return Number(m![1]);
}

describe('model-facts coincide con config.yaml', () => {
  it('Elo', () => {
    expect(ELO.initial).toBe(yamlNum('elo', 'initial'));
    expect(ELO.k).toBe(yamlNum('elo', 'k'));
    expect(ELO.kInternational).toBe(yamlNum('elo', 'k_international'));
    expect(ELO.blueBonus).toBe(yamlNum('elo', 'blue_bonus'));
    expect(ELO.seasonRegression).toBe(yamlNum('elo', 'season_regression'));
  });

  it('Simulación y scouting', () => {
    expect(SIM.nBootstrap).toBe(yamlNum('simulation', 'n_bootstrap'));
    expect(SIM.map1Blue).toBe(yamlNum('simulation', 'map1_p_team_blue'));
    const draft = JSON.parse(readFileSync(resolve(process.cwd(), 'src/assets/data/draft.json'), 'utf8'));
    expect(draft.meta.prior_weight).toBe(yamlNum('scouting', 'prior_weight'));
  });

  it('elección del perdedor: probabilidades que suman 1', () => {
    const total = Object.values(LOSER_CHOICE).reduce((a, b) => a + b, 0);
    expect(total).toBeCloseTo(1, 3);
    expect(loserRed()).toBeGreaterThan(0.5);
    expect(loserFirstPick()).toBeGreaterThan(0.5);
  });
});
