import { Component, computed, inject } from '@angular/core';
import { DataService } from '../data/data.service';
import { ELO } from './model-facts';
import { date, num, pct } from '../shared/format';

/**
 * "¿Qué es el Elo?" en lenguaje simple, con ejemplos calculados con el Elo real de los equipos.
 * Se usa en "Mapa a mapa" y desplegado dentro de la sección "Elo". Reglas: config.yaml (sección elo).
 */
@Component({
  selector: 'app-elo-explainer',
  template: `
    <section class="elo panel">
        <p class="eyebrow">¿Qué es el Elo?</p>
        <p>
          Es una puntuación de fuerza que viene del ajedrez (Riot la usó en las clasificatorias de LoL hasta la
          temporada 3). Acá la calculamos <strong>por equipo</strong>, no por jugador, y no tiene relación con los LP.
          Funciona así:
        </p>
        <ul class="steps">
          <li><strong>Todos empiezan iguales</strong>, con {{ initial }} puntos.</li>
          <li><strong>Ganas un mapa, sumas; pierdes, restas.</strong> Los puntos que gana uno son los que pierde el otro.</li>
          <li>
            <strong>Ganarle a un fuerte vale más.</strong> Si dos equipos parejos juegan, el ganador suma unos 8 puntos.
            @if (ex(); as x) {
              <span class="ex">
                Ejemplo en la {{ x.league }}: {{ x.fav }} ({{ num(x.favElo, 0) }}) contra {{ x.dog }} ({{ num(x.dogElo, 0) }}).
                Si gana {{ x.fav }}, suma solo <strong>{{ num(x.favWin, 0) }}</strong> puntos, porque era lo esperado.
                Si gana {{ x.dog }}, se lleva <strong>{{ num(x.dogWin, 0) }}</strong>, porque fue una sorpresa.
              </span>
            }
          </li>
          <li>
            <strong>MSI y Mundial cuentan {{ kInt }} veces más</strong>, porque son los únicos torneos donde la LCK juega contra la
            LPL y las demás regiones. Sin ellos no se podría comparar a un equipo coreano con uno chino.
            @if (exInt(); as y) {
              <span class="ex">
                Ejemplo: cuando {{ y.a }} le gana un mapa a {{ y.b }} en el Mundial, suma unos
                <strong>{{ num(y.intl, 0) }}</strong> puntos. Si ese mismo resultado fuera en una liga, sumaría solo unos
                <strong>{{ num(y.league, 0) }}</strong>. Por eso lo que pasa en el Mundial mueve tanto la tabla.
              </span>
            }
          </li>
          <li><strong>Cada año se recorta un poco la ventaja</strong> de todos, porque los equipos cambian de jugadores.</li>
        </ul>
        @if (elo(); as e) {
          <div class="vs">
            <div class="t a"><span class="eyebrow">#{{ e.a.rank }} del mundo</span><span class="num gold-text">{{ num(e.a.elo, 0) }}</span><span>{{ e.a.teamname }}</span></div>
            <div class="gap"><span class="eyebrow">Diferencia</span><span class="num">{{ num(e.a.elo - e.b.elo, 0) }}</span></div>
            <div class="t b"><span class="eyebrow">#{{ e.b.rank }} del mundo</span><span class="num cyan-text">{{ num(e.b.elo, 0) }}</span><span>{{ e.b.teamname }}</span></div>
          </div>
          <p>
            Esa diferencia de puntos se convierte en probabilidad: a más distancia, más favorito. Con
            {{ num(e.a.elo - e.b.elo, 0) }} puntos de ventaja, más el pequeño plus del lado azul, sale el
            {{ pct(pBlue()) }} de ganar un mapa en lado azul. Datos hasta el {{ e.date }}, antes de la final.
          </p>
        }
    </section>
  `,
  styles: `
    .ex {
      display: block;
      margin-top: 4px;
      padding: 6px 10px;
      border-left: 2px solid var(--violet-2);
      border-radius: 0 8px 8px 0;
      background: rgba(157, 123, 255, 0.07);
      font-size: 12.5px;
    }
    .steps {
      margin: 0 0 10px;
      padding-left: 18px;
      display: grid;
      gap: 5px;
      font-size: 13px;
      line-height: 1.5;
      color: var(--ink-2);
      strong {
        color: var(--ink);
      }
    }
    .elo {
      transition: box-shadow 0.4s, border-color 0.4s;
      scroll-margin-top: 8px;
      // Resaltado al llegar desde el atajo de la sección Elo.
      &.flash {
        border-color: var(--violet-2);
        box-shadow: 0 0 0 3px rgba(157, 123, 255, 0.35);
      }
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
      .vs {
        display: grid;
        grid-template-columns: 1fr auto 1fr;
        align-items: end;
        gap: 10px;
        margin: 10px 0 12px;
        padding: 10px 12px;
        border-radius: 12px;
        background: rgba(255, 255, 255, 0.04);
        .t,
        .gap {
          display: grid;
          gap: 2px;
          font-size: 12.5px;
          color: var(--ink-2);
        }
        .t.b {
          text-align: right;
        }
        .gap {
          text-align: center;
        }
        .num {
          font-family: var(--f-title);
          font-size: 24px;
          font-weight: 700;
          color: var(--ink);
        }
        .gold-text {
          color: var(--gold-2);
        }
        .cyan-text {
          color: var(--cyan-2);
        }
      }
    }
  `,
})
export class EloExplainer {
  /** Reglas del Elo (config.yaml, sección elo): K por mapa y multiplicador de MSI/Mundial. */
  protected readonly initial = ELO.initial;
  protected readonly kInt = ELO.kInternational;
  private readonly K = ELO.k;
  private readonly K_INT = ELO.kInternational;
  /** Probabilidad esperada de ganar según la diferencia de Elo. */
  private expected(a: number, b: number): number {
    return 1 / (1 + Math.pow(10, (b - a) / 400));
  }

  /** Ejemplo de liga: el finalista A contra el mejor equipo de su región que no está en la final. */
  protected readonly ex = computed(() => {
    const t = this.data.topElo()?.teams ?? [];
    const p = this.pred();
    const fav = t.find((x) => x.teamname === p?.team_a);
    const dog = t.find((x) => x.region === fav?.region && x.teamname !== p?.team_a && x.teamname !== p?.team_b);
    if (!fav || !dog) return null;
    const e = this.expected(fav.elo, dog.elo);
    return {
      league: fav.region,
      fav: fav.teamname,
      favElo: fav.elo,
      dog: dog.teamname,
      dogElo: dog.elo,
      favWin: this.K * (1 - e),
      dogWin: this.K * e,
    };
  });

  /** Ejemplo internacional: el mismo mapa entre los dos finalistas, en liga o en el Mundial. */
  protected readonly exInt = computed(() => {
    const e = this.elo();
    if (!e) return null;
    const gain = this.K * (1 - this.expected(e.a.elo, e.b.elo));
    return { a: e.a.teamname, b: e.b.teamname, league: gain, intl: gain * this.K_INT };
  });

  /** Elo de los dos finalistas (top_elo.json, tras el último mapa antes de la final). */
  protected readonly elo = computed(() => {
    const p = this.pred();
    const t = this.data.topElo();
    const a = t?.teams.find((x) => x.teamname === p?.team_a);
    const b = t?.teams.find((x) => x.teamname === p?.team_b);
    return a && b && t ? { a, b, date: date(t.fecha_corte.slice(0, 10)) } : null;
  });

  private readonly data = inject(DataService);
  private readonly pred = computed(() => this.data.prediction());
  protected readonly pct = pct;
  protected readonly num = num;
  /** P(A gana un mapa en azul): el resultado de pasar la diferencia de Elo a probabilidad. */
  protected readonly pBlue = computed(() => this.pred()?.maps.find((m) => m.a_blue && !m.a_first_pick)?.p_a ?? 0);
}
