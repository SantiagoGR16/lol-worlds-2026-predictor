import {
  AfterViewInit,
  Component,
  DestroyRef,
  ElementRef,
  computed,
  effect,
  inject,
  signal,
  untracked,
  viewChild,
} from '@angular/core';
import { gsap } from 'gsap';
import { DataService } from '../data/data.service';
import { UiStateService } from '../ui/ui-state.service';
import { pct } from '../shared/format';
import { short } from '../shared/event';
import { USE_IMAGES, picSrc, slug } from '../shared/pic';
import {
  BASE_A,
  BASE_B,
  BOUNDARY,
  CAMPS,
  FULL_VIEW,
  LANES,
  MAP_IMAGE,
  MAP_IMAGE_TRANSFORM,
  PIT_N,
  PIT_S,
  POIS,
  Poi,
  ROLE_LANE,
  RIVER,
  ROLE_SPOTS,
  ViewBox,
  cameraFor,
  fit,
  front,
  roleView,
  iso,
} from './geometry';
import { Role } from '../data/models';
import { ROLE_LABEL } from '../shared/format';

const ROLES: Role[] = ['top', 'jng', 'mid', 'bot', 'sup'];
/** Letras de los círculos, como en la referencia: T(op) J(ungla) M(id) B(ot) S(oporte). */
const ROLE_LETTER: Record<Role, string> = { top: 'T', jng: 'J', mid: 'M', bot: 'B', sup: 'S' };

interface Ping {
  id: number;
  x: number;
  y: number;
}

/** Mapa táctico: SVG original a pantalla completa con cámara animada (GSAP sobre el viewBox). */
@Component({
  selector: 'app-map',
  templateUrl: './map.html',
  styleUrl: './map.scss',
})
export class MapComponent implements AfterViewInit {
  protected readonly data = inject(DataService);
  protected readonly ui = inject(UiStateService);
  private readonly destroyRef = inject(DestroyRef);

  private readonly svg = viewChild.required<ElementRef<SVGSVGElement>>('svg');

  // Geometría estática para la plantilla.
  protected readonly useImage = USE_IMAGES;
  protected readonly mapImage = MAP_IMAGE;
  protected readonly mapImageTransform = MAP_IMAGE_TRANSFORM;
  /** Logo de un equipo (img/equipos, aportados por el usuario; ver img/LEEME.md). */
  protected logo(team: string): string {
    return `assets/img/equipos/${slug(team)}.png`;
  }
  protected readonly boundary = BOUNDARY;
  protected readonly lanes = LANES;
  protected readonly river = RIVER;
  protected readonly pits = [PIT_N, PIT_S];
  protected readonly camps = CAMPS;
  protected readonly baseA = BASE_A;
  protected readonly baseB = BASE_B;
  protected readonly pois = POIS;
  protected readonly gridLines = Array.from({ length: 9 }, (_, i) => (i + 1) * 10).flatMap((v) => {
    const a = iso(v, 0), b = iso(v, 100), c = iso(0, v), d = iso(100, v);
    return [
      { x1: a.x, y1: a.y, x2: b.x, y2: b.y },
      { x1: c.x, y1: c.y, x2: d.x, y2: d.y },
    ];
  });

  // Datos -> frente de energía en el río.
  protected readonly pA = computed(() => this.data.prediction()?.p_series_a ?? 0.5);
  protected readonly teamA = computed(() => this.data.prediction()?.team_a ?? '');
  protected readonly teamB = computed(() => this.data.prediction()?.team_b ?? '');
  // La línea divisoria va siempre en la mitad (el río); la probabilidad se muestra en el panel lateral.
  protected readonly fr = computed(() => front(0.5));
  /** Polígonos de territorio (dorado del lado A, cian del lado B), recortados al cuadrado. */
  protected readonly territory = computed(() => {
    const { mid: m, d, n } = this.fr();
    const L = 2000;
    const pt = (sd: number, sn: number) => `${m.x + sd * d.x + sn * n.x},${m.y + sd * d.y + sn * n.y}`;
    return { gold: `${pt(-L, 0)} ${pt(L, 0)} ${pt(L, -L)} ${pt(-L, -L)}`, cyan: `${pt(-L, 0)} ${pt(L, 0)} ${pt(L, L)} ${pt(-L, L)}` };
  });
  /** Extremos de la banda del frente, alargados (el recorte al cuadrado los corta). */
  protected readonly frontBand = computed(() => {
    const { a, b, d, mid: m, n } = this.fr();
    return {
      x1: a.x - 80 * d.x, y1: a.y - 80 * d.y, x2: b.x + 80 * d.x, y2: b.y + 80 * d.y,
      gx1: m.x - 40 * n.x, gy1: m.y - 40 * n.y, gx2: m.x + 40 * n.x, gy2: m.y + 40 * n.y,
    };
  });
  protected readonly frontLabel = computed(() => pct(this.pA()));
  protected readonly short = short;

  /** Círculos de jugador (T/J/M/B/S) con el nombre real del draft del Mundial y su foto. */
  protected readonly markers = computed(() => {
    const players = this.data.draft()?.players ?? {};
    const out: { side: 'a' | 'b'; role: Role; letter: string; at: { x: number; y: number }; name: string; team: string; photo: string | null }[] = [];
    for (const [side, team] of [['a', this.teamA()], ['b', this.teamB()]] as const) {
      for (const role of ROLES) {
        const name = Object.entries(players).find(([, p]) => p.team === team && p.role === role)?.[0] ?? '';
        // Foto: img/jugadores/<slug>.webp (recortes de assets/players aportados por el usuario).
        const photo = name ? picSrc('jugadores', name) : null;
        out.push({ side, role, letter: ROLE_LETTER[role], at: ROLE_SPOTS[side][role], name, team, photo });
      }
    }
    return out;
  });

  protected readonly roleLabel = ROLE_LABEL;

  /** Clic en un jugador: abre Scouting y lleva la cámara a su rol (los dos jugadores). */
  protected selectPlayer(role: Role, ev: Event): void {
    ev.stopPropagation();
    this.ui.focus(role);
  }

  /** Línea iluminada: la del POI activo o la del rol bajo el cursor (scouting). */
  protected readonly hotLane = computed(() => {
    const role = this.ui.hoveredRole() ?? this.ui.spotRole();
    if (role) return ROLE_LANE[role];
    return this.ui.active()?.lane ?? null;
  });

  protected readonly pings = signal<Ping[]>([]);
  private pingId = 0;

  private cam: ViewBox = { ...FULL_VIEW };
  private tween: gsap.core.Tween | null = null;
  private aspect = 16 / 9;

  constructor() {
    // Cámara: cada cambio de POI (o de modo móvil) anima el viewBox.
    effect(() => {
      const poi = this.ui.active();
      const role = this.ui.focusRole();
      const mobile = this.ui.mobile();
      // Con un rol elegido en Scouting, la cámara encuadra a los jugadores de ese rol.
      const target = poi && role ? { ...poi, ...roleView(role) } : poi;
      untracked(() => this.moveCamera(target, mobile, true));
    });
  }

  ngAfterViewInit(): void {
    const el = this.svg().nativeElement;
    const ro = new ResizeObserver(() => {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) {
        this.aspect = r.width / r.height;
        const poi = this.ui.active(), role = this.ui.focusRole();
        this.moveCamera(poi && role ? { ...poi, ...roleView(role) } : poi, this.ui.mobile(), false);
      }
    });
    ro.observe(el);
    this.destroyRef.onDestroy(() => {
      ro.disconnect();
      this.tween?.kill();
    });
  }

  private apply(v: ViewBox): void {
    this.svg().nativeElement.setAttribute('viewBox', `${v.x} ${v.y} ${v.w} ${v.h}`);
    this.ui.viewBox.set({ ...v });
  }

  private moveCamera(poi: Poi | null, mobile: boolean, animate: boolean): void {
    const target = poi ? cameraFor(poi, this.aspect, mobile) : fit(FULL_VIEW, this.aspect);
    this.tween?.kill();
    if (!animate || this.ui.reducedMotion()) {
      this.cam = target;
      this.apply(target);
      return;
    }
    this.tween = gsap.to(this.cam, {
      ...target,
      duration: 0.9,
      ease: 'power3.inOut',
      onUpdate: () => this.apply(this.cam),
    });
  }

  protected selectPoi(p: Poi, ev?: Event): void {
    ev?.stopPropagation();
    this.addPing(p.at.x, p.at.y);
    this.ui.select(this.ui.activePoi() === p.id ? null : p.id);
  }

  protected onKey(p: Poi, ev: KeyboardEvent): void {
    if (ev.key === 'Enter' || ev.key === ' ') {
      ev.preventDefault();
      this.selectPoi(p);
    }
  }

  /** "Ping" circular en cada clic sobre el mapa (en coordenadas del SVG). */
  protected onPointer(ev: PointerEvent): void {
    const svg = this.svg().nativeElement;
    const ctm = svg.getScreenCTM();
    if (!ctm) return;
    const pt = new DOMPoint(ev.clientX, ev.clientY).matrixTransform(ctm.inverse());
    this.addPing(pt.x, pt.y);
  }

  private addPing(x: number, y: number): void {
    if (this.ui.reducedMotion()) return;
    const id = ++this.pingId;
    this.pings.update((p) => [...p, { id, x, y }]);
    setTimeout(() => this.pings.update((p) => p.filter((q) => q.id !== id)), 900);
  }

  /** Radio del ping proporcional al zoom actual (se ve igual en pantalla). */
  protected readonly pingScale = computed(() => this.ui.viewBox().w / FULL_VIEW.w);
}
