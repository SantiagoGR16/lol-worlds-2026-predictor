import { Component, computed, inject } from '@angular/core';
import { DataService } from '../data/data.service';
import { CountUpDirective } from '../shared/count-up';
import { complement, date, num, pct } from '../shared/format';
import { short } from '../shared/event';

/** La final: la probabilidad de la serie, explicada sin tecnicismos. */
@Component({
  selector: 'app-hero',
  imports: [CountUpDirective],
  template: `
    @if (pred(); as p) {
      <div class="teams">
        <div class="side a">
          <span class="badge gold">{{ short(p.team_a) }}</span>
          <span class="name">{{ p.team_a }}</span>
          <span class="big gold-text num" [appCountUp]="p.p_series_a">0</span>
        </div>
        <span class="vs eyebrow">vs</span>
        <div class="side b">
          <span class="badge cyan">{{ short(p.team_b) }}</span>
          <span class="name">{{ p.team_b }}</span>
          <span class="big cyan-text num" [appCountUp]="complement(p.p_series_a)">0</span>
        </div>
      </div>

      <div class="split" role="img" [attr.aria-label]="p.team_a + ' ' + pct(p.p_series_a) + ', ' + p.team_b + ' ' + pct(complement(p.p_series_a))">
        <div class="seg gold" [style.flex-grow]="p.p_series_a"><span>{{ short(p.team_a) }} {{ pct(p.p_series_a) }}</span></div>
        <div class="seg cyan" [style.flex-grow]="complement(p.p_series_a)"><span>{{ pct(complement(p.p_series_a)) }} {{ short(p.team_b) }}</span></div>
        <div class="ci" [style.left.%]="p.ci[0] * 100" [style.width.%]="(p.ci[1] - p.ci[0]) * 100" title="Intervalo"></div>
      </div>
      <p class="ci-text mono">
        Margen de error: entre {{ pct(p.ci[0]) }} y {{ pct(p.ci[1]) }}
      </p>

      <p class="lead">
        Si esta misma final (la serie completa, al mejor de 5 mapas) se jugara 100 veces, <strong class="gold-text">{{ p.team_a }}</strong> ganaría
        unas <strong class="gold-text">{{ per100(p.p_series_a) }}</strong> y {{ p.team_b }} unas {{ 100 - per100(p.p_series_a) }}.
        {{ p.team_a }} llega como favorito, pero {{ p.team_b }} tiene opciones reales.
      </p>

      <!-- Hallazgo: la estadística da la base; el "día" (factores humanos) la mueve. -->
      @if (day(); as d) {
        <section class="finding panel">
          <p class="eyebrow">Lo que encontramos</p>
          <h3>El día de la final también cuenta</h3>
          <p>
            Los datos dicen quién es mejor <em>en promedio</em>, pero una final la juegan personas, y los nervios, la
            preparación o el draft de ese día también pesan. Revisando <strong>{{ seriesFit }} series reales a 5
            mapas</strong> vimos que los mapas de una misma serie van muy ligados. Si un equipo llega bien, normalmente
            juega bien toda la serie, y si llega mal, también. A eso le llamamos <strong>"la forma del día"</strong>.
          </p>

          <p class="rows-title">Probabilidad de que {{ p.team_a }} gane <em>un mapa</em> según su día</p>
          <div class="rows">
            @for (r of d.rows; track r.label) {
              <div class="row" [class]="'row ' + r.cls">
                <span class="lbl">{{ r.label }}</span>
                <span class="track"><span class="fill" [style.width.%]="r.p * 100"></span><span class="mid"></span></span>
                <span class="num">{{ pct(r.p, 0) }}</span>
              </div>
            }
          </div>
          <p class="note">
            A cualquier equipo le toca un día así más o menos en 1 de cada 6 series. Ese día
            <strong>{{ p.team_b }} sería favorito</strong> en cada mapa, aunque las estadísticas digan lo contrario.
          </p>

          <div class="impact">
            <div>
              <span class="eyebrow">Solo estadística</span>
              <span class="num v">{{ pct(p.p_series_a_static) }}</span>
            </div>
            <span class="arrow" aria-hidden="true">→</span>
            <div>
              <span class="eyebrow">Contando el día</span>
              <span class="num v gold-text">{{ pct(p.p_series_a) }}</span>
            </div>
            <div class="delta">
              <span class="eyebrow">Diferencia</span>
              <span class="num v">{{ signedPts(p.p_series_a - p.p_series_a_static) }}</span>
            </div>
          </div>
          <p class="why">
            Para eso hicimos este mapa: para ver qué parte del resultado explican las estadísticas y cuánto lo pueden
            mover los factores humanos. Contando el día, {{ p.team_a }} sigue de favorito, pero pierde {{ signedPts(p.p_series_a_static - p.p_series_a).replace(' pts', '').replace('+', '') }} puntos de ventaja.
          </p>
        </section>
      }

      <p class="note">
        Basado en partidos oficiales hasta el {{ date(p.data_date) }}. La fuerza de cada equipo sale de sus resultados
        (sistema Elo, como en el ajedrez). Para calcular la probabilidad se simuló la final
        {{ p.n_series_montecarlo.toLocaleString('es-ES') }} veces. Igual que en la competición, el lado del primer mapa se
        sortea y en los siguientes elige el equipo que perdió el mapa anterior.
      </p>
    }
  `,
  styles: `
    .teams {
      display: grid;
      grid-template-columns: 1fr auto 1fr;
      align-items: end;
      gap: 8px;
      margin-bottom: 14px;
    }
    .side {
      display: grid;
      gap: 6px;
      &.b {
        justify-items: end;
        text-align: right;
      }
    }
    .name {
      font-family: var(--f-title);
      font-size: 14px;
      color: var(--ink-2);
    }
    .big {
      font-family: var(--f-title);
      font-weight: 700;
      font-size: clamp(30px, 5vw, 44px);
      line-height: 1;
    }
    .vs {
      padding-bottom: 8px;
    }
    .split {
      position: relative;
      display: flex;
      height: 34px;
      border-radius: 10px;
      overflow: hidden;
      border: 1px solid var(--line);
    }
    .seg {
      display: flex;
      align-items: center;
      padding: 0 10px;
      font-family: var(--f-mono);
      font-size: 12px;
      font-weight: 600;
      transition: flex-grow 1s cubic-bezier(0.2, 0.9, 0.2, 1);
      &.gold {
        background: linear-gradient(90deg, var(--gold), var(--gold-2));
        color: #1b1303;
      }
      &.cyan {
        justify-content: flex-end;
        background: linear-gradient(90deg, var(--cyan-2), var(--cyan));
        color: #021a21;
      }
    }
    .ci {
      position: absolute;
      top: -4px;
      bottom: -4px;
      border-left: 2px solid #fff;
      border-right: 2px solid #fff;
      background: rgba(255, 255, 255, 0.18);
      min-width: 4px;
    }
    .ci-text {
      margin: 8px 0 16px;
      font-size: 12px;
      color: var(--ink-2);
    }
    .finding {
      margin: 4px 0 12px;
      padding: 14px 16px;
      border-color: rgba(157, 123, 255, 0.45);
      background: linear-gradient(160deg, rgba(157, 123, 255, 0.1), rgba(35, 213, 255, 0.04));
      h3 {
        margin: 4px 0 8px;
        font-size: 17px;
      }
      p {
        margin: 0 0 10px;
        font-size: 13.5px;
        line-height: 1.55;
        color: var(--ink-2);
      }
      strong {
        color: var(--ink);
      }
      .rows-title {
        margin: 12px 0 6px;
        font-size: 12.5px;
        color: var(--ink);
      }
      .rows {
        display: grid;
        gap: 6px;
        margin-bottom: 8px;
      }
      .row {
        display: grid;
        grid-template-columns: 82px 1fr 44px;
        align-items: center;
        gap: 10px;
        font-size: 12.5px;
        .lbl {
          color: var(--ink-2);
        }
        .num {
          text-align: right;
          font-weight: 700;
        }
        .track {
          position: relative;
          height: 10px;
          border-radius: 999px;
          background: color-mix(in srgb, var(--cyan) 35%, transparent);
          overflow: hidden;
        }
        .fill {
          position: absolute;
          inset: 0 auto 0 0;
          border-radius: 999px;
          background: linear-gradient(90deg, var(--gold), var(--gold-2));
        }
        // Línea del 50 %: a la izquierda, el rival es favorito.
        .mid {
          position: absolute;
          left: 50%;
          top: -2px;
          bottom: -2px;
          width: 2px;
          background: #fff;
          opacity: 0.8;
        }
        &.bad .num {
          color: var(--cyan-2);
        }
        &.good .num,
        &.mid .num {
          color: var(--gold-2);
        }
      }
      .impact {
        display: flex;
        align-items: end;
        gap: 14px;
        flex-wrap: wrap;
        margin: 12px 0 10px;
        padding: 10px 12px;
        border-radius: 12px;
        background: rgba(255, 255, 255, 0.04);
        div {
          display: grid;
          gap: 2px;
        }
        .v {
          font-family: var(--f-title);
          font-size: 22px;
          font-weight: 700;
        }
        .arrow {
          font-size: 20px;
          color: var(--ink-3);
          padding-bottom: 2px;
        }
        .delta {
          margin-left: auto;
          text-align: right;
        }
      }
      .why {
        margin: 0;
        color: var(--ink);
      }
    }
    .lead {
      margin: 10px 0 14px;
      font-size: 14.5px;
      line-height: 1.55;
      color: var(--ink);
    }
    .facts {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px;
      margin-bottom: 12px;
      p {
        margin: 0;
      }
      .val {
        font-size: 20px;
        color: var(--ink);
        margin: 2px 0 4px;
      }
    }
    @media (max-width: 520px) {
      .facts {
        grid-template-columns: 1fr;
      }
    }
  `,
})
export class HeroSection {
  /** Número de Bo5 reales con que se midió la forma del día (sale de la nota de prediction.json). */
  protected get seriesFit(): string {
    return this.pred()?.day_form?.nota.match(/(\d+) Bo5/)?.[1] ?? 'cientos de';
  }

  /**
   * Probabilidad de que el equipo A gane un mapa en un día malo / normal / bueno: el promedio de sus
   * mapas desplazado ±σ en la escala logit (σ = forma del día; ±1σ ocurre ~1 de cada 6 series).
   */
  protected readonly day = computed(() => {
    const p = this.pred();
    const sigma = p?.day_form?.sigma ?? p?.sigma;
    if (!p || !sigma || !p.maps.length) return null;
    const logit = (x: number) => Math.log(x / (1 - x));
    const inv = (z: number) => 1 / (1 + Math.exp(-z));
    const base = logit(p.maps.reduce((a, m) => a + m.p_a, 0) / p.maps.length);
    return {
      rows: [
        { label: 'Mal día', cls: 'bad', p: inv(base - sigma) },
        { label: 'Día normal', cls: 'mid', p: inv(base) },
        { label: 'Buen día', cls: 'good', p: inv(base + sigma) },
      ],
    };
  });

  /** Probabilidad como "de cada 100". */
  protected per100(p: number): number {
    return Math.round(p * 100);
  }
  /** Diferencia en puntos porcentuales con signo: "−5,8 pts". */
  protected signedPts(d: number): string {
    const v = (d * 100).toLocaleString('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    return (d > 0 ? '+' : '') + v.replace('-', '−') + ' pts';
  }

  private readonly data = inject(DataService);
  protected readonly pred = computed(() => this.data.prediction());
  protected readonly pct = pct;
  protected readonly complement = complement;
  protected readonly num = num;
  protected readonly date = date;
  protected readonly short = short;
}
