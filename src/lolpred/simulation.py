"""Simulación de la serie Bo5 de la final.

1. P(equipo A gana un mapa) para cada combinación de lado y primer pick, con el modelo
   guardado y las features vigentes justo antes de la final. Para obtenerlas se añade
   UN mapa hipotético al final de la historia y se recorre el mismo pipeline (Elo y
   rolling con shift(1)): sus features solo ven mapas ya jugados. Su ``result`` es un
   marcador de posición que nunca se lee para sus propias features.
2. Mapa 1: lado con ``map1_p_team_blue`` y primer pick del azul con la frecuencia de
   ``side_choice.parquet``. Mapas 2+: el perdedor elige con las frecuencias de 2026.
3. Serie: cálculo exacto (recursión) y Monte Carlo; deben coincidir.
4. Intervalo: bootstrap de la recalibración del modelo sobre el train (ver ``bootstrap``).

Supuesto: las probabilidades por mapa son fijas durante la serie (el EDA no encontró
"momentum" entre mapas).
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from lolpred.elo import compute_elo
from lolpred.etl import PROJECT_ROOT
from lolpred.features import build_features
from lolpred.modeling import FittedModel, temporal_split

logger = logging.getLogger(__name__)

SIM_GAMEID = "SIM_FINAL"


# ---------------------------------------------------------------------------
# 1. Features del mapa hipotético
# ---------------------------------------------------------------------------
def hypothetical_map(games: pd.DataFrame, blue: str, red: str, league: str, year: int) -> pd.DataFrame:
    """Dos filas de equipo para un mapa futuro entre ``blue`` y ``red`` (stats vacías).

    Se copian columnas estáticas de la última fila de cada equipo; la fecha es la del
    último mapa conocido + 1 día, solo para ordenarlo al final.
    """
    rows = []
    date = games["date"].max() + pd.Timedelta(days=1)
    stat_like = games.select_dtypes("number").columns
    for side, team in (("Blue", blue), ("Red", red)):
        last = games[games["teamname"] == team].sort_values("date").iloc[-1].copy()
        last[stat_like] = np.nan
        last["gameid"], last["date"], last["side"] = SIM_GAMEID, date, side
        last["league"], last["year"], last["game"], last["is_warmup"] = league, year, 1, False
        # Marcadores de posición: nunca se leen para las features de este mapa (shift(1)).
        last["result"] = 0 if side == "Blue" else 1
        last["firstPick"] = 1 if side == "Blue" else 0
        rows.append(last)
    return pd.DataFrame(rows)


def scenario_features(games: pd.DataFrame, cfg: dict[str, Any], teams: list[str]) -> pd.DataFrame:
    """Features del mapa hipotético para cada lado (A azul / B azul) y primer pick (0/1)."""
    a, b = teams
    league = cfg["data"]["eval_league"]
    year = int(cfg["modeling"]["eval_year"])
    out = []
    for blue, red in ((a, b), (b, a)):
        g = pd.concat([games, hypothetical_map(games, blue, red, league, year)], ignore_index=True)
        ge = compute_elo(g, cfg["elo"])
        f = build_features(ge, cfg["features"])
        row = f[f["gameid"] == SIM_GAMEID]
        if len(row) != 1:
            raise RuntimeError("No se pudo construir la fila del mapa hipotético")
        for fp in (1, 0):
            r = row.copy()
            r["blue_first_pick"] = fp
            r["team_a_blue"] = blue == a
            r["team_a_fp"] = (fp == 1) == (blue == a)
            out.append(r)
    return pd.concat(out, ignore_index=True)


def map_probabilities(model: FittedModel, scen: pd.DataFrame) -> dict[tuple[bool, bool], float]:
    """P(A gana el mapa) por (A en azul?, A con primer pick?)."""
    p_blue = model.predict_proba(scen)
    p_a = np.where(scen["team_a_blue"], p_blue, 1 - p_blue)
    return {(bool(ab), bool(af)): float(p) for ab, af, p in zip(scen["team_a_blue"], scen["team_a_fp"], p_a)}


# ---------------------------------------------------------------------------
# 2-3. Serie: reglas de lado, cálculo exacto y Monte Carlo
# ---------------------------------------------------------------------------
def side_rules(side_choice: pd.DataFrame, p_a_blue_map1: float) -> dict[str, Any]:
    """Probabilidades de (lado, primer pick) en el mapa 1 y de la elección del perdedor."""
    m1 = side_choice[(side_choice["contexto"] == "mapa1") & side_choice["primer_pick"]]
    p_blue_fp = float(m1["prob"].iloc[0])
    loser = side_choice[side_choice["contexto"] == "mapa2+"]
    # Las 4 combinaciones siempre presentes (una combinación nunca observada vale 0).
    choice = {(az, fp): 0.0 for az in (True, False) for fp in (True, False)}
    choice.update({(bool(r.azul), bool(r.primer_pick)): float(r.prob) for r in loser.itertuples()})
    total = sum(choice.values())
    choice = {k: v / total for k, v in choice.items()}
    # Mapa 1 desde la perspectiva de A: (A azul?, A con primer pick?).
    map1 = {
        (True, True): p_a_blue_map1 * p_blue_fp,
        (True, False): p_a_blue_map1 * (1 - p_blue_fp),
        (False, True): (1 - p_a_blue_map1) * (1 - p_blue_fp),
        (False, False): (1 - p_a_blue_map1) * p_blue_fp,
    }
    return {"map1": map1, "loser": choice}


def _p_map(pmap: dict[tuple[bool, bool], float], dist: dict[tuple[bool, bool], float]) -> float:
    """P(A gana el mapa) promediando sobre una distribución de (A azul?, A con FP?)."""
    return sum(prob * pmap[k] for k, prob in dist.items())


def _loser_dist_for_a(loser_choice: dict[tuple[bool, bool], float], a_lost: bool) -> dict[tuple[bool, bool], float]:
    """Distribución de (A azul?, A con FP?) cuando elige el perdedor previo."""
    if a_lost:
        return loser_choice
    # Eligió B: lo que obtiene B es lo contrario para A.
    return {(not azul, not fp): p for (azul, fp), p in loser_choice.items()}


def exact_series(pmap: dict[tuple[bool, bool], float], rules: dict[str, Any], wins: int = 3) -> dict[str, float]:
    """Distribución exacta de marcadores (desde A) por recursión sobre (victorias A, victorias B, quién perdió)."""
    p1 = _p_map(pmap, rules["map1"])
    p_after_a_lost = _p_map(pmap, _loser_dist_for_a(rules["loser"], True))
    p_after_b_lost = _p_map(pmap, _loser_dist_for_a(rules["loser"], False))

    @lru_cache(maxsize=None)
    def go(wa: int, wb: int, a_lost_last: int) -> dict[str, float]:
        if wa == wins or wb == wins:
            return {f"{wa}-{wb}": 1.0}
        p = p1 if a_lost_last == -1 else (p_after_a_lost if a_lost_last else p_after_b_lost)
        res: dict[str, float] = {}
        for key, prob in go(wa + 1, wb, 0).items():
            res[key] = res.get(key, 0.0) + p * prob
        for key, prob in go(wa, wb + 1, 1).items():
            res[key] = res.get(key, 0.0) + (1 - p) * prob
        return res

    return go(0, 0, -1)


ELO_SCALE: float = np.log(10) / 400  # Elo -> logit


def exact_series_elo(
    diff: float, bonus: float, k: float, p_blue_map1: float, p_loser_blue: float,
    eps: float = 0.0, wins: int = 3,
) -> dict[str, float]:
    """Marcadores exactos (desde A) con el Elo ACTUALIZADO dentro de la serie.

    ``diff`` = Elo(A) − Elo(B) antes de la serie. Tras cada mapa se aplica la misma
    actualización del modelo Elo (K = ``k``, expectativa con bonus azul), así el
    resultado de un mapa cambia la probabilidad de los siguientes. ``k = 0`` reproduce
    el simulador estático. ``eps`` desplaza el logit de TODOS los mapas de la serie
    (forma del día); la actualización del Elo usa su propia expectativa, sin ``eps``.

    ``p_blue_map1`` = P(A azul en el mapa 1); ``p_loser_blue`` = P(el perdedor elige azul).
    El modelo Elo no usa el primer pick, así que basta con el lado.
    """

    @lru_cache(maxsize=None)
    def go(wa: int, wb: int, last: int, d: float) -> tuple[tuple[str, float], ...]:
        if wa == wins or wb == wins:
            return ((f"{wa}-{wb}", 1.0),)
        if last == -1:
            p_a_blue = p_blue_map1
        else:  # last = 1 si A perdió el mapa anterior
            p_a_blue = p_loser_blue if last == 1 else 1 - p_loser_blue
        acc: dict[str, float] = {}
        for a_blue, ps in ((True, p_a_blue), (False, 1 - p_a_blue)):
            if ps <= 0:
                continue
            z = ELO_SCALE * (d + (bonus if a_blue else -bonus))
            expected = 1 / (1 + np.exp(-z))
            p_true = 1 / (1 + np.exp(-(z + eps)))
            # A gana: A sube k·(1−exp) y B baja lo mismo -> la diferencia sube 2k·(1−exp).
            for res, pr, nd in ((1, p_true, d + 2 * k * (1 - expected)), (0, 1 - p_true, d - 2 * k * expected)):
                sub = go(wa + res, wb + 1 - res, 0 if res else 1, round(nd, 6))
                for key, v in sub:
                    acc[key] = acc.get(key, 0.0) + ps * pr * v
        return tuple(acc.items())

    return dict(go(0, 0, -1, round(float(diff), 6)))


def series_dist_mixture(
    diff: float, bonus: float, k: float, p_blue_map1: float, p_loser_blue: float,
    sigma: float, n_nodes: int = 12, wins: int = 3,
) -> dict[str, float]:
    """Promedia ``exact_series_elo`` sobre eps ~ N(0, sigma²) (cuadratura de Gauss-Hermite)."""
    if sigma <= 0:
        return exact_series_elo(diff, bonus, k, p_blue_map1, p_loser_blue, 0.0, wins)
    x, w = np.polynomial.hermite.hermgauss(n_nodes)
    out: dict[str, float] = {}
    for xi, wi in zip(x, w):
        d = exact_series_elo(diff, bonus, k, p_blue_map1, p_loser_blue, float(np.sqrt(2) * sigma * xi), wins)
        for key, v in d.items():
            out[key] = out.get(key, 0.0) + wi / np.sqrt(np.pi) * v
    return out


def monte_carlo(
    pmap: dict[tuple[bool, bool], float], rules: dict[str, Any], n: int, rng: np.random.Generator, wins: int = 3,
    sigma: float = 0.0,
) -> dict[str, float]:
    """Simula ``n`` series: en cada mapa se sortea (lado, primer pick) y luego el ganador.

    Con ``sigma > 0`` cada serie recibe su propia forma del día eps ~ N(0, sigma²).
    """
    keys = list(pmap)
    p_of = np.array([pmap[k] for k in keys])
    eps = rng.normal(0.0, sigma, n) if sigma > 0 else np.zeros(n)
    logit_of = _logit(p_of)
    m1 = np.array([rules["map1"][k] for k in keys])
    lose_a = np.array([_loser_dist_for_a(rules["loser"], True)[k] for k in keys])
    lose_b = np.array([_loser_dist_for_a(rules["loser"], False)[k] for k in keys])

    wa, wb = np.zeros(n, dtype=int), np.zeros(n, dtype=int)
    a_lost = np.full(n, -1)
    for _ in range(2 * wins - 1):
        live = (wa < wins) & (wb < wins)
        if not live.any():
            break
        u = rng.random(n)
        idx = np.where(a_lost == -1, np.searchsorted(np.cumsum(m1), u),
                       np.where(a_lost == 1, np.searchsorted(np.cumsum(lose_a), u),
                                np.searchsorted(np.cumsum(lose_b), u)))
        idx = np.minimum(idx, len(keys) - 1)
        a_wins = rng.random(n) < 1 / (1 + np.exp(-(logit_of[idx] + eps)))
        wa = np.where(live & a_wins, wa + 1, wa)
        wb = np.where(live & ~a_wins, wb + 1, wb)
        a_lost = np.where(live, np.where(a_wins, 0, 1), a_lost)
    scores = pd.Series([f"{a}-{b}" for a, b in zip(wa, wb)]).value_counts(normalize=True)
    return scores.to_dict()


def series_win(dist: dict[str, float]) -> float:
    """P(A gana la serie) a partir de la distribución de marcadores."""
    return sum(p for k, p in dist.items() if int(k.split("-")[0]) > int(k.split("-")[1]))


# ---------------------------------------------------------------------------
# 4. Bootstrap
# ---------------------------------------------------------------------------
def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def bootstrap(
    model: FittedModel, train: pd.DataFrame, pmap: dict[tuple[bool, bool], float], rules: dict[str, Any],
    n_boot: int, rng: np.random.Generator, wins: int = 3,
) -> np.ndarray:
    """P(A gana la serie) en ``n_boot`` remuestreos.

    En cada remuestreo (con reemplazo) del train se reajusta una recalibración logística
    p' = sigmoide(a + b·logit(p_modelo)) y se aplica a las probabilidades por mapa.
    Cubre la incertidumbre de la relación "probabilidad del modelo -> frecuencia real";
    NO cubre la incertidumbre de los propios ratings Elo de los finalistas.
    """
    from sklearn.linear_model import LogisticRegression

    x = _logit(model.predict_proba(train)).reshape(-1, 1)
    y = train["target"].to_numpy()
    keys = list(pmap)
    xs = _logit(np.array([pmap[k] for k in keys])).reshape(-1, 1)
    out = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, len(y), len(y))
        lr = LogisticRegression(C=1e6, max_iter=1000).fit(x[idx], y[idx])
        pb = dict(zip(keys, lr.predict_proba(xs)[:, 1]))
        out[i] = series_win(exact_series(pb, rules, wins))
    return out


# ---------------------------------------------------------------------------
# Orquestación
# ---------------------------------------------------------------------------
def run_simulation(cfg: dict[str, Any], model_path: Path | None = None) -> dict[str, Any]:
    """Calcula la predicción completa de la final con el modelo indicado (por defecto el mejor)."""
    scfg, mcfg = cfg["simulation"], cfg["modeling"]
    proc = PROJECT_ROOT / cfg["data"]["processed_dir"]
    teams = list(scfg["teams"])
    wins = int(scfg["wins_needed"])
    rng = np.random.default_rng(int(scfg["random_state"]))

    model: FittedModel = joblib.load(model_path or PROJECT_ROOT / mcfg["models_dir"] / mcfg["model_file"])
    games = pd.read_parquet(proc / cfg["data"]["games_file"])
    scen = scenario_features(games, cfg, teams)
    pmap = map_probabilities(model, scen)
    rules = side_rules(pd.read_parquet(proc / cfg["series"]["output_file"]), float(scfg["map1_p_team_blue"]))

    exact = exact_series(pmap, rules, wins)
    mc = monte_carlo(pmap, rules, int(scfg["n_series"]), rng, wins)

    feats = pd.read_parquet(proc / cfg["features"]["output_file"])
    train, _ = temporal_split(feats, cfg)
    boot = bootstrap(model, train, pmap, rules, int(scfg["n_bootstrap"]), rng, wins)
    alpha = (1 - float(scfg["ci_level"])) / 2
    ci = (float(np.quantile(boot, alpha)), float(np.quantile(boot, 1 - alpha)))
    res = {"model": model, "pmap": pmap, "rules": rules, "exact": exact, "mc": mc,
           "p_series": series_win(exact), "p_series_mc": series_win(mc), "ci": ci, "boot": boot,
           "scenarios": scen, "adjustment": "none"}

    adjustment = scfg.get("series_adjustment", "none")
    if adjustment == "day_form":
        # Forma del día: eps ~ N(0, sigma²) compartido por todos los mapas de la serie.
        sigma = float(scfg["day_form_sigma"])
        lo, hi = (float(x) for x in scfg["day_form_sigma_ci"])
        nodes = int(scfg["gh_nodes"])
        if scfg.get("day_form_dynamic_elo", False):
            raise NotImplementedError("La variante elegida con Elo dinámico no está conectada a la predicción")
        dist = exact_series_day_form(pmap, rules, sigma, nodes, wins)
        p_lo_sigma = series_win(exact_series_day_form(pmap, rules, lo, nodes, wins))
        p_hi_sigma = series_win(exact_series_day_form(pmap, rules, hi, nodes, wins))
        mc_adj = monte_carlo(pmap, rules, int(scfg["n_series"]), rng, wins, sigma=sigma)
        res.update({
            "adjustment": "day_form", "p_series_raw": res["p_series"], "ci_raw": ci, "exact_raw": exact,
            "p_series": series_win(dist), "exact": dist, "mc": mc_adj, "p_series_mc": series_win(mc_adj),
            "ci": (min(p_lo_sigma, p_hi_sigma), max(p_lo_sigma, p_hi_sigma)),
            "day_form": {"sigma": sigma, "sigma_ci": [lo, hi]},
        })
    elif adjustment == "recalibration":
        # Recalibración a nivel de serie ajustada en el backtest (lolpred.verification).
        recal = pd.read_parquet(proc / cfg["verification"]["recal_file"])
        full = recal[recal["muestra"] == -1].iloc[0]
        bs = recal[recal["muestra"] >= 0]
        p_raw = res["p_series"]
        p_cal = float(recalibrate(p_raw, full["a"], full["b"]))
        samples = recalibrate(p_raw, bs["a"].to_numpy(), bs["b"].to_numpy())
        res.update({
            "adjustment": "recalibration", "p_series_raw": p_raw, "ci_raw": ci, "exact_raw": exact,
            "p_series": p_cal, "exact": rescale_scores(exact, p_cal),
            "ci": (float(np.quantile(samples, alpha)), float(np.quantile(samples, 1 - alpha))),
            "recal": {"a": float(full["a"]), "b": float(full["b"]), "n_series": int(full["n_series"])},
        })
    return res


def shift_pmap(pmap: dict[tuple[bool, bool], float], eps: float) -> dict[tuple[bool, bool], float]:
    """Desplaza el logit de todas las probabilidades por mapa en ``eps`` (forma del día)."""
    return {k: float(1 / (1 + np.exp(-(_logit(np.array(v)) + eps)))) for k, v in pmap.items()}


def exact_series_day_form(
    pmap: dict[tuple[bool, bool], float], rules: dict[str, Any], sigma: float, n_nodes: int = 12, wins: int = 3
) -> dict[str, float]:
    """Marcadores exactos integrando eps ~ N(0, sigma²) por Gauss-Hermite (un eps por serie)."""
    if sigma <= 0:
        return exact_series(pmap, rules, wins)
    x, w = np.polynomial.hermite.hermgauss(n_nodes)
    out: dict[str, float] = {}
    for xi, wi in zip(x, w):
        for key, v in exact_series(shift_pmap(pmap, float(np.sqrt(2) * sigma * xi)), rules, wins).items():
            out[key] = out.get(key, 0.0) + wi / np.sqrt(np.pi) * v
    return out


def recalibrate(p: float, a: float | np.ndarray, b: float | np.ndarray) -> float | np.ndarray:
    """p' = sigmoide(a + b·logit(p)), la recalibración de series del backtest."""
    return 1.0 / (1.0 + np.exp(-(a + b * _logit(np.asarray(p)))))


def rescale_scores(dist: dict[str, float], p_win: float) -> dict[str, float]:
    """Reescala la distribución de marcadores para que P(A gana) = ``p_win``.

    Mantiene la forma condicional (cómo se reparte la victoria entre 3-0/3-1/3-2 y la
    derrota entre 2-3/1-3/0-3). Nota: el backtest mostró más barridas reales que las
    predichas; esta reescala no corrige eso.
    """
    win = {k: v for k, v in dist.items() if int(k.split("-")[0]) > int(k.split("-")[1])}
    lose = {k: v for k, v in dist.items() if k not in win}
    sw, sl = sum(win.values()), sum(lose.values())
    out = {k: v * p_win / sw for k, v in win.items()}
    out.update({k: v * (1 - p_win) / sl for k, v in lose.items()})
    return out


def save_prediction(res: dict[str, Any], cfg: dict[str, Any]) -> None:
    """Guarda el parquet de la etapa y el JSON para la web."""
    scfg = cfg["simulation"]
    teams = list(scfg["teams"])
    order = ["3-0", "3-1", "3-2", "2-3", "1-3", "0-3"]
    scores = pd.DataFrame({"marcador": order,
                           "p_exacta": [res["exact"].get(k, 0.0) for k in order],
                           "p_montecarlo": [res["mc"].get(k, 0.0) for k in order]})
    maps = pd.DataFrame([{"team_a_blue": k[0], "team_a_first_pick": k[1], "p_team_a": v} for k, v in res["pmap"].items()])
    proc = PROJECT_ROOT / cfg["data"]["processed_dir"]
    scores.assign(tipo="marcador").to_parquet(proc / scfg["output_file"], index=False)
    maps.to_parquet(proc / scfg["output_file"].replace(".parquet", "_mapas.parquet"), index=False)

    web = PROJECT_ROOT / cfg["scouting"]["web_data_dir"] / "prediction.json"
    games = pd.read_parquet(proc / cfg["data"]["games_file"], columns=["date", "is_warmup"])
    static = res.get("exact_raw", res["exact"])
    obj = {
        "team_a": teams[0], "team_b": teams[1],
        "model": f"{res['model'].name} ({res['model'].calibration})",
        "adjustment": res.get("adjustment", "none"),
        "data_date": f"{games.loc[~games['is_warmup'], 'date'].max():%Y-%m-%d}",
        "generated_at": f"{pd.Timestamp.now():%Y-%m-%d %H:%M}",
        "p_series_a": round(res["p_series"], 4),
        "p_series_a_static": round(res.get("p_series_raw", res["p_series"]), 4),
        "ci": [round(res["ci"][0], 4), round(res["ci"][1], 4)], "ci_level": scfg["ci_level"],
        "sigma": round(float(res["day_form"]["sigma"]), 4) if res.get("adjustment") == "day_form" else None,
        "n_series_montecarlo": int(scfg["n_series"]),
        # Marcadores desde el equipo A: con el ajuste elegido (forma del día) y estáticos.
        "scores": [{"score": k, "p": round(res["exact"].get(k, 0.0), 4)} for k in order],
        "scores_static": [{"score": k, "p": round(static.get(k, 0.0), 4)} for k in order],
        "maps": [{"a_blue": k[0], "a_first_pick": k[1], "p_a": round(v, 4)} for k, v in res["pmap"].items()],
        "nota": ("Probabilidades por mapa fijas durante la serie salvo la forma del día. Lado del "
                 "mapa 1 al 50 %; elecciones del perdedor según frecuencias de 2026."),
    }
    if res.get("adjustment") == "day_form":
        obj["day_form"] = {
            "sigma": round(res["day_form"]["sigma"], 4),
            "sigma_ci": [round(x, 4) for x in res["day_form"]["sigma_ci"]],
            "p_series_a_raw": round(res["p_series_raw"], 4),
            "nota": ("Forma del día: cada serie recibe un desplazamiento común eps ~ N(0, sigma²) en "
                     "el logit de todos sus mapas. sigma se ajustó con el marcador de 411 Bo5 reales "
                     "previos al Mundial 2026 y corrige la sobreconfianza y la falta de barridas del "
                     "simulador estático. El intervalo corresponde al IC perfilado de sigma."),
        }
    if res.get("adjustment") == "recalibration":
        obj["recalibration"] = {
            **{k: round(v, 4) if isinstance(v, float) else v for k, v in res["recal"].items()},
            "p_series_a_raw": round(res["p_series_raw"], 4),
            "nota": ("El backtest en Bo5 reales mostró que el simulador sobreestima al favorito; "
                     "p_series_a está recalibrada a nivel de serie y el intervalo es el bootstrap "
                     "de esa recalibración. Los marcadores se reescalan con la misma forma."),
        }
    web.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Guardado %s", web)
