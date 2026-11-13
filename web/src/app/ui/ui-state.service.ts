import { Injectable, computed, signal } from '@angular/core';
import { Role } from '../data/models';
import { POIS, PoiId, ViewBox, FULL_VIEW } from '../map/geometry';

export type Tab = 'mapa' | 'partido';

/** Estado compartido de la interfaz (POI activo, cámara, hover de rol, preferencias). */
@Injectable({ providedIn: 'root' })
export class UiStateService {
  readonly entered = signal(false);
  /** Pestaña visible: el mapa táctico o el marcador de la previa. */
  readonly tab = signal<Tab>('mapa');
  readonly activePoi = signal<PoiId | null>(null);
  readonly hoveredRole = signal<Role | null>(null);
  /** Rol elegido en Scouting (clic en un jugador): la cámara va a ese rol. */
  readonly focusRole = signal<Role | null>(null);
  /** viewBox actual del mapa (lo actualiza la cámara en cada fotograma; lo dibuja el minimapa). */
  readonly viewBox = signal<ViewBox>(FULL_VIEW);

  readonly reducedMotion = signal(matchMedia('(prefers-reduced-motion: reduce)').matches);
  readonly mobile = signal(matchMedia('(max-width: 860px)').matches);

  readonly activeIndex = computed(() => {
    const id = this.activePoi();
    return id ? POIS.findIndex((p) => p.id === id) : -1;
  });
  readonly active = computed(() => POIS.find((p) => p.id === this.activePoi()) ?? null);

  constructor() {
    matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change', (e) => this.reducedMotion.set(e.matches));
    matchMedia('(max-width: 860px)').addEventListener('change', (e) => this.mobile.set(e.matches));
  }

  /** Cambia de pestaña. Volver al mapa restaura su enlace (#mapa o #poi/<id>). */
  setTab(tab: Tab): void {
    this.entered.set(true);
    this.tab.set(tab);
    if (tab === 'partido') {
      history.replaceState(null, '', '#partido');
    } else {
      const id = this.activePoi();
      history.replaceState(null, '', id ? `#poi/${id}` : '#mapa');
    }
  }

  select(id: PoiId | null): void {
    this.entered.set(true);
    this.tab.set('mapa');
    this.activePoi.set(id);
    this.focusRole.set(null);
    // Enlace profundo: #poi/<id> o #mapa (también lo usan las capturas automáticas).
    history.replaceState(null, '', id ? `#poi/${id}` : '#mapa');
  }

  /** Scouting centrado en un rol: abre la tarjeta y lleva la cámara a los dos jugadores. */
  focus(role: Role): void {
    if (this.activePoi() !== 'linea-inferior') this.select('linea-inferior');
    this.focusRole.set(role);
  }

  /** Rol destacado en el mapa: el elegido en Scouting o el del POI activo (Jungla). */
  readonly spotRole = computed<Role | null>(() => this.focusRole() ?? this.active()?.role ?? null);

  step(delta: 1 | -1): void {
    const i = this.activeIndex();
    const next = i < 0 ? (delta > 0 ? 0 : POIS.length - 1) : (i + delta + POIS.length) % POIS.length;
    this.select(POIS[next].id);
  }
}
