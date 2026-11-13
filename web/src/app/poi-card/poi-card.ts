import { Component, ElementRef, effect, inject, untracked, viewChild } from '@angular/core';
import { gsap } from 'gsap';
import { UiStateService } from '../ui/ui-state.service';
import { POIS, cardSide } from '../map/geometry';
import { HeroSection } from '../sections/hero';
import { ScoresSection } from '../sections/scores';
import { PerMapSection } from '../sections/per-map';
import { EloSection } from '../sections/elo';
import { WhySection } from '../sections/why';
import { ScoutingSection } from '../sections/scouting';
import { MethodSection } from '../sections/method';

/** Tarjeta de cristal del POI activo: entra desde el lado contrario con fade y desenfoque. */
@Component({
  selector: 'app-poi-card',
  imports: [HeroSection, ScoresSection, PerMapSection, EloSection, WhySection, ScoutingSection, MethodSection],
  template: `
    @if (ui.active(); as p) {
      <article
        #card
        class="card glass"
        [class]="'card glass ' + p.accent + ' ' + side()"
        role="dialog"
        aria-modal="false"
        [attr.aria-labelledby]="'card-title-' + p.id"
      >
        <header>
          <div>
            <p class="eyebrow">{{ ui.activeIndex() + 1 }}/{{ total }} · {{ p.title }}</p>
            <h2 [id]="'card-title-' + p.id">{{ p.place }}</h2>
          </div>
          <button type="button" class="close" (click)="ui.select(null)" aria-label="Cerrar y volver al mapa (Esc)">✕</button>
        </header>
        <div class="body">
          @switch (p.id) {
            @case ('nexos') { <app-hero /> }
            @case ('foso-norte') { <app-scores /> }
            @case ('foso-sur') { <app-per-map /><app-elo /> }
            @case ('linea-central') { <app-why /> }
            @case ('linea-inferior') { <app-scouting /> }
            @case ('jungla') { <app-method /> }
          }
        </div>
        <footer>
          <button type="button" (click)="ui.step(-1)" aria-label="POI anterior">← Anterior</button>
          <span class="mono keys">← → · Esc</span>
          <button type="button" (click)="ui.step(1)" aria-label="POI siguiente">Siguiente →</button>
        </footer>
      </article>
    }
  `,
  styles: `
    :host {
      display: contents;
    }
    .card {
      position: fixed;
      z-index: 20;
      top: 84px;
      bottom: 40px;
      width: min(500px, 42vw);
      display: flex;
      flex-direction: column;
      &.right {
        right: 20px;
      }
      &.left {
        // Junto a la botonera de la izquierda (--nav, ver app.ts).
        left: calc(var(--nav, 0px) + 8px);
      }
    }
    header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 10px;
      padding: 16px 18px 10px;
      border-bottom: 1px solid var(--line);
      h2 {
        font-size: 22px;
      }
      p {
        margin: 0 0 2px;
      }
    }
    .close {
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.04);
      border-radius: 10px;
      width: 34px;
      height: 34px;
      cursor: pointer;
      &:hover {
        border-color: var(--glow);
      }
    }
    .body {
      flex: 1;
      overflow: auto;
      padding: 14px 18px;
      scrollbar-width: thin;
    }
    footer {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 10px 14px;
      border-top: 1px solid var(--line);
      button {
        border: 1px solid var(--line);
        background: transparent;
        border-radius: 10px;
        padding: 6px 10px;
        font-size: 12.5px;
        cursor: pointer;
        &:hover {
          border-color: var(--glow);
        }
      }
    }
    .keys {
      font-size: 11px;
      color: var(--ink-3);
    }
    @media (max-width: 860px) {
      .card {
        position: relative;
        top: auto;
        bottom: auto;
        left: auto !important;
        right: auto !important;
        width: auto;
        z-index: auto;
        margin: 0 12px 140px;
      }
      .body {
        overflow: visible;
      }
    }
  `,
})
export class PoiCardComponent {
  protected readonly ui = inject(UiStateService);
  protected readonly total = POIS.length;
  private readonly card = viewChild<ElementRef<HTMLElement>>('card');

  protected side(): string {
    const p = this.ui.active();
    return p ? cardSide(p) : 'right';
  }

  constructor() {
    // Entrada: desde el lado contrario al POI, con fade y desenfoque.
    effect(() => {
      const el = this.card()?.nativeElement;
      const p = this.ui.active();
      if (!el || !p) return;
      untracked(() => {
        if (this.ui.reducedMotion()) return;
        const dx = this.ui.mobile() ? 0 : cardSide(p) === 'right' ? 70 : -70;
        gsap.fromTo(
          el,
          { opacity: 0, x: dx, y: this.ui.mobile() ? 24 : 0, filter: 'blur(10px)' },
          { opacity: 1, x: 0, y: 0, filter: 'blur(0px)', duration: 0.55, ease: 'power3.out', delay: 0.15, clearProps: 'filter' },
        );
      });
    });
  }
}
