"""Imprime la predicción de la final Bo5 (Gen.G vs Bilibili Gaming).

Uso: ``py scripts/predict_series.py``
Requiere haber ejecutado antes el pipeline (etl, elo, features, series, modeling).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Permite ejecutar el script sin instalar el paquete.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lolpred.etl import PROJECT_ROOT, load_config  # noqa: E402
from lolpred.simulation import run_simulation, save_prediction, series_win, exact_series  # noqa: E402


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    cfg = load_config()
    a, b = cfg["simulation"]["teams"]
    res = run_simulation(cfg)
    save_prediction(res, cfg)

    m = res["model"]
    print(f"\n=== Final {cfg['data']['eval_league']} {cfg['modeling']['eval_year']}: {a} vs {b} ===")
    print(f"Modelo: {m.name} (calibración: {m.calibration})")

    print(f"\nP({a} gana un mapa) según lado y primer pick:")
    for (blue, fp), p in sorted(res["pmap"].items(), reverse=True):
        print(f"  {a} {'azul' if blue else 'rojo':<4} | {'con' if fp else 'sin'} primer pick: {p:.3f}")

    r = res["rules"]
    print("\nReglas de lado usadas:")
    print(f"  Mapa 1: P({a} azul) = {cfg['simulation']['map1_p_team_blue']:.2f}; "
          f"P(azul con primer pick) = {r['map1'][(True, True)] / cfg['simulation']['map1_p_team_blue']:.3f}")
    print("  Mapas 2+ (elige el perdedor): " + ", ".join(
        f"{'azul' if az else 'rojo'}+{'FP' if fp else 'sin FP'} {p:.1%}" for (az, fp), p in r["loser"].items()))

    lvl = cfg["simulation"]["ci_level"]
    raw = res.get("p_series_raw", res["p_series"])
    print(f"\nSimulador estático (sin ajuste): P({a} gana la serie) = {raw:.3f}")
    print(f"Simulaciones Monte Carlo: {cfg['simulation']['n_series']:,} series")
    if res["adjustment"] == "day_form":
        df = res["day_form"]
        print(f"Forma del día: sigma={df['sigma']:.3f} (IC {lvl:.0%} perfilado [{df['sigma_ci'][0]:.3f}, {df['sigma_ci'][1]:.3f}])")
        print(f">>> P({a} gana la serie) con forma del día: {res['p_series']:.3f}  "
              f"IC {lvl:.0%}: [{res['ci'][0]:.3f}, {res['ci'][1]:.3f}]  "
              f"(Monte Carlo: {res['p_series_mc']:.3f})")
    elif res["adjustment"] == "recalibration":
        rc = res["recal"]
        print(f"Recalibración de series (backtest, {rc['n_series']} Bo5): a={rc['a']:+.3f}, b={rc['b']:.3f}")
        print(f">>> P({a} gana la serie) RECALIBRADA: {res['p_series']:.3f}  "
              f"IC {lvl:.0%}: [{res['ci'][0]:.3f}, {res['ci'][1]:.3f}]")
    else:
        print(f"Intervalo bootstrap {lvl:.0%}: [{res['ci'][0]:.3f}, {res['ci'][1]:.3f}]")

    raw_dist = res.get("exact_raw", res["exact"])
    print(f"\nMarcador ({a}-{b}):   ajustado   estático   Monte Carlo (ajustado)")
    for k in ["3-0", "3-1", "3-2", "2-3", "1-3", "0-3"]:
        print(f"  {k}              {res['exact'].get(k, 0):.3f}      {raw_dist.get(k, 0):.3f}      "
              f"{res['mc'].get(k, 0):.3f}")

    # Sensibilidad: los otros modelos guardados.
    print("\nSensibilidad por modelo (P serie estática -> con el ajuste de config):")
    models_dir = PROJECT_ROOT / cfg["modeling"]["models_dir"]
    for name in ("elo", "logreg", "lgbm"):
        path = models_dir / f"model_{name}.joblib"
        if path.exists():
            alt = run_simulation({**cfg, "simulation": {**cfg["simulation"], "n_bootstrap": 1, "n_series": 1000}}, path)
            pm = alt["pmap"]
            p_raw = series_win(exact_series(pm, alt["rules"]))
            print(f"  {name:<7} P(serie)={p_raw:.3f} -> {alt['p_series']:.3f}  "
                  f"mapa: azul+FP {pm[(True, True)]:.3f} | azul {pm[(True, False)]:.3f} | "
                  f"rojo+FP {pm[(False, True)]:.3f} | rojo {pm[(False, False)]:.3f}")


if __name__ == "__main__":
    main()
