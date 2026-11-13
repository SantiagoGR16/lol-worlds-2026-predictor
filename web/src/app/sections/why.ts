import { Component, computed, inject, signal } from '@angular/core';
import { NgxEchartsDirective } from 'ngx-echarts';
import { DataService } from '../data/data.service';
import { UiStateService } from '../ui/ui-state.service';
import { COLORS, axisStyle, baseChart } from '../shared/chart';
import { pct } from '../shared/format';
import { PicComponent } from '../shared/pic';
import { short } from '../shared/event';

/** Por qué: qué datos pesan en el modelo auxiliar (SHAP agrupado), explicado sin tecnicismos. */
@Component({
  selector: 'app-why',
  imports: [NgxEchartsDirective, PicComponent],
  template: `
    @if (shap(); as s) {
      <section class="intro panel">
        <p class="eyebrow">¿Qué mira el modelo para decidir?</p>
        <p>
          Además del Elo, probamos un segundo modelo que mira otras estadísticas de cada equipo en sus últimas
          partidas: oro a los 15 minutos, objetivos, muertes, daño… En esta sección se ve <strong>cuánto pesa cada
          dato</strong> cuando el modelo intenta adivinar quién gana un mapa.
        </p>
        <p>
          La predicción oficial usa <strong>solo el Elo</strong>, porque en los Mundiales anteriores estos datos extra
          no mejoraron el acierto. Igual nos sirven para entender de dónde sale la fuerza de cada equipo.
        </p>
      </section>

      <h3 class="sub">Qué pesa más para ganar un mapa</h3>
      <p class="hint">Porcentaje del peso total en las decisiones del modelo, en los mapas del Mundial.</p>
      <div echarts class="chart g" [options]="globalOpts()"></div>

      <details class="gloss">
        <summary>¿Qué significa cada dato?</summary>
        <dl>
          @for (g of s.global; track g.grupo) {
            <div><dt>{{ g.grupo }}</dt><dd>{{ meaning[g.grupo] ?? '' }}</dd></div>
          }
        </dl>
      </details>

      <div class="head">
        <h3 class="sub">En la final: ¿qué empuja hacia cada lado?</h3>
        <div class="toggle" role="group" [attr.aria-label]="'Lado de ' + s.team_a">
          @for (m of s.matchup; track m.escenario; let i = $index) {
            <button type="button" [attr.aria-pressed]="sel() === i" (click)="sel.set(i)">
              {{ s.team_a }} en {{ m.team_a_blue ? 'azul' : 'rojo' }}
            </button>
          }
        </div>
      </div>
      @if (scen(); as m) {
        <div class="vs">
          <app-pic class="vl" kind="equipos" [name]="s.team_a" [fallback]="short(s.team_a)" tone="gold" />
          <span class="mono">vs</span>
          <app-pic class="vl" kind="equipos" [name]="s.team_b" [fallback]="short(s.team_b)" tone="cyan" />
        </div>
        <p class="scenario">
          Pongamos un mapa de la final con <strong>{{ s.team_a }} en el lado {{ m.team_a_blue ? 'azul' : 'rojo' }}</strong>
          y <strong>{{ m.team_a_first_pick ? s.team_a : s.team_b }}</strong> eligiendo primero en el draft (primer pick).
        </p>
        <ul class="explain">
          <li class="res">
            <span class="k">Resultado</span>
            <span>
              Este modelo le da a {{ s.team_a }} un <strong class="gold-text">{{ pct(m.p) }}</strong> de ganar ese mapa.
              @if (official(m.team_a_blue, m.team_a_first_pick); as o) {
                <span class="mut">(La predicción oficial, que solo usa el Elo, da {{ pct(o) }}.)</span>
              }
            </span>
          </li>
          @if (pushers().forA.length) {
            <li class="a">
              <span class="k"><app-pic class="tl" kind="equipos" [name]="s.team_a" [fallback]="short(s.team_a)" tone="gold" />A favor de {{ s.team_a }}</span>
              <span>
                @for (g of pushers().forA; track g; let last = $last) {
                  <strong>{{ g }}</strong><span class="mut">&nbsp;({{ reason(g, s.team_a) }})</span>{{ last ? '.' : ';' }}
                }
              </span>
            </li>
          }
          @if (pushers().forB.length) {
            <li class="b">
              <span class="k"><app-pic class="tl" kind="equipos" [name]="s.team_b" [fallback]="short(s.team_b)" tone="cyan" />A favor de {{ s.team_b }}</span>
              <span>
                @for (g of pushers().forB; track g; let last = $last) {
                  <strong>{{ g }}</strong><span class="mut">&nbsp;({{ reason(g, s.team_b) }})</span>{{ last ? '.' : ';' }}
                }
              </span>
            </li>
          }
        </ul>
        <p class="how">
          En el gráfico están todos los datos. Las <span class="gold-text">barras doradas</span> (hacia la derecha)
          ayudan a {{ s.team_a }} y las <span class="cyan-text">cian</span> (hacia la izquierda) a {{ s.team_b }}.
          Mientras más larga la barra, más pesa ese dato.
        </p>
        <div echarts class="chart m" [options]="matchupOpts()"></div>
      }
    }
  `,
  styles: `
    .tl {
      --pic: 18px;
      --pic-radius: 3px;
      display: inline-block;
      vertical-align: -4px;
      margin-right: 6px;
    }
    .vs {
      display: flex;
      align-items: center;
      gap: 12px;
      margin: 8px 0 2px;
      color: var(--ink-3);
      font-size: 12px;
    }
    .vl {
      --pic: 40px;
      --pic-radius: 6px;
    }
    .scenario {
      margin: 6px 0 8px;
      font-size: 13.5px;
      line-height: 1.55;
      color: var(--ink-2);
      strong {
        color: var(--ink);
      }
    }
    .explain {
      list-style: none;
      margin: 0 0 10px;
      padding: 0;
      display: grid;
      gap: 6px;
      li {
        display: grid;
        grid-template-columns: 150px 1fr;
        gap: 10px;
        padding: 8px 10px;
        border-radius: 10px;
        background: rgba(255, 255, 255, 0.04);
        border-left: 3px solid var(--violet-2);
        font-size: 13px;
        line-height: 1.5;
        color: var(--ink-2);
        &.a {
          border-left-color: var(--gold-2);
        }
        &.b {
          border-left-color: var(--cyan-2);
        }
      }
      .k {
        font-family: var(--f-mono);
        font-size: 11px;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: var(--ink-3);
        padding-top: 2px;
      }
      strong {
        color: var(--ink);
      }
    }
    .mut {
      color: var(--ink-3);
    }
    .how {
      margin: 0;
      font-size: 12.5px;
      line-height: 1.5;
      color: var(--ink-2);
    }
    @media (max-width: 520px) {
      .explain li {
        grid-template-columns: 1fr;
        gap: 2px;
      }
    }
    .intro {
      padding: 12px 14px;
      margin: 0 0 14px;
      border-color: rgba(157, 123, 255, 0.45);
      background: rgba(157, 123, 255, 0.06);
      p {
        margin: 0 0 8px;
        font-size: 13px;
        line-height: 1.55;
        color: var(--ink-2);
        &:last-child {
          margin-bottom: 0;
        }
      }
      .eyebrow {
        color: var(--violet-2);
      }
      strong {
        color: var(--ink);
      }
    }
    .hint {
      margin: 0;
      font-size: 12px;
      color: var(--ink-3);
    }
    .gloss {
      margin: 4px 0 14px;
      font-size: 12.5px;
      summary {
        cursor: pointer;
        color: var(--violet-2);
        font-weight: 600;
      }
      dl {
        display: grid;
        gap: 5px;
        margin: 8px 0 0;
      }
      dl div {
        display: grid;
        grid-template-columns: 150px 1fr;
        gap: 10px;
      }
      dt {
        color: var(--ink);
        font-weight: 600;
      }
      dd {
        margin: 0;
        color: var(--ink-2);
      }
    }
    .summary {
      margin: 6px 0 0;
      font-size: 13.5px;
      line-height: 1.55;
      color: var(--ink-2);
    }
    .legend {
      display: flex;
      flex-wrap: wrap;
      gap: 6px 16px;
      margin: 4px 0 0;
      font-size: 12px;
      color: var(--ink-2);
      span {
        display: inline-flex;
        align-items: center;
        gap: 6px;
      }
      .sw {
        width: 11px;
        height: 11px;
        border-radius: 3px;
        &.gold {
          background: var(--gold-2);
        }
        &.cyan {
          background: var(--cyan-2);
        }
      }
      .mut {
        color: var(--ink-3);
      }
    }
    @media (max-width: 520px) {
      .gloss dl div {
        grid-template-columns: 1fr;
        gap: 0;
      }
    }
    .warn {
      padding: 8px 10px;
      border-radius: 10px;
      border: 1px dashed rgba(157, 123, 255, 0.5);
      margin: 0 0 12px;
    }
    .sub {
      font-size: 14px;
      margin: 4px 0;
    }
    .head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 8px;
    }
    .chart.g {
      height: 250px;
    }
    .chart.m {
      height: 270px;
    }
  `,
})
export class WhySection {
  private readonly data = inject(DataService);
  private readonly ui = inject(UiStateService);
  protected readonly shap = computed(() => this.data.shap());
  protected readonly sel = signal(0);
  protected readonly scen = computed(() => this.shap()?.matchup[this.sel()] ?? null);
  protected readonly pct = pct;
  protected readonly short = short;

  /** Por qué un dato ayuda a un equipo, en una frase (sin afirmar más de lo que dice el modelo). */
  protected reason(grupo: string, team: string): string {
    const r: Record<string, string> = {
      Elo: `${team} tiene más puntos: ha ganado más y contra mejores rivales`,
      'Forma reciente': `cómo le ha ido a ${team} en sus últimos mapas`,
      'Primer pick': `${team} elige campeón primero en el draft`,
      'Ventaja temprana': 'el oro y la experiencia de cada equipo al minuto 15',
      'Objetivos tempranos': 'quién suele llevarse el primer dragón, heraldo y torre',
      'Muertes por minuto': 'qué tan seguido muere cada equipo',
      'Daño por minuto': 'cuánto daño hace cada equipo',
      'Duración de partidas': 'si cada equipo juega partidas cortas o largas',
      'Tamaño de muestra': 'cuántas partidas recientes hay de cada equipo',
    };
    return r[grupo] ?? '';
  }

  /** Probabilidad oficial (solo Elo) para el mismo lado y primer pick. */
  protected official(blue: boolean, fp: boolean): number | null {
    return this.data.prediction()?.maps.find((m) => m.a_blue === blue && m.a_first_pick === fp)?.p_a ?? null;
  }

  /** Qué significa cada grupo de datos (las variables reales de cada grupo están en shap.json). */
  protected readonly meaning: Record<string, string> = {
    Elo: 'La fuerza del equipo según todos sus resultados (ver "Mapa a mapa").',
    'Ventaja temprana': 'Cuánto oro y experiencia de ventaja suele tener al minuto 15.',
    'Forma reciente': 'Cuánto viene ganando y cuántas kills hace en sus últimos 10 y 20 mapas.',
    'Objetivos tempranos': 'Qué tan seguido se lleva el primer dragón, el primer heraldo y la primera torre.',
    'Muertes por minuto': 'Qué tan seguido mueren sus jugadores.',
    'Daño por minuto': 'Cuánto daño hace a los campeones rivales.',
    'Duración de partidas': 'Si suele jugar partidas cortas o largas.',
    'Primer pick': 'Si elige campeón primero en el draft.',
    'Tamaño de muestra': 'Cuántas partidas recientes hay para calcular lo anterior (con pocas, el dato es menos fiable).',
  };

  /** Los dos datos que más empujan a favor de cada equipo en el escenario elegido. */
  protected readonly pushers = computed(() => {
    const c = this.scen()?.contribuciones ?? [];
    const top = (xs: typeof c) => xs.slice(0, 2).map((x) => x.grupo);
    return {
      forA: top([...c].filter((x) => x.shap > 0.02).sort((a, b) => b.shap - a.shap)),
      forB: top([...c].filter((x) => x.shap < -0.02).sort((a, b) => a.shap - b.shap)),
    };
  });

  protected readonly globalOpts = computed(() => {
    const g = [...(this.shap()?.global ?? [])].reverse();
    const total = g.reduce((a, x) => a + x.importancia, 0) || 1;
    const base = baseChart(this.ui.reducedMotion());
    return {
      ...base,
      tooltip: { ...(base['tooltip'] as object), trigger: 'item', formatter: (d: { name: string; value: number }) => `${d.name}: ${pct(d.value, 0)} del peso` },
      xAxis: { type: 'value', ...axisStyle, axisLabel: { show: false }, splitLine: { show: false } },
      yAxis: { type: 'category', data: g.map((x) => x.grupo), ...axisStyle, axisLabel: { color: COLORS.ink, fontFamily: 'Inter' } },
      series: [
        {
          type: 'bar',
          data: g.map((x) => x.importancia / total),
          barWidth: '60%',
          itemStyle: { color: COLORS.violet, borderRadius: [0, 6, 6, 0], shadowBlur: 10, shadowColor: 'rgba(157,123,255,.45)' },
          label: { show: true, position: 'right', color: COLORS.ink2, formatter: (d: { value: number }) => pct(d.value, 0) },
        },
      ],
    };
  });

  protected readonly matchupOpts = computed(() => {
    const m = this.scen();
    const c = [...(m?.contribuciones ?? [])].reverse();
    const base = baseChart(this.ui.reducedMotion());
    return {
      ...base,
      tooltip: { show: false },
      // Sin números: las unidades (logit) no dicen nada al lector; importa el lado y el largo de la barra.
      xAxis: { type: 'value', ...axisStyle, axisLabel: { show: false }, splitLine: { show: false } },
      yAxis: { type: 'category', data: c.map((x) => x.grupo), ...axisStyle, axisLabel: { color: COLORS.ink, fontFamily: 'Inter' } },
      series: [
        {
          type: 'bar',
          barWidth: '60%',
          markLine: { silent: true, symbol: 'none', data: [{ xAxis: 0 }], lineStyle: { color: 'rgba(255,255,255,.5)', type: 'solid' }, label: { show: false } },
          data: c.map((x) => ({
            value: x.shap,
            itemStyle: { color: x.shap >= 0 ? COLORS.gold : COLORS.cyan, borderRadius: x.shap >= 0 ? [0, 6, 6, 0] : [6, 0, 0, 6] },
          })),
          label: { show: false },
        },
      ],
    };
  });
}
