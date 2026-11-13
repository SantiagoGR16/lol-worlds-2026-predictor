// Geometría del mapa táctico: vista cenital RECTA de un cuadrado, con la base de Gen.G abajo
// a la izquierda y la de BLG arriba a la derecha, el río en diagonal, 3 líneas y 2 fosos.
// El fondo es la imagen cenital MAP_IMAGE (si USE_IMAGES) o el terreno abstracto original.
//
// Todo se define en coordenadas de "cuadrado" (0..100)² y se lleva al SVG con iso()
// (el nombre se conserva de la versión isométrica; hoy es una escala y un desplazamiento).

export interface Pt {
  x: number;
  y: number;
}

export interface ViewBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

// Escala: el mapa se alarga a lo ancho (x ∈ [-650, 650], y ∈ [0, 1000]) para llenar más pantalla.
// Solo se estiran el fondo y las posiciones; círculos, logos y textos conservan su forma.
const SX = 13;
const SY = 10;

/** Del cuadrado (0..100)² al plano del SVG (vista cenital, sin girar, alargada a lo ancho). */
export function iso(x: number, y: number): Pt {
  return { x: (x - 50) * SX, y: y * SY };
}

const P = (x: number, y: number) => {
  const p = iso(x, y);
  return `${p.x.toFixed(1)} ${p.y.toFixed(1)}`;
};

/**
 * Vista completa: el cuadrado con un margen mínimo (la cabecera y los botones quedan fuera
 * del área del mapa, ver app.ts).
 */
export const FULL_VIEW: ViewBox = { x: -50 * SX - 15, y: -15, w: 100 * SX + 30, h: 100 * SY + 30 };

/**
 * Fondo del mapa: imagen cenital cuadrada (uso privado; ver USE_IMAGES en shared/pic.ts).
 * Ocupa el cuadrado (0..100)²: su esquina inferior izquierda (base azul) cae en BASE_A.
 */
export const MAP_IMAGE = 'assets/map/grieta.jpg';
export const MAP_IMAGE_TRANSFORM = `translate(${-50 * SX} 0) scale(${SX} ${SY})`;

export const BOUNDARY =`M ${P(0, 0)} L ${P(100, 0)} L ${P(100, 100)} L ${P(0, 100)} Z`;

export const BASE_A = iso(7, 93); // Gen.G (abajo a la izquierda)
export const BASE_B = iso(93, 7); // BLG (arriba a la derecha)

// Líneas: superior (borde izquierdo y de arriba), central (diagonal) e inferior (abajo y derecha).
export const LANES = {
  top: `M ${P(9, 91)} L ${P(9, 9)} L ${P(91, 9)}`,
  mid: `M ${P(9, 91)} L ${P(91, 9)}`,
  bot: `M ${P(9, 91)} L ${P(91, 91)} L ${P(91, 9)}`,
} as const;

/** Río en diagonal (arriba-izquierda -> abajo-derecha) con meandros suaves. */
export const RIVER = `M ${P(2, 2)} C ${P(22, 14)}, ${P(38, 44)}, ${P(50, 50)} S ${P(86, 78)}, ${P(98, 98)}`;

export const PIT_N = iso(30, 30);
export const PIT_S = iso(70, 70);

/** Campamentos de jungla (formas abstractas): cuatro cuadrantes entre líneas. */
export const CAMPS: Pt[] = [
  iso(28, 52), iso(22, 70), iso(42, 78), // Gen.G inferior
  iso(52, 28), iso(70, 22), iso(78, 42), // BLG superior
  iso(30, 22), iso(48, 14),              // superior izquierda
  iso(70, 78), iso(86, 52),              // inferior derecha
];

/**
 * Frente de energía según P(A gana la serie): una recta paralela al río (x − y = c) que avanza
 * por la diagonal base A -> base B. Devuelve sus extremos sobre el borde del cuadrado, el punto
 * medio, la dirección de la recta (d), la normal hacia B (n) y dónde va el número.
 */
export interface Front {
  a: Pt;
  b: Pt;
  mid: Pt;
  d: Pt;
  n: Pt;
  label: Pt;
}

export function front(pA: number): Front {
  const cA = 7 - 93; // x − y en la base A
  const c = cA + pA * (-2 * cA);
  const [a, b] = c >= 0 ? [iso(c, 0), iso(100, 100 - c)] : [iso(0, -c), iso(100 + c, 100)];
  // Dirección de la recta (paralela al río) y normal hacia la base B, ya con el estiramiento.
  const len = Math.hypot(SX, SY);
  return {
    a,
    b,
    mid: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 },
    d: { x: SX / len, y: SY / len },
    n: { x: SY / len, y: -SX / len },
    // El número va dentro del mapa, bajo el borde superior, junto al extremo alto del frente.
    label: { x: Math.max(-50 * SX + 150, Math.min(50 * SX - 150, a.x)), y: 64 },
  };
}

/**
 * Posiciones de los 10 jugadores en el mapa (como en la referencia del usuario), en coordenadas
 * del cuadrado. Los centrales se abren un poco sobre su línea para no tapar el punto "Nexos".
 */
export const ROLE_SPOTS: Record<'a' | 'b', Record<'top' | 'jng' | 'mid' | 'bot' | 'sup', Pt>> = {
  a: { top: iso(5.5, 20), jng: iso(15.5, 48.5), mid: iso(37, 63), bot: iso(83, 86.5), sup: iso(86.5, 93) },
  b: { top: iso(12, 11), jng: iso(81.5, 52.4), mid: iso(61, 39), bot: iso(89.5, 80.5), sup: iso(95, 85) },
};

export type RoleKey = 'top' | 'jng' | 'mid' | 'bot' | 'sup';

/**
 * Encuadre de un rol: centro y ancho de cámara que muestran a los dos jugadores de ese rol
 * (bot y soporte comparten la vista: los cuatro de la línea inferior). El ancho deja sitio a la
 * tarjeta, que tapa casi la mitad del mapa en escritorio (los dos jugadores caben en el ~40 % libre).
 */
export function roleView(role: RoleKey): { at: Pt; zoom: number } {
  const roles: RoleKey[] = role === 'bot' || role === 'sup' ? ['bot', 'sup'] : [role];
  const pts = roles.flatMap((r) => [ROLE_SPOTS.a[r], ROLE_SPOTS.b[r]]);
  const xs = pts.map((p) => p.x), ys = pts.map((p) => p.y);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  return {
    at: { x: (x0 + x1) / 2, y: (y0 + y1) / 2 },
    zoom: Math.max((x1 - x0 + 160) / 0.4, (y1 - y0 + 180) * 1.5, 540),
  };
}

export type PoiId = 'nexos' | 'foso-norte' | 'foso-sur' | 'linea-central' | 'linea-inferior' | 'jungla';

/** Ids antiguos que se redirigen (la sección Elo se unió a "Mapa a mapa"). */
export const POI_ALIAS: Record<string, PoiId> = { 'linea-superior': 'foso-sur' };

export interface Poi {
  id: PoiId;
  /** Nombre de la sección (botón y título de la tarjeta). */
  place: string;
  /** Subtítulo: qué muestra la sección. */
  title: string;
  at: Pt;
  /** Ancho del viewBox al hacer zoom (más chico = más zoom). */
  zoom: number;
  /** Ícono genérico (path SVG en una caja de 24x24). */
  icon: string;
  /** Color de acento de la sección. */
  accent: 'gold' | 'cyan' | 'violet';
  /** Línea o zona que se ilumina con este POI. */
  lane?: 'top' | 'mid' | 'bot' | 'jungle' | 'river';
  /** Rol que se destaca en el mapa (los demás jugadores se atenúan). */
  role?: RoleKey;
}

// Íconos propios, geométricos y genéricos (no derivan de ningún juego).
const ICON = {
  crystal: 'M12 2 L19 10 L12 22 L5 10 Z M5 10 H19',
  bars: 'M4 20 V12 M10 20 V6 M16 20 V9 M22 20 V15 M2 20 H24',
  split: 'M3 12 H21 M12 3 V21 M6 6 L18 18',
  wave: 'M2 16 L7 9 L12 13 L17 5 L22 8',
  why: 'M4 20 V14 M9 20 V8 M14 20 V11 M19 20 V4 M3 4 H11',
  people: 'M8 9 a3 3 0 1 0 0.1 0 M16 9 a3 3 0 1 0 0.1 0 M3 20 C4 14 12 14 13 20 M11 20 C12 14 20 14 21 20',
  compass: 'M12 2 a10 10 0 1 0 0.1 0 M15 9 L13 13 L9 15 L11 11 Z',
};

export const POIS: Poi[] = [
  // Nexos: vista amplia (casi todo el mapa cabe junto a la tarjeta).
  { id: 'nexos', place: 'La final', title: 'Quién gana la serie', at: iso(50, 50), zoom: 1150, icon: ICON.crystal, accent: 'violet', lane: 'river' },
  { id: 'foso-norte', place: 'Marcadores', title: '3-0, 3-1, 3-2…', at: PIT_N, zoom: 640, icon: ICON.bars, accent: 'gold', lane: 'river' },
  { id: 'foso-sur', place: 'Mapa a mapa', title: 'Lado, Elo y fuerza en el tiempo', at: PIT_S, zoom: 640, icon: ICON.split, accent: 'cyan', lane: 'river' },
  { id: 'linea-central', place: 'Por qué', title: 'Qué pesa en la predicción', at: iso(28, 72), zoom: 680, icon: ICON.why, accent: 'violet', lane: 'mid' },
  // Scouting: el id se conserva por los enlaces #poi/linea-inferior. Sin rol elegido muestra todo
  // el mapa; un clic en un jugador (o en un rol de la tarjeta) lleva la cámara a ese rol.
  { id: 'linea-inferior', place: 'Jugadores', title: 'MVP, draft y bans', at: iso(50, 50), zoom: 100 * SX + 30, icon: ICON.people, accent: 'cyan' },
  { id: 'jungla', place: 'Metodología', title: 'Cómo se evaluó el modelo', at: iso(50, 50), zoom: 100 * SX + 30, icon: ICON.compass, accent: 'violet' },
];

/** Lado en que entra la tarjeta: el contrario al POI (para no taparlo). */
export function cardSide(p: Poi): 'left' | 'right' {
  return p.at.x > 40 ? 'left' : 'right';
}

/** viewBox de cámara para un POI, dejando hueco para la tarjeta y respetando el aspecto. */
export function cameraFor(p: Poi | null, aspect: number, mobile: boolean): ViewBox {
  if (!p) {
    return fit(FULL_VIEW, aspect);
  }
  const w = mobile ? Math.min(p.zoom * 1.25, FULL_VIEW.w) : p.zoom;
  const h = w / aspect;
  // En escritorio, el POI queda en el centro del espacio libre que deja la tarjeta (~42 %).
  const shift = mobile ? 0 : cardSide(p) === 'right' ? 0.21 * w : -0.21 * w;
  return { x: p.at.x - w / 2 + shift, y: p.at.y - h / 2, w, h };
}

/** Ajusta un viewBox al aspecto del contenedor sin recortar (como "meet"). */
export function fit(v: ViewBox, aspect: number): ViewBox {
  const va = v.w / v.h;
  if (aspect > va) {
    const w = v.h * aspect;
    return { x: v.x - (w - v.w) / 2, y: v.y, w, h: v.h };
  }
  const h = v.w / aspect;
  return { x: v.x, y: v.y - (h - v.h) / 2, w: v.w, h };
}

export const ROLE_LANE: Record<string, Poi['lane']> = {
  top: 'top',
  jng: 'jungle',
  mid: 'mid',
  bot: 'bot',
  sup: 'bot',
};
