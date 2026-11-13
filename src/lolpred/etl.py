"""ETL: lee los CSV de Oracle's Elixir y produce una tabla de partidas a nivel equipo.

Salida: ``data/processed/games.parquet`` con 2 filas por ``gameid`` (Blue y Red).
Este módulo no calcula features ni separa train/test: el Mundial (``eval_league``)
se conserva en la tabla y se excluye del entrenamiento en etapas posteriores.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

logger = logging.getLogger(__name__)

# Raíz del proyecto: src/lolpred/etl.py -> sube tres niveles.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]


def load_config(path: Path | str | None = None) -> dict[str, Any]:
    """Carga ``config.yaml`` (por defecto el de la raíz del proyecto)."""
    cfg_path = Path(path) if path is not None else PROJECT_ROOT / "config.yaml"
    with open(cfg_path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def read_raw(raw_dir: Path, years: list[int], file_pattern: str) -> pd.DataFrame:
    """Lee y concatena los CSV de los años indicados.

    Si falta algún archivo se lanza un error: nunca se rellenan datos inventados.
    """
    frames: list[pd.DataFrame] = []
    for year in years:
        csv_path = raw_dir / file_pattern.format(year=year)
        if not csv_path.exists():
            raise FileNotFoundError(f"Falta el CSV de {year}: {csv_path}")
        logger.info("Leyendo %s", csv_path.name)
        # 'patch' como texto: como float, "16.20" se leería como 16.2.
        frames.append(pd.read_csv(csv_path, low_memory=False, dtype={"patch": str}))
    out = pd.concat(frames, ignore_index=True)
    # Año del ARCHIVO de origen (distinto de la temporada 'year').
    out["source_year"] = [y for y, f in zip(years, frames) for _ in range(len(f))]
    return out


# Columnas de las filas de jugador que se conservan (scouting; no entran al modelo).
PLAYER_COLS: list[str] = [
    "gameid", "date", "league", "year", "split", "playoffs", "game", "patch", "side", "position",
    "playerid", "playername", "teamid", "teamname", "champion", "result", "kills", "deaths",
    "assists", "teamkills", "dpm", "damageshare", "earnedgoldshare", "vspm", "golddiffat15",
    "csdiffat15", "gamelength",
    # Marcador de la web (lolpred.scoreboard): totales por mapa.
    "damagetochampions", "totalgold", "total cs", "csat15", "wardsplaced", "wardskilled", "visionscore",
]


def load_player_rows(cfg: dict[str, Any], root: Path = PROJECT_ROOT) -> pd.DataFrame:
    """Filas de jugador (``position != 'team'``) de las mismas ligas y temporadas del modelo.

    Solo se usan para scouting (tablero web): no entran al modelo. Los jugadores se
    identifican por ``playerid``; ``playername`` es solo para mostrar.
    """
    dcfg = cfg["data"]
    years = list(dcfg["years"])
    raw = read_raw(root / dcfg["raw_dir"], years, dcfg["file_pattern"])
    mask = (raw["position"] != "team") & raw["league"].isin(dcfg["leagues"]) & raw["year"].isin(years)
    players = raw.loc[mask, PLAYER_COLS].copy()
    players["date"] = pd.to_datetime(players["date"], errors="coerce")
    players = players.sort_values(["date", "gameid", "side", "position"], kind="mergesort").reset_index(drop=True)
    # Validación: 5 jugadores por lado en cada mapa.
    per_side = players.groupby(["gameid", "side"]).size()
    bad = per_side[per_side != 5].index.get_level_values(0).unique()
    if len(bad):
        logger.warning("Se descartan %d mapas sin 5 jugadores por lado", len(bad))
        players = players[~players["gameid"].isin(bad)].reset_index(drop=True)
    return players


def save_player_rows(cfg: dict[str, Any], root: Path = PROJECT_ROOT) -> pd.DataFrame:
    """Carga las filas de jugador y guarda ``players.parquet``."""
    players = load_player_rows(cfg, root)
    out_path = root / cfg["data"]["processed_dir"] / cfg["data"]["players_file"]
    players.to_parquet(out_path, index=False)
    logger.info("Guardado %s (%d filas, %d jugadores)", out_path, len(players), players["playerid"].nunique())
    return players


def select_rows(raw: pd.DataFrame, dcfg: dict[str, Any]) -> pd.DataFrame:
    """Separa filas del modelo y de calentamiento y marca ``is_warmup``.

    - Modelo: archivos de ``years``, temporada en ``years`` y liga en ``leagues``.
    - Calentamiento: archivos de ``warmup_years`` y liga en ``warmup_leagues``
      (cualquier temporada). Solo alimentan el Elo y los rolling.
    """
    years = list(dcfg["years"])
    model = filter_team_rows(raw[raw["source_year"].isin(years)], list(dcfg["leagues"]), years)
    model["is_warmup"] = False
    parts = [model]
    warm_years = list(dcfg.get("warmup_years") or [])
    if warm_years:
        warm = filter_team_rows(raw[raw["source_year"].isin(warm_years)], list(dcfg["warmup_leagues"]))
        warm["is_warmup"] = True
        # Un gameid de calentamiento que también esté en un archivo del modelo se queda en el modelo.
        warm = warm[~warm["gameid"].isin(model["gameid"])]
        parts.append(warm)
    return pd.concat(parts, ignore_index=True)


def filter_team_rows(
    df: pd.DataFrame, leagues: list[str], years: list[int] | None = None
) -> pd.DataFrame:
    """Conserva solo las filas de equipo (``position == 'team'``) de las ligas y años pedidos.

    El filtro por la columna ``year`` es necesario porque el CSV de 2026 trae filas
    etiquetadas como temporada 2027 (equipos amateur bajo "LCS" en oct-2026).
    """
    mask = (df["position"] == "team") & (df["league"].isin(leagues))
    if years is not None:
        mask &= df["year"].isin(years)
    return df.loc[mask].copy()


def parse_and_sort(df: pd.DataFrame) -> pd.DataFrame:
    """Convierte ``date`` a datetime y ordena por fecha, partida y lado.

    El orden temporal es la base para los cortes sin leakage de las etapas siguientes.
    """
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    n_bad = int(out["date"].isna().sum())
    if n_bad:
        logger.warning("Se descartan %d filas con fecha no parseable", n_bad)
        out = out.loc[out["date"].notna()]
    # 'Blue' < 'Red' alfabéticamente, así Blue queda siempre primero.
    return out.sort_values(["date", "gameid", "side"], kind="mergesort").reset_index(drop=True)


def validate_games(df: pd.DataFrame) -> pd.DataFrame:
    """Exige exactamente 2 filas por ``gameid``: una Blue y una Red.

    Las partidas que no cumplen se descartan con un aviso (no se reparan).
    """
    grp = df.groupby("gameid")["side"]
    n_rows = grp.transform("size")
    n_blue = grp.transform(lambda s: (s == "Blue").sum())
    n_red = grp.transform(lambda s: (s == "Red").sum())
    ok = (n_rows == 2) & (n_blue == 1) & (n_red == 1)

    bad_ids = df.loc[~ok, "gameid"].unique()
    if len(bad_ids):
        logger.warning(
            "Se descartan %d partidas sin exactamente una fila Blue y una Red (ej.: %s)",
            len(bad_ids),
            list(bad_ids[:5]),
        )
    return df.loc[ok].reset_index(drop=True)


def run_etl(cfg: dict[str, Any], root: Path = PROJECT_ROOT) -> pd.DataFrame:
    """Ejecuta el ETL completo y guarda el parquet. Devuelve la tabla resultante."""
    dcfg = cfg["data"]
    files = sorted(set(dcfg["years"]) | set(dcfg.get("warmup_years") or []))
    raw = read_raw(root / dcfg["raw_dir"], files, dcfg["file_pattern"])
    games = select_rows(raw, dcfg)
    games = parse_and_sort(games)
    games = validate_games(games)

    out_dir = root / dcfg["processed_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / dcfg["games_file"]
    games.to_parquet(out_path, index=False)
    logger.info("Guardado %s (%d filas, %d partidas)", out_path, len(games), games["gameid"].nunique())
    return games


def summarize(games: pd.DataFrame, eval_league: str) -> str:
    """Resumen legible: filas por liga y año, y rango de fechas del Mundial más reciente."""
    lines: list[str] = []
    warm = games[games["is_warmup"]]
    games = games[~games["is_warmup"]]
    if len(warm):
        lines.append(f"Calentamiento (solo Elo/rolling): {warm['gameid'].nunique()} mapas, "
                     f"{warm['date'].min():%Y-%m-%d} -> {warm['date'].max():%Y-%m-%d}")
        lines.append(warm.groupby("league")["gameid"].nunique().to_string())
        lines.append("")
    counts = games.pivot_table(index="league", columns="year", values="gameid", aggfunc="size", fill_value=0)
    lines.append("Filas de equipo del modelo por liga y temporada:")
    lines.append(counts.to_string())

    wlds = games.loc[games["league"] == eval_league]
    for year, sub in wlds.groupby("year"):
        lines.append(
            f"\n{eval_league} {year}: {sub['date'].min()} -> {sub['date'].max()} "
            f"({sub['gameid'].nunique()} partidas)"
        )
    if wlds.empty:
        lines.append(f"\nNo hay filas de {eval_league} en los años cargados.")
    return "\n".join(lines)


def main() -> None:
    """Punto de entrada: ``python -m lolpred.etl``."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = load_config()
    games = run_etl(cfg)
    save_player_rows(cfg)
    print(summarize(games, cfg["data"]["eval_league"]))


if __name__ == "__main__":
    sys.exit(main())
