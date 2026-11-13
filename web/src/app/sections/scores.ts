import { Component, computed, inject, signal } from '@angular/core';
import { NgxEchartsDirective } from 'ngx-echarts';
import { DataService } from '../data/data.service';
import { UiStateService } from '../ui/ui-state.service';
import { COLORS, axisStyle, baseChart } from '../shared/chart';
import { pct } from '../shared/format';

/** Marcadores: distribución de resultados, contando la forma del día o solo con estadística. */
@Component({
  selector: 'app-scores',
  imports: [NgxEchartsDirective],
  template: `
    @if (pred(); as p) {
      <div class="head">
        <div class="toggle" role="group" aria-label="Variante del simulador">
          <button type="button" [attr.aria-pressed]="mode() === 'static'" (click)="mode.set('static')">Solo estadística</button>
          <button type="button" [attr.aria-pressed]="mode() === 'form'" (click)="mode.set('form')">Forma del día</button>
        </div>
        <span class="eyebrow">marcador {{ p.team_a }}–{{ p.team_b }}</span>
      </div>
      <div echarts class="chart" [options]="options()"></div>
      <div class="sum">
        <div class="panel">
          <p class="eyebrow">Más probable</p>
          <p class="num val">{{ top().score }} · {{ pct(top().p) }}</p>
        </div>
        <div class="panel">
          <p class="eyebrow">3-0 o 0-3</p>
          <p class="num val">{{ pct(sweep()) }}</p>
        </div>
        <div class="panel">
          <p class="eyebrow">{{ p.team_a }} gana la final</p>
          <p class="num val">{{ pct(winA()) }}</p>
        </div>
      </div>
      <p class="legend">
        <span><i class="sw gold" aria-hidden="true"></i>Gana {{ p.team_a }}</span>
        <span><i class="sw cyan" aria-hidden="true"></i>Gana {{ p.team_b }}</span>
      </p>
      <div class="why panel">
        <p class="eyebrow">¿Por qué sube el 3-0 al contar el día?</p>
        <p>
          Porque el día de un equipo se nota en toda la serie. Si {{ p.team_a }} tiene un buen día, lo tiene en los
          tres mapas y gana rápido. Si tiene un mal día, el que gana rápido es {{ p.team_b }}: su 0-3 sube de
          <strong>{{ pct(scoreOf(p.scores_static, '0-3')) }}</strong> a <strong>{{ pct(scoreOf(p.scores, '0-3')) }}</strong>.
        </p>
        <p>
          Por eso, al contar el día, las series que terminan 3-0 o 0-3 se vuelven más probables, y las que se alargan
          hasta el cuarto o quinto mapa (3-1, 3-2, 2-3) un poco menos. En total, la probabilidad de {{ p.team_a }} de
          ganar la final baja de {{ pct(p.p_series_a_static) }} a {{ pct(p.p_series_a) }}. En las series reales pasa
          lo mismo: el equipo que llega bien suele cerrar rápido.
        </p>
      </div>
    }
  `,
  styles: `
    .legend {
      display: flex;
      flex-wrap: wrap;
      gap: 6px 18px;
      margin: 10px 0 0;
      font-size: 12.5px;
      color: var(--ink-2);
      span {
        display: inline-flex;
        align-items: center;
        gap: 7px;
      }
      .sw {
        width: 12px;
        height: 12px;
        border-radius: 3px;
        &.gold {
          background: linear-gradient(135deg, var(--gold), var(--gold-2));
        }
        &.cyan {
          background: linear-gradient(135deg, var(--cyan), var(--cyan-2));
        }
      }
    }
    .why {
      margin-top: 10px;
      padding: 12px 14px;
      border-color: rgba(157, 123, 255, 0.45);
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
    .head {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      justify-content: space-between;
      align-items: center;
    }
    .chart {
      height: 250px;
      margin: 6px -6px 8px;
    }
    .sum {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px;
      margin-bottom: 10px;
      p {
        margin: 0;
      }
      .val {
        font-size: 15px;
        color: var(--ink);
        white-space: nowrap;
      }
    }
  `,
})
export class ScoresSection {
  private readonly data = inject(DataService);
  private readonly ui = inject(UiStateService);
  protected readonly pred = computed(() => this.data.prediction());
  protected readonly mode = signal<'form' | 'static'>('static');
  protected readonly pct = pct;
  /** Probabilidad de un marcador concreto ("3-0", "0-3"...) en una lista. */
  protected scoreOf(list: { score: string; p: number }[], score: string): number {
    return list.find((x) => x.score === score)?.p ?? 0;
  }

  private readonly scores = computed(() => {
    const p = this.pred();
    if (!p) return [];
    return this.mode() === 'form' ? p.scores : p.scores_static;
  });
  protected readonly top = computed(() => this.scores().reduce((a, b) => (b.p > a.p ? b : a), { score: '—', p: 0 }));
  protected readonly sweep = computed(() =>
    this.scores().filter((s) => s.score === '3-0' || s.score === '0-3').reduce((a, s) => a + s.p, 0),
  );
  // La misma cifra que el resto de la web (sumar los marcadores redondeados daba 71,3 en vez de 71,4).
  protected readonly winA = computed(() => {
    const p = this.pred();
    return p ? (this.mode() === 'form' ? p.p_series_a : p.p_series_a_static) : 0;
  });

  protected readonly options = computed(() => {
    const s = this.scores();
    const reduced = this.ui.reducedMotion();
    return {
      ...baseChart(reduced),
      tooltip: { ...(baseChart(reduced)['tooltip'] as object), trigger: 'axis', valueFormatter: (v: number) => pct(v) },
      xAxis: { type: 'category', data: s.map((x) => x.score), ...axisStyle, axisLabel: { color: COLORS.ink, fontSize: 12 } },
      yAxis: { type: 'value', ...axisStyle, axisLabel: { color: COLORS.ink3, formatter: (v: number) => `${Math.round(v * 100)} %` } },
      series: [
        {
          type: 'bar',
          barWidth: '58%',
          data: s.map((x) => ({
            value: x.p,
            itemStyle: {
              borderRadius: [6, 6, 0, 0],
              color: Number(x.score[0]) > Number(x.score[2]) ? COLORS.gold : COLORS.cyan,
              shadowBlur: 14,
              shadowColor: Number(x.score[0]) > Number(x.score[2]) ? 'rgba(232,182,76,.45)' : 'rgba(35,213,255,.45)',
            },
          })),
          label: { show: true, position: 'top', color: COLORS.ink, formatter: (d: { value: number }) => pct(d.value) },
          // Las barras "caen" con rebote al entrar.
          animationDuration: 1100,
          animationEasing: 'bounceOut',
          animationDelay: (i: number) => i * 70,
          animationDurationUpdate: 700,
          animationEasingUpdate: 'cubicOut',
        },
      ],
    };
  });
}
