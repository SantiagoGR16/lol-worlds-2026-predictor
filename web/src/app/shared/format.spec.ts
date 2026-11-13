import { complement, num, pct, signed } from './format';
import { oneIn } from './model-facts';

// Intl usa espacio duro antes de % y signos tipográficos; normalizamos para comparar.
const norm = (s: string) => s.replace(/ | /g, ' ');

describe('format', () => {
  it('pct: coma decimal y redondeo a 1 decimal', () => {
    expect(norm(pct(0.6555))).toBe('65,6 %');
    expect(norm(pct(0.6555, 0))).toBe('66 %');
    expect(pct(null)).toBe('—');
    expect(pct(Number.NaN)).toBe('—');
  });

  it('complement: A y B mostrados suman 100,0 %', () => {
    for (const a of [0.6555, 0.7135, 0.5, 0.1234, 0.9995]) {
      const shownA = Number(norm(pct(a)).replace(' %', '').replace(',', '.'));
      const shownB = Number(norm(pct(complement(a))).replace(' %', '').replace(',', '.'));
      expect(shownA + shownB).toBeCloseTo(100, 5);
    }
  });

  it('num y signed', () => {
    expect(num(0.6524)).toBe('0,652');
    expect(num(100000, 0).replace(/ | /g, '.')).toMatch(/^100[.]?000$/);
    expect(signed(0.03)).toBe('+0,030');
    expect(signed(-0.0144)).toBe('−0,014');
  });

  it('oneIn: "1 de cada N"', () => {
    expect(oneIn(1 - 0.6555)).toBe(3);
    expect(oneIn(0.159)).toBe(6);
    expect(oneIn(2)).toBe(1);
  });
});
