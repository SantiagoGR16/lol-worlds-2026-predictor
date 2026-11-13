// Parámetros del modelo que la web cita en sus textos.
// Copiados de config.yaml (y de side_choice.parquet para la regla de lados), que no se publica
// en assets. `model-facts.spec.ts` comprueba que coinciden con config.yaml: si cambias config,
// el test falla hasta que actualices este archivo.

export const ELO = {
  /** Elo inicial de cada equipo (elo.initial). */
  initial: 1500,
  /** Puntos en juego por mapa (elo.k). */
  k: 16,
  /** Multiplicador de K en MSI y Mundial (elo.k_international). */
  kInternational: 4,
  /** Puntos de ventaja del lado azul (elo.blue_bonus). */
  blueBonus: 30,
  /** Al cambiar de año: elo = media + factor·(elo − media) (elo.season_regression). */
  seasonRegression: 0.75,
} as const;

export const SIM = {
  /** Repeticiones del bootstrap para el margen de error (simulation.n_bootstrap). */
  nBootstrap: 200,
  /** P(Gen.G en azul) en el mapa 1 (simulation.map1_p_team_blue). */
  map1Blue: 0.5,
} as const;

/**
 * Elección del perdedor en mapas 2+ de un Bo5 en 2026 (data/processed/side_choice.parquet,
 * contexto "mapa2+"). Rojo = rojo sin FP + rojo con FP; FP = azul con FP + rojo con FP.
 */
export const LOSER_CHOICE = {
  redNoFp: 0.2699,
  redFp: 0.4945,
  blueNoFp: 0.1033,
  blueFp: 0.1323,
} as const;

export const loserRed = (): number => LOSER_CHOICE.redNoFp + LOSER_CHOICE.redFp;
export const loserFirstPick = (): number => LOSER_CHOICE.redFp + LOSER_CHOICE.blueFp;

/** "1 de cada N": N entero más cercano a 1/p (p > 0). */
export function oneIn(p: number): number {
  return Math.max(1, Math.round(1 / p));
}
