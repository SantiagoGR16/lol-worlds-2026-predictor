import { Injectable, computed, signal } from '@angular/core';
import { AllData } from './models';

/** Archivos que genera el pipeline (web/src/assets/data). El orden es el de la pantalla de carga. */
export const DATA_FILES: { key: keyof AllData; file: string }[] = [
  { key: 'prediction', file: 'prediction.json' },
  { key: 'elo', file: 'elo_history.json' },
  { key: 'topElo', file: 'top_elo.json' },
  { key: 'shap', file: 'shap.json' },
  { key: 'metrics', file: 'metrics.json' },
  { key: 'mvp', file: 'mvp.json' },
  { key: 'draft', file: 'draft.json' },
  { key: 'scoreboard', file: 'scoreboard.json' },
];

export type FileStatus = 'pendiente' | 'ok' | 'error';

/** Carga todos los JSON una sola vez y los expone como signals. */
@Injectable({ providedIn: 'root' })
export class DataService {
  private readonly _data = signal<Partial<AllData>>({});
  readonly status = signal<Record<string, FileStatus>>(
    Object.fromEntries(DATA_FILES.map((f) => [f.file, 'pendiente' as FileStatus])),
  );

  /** Fracción de archivos cargados (0..1): mueve la barra de la pantalla de carga. */
  readonly progress = computed(() => {
    const s = Object.values(this.status());
    return s.filter((x) => x === 'ok').length / s.length;
  });
  readonly ready = computed(() => this.progress() === 1);
  readonly failed = computed(() => Object.values(this.status()).some((x) => x === 'error'));

  readonly prediction = computed(() => this._data().prediction);
  readonly elo = computed(() => this._data().elo);
  readonly topElo = computed(() => this._data().topElo);
  readonly shap = computed(() => this._data().shap);
  readonly metrics = computed(() => this._data().metrics);
  readonly mvp = computed(() => this._data().mvp);
  readonly draft = computed(() => this._data().draft);
  readonly scoreboard = computed(() => this._data().scoreboard);

  private started = false;

  load(): void {
    if (this.started) return;
    this.started = true;
    for (const { key, file } of DATA_FILES) {
      fetch(`assets/data/${file}`, { cache: 'no-cache' })
        .then((r) => {
          if (!r.ok) throw new Error(`${file}: HTTP ${r.status}`);
          return r.json();
        })
        .then((json) => {
          this._data.update((d) => ({ ...d, [key]: json }));
          this.status.update((s) => ({ ...s, [file]: 'ok' }));
        })
        .catch((err) => {
          console.error(err);
          this.status.update((s) => ({ ...s, [file]: 'error' }));
        });
    }
  }
}
