# Verificación de la "forma del día"

Generado por `python -m lolpred.verification --diagnosticos` a partir de los datos reales de
Oracle's Elixir (Bo5 de 2025-2026 en las ligas del proyecto). Fecha: 2026-11-12 17:43.

- **Simulador estático**: probabilidad por mapa fija durante la serie (Elo previo a la serie + lado).
- **Recalibración**: P(serie) del estático pasada por sigmoide(a + b·logit(p)) ajustada en el backtest.
- **Forma del día**: cada serie recibe eps ~ N(0, σ²) común a todos sus mapas;
  σ = 0.839 (IC 90% perfilado: [0.739, 0.939]),
  ajustado con el marcador de los Bo5 previos al Mundial 2026.

Los ajustes (σ, recalibración) usan solo series **anteriores** al WLDs 2026; las
series del WLDs 2026 son **fuera de muestra**.

## 1. Momentum en Bo5: P(gana el mapa n | ganó el mapa n−1)

El error estándar es robusto a la correlación dentro de cada serie (cluster por serie).

| Grupo | Esperado según | Mapas | Series | Real | Esperado | Residual ± EE (cluster) | z |
|---|---|---|---|---|---|---|---|
| Bo5 previos al Mundial 2026 | Elo actualizado mapa a mapa | 1190 | 411 | 0.550 | 0.540 | +0.010 ± 0.014 | +0.7 |
| Bo5 previos al Mundial 2026 | Simulador estático | 1190 | 411 | 0.550 | 0.518 | +0.032 ± 0.014 | +2.2 |
| Bo5 previos al Mundial 2026 | Forma del día | 1190 | 411 | 0.550 | 0.560 | -0.009 ± 0.014 | -0.7 |
| Bo5 WLDs 2026 | Elo actualizado mapa a mapa | 40 | 15 | 0.600 | 0.610 | -0.010 ± 0.065 | -0.2 |
| Bo5 WLDs 2026 | Simulador estático | 40 | 15 | 0.600 | 0.536 | +0.064 ± 0.068 | +0.9 |
| Bo5 WLDs 2026 | Forma del día | 40 | 15 | 0.600 | 0.582 | +0.018 ± 0.065 | +0.3 |

**Lectura.** Con el Elo actualizado mapa a mapa no hay momentum (residual +0.010 ±
0.014). El simulador estático, que no actualiza, subestima la probabilidad de
que el ganador del mapa anterior repita (residual +0.032 ± 0.014,
z = +2.2). La forma del día absorbe esa correlación
(residual -0.009 ± 0.014).

## 2. Tasa de barridas (3-0 o 0-3) en Bo5

| Grupo | Series | Real ± EE | Estático | Recalibración | Forma del día |
|---|---|---|---|---|---|
| Bo5 previos al Mundial 2026 | 411 | 36.7 % ± 2.4 % | 30.3 % | 29.2 % | 38.1 % |
| Bo5 WLDs 2026 | 15 | 40.0 % ± 13.1 % | 31.6 % | 30.7 % | 39.7 % |

**Lectura.** En los 411 Bo5 previos, el estático predice
30.3 % de barridas frente a 36.7 % reales; la
recalibración no lo corrige (29.2 %) y la forma del día sí
(38.1 %).

## 3. Log-loss y Brier por serie

### WLDs 2026 (fuera de muestra)

| Variante | Series | Log-loss | Brier | NLL del marcador | Δ log-loss vs estático ± EE |
|---|---|---|---|---|---|
| estático | 15 | 0.6934 | 0.2539 | 1.7000 | — |
| recalibración | 15 | 0.6639 | 0.2378 | 1.6704 | -0.0296 ± 0.0352 |
| forma del día | 15 | 0.6743 | 0.2433 | 1.6363 | -0.0191 ± 0.0276 |

**Lectura.** Frente al estático, la recalibración mejora el log-loss del ganador
(-0.0296 ± 0.0352) y la forma del
día el del marcador completo (NLL 1.636 frente a
1.700). Con 15 series ninguna
diferencia es estadísticamente significativa: los errores estándar son mayores que las diferencias.

### Bo5 previos (referencia; muestra de ajuste, no fuera de muestra)

| Variante | Series | Log-loss | Brier | NLL del marcador | Δ log-loss vs estático ± EE |
|---|---|---|---|---|---|
| estático | 411 | 0.6524 | 0.2232 | 1.7321 | — |
| recalibración | 411 | 0.6375 | 0.2218 | 1.7173 | -0.0149 ± 0.0105 |
| forma del día | 411 | 0.6380 | 0.2214 | 1.6996 | -0.0144 ± 0.0084 |

## Conclusión

La forma del día explica el mecanismo (correlación entre mapas que el simulador estático pierde),
reproduce la tasa de barridas y rinde igual que la recalibración en el ganador de la serie. Se
mantiene como ajuste oficial (`simulation.series_adjustment: day_form` en `config.yaml`).
