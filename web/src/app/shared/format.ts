// Formato numérico en español (coma decimal). Los valores vienen siempre de los JSON.

const nf = (d: number) => new Intl.NumberFormat('es-ES', { minimumFractionDigits: d, maximumFractionDigits: d });

/** 0.6555 -> "65,6 %" */
export function pct(x: number | null | undefined, digits = 1): string {
  if (x === null || x === undefined || Number.isNaN(x)) return '—';
  return `${nf(digits).format(x * 100)} %`;
}

/**
 * Complemento coherente con el redondeo a 1 decimal en %: si A se muestra como 65,6 %,
 * B se muestra como 34,4 % (y no 34,5 %, que sumaría 100,1 %).
 */
export function complement(a: number): number {
  return 1 - Math.round(a * 1000) / 1000;
}

/** Número con decimales fijos: 0.6524 -> "0,652" */
export function num(x: number | null | undefined, digits = 3): string {
  if (x === null || x === undefined || Number.isNaN(x)) return '—';
  return nf(digits).format(x);
}

/** Con signo: 0.03 -> "+0,030" */
export function signed(x: number | null | undefined, digits = 3): string {
  if (x === null || x === undefined || Number.isNaN(x)) return '—';
  return `${x >= 0 ? '+' : '−'}${nf(digits).format(Math.abs(x))}`;
}

/** "2026-11-09" -> "9 nov 2026" */
export function date(iso: string): string {
  // "2026-11-09" sin hora se interpretaría en UTC (y en América caería al día anterior):
  // se fuerza la hora local.
  const d = new Date(iso.length === 10 ? `${iso}T00:00` : iso.replace(' ', 'T'));
  return new Intl.DateTimeFormat('es-ES', { day: 'numeric', month: 'short', year: 'numeric' }).format(d);
}

export const ROLE_LABEL: Record<string, string> = {
  top: 'Superior',
  jng: 'Jungla',
  mid: 'Central',
  bot: 'Tirador',
  sup: 'Soporte',
};
