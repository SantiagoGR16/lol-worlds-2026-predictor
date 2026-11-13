# Proyecto ML LOL: cómo correrlo en otro PC

Predicción de la final del Mundial 2026 de League of Legends (Gen.G vs Bilibili Gaming)
con datos de Oracle's Elixir, más un tablero web interactivo en Angular.

## Requisitos

- **Python 3.11 o superior** (en Windows, instálalo desde python.org y marca "Add to PATH").
- **Node.js 22 LTS o superior** (incluye npm), para el tablero.

## Atajo en Windows

`instalar.bat` hace todo (Python/Node con winget si faltan, venv en `%USERPROFILE%\.lolpred\.venv`
fuera de OneDrive, tests, predicción y build). Después: `ver_tablero.bat` y `correr_modelo.bat`.

## 1. Ver el tablero (no hace falta correr Python)

Los JSON con los resultados ya vienen en `web/src/assets/data/`.

```bash
cd web
npm install        # la primera vez: descarga dependencias (unos minutos)
npm start          # equivale a: ng serve
```

Abre http://localhost:4200 en el navegador.
Controles: ← → recorre los puntos del mapa, M muestra el mapa completo, F activa la pantalla completa.

## 2. Volver a correr el modelo (opcional)

Desde la raíz del proyecto:

```bash
python -m venv .venv
# Windows:   .venv\Scripts\activate
# Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt

python scripts/run_pipeline.py --rapido   # usa los parámetros guardados en config.yaml (~minutos)
python scripts/run_pipeline.py            # completo: re-ajusta el Elo y la forma del día (más lento)
python scripts/predict_series.py          # imprime la predicción de la final
pytest -q                                 # tests (incluye test_no_leakage)
```

El pipeline regenera `data/processed/`, `models/`, `reports/` y los JSON de `web/src/assets/data/`.

## Contenido

| Carpeta | Qué contiene |
|---|---|
| `src/lolpred/` | ETL, Elo, features, modelado, simulación del Bo5, verificación, scouting, SHAP |
| `scripts/` | `run_pipeline.py`, `predict_series.py`, `export_web.py` |
| `tests/` | Tests con datos sintéticos, incluido el anti-leakage |
| `data/raw/` | CSV de Oracle's Elixir 2024 (historial previo del Elo), 2025 y 2026 (no vienen en el repo: ver "Datos") |
| `data/processed/`, `models/` | Salidas del pipeline (no vienen en el repo: se generan con `run_pipeline.py`) |
| `reports/` | EDA, métricas, verificación de la forma del día y capturas de la web |
| `web/` | Tablero en Angular (sin `node_modules`: se instala con `npm install`) |
| `config.yaml` | Parámetros del proyecto |

No se incluyen `node_modules`, `.angular`, `dist`, `__pycache__` ni los CSV de 2014–2023
(el modelo no los usa). Si necesitas otro año, descárgalo desde oracleselixir.com/tools/downloads
y ponlo en `data/raw/`.

## Datos

Datos: Oracle's Elixir · Proyecto no afiliado a Riot Games ni a los equipos.
