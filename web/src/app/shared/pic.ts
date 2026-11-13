import { Component, computed, input, signal } from '@angular/core';

/**
 * Interruptor de imágenes de terceros (fotos de jugadores, logos e íconos de campeones).
 * Son imágenes de uso privado (de Riot y de los equipos). Con `false` la web vuelve a usar
 * solo insignias propias con iniciales, como en la versión pública.
 */
export const USE_IMAGES = true;

/** Carpetas dentro de src/assets/img/. */
export type PicKind = 'equipos' | 'jugadores' | 'campeones';

/**
 * Índice de imágenes disponibles (assets/img/index.json, lo genera scripts/img-index.mjs antes
 * de `npm start` / `npm run build`): tipo -> slug -> archivo. Se carga una sola vez.
 */
const imgIndex = signal<Record<string, Record<string, string>> | null>(null);
let indexRequested = false;
function loadIndex(): void {
  if (indexRequested || !USE_IMAGES) return;
  indexRequested = true;
  fetch('assets/img/index.json', { cache: 'no-cache' })
    .then((r) => (r.ok ? r.json() : {}))
    .then((j) => imgIndex.set(j))
    .catch(() => imgIndex.set({}));
}

/**
 * Ruta de una imagen si figura en el índice (null si falta o están desactivadas).
 * Lee una señal: dentro de un computed() se actualiza cuando llega el índice.
 */
export function picSrc(kind: PicKind, name: string): string | null {
  loadIndex();
  const file = imgIndex()?.[kind]?.[slug(name)];
  return USE_IMAGES && file ? `assets/img/${kind}/${file}` : null;
}

/** Nombre de archivo: minúsculas, sin acentos ni signos. "Kai'Sa" -> "kaisa", "Gen.G" -> "geng". */
export function slug(name: string): string {
  return name
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]/g, '');
}

/**
 * Imagen con respaldo: usa assets/img/<tipo>/<archivo> si figura en el índice y, si no
 * existe, falla al cargar o las imágenes están desactivadas, muestra una insignia con iniciales.
 */
@Component({
  selector: 'app-pic',
  template: `
    @if (src(); as s) {
      <img [src]="s" [alt]="alt()" [title]="alt()" (error)="broken.set(true)" loading="lazy" decoding="async"
           [class.contain]="kind() === 'equipos'" />
    } @else {
      <span class="fb" [class]="'fb ' + tone()" [title]="alt()" role="img" [attr.aria-label]="alt()">{{ initials() }}</span>
    }
  `,
  styles: `
    :host {
      display: inline-grid;
      place-items: center;
      width: var(--pic, 28px);
      height: var(--pic, 28px);
      flex: none;
      border-radius: var(--pic-radius, 6px);
      overflow: hidden;
    }
    img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      // Los logos no son cuadrados: se muestran enteros.
      &.contain {
        object-fit: contain;
      }
    }
    .fb {
      display: grid;
      place-items: center;
      width: 100%;
      height: 100%;
      font-family: var(--f-title);
      font-weight: 700;
      font-size: calc(var(--pic, 28px) * 0.36);
      letter-spacing: 0.04em;
      color: var(--ink-2);
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid var(--line);
      border-radius: inherit;
      &.gold {
        background: linear-gradient(135deg, var(--gold), var(--gold-2));
        color: #1b1303;
        border: 0;
      }
      &.cyan {
        background: linear-gradient(135deg, var(--cyan), var(--cyan-2));
        color: #021a21;
        border: 0;
      }
    }
  `,
})
export class PicComponent {
  readonly kind = input.required<PicKind>();
  readonly name = input.required<string>();
  /** Texto de la insignia de respaldo (por defecto, 2-3 letras del nombre). */
  readonly fallback = input<string>('');
  readonly tone = input<'gold' | 'cyan' | 'plain'>('plain');

  protected readonly broken = signal(false);
  protected readonly alt = computed(() => this.name());
  protected readonly initials = computed(
    () => this.fallback() || this.name().replace(/[^A-Za-z0-9]/g, '').slice(0, this.kind() === 'equipos' ? 3 : 2).toUpperCase(),
  );
  protected readonly src = computed(() => {
    const file = imgIndex()?.[this.kind()]?.[slug(this.name())];
    return USE_IMAGES && file && !this.broken() ? `assets/img/${this.kind()}/${file}` : null;
  });

  constructor() {
    loadIndex();
  }
}
