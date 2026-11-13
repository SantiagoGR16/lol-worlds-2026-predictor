"""Ajuste del Elo en dos etapas, sin tocar el Mundial de evaluación.

1. ``blue_bonus``: log-loss en mapas de ligas regulares (no internacionales) de los
   años modelados, anteriores al Mundial de evaluación. Son miles de mapas, mucho
   más estables que los 96 del Mundial 2025 para estimar la ventaja de lado.
2. ``k``, ``k_international`` y ``season_regression``: log-loss en ``tune_league``/
   ``tune_year`` (Mundial 2025), con el bonus de la etapa 1 fijo. Con 2024 como
   calentamiento, la regresión de enero de 2025 ya actúa antes del Mundial 2025.

Los mejores valores se escriben en ``config.yaml`` (conservando sus comentarios)
y se regenera ``games_elo.parquet``.
"""

from __future__ import annotations

import itertools
import logging
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from lolpred.elo import compute_elo, log_loss_on, report, run_elo
from lolpred.etl import PROJECT_ROOT, load_config

logger = logging.getLogger(__name__)

STAGE2: tuple[str, ...] = ("k", "k_international", "season_regression")


def _log_loss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def domestic_mask(ge: pd.DataFrame, cfg: dict[str, Any]) -> pd.Series:
    """Filas azules de ligas regulares de los años modelados, antes del Mundial de evaluación."""
    eval_league, eval_year = cfg["data"]["eval_league"], int(cfg["modeling"]["eval_year"])
    start = ge.loc[(ge["league"] == eval_league) & (ge["year"] == eval_year), "date"].min()
    return (
        (ge["side"] == "Blue")
        & ~ge["is_warmup"]
        & ~ge["league"].isin(cfg["elo"]["international_leagues"])
        & (ge["date"] < start)
    )


def tune_blue_bonus(games: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    """Etapa 1: log-loss del Elo en ligas regulares para cada bonus azul."""
    rows = []
    for bonus in cfg["elo"]["tuning"]["blue_bonus_grid"]:
        ge = compute_elo(games, {**cfg["elo"], "blue_bonus": bonus})
        sub = ge[domestic_mask(ge, cfg)]
        rows.append({"blue_bonus": bonus, "mapas": len(sub),
                     "log_loss": _log_loss(sub["elo_prob"].to_numpy(), sub["result"].to_numpy()),
                     "p_media": sub["elo_prob"].mean(), "wr_azul": sub["result"].mean()})
    return pd.DataFrame(rows).sort_values("log_loss", kind="mergesort").reset_index(drop=True)


def grid_search(games: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    """Etapa 2: todas las combinaciones de la grilla, ordenadas por log-loss en el Mundial 2025."""
    tcfg = cfg["elo"]["tuning"]
    league, year = tcfg["tune_league"], int(tcfg["tune_year"])
    if league == cfg["data"]["eval_league"] and year == int(cfg["modeling"]["eval_year"]):
        raise ValueError("El torneo de ajuste no puede ser el de evaluación")

    grid = tcfg["grid"]
    rows: list[dict[str, Any]] = []
    for combo in itertools.product(*(grid[p] for p in STAGE2)):
        ecfg = {**cfg["elo"], **dict(zip(STAGE2, combo))}
        ge = compute_elo(games, ecfg)
        # Desempate: si un parámetro no mueve el log-loss se conserva el valor vigente.
        n_changed = sum(float(v) != float(cfg["elo"][p]) for p, v in zip(STAGE2, combo))
        rows.append({**dict(zip(STAGE2, combo)), "log_loss": log_loss_on(ge, league, year), "n_changed": n_changed})
    out = pd.DataFrame(rows)
    out["log_loss_r"] = out["log_loss"].round(10)  # empates numéricos exactos
    out = out.sort_values(["log_loss_r", "n_changed"], kind="mergesort")
    return out.drop(columns="log_loss_r").reset_index(drop=True)


def write_params(params: dict[str, Any], cfg_path: Path) -> None:
    """Reescribe en config.yaml solo esos valores de la sección ``elo`` (mantiene comentarios)."""
    text = cfg_path.read_text(encoding="utf-8")
    start = text.index("\nelo:")
    end = text.index("\n  tuning:", start)  # los valores viven antes de la subsección tuning
    block = text[start:end]
    for p, val in params.items():
        val_str = str(int(val)) if float(val).is_integer() else str(val)
        block, n = re.subn(rf"(\n  {p}: )[^\n#]*", rf"\g<1>{val_str}", block)
        if n != 1:
            raise ValueError(f"No se encontró '{p}' en la sección elo de config.yaml")
    cfg_path.write_text(text[:start] + block + text[end:], encoding="utf-8")


def main() -> None:
    """Punto de entrada: ``python -m lolpred.tune_elo``."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg_path = PROJECT_ROOT / "config.yaml"
    cfg = load_config(cfg_path)
    games = pd.read_parquet(PROJECT_ROOT / cfg["data"]["processed_dir"] / cfg["data"]["games_file"])

    # Etapa 1: bonus azul con ligas regulares.
    bonus_tab = tune_blue_bonus(games, cfg)
    print("\nEtapa 1 - blue_bonus (log-loss en ligas regulares antes del Mundial de evaluación):")
    print(bonus_tab.round(4).to_string(index=False))
    best_bonus = float(bonus_tab.iloc[0]["blue_bonus"])
    write_params({"blue_bonus": best_bonus}, cfg_path)
    cfg = load_config(cfg_path)

    # Etapa 2: k, k_international y season_regression con el Mundial 2025.
    results = grid_search(games, cfg)
    tcfg = cfg["elo"]["tuning"]
    print(f"\nEtapa 2 - top 10 (log-loss en {tcfg['tune_league']} {tcfg['tune_year']}, bonus={best_bonus:g}):")
    print(results.head(10).round(4).to_string())
    for p in STAGE2:
        spread = results.groupby(p)["log_loss"].min()
        print(f"  mejor log-loss por {p}: " + ", ".join(f"{k:g}={v:.4f}" for k, v in spread.items()))

    best = {p: results.iloc[0][p] for p in STAGE2}
    write_params(best, cfg_path)
    logger.info("Parámetros escritos en config.yaml: %s", {**best, "blue_bonus": best_bonus})

    cfg = load_config(cfg_path)
    ge = run_elo(cfg)
    report(ge, cfg, top_n=10)


if __name__ == "__main__":
    sys.exit(main())
