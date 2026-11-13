import { Component, computed, inject, output } from '@angular/core';
import { DataService } from '../data/data.service';
import { complement, pct } from '../shared/format';
import { short } from '../shared/event';
import { UiStateService } from '../ui/ui-state.service';
import { POIS } from '../map/geometry';

/**
 * Botonera al costado del mapa: un botón por punto de interés (lugar + sección), vista completa
 * y pantalla completa. En móvil pasa a una fila con scroll horizontal debajo del mapa.
 */
@Component({
  selector: 'app-dock',
  template: `
    <!-- Probabilidad de la serie: fuera del mapa para no tapar el terreno. -->
    @if (data.prediction(); as p) {
      <section class="prob glass violet" aria-label="Probabilidad de la serie">
        <span class="eyebrow">Probabilidad de que {{ p.team_a }} gane la serie</span>
        <strong class="big">{{ pct(p.p_series_a, 1) }}</strong>
        <div class="bar" aria-hidden="true">
          <span class="a" [style.width.%]="p.p_series_a * 100"></span>
          <span class="b"></span>
        </div>
        <div class="teams mono">
          <span class="ta">{{ short(p.team_a) }} {{ pct(p.p_series_a, 1) }}</span>
          <span class="tb">{{ pct(complement(p.p_series_a), 1) }} {{ short(p.team_b) }}</span>
        </div>
        <span class="likely mono">Más probable: {{ top().score }} ({{ pct(top().p, 0) }})</span>
      </section>
    }
    <nav class="dock glass violet" aria-label="Secciones del mapa">
      <button type="button" class="slot" [class.active]="!ui.activePoi()" (click)="ui.select(null)" aria-label="Vista completa del mapa (M)">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 3 H21 V21 H3 Z M3 21 L21 3" /></svg>
        <span class="txt"><span class="place">Mapa completo</span></span>
        <span class="key mono">M</span>
      </button>
      <span class="sep" aria-hidden="true"></span>
      @for (p of pois; track p.id; let i = $index) {
        <button
          type="button"
          class="slot"
          [class]="'slot ' + p.accent"
          [class.active]="ui.activePoi() === p.id"
          [attr.aria-pressed]="ui.activePoi() === p.id"
          [attr.aria-label]="p.place + ': ' + p.title"
          (click)="ui.select(ui.activePoi() === p.id ? null : p.id)"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true"><path [attr.d]="p.icon" /></svg>
          <span class="txt">
            <span class="place">{{ p.place }}</span>
            <span class="title mono">{{ p.title }}</span>
          </span>
          <span class="key mono">{{ i + 1 }}</span>
        </button>
      }
      <span class="sep" aria-hidden="true"></span>
      <button type="button" class="slot" (click)="fullscreen.emit()" aria-label="Pantalla completa (F)">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 9 V3 H9 M15 3 H21 V9 M21 15 V21 H15 M9 21 H3 V15" /></svg>
        <span class="txt"><span class="place">Pantalla completa</span></span>
        <span class="key mono">F</span>
      </button>
    </nav>
  `,
  styles: `
    :host {
      display: flex;
      flex-direction: column;
      gap: 10px;
      height: 100%;
      min-height: 0;
    }
    .prob {
      flex: none;
      order: 2;
      display: grid;
      gap: 4px;
      padding: 12px 14px;
      border-radius: 16px;
      .eyebrow {
        font-size: 10.5px;
      }
      .big {
        font-family: var(--f-title);
        font-size: 40px;
        line-height: 1;
        color: var(--gold-2);
        text-shadow: 0 0 18px rgba(232, 182, 76, 0.45);
      }
      .bar {
        display: flex;
        height: 6px;
        border-radius: 999px;
        overflow: hidden;
        margin-top: 4px;
        .a {
          background: linear-gradient(90deg, var(--gold), var(--gold-2));
        }
        .b {
          flex: 1;
          background: linear-gradient(90deg, var(--cyan-2), var(--cyan));
        }
      }
      .teams {
        display: flex;
        justify-content: space-between;
        gap: 6px;
        font-size: 10.5px;
        white-space: nowrap;
        .ta {
          color: var(--gold-2);
        }
        .tb {
          color: var(--cyan-2);
        }
      }
      .likely {
        font-size: 10.5px;
        color: var(--ink-3);
      }
    }
    .dock {
      flex: 0 1 auto;
      min-height: 0;
      display: flex;
      flex-direction: column;
      gap: 3px;
      padding: 8px;
      border-radius: 16px;
      overflow-y: auto;
      scrollbar-width: none;
    }
    .sep {
      height: 1px;
      background: var(--line);
      margin: 4px 6px;
      flex: none;
    }
    .slot {
      --c: var(--violet-2);
      position: relative;
      flex: none;
      display: flex;
      align-items: center;
      gap: 12px;
      width: 100%;
      min-height: 42px;
      padding: 4px 30px 4px 10px;
      border-radius: 11px;
      border: 1px solid transparent;
      background: transparent;
      cursor: pointer;
      text-align: left;
      transition: background 0.2s, border-color 0.2s, transform 0.2s;
      &.gold {
        --c: var(--gold-2);
      }
      &.cyan {
        --c: var(--cyan-2);
      }
      svg {
        flex: none;
        width: 20px;
        height: 20px;
        fill: none;
        stroke: var(--c);
        stroke-width: 1.8;
        stroke-linecap: round;
        stroke-linejoin: round;
      }
      .txt {
        display: grid;
        gap: 1px;
        min-width: 0;
      }
      .place {
        font-family: var(--f-title);
        font-weight: 700;
        font-size: 14px;
        color: var(--ink);
        white-space: nowrap;
      }
      .title {
        font-size: 11px;
        color: var(--c);
        white-space: nowrap;
      }
      .key {
        position: absolute;
        top: 50%;
        right: 10px;
        transform: translateY(-50%);
        font-size: 10px;
        color: var(--ink-3);
      }
      &:hover {
        background: rgba(255, 255, 255, 0.05);
        transform: translateX(2px);
      }
      &:focus-visible {
        outline: 2px solid var(--violet-2);
        outline-offset: 1px;
      }
      &.active {
        background: color-mix(in srgb, var(--c) 14%, transparent);
        border-color: color-mix(in srgb, var(--c) 55%, transparent);
      }
    }
    // Móvil: fila horizontal con scroll; la probabilidad va compacta antes de los botones.
    @media (max-width: 860px) {
      :host {
        flex-direction: row;
        align-items: stretch;
        height: auto;
        gap: 6px;
      }
      .prob {
        order: 0;
        padding: 6px 10px;
        gap: 2px;
        .big {
          font-size: 24px;
        }
        .teams,
        .likely,
        .bar {
          display: none;
        }
      }
      .dock {
        flex-direction: row;
        flex: 1 1 auto;
        min-width: 0;
        overflow-x: auto;
        overflow-y: hidden;
      }
      .sep {
        width: 1px;
        height: 30px;
        margin: auto 4px;
      }
      .slot {
        width: auto;
        &:hover {
          transform: none;
        }
      }
    }
  `,
})
export class DockComponent {
  protected readonly ui = inject(UiStateService);
  protected readonly pois = POIS;
  protected readonly data = inject(DataService);
  protected readonly pct = pct;
  protected readonly complement = complement;
  protected readonly short = short;
  /** Marcador exacto más probable de la serie. */
  protected readonly top = computed(() => {
    const scores = this.data.prediction()?.scores ?? [];
    return scores.reduce((a, b) => (b.p > a.p ? b : a), scores[0] ?? { score: '—', p: 0 });
  });
  readonly fullscreen = output<void>();
}
