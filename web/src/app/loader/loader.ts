import { Component, computed, inject, output } from '@angular/core';
import { DATA_FILES, DataService } from '../data/data.service';
import { EVENT_LABEL } from '../shared/event';

/** Pantalla de carga tipo terminal: la barra llega a 100 % cuando los JSON están listos. */
@Component({
  selector: 'app-loader',
  template: `
    <section class="loader" aria-labelledby="loader-title">
      <div class="term glass violet">
        <p class="eyebrow">lolpred · tablero táctico</p>
        <h1 id="loader-title" class="title">{{ label }}</h1>
        <ul class="lines mono" aria-live="polite">
          @for (f of files; track f.file; let i = $index) {
            <li [style.animation-delay]="i * 90 + 'ms'">
              <span class="prompt">&gt;</span> cargar {{ f.file }}
              <span class="st" [class]="'st ' + data.status()[f.file]">{{ data.status()[f.file] }}</span>
            </li>
          }
        </ul>
        <div
          class="bar"
          role="progressbar"
          aria-label="Carga de datos"
          aria-valuemin="0"
          aria-valuemax="100"
          [attr.aria-valuenow]="percent()"
        >
          <div class="fill" [style.width.%]="percent()"></div>
        </div>
        <div class="row">
          <span class="mono pct">{{ percent() }} %</span>
          @if (data.failed()) {
            <span class="err">No se pudieron leer todos los datos. Corre scripts/run_pipeline.py.</span>
          }
        </div>
        <button class="enter" type="button" [disabled]="!data.ready()" (click)="enter.emit()">
          ENTRAR A LA GRIETA
        </button>
        <p class="note">Uso personal, no comercial · Proyecto no afiliado a Riot Games ni a los equipos.</p>
      </div>
    </section>
  `,
  styles: `
    .loader {
      position: fixed;
      inset: 0;
      z-index: 50;
      display: grid;
      place-items: center;
      padding: 16px;
    }
    .term {
      width: min(560px, 100%);
      padding: 28px 28px 22px;
    }
    .title {
      font-size: clamp(20px, 3.4vw, 28px);
      margin: 6px 0 18px;
      background: linear-gradient(90deg, var(--gold-2), var(--violet-2), var(--cyan-2));
      -webkit-background-clip: text;
      background-clip: text;
      color: transparent;
    }
    .lines {
      list-style: none;
      padding: 0;
      margin: 0 0 18px;
      font-size: 13px;
      color: var(--ink-2);
      li {
        opacity: 0;
        animation: type 0.3s ease-out forwards;
      }
    }
    .prompt {
      color: var(--violet-2);
    }
    .st {
      float: right;
      &.ok {
        color: #7ef0a0;
      }
      &.error {
        color: var(--danger);
      }
      &.pendiente {
        color: var(--ink-3);
      }
    }
    .bar {
      height: 6px;
      border-radius: 99px;
      background: rgba(255, 255, 255, 0.07);
      overflow: hidden;
    }
    .fill {
      height: 100%;
      background: linear-gradient(90deg, var(--gold), var(--violet), var(--cyan));
      box-shadow: 0 0 16px var(--violet);
      transition: width 0.4s ease;
    }
    .row {
      display: flex;
      gap: 12px;
      justify-content: space-between;
      margin: 8px 0 18px;
      font-size: 12px;
    }
    .err {
      color: var(--danger);
    }
    .enter {
      width: 100%;
      padding: 14px;
      border-radius: 12px;
      border: 1px solid var(--violet);
      background: linear-gradient(90deg, rgba(232, 182, 76, 0.18), rgba(157, 123, 255, 0.3), rgba(35, 213, 255, 0.18));
      font-family: var(--f-title);
      font-weight: 700;
      letter-spacing: 0.18em;
      cursor: pointer;
      transition: box-shadow 0.2s, transform 0.2s;
      &:hover:not(:disabled) {
        box-shadow: 0 0 28px rgba(157, 123, 255, 0.6);
        transform: translateY(-1px);
      }
      &:disabled {
        opacity: 0.4;
        cursor: progress;
      }
    }
    .note {
      margin: 14px 0 0;
      text-align: center;
    }
    @keyframes type {
      from {
        opacity: 0;
        transform: translateX(-6px);
      }
      to {
        opacity: 1;
        transform: none;
      }
    }
  `,
})
export class LoaderComponent {
  protected readonly data = inject(DataService);
  readonly enter = output<void>();
  protected readonly label = EVENT_LABEL;
  protected readonly files = DATA_FILES;
  protected readonly percent = computed(() => Math.round(this.data.progress() * 100));
}
