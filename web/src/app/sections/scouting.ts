import { Component, ElementRef, computed, effect, inject } from '@angular/core';
import { DataService } from '../data/data.service';
import { MvpPlayer, Role } from '../data/models';
import { UiStateService } from '../ui/ui-state.service';
import { ROLE_LABEL, num, pct } from '../shared/format';
import { short } from '../shared/event';
import { PicComponent } from '../shared/pic';

const ROLES: Role[] = ['top', 'jng', 'mid', 'bot', 'sup'];

/**
 * Jugadores · Scouting: candidatos a MVP por rol y draft esperado. Hover sobre un rol ilumina su
 * línea; clic (o clic en un jugador del mapa) lleva la cámara a los dos jugadores de ese rol.
 */
@Component({
  selector: 'app-scouting',
  imports: [PicComponent],
  template: `
    @if (mvp(); as m) {
      <h3 class="sub">MVP por rol <span class="note">({{ m.meta.league }} {{ m.meta.year }}, {{ m.meta.maps }} mapas)</span></h3>
      <div class="how panel">
        <p class="eyebrow">¿Qué es el número de la derecha?</p>
        <ul>
          <li>Es el <strong>puntaje MVP</strong> (no es un porcentaje).</li>
          <li>Compara a cada jugador con <strong>todos los de su mismo rol</strong> en el Mundial, en 5 datos: KDA,
            participación en kills (KP), daño por minuto, oro de ventaja al minuto 15 y % del daño de su equipo.</li>
          <li>Cuenta más rendir bien contra rivales fuertes (según su Elo).</li>
          <li><strong>0</strong> = jugador promedio de su rol · <strong>+1</strong> = muy por encima · <strong>+2</strong>
            = de lo mejor del torneo · <strong>negativo</strong> = por debajo del promedio.</li>
          <li><span class="star">★ MVP</span> marca al jugador con el puntaje más alto de cada equipo.</li>
        </ul>
      </div>
      <div class="roles">
        @for (r of rows(); track r.role) {
          <div
            class="role panel"
            [class.focus]="ui.focusRole() === r.role"
            [attr.data-role]="r.role"
            role="button"
            [attr.aria-pressed]="ui.focusRole() === r.role"
            (click)="toggle(r.role)"
            (keydown.enter)="toggle(r.role)"
            (mouseenter)="ui.hoveredRole.set(r.role)"
            (mouseleave)="ui.hoveredRole.set(null)"
            (focusin)="ui.hoveredRole.set(r.role)"
            (focusout)="ui.hoveredRole.set(null)"
            tabindex="0"
            [attr.aria-label]="'Rol ' + roleLabel[r.role] + ': ver draft y mapa'"
          >
            <span class="eyebrow">{{ roleLabel[r.role] }} <span class="go" aria-hidden="true">ver draft y mapa →</span></span>
            @for (pl of r.players; track pl.player) {
              <div class="pl" [class.cand]="pl.mvp_candidate">
                <span class="badge" [class]="'badge ' + colorOf(pl.team)">{{ short(pl.team) }}</span>
                <span class="name">{{ pl.player }}</span>
                @if (pl.mvp_candidate) {
                  <span class="star" title="Candidato a MVP">★ MVP</span>
                }
                <span class="num score" title="Puntaje MVP: 0 = promedio del rol; positivo = mejor; no es un %">{{ num(pl.mvp_score, 2) }}</span>
                <span class="num kda">KDA {{ num(pl.kda, 1) }} · KP {{ pct(pl.kp, 0) }}</span>
              </div>
            }
            <!-- Rol elegido: draft esperado (top 3 picks) de los dos jugadores, ahí mismo. -->
            @if (ui.focusRole() === r.role) {
              <div class="role-picks" (click)="$event.stopPropagation()">
                <span class="eyebrow">Draft esperado · top 3 picks</span>
                <div class="picks">
                  @for (pl of picksFor(r.role); track pl.name) {
                    <div class="pick panel">
                      <span class="badge" [class]="'badge ' + colorOf(pl.team)">{{ short(pl.team) }}</span>
                      <span class="name">{{ pl.name }}</span>
                      <span></span>
                      <ol>
                        @for (c of pl.picks; track c.champion) {
                          <li><span class="champ"><app-pic class="ci" kind="campeones" [name]="c.champion" />{{ c.champion }}</span><span class="num">{{ pct(c.p, 0) }} <small>n={{ c.n }}</small></span></li>
                        } @empty {
                          <li><span class="note">Sin datos de picks.</span></li>
                        }
                      </ol>
                    </div>
                  }
                </div>
              </div>
            }
          </div>
        }
      </div>
    }

    @if (draft(); as d) {
      <h3 class="sub">Resumen del draft: top 3 picks de todos</h3>
      <div class="picks">
        @for (pl of pickRows(); track pl.name) {
          <div
            class="pick panel"
            (mouseenter)="ui.hoveredRole.set(pl.role)"
            (mouseleave)="ui.hoveredRole.set(null)"
          >
            <span class="badge" [class]="'badge ' + colorOf(pl.team)">{{ short(pl.team) }}</span>
            <span class="name">{{ pl.name }}</span>
            <span class="eyebrow">{{ roleLabel[pl.role] }}</span>
            <ol>
              @for (c of pl.picks; track c.champion) {
                <li><span class="champ"><app-pic class="ci" kind="campeones" [name]="c.champion" />{{ c.champion }}</span><span class="num">{{ pct(c.p, 0) }} <small>n={{ c.n }}</small></span></li>
              }
            </ol>
          </div>
        }
      </div>

      <div class="bans">
        @for (t of teamsList(); track t.name) {
          <div class="panel">
            <span class="eyebrow">Bans de {{ t.name }}</span>
            <ul>
              @for (b of d.bans_by[t.name].slice(0, 5); track b.champion) {
                <li><span class="champ"><app-pic class="ci" kind="campeones" [name]="b.champion" />{{ b.champion }}</span><span class="num">{{ pct(b.rate, 0) }}</span></li>
              }
            </ul>
          </div>
        }
      </div>

      @if (d.crossovers.length) {
        <h3 class="sub">Choques en el draft</h3>
        <p class="note">Son campeones que un jugador elige seguido y que el rival suele banear. Ahí es probable que se pelee el draft.</p>
        <ul class="cross">
          @for (c of d.crossovers; track c.player + c.champion) {
            <li (mouseenter)="ui.hoveredRole.set(c.role)" (mouseleave)="ui.hoveredRole.set(null)">
              <span class="champ"><app-pic class="ci" kind="campeones" [name]="c.champion" /><strong>{{ c.champion }}</strong></span>
              <ul>
                <li><strong>{{ c.player }}</strong> ({{ c.team }}) lo elige en el <span class="num">{{ pct(c.p_pick, 0) }}</span> de sus mapas.</li>
                <li><strong>{{ c.rival }}</strong> lo banea en el <span class="num">{{ pct(c.rival_ban_rate, 0) }}</span> de sus mapas.</li>
                <li class="mut">Si {{ c.rival }} lo banea otra vez, {{ c.player }} tendrá que jugar otra cosa. Si lo deja pasar, {{ c.team }} lo puede tomar.</li>
              </ul>
            </li>
          }
        </ul>
      }
      <div class="how panel">
        <p class="eyebrow">Cómo leer los % de pick</p>
        <ul>
          <li>El % es la probabilidad de que el jugador elija ese campeón en un mapa.</li>
          <li>Mezcla un <strong>{{ pct(1 - d.meta.prior_weight, 0) }}</strong> de lo que jugó en el Mundial y un <strong>{{ pct(d.meta.prior_weight, 0) }}</strong> de lo que jugó en
            todo el año con los mismos parches (así no depende solo de pocos mapas).</li>
          <li><strong>n</strong> = cuántos mapas lo jugó en el Mundial.</li>
        </ul>
      </div>
    }
  `,
  styles: `
    .how {
      padding: 10px 12px;
      margin: 6px 0 12px;
      border-color: rgba(157, 123, 255, 0.45);
      background: rgba(157, 123, 255, 0.06);
      .eyebrow {
        margin: 0 0 4px;
        color: var(--violet-2);
      }
      ul {
        margin: 0;
        padding-left: 18px;
        font-size: 12.5px;
        line-height: 1.5;
        color: var(--ink-2);
      }
      li {
        margin-bottom: 3px;
      }
      strong {
        color: var(--ink);
      }
    }
    .cross {
      list-style: none;
      padding-left: 0 !important;
      > li {
        margin-bottom: 10px !important;
      }
      ul {
        margin: 4px 0 0;
        padding-left: 18px;
      }
      .mut {
        color: var(--ink-3);
      }
    }
    .sub {
      font-size: 14px;
      margin: 6px 0 8px;
    }
    .roles {
      display: grid;
      gap: 6px;
    }
    .role {
      padding: 8px 10px;
      cursor: pointer;
      transition: border-color 0.2s, background 0.2s;
      .go {
        float: right;
        letter-spacing: 0.04em;
        text-transform: none;
        color: var(--ink-3);
        opacity: 0;
        transition: opacity 0.2s;
      }
      &:hover,
      &:focus-visible {
        border-color: rgba(157, 123, 255, 0.6);
        background: rgba(157, 123, 255, 0.07);
        .go {
          opacity: 1;
        }
      }
      .role-picks {
        margin-top: 10px;
        padding-top: 8px;
        border-top: 1px solid var(--line);
        cursor: default;
        .eyebrow {
          display: block;
          margin-bottom: 6px;
        }
      }
      // Rol que la cámara está mostrando.
      &.focus {
        border-color: var(--cyan-2);
        background: rgba(35, 213, 255, 0.08);
      }
    }
    .pl {
      display: grid;
      grid-template-columns: auto 1fr auto auto;
      gap: 2px 8px;
      align-items: center;
      margin-top: 4px;
      &.cand .name {
        color: var(--ink);
        font-weight: 600;
      }
    }
    .name {
      font-size: 13.5px;
    }
    .star {
      font-size: 10.5px;
      font-family: var(--f-mono);
      color: var(--violet-2);
      border: 1px solid rgba(157, 123, 255, 0.6);
      border-radius: 6px;
      padding: 0 5px;
    }
    .score {
      grid-column: 4;
      grid-row: 1;
      font-size: 13px;
    }
    .kda {
      grid-column: 2 / -1;
      font-size: 11px;
      color: var(--ink-3);
    }
    .picks {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px;
    }
    .pick {
      padding: 8px 10px;
      display: grid;
      grid-template-columns: auto 1fr auto;
      gap: 4px 8px;
      align-items: center;
      ol {
        grid-column: 1 / -1;
        list-style: none;
        margin: 4px 0 0;
        padding: 0;
        font-size: 12.5px;
        display: grid;
        gap: 4px;
      }
      li {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 6px;
      }
      small {
        color: var(--ink-3);
      }
    }
    .bans {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px;
      margin-top: 8px;
      ul {
        list-style: none;
        padding: 0;
        margin: 4px 0 0;
        font-size: 12.5px;
      }
      li {
        display: flex;
        justify-content: space-between;
      }
    }
    // Campeón: ícono pequeño (aportado por el usuario, img/campeones) + nombre.
    .champ {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      min-width: 0;
    }
    .ci {
      --pic: 24px;
      --pic-radius: 5px;
      box-shadow: 0 0 0 1px var(--line);
    }
    .bans li {
      align-items: center;
      margin-bottom: 4px;
    }
    .cross {
      padding-left: 18px;
      margin: 0 0 8px;
      font-size: 12.5px;
      color: var(--ink-2);
      li {
        margin-bottom: 4px;
      }
    }
    @media (max-width: 520px) {
      .picks,
      .bans {
        grid-template-columns: 1fr;
      }
    }
  `,
})
export class ScoutingSection {
  private readonly data = inject(DataService);
  protected readonly ui = inject(UiStateService);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  /** Al elegir un rol (también desde el mapa), su bloque se desplaza a la vista en la tarjeta. */
  private readonly scrollToRole = effect(() => {
    const role = this.ui.focusRole();
    if (!role) return;
    setTimeout(() =>
      this.host.nativeElement.querySelector(`[data-role="${role}"]`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }),
    );
  });
  protected readonly mvp = computed(() => this.data.mvp());
  protected readonly draft = computed(() => this.data.draft());
  protected readonly roleLabel = ROLE_LABEL;
  protected readonly num = num;
  protected readonly pct = pct;
  protected readonly short = short;

  protected readonly teamsList = computed(() => {
    const p = this.data.prediction();
    return p ? [{ name: p.team_a }, { name: p.team_b }] : [];
  });

  protected colorOf(team: string): string {
    return team === this.data.prediction()?.team_a ? 'gold' : 'cyan';
  }

  protected readonly rows = computed(() => {
    const players = this.mvp()?.players ?? [];
    const order = this.teamsList().map((t) => t.name);
    return ROLES.map((role) => ({
      role,
      players: players
        .filter((p) => p.role === role)
        .sort((a: MvpPlayer, b: MvpPlayer) => order.indexOf(a.team) - order.indexOf(b.team)),
    }));
  });

  /** Clic en un rol: lo abre (cámara + draft); otro clic sobre el mismo lo cierra. */
  protected toggle(role: Role): void {
    if (this.ui.focusRole() === role) {
      this.ui.focusRole.set(null);
    } else {
      this.ui.focus(role);
    }
  }

  /** Top 3 picks de los dos jugadores de un rol (Gen.G primero). */
  protected picksFor(role: Role) {
    return this.pickRows().filter((p) => p.role === role);
  }

  protected readonly pickRows = computed(() => {
    const d = this.draft();
    if (!d) return [];
    const order = this.teamsList().map((t) => t.name);
    return Object.entries(d.players)
      .map(([name, info]) => ({ name, team: info.team, role: info.role, picks: (d.picks[name] ?? []).slice(0, 3) }))
      .sort((a, b) => ROLES.indexOf(a.role) - ROLES.indexOf(b.role) || order.indexOf(a.team) - order.indexOf(b.team));
  });
}
