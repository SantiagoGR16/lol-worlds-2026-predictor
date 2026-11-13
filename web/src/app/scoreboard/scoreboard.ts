import { Component, computed, inject, signal } from '@angular/core';
import { DataService } from '../data/data.service';
import { Role, ScoreboardPlayer, ScoreboardTeam } from '../data/models';
import { ROLE_LABEL, complement, date, num, pct } from '../shared/format';
import { short } from '../shared/event';
import { PicComponent } from '../shared/pic';

type SortKey = 'role' | 'kda' | 'kp' | 'dmg' | 'gold' | 'cs' | 'gpm' | 'vspm' | 'wards';

/** Columnas numéricas donde se marca al mejor de los 10 titulares (mayor es mejor). */
const BEST_COLS: { key: SortKey; get: (p: ScoreboardPlayer) => number | null }[] = [
  { key: 'kda', get: (p) => p.kda },
  { key: 'kp', get: (p) => p.kp },
  { key: 'dmg', get: (p) => p.dmg },
  { key: 'gold', get: (p) => p.gold },
  { key: 'cs', get: (p) => p.cs },
  { key: 'gpm', get: (p) => p.gpm },
  { key: 'vspm', get: (p) => p.vspm },
  { key: 'wards', get: (p) => p.wards_placed },
];

const ROLE_ORDER: Record<Role, number> = { top: 0, jng: 1, mid: 2, bot: 3, sup: 4 };

/**
 * Pestaña "Partido": previa de la final al estilo de una hoja de partido.
 * Cabecera con P(serie), una ficha por mapa (P de jugarse y de ganarlo) y la tabla de
 * jugadores con sus promedios REALES del Mundial (scoreboard.json).
 */
@Component({
  selector: 'app-scoreboard',
  imports: [PicComponent],
  template: `
    @if (sb(); as s) {
      @if (pred(); as p) {
        <nav class="crumbs mono" aria-label="Ubicación">
          <span>{{ eventName() }}</span> <span aria-hidden="true">›</span> <span>Playoffs</span>
          <span aria-hidden="true">›</span> <span class="here">Final · Bo5</span>
        </nav>

        <!-- Cabecera del partido -->
        <section class="match glass violet" aria-label="Resumen de la final">
          <p class="status eyebrow">Previa · datos hasta {{ date(s.meta.data_date) }}</p>
          <div class="versus">
            <div class="side a">
              <span class="tname">{{ s.team_a }}</span>
              <app-pic class="logo" kind="equipos" [name]="s.team_a" [fallback]="short(s.team_a)" tone="gold" />
            </div>
            <div class="center">
              <span class="eyebrow">Probabilidad de ganar la serie</span>
              <div class="probs num">
                <span class="gold-text" [class.fav]="p.p_series_a >= 0.5">{{ pct(p.p_series_a) }}</span>
                <span class="dash" aria-hidden="true">–</span>
                <span class="cyan-text" [class.fav]="p.p_series_a < 0.5">{{ pct(complement(p.p_series_a)) }}</span>
              </div>
              <span class="likely mono">Marcador más probable {{ topScore().score }} ({{ pct(topScore().p, 0) }})</span>
            </div>
            <div class="side b">
              <app-pic class="logo" kind="equipos" [name]="s.team_b" [fallback]="short(s.team_b)" tone="cyan" />
              <span class="tname">{{ s.team_b }}</span>
            </div>
          </div>
        </section>

        <!-- Fichas: serie completa + un mapa por ficha -->
        <section class="tiles" aria-label="Probabilidades por mapa">
          <div class="tile whole">
            <span class="eyebrow">Serie completa</span>
            <app-pic class="tlogo" kind="equipos" [name]="favSeries()" [fallback]="short(favSeries())"
                     [tone]="favSeries() === s.team_a ? 'gold' : 'cyan'" />
            <span class="mono small">Favorito</span>
            <span class="mono small dim">IC {{ (p.ci_level * 100).toFixed(0) }} %: {{ pct(p.ci[0]) }} – {{ pct(p.ci[1]) }}</span>
          </div>
          @for (m of s.maps; track m.map) {
            <div class="tile" [class.maybe]="m.p_played < 0.999">
              <span class="eyebrow">Mapa {{ m.map }}</span>
              @if (m.p_a_win_if_played !== null) {
                <app-pic class="tlogo" kind="equipos" [name]="favMap(m.p_a_win_if_played)"
                         [fallback]="short(favMap(m.p_a_win_if_played))"
                         [tone]="m.p_a_win_if_played >= 0.5 ? 'gold' : 'cyan'" />
                <span class="score num">
                  <span class="gold-text">{{ pct(m.p_a_win_if_played, 0) }}</span>
                  <span class="dim"> – </span>
                  <span class="cyan-text">{{ pct(complement(m.p_a_win_if_played), 0) }}</span>
                </span>
              }
              <span class="mono small dim">{{ m.p_played >= 0.999 ? 'Se juega seguro' : 'Se juega: ' + pct(m.p_played, 0) }}</span>
            </div>
          }
        </section>

        @if (showNote()) {
          <aside class="info" role="note">
            <div>
              <strong>Cómo leer esta pestaña</strong>
              <p>
                La final todavía no se ha jugado. Las fichas de cada mapa muestran lo que predice el modelo: la
                probabilidad de que {{ s.team_a }} gane ese mapa si llega a jugarse, contando la forma del día.
              </p>
              <p>
                Las tablas sí son <b>datos reales</b>: el promedio de cada jugador en el {{ eventName() }}
                ({{ s.team_a }} jugó {{ teamA().maps }} mapas y {{ s.team_b }}, {{ teamB().maps }}). Para compararlos
                parejo, las kills, muertes, asistencias, daño, oro, CS y wards se pasan a un mapa de
                {{ minutes(s.meta.ref_length_s) }}, que es lo que duran en promedio los mapas de los dos finalistas. Así
                un equipo que juega partidas largas no sale inflado. KP, GPM y visión por minuto se calculan sobre los
                totales.
              </p>
              <p>El valor <u>subrayado</u> es el mejor de los 10 titulares (en K/D/A se toma el mejor KDA).</p>
            </div>
            <button type="button" class="close" (click)="showNote.set(false)" aria-label="Ocultar aviso">×</button>
          </aside>
        }

        @for (t of teams(); track t.name) {
          <section class="team" [attr.aria-label]="'Marcador de ' + t.name">
            <header class="thead">
              <h2 class="eyebrow">{{ t.name }} · marcador</h2>
              <ul class="summary mono">
                <li><span class="dim">Récord en mapas</span> {{ t.data.wins }}-{{ t.data.losses }}</li>
                <li><span class="dim">Duración</span> {{ minutes(t.data.avg_length_s) }}</li>
                <li><span class="dim">Kills/mapa</span> {{ num(t.data.per_game.kills, 1) }}</li>
                <li><span class="dim">Torres</span> {{ num(t.data.per_game.towers, 1) }}</li>
                <li><span class="dim">Dragones</span> {{ num(t.data.per_game.dragons, 1) }}</li>
                <li><span class="dim">Barones</span> {{ num(t.data.per_game.barons, 2) }}</li>
                <li><span class="dim">Primera sangre</span> {{ pct(t.data.first_blood, 0) }}</li>
              </ul>
            </header>
            <div class="scroll-x">
              <table class="board" [class.gold]="t.tone === 'gold'" [class.cyan]="t.tone === 'cyan'">
                <caption class="sr-only">Promedios por jugador de {{ t.name }} en el {{ eventName() }}</caption>
                <thead>
                  <tr>
                    <th scope="col" class="pl">
                      <button type="button" (click)="sortBy('role')" [class.on]="sort() === 'role'">
                        <app-pic class="mini" kind="equipos" [name]="t.name" [fallback]="short(t.name)" [tone]="t.tone" />
                        {{ t.name }}
                      </button>
                    </th>
                    <th scope="col" class="champs">Campeones</th>
                    <th scope="col"><button type="button" (click)="sortBy('kda')" [class.on]="sort() === 'kda'" title="Kills / Muertes / Asistencias por mapa (orden por KDA)">K / D / A</button></th>
                    <th scope="col"><button type="button" (click)="sortBy('kp')" [class.on]="sort() === 'kp'" title="Participación en kills">KP %</button></th>
                    <th scope="col"><button type="button" (click)="sortBy('dmg')" [class.on]="sort() === 'dmg'" title="Daño a campeones por mapa">DMG</button></th>
                    <th scope="col"><button type="button" (click)="sortBy('gold')" [class.on]="sort() === 'gold'" title="Oro por mapa">Oro</button></th>
                    <th scope="col"><button type="button" (click)="sortBy('cs')" [class.on]="sort() === 'cs'" title="CS a los 15 min / CS por mapa">CS</button></th>
                    <th scope="col"><button type="button" (click)="sortBy('gpm')" [class.on]="sort() === 'gpm'" title="Oro por minuto">GPM</button></th>
                    <th scope="col"><button type="button" (click)="sortBy('vspm')" [class.on]="sort() === 'vspm'" title="Puntaje de visión por minuto">Visión/min</button></th>
                    <th scope="col"><button type="button" (click)="sortBy('wards')" [class.on]="sort() === 'wards'" title="Wards puestos / destruidos por mapa">Wards (P/D)</button></th>
                  </tr>
                </thead>
                <tbody>
                  @for (pl of t.rows; track pl.player) {
                    <tr [class.sub]="!pl.starter">
                      <th scope="row" class="pl">
                        <span class="who">
                          <app-pic class="face" kind="jugadores" [name]="pl.player" [tone]="t.tone" />
                          <span class="nm">
                            <span class="name">{{ pl.player }}</span>
                            <span class="role">{{ roleLabel[pl.role] }}{{ pl.starter ? '' : ' · suplente' }} · {{ pl.maps }} mapas</span>
                          </span>
                        </span>
                      </th>
                      <td class="champs">
                        <span class="clist">
                          @for (c of pl.champions; track c.champion) {
                            <span class="champ" [title]="c.champion + ': ' + c.n + ' mapas, ' + c.wins + ' victorias'">
                              <app-pic class="cicon" kind="campeones" [name]="c.champion" />
                              <span class="cn mono">{{ c.n }}</span>
                            </span>
                          }
                        </span>
                      </td>
                      <td [title]="'KDA ' + num(pl.kda, 2)">
                        <span [class.best]="isBest('kda', pl)">
                          {{ num(pl.kills, 1) }}<span class="dim"> / </span><span class="deaths">{{ num(pl.deaths, 1) }}</span><span class="dim"> / </span>{{ num(pl.assists, 1) }}
                        </span>
                      </td>
                      <td><span [class.best]="isBest('kp', pl)">{{ pct(pl.kp, 1) }}</span></td>
                      <td><span [class.best]="isBest('dmg', pl)">{{ k(pl.dmg) }}</span></td>
                      <td><span class="goldv" [class.best]="isBest('gold', pl)">{{ k(pl.gold) }}</span></td>
                      <td class="stack">
                        <span class="dim">{{ num(pl.cs15, 0) }}</span>
                        <span [class.best]="isBest('cs', pl)">{{ num(pl.cs, 0) }}</span>
                      </td>
                      <td><span [class.best]="isBest('gpm', pl)">{{ num(pl.gpm, 0) }}</span></td>
                      <td><span [class.best]="isBest('vspm', pl)">{{ num(pl.vspm, 2) }}</span></td>
                      <td>
                        <span [class.best]="isBest('wards', pl)">{{ num(pl.wards_placed, 1) }}</span>
                        <span class="dim"> / </span>{{ num(pl.wards_killed, 1) }}
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          </section>
        }

        <p class="note">{{ s.meta.nota }}</p>
      }
    } @else {
      <p class="note">Cargando marcador…</p>
    }
  `,
  styles: `
    :host {
      display: block;
      max-width: 1180px;
      margin: 0 auto;
      padding: 0 16px 64px;
    }
    .dim {
      color: var(--ink-3);
    }
    .small {
      font-size: 11px;
    }
    .crumbs {
      font-size: 11.5px;
      color: var(--ink-3);
      margin: 0 0 10px;
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      .here {
        color: var(--ink-2);
      }
    }

    /* Cabecera */
    .match {
      padding: 12px 18px 16px;
      margin-bottom: 14px;
    }
    .status {
      margin: 0 0 6px;
    }
    .versus {
      display: grid;
      grid-template-columns: 1fr auto 1fr;
      align-items: center;
      gap: 18px;
    }
    .side {
      display: flex;
      align-items: center;
      gap: 12px;
      &.a {
        justify-content: flex-end;
      }
    }
    .tname {
      font-family: var(--f-title);
      font-weight: 700;
      font-size: 20px;
    }
    .logo {
      --pic: 52px;
      --pic-radius: 12px;
    }
    .center {
      display: grid;
      justify-items: center;
      gap: 2px;
      text-align: center;
    }
    .probs {
      font-size: 30px;
      font-weight: 700;
      display: flex;
      gap: 10px;
      align-items: baseline;
      span:not(.fav):not(.dash) {
        opacity: 0.7;
        font-size: 22px;
      }
      .dash {
        color: var(--ink-3);
      }
    }
    .likely {
      font-size: 11.5px;
      color: var(--ink-2);
    }

    /* Fichas */
    .tiles {
      display: grid;
      grid-template-columns: repeat(6, minmax(128px, 1fr));
      gap: 10px;
      margin-bottom: 14px;
      overflow-x: auto;
      padding-bottom: 2px;
    }
    .tile {
      display: grid;
      justify-items: center;
      align-content: start;
      gap: 6px;
      padding: 10px 8px 12px;
      border-radius: 12px;
      background: rgba(255, 255, 255, 0.035);
      border: 1px solid var(--line);
      text-align: center;
      &.whole {
        border-color: color-mix(in srgb, var(--gold) 60%, transparent);
        background: color-mix(in srgb, var(--gold) 7%, transparent);
      }
      &.maybe {
        border-style: dashed;
      }
    }
    .tlogo {
      --pic: 34px;
      --pic-radius: 8px;
    }
    .score {
      font-size: 16px;
      font-weight: 700;
      white-space: nowrap;
    }

    /* Aviso */
    .info {
      display: flex;
      gap: 12px;
      align-items: flex-start;
      padding: 10px 14px;
      margin-bottom: 18px;
      border-radius: 10px;
      border: 1px solid color-mix(in srgb, var(--gold) 55%, transparent);
      background: color-mix(in srgb, var(--gold) 6%, transparent);
      font-size: 12.5px;
      color: var(--ink-2);
      strong {
        color: var(--gold-2);
        font-family: var(--f-mono);
        font-size: 11px;
        letter-spacing: 0.1em;
        text-transform: uppercase;
      }
      p {
        margin: 4px 0 0;
      }
      .close {
        margin-left: auto;
        background: none;
        border: 0;
        font-size: 20px;
        line-height: 1;
        cursor: pointer;
        color: var(--ink-2);
      }
    }

    /* Tablas */
    .team {
      margin-bottom: 22px;
    }
    .thead {
      display: flex;
      flex-wrap: wrap;
      align-items: baseline;
      justify-content: space-between;
      gap: 6px 16px;
      margin-bottom: 6px;
      h2 {
        font-size: 11.5px;
        color: var(--ink-2);
      }
    }
    .summary {
      display: flex;
      flex-wrap: wrap;
      gap: 4px 14px;
      list-style: none;
      margin: 0;
      padding: 0;
      font-size: 11.5px;
    }
    .board {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      background: rgba(255, 255, 255, 0.025);
      border: 1px solid var(--line);
      border-radius: 10px;
      th,
      td {
        padding: 7px 10px;
        text-align: right;
        white-space: nowrap;
        border-bottom: 1px solid var(--line);
      }
      td {
        font-family: var(--f-mono);
        font-variant-numeric: tabular-nums;
      }
      thead th {
        font-family: var(--f-mono);
        font-weight: 400;
        font-size: 10.5px;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: var(--ink-3);
        background: rgba(255, 255, 255, 0.03);
        button {
          background: none;
          border: 0;
          padding: 0;
          cursor: pointer;
          color: inherit;
          font: inherit;
          letter-spacing: inherit;
          text-transform: inherit;
          display: inline-flex;
          align-items: center;
          gap: 6px;
          &.on {
            color: var(--ink);
          }
          &.on::after {
            content: '▾';
          }
        }
      }
      .pl {
        text-align: left;
      }
      .champs {
        text-align: left;
      }
      tbody tr:hover {
        background: rgba(255, 255, 255, 0.035);
      }
      tr.sub {
        opacity: 0.7;
      }
      &.gold tbody th {
        box-shadow: inset 3px 0 0 var(--gold);
      }
      &.cyan tbody th {
        box-shadow: inset 3px 0 0 var(--cyan);
      }
    }
    .mini {
      --pic: 18px;
      --pic-radius: 4px;
    }
    .who {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .face {
      --pic: 34px;
      --pic-radius: 50%;
    }
    .nm {
      display: grid;
      line-height: 1.2;
    }
    .name {
      font-family: var(--f-title);
      font-weight: 700;
      font-size: 14px;
      color: var(--ink);
    }
    .role {
      font-size: 11px;
      color: var(--ink-3);
      font-weight: 400;
    }
    .clist {
      display: inline-flex;
      gap: 5px;
    }
    .champ {
      position: relative;
      display: inline-block;
    }
    .cicon {
      --pic: 28px;
      --pic-radius: 5px;
    }
    .cn {
      position: absolute;
      right: -3px;
      bottom: -3px;
      min-width: 14px;
      padding: 0 3px;
      border-radius: 4px;
      font-size: 9.5px;
      line-height: 14px;
      text-align: center;
      background: #0b0f19;
      border: 1px solid var(--line);
      color: var(--ink-2);
    }
    .stack {
      line-height: 1.25;
      span {
        display: block;
      }
    }
    .goldv {
      color: var(--gold-2);
    }
    .deaths {
      color: #ff9aa5;
    }
    .best {
      text-decoration: underline;
      text-decoration-thickness: 2px;
      text-underline-offset: 3px;
      font-weight: 700;
      color: var(--ink);
    }

    @media (max-width: 860px) {
      .versus {
        grid-template-columns: 1fr;
        gap: 8px;
      }
      .side,
      .side.a {
        justify-content: center;
      }
      .side.a {
        flex-direction: row-reverse;
      }
      .tname {
        font-size: 17px;
      }
      .tiles {
        grid-template-columns: repeat(6, 128px);
      }
    }
  `,
})
export class ScoreboardComponent {
  private readonly data = inject(DataService);
  protected readonly sb = this.data.scoreboard;
  protected readonly pred = this.data.prediction;
  protected readonly showNote = signal(true);
  protected readonly sort = signal<SortKey>('role');

  protected readonly pct = pct;
  protected readonly num = num;
  protected readonly date = date;
  protected readonly complement = complement;
  protected readonly short = short;
  protected readonly roleLabel = ROLE_LABEL;

  protected readonly eventName = computed(() => {
    const m = this.sb()?.meta;
    return m ? `${m.league === 'WLDs' ? 'Worlds' : m.league} ${m.year}` : '';
  });

  protected readonly teamA = computed(() => this.sb()!.teams[this.sb()!.team_a]);
  protected readonly teamB = computed(() => this.sb()!.teams[this.sb()!.team_b]);

  protected readonly topScore = computed(() => {
    const scores = this.pred()?.scores ?? [];
    return scores.reduce((a, b) => (b.p > a.p ? b : a), scores[0] ?? { score: '—', p: 0 });
  });

  protected readonly favSeries = computed(() => {
    const s = this.sb()!;
    return (this.pred()?.p_series_a ?? 0.5) >= 0.5 ? s.team_a : s.team_b;
  });

  protected favMap(pA: number): string {
    const s = this.sb()!;
    return pA >= 0.5 ? s.team_a : s.team_b;
  }

  /** Equipos con sus filas ordenadas (titulares primero, suplentes al final). */
  protected readonly teams = computed(() => {
    const s = this.sb();
    if (!s) return [];
    const key = this.sort();
    const order = (rows: ScoreboardPlayer[]) =>
      [...rows].sort((x, y) => {
        if (x.starter !== y.starter) return x.starter ? -1 : 1;
        if (key === 'role') return ROLE_ORDER[x.role] - ROLE_ORDER[y.role];
        return (sortValue(y, key) ?? -Infinity) - (sortValue(x, key) ?? -Infinity);
      });
    return [
      { name: s.team_a, tone: 'gold' as const, data: s.teams[s.team_a], rows: order(s.teams[s.team_a].players) },
      { name: s.team_b, tone: 'cyan' as const, data: s.teams[s.team_b], rows: order(s.teams[s.team_b].players) },
    ] satisfies { name: string; tone: 'gold' | 'cyan'; data: ScoreboardTeam; rows: ScoreboardPlayer[] }[];
  });

  /** Máximo de cada columna entre los 10 titulares. */
  private readonly best = computed(() => {
    const s = this.sb();
    const out = new Map<SortKey, number>();
    if (!s) return out;
    const starters = Object.values(s.teams).flatMap((t) => t.players.filter((p) => p.starter));
    for (const c of BEST_COLS) {
      const vals = starters.map(c.get).filter((v): v is number => v !== null);
      if (vals.length) out.set(c.key, Math.max(...vals));
    }
    return out;
  });

  protected isBest(key: SortKey, p: ScoreboardPlayer): boolean {
    if (!p.starter) return false;
    const v = BEST_COLS.find((c) => c.key === key)!.get(p);
    return v !== null && v === this.best().get(key);
  }

  protected sortBy(key: SortKey): void {
    this.sort.set(this.sort() === key ? 'role' : key);
  }

  /** 13 578 -> "13,6K" */
  protected k(x: number): string {
    return `${num(x / 1000, 1)}K`;
  }

  /** Segundos -> "32:41" */
  protected minutes(sec: number): string {
    const t = Math.round(sec);
    const m = Math.floor(t / 60);
    const s = t % 60;
    return `${m}:${String(s).padStart(2, '0')}`;
  }
}

function sortValue(p: ScoreboardPlayer, key: SortKey): number | null {
  if (key === 'wards') return p.wards_placed;
  if (key === 'role') return null;
  return p[key];
}
