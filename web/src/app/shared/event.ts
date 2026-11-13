// Etiqueta del evento para la pantalla de carga. El texto ("14.11") lo fijó el usuario en el
// encargo de la web; los datos del modelo no traen la fecha de la final.
export const EVENT_LABEL = 'GEN.G vs BLG · FINAL WORLDS 2026 · 14.11';

/** Siglas propias para las insignias (no se usan logos). */
export const TEAM_SHORT: Record<string, string> = {
  'Gen.G': 'GEN',
  'Bilibili Gaming': 'BLG',
};

export const short = (team: string) => TEAM_SHORT[team] ?? team.slice(0, 3).toUpperCase();
