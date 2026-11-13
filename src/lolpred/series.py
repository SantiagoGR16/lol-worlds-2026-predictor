"""Series (Bo1/Bo3/Bo5): reconstrucción y regla empírica de lado y primer pick.

Oracle's Elixir no trae un id de serie, así que se reconstruye. La regla de lado se
ESTIMA de los datos: desde 2026 el primer pick está separado del lado y el perdedor
del mapa anterior ya no juega "normalmente en azul" (ver reports/eda/hallazgos.md).

Salida: ``data/processed/side_choice.parquet`` con las frecuencias que usará la
simulación del Bo5. Se calcula con la última temporada modelada, sin el Mundial de
evaluación ni filas de calentamiento.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import numpy as np
import pandas as pd

from lolpred.etl import PROJECT_ROOT, load_config

logger = logging.getLogger(__name__)


def build_series(feats: pd.DataFrame, max_gap_hours: float = 8.0) -> pd.DataFrame:
    """Reconstruye series agrupando mapas consecutivos del mismo par de equipos.

    Se abre una serie nueva cuando ``game == 1``, es el primer mapa del par o pasan
    más de ``max_gap_hours`` desde el mapa anterior del par. El contador se acumula
    DENTRO de cada par: con un contador global, series simultáneas de otras ligas
    quedaban mezcladas en la misma serie.
    """
    f = feats.sort_values(["date", "gameid"]).copy()
    f["par"] = ["|".join(sorted(x)) for x in zip(f["teamid_blue"], f["teamid_red"])]
    gap_h = f.groupby("par")["date"].diff().dt.total_seconds() / 3600
    new = (f["game"] == 1) | gap_h.isna() | (gap_h > max_gap_hours)
    f["serie"] = f["par"] + "#" + new.astype(int).groupby(f["par"]).cumsum().astype(str)
    # Formato por victorias del ganador (1 = Bo1, 2 = Bo3, 3 = Bo5). Un 1-1 es "Bo2/incompleta".
    f["ganador"] = np.where(f["target"] == 1, f["teamid_blue"], f["teamid_red"])
    wins = f.groupby(["serie", "ganador"]).size().groupby("serie").max()
    n_maps = f.groupby("serie").size()
    fmt = wins.map({1: "Bo1", 2: "Bo3", 3: "Bo5"}).fillna("otro")
    fmt[(wins == 1) & (n_maps == 2)] = "Bo2/incompleta"
    f["formato"] = f["serie"].map(fmt)
    f["ganador_prev"] = f.groupby("serie")["ganador"].shift(1)
    return f


def side_choice(series: pd.DataFrame, cfg: dict[str, Any], season: int | None = None) -> pd.DataFrame:
    """Frecuencias de lado y primer pick en Bo3/Bo5 de una temporada (sin el Mundial de evaluación).

    Por defecto, la temporada de evaluación. El backtest usa también la de 2025, cuando
    la regla era distinta (el perdedor elegía azul con primer pick).

    Contextos:
      - ``mapa1``: mapa 1 de la serie; probabilidad de que el AZUL tenga el primer pick.
      - ``mapa2+``: mapas siguientes; combinación (perdedor previo en azul?, con primer pick?).
    """
    eval_league = cfg["data"]["eval_league"]
    season = int(cfg["modeling"]["eval_year"]) if season is None else int(season)
    s = series[(series["year"] == season) & (series["league"] != eval_league)
               & series["formato"].isin(["Bo3", "Bo5"])]
    if "is_warmup" in s.columns:
        s = s[~s["is_warmup"]]

    rows: list[dict[str, Any]] = []
    m1 = s[s["game"] == 1]
    p_fp = float(m1["blue_first_pick"].mean())
    rows += [
        {"contexto": "mapa1", "azul": True, "primer_pick": True, "prob": p_fp, "n": len(m1)},
        {"contexto": "mapa1", "azul": True, "primer_pick": False, "prob": 1 - p_fp, "n": len(m1)},
    ]
    m = s[(s["game"] >= 2) & s["ganador_prev"].notna()].copy()
    m["azul"] = m["teamid_blue"] != m["ganador_prev"]  # el perdedor previo juega en azul
    m["primer_pick"] = np.where(m["azul"], m["blue_first_pick"] == 1, m["blue_first_pick"] == 0)
    combos = m.groupby(["azul", "primer_pick"]).size()
    for (azul, fp), n in combos.items():
        rows.append({"contexto": "mapa2+", "azul": bool(azul), "primer_pick": bool(fp),
                     "prob": n / len(m), "n": len(m)})
    out = pd.DataFrame(rows)
    out["temporada"] = season
    return out


def run_series(cfg: dict[str, Any]) -> pd.DataFrame:
    """Lee features.parquet, estima la regla de lado y guarda side_choice.parquet."""
    proc = PROJECT_ROOT / cfg["data"]["processed_dir"]
    feats = pd.read_parquet(proc / cfg["features"]["output_file"])
    series = build_series(feats, float(cfg["series"]["max_gap_hours"]))
    out = side_choice(series, cfg)
    out_path = proc / cfg["series"]["output_file"]
    out.to_parquet(out_path, index=False)
    logger.info("Guardado %s", out_path)
    return out


def main() -> None:
    """Punto de entrada: ``python -m lolpred.series``."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = load_config()
    out = run_series(cfg)
    print("\nRegla empírica de lado / primer pick (Bo3+Bo5, sin Mundial de evaluación):")
    print("  mapa1: 'azul' = equipo azul; mapa2+: 'azul' = perdedor del mapa anterior en azul")
    print(out.round(3).to_string(index=False))


if __name__ == "__main__":
    sys.exit(main())
