"""Marcador de la previa de la final para la web (pestaña "Partido"). NO entra al modelo.

1. Mapas: para cada mapa k del Bo5, P(se juega) y P(Gen.G gana | se juega), con la misma
   regla de lados y la misma forma del día que P(serie) (``lolpred.simulation``).
2. Jugadores y equipos: promedios REALES del Mundial de evaluación. Los conteos (K/D/A,
   daño, oro, CS, wards) se calculan por minuto y se escalan a una duración de referencia
   (la duración media de los mapas de los dos finalistas en el torneo), para que las
   partidas largas no pesen más. Las tasas (KP, GPM, visión/min) se calculan sobre totales.

Salida: ``scoreboard.json`` en ``web/src/assets/data/``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from lolpred.etl import PROJECT_ROOT, load_config
from lolpred.simulation import map_probabilities, scenario_features, shift_pmap, side_rules, _loser_dist_for_a, _p_map

logger = logging.getLogger(__name__)

ROLE_ORDER: dict[str, int] = {"top": 0, "jng": 1, "mid": 2, "bot": 3, "sup": 4}


# ---------------------------------------------------------------------------
# 1. Probabilidades por mapa
# ---------------------------------------------------------------------------
def map_marginals(pmap: dict[tuple[bool, bool], float], rules: dict[str, Any], wins: int = 3) -> list[dict[str, float]]:
    """P(se juega el mapa k) y P(A gana el mapa k) (incondicional) para k = 1..2·wins-1.

    Recorre hacia adelante los estados (victorias A, victorias B, ¿A perdió el anterior?)
    con las mismas probabilidades de mapa que ``exact_series``.
    """
    p1 = _p_map(pmap, rules["map1"])
    p_after = {True: _p_map(pmap, _loser_dist_for_a(rules["loser"], True)),
               False: _p_map(pmap, _loser_dist_for_a(rules["loser"], False))}
    states: dict[tuple[int, int, int], float] = {(0, 0, -1): 1.0}
    out = []
    for _ in range(2 * wins - 1):
        played = a_win = 0.0
        nxt: dict[tuple[int, int, int], float] = {}
        for (wa, wb, last), prob in states.items():
            if wa == wins or wb == wins:
                continue  # serie terminada: este mapa no se juega
            p = p1 if last == -1 else p_after[bool(last)]
            played += prob
            a_win += prob * p
            nxt[(wa + 1, wb, 0)] = nxt.get((wa + 1, wb, 0), 0.0) + prob * p
            nxt[(wa, wb + 1, 1)] = nxt.get((wa, wb + 1, 1), 0.0) + prob * (1 - p)
        out.append({"p_played": played, "p_a_win": a_win})
        states = nxt
    return out


def map_marginals_day_form(
    pmap: dict[tuple[bool, bool], float], rules: dict[str, Any], sigma: float, n_nodes: int = 12, wins: int = 3
) -> list[dict[str, float]]:
    """``map_marginals`` integrando la forma del día eps ~ N(0, sigma²) (un eps por serie)."""
    if sigma <= 0:
        base = map_marginals(pmap, rules, wins)
    else:
        x, w = np.polynomial.hermite.hermgauss(n_nodes)
        base = [{"p_played": 0.0, "p_a_win": 0.0} for _ in range(2 * wins - 1)]
        for xi, wi in zip(x, w):
            for acc, m in zip(base, map_marginals(shift_pmap(pmap, float(np.sqrt(2) * sigma * xi)), rules, wins)):
                acc["p_played"] += wi / np.sqrt(np.pi) * m["p_played"]
                acc["p_a_win"] += wi / np.sqrt(np.pi) * m["p_a_win"]
    return [{"map": k + 1, "p_played": m["p_played"],
             "p_a_win_if_played": m["p_a_win"] / m["p_played"] if m["p_played"] > 0 else None}
            for k, m in enumerate(base)]


# ---------------------------------------------------------------------------
# 2. Promedios del torneo
# ---------------------------------------------------------------------------
def player_averages(rows: pd.DataFrame, ref_minutes: float, top_champs: int = 4) -> pd.DataFrame:
    """Una fila por jugador con sus promedios en ``rows`` (filas de jugador de un equipo).

    Conteos: total / minutos jugados * ``ref_minutes``. Tasas: sobre totales.
    """
    out = []
    for pid, g in rows.groupby("playerid", sort=False):
        minutes = g["gamelength"].sum() / 60
        per_ref = lambda col: g[col].sum() / minutes * ref_minutes  # noqa: E731
        champs = (g.groupby("champion")["result"].agg(n="size", wins="sum").reset_index()
                  .sort_values(["n", "wins", "champion"], ascending=[False, False, True]).head(top_champs))
        teamkills = g["teamkills"].sum()
        out.append({
            "playerid": pid,
            "player": g.sort_values("date")["playername"].iloc[-1],
            "role": g["position"].mode().iloc[0],
            "maps": len(g),
            "wins": int(g["result"].sum()),
            "kills": per_ref("kills"),
            "deaths": per_ref("deaths"),
            "assists": per_ref("assists"),
            "kda": (g["kills"].sum() + g["assists"].sum()) / max(g["deaths"].sum(), 1),
            "kp": (g["kills"].sum() + g["assists"].sum()) / teamkills if teamkills > 0 else np.nan,
            "dmg": per_ref("damagetochampions"),
            "gold": per_ref("totalgold"),
            "gpm": g["totalgold"].sum() / minutes,
            "cs": per_ref("total cs"),
            "cs15": g["csat15"].mean(),
            "vspm": g["visionscore"].sum() / minutes,
            "wards_placed": per_ref("wardsplaced"),
            "wards_killed": per_ref("wardskilled"),
            "champions": champs.to_dict("records"),
        })
    df = pd.DataFrame(out)
    if df.empty:
        return df
    # Titulares primero (más mapas por rol), luego suplentes; orden top -> sup.
    df["_r"] = df["role"].map(ROLE_ORDER).fillna(9)
    df = df.sort_values(["_r", "maps"], ascending=[True, False])
    df["starter"] = ~df.duplicated("role")
    return df.drop(columns="_r").reset_index(drop=True)


def team_averages(team_rows: pd.DataFrame) -> dict[str, Any]:
    """Récord de mapas y promedios por mapa de un equipo (filas de equipo)."""
    per_game = {c: float(team_rows[c].mean()) for c in
                ["kills", "deaths", "towers", "dragons", "barons", "void_grubs", "totalgold"] if c in team_rows}
    return {
        "maps": int(len(team_rows)),
        "wins": int(team_rows["result"].sum()),
        "losses": int(len(team_rows) - team_rows["result"].sum()),
        "avg_length_s": float(team_rows["gamelength"].mean()),
        "first_blood": float(team_rows["firstblood"].mean()),
        "per_game": per_game,
    }


def _clean(obj: Any, digits: int = 4) -> Any:
    """Tipos JSON: NaN -> null, numpy -> python, floats redondeados."""
    if isinstance(obj, dict):
        return {str(k): _clean(v, digits) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v, digits) for v in obj]
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        return None if np.isnan(obj) else round(float(obj), digits)
    return obj


# ---------------------------------------------------------------------------
def run_scoreboard(cfg: dict[str, Any]) -> dict[str, Any]:
    """Calcula y escribe ``scoreboard.json``. Devuelve el objeto exportado."""
    scfg, simcfg, mcfg = cfg["scouting"], cfg["simulation"], cfg["modeling"]
    proc = PROJECT_ROOT / cfg["data"]["processed_dir"]
    league, year = scfg["eval_league"], int(scfg["eval_year"])
    teams: list[str] = list(simcfg["teams"])
    wins = int(simcfg["wins_needed"])

    # 1. Mapas del Bo5 (mismo modelo, reglas y forma del día que prediction.json).
    model = joblib.load(PROJECT_ROOT / mcfg["models_dir"] / mcfg["model_file"])
    games = pd.read_parquet(proc / cfg["data"]["games_file"])
    pmap = map_probabilities(model, scenario_features(games, cfg, teams))
    rules = side_rules(pd.read_parquet(proc / cfg["series"]["output_file"]), float(simcfg["map1_p_team_blue"]))
    sigma = float(simcfg["day_form_sigma"]) if simcfg.get("series_adjustment") == "day_form" else 0.0
    maps = map_marginals_day_form(pmap, rules, sigma, int(simcfg.get("gh_nodes", 12)), wins)

    # 2. Promedios reales del Mundial de evaluación.
    ev_games = games[(games["league"] == league) & (games["year"] == year) & ~games["is_warmup"]]
    players = pd.read_parquet(proc / cfg["data"]["players_file"])
    ev_players = players[(players["league"] == league) & (players["year"] == year)]
    missing = [t for t in teams if t not in set(ev_games["teamname"])]
    if missing:
        raise ValueError(f"Equipos sin mapas en {league} {year}: {missing}")
    finalist_rows = ev_games[ev_games["teamname"].isin(teams)]
    ref_minutes = float(finalist_rows["gamelength"].mean()) / 60
    top_champs = int(scfg.get("scoreboard_top_champs", 4))

    team_out = {}
    for t in teams:
        tid = finalist_rows.loc[finalist_rows["teamname"] == t].sort_values("date")["teamid"].iloc[-1]
        tr = ev_games[ev_games["teamid"] == tid]
        pl = player_averages(ev_players[ev_players["teamid"] == tid], ref_minutes, top_champs)
        team_out[t] = {"teamid": tid, **team_averages(tr), "players": pl.drop(columns="playerid").to_dict("records")}

    obj = _clean({
        "meta": {
            "league": league, "year": year, "data_date": f"{ev_games['date'].max():%Y-%m-%d}",
            "ref_length_s": ref_minutes * 60, "sigma": sigma,
            "nota": "Promedios reales del torneo. K/D/A, daño, oro, CS y wards: por minuto, escalados a la "
                    "duración media de los mapas de ambos finalistas. KP, GPM y visión/min: sobre totales. "
                    "Mapas: P(se juega) y P(gana | se juega) con la regla de lados y la forma del día de la predicción.",
        },
        "team_a": teams[0], "team_b": teams[1],
        "maps": maps,
        "teams": team_out,
    })
    out = PROJECT_ROOT / scfg["web_data_dir"] / "scoreboard.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Guardado %s", out)
    return obj


def main() -> None:
    """Punto de entrada: ``python -m lolpred.scoreboard``."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    obj = run_scoreboard(load_config())
    a = obj["team_a"]
    print(f"\nMapas del Bo5 ({a} vs {obj['team_b']}):")
    for m in obj["maps"]:
        pw = m["p_a_win_if_played"]
        print(f"  Mapa {m['map']}: se juega {m['p_played']:.3f} | P({a} gana | se juega) {pw:.3f}")
    for t, d in obj["teams"].items():
        print(f"\n{t}: {d['wins']}-{d['losses']} en mapas ({obj['meta']['league']} {obj['meta']['year']})")
        for p in d["players"]:
            champs = ", ".join(f"{c['champion']}×{c['n']}" for c in p["champions"])
            print(f"  {p['role']:<4} {p['player']:<10} {p['maps']:>2} mapas  {p['kills']:.1f}/{p['deaths']:.1f}/"
                  f"{p['assists']:.1f}  KP {p['kp']:.0%}  DMG {p['dmg']:,.0f}  oro {p['gold']:,.0f}  [{champs}]")


if __name__ == "__main__":
    main()
