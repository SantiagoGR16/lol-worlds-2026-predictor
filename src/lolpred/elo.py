"""Elo por mapa, sin leakage.

Se recorre ``games.parquet`` en orden temporal, mapa por mapa. Para cada ``gameid``
se guarda el Elo de ambos equipos ANTES de actualizarlo con el resultado de ese mapa.
Los equipos se identifican por ``teamid`` porque los nombres cambian entre años.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import numpy as np
import pandas as pd

from lolpred.etl import PROJECT_ROOT, load_config

logger = logging.getLogger(__name__)


def expected_score(elo_a: float, elo_b: float) -> float:
    """Probabilidad de que A gane a B según la fórmula logística del Elo (base 10, escala 400)."""
    return 1.0 / (1.0 + 10.0 ** ((elo_b - elo_a) / 400.0))


def _k_for(league: str, ecfg: dict[str, Any]) -> float:
    """K del mapa: el base, multiplicado si la liga es internacional (MSI/WLDs)."""
    mult = float(ecfg["k_international"]) if league in set(ecfg["international_leagues"]) else 1.0
    return float(ecfg["k"]) * mult


def compute_elo(games: pd.DataFrame, ecfg: dict[str, Any]) -> pd.DataFrame:
    """Calcula el Elo previo a cada mapa y devuelve una copia con las columnas nuevas.

    Columnas añadidas (por fila de equipo):
      - ``elo_pre``: Elo del equipo antes del mapa (sin bonus de lado).
      - ``elo_opp_pre``: Elo del rival antes del mapa.
      - ``elo_diff``: diferencia efectiva, con el bonus de lado azul incluido
        (+bonus en la fila Blue, -bonus en la Red).
      - ``elo_prob``: probabilidad de victoria del equipo según ``elo_diff``.

    Regresión a la media: la primera vez que un equipo juega en un año calendario
    nuevo, su Elo se acerca a ``initial`` con el factor ``season_regression``.
    Se usa el año de ``date`` y no la columna ``year`` (que es la temporada y trae
    filas de oct-2025 etiquetadas como 2026).
    """
    initial = float(ecfg["initial"])
    factor = float(ecfg["season_regression"])
    bonus = float(ecfg.get("blue_bonus", 0.0))

    # Orden temporal estricto; Blue antes que Red dentro de cada mapa.
    df = games.sort_values(["date", "gameid", "side"], kind="mergesort").reset_index(drop=True)

    ratings: dict[str, float] = {}  # Elo vigente por teamid
    last_year: dict[str, int] = {}  # último año calendario en que jugó cada equipo
    elo_pre = np.empty(len(df), dtype=float)

    teamids = df["teamid"].to_numpy()
    results = df["result"].to_numpy()
    leagues = df["league"].to_numpy()
    years = df["date"].dt.year.to_numpy()
    k_by_league = {lg: _k_for(lg, ecfg) for lg in pd.unique(leagues)}

    # Cada mapa son dos filas consecutivas (validado en el ETL): i = Blue, i+1 = Red.
    for i in range(0, len(df), 2):
        j = i + 1
        a, b = teamids[i], teamids[j]
        year = int(years[i])

        # 1) Regresión a la media al cambiar de año (antes de leer el Elo previo).
        for t in (a, b):
            if t not in ratings:
                ratings[t] = initial
            elif last_year[t] < year:
                ratings[t] = initial + factor * (ratings[t] - initial)
            last_year[t] = year

        # 2) Se guarda el Elo PREVIO: nunca depende del resultado de este mapa.
        ra, rb = ratings[a], ratings[b]
        elo_pre[i], elo_pre[j] = ra, rb

        # 3) Solo después se actualiza con el resultado (la expectativa incluye el bonus azul).
        exp_a = expected_score(ra + bonus, rb)
        delta = k_by_league[leagues[i]] * (float(results[i]) - exp_a)
        ratings[a] = ra + delta
        ratings[b] = rb - delta

    df["elo_pre"] = elo_pre
    # El rival de la fila i es la otra fila del mismo par.
    df["elo_opp_pre"] = elo_pre[np.arange(len(df)) ^ 1]
    side_sign = np.where(df["side"].to_numpy() == "Blue", 1.0, -1.0)
    df["elo_diff"] = df["elo_pre"] - df["elo_opp_pre"] + side_sign * bonus
    df["elo_prob"] = 1.0 / (1.0 + 10.0 ** (-df["elo_diff"] / 400.0))
    return df


def log_loss_on(games_elo: pd.DataFrame, league: str, year: int) -> float:
    """Log-loss de ``elo_prob`` (fila Blue de cada mapa) en un torneo y temporada dados."""
    sub = games_elo[(games_elo["league"] == league) & (games_elo["year"] == year) & (games_elo["side"] == "Blue")]
    if "is_warmup" in sub.columns:
        sub = sub[~sub["is_warmup"]]
    if sub.empty:
        raise ValueError(f"No hay mapas de {league} {year}")
    p = sub["elo_prob"].clip(1e-12, 1 - 1e-12).to_numpy()
    y = sub["result"].to_numpy()
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def final_ratings(games_elo: pd.DataFrame, ecfg: dict[str, Any]) -> pd.DataFrame:
    """Elo de cada equipo DESPUÉS de su último mapa (aplica la actualización de ese mapa)."""
    last = games_elo.groupby("teamid").tail(1).copy()
    k = last["league"].map(lambda lg: _k_for(lg, ecfg))
    last["elo_post"] = last["elo_pre"] + k * (last["result"] - last["elo_prob"])
    return last[["teamid", "teamname", "league", "date", "elo_post"]].sort_values("elo_post", ascending=False)


def run_elo(cfg: dict[str, Any]) -> pd.DataFrame:
    """Lee games.parquet, calcula el Elo y guarda games_elo.parquet."""
    proc = PROJECT_ROOT / cfg["data"]["processed_dir"]
    games = pd.read_parquet(proc / cfg["data"]["games_file"])
    out = compute_elo(games, cfg["elo"])
    out_path = proc / cfg["elo"]["output_file"]
    out.to_parquet(out_path, index=False)
    logger.info("Guardado %s (%d filas)", out_path, len(out))
    return out


def report(ge: pd.DataFrame, cfg: dict[str, Any], top_n: int = 15) -> None:
    """Imprime el top de Elo tras el último mapa del Mundial de evaluación y la P(Gen.G) por mapa."""
    ecfg = cfg["elo"]
    eval_league = cfg["data"]["eval_league"]
    eval_year = int(cfg["modeling"]["eval_year"])

    # Top tras el último mapa del Mundial (= justo antes de la final, que aún no está en los datos).
    cutoff = ge.loc[(ge["league"] == eval_league) & (ge["year"] == eval_year), "date"].max()
    ratings = final_ratings(ge[ge["date"] <= cutoff], ecfg)
    top = ratings.head(top_n).reset_index(drop=True)
    top.index += 1
    print(f"\nTop {top_n} Elo tras el último mapa de {eval_league} {eval_year} ({cutoff}):")
    print(top[["teamname", "league", "elo_post"]].round(1).to_string())

    # Gen.G vs Bilibili Gaming: mapas históricos entre ellos con su elo_prob previo.
    ids = {n: ge.loc[ge["teamname"] == n, "teamid"].iloc[0] for n in ("Gen.G", "Bilibili Gaming")}
    gen = ge[ge["teamid"] == ids["Gen.G"]]
    h2h = gen[gen["gameid"].isin(ge.loc[ge["teamid"] == ids["Bilibili Gaming"], "gameid"])]
    print("\nGen.G vs Bilibili Gaming, mapas en los datos (perspectiva Gen.G):")
    cols = ["date", "league", "game", "side", "elo_pre", "elo_opp_pre", "elo_prob", "result"]
    print(h2h[cols].round({"elo_pre": 1, "elo_opp_pre": 1, "elo_prob": 3}).to_string(index=False)
          if len(h2h) else "  (sin enfrentamientos)")

    # Probabilidad por mapa en la final, según el lado de Gen.G.
    r = ratings.set_index("teamid")["elo_post"]
    rg, rb = r[ids["Gen.G"]], r[ids["Bilibili Gaming"]]
    bonus = float(ecfg.get("blue_bonus", 0.0))
    print(f"\nFinal {eval_league} {eval_year}: Elo Gen.G {rg:.1f} vs BLG {rb:.1f}")
    print(f"  P(Gen.G gana un mapa) con Gen.G en azul: {expected_score(rg + bonus, rb):.3f}")
    print(f"  P(Gen.G gana un mapa) con Gen.G en rojo: {expected_score(rg, rb + bonus):.3f}")


def main() -> None:
    """Punto de entrada: ``python -m lolpred.elo``."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = load_config()
    ge = run_elo(cfg)
    report(ge, cfg)


if __name__ == "__main__":
    sys.exit(main())
