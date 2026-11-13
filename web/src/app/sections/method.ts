import { Component, computed, inject } from '@angular/core';
import { DataService } from '../data/data.service';
import { SweepRow } from '../data/models';
import { num, pct, signed } from '../shared/format';
import { ELO, SIM, loserFirstPick, loserRed, LOSER_CHOICE, oneIn } from '../shared/model-facts';

/** Metodología: por qué elegimos el modelo, qué resultados dio y una conclusión, en lenguaje simple. */
@Component({
  selector: 'app-method',
  template: `
    @if (m(); as m) {
      <section class="intro panel">
        <p class="eyebrow">¿Cómo sabemos si el modelo acierta?</p>
        <ul>
          <li>Lo entrenamos con partidas <strong>anteriores</strong> y lo pusimos a predecir un Mundial que
            <strong>nunca vio</strong>. Es como probarlo con partidos que todavía no se habían jugado.</li>
          <li>Para elegir el modelo usamos el <strong>Mundial 2025</strong>; el <strong>Mundial 2026</strong> quedó
            guardado solo para comprobar al final.</li>
          <li>Para predecir un partido, el modelo solo usa lo que pasó antes de ese partido.</li>
        </ul>
      </section>

      <h3 class="sub">Paso a paso: qué hicimos y por qué</h3>
      <ol class="steps">
        <li>
          <strong>Juntamos los datos.</strong> Todas las partidas de las ligas principales (LCK, LPL, LEC, LCS, LCP,
          CBLOL), el MSI y los Mundiales de 2024 a 2026, de Oracle's Elixir.
          <span class="why">2024 lo usamos solo como historial previo, para que en 2025 cada equipo empiece con un
          Elo que ya refleje su nivel (y no todos en {{ elo.initial }}). No se usa para entrenar ni para evaluar.</span>
        </li>
        <li>
          <strong>Calculamos el Elo de cada equipo</strong>, partida a partida: todos empiezan en {{ elo.initial }}, el que gana sube
          y el que pierde baja ({{ elo.k }} puntos como base, ×{{ elo.kInternational }} en MSI y Mundial porque son los únicos cruces entre regiones). El
          lado azul suma {{ elo.blueBonus }} puntos de ventaja y al empezar cada año el Elo se acerca un {{ pct(1 - elo.seasonRegression, 0) }} a la media.
          <span class="why">Esos números no son al azar: probamos varias combinaciones y nos quedamos con la que menos
          falló en el Mundial 2025.</span>
        </li>
        <li>
          <strong>Comparamos tres modelos</strong> para predecir un mapa: solo Elo, una regresión logística (Elo + lado y
          primer pick) y LightGBM (además, oro, objetivos, muertes, daño… de los últimos 10 y 20 mapas).
          <span class="why">Ganó el Elo. Los tres fallaban casi lo mismo, y en ese caso preferimos el más simple (los
          resultados están más abajo).</span>
        </li>
        <li>
          <strong>Aprendimos cómo se eligen los lados en un Bo5.</strong> El que pierde un mapa elige en el siguiente. En
          2026 elige rojo el {{ pct(loserRed(), 0) }} de las veces y se queda el primer pick el {{ pct(loserFirstPick(), 0) }}; lo más
          común es rojo + primer pick ({{ pct(choice.redFp, 0) }}). El mapa 1 es {{ pct(sim.map1Blue, 0) }} / {{ pct(1 - sim.map1Blue, 0) }}.
          <span class="why">La regla cambió en 2026, por eso la sacamos de los datos en vez de suponerla.</span>
        </li>
        <li>
          <strong>Simulamos la final {{ pred_() ? num(pred_()!.n_series_montecarlo, 0) : '' }} veces (Montecarlo).</strong> En cada simulación se juega mapa a mapa: el
          modelo da la probabilidad de ganar ese mapa según el lado, se "tira un dado" con esa probabilidad, el perdedor
          elige lado para el siguiente, y así hasta que alguien llega a 3 victorias. Al final contamos cuántas series ganó
          cada equipo y con qué marcador. También lo calculamos de forma exacta, sin azar, y da lo mismo.
          <span class="why">Simulamos porque un Bo5 depende del orden de los mapas y de los lados, y así cubrimos todos
          los casos sin fórmulas complicadas.</span>
        </li>
        <li>
          <strong>Añadimos la "forma del día".</strong> En cada simulación se sortea qué tan buen o mal día tiene Gen.G
          frente a BLG, y eso afecta a todos sus mapas de esa serie. Cuánto puede variar se ajustó con {{ nPrev() }} Bo5 reales.
          <span class="why">Sin esto, el simulador confiaba demasiado en el favorito y daba muy pocos 3-0. Con la forma
          del día mejoran las dos cosas (está en las tablas de abajo).</span>
        </li>
        <li>
          <strong>Calculamos el margen de error.</strong> Reajustamos el modelo {{ sim.nBootstrap }} veces sobre mezclas al azar de las
          partidas de entrenamiento (bootstrap)
          @if (pred_(); as p) { y la probabilidad de Gen.G quedó entre {{ pct(p.ci[0]) }} y {{ pct(p.ci[1]) }} en el {{ pct(p.ci_level, 0) }} de los casos. }
          @else { para ver cuánto cambia la probabilidad. }
          <span class="why">Sirve para ver si el resultado depende de unas pocas partidas. El rango sale estrecho porque
          solo mide eso; lo que puede pasar el día de la final ya va incluido en la forma del día.</span>
        </li>
      </ol>

      <h3 class="sub">Cómo se mide el error</h3>
      <ul class="plain">
        <li>Contar aciertos no alcanza, también importa <strong>qué tan seguro</strong> estaba el modelo. Fallar diciendo
          90 % es peor que fallar diciendo 55 %.</li>
        <li>Para eso usamos <strong>log-loss</strong> y <strong>Brier</strong>. Las dos miden el error, así que
          <strong>mientras más bajo, mejor</strong> (0 sería perfecto).</li>
      </ul>
      <div class="metric panel">
        <p class="mt">Brier: la distancia al resultado, al cuadrado</p>
        <p class="md">(probabilidad que dio el modelo − lo que pasó)². Lo que pasó vale 1 si ganó y 0 si perdió.</p>
        <table class="data mini">
          <thead><tr><th>El modelo dijo</th><th>Gen.G ganó</th><th>Gen.G perdió</th></tr></thead>
          <tbody>
            <tr><td>80 % Gen.G</td><td>(1 − 0,8)² = <strong>0,04</strong></td><td>(0 − 0,8)² = <strong>0,64</strong></td></tr>
            <tr><td>50 % (moneda)</td><td><strong>0,25</strong></td><td><strong>0,25</strong></td></tr>
          </tbody>
        </table>
      </div>
      <div class="metric panel">
        <p class="mt">Log-loss: castiga fuerte el exceso de confianza</p>
        <p class="md">Mira qué probabilidad le dio el modelo al equipo que ganó de verdad: si le dio mucha, el castigo es
          pequeño; si le dio poca, el castigo es grande y crece muy rápido.</p>
        <table class="data mini">
          <thead><tr><th>Probabilidad que le dio al que ganó</th><th>Castigo</th></tr></thead>
          <tbody>
            <tr><td>80 %</td><td><strong>0,22</strong></td></tr>
            <tr><td>50 % (moneda)</td><td><strong>0,69</strong></td></tr>
            <tr><td>20 %</td><td><strong>1,61</strong></td></tr>
            <tr><td>5 %</td><td><strong>3,00</strong></td></tr>
          </tbody>
        </table>
        <p class="md">Por eso un modelo que dice "99 % seguro" y falla queda muy mal en log-loss.</p>
      </div>
      <ul class="plain">
        <li>Referencia: tirar una moneda (50 % siempre) da log-loss <span class="num">0,693</span> y Brier
          <span class="num">0,250</span>. Si un modelo da menos que eso, sabe algo más que la moneda.</li>
      </ul>

      <h3 class="sub">Los tres modelos que probamos</h3>
      <ul class="plain">
        <li><strong>(a) Solo Elo:</strong> la fuerza de cada equipo según sus resultados, más la ventaja del lado azul.</li>
        <li><strong>(b) Regresión logística:</strong> el mismo Elo más el lado y el primer pick, con pesos aprendidos de los datos.</li>
        <li><strong>(c) LightGBM:</strong> un modelo más complejo que además mira estadísticas recientes (oro y experiencia al
          minuto 15, objetivos, muertes, daño, duración…).</li>
      </ul>
      <div class="scroll-x">
        <table class="data">
          <thead><tr><th>Mundial</th><th>Modelo</th><th>Mapas</th><th>Log-loss</th><th>Brier</th><th>Aciertos</th></tr></thead>
          <tbody>
            @for (r of m.modelos_mapa; track r.mundial + r.modelo) {
              <tr [class.hl]="r.modelo.startsWith('(a)')">
                <td>{{ r.mundial }}</td><td>{{ r.modelo }}</td><td>{{ r.n }}</td>
                <td>{{ num(r.log_loss, 3) }}</td><td>{{ num(r.brier, 3) }}</td><td>{{ pct(r.accuracy, 0) }}</td>
              </tr>
            }
          </tbody>
        </table>
      </div>
      @if (cmp(); as c) {
        <ul class="plain result">
          <li>En el Mundial 2025, <strong>Solo Elo</strong> tuvo el menor error ({{ num(c.e25.log_loss, 4) }}), casi
            empatado con la logística ({{ num(c.l25.log_loss, 4) }}). LightGBM quedó peor que tirar una moneda
            ({{ num(c.g25.log_loss, 3) }}).</li>
          <li>Como quedaron prácticamente empatados, <strong>nos quedamos con el más simple</strong>. Ni la logística ni
            LightGBM mejoraban al Elo, y un modelo simple suele aguantar mejor cuando aparecen equipos nuevos o datos raros.</li>
          <li>En el Mundial 2026 (la prueba final) se repitió: Elo {{ num(c.e26.log_loss, 4) }} vs logística
            {{ num(c.l26.log_loss, 4) }} vs LightGBM {{ num(c.g26.log_loss, 4) }}. Acierta el ganador del mapa
            ~{{ pct(c.e26.accuracy, 0) }} de las veces.</li>
        </ul>
      }

      <h3 class="sub">¿Funciona para series completas (Bo5)?</h3>
      <p class="note">Simulamos cada Bo5 real del pasado mapa a mapa y lo comparamos con lo que pasó.</p>
      <div class="scroll-x">
        <table class="data">
          <thead><tr><th>Series</th><th>Cuántas</th><th>Log-loss</th><th>Brier</th><th>Favorito según modelo</th><th>Favorito ganó</th></tr></thead>
          <tbody>
            @for (r of m.backtest_series; track r.grupo) {
              <tr>
                <td>{{ r.grupo }}</td><td>{{ r.n }}</td><td>{{ num(r.log_loss, 3) }}</td><td>{{ num(r.brier, 3) }}</td>
                <td>{{ pct(r.p_media_fav, 0) }}</td><td>{{ pct(r.fav_gana, 0) }}</td>
              </tr>
            }
          </tbody>
        </table>
      </div>
      @if (all(); as a) {
        <ul class="plain result">
          <li>En {{ a.n }} series, el modelo daba al favorito un {{ pct(a.p_media_fav, 0) }} de media y el favorito ganó
            el {{ pct(a.fav_gana, 0) }}: <strong>acierta bastante, pero es algo optimista</strong> con el favorito.</li>
          @if (w26(); as w) {
            <li>En el Mundial 2026 hubo solo {{ w.n }} Bo5 y el favorito ganó {{ pct(w.fav_gana, 0) }}: un torneo con
              muchas sorpresas. Con tan pocas series no se puede sacar una conclusión firme.</li>
          }
        </ul>
      }

      <h3 class="sub">¿Ayuda la "forma del día"?</h3>
      <p class="note">
        Comparamos tres formas de simular la serie: <strong>estático</strong> (cada mapa independiente),
        <strong>recalibración</strong> (corregir lo optimista) y <strong>forma del día</strong> (el equipo puede tener un
        buen o mal día que afecta a todos sus mapas).
      </p>
      <div class="scroll-x">
        <table class="data">
          <thead><tr><th>Series</th><th>Variante</th><th>Log-loss</th><th>Brier</th><th>Error del marcador</th><th>Mejora vs estático</th></tr></thead>
          <tbody>
            @for (r of m.variantes_series; track r.grupo + r.variante) {
              <tr [class.hl]="r.variante === 'forma del día'">
                <td>{{ r.grupo }}</td><td>{{ r.variante }}</td><td>{{ num(r.log_loss, 3) }}</td><td>{{ num(r.brier, 3) }}</td>
                <td>{{ num(r.nll_marcador, 3) }}</td>
                <td>{{ r.variante === 'estático' ? '—' : signed(r.dif_vs_estatico, 3) + ' ± ' + num(r.se_dif, 3) }}</td>
              </tr>
            }
          </tbody>
        </table>
      </div>

      <h3 class="sub">Barridas (3-0 o 0-3)</h3>
      <div class="scroll-x">
        <table class="data">
          <thead><tr><th>Series</th><th>Pasó de verdad</th><th>Estático</th><th>Recalibración</th><th>Forma del día</th></tr></thead>
          <tbody>
            @for (r of m.barridas; track r.grupo) {
              <tr>
                <td>{{ r.grupo }} ({{ r.n_series }})</td><td>{{ pct(r.barridas_real) }}</td>
                <td>{{ pct(pred(r, 'estático')) }}</td><td>{{ pct(pred(r, 'recalibración')) }}</td>
                <td>{{ pct(pred(r, 'forma del día')) }}</td>
              </tr>
            }
          </tbody>
        </table>
      </div>
      @if (sw(); as s) {
        <ul class="plain result">
          <li>De verdad, el <strong>{{ pct(s.barridas_real, 0) }}</strong> de los Bo5 terminó 3-0 o 0-3. El modelo
            estático decía {{ pct(pred(s, 'estático'), 0) }} (se quedaba corto); con forma del día,
            <strong>{{ pct(pred(s, 'forma del día'), 0) }}</strong>: mucho más cerca.</li>
          <li>Pasa porque en la vida real los mapas de una serie no son independientes. El equipo que llega bien (o mal)
            lo arrastra a toda la serie.</li>
          @if (oos(); as o) {
            <li class="mut">En el Mundial 2026 ({{ o.n_series }} series) va en la misma dirección, pero son muy pocas para
              asegurarlo.</li>
          }
        </ul>
      }

      <section class="concl panel">
        <p class="eyebrow">Conclusión</p>
        <ul>
          <li><strong>El Elo solo predice igual de bien que los modelos más complejos</strong> y además es más fácil de
            explicar. Por eso la predicción oficial usa el Elo.</li>
          <li>Entre equipos de élite cuesta acertar quién gana un mapa, y un
            {{ cmp() ? pct(cmp()!.e26.accuracy, 0) : '60 %' }} de aciertos es normal. Si nos diera más de ~72 %
            pensaríamos que hay un error en los datos.</li>
          <li>Las estadísticas dan una base, pero <strong>los nervios, la estrategia y el draft también mueven el
            resultado</strong>. Al sumar la forma del día, los marcadores se parecen más a los reales.</li>
          @if (pred_(); as p) {
            <li>Para la final, <strong class="gold-text">{{ p.team_a }}</strong> tiene un
              <strong class="gold-text">{{ pct(p.p_series_a, 0) }}</strong> de ganar la serie. Es favorito, pero
              {{ p.team_b }} la ganaría más o menos 1 de cada {{ oneIn(1 - p.p_series_a) }} veces.</li>
          }
        </ul>
      </section>
      <p class="note">Todo sale de los CSV de Oracle's Elixir; el código y los informes están en el repositorio del proyecto.</p>
    }
  `,
  styles: `
    .intro,
    .concl {
      padding: 10px 12px;
      margin: 0 0 12px;
      border-color: rgba(157, 123, 255, 0.45);
      background: rgba(157, 123, 255, 0.06);
      .eyebrow {
        margin: 0 0 4px;
        color: var(--violet-2);
      }
      ul {
        margin: 0;
        padding-left: 18px;
        font-size: 13px;
        line-height: 1.55;
        color: var(--ink-2);
      }
      li {
        margin-bottom: 4px;
      }
      strong {
        color: var(--ink);
      }
    }
    .concl {
      margin-top: 18px;
      border-color: rgba(255, 200, 87, 0.5);
      background: rgba(255, 200, 87, 0.06);
      .eyebrow {
        color: var(--gold-2);
      }
    }
    .plain {
      margin: 0 0 8px;
      padding-left: 18px;
      font-size: 13px;
      line-height: 1.55;
      color: var(--ink-2);
      li {
        margin-bottom: 3px;
      }
      strong {
        color: var(--ink);
      }
      .mut {
        color: var(--ink-3);
      }
    }
    .steps {
      margin: 0 0 8px;
      padding-left: 20px;
      font-size: 13px;
      line-height: 1.55;
      color: var(--ink-2);
      li {
        margin-bottom: 9px;
        padding-left: 2px;
      }
      li::marker {
        color: var(--violet-2);
        font-weight: 700;
      }
      strong {
        color: var(--ink);
      }
      .why {
        display: block;
        margin-top: 2px;
        padding-left: 8px;
        border-left: 2px solid rgba(157, 123, 255, 0.5);
        color: var(--ink-3);
        font-size: 12.5px;
      }
    }
    .metric {
      padding: 10px 12px;
      margin: 0 0 8px;
      .mt {
        margin: 0 0 4px;
        font-weight: 700;
        font-size: 13.5px;
        color: var(--ink);
      }
      .md {
        margin: 0 0 6px;
        font-size: 12.5px;
        line-height: 1.5;
        color: var(--ink-2);
        &:last-child {
          margin: 6px 0 0;
        }
      }
      .mini {
        width: 100%;
        font-size: 12.5px;
      }
    }
    .result {
      margin-top: 8px;
    }
    .sub {
      font-size: 14px;
      margin: 16px 0 6px;
    }
  `,
})
export class MethodSection {
  private readonly data = inject(DataService);
  protected readonly m = computed(() => this.data.metrics());
  protected readonly pred_ = computed(() => this.data.prediction());
  protected readonly num = num;
  protected readonly pct = pct;
  protected readonly elo = ELO;
  protected readonly sim = SIM;
  protected readonly choice = LOSER_CHOICE;
  protected readonly loserRed = loserRed;
  protected readonly loserFirstPick = loserFirstPick;
  protected readonly oneIn = oneIn;
  /** Bo5 previos con los que se ajustó la forma del día. */
  protected readonly nPrev = computed(() => this.m()?.variantes_series.find((r) => r.grupo.includes('previos'))?.n_series ?? 0);
  protected readonly signed = signed;

  /** Filas de la tabla de modelos por Mundial y letra del modelo. */
  protected readonly cmp = computed(() => {
    const rows = this.m()?.modelos_mapa ?? [];
    const get = (y: string, k: string) => rows.find((r) => r.mundial.includes(y) && r.modelo.startsWith(k));
    const v = {
      e25: get('2025', '(a)'), l25: get('2025', '(b)'), g25: get('2025', '(c)'),
      e26: get('2026', '(a)'), l26: get('2026', '(b)'), g26: get('2026', '(c)'),
    };
    return Object.values(v).every(Boolean) ? (v as { [K in keyof typeof v]: NonNullable<(typeof v)[K]> }) : null;
  });

  protected readonly all = computed(() => this.m()?.backtest_series.find((r) => r.grupo === 'Todas') ?? null);
  protected readonly w26 = computed(() => this.m()?.backtest_series.find((r) => r.grupo.startsWith('WLDs')) ?? null);
  /** Barridas en los Bo5 previos (la muestra grande). */
  protected readonly sw = computed(() => this.m()?.barridas.find((r) => r.grupo.includes('previos')) ?? null);

  /** Grupo fuera de muestra: el de las series del Mundial de evaluación (el que no es "previos"). */
  protected readonly oos = computed(() => this.m()?.variantes_series.find((r) => !r.grupo.includes('previos')) ?? null);

  /** Las claves de predicción de barridas vienen de pandas: "pred_<variante>". */
  protected pred(r: SweepRow, variant: string): number {
    return Number(r[`pred_${variant}`]);
  }
}
