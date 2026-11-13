import { Component, inject } from '@angular/core';
import { UiStateService } from '../ui/ui-state.service';
import { BASE_A, BASE_B, BOUNDARY, FULL_VIEW, LANES, MAP_IMAGE, MAP_IMAGE_TRANSFORM, POIS, RIVER } from '../map/geometry';
import { USE_IMAGES } from '../shared/pic';

/** Minimapa: puntos clicables y el recuadro de la cámara actual. */
@Component({
  selector: 'app-minimap',
  template: `
    <nav class="mini glass violet" aria-label="Minimapa">
      <svg [attr.viewBox]="vb" preserveAspectRatio="xMidYMid meet">
        @if (useImage) {
          <clipPath id="miniDiamond"><path [attr.d]="boundary" /></clipPath>
          <image [attr.href]="mapImage" x="0" y="0" width="100" height="100" preserveAspectRatio="none"
                 [attr.transform]="mapImageTransform" clip-path="url(#miniDiamond)" class="bg" />
          <path [attr.d]="boundary" class="edge img" />
        } @else {
          <path [attr.d]="boundary" class="edge" />
          <path [attr.d]="river" class="river" />
        }
        @for (l of lanes; track $index) {
          <path [attr.d]="l" class="lane" />
        }
        <circle [attr.cx]="a.x" [attr.cy]="a.y" r="34" class="base gold" />
        <circle [attr.cx]="b.x" [attr.cy]="b.y" r="34" class="base cyan" />
        <rect
          class="cam"
          [attr.x]="ui.viewBox().x"
          [attr.y]="ui.viewBox().y"
          [attr.width]="ui.viewBox().w"
          [attr.height]="ui.viewBox().h"
        />
        @for (p of pois; track p.id) {
          <circle
            [attr.cx]="p.at.x"
            [attr.cy]="p.at.y"
            r="42"
            class="dot"
            [class.active]="ui.activePoi() === p.id"
            tabindex="0"
            role="button"
            [attr.aria-label]="'Ir a ' + p.place"
            (click)="ui.select(p.id)"
            (keydown.enter)="ui.select(p.id)"
          >
            <title>{{ p.place }} · {{ p.title }}</title>
          </circle>
        }
      </svg>
    </nav>
  `,
  styles: `
    .mini {
      width: 196px;
      padding: 8px;
    }
    svg {
      width: 100%;
      display: block;
    }
    .edge {
      fill: rgba(18, 24, 40, 0.7);
      stroke: rgba(157, 123, 255, 0.6);
      stroke-width: 8;
      &.img {
        fill: rgba(5, 7, 13, 0.3);
      }
    }
    .bg {
      filter: saturate(0.85) brightness(0.9);
    }
    .river {
      fill: none;
      stroke: rgba(106, 125, 255, 0.5);
      stroke-width: 30;
    }
    .lane {
      fill: none;
      stroke: rgba(201, 182, 255, 0.5);
      stroke-width: 10;
    }
    .base.gold {
      fill: var(--gold);
    }
    .base.cyan {
      fill: var(--cyan);
    }
    .cam {
      fill: rgba(157, 123, 255, 0.08);
      stroke: #e9edf6;
      stroke-width: 8;
      stroke-dasharray: 30 20;
    }
    .dot {
      fill: #0f1420;
      stroke: var(--violet-2);
      stroke-width: 12;
      cursor: pointer;
      outline: none;
      &.active,
      &:hover,
      &:focus-visible {
        fill: var(--violet);
        stroke: #fff;
      }
    }
  `,
})
export class MinimapComponent {
  protected readonly ui = inject(UiStateService);
  protected readonly pois = POIS;
  protected readonly useImage = USE_IMAGES;
  protected readonly mapImage = MAP_IMAGE;
  protected readonly mapImageTransform = MAP_IMAGE_TRANSFORM;
  protected readonly boundary = BOUNDARY;
  protected readonly river = RIVER;
  protected readonly lanes = [LANES.top, LANES.mid, LANES.bot];
  protected readonly a = BASE_A;
  protected readonly b = BASE_B;
  protected readonly vb = `${FULL_VIEW.x + 60} ${FULL_VIEW.y + 60} ${FULL_VIEW.w - 120} ${FULL_VIEW.h - 120}`;
}
