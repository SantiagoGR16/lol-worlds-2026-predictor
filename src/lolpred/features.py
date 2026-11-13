"""Features por mapa, una fila por ``gameid`` desde la perspectiva del lado azul.

Reglas anti-leakage:
  - Todas las stats por equipo se desplazan con ``shift(1)`` ANTES del rolling: la
    fila de un mapa solo ve mapas anteriores del mismo equipo.
  - El Elo viene de ``games_elo.parquet``, guardado antes de actualizar con el resultado.
  - Los NaN de partidas 'partial' (LPL) NO se rellenan: el rolling los ignora y se
    expone ``n_validos15_*`` con cuántos mapas válidos tuvo la ventana.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import pandas as pd

from lolpred.etl import PROJECT_ROOT, load_config

logger = logging.getLogger(__name__)

# Columnas de contexto que se conservan en la tabla final.
META_COLS: list[str] = ["gameid", "date", "league", "year", "split", "playoffs", "game", "patch"]


def add_derived_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Añade kills y deaths por minuto (``gamelength`` está en segundos)."""
    out = df.copy()
    minutes = out["gamelength"] / 60.0
    out["kills_pm"] = out["kills"] / minutes
    out["deaths_pm"] = out["deaths"] / minutes
    return out


def team_rolling(df: pd.DataFrame, fcfg: dict[str, Any]) -> pd.DataFrame:
    """Calcula los rolling por ``teamid`` sobre filas de equipo ordenadas por fecha.

    Para cada stat y ventana N: media de los N mapas ANTERIORES del equipo
    (``shift(1)`` y luego ``rolling(N, min_periods=1)``). Además:
      - ``n_mapas_r{N}``: mapas previos disponibles en la ventana (máx. N).
      - ``n_validos15_r{N}``: mapas previos con stats del minuto 15 no nulas.
      - ``dias_desde_ultimo``: días desde el mapa anterior del equipo.
    """
    out = df.sort_values(["date", "gameid", "side"], kind="mergesort").reset_index(drop=True)
    grp = out.groupby("teamid", sort=False)
    new_cols: dict[str, pd.Series] = {}

    def roll(series: pd.Series, n: int, how: str) -> pd.Series:
        # shift(1) dentro de cada equipo y después el rolling, también por equipo.
        shifted = series.groupby(out["teamid"], sort=False).shift(1)
        r = shifted.groupby(out["teamid"], sort=False).rolling(n, min_periods=1)
        res = r.mean() if how == "mean" else r.count()
        return res.reset_index(level=0, drop=True).sort_index()

    # 1.0 si el mapa tiene todas las stats @15; NaN si no (así rolling().count() las salta).
    valid15 = out[fcfg["stats_at15"]].notna().all(axis=1).astype(float).where(lambda s: s > 0)

    for n in fcfg["windows"]:
        for stat in fcfg["stats"]:
            new_cols[f"{stat}_r{n}"] = roll(out[stat].astype(float), n, "mean")
        new_cols[f"n_mapas_r{n}"] = roll(out["result"].astype(float), n, "count")
        new_cols[f"n_validos15_r{n}"] = roll(valid15, n, "count")

    prev_date = grp["date"].shift(1)
    new_cols["dias_desde_ultimo"] = (out["date"] - prev_date).dt.total_seconds() / 86400.0
    return pd.concat([out, pd.DataFrame(new_cols)], axis=1)


def to_game_level(team_df: pd.DataFrame, fcfg: dict[str, Any]) -> pd.DataFrame:
    """Une las filas Blue y Red de cada mapa: una fila por mapa con diferencias Blue − Red."""
    windows = fcfg["windows"]
    roll_cols = [f"{s}_r{n}" for n in windows for s in fcfg["stats"]]
    count_cols = [f"n_mapas_r{n}" for n in windows] + [f"n_validos15_r{n}" for n in windows]
    side_cols = ["teamid", "teamname", "elo_pre", "dias_desde_ultimo", *roll_cols, *count_cols]

    blue = team_df[team_df["side"] == "Blue"].set_index("gameid")
    red = team_df[team_df["side"] == "Red"].set_index("gameid")
    red = red.loc[blue.index]

    meta = [c for c in META_COLS if c != "gameid" and c in blue.columns]
    out = blue[meta].copy()
    # Elo: elo_diff y elo_prob de la fila Blue ya incluyen el bonus de lado azul.
    out["elo_diff"] = blue["elo_diff"]
    out["elo_prob"] = blue["elo_prob"]
    # Primer pick: se decide antes del draft, así que no es leakage. En 2025 siempre era
    # del azul; desde 2026 está separado del lado (el rojo lo tiene ~60 % de las veces).
    out["blue_first_pick"] = blue["firstPick"].astype(int)
    for c in side_cols:
        out[f"{c}_blue"] = blue[c]
        out[f"{c}_red"] = red[c]
    for c in [*roll_cols, "dias_desde_ultimo"]:
        out[f"diff_{c}"] = blue[c] - red[c]
    # Target: victoria del lado azul.
    out["target"] = blue["result"].astype(int)
    return out.reset_index().sort_values(["date", "gameid"], kind="mergesort").reset_index(drop=True)


def build_features(games_elo: pd.DataFrame, fcfg: dict[str, Any]) -> pd.DataFrame:
    """Pipeline completo de features a partir de la tabla con Elo.

    Los rolling se calculan sobre TODA la historia (incluido el calentamiento), pero
    la tabla final solo contiene mapas del modelo: el calentamiento nunca es una fila.
    """
    team = team_rolling(add_derived_stats(games_elo), fcfg)
    if "is_warmup" in team.columns:
        team = team[~team["is_warmup"]]
    return to_game_level(team, fcfg)


def run_features(cfg: dict[str, Any]) -> pd.DataFrame:
    """Lee games_elo.parquet, construye las features y guarda features.parquet."""
    proc = PROJECT_ROOT / cfg["data"]["processed_dir"]
    ge = pd.read_parquet(proc / cfg["elo"]["output_file"])
    feats = build_features(ge, cfg["features"])
    out_path = proc / cfg["features"]["output_file"]
    feats.to_parquet(out_path, index=False)
    logger.info("Guardado %s (%d mapas, %d columnas)", out_path, len(feats), feats.shape[1])
    return feats


def main() -> None:
    """Punto de entrada: ``python -m lolpred.features``."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = load_config()
    feats = run_features(cfg)
    n = max(cfg["features"]["windows"])
    diff_cols = [c for c in feats.columns if c.startswith("diff_") and c.endswith(f"_r{n}")]
    print(f"\nMapas: {len(feats)}  |  tasa de victoria azul: {feats['target'].mean():.3f}")
    print(f"\nNaN por feature (ventana {n}):")
    print(feats[diff_cols].isna().mean().round(3).to_string())
    print(f"\nCorrelación con target (ventana {n}):")
    corr = feats[["elo_diff", *diff_cols]].corrwith(feats["target"]).sort_values(ascending=False)
    print(corr.round(3).to_string())


if __name__ == "__main__":
    sys.exit(main())
