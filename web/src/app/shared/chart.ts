// Base común de los gráficos ECharts: tema oscuro, tipografía de datos y movimiento reducido.

export const COLORS = {
  gold: '#e8b64c',
  gold2: '#ffd98a',
  cyan: '#23d5ff',
  cyan2: '#7ef0ff',
  violet: '#9d7bff',
  violet2: '#c9b6ff',
  ink: '#e9edf6',
  ink2: '#b4bccd',
  ink3: '#8a93a8',
  line: 'rgba(160,175,210,0.16)',
};

export function baseChart(reduced: boolean): Record<string, unknown> {
  return {
    backgroundColor: 'transparent',
    animation: !reduced,
    textStyle: { fontFamily: 'JetBrains Mono, monospace', color: COLORS.ink2, fontSize: 11 },
    grid: { left: 8, right: 12, top: 24, bottom: 8, containLabel: true },
    tooltip: {
      backgroundColor: 'rgba(15,20,32,0.95)',
      borderColor: 'rgba(157,123,255,0.5)',
      textStyle: { color: COLORS.ink, fontFamily: 'Inter, sans-serif', fontSize: 12 },
    },
  };
}

export const axisStyle = {
  axisLine: { lineStyle: { color: COLORS.line } },
  axisTick: { show: false },
  splitLine: { lineStyle: { color: COLORS.line } },
  axisLabel: { color: COLORS.ink2 },
};
