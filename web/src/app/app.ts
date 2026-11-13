import { Component, HostListener, computed, inject } from '@angular/core';
import { DataService } from './data/data.service';
import { UiStateService } from './ui/ui-state.service';
import { LoaderComponent } from './loader/loader';
import { MapComponent } from './map/map';
import { PoiCardComponent } from './poi-card/poi-card';
import { MinimapComponent } from './hud/minimap';
import { DockComponent } from './hud/dock';
import { ScoreboardComponent } from './scoreboard/scoreboard';
import { PicComponent } from './shared/pic';
import { POIS, POI_ALIAS, PoiId, cardSide } from './map/geometry';
import { date } from './shared/format';
import { short } from './shared/event';

@Component({
  selector: 'app-root',
  imports: [LoaderComponent, MapComponent, PoiCardComponent, MinimapComponent, DockComponent, ScoreboardComponent, PicComponent],
  template: `
    <div class="backdrop" aria-hidden="true"></div>

    @if (!ui.entered()) {
      <app-loader (enter)="ui.select(null)" />
    }

    <main class="stage" [class.hidden]="!ui.entered()" [attr.aria-hidden]="!ui.entered()">
      <header class="hud-top glass violet">
        @if (data.prediction(); as p) {
          <div class="title">
            <app-pic class="hlogo" kind="equipos" [name]="p.team_a" [fallback]="short(p.team_a)" tone="gold" />
            <h1>{{ p.team_a }} <span class="vs">vs</span> {{ p.team_b }}</h1>
            <app-pic class="hlogo" kind="equipos" [name]="p.team_b" [fallback]="short(p.team_b)" tone="cyan" />
          </div>
          <p class="meta mono">Final Bo5 · datos hasta {{ date(p.data_date) }}</p>
        }
        <div class="tabs" role="tablist" aria-label="Vistas">
          <button type="button" role="tab" id="tab-mapa" aria-controls="panel-mapa"
                  [attr.aria-selected]="ui.tab() === 'mapa'" [class.on]="ui.tab() === 'mapa'" (click)="ui.setTab('mapa')">
            Mapa
          </button>
          <button type="button" role="tab" id="tab-partido" aria-controls="panel-partido"
                  [attr.aria-selected]="ui.tab() === 'partido'" [class.on]="ui.tab() === 'partido'" (click)="ui.setTab('partido')">
            Partido
          </button>
        </div>
        @if (ui.tab() === 'mapa') {
          <p class="help mono" aria-hidden="true">← → recorrer · Esc/M mapa · F pantalla completa</p>
        }
      </header>

      <!-- El mapa queda montado (conserva cámara y POI) y solo se oculta en la otra pestaña. -->
      <div id="panel-mapa" role="tabpanel" aria-labelledby="tab-mapa" class="panel-mapa"
           [class.off]="ui.tab() !== 'mapa'" [attr.aria-hidden]="ui.tab() !== 'mapa'" [attr.inert]="ui.tab() !== 'mapa' ? '' : null">
          <div class="map-wrap">
            <app-map />
          </div>

          <app-poi-card />

          <div class="hud-dock">
            <app-dock (fullscreen)="toggleFullscreen()" />
          </div>
          <!-- El minimapa se va al lado contrario de la tarjeta para no quedar tapado. -->
          <div class="hud-mini" [class.left]="miniLeft()">
            <app-minimap />
          </div>
          <p class="sr-only" aria-live="polite">{{ liveText() }}</p>
      </div>
      @if (ui.tab() === 'partido') {
        <div id="panel-partido" class="page" role="tabpanel" aria-labelledby="tab-partido">
          <app-scoreboard />
        </div>
      }
    </main>

    <footer class="foot">Datos: Oracle's Elixir · Proyecto no afiliado a Riot Games</footer>
  `,
  styles: `
    :host {
      display: block;
      height: 100%;
    }
    .stage {
      position: fixed;
      inset: 0;
      z-index: 1;
      &.hidden {
        visibility: hidden;
      }
    }
    // Escritorio: botonera a la izquierda (--nav) y el mapa en el resto, bajo la cabecera.
    .stage {
      --nav: 250px;
    }
    .map-wrap {
      position: absolute;
      top: 74px;
      left: var(--nav);
      right: 12px;
      bottom: 28px;
    }
    .hud-top {
      position: fixed;
      z-index: 15;
      top: 14px;
      left: 50%;
      transform: translateX(-50%);
      display: flex;
      align-items: center;
      gap: 18px;
      padding: 8px 16px;
      border-radius: 14px;
      max-width: calc(100vw - 32px);
      p {
        margin: 0;
      }
    }
    .hlogo {
      --pic: 34px;
      --pic-radius: 4px;
    }
    .title {
      display: flex;
      align-items: center;
      gap: 10px;
      h1 {
        font-size: 17px;
        white-space: nowrap;
      }
      .vs {
        color: var(--ink-3);
        font-weight: 500;
      }
    }
    .tabs {
      display: inline-flex;
      padding: 3px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.04);
      button {
        border: 0;
        background: none;
        cursor: pointer;
        padding: 4px 14px;
        border-radius: 999px;
        font-family: var(--f-mono);
        font-size: 11.5px;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: var(--ink-2);
        &.on {
          background: linear-gradient(135deg, var(--violet), var(--violet-2));
          color: #120a2b;
          font-weight: 700;
        }
      }
    }
    .panel-mapa.off {
      visibility: hidden;
      // Los hijos con position: fixed (dock, minimapa, tarjeta) también se ocultan.
      * {
        visibility: hidden !important;
      }
    }
    // Pestaña "Partido": página con scroll propio bajo la cabecera fija.
    .page {
      position: absolute;
      inset: 0;
      overflow-y: auto;
      padding-top: 86px;
    }
    .meta,
    .help {
      font-size: 11px;
      color: var(--ink-2);
      white-space: nowrap;
    }
    .help {
      color: var(--ink-3);
    }
    .hud-dock {
      position: fixed;
      z-index: 25;
      top: 84px;
      bottom: 38px;
      left: 16px;
      width: calc(var(--nav) - 28px);
      display: flex;
      flex-direction: column;
    }
    .hud-mini {
      position: fixed;
      z-index: 15;
      right: 18px;
      bottom: 34px;
      &.left {
        right: auto;
        left: calc(var(--nav) + 8px);
      }
    }
    .foot {
      position: fixed;
      z-index: 30;
      left: 0;
      right: 0;
      bottom: 0;
      padding: 6px 12px;
      text-align: center;
      font-size: 11.5px;
      color: var(--ink-2);
      background: linear-gradient(transparent, rgba(5, 7, 13, 0.9) 40%);
    }
    @media (max-width: 1280px) {
      .help {
        display: none;
      }
    }
    @media (max-width: 1100px) {
      .hud-mini {
        display: none;
      }
    }
    // Móvil: el mapa arriba como selector; la tarjeta ocupa el ancho completo debajo.
    @media (max-width: 860px) {
      .stage {
        overflow-y: auto;
      }
      .hud-top {
        position: sticky;
        top: 0;
        left: 0;
        transform: none;
        border-radius: 0 0 14px 14px;
        flex-wrap: wrap;
        gap: 4px 12px;
        max-width: none;
        h1 {
          font-size: 15px;
        }
      }
      .page {
        position: relative;
        inset: auto;
        overflow: visible;
        padding-top: 14px;
      }
      // En móvil el mapa ocupa espacio en el flujo: oculto, se saca para no empujar el marcador.
      .panel-mapa.off {
        display: none;
      }
      .map-wrap {
        position: relative;
        inset: auto;
        // Alto según el ancho: el mapa (1,3:1) ocupa toda la pantalla a lo ancho.
        height: min(calc(100vw / 1.3 + 10px), 72vh);
        min-height: 280px;
      }
      .map-wrap {
        left: 0;
        right: 0;
      }
      .hud-dock {
        top: auto;
        bottom: 28px;
        left: 8px;
        right: 8px;
        width: auto;
        flex-direction: row;
        justify-content: center;
      }
    }
  `,
})
export class App {
  protected readonly data = inject(DataService);
  protected readonly ui = inject(UiStateService);
  protected readonly date = date;
  protected readonly short = short;

  protected readonly miniLeft = computed(() => {
    const p = this.ui.active();
    return !!p && cardSide(p) === 'right';
  });

  protected readonly liveText = computed(() => {
    const p = this.ui.active();
    return p ? `${p.place}: ${p.title}` : 'Vista completa del mapa';
  });

  constructor() {
    this.data.load();
    // Enlaces profundos: #mapa salta la carga; #poi/<id> abre un POI (también para capturas).
    const hash = location.hash.replace(/^#/, '');
    if (hash === 'mapa') {
      this.ui.entered.set(true);
    } else if (hash === 'partido') {
      this.ui.entered.set(true);
      this.ui.tab.set('partido');
    } else if (hash.startsWith('poi/')) {
      const id = (POI_ALIAS[hash.slice(4)] ?? hash.slice(4)) as PoiId;
      if (POIS.some((p) => p.id === id)) {
        this.ui.entered.set(true);
        this.ui.activePoi.set(id);
      }
    }
  }

  /** Enlaces #partido / #mapa escritos a mano o con atrás/adelante del navegador. */
  @HostListener('window:hashchange')
  onHash(): void {
    const hash = location.hash.replace(/^#/, '');
    if (hash === 'partido' && this.ui.tab() !== 'partido') {
      this.ui.setTab('partido');
    } else if (hash === 'mapa' && (this.ui.tab() !== 'mapa' || this.ui.activePoi())) {
      this.ui.select(null);
    } else if (hash.startsWith('poi/')) {
      const id = (POI_ALIAS[hash.slice(4)] ?? hash.slice(4)) as PoiId;
      if (id !== this.ui.activePoi() && POIS.some((p) => p.id === id)) this.ui.select(id);
    }
  }

  @HostListener('document:keydown', ['$event'])
  onKey(ev: KeyboardEvent): void {
    if (!this.ui.entered() || ev.ctrlKey || ev.metaKey || ev.altKey) return;
    const k = ev.key.toLowerCase();
    // En la pestaña "Partido" las flechas y números se dejan al navegador (scroll, tablas).
    if (this.ui.tab() === 'partido' && k !== 'f' && k !== 'm' && k !== 'escape') return;
    if (k === 'arrowright') {
      this.ui.step(1);
    } else if (k === 'arrowleft') {
      this.ui.step(-1);
    } else if (k === 'escape' || k === 'm') {
      this.ui.select(null);
    } else if (k === 'f') {
      this.toggleFullscreen();
    } else if (/^[1-9]$/.test(k) && Number(k) <= POIS.length) {
      this.ui.select(POIS[Number(k) - 1].id);
    } else {
      return;
    }
    ev.preventDefault();
  }

  protected toggleFullscreen(): void {
    if (document.fullscreenElement) {
      void document.exitFullscreen();
    } else {
      void document.documentElement.requestFullscreen?.();
    }
  }
}
