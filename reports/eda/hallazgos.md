# EDA: hallazgos y cambios propuestos

Fuente: `data/processed/*.parquet` (2025–2026; LCK, LPL, LEC, LCS, LTA N, LTA S, LCP, MSI, WLDs)
y las filas de jugadores de los CSV crudos. Script: `python -m lolpred.eda`. Gráficos en esta carpeta.
El Mundial 2026 solo se describe; no se usó para elegir nada.

## 1. La regla de lado en series cambió en 2026 (`04_regla_lado_series.png`)
Mapas 2+ de Bo3/Bo5, perdedor del mapa anterior:

| Año | Juega en azul | Tiene primer pick | n |
|---|---|---|---|
| 2025 | 90 % | 90 % | 1.541 |
| 2026 | 23 % | 64 % | 1.398 |

- En 2025 el primer pick iba siempre con el azul, y el perdedor elegía azul.
- En 2026 el primer pick está **separado del lado**: el rojo lo tiene el 61 % de las veces. El perdedor suele quedarse **rojo + primer pick**.
  Ejemplo: en la semifinal Gen.G–IG, IG perdió el mapa 1 y jugó el mapa 2 en rojo con primer pick.
- **La regla inicial del proyecto ("el perdedor elige lado, normalmente azul") ya no describe 2026.**

## 2. Lado azul y primer pick (`01_lado_azul_por_liga.png`)
- El azul gana el 53,9 % de los mapas (IC 95 %: 52,5–55,3).
- En 2026 el azul gana el 57,6 % con primer pick y el 53,9 % sin él: el lado y el primer pick suman ventajas por separado.
- El Elo está **descalibrado hacia el azul**: predice 52,1 % de media y el real es 54,4 %. El bonus de 15 se eligió con solo 96 mapas del Mundial 2025.

## 3. Sin "momentum" entre mapas
Quien gana un mapa gana el siguiente el 54,7 % de las veces, y el Elo ya esperaba el 55,1 %. El residual es −0,003 ± 0,017.
→ Tratar los mapas de un Bo5 como independientes (dado Elo, lado y primer pick) está respaldado por los datos.

## 4. Datos parciales (`02_datos_parciales.png`)
- LPL 2025: **100 %** de los mapas sin stats del minuto 15. LPL 2026: entre el 7 y el 25 % según el trimestre.
- Consecuencia: las features @15 de BLG salen solo de 2026, con unos 10 mapas válidos de cada 20.

## 5. Historial de los participantes del Mundial 2026 (`06_historial_participantes.png`)
- **LØS llega con 0 mapas y FURIA con solo 54 de liga local**: los dos juegan **CBLOL** en 2026, que no está en config.
- Cloud9, MVK, Dplus KIA y Team WE no tienen mapas internacionales previos: su Elo solo se conecta con otras regiones a través de su liga.

## 6. Regiones (`05_regiones.png`, MSI 2025-26 + Mundial 2025)
- LCK gana a LPL el 62 % de los mapas (n=45) y a LEC el 76 %. LPL gana a LEC el 68 %.
- Coincide con que el ajuste eligiera `k_international = 3` (el máximo de la grilla): los partidos internacionales son la única vía para mover el Elo entre regiones.

## 7. Plantillas (`07_estabilidad_plantillas.png`)
- Solo el 4,8 % de los mapas tienen algún titular distinto al mapa anterior.
- Gen.G: 0 cambios en 264 mapas. BLG: 4,3 %. Rotaron la jungla en 2025 y en 2026 cambiaron tirador y jungla (Viper, Xun) y top (Bin, Wenbo, Flandre).
- Una feature de continuidad de plantilla aportaría poco en general. En BLG, la regresión entre temporadas ya amortigua el cambio de 2026.

## 8. Features (`08_correlacion_features.png`, sin Mundial)
- `elo_diff` es la más informativa (r=0,31). Le siguen winrate, kills/min, dpm y golddiff@15 (0,20–0,26).
- **Casi sin señal:** `firstdragon` (0,03), `gamelength` (0,00) y `dias_desde_ultimo` (≈0).
- **Redundantes:** golddiff@15 y xpdiff@15 (0,87); winrate y kills/min (0,83). Para LightGBM no es un problema, pero complica leer SHAP.
- La ventana de 20 mapas es igual o ligeramente mejor que la de 10 en casi todas las stats.

## Cambios propuestos (por impacto)
1. **Actualizar la regla de lado** en las reglas del proyecto y en la futura simulación del Bo5: usar las frecuencias de 2026 (perdedor en rojo el 76 %, con primer pick el 63 %) en lugar de "perdedor = azul".
2. **Añadir `firstPick` como feature** (lado y primer pick). Se conoce antes del draft, así que no hay leakage. En la simulación se trata con la distribución empírica del punto 1.
3. **Añadir CBLOL** a las ligas: LØS y FURIA dejan de llegar al Mundial casi sin historia.
4. **Ajustar `blue_bonus` con las ligas regulares** (miles de mapas) en lugar de los 96 del Mundial 2025, o ampliar la grilla. Hoy el Elo subestima al azul en 2,3 puntos.
5. **Cargar 2024 solo como calentamiento del Elo** (no para entrenar). Así el Elo no empieza en 1.500 en enero de 2025, y `season_regression` (que hoy no se puede identificar) se puede ajustar.
6. **Quitar `firstdragon`, `gamelength` y `dias_desde_ultimo`**, o dejar que el modelo lo decida y confirmarlo con SHAP.

## Bug encontrado y corregido durante el EDA
La primera versión de la reconstrucción de series usaba un `cumsum` global y mezclaba series simultáneas de otras ligas, lo que daba "perdedor en azul" del 31–43 %. Se corrigió calculando el id de serie dentro de cada par de equipos.

## Cambios aplicados (2026-11-12)
| # | Cambio | Resultado |
|---|---|---|
| 1 | Regla de lado empírica (`lolpred.series` → `side_choice.parquet`); reglas del proyecto actualizadas | Mapas 2+ de 2026: el perdedor juega en rojo con primer pick el 49,5 %, en rojo sin primer pick el 27,0 %, en azul con primer pick el 13,2 % y en azul sin primer pick el 10,3 %. Mapa 1: el azul tiene el primer pick el 38 % |
| 2 | Feature `blue_first_pick` | Incluida en `features.parquet` |
| 3 | CBLOL añadido | LØS pasa de 0 a 76 mapas previos al Mundial y FURIA de 70 a 142 |
| 4 | `blue_bonus` ajustado con 4.704 mapas de ligas regulares | 30 puntos; el Elo predice 53,8 % de victorias azules frente al 54,4 % real (antes 52,1 %) |
| 5 | 2024 como calentamiento (2.707 mapas, `is_warmup`) | `season_regression` ya se puede ajustar: 0,75 gana a 0,5. Etapa 2: k=16, k_international=4. Log-loss en el Mundial 2025: 0,6557 (antes 0,6609) |
| 6 | Quitar features sin señal | Pendiente: se decidirá con SHAP en el modelado |
