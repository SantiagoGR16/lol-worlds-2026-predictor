"""Scouting de los finalistas para el tablero web. NO entra al modelo.

1. Candidatos a MVP: stats por jugador en el Mundial de evaluación, ponderadas por la
   fuerza del rival (``elo_opp_pre`` / media), y un ``mvp_score`` = promedio de z-scores
   dentro del rol contra TODOS los jugadores de ese rol en el torneo.
2. Draft esperado: P(pick) por jugador (Mundial suavizado con todo el año, solo en los
   parches del Mundial), bans hechos y recibidos, presencia y cruces pick-ban.

Salida: ``mvp.json`` y ``draft.json`` en ``web/src/assets/data/``. Solo nombres de
campeones como texto: sin arte ni íconos.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from lolpred.etl import PROJECT_ROOT, load_config

logger = logging.getLogger(__name__)

BAN_COLS: list[str] = ["ban1", "ban2", "ban3", "ban4", "ban5"]


# ---------------------------------------------------------------------------
# 1. MVP
# ---------------------------------------------------------------------------
def player_map_stats(players: pd.DataFrame, team_elo: pd.DataFrame) -> pd.DataFrame:
    """Stats por jugador y mapa, con el peso por fuerza del rival.

    ``weight`` = ``elo_opp_pre`` del equipo del jugador / media de ``elo_opp_pre`` en
    estas filas: un mapa contra un rival fuerte cuenta más que uno contra uno débil.
    """
    elo = team_elo[["gameid", "teamid", "elo_opp_pre"]]
    pm = players.merge(elo, on=["gameid", "teamid"], how="left", validate="many_to_one")
    if pm["elo_opp_pre"].isna().any():
        raise ValueError("Hay filas de jugador sin Elo del rival: revisa games_elo.parquet")
    pm["weight"] = pm["elo_opp_pre"] / pm["elo_opp_pre"].mean()
    # KP del mapa: (K+A)/kills del equipo. Con 0 kills de equipo queda indefinido.
    pm["kp_map"] = (pm["kills"] + pm["assists"]) / pm["teamkills"].where(pm["teamkills"] > 0)
    return pm


def _wavg(x: pd.Series, w: pd.Series) -> float:
    """Media ponderada ignorando NaN (p. ej. stats @15 faltantes)."""
    m = x.notna()
    return float(np.average(x[m], weights=w[m])) if m.any() else np.nan


def aggregate_players(pm: pd.DataFrame) -> pd.DataFrame:
    """Agrega por jugador con los pesos por rival (totales ponderados para KDA y KP)."""
    rows = []
    for pid, g in pm.groupby("playerid", sort=False):
        w = g["weight"]
        k, d, a = (w * g["kills"]).sum(), (w * g["deaths"]).sum(), (w * g["assists"]).sum()
        tk = (w * g["teamkills"]).sum()
        rows.append({
            "playerid": pid,
            "player": g["playername"].iloc[-1],
            "team": g["teamname"].iloc[-1],
            "role": g["position"].iloc[-1],
            "maps": len(g),
            "kills": int(g["kills"].sum()), "deaths": int(g["deaths"].sum()), "assists": int(g["assists"].sum()),
            "kda": (k + a) / max(d, 1.0),
            "kp": (k + a) / tk if tk > 0 else np.nan,
            "dpm": _wavg(g["dpm"], w),
            "gd15": _wavg(g["golddiffat15"], w),
            "cs15": _wavg(g["csdiffat15"], w),
            "dmg_share": _wavg(g["damageshare"], w),
            "gold_share": _wavg(g["earnedgoldshare"], w),
            "vspm": _wavg(g["vspm"], w),
        })
    return pd.DataFrame(rows)


def mvp_scores(agg: pd.DataFrame, metrics: list[str], min_maps: int) -> pd.DataFrame:
    """``mvp_score`` = promedio de z-scores de ``metrics`` dentro de cada rol.

    La referencia de cada rol son TODOS sus jugadores del torneo con >= ``min_maps``
    mapas. Quien no llega al mínimo queda sin score (NaN).
    """
    out = agg.copy()
    eligible = out["maps"] >= min_maps
    zcols = []
    for m in metrics:
        ref = out[eligible].groupby("role")[m].agg(["mean", "std"])
        mu, sd = out["role"].map(ref["mean"]), out["role"].map(ref["std"])
        out[f"z_{m}"] = ((out[m] - mu) / sd).where(eligible)
        zcols.append(f"z_{m}")
    out["mvp_score"] = out[zcols].mean(axis=1, skipna=False)
    return out


# ---------------------------------------------------------------------------
# 2. Draft
# ---------------------------------------------------------------------------
def pick_probabilities(
    eval_picks: pd.DataFrame, prior_picks: pd.DataFrame, player_ids: list[str], prior_weight: float
) -> pd.DataFrame:
    """P(pick) por jugador: (1-w) * share en el Mundial + w * share en todo el año.

    Cada share suma 1 por jugador, así que la mezcla suma <= 1 (exactamente 1 si el
    jugador tiene mapas en ambos pools). ``n`` = mapas con ese campeón en el Mundial,
    ``n_year`` = en todo el año (mismos parches).
    """
    rows = []
    for pid in player_ids:
        ev = eval_picks.loc[eval_picks["playerid"] == pid, "champion"].value_counts()
        pr = prior_picks.loc[prior_picks["playerid"] == pid, "champion"].value_counts()
        s_ev = ev / ev.sum() if ev.sum() else ev.astype(float)
        s_pr = pr / pr.sum() if pr.sum() else pr.astype(float)
        for champ in ev.index.union(pr.index):
            rows.append({
                "playerid": pid,
                "champion": champ,
                "p": (1 - prior_weight) * s_ev.get(champ, 0.0) + prior_weight * s_pr.get(champ, 0.0),
                "n": int(ev.get(champ, 0)),
                "n_year": int(pr.get(champ, 0)),
            })
    out = pd.DataFrame(rows, columns=["playerid", "champion", "p", "n", "n_year"])
    return out.sort_values(["playerid", "p", "n"], ascending=[True, False, False]).reset_index(drop=True)


def patch_key(patch: str) -> tuple[int, ...]:
    """Orden numérico de parches en texto: "16.9" < "16.16" < "16.20"."""
    return tuple(int(x) for x in str(patch).split("."))


def prior_patch_set(all_patches: Any, eval_patches: list[str], extra: int) -> list[str]:
    """Parches del pool del año: los del Mundial más los ``extra`` inmediatamente anteriores."""
    ordered = sorted(set(map(str, all_patches)) | set(eval_patches), key=patch_key)
    first = ordered.index(min(eval_patches, key=patch_key))
    previous = ordered[max(0, first - extra):first] if extra > 0 else []
    return sorted(set(previous) | set(eval_patches), key=patch_key)


def _long_bans(team_rows: pd.DataFrame) -> pd.DataFrame:
    """Una fila por (mapa, equipo que banea, campeón baneado)."""
    # Solo las columnas necesarias: las filas reales de equipo traen una columna 'champion' vacía.
    ids = ["gameid", "teamid", "teamname"]
    long = team_rows[ids + BAN_COLS].melt(id_vars=ids, value_vars=BAN_COLS, value_name="champion")
    return long.dropna(subset=["champion"])[["gameid", "teamid", "teamname", "champion"]]


def bans_by(team_rows: pd.DataFrame, team: str) -> pd.DataFrame:
    """Bans que hace ``team``: % de sus mapas en que banea cada campeón."""
    own = team_rows[team_rows["teamname"] == team]
    n_maps = own["gameid"].nunique()
    c = _long_bans(own).groupby("champion")["gameid"].nunique()
    return pd.DataFrame({"champion": c.index, "rate": (c / n_maps).to_numpy(), "n": c.to_numpy()}) \
        .sort_values(["rate", "champion"], ascending=[False, True]).reset_index(drop=True)


def bans_against(team_rows: pd.DataFrame, team: str) -> pd.DataFrame:
    """Bans que recibe ``team``: los que hace su rival en los mapas de ``team``."""
    maps = team_rows.loc[team_rows["teamname"] == team, "gameid"].unique()
    rival = team_rows[team_rows["gameid"].isin(maps) & (team_rows["teamname"] != team)]
    c = _long_bans(rival).groupby("champion")["gameid"].nunique()
    return pd.DataFrame({"champion": c.index, "rate": (c / len(maps)).to_numpy(), "n": c.to_numpy()}) \
        .sort_values(["rate", "champion"], ascending=[False, True]).reset_index(drop=True)


def presence(team_rows: pd.DataFrame, player_rows: pd.DataFrame) -> pd.DataFrame:
    """Presencia en el torneo: % de mapas en que cada campeón fue elegido o baneado."""
    n_maps = team_rows["gameid"].nunique()
    picks = player_rows[["gameid", "champion"]].drop_duplicates()
    bans = _long_bans(team_rows)[["gameid", "champion"]].drop_duplicates()
    both = pd.concat([picks.assign(tipo="pick"), bans.assign(tipo="ban")])
    agg = both.groupby("champion").agg(
        maps=("gameid", "nunique"),
        picks=("tipo", lambda s: int((s == "pick").sum())),
        bans=("tipo", lambda s: int((s == "ban").sum())),
    )
    agg["presence"] = agg["maps"] / n_maps
    return agg.reset_index().sort_values(["presence", "champion"], ascending=[False, True]).reset_index(drop=True)


def crossovers(
    picks: pd.DataFrame, roster: pd.DataFrame, team_bans: dict[str, pd.DataFrame], top: int, threshold: float
) -> pd.DataFrame:
    """Campeones del top ``top`` de un jugador que el rival banea en >= ``threshold`` de sus mapas."""
    teams = list(team_bans)
    rows = []
    for _, pl in roster.iterrows():
        rival = next(t for t in teams if t != pl["team"])
        rb = team_bans[rival].set_index("champion")["rate"]
        for _, pk in picks[picks["playerid"] == pl["playerid"]].head(top).iterrows():
            rate = float(rb.get(pk["champion"], 0.0))
            if rate >= threshold:
                rows.append({"team": pl["team"], "player": pl["player"], "role": pl["role"],
                             "champion": pk["champion"], "p_pick": pk["p"], "rival": rival, "rival_ban_rate": rate})
    return pd.DataFrame(rows, columns=["team", "player", "role", "champion", "p_pick", "rival", "rival_ban_rate"])


# ---------------------------------------------------------------------------
# Orquestación
# ---------------------------------------------------------------------------
def _records(df: pd.DataFrame, cols: list[str], digits: int = 4) -> list[dict[str, Any]]:
    """DataFrame -> lista de dicts JSON-serializable (NaN -> null, floats redondeados)."""
    out = []
    for rec in df[cols].to_dict("records"):
        clean = {}
        for k, v in rec.items():
            if isinstance(v, (float, np.floating)):
                clean[k] = None if np.isnan(v) else round(float(v), digits)
            elif isinstance(v, (np.integer,)):
                clean[k] = int(v)
            else:
                clean[k] = v
        out.append(clean)
    return out


def run_scouting(cfg: dict[str, Any]) -> dict[str, Any]:
    """Calcula MVP y draft y escribe mvp.json y draft.json. Devuelve las tablas."""
    scfg = cfg["scouting"]
    proc = PROJECT_ROOT / cfg["data"]["processed_dir"]
    league, year = scfg["eval_league"], int(scfg["eval_year"])
    teams: list[str] = list(scfg["teams"])

    players = pd.read_parquet(proc / cfg["data"]["players_file"])
    games = pd.read_parquet(proc / cfg["data"]["games_file"])
    games = games[~games["is_warmup"]]
    team_elo = pd.read_parquet(proc / cfg["elo"]["output_file"])

    ev_players = players[(players["league"] == league) & (players["year"] == year)]
    ev_teams = games[(games["league"] == league) & (games["year"] == year)]
    missing = [t for t in teams if t not in set(ev_teams["teamname"])]
    if missing:
        raise ValueError(f"Equipos sin mapas en {league} {year}: {missing}")

    # 1. MVP: z-scores contra todos los jugadores del torneo, luego se filtran los finalistas.
    agg = aggregate_players(player_map_stats(ev_players, team_elo))
    scored = mvp_scores(agg, list(scfg["mvp_metrics"]), int(scfg["min_maps_z"]))
    fin = scored[scored["team"].isin(teams)].copy()
    fin["mvp_candidate"] = fin["mvp_score"] == fin.groupby("team")["mvp_score"].transform("max")
    role_order = {r: i for i, r in enumerate(["top", "jng", "mid", "bot", "sup"])}
    fin = fin.sort_values(["team", "role"], key=lambda s: s.map(role_order) if s.name == "role" else s)

    # 2. Draft: el share del Mundial usa sus parches; el pool del año suma N parches previos.
    patches = sorted(ev_players["patch"].dropna().unique(), key=patch_key)
    year_players = players[players["year"] == year]
    prior_patches = prior_patch_set(year_players["patch"].dropna().unique(), patches,
                                    int(scfg.get("prior_extra_patches", 0)))
    prior = year_players[year_players["patch"].isin(prior_patches)]
    picks = pick_probabilities(ev_players, prior, fin["playerid"].tolist(), float(scfg["prior_weight"]))
    by = {t: bans_by(ev_teams, t) for t in teams}
    against = {t: bans_against(ev_teams, t) for t in teams}
    pres = presence(ev_teams, ev_players)
    cross = crossovers(picks, fin, by, int(scfg["crossover_top"]), float(scfg["crossover_ban_rate"]))

    # 3. Exportar JSON para la web.
    top_n = int(scfg["top_n_champs"])
    out_dir = PROJECT_ROOT / scfg["web_data_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    mvp_cols = ["team", "player", "role", "maps", "kda", "kp", "dpm", "gd15", "dmg_share", "mvp_score", "mvp_candidate"]
    meta = {"league": league, "year": year, "patches": patches, "maps": int(ev_teams["gameid"].nunique()),
            "nota": "Stats ponderadas por el Elo previo del rival; mvp_score = media de z-scores dentro del rol."}
    _write_json(out_dir / "mvp.json", {"meta": meta, "players": _records(fin, mvp_cols)})

    name_of = fin.set_index("playerid")["player"]
    draft = {
        "meta": {**meta, "prior_weight": scfg["prior_weight"], "prior_patches": prior_patches,
                 "nota": "p = (1-w)·share en el Mundial + w·share en todo el año (mismos parches); n = mapas en el Mundial; n_year = mapas en el pool del año."},
        "players": {r["player"]: {"team": r["team"], "role": r["role"]} for _, r in fin.iterrows()},
        "picks": {name_of[pid]: _records(g.head(top_n), ["champion", "p", "n", "n_year"])
                  for pid, g in picks.groupby("playerid", sort=False)},
        "bans_by": {t: _records(by[t].head(top_n * 2), ["champion", "rate", "n"]) for t in teams},
        "bans_against": {t: _records(against[t].head(top_n * 2), ["champion", "rate", "n"]) for t in teams},
        "presence": _records(pres.head(20), ["champion", "presence", "picks", "bans", "maps"]),
        "crossovers": _records(cross, list(cross.columns)),
    }
    _write_json(out_dir / "draft.json", draft)
    return {"mvp": fin, "picks": picks, "bans_by": by, "bans_against": against, "presence": pres,
            "crossovers": cross, "patches": patches, "prior_patches": prior_patches}


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Guardado %s", path)


def main() -> None:
    """Punto de entrada: ``python -m lolpred.scouting``."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = load_config()
    res = run_scouting(cfg)
    pd.set_option("display.width", 160)
    print(f"\nParches del Mundial: {res['patches']}  |  pool del año: {res['prior_patches']}")
    print("\nmvp_score por jugador (z dentro del rol vs todo el Mundial; ponderado por Elo del rival):")
    cols = ["team", "player", "role", "maps", "kda", "kp", "dpm", "gd15", "dmg_share", "mvp_score", "mvp_candidate"]
    print(res["mvp"][cols].round(3).to_string(index=False))

    print("\nTop 3 picks por jugador (p, n = mapas en el Mundial, n_year = en 2026):")
    for t in res["mvp"].itertuples():
        g = res["picks"][res["picks"]["playerid"] == t.playerid]
        txt = " | ".join(f"{r.champion} {r.p:.2f} (n={r.n}, año={r.n_year})" for r in g.head(3).itertuples())
        print(f"  {t.team:<16} {t.player:<8} {t.role:<4} {txt}")

    for t in res["bans_by"]:
        print(f"\nBans de {t}: " + ", ".join(f"{r.champion} {r.rate:.0%}" for r in res["bans_by"][t].head(5).itertuples()))
        print(f"Bans contra {t}: " + ", ".join(f"{r.champion} {r.rate:.0%}" for r in res["bans_against"][t].head(5).itertuples()))
    print("\nPresencia (top 8): " + ", ".join(f"{r.champion} {r.presence:.0%}" for r in res["presence"].head(8).itertuples()))
    print("\nCruces (top 3 de un jugador baneado por el rival en >= umbral):")
    print(res["crossovers"].round(3).to_string(index=False) if len(res["crossovers"]) else "  (ninguno)")


if __name__ == "__main__":
    sys.exit(main())
