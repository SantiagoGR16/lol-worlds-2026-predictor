"""Corre todo el pipeline de punta a punta y exporta los JSON de la web.

Uso:
    py scripts/run_pipeline.py            # completo (incluye ajuste del Elo y de la forma del día)
    py scripts/run_pipeline.py --rapido   # sin re-ajustar el Elo ni las variantes del simulador
                                          # (usa los parámetros ya guardados en config.yaml)

Orden: etl -> elo (tune_elo) -> features -> series -> modeling -> verification ->
diagnósticos -> scouting -> scoreboard -> eda -> explain -> pytest -> export_web.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))


def _step(name: str, fn) -> None:  # noqa: ANN001
    t0 = time.time()
    print(f"\n>>> {name}", flush=True)
    fn()
    print(f"<<< {name} ({time.time() - t0:.0f} s)", flush=True)


def main() -> None:
    rapido = "--rapido" in sys.argv

    from lolpred import eda, elo, etl, explain, features, modeling, scoreboard, scouting, series, tune_elo, verification

    _step("ETL (equipos + jugadores)", etl.main)
    _step("Elo" + (" (parámetros de config)" if rapido else " (ajuste en dos etapas)"),
          elo.main if rapido else tune_elo.main)
    _step("Features", features.main)
    _step("Regla de lado (series)", series.main)
    _step("Modelado", modeling.main)
    if rapido:
        _step("Diagnósticos (requiere backtest previo)", verification.diagnostics_main)
    else:
        _step("Verificación (backtest, forma del día, Bradley-Terry)", verification.main)
        _step("Diagnósticos de la forma del día", verification.diagnostics_main)
    _step("Scouting", scouting.main)
    _step("Marcador de la previa (web)", scoreboard.main)
    _step("EDA", eda.main)
    _step("Explicación SHAP", explain.main)

    # Tests antes de exportar: si algo falla, no se publican JSON nuevos.
    def _pytest() -> None:
        r = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT)
        if r.returncode != 0:
            raise SystemExit("pytest falló: no se exportan los JSON")

    _step("pytest", _pytest)

    import export_web

    _step("Export web", export_web.main)
    print("\nPipeline completo.")


if __name__ == "__main__":
    main()
