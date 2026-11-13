import { Component, computed, inject } from '@angular/core';
import { DataService } from '../data/data.service';
import { CountUpDirective } from '../shared/count-up';
import { EloExplainer } from '../shared/elo-explainer';
import { num, pct } from '../shared/format';

/** Mapa a mapa: P(ganar un mapa) según lado (y primer pick si el modelo lo usa), con el Elo explicado. */
@Component({
  selector: 'app-per-map',
  imports: [CountUpDirective, EloExplainer],
  template: `
    @if (pred(); as p) {
      <p class="lead">
        ¿Qué tan probable es que <strong class="gold-text">{{ p.team_a }}</strong> gane <em>un</em> mapa? Depende de dos
        cosas: qué tan fuerte es cada equipo (su Elo) y de qué lado del mapa juega.
      </p>

      <div class="grid">
        @for (side of sides; track side.blue) {
          <div class="col panel" [class]="'col panel ' + (side.blue ? 'blue' : 'red')">
            <h3>{{ p.team_a }} en lado {{ side.label }}</h3>
            <div class="row">
              <span class="lbl">Gana el mapa</span>
              <span class="num v" [appCountUp]="val(side.blue, false)">0</span>
              <div class="meter" aria-hidden="true">
                <div class="fill" [style.width.%]="val(side.blue, false) * 100"></div>
                <div class="half"></div>
              </div>
            </div>
            @if (!fpIgnored()) {
              <div class="row">
                <span class="lbl">Con primer pick</span>
                <span class="num v" [appCountUp]="val(side.blue, true)">0</span>
                <div class="meter" aria-hidden="true">
                  <div class="fill" [style.width.%]="val(side.blue, true) * 100"></div>
                  <div class="half"></div>
                </div>
              </div>
            }
          </div>
        }
      </div>
      <div class="panel diff">
        <span class="eyebrow">Jugar en azul vale</span>
        <span class="num">+{{ num((val(true, false) - val(false, false)) * 100, 1) }} pts</span>
        <span class="note">
          En los datos, el lado azul gana algo más seguido, así que {{ p.team_a }} tiene más opciones cuando le toca azul.
          @if (fpIgnored()) { Tener o no el primer pick no cambia estos números en este modelo. }
        </span>
      </div>

      <app-elo-explainer />
    }
  `,
  styles: `
    .lead em {
      font-style: italic;
    }
    .lead {
      margin: 0 0 12px;
      color: var(--ink-2);
    }
    .grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      margin-bottom: 10px;
    }
    .col h3 {
      font-size: 14px;
      margin-bottom: 8px;
    }
    .col.blue h3::before,
    .col.red h3::before {
      content: '';
      display: inline-block;
      width: 9px;
      height: 9px;
      margin-right: 7px;
      border-radius: 2px;
      vertical-align: 1px;
    }
    .col.blue h3::before {
      background: #5b8cff;
    }
    .col.red h3::before {
      background: #ff6b7a;
    }
    .row {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 4px 8px;
      margin-bottom: 10px;
    }
    .lbl {
      font-size: 12.5px;
      color: var(--ink-2);
    }
    .v {
      font-size: 17px;
      color: var(--gold-2);
    }
    .meter {
      grid-column: 1 / -1;
      position: relative;
      height: 8px;
      border-radius: 99px;
      background: rgba(35, 213, 255, 0.25);
      overflow: hidden;
    }
    .fill {
      height: 100%;
      background: linear-gradient(90deg, var(--gold), var(--gold-2));
      transition: width 0.9s ease;
    }
    .half {
      position: absolute;
      left: 50%;
      top: 0;
      bottom: 0;
      width: 1px;
      background: #fff;
      opacity: 0.6;
    }
    .diff {
      display: flex;
      gap: 10px;
      align-items: baseline;
      flex-wrap: wrap;
      margin-bottom: 8px;
      .num {
        font-size: 18px;
      }
    }
    @media (max-width: 520px) {
      .grid {
        grid-template-columns: 1fr;
      }
    }
  `,
})
export class PerMapSection {

  private readonly data = inject(DataService);
  protected readonly pred = computed(() => this.data.prediction());
  protected readonly pct = pct;
  protected readonly num = num;
  protected readonly sides = [
    { blue: true, label: 'azul' },
    { blue: false, label: 'rojo' },
  ];

  protected val(blue: boolean, fp: boolean): number {
    return this.pred()?.maps.find((m) => m.a_blue === blue && m.a_first_pick === fp)?.p_a ?? 0;
  }

  /** El modelo no distingue el primer pick si las probabilidades con y sin él coinciden. */
  protected readonly fpIgnored = computed(() => {
    const m = this.pred()?.maps ?? [];
    const get = (b: boolean, f: boolean) => m.find((x) => x.a_blue === b && x.a_first_pick === f)?.p_a ?? 0;
    return Math.abs(get(true, true) - get(true, false)) < 1e-4 && Math.abs(get(false, true) - get(false, false)) < 1e-4;
  });
}
