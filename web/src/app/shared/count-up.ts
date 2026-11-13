import { Directive, ElementRef, effect, inject, input } from '@angular/core';
import { gsap } from 'gsap';
import { UiStateService } from '../ui/ui-state.service';
import { num, pct } from './format';

/** Número que cuenta desde 0 al entrar (sin animación con prefers-reduced-motion). */
@Directive({ selector: '[appCountUp]' })
export class CountUpDirective {
  readonly appCountUp = input.required<number>();
  readonly format = input<'pct' | 'num'>('pct');
  readonly digits = input(1);

  private readonly el = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly ui = inject(UiStateService);

  constructor() {
    effect((onCleanup) => {
      const target = this.appCountUp();
      const fmt = (v: number) => (this.format() === 'pct' ? pct(v, this.digits()) : num(v, this.digits()));
      if (this.ui.reducedMotion()) {
        this.el.nativeElement.textContent = fmt(target);
        return;
      }
      const state = { v: 0 };
      const tw = gsap.to(state, {
        v: target,
        duration: 1.2,
        ease: 'power2.out',
        onUpdate: () => (this.el.nativeElement.textContent = fmt(state.v)),
      });
      onCleanup(() => tw.kill());
    });
  }
}
