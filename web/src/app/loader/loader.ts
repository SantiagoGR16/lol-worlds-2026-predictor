import { Component, DestroyRef, ElementRef, computed, inject, output, signal, viewChild } from '@angular/core';
import { DomSanitizer } from '@angular/platform-browser';
import { DataService } from '../data/data.service';

/** Video de YouTube de la portada: pantalla de inicio de la final del Mundial 2015 (canal oficial de LoL Corea). */
const VIDEO_ID = '-MBvUX8FWos';
// youtube-nocookie: no deja cookies de seguimiento hasta que el usuario interactúa con el video.
const YT_ORIGIN = 'https://www.youtube-nocookie.com';
// Sin loop=1: repetir con la API (seekTo) evita que YouTube recargue y vuelva a mostrar sus controles.
const VIDEO_URL =
  `${YT_ORIGIN}/embed/${VIDEO_ID}?autoplay=1&mute=1` +
  '&controls=0&rel=0&playsinline=1&modestbranding=1&iv_load_policy=3&disablekb=1&enablejsapi=1';
/** Imagen del propio video: tapa los controles que YouTube muestra unos segundos al arrancar. */
const POSTER = `https://i.ytimg.com/vi/${VIDEO_ID}/maxresdefault.jpg`;
/** Tiempo que YouTube deja visibles sus controles (⏮ ⏸ ⏭) tras empezar a reproducir. */
const CONTROLS_MS = 3500;

/** Portada: video de fondo y el botón para entrar. El botón se activa cuando los JSON ya cargaron. */
@Component({
  selector: 'app-loader',
  template: `
    <section class="intro" aria-label="Portada">
      <div class="video" aria-hidden="true" [style.background-image]="'url(' + poster + ')'">
        <iframe
          #yt
          [class.on]="showVideo()"
          (load)="listen()"
          [src]="src"
          title="Video de portada"
          tabindex="-1"
          allow="autoplay; encrypted-media"
          referrerpolicy="strict-origin-when-cross-origin"
        ></iframe>
      </div>
      <div class="shade" aria-hidden="true"></div>

      <div class="cta">
        <button class="enter" type="button" [disabled]="!data.ready()" (click)="enter.emit()">
          @if (data.ready()) {
            ENTRAR A LA GRIETA
          } @else {
            CARGANDO… {{ percent() }} %
          }
        </button>
        @if (data.failed()) {
          <p class="err">No se pudieron leer todos los datos. Corre scripts/run_pipeline.py.</p>
        }
      </div>

      <button class="sound" type="button" (click)="toggleSound()" [attr.aria-pressed]="!muted()"
              [attr.aria-label]="muted() ? 'Activar sonido del video' : 'Silenciar video'">
        {{ muted() ? '🔇 Activar sonido' : '🔊 Silenciar' }}
      </button>
      <p class="note">Video: League of Legends (Riot Games) · Proyecto no afiliado a Riot Games ni a los equipos.</p>
    </section>
  `,
  styles: `
    .intro {
      position: fixed;
      inset: 0;
      z-index: 50;
      overflow: hidden;
      background: #05070d;
    }
    // El iframe cubre toda la pantalla (como background-size: cover) manteniendo 16:9.
    .video {
      position: absolute;
      inset: 0;
      pointer-events: none;
      background: center / cover no-repeat;
      iframe {
        opacity: 0;
        transition: opacity 0.8s ease;
        &.on {
          opacity: 1;
        }
        position: absolute;
        top: 50%;
        left: 50%;
        width: max(100vw, 177.78vh);
        height: max(56.25vw, 100vh);
        // Un poco más grande para recortar los bordes y el título que muestra YouTube al empezar.
        transform: translate(-50%, -50%) scale(1.12);
        border: 0;
      }
    }
    .shade {
      position: absolute;
      inset: 0;
      background:
        linear-gradient(to top, rgba(5, 7, 13, 0.92) 0%, rgba(5, 7, 13, 0.35) 32%, transparent 55%),
        radial-gradient(ellipse at center, transparent 55%, rgba(5, 7, 13, 0.55) 100%);
    }
    .cta {
      position: absolute;
      left: 50%;
      bottom: 13vh;
      transform: translateX(-50%);
      width: min(420px, calc(100vw - 32px));
      text-align: center;
    }
    .enter {
      width: 100%;
      padding: 16px;
      border-radius: 12px;
      border: 1px solid var(--violet);
      background: linear-gradient(90deg, rgba(232, 182, 76, 0.28), rgba(157, 123, 255, 0.4), rgba(35, 213, 255, 0.28));
      backdrop-filter: blur(6px);
      font-family: var(--f-title);
      font-weight: 700;
      font-size: 15px;
      letter-spacing: 0.2em;
      color: var(--ink);
      cursor: pointer;
      box-shadow: 0 0 24px rgba(157, 123, 255, 0.35);
      transition: box-shadow 0.2s, transform 0.2s;
      &:hover:not(:disabled) {
        box-shadow: 0 0 36px rgba(157, 123, 255, 0.75);
        transform: translateY(-1px);
      }
      &:disabled {
        opacity: 0.6;
        cursor: progress;
      }
    }
    .err {
      margin: 10px 0 0;
      color: var(--danger);
      font-size: 12.5px;
    }
    .sound {
      position: absolute;
      right: 16px;
      bottom: 16px;
      padding: 7px 12px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(5, 7, 13, 0.6);
      font-size: 12px;
      cursor: pointer;
      &:hover {
        border-color: var(--glow);
      }
    }
    .note {
      position: absolute;
      left: 16px;
      bottom: 20px;
      right: 170px;
      margin: 0;
      font-size: 11.5px;
      color: var(--ink-3);
    }
    @media (max-width: 600px) {
      .note {
        right: 16px;
        bottom: 56px;
        text-align: center;
      }
      .cta {
        bottom: 18vh;
      }
    }
  `,
})
export class LoaderComponent {
  protected readonly data = inject(DataService);
  readonly enter = output<void>();
  // URL fija escrita en el código (no viene del usuario): segura para el iframe.
  protected readonly src = inject(DomSanitizer).bypassSecurityTrustResourceUrl(VIDEO_URL);
  protected readonly percent = computed(() => Math.round(this.data.progress() * 100));
  protected readonly poster = POSTER;
  protected readonly muted = signal(true);
  /** El iframe se muestra cuando YouTube ya ocultó sus controles; antes se ve la imagen del video. */
  protected readonly showVideo = signal(false);
  private readonly yt = viewChild<ElementRef<HTMLIFrameElement>>('yt');
  private revealTimer: ReturnType<typeof setTimeout> | undefined;

  constructor() {
    // Mensajes del reproductor (API de iframes de YouTube): estado de reproducción.
    const onMsg = (ev: MessageEvent) => {
      if (ev.origin !== YT_ORIGIN || typeof ev.data !== 'string') return;
      let msg: { event?: string; info?: unknown };
      try {
        msg = JSON.parse(ev.data);
      } catch {
        return;
      }
      const state =
        msg.event === 'onStateChange'
          ? msg.info
          : (msg.info as { playerState?: number } | null)?.playerState;
      if (state === 1 && !this.showVideo() && this.revealTimer === undefined) {
        // 1 = reproduciendo: esperar a que YouTube oculte sus controles.
        this.revealTimer = setTimeout(() => this.showVideo.set(true), CONTROLS_MS);
      } else if (state === 0) {
        // 0 = terminó: volver al inicio sin recargar el reproductor.
        this.cmd('seekTo', [0, true]);
        this.cmd('playVideo');
      }
    };
    window.addEventListener('message', onMsg);
    inject(DestroyRef).onDestroy(() => {
      window.removeEventListener('message', onMsg);
      clearTimeout(this.revealTimer);
    });
  }

  /** Pide al reproductor que avise de sus cambios de estado. */
  protected listen(): void {
    this.yt()?.nativeElement.contentWindow?.postMessage(JSON.stringify({ event: 'listening', id: 'portada' }), YT_ORIGIN);
  }

  private cmd(func: string, args: unknown[] = []): void {
    this.yt()?.nativeElement.contentWindow?.postMessage(JSON.stringify({ event: 'command', func, args }), YT_ORIGIN);
  }

  /** El autoplay solo funciona en silencio; el sonido se activa con un clic (API de iframes de YouTube). */
  protected toggleSound(): void {
    const next = !this.muted();
    if (next) {
      this.cmd('mute');
    } else {
      this.cmd('unMute');
      this.cmd('setVolume', [70]);
    }
    this.muted.set(next);
  }
}
