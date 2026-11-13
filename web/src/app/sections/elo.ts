import { Component, computed, inject } from '@angular/core';
import { NgxEchartsDirective } from 'ngx-echarts';
import { DataService } from '../data/data.service';
import { UiStateService } from '../ui/ui-state.service';
import { COLORS, axisStyle, baseChart } from '../shared/chart';
import { date, num } from '../shared/format';
import { short } from '../shared/event';

/** Elo en el tiempo (parte de "Mapa a mapa"): evolución de los finalistas y top 15 antes de la final. */
@Component({
  selector: 'app-elo',
  imports: [NgxEchartsDirective],
  template: `
    <h3 class="sub first">El Elo en el tiempo</h3>
    <p class="intro">Cómo se movió la puntuación de los dos finalistas en 2025 y 2026, mapa a mapa.</p>
    @if (hist(); as h) {
      <div echarts class="chart" [options]="options()"></div>
      <div class="now">
        @for (t of teams(); track t.name) {
          <div class="panel">
            <span class="badge" [class]="'badge ' + t.color">{{ short(t.name) }}</span>
            <span class="num v" [class]="'num v ' + t.color + '-text'">{{ num(t.elo, 0) }}</span>
            <span class="note">Elo actual · {{ t.n }} mapas en 2025-26</span>
          </div>
        }
      </div>
    }
    @if (top(); as t) {
      <h3 class="sub">Top {{ t.teams.length }} antes de la final</h3>
      <div class="scroll-x">
        <table class="data">
          <thead>
            <tr><th>#</th><th>Equipo</th><th>Región</th><th>Elo</th></tr>
          </thead>
          <tbody>
            @for (r of t.teams; track r.rank) {
              <tr [class.hl]="isFinalist(r.teamname)">
                <td>{{ r.rank }}</td>
                <td>{{ r.teamname }}</td>
                <td>{{ r.region ?? '—' }}</td>
                <td>{{ num(r.elo, 0) }}</td>
              </tr>
            }
          </tbody>
        </table>
      </div>
      <p class="note">{{ t.nota }} Corte: {{ date(t.fecha_corte) }}.</p>
    }
  `,
  styles: `
    .sub.first {
      margin-top: 22px;
      padding-top: 16px;
      border-top: 1px solid var(--line);
    }
    .intro {
      margin: 0 0 8px;
      font-size: 13px;
      color: var(--ink-2);
    }
    .now {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin: 8px 0 14px;
      .panel {
        display: grid;
        gap: 4px;
      }
      .v {
        font-size: 22px;
      }
    }
    .sub {
      font-size: 14px;
      margin-bottom: 6px;
    }
  `,
})
export class EloSection {
  private readonly data = inject(DataService);
  private readonly ui = inject(UiStateService);



  protected readonly hist = computed(() => this.data.elo());
  protected readonly top = computed(() => this.data.topElo());
  protected readonly num = num;
  protected readonly date = date;
  protected readonly short = short;

  private readonly finalists = computed(() => {
    const p = this.data.prediction();
    return p ? [p.team_a, p.team_b] : [];
  });
  protected isFinalist(name: string): boolean {
    return this.finalists().includes(name);
  }

  protected readonly teams = computed(() => {
    const h = this.hist();
    const [a, b] = this.finalists();
    if (!h) return [];
    return [a, b]
      .filter((n) => h.teams[n])
      .map((n, i) => ({ name: n, color: i === 0 ? 'gold' : 'cyan', elo: h.teams[n].elo_actual, n: h.teams[n].points.length }));
  });

  protected readonly options = computed(() => {
    const h = this.hist();
    const reduced = this.ui.reducedMotion();
    const names = this.finalists();
    const colors = [COLORS.gold, COLORS.cyan];
    const base = baseChart(reduced);
    return {
      ...base,
      tooltip: {
        ...(base['tooltip'] as object),
        trigger: 'axis',
        valueFormatter: (v: number) => num(v, 0),
      },
      legend: { top: 0, textStyle: { color: COLORS.ink2 }, icon: 'roundRect' },
      grid: { left: 8, right: 12, top: 30, bottom: 8, containLabel: true },
      xAxis: { type: 'time', ...axisStyle, splitLine: { show: false } },
      yAxis: { type: 'value', scale: true, ...axisStyle },
      series: names
        .filter((n) => h?.teams[n])
        .map((n, i) => ({
          name: n,
          type: 'line',
          showSymbol: false,
          smooth: 0.25,
          lineStyle: { width: 2.2, color: colors[i], shadowBlur: 10, shadowColor: colors[i] },
          itemStyle: { color: colors[i] },
          areaStyle: { color: colors[i], opacity: 0.06 },
          data: h!.teams[n].points.map((p) => [new Date(p.date.replace(' ', 'T')).getTime(), p.elo]),
          animationDuration: 1400,
        })),
    };
  });
}
