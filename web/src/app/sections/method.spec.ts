import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { DataService } from '../data/data.service';
import { Metrics, Prediction } from '../data/models';
import { MethodSection } from './method';

const load = <T>(file: string): T =>
  JSON.parse(readFileSync(resolve(process.cwd(), 'src/assets/data', file), 'utf8')) as T;

describe('MethodSection (Metodología)', () => {
  const pred = load<Prediction>('prediction.json');
  const metrics = load<Metrics>('metrics.json');
  let text = '';

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [MethodSection],
      providers: [{ provide: DataService, useValue: { prediction: signal(pred), metrics: signal(metrics) } }],
    }).compileComponents();
    const f = TestBed.createComponent(MethodSection);
    f.detectChanges();
    text = (f.nativeElement as HTMLElement).textContent!.replace(/\s+/g, ' ').replace(/ | /g, ' ');
  });

  it('muestra los parámetros reales del Elo y de la simulación', () => {
    expect(text).toContain('todos empiezan en 1500');
    expect(text).toContain('16 puntos como base, ×4 en MSI y Mundial');
    expect(text).toContain('lado azul suma 30 puntos');
    expect(text).toContain('se acerca un 25 % a la media');
    expect(text).toMatch(/Simulamos la final 100.?000 veces/);
    expect(text).toContain('Reajustamos el modelo 200 veces');
  });

  it('la regla de lados sale de la elección del perdedor', () => {
    expect(text).toContain('elige rojo el 76 % de las veces');
    expect(text).toContain('primer pick el 63 %');
    expect(text).toContain('rojo + primer pick (49 %)');
  });

  it('describe bien qué usa cada modelo', () => {
    expect(text).toContain('Regresión logística: el mismo Elo más el lado y el primer pick');
    expect(text).not.toMatch(/Regresión logística: el Elo más estadísticas/);
  });

  it('cifras de la conclusión y del margen de error coherentes con prediction.json', () => {
    expect(text).toContain('tiene un 66 % de ganar la serie');
    expect(text).toContain('1 de cada 3 veces');
    expect(text).toContain('entre 64,7 % y 66,4 % en el 90 % de los casos');
    expect(text).toContain('se ajustó con 411 Bo5 reales');
  });
});
