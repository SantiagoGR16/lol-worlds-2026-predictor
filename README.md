# Predictor de la final del Mundial de LoL 2026: Gen.G vs Bilibili Gaming

**Español** · [English](README.en.md)

[![Demo en vivo](https://img.shields.io/badge/demo-vercel-000?logo=vercel)](https://lol-worlds-2026-predictor.vercel.app) ![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white) ![Angular](https://img.shields.io/badge/Angular-22-DD0031?logo=angular&logoColor=white)

Pipeline de machine learning que estima la probabilidad de cada equipo en la final Bo5 del Mundial 2026, con datos reales de Oracle's Elixir, validación temporal sin leakage y simulación Monte Carlo mapa a mapa. Incluye un tablero interactivo en Angular.

![Tablero: mapa completo](reports/web/02_mapa_completo.png)

---

## Resultado

| | Gen.G | Bilibili Gaming |
|---|---|---|
| **P(ganar la serie)** | **65,6 %** (64,7 – 66,4 %) | 34,4 % |
| Marcador más probable | **3-0 Gen.G (28,7 %)** | |
| P(mapa) en lado azul | 65,9 % | |
| P(mapa) en lado rojo | 57,7 % | |

Corte de datos: 9 de noviembre de 2026. Intervalo: bootstrap con 200 repeticiones.

## Método

1. **Datos.** CSV de Oracle's Elixir, filas `position == 'team'`, ligas LCK, LPL, LEC, LCS, MSI y WLDs.
2. **Elo.** Inicia en 1500, K = 16 (×4 en MSI y Mundial), +30 por lado azul y regresión del 25 % a la media cada año. El Elo se guarda **antes** de actualizar.
3. **Modelos candidatos.** Elo solo, regresión logística y LightGBM con features rolling (`shift(1)` antes de cada ventana).
4. **Forma del día.** Un factor común a todos los mapas de una serie: si un equipo llega fino, llega fino a los cinco mapas. Se ajustó con 411 series Bo5 reales.
5. **Simulación.** Monte Carlo con 100.000 series. El perdedor del mapa anterior elige lado; en 2026 se elige rojo el 76 % de las veces y first pick el 63 %.

### Comparación de modelos (log-loss; moneda = 0,693)

| Modelo | Mundial 2025 (selección) | Mundial 2026 (evaluación) | Accuracy 2026 |
|---|---|---|---|
| **(a) Solo Elo** | **0,6557** | **0,6455** | 59 % |
| (b) Regresión logística | 0,6562 | 0,6459 | 61 % |
| (c) LightGBM | 0,7009 | 0,6591 | 61 % |

El Elo simple le ganó a LightGBM. Con pocas series internacionales, el modelo complejo se sobreajusta y sus probabilidades salen peor calibradas.

### Efecto de la forma del día

| | Sin ajuste | Con ajuste | Real |
|---|---|---|---|
| Tasa de 3-0 | 30 % | 38 % | 37 % |
| P(Gen.G gana la serie) | 71,4 % | 65,6 % | — |

## Tablero web

Angular 22 con navegación sobre un mapa. **Demo:** https://lol-worlds-2026-predictor.vercel.app

| Inicio | Jugadores |
|---|---|
| ![Inicio](reports/web/03_poi_nexos.png) | ![Jugadores](reports/web/04_poi_scouting.png) |

## Uso

**Solo el tablero (Windows):** ejecuta `ver_tablero.bat`.

**Pipeline completo (Windows):**
```bat
instalar.bat          :: crea el entorno e instala dependencias
correr_modelo.bat     :: ETL → Elo → modelos → simulación → export web
```

**Manual:**
```bash
pip install -r requirements.txt
python scripts/run_pipeline.py
python scripts/predict_series.py
python scripts/export_web.py
pytest            # incluye test_no_leakage
```
Pon los CSV de Oracle's Elixir en `data/raw/`. Los parámetros están en `config.yaml`. Para más detalles, consulta `LEEME_INSTALACION.md`.

## Estructura

| Ruta | Contenido |
|---|---|
| `src/lolpred/` | `etl`, `elo`, `features`, `modeling`, `simulation`, `explain` |
| `scripts/` | Ejecución del pipeline, predicción y exportación para la web |
| `tests/` | Pruebas, incluida la de no leakage |
| `web/` | Tablero en Angular |
| `reports/` | Figuras y capturas |
| `config.yaml` | Parámetros |

## Limitaciones

- Hay pocos enfrentamientos internacionales, así que la comparación LCK contra LPL depende de MSI y el Mundial.
- No modela cambios de parche ni de roster dentro de la temporada.
- El tablero todavía no está adaptado para celular. Por ahora se ve bien solo en computador.
- Una accuracy cercana al 60 % es lo esperable. Lo que importa es la calibración, no acertar el ganador.

---

Datos: Oracle's Elixir · Proyecto no afiliado a Riot Games
