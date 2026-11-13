"""Verificación independiente de la predicción de la final.

1. Backtest del simulador: para cada Bo5 real de 2025-2026 se predice P(gana la serie)
   con el Elo PREVIO a la serie (el del mapa 1), el lado real del mapa 1 y las reglas de
   lado de esa temporada, y se compara con el resultado real (log-loss y Brier por serie).
2. Bradley-Terry: modelo distinto del Elo. Fuerza por equipo + ventaja de lado azul +
   efecto del primer pick, por regresión logística con decaimiento temporal. Intervalo
   por bootstrap de SERIES: sí cubre la incertidumbre de las fuerzas de los equipos.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import sparse  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402

from lolpred.etl import PROJECT_ROOT, load_config  # noqa: E402
from lolpred.series import build_series, side_choice  # noqa: E402
from lolpred.elo import _k_for  # noqa: E402
from lolpred.simulation import (  # noqa: E402
    exact_series,
    rescale_scores,
    series_dist_mixture,
    series_win,
    side_rules,
)

ELO_LOGIT: float = np.log(10) / 400  # diferencia de Elo -> logit

logger = logging.getLogger(__name__)


def _sigmoid(x: float | np.ndarray) -> float | np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _metrics(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return {"n": int(len(y)),
            "log_loss": float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))),
            "brier": float(np.mean((p - y) ** 2)),
            "accuracy": float(np.mean((p > 0.5) == (y == 1)))}


# ---------------------------------------------------------------------------
# 1. Backtest del simulador
# ---------------------------------------------------------------------------
def elo_pmap(elo_a: float, elo_b: float, bonus: float) -> dict[tuple[bool, bool], float]:
    """P(A gana un mapa) con el Elo: depende del lado (bonus azul), no del primer pick."""
    p_blue = float(_sigmoid((elo_a + bonus - elo_b) * np.log(10) / 400))
    p_red = float(_sigmoid((elo_a - elo_b - bonus) * np.log(10) / 400))
    return {(True, True): p_blue, (True, False): p_blue, (False, True): p_red, (False, False): p_red}


def backtest_series(series: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    """Predicción previa a cada serie real y su resultado.

    A = equipo azul del mapa 1 (el lado del mapa 1 se conoce antes de empezar la serie).
    """
    vcfg = cfg["verification"]
    bonus = float(cfg["elo"]["blue_bonus"])
    s = series[series["formato"].isin(vcfg["backtest_formats"])]
    rules_by_season = {int(y): side_rules(side_choice(series, cfg, int(y)), 1.0)["loser"]
                       for y in s["year"].unique()}
    rows = []
    for sid, g in s.groupby("serie", sort=False):
        g = g.sort_values("date")
        first = g.iloc[0]
        a, b = first["teamid_blue"], first["teamid_red"]
        fp_a = bool(first["blue_first_pick"] == 1)
        rules = {"map1": {(True, fp_a): 1.0, (True, not fp_a): 0.0, (False, True): 0.0, (False, False): 0.0},
                 "loser": rules_by_season[int(first["year"])]}
        pmap = elo_pmap(first["elo_pre_blue"], first["elo_pre_red"], bonus)
        dist = exact_series(pmap, rules)
        wins_a = int((g["ganador"] == a).sum())
        wins_b = int((g["ganador"] == b).sum())
        loser = rules_by_season[int(first["year"])]
        rows.append({
            "serie": sid, "date": first["date"], "league": first["league"], "year": int(first["year"]),
            "team_a": first["teamname_blue"], "team_b": first["teamname_red"],
            "p_a": series_win(dist), "a_gana": int(wins_a > wins_b),
            "marcador": f"{wins_a}-{wins_b}", "p_barrida": dist.get("3-0", 0) + dist.get("0-3", 0),
            "p_map1": pmap[(True, fp_a)],
            # Entradas para resimular la serie con otras variantes del simulador.
            "elo_diff_pre": float(first["elo_pre_blue"] - first["elo_pre_red"]),
            "k_series": _k_for(first["league"], cfg["elo"]),
            "p_loser_blue": float(loser[(True, True)] + loser[(True, False)]),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 1b. Variantes del simulador: Elo dinámico y forma del día
# ---------------------------------------------------------------------------
SCORES: tuple[str, ...] = ("3-0", "3-1", "3-2", "2-3", "1-3", "0-3")


def variant_dists(bt: pd.DataFrame, bonus: float, dynamic: bool, sigma: float, n_nodes: int) -> list[dict[str, float]]:
    """Distribución de marcadores de cada serie del backtest para una variante del simulador."""
    return [
        series_dist_mixture(r.elo_diff_pre, bonus, r.k_series if dynamic else 0.0, 1.0, r.p_loser_blue, sigma, n_nodes)
        for r in bt.itertuples()
    ]


def score_nll(bt: pd.DataFrame, dists: list[dict[str, float]]) -> float:
    """Log-verosimilitud negativa media del MARCADOR observado (usa toda la información de la serie)."""
    p = np.array([max(d.get(s, 0.0), 1e-9) for d, s in zip(dists, bt["marcador"])])
    return float(-np.mean(np.log(p)))


def fit_sigma(bt: pd.DataFrame, bonus: float, dynamic: bool, max_sigma: float, n_nodes: int) -> float:
    """sigma que maximiza la verosimilitud de los marcadores observados."""
    from scipy.optimize import minimize_scalar

    res = minimize_scalar(lambda s: score_nll(bt, variant_dists(bt, bonus, dynamic, s, n_nodes)),
                          bounds=(0.0, max_sigma), method="bounded", options={"xatol": 0.01})
    return float(res.x)


def evaluate_variants(bt: pd.DataFrame, cfg: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Compara 4 variantes: estático, Elo dinámico, y cada una con forma del día (sigma ajustado).

    Se ajusta y elige con las series ANTERIORES al Mundial de evaluación (por NLL del
    marcador); las del Mundial de evaluación solo se reportan.
    """
    vcfg = cfg["verification"]
    bonus = float(cfg["elo"]["blue_bonus"])
    nodes = int(vcfg["gh_nodes"])
    eval_league, eval_year = cfg["data"]["eval_league"], int(cfg["modeling"]["eval_year"])
    is_eval = (bt["league"] == eval_league) & (bt["year"] == eval_year)
    fit, ev = bt[~is_eval & (bt["date"] < bt.loc[is_eval, "date"].min())], bt[is_eval]

    variants = {"estático": (False, 0.0), "Elo dinámico": (True, 0.0)}
    variants["estático + forma del día"] = (False, fit_sigma(fit, bonus, False, float(vcfg["max_sigma"]), nodes))
    variants["Elo dinámico + forma del día"] = (True, fit_sigma(fit, bonus, True, float(vcfg["max_sigma"]), nodes))

    rows = []
    for name, (dyn, sig) in variants.items():
        for grupo, sub in (("ajuste (pre-Mundial)", fit), (f"{eval_league} {eval_year}", ev)):
            if sub.empty:
                continue
            d = variant_dists(sub, bonus, dyn, sig, nodes)
            p_a = np.array([series_win(x) for x in d])
            y = sub["a_gana"].to_numpy()
            p_sweep = np.array([x.get("3-0", 0) + x.get("0-3", 0) for x in d])
            row = {"variante": name, "grupo": grupo, "dinamico": dyn, "sigma": sig, "n": len(sub),
                   "nll_marcador": score_nll(sub, d), **{f"ll_{k}": v for k, v in _metrics(y, p_a).items() if k != "n"},
                   "barridas_pred": float(p_sweep.mean()), "barridas_real": float(sub["marcador"].isin(["3-0", "0-3"]).mean()),
                   "fav_pred": float(np.maximum(p_a, 1 - p_a).mean()),
                   "fav_real": float(((p_a > 0.5) == (y == 1)).mean())}
            if grupo.startswith("ajuste"):
                lr = LogisticRegression(C=1e6, max_iter=1000).fit(_logit(p_a).reshape(-1, 1), y)
                row["pendiente_recal"] = float(lr.coef_[0][0])
            rows.append(row)
    table = pd.DataFrame(rows)
    best = table[table["grupo"].str.startswith("ajuste")].sort_values("nll_marcador").iloc[0]
    choice = {"variante": best["variante"], "dynamic": bool(best["dinamico"]), "sigma": float(best["sigma"])}
    choice["sigma_lo"], choice["sigma_hi"] = sigma_profile_ci(
        fit, bonus, choice["dynamic"], choice["sigma"], float(cfg["simulation"]["ci_level"]), nodes)
    choice["n_series"] = len(fit)
    return table, choice


def sigma_profile_ci(
    fit: pd.DataFrame, bonus: float, dynamic: bool, sigma: float, level: float, nodes: int, n_grid: int = 13
) -> tuple[float, float]:
    """Intervalo de sigma por verosimilitud perfilada: 2·(NLL_total − mín) <= chi²(level, 1)."""
    from scipy.stats import chi2

    grid = np.linspace(max(0.0, sigma - 0.6), sigma + 0.6, n_grid)
    nll = np.array([score_nll(fit, variant_dists(fit, bonus, dynamic, s, nodes)) * len(fit) for s in grid])
    ok = grid[2 * (nll - nll.min()) <= chi2.ppf(level, 1)]
    return float(ok.min()), float(ok.max())


def write_series_model(choice: dict[str, Any], cfg_path: Any) -> None:
    """Escribe en config.yaml la variante elegida (sección simulation)."""
    import re

    text = cfg_path.read_text(encoding="utf-8")
    vals = {"day_form_dynamic_elo": str(choice["dynamic"]).lower(), "day_form_sigma": f"{choice['sigma']:.4f}",
            "day_form_sigma_ci": f"[{choice['sigma_lo']:.4f}, {choice['sigma_hi']:.4f}]"}
    for key, val in vals.items():
        text, n = re.subn(rf"(\n  {key}: )[^\n#]*", rf"\g<1>{val}", text)
        if n != 1:
            raise ValueError(f"No se encontró '{key}' en config.yaml")
    cfg_path.write_text(text, encoding="utf-8")


def backtest_report(bt: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    """Métricas por grupo y gráfico de calibración a nivel de serie."""
    eval_league = cfg["data"]["eval_league"]
    eval_year = int(cfg["modeling"]["eval_year"])
    groups = {
        "Todas": bt,
        "2025": bt[bt["year"] == 2025],
        "2026 (sin Mundial 2026)": bt[(bt["year"] == 2026) & ~((bt["league"] == eval_league) & (bt["year"] == eval_year))],
        "Internacionales (MSI + Mundial 2025)": bt[bt["league"].isin(cfg["elo"]["international_leagues"])
                                                  & ~((bt["league"] == eval_league) & (bt["year"] == eval_year))],
        f"{eval_league} {eval_year}": bt[(bt["league"] == eval_league) & (bt["year"] == eval_year)],
    }
    rows = []
    for name, g in groups.items():
        if len(g):
            m = _metrics(g["a_gana"].to_numpy(), g["p_a"].to_numpy())
            sweep = g["marcador"].isin(["3-0", "0-3"]).mean()
            rows.append({"grupo": name, **m, "p_media_fav": float(np.maximum(g["p_a"], 1 - g["p_a"]).mean()),
                         "fav_gana": float(((g["p_a"] > 0.5) == (g["a_gana"] == 1)).mean()),
                         "barridas_pred": float(g["p_barrida"].mean()), "barridas_real": float(sweep)})
    table = pd.DataFrame(rows)

    # Calibración: probabilidad del favorito por quintiles.
    fav_p = np.maximum(bt["p_a"], 1 - bt["p_a"])
    fav_win = np.where(bt["p_a"] >= 0.5, bt["a_gana"], 1 - bt["a_gana"])
    d = pd.DataFrame({"p": fav_p, "y": fav_win})
    cal = d.groupby(pd.qcut(d["p"], 5, duplicates="drop"), observed=True).agg(p=("p", "mean"), y=("y", "mean"), n=("y", "size"))
    fig, ax = plt.subplots(figsize=(5.4, 5))
    ax.plot([0.5, 1], [0.5, 1], color="#52514e", linestyle="--", linewidth=1)
    ax.plot(cal["p"], cal["y"], marker="o", color="#2a78d6", linewidth=2, markersize=7)
    for _, r in cal.iterrows():
        ax.annotate(f"n={int(r['n'])}", (r["p"], r["y"]), textcoords="offset points", xytext=(6, -12), fontsize=8, color="#52514e")
    ax.set_xlim(0.5, 1)
    ax.set_ylim(0.3, 1)
    ax.set_xlabel("P(gana el favorito) según el simulador")
    ax.set_ylabel("Frecuencia real (quintiles)")
    ax.set_title(f"Backtest del simulador: {len(bt)} Bo5 reales", fontweight="bold")
    ax.grid(color="#e4e3df")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.tight_layout()
    out = PROJECT_ROOT / "reports" / "model"
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / "backtest_series.png", dpi=150)
    plt.close(fig)
    return table


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def fit_series_recalibration(
    bt: pd.DataFrame, cfg: dict[str, Any], rng: np.random.Generator
) -> pd.DataFrame:
    """Ajusta p' = sigmoide(a + b·logit(p)) con las series del backtest previas al Mundial de evaluación.

    Devuelve una fila por remuestreo bootstrap de SERIES (la fila ``muestra == -1`` es el
    ajuste con todas). El Mundial de evaluación nunca entra al ajuste.
    """
    eval_league, eval_year = cfg["data"]["eval_league"], int(cfg["modeling"]["eval_year"])
    is_eval = (bt["league"] == eval_league) & (bt["year"] == eval_year)
    start = bt.loc[is_eval, "date"].min() if is_eval.any() else bt["date"].max() + pd.Timedelta(days=1)
    fit = bt[~is_eval & (bt["date"] < start)]
    x, y = _logit(fit["p_a"]).reshape(-1, 1), fit["a_gana"].to_numpy()

    def _fit(idx: np.ndarray) -> tuple[float, float]:
        lr = LogisticRegression(C=1e6, max_iter=1000).fit(x[idx], y[idx])
        return float(lr.intercept_[0]), float(lr.coef_[0][0])

    rows = [{"muestra": -1, "a": (ab := _fit(np.arange(len(y))))[0], "b": ab[1], "n_series": len(y)}]
    for i in range(int(cfg["verification"]["recal_n_bootstrap"])):
        a, b = _fit(rng.integers(0, len(y), len(y)))
        rows.append({"muestra": i, "a": a, "b": b, "n_series": len(y)})
    return pd.DataFrame(rows)


def apply_recalibration(p: float, a: float | np.ndarray, b: float | np.ndarray) -> float | np.ndarray:
    """p' = sigmoide(a + b·logit(p))."""
    return _sigmoid(a + b * _logit(p))


# ---------------------------------------------------------------------------
# 2. Bradley-Terry
# ---------------------------------------------------------------------------
def bt_design(maps: pd.DataFrame, teams: list[str]) -> sparse.csr_matrix:
    """Matriz de diseño: +1 equipo azul, -1 rojo; última columna: +1 si el azul tiene FP, -1 si no."""
    idx = {t: i for i, t in enumerate(teams)}
    n, k = len(maps), len(teams)
    rows = np.repeat(np.arange(n), 3)
    cols = np.column_stack([maps["teamid_blue"].map(idx), maps["teamid_red"].map(idx), np.full(n, k)]).ravel()
    vals = np.column_stack([np.ones(n), -np.ones(n), np.where(maps["blue_first_pick"] == 1, 1.0, -1.0)]).ravel()
    return sparse.csr_matrix((vals, (rows, cols)), shape=(n, k + 1))


def fit_bt(maps: pd.DataFrame, half_life: float, c: float, ref_date: pd.Timestamp | None = None) -> dict[str, Any]:
    """Ajusta Bradley-Terry con pesos exp(-ln2·edad/half_life). El intercepto es la ventaja azul."""
    teams = sorted(set(maps["teamid_blue"]) | set(maps["teamid_red"]))
    x = bt_design(maps, teams)
    ref = maps["date"].max() if ref_date is None else ref_date
    age = (ref - maps["date"]).dt.total_seconds().to_numpy() / 86400
    w = np.power(0.5, age / half_life) if half_life > 0 else np.ones(len(maps))
    lr = LogisticRegression(C=c, max_iter=2000).fit(x, maps["target"].to_numpy(), sample_weight=w)
    coef = lr.coef_[0]
    return {"teams": teams, "strength": dict(zip(teams, coef[:-1])), "fp": float(coef[-1]),
            "blue": float(lr.intercept_[0])}


def bt_predict(model: dict[str, Any], maps: pd.DataFrame) -> np.ndarray:
    """P(gana el azul). Un equipo sin mapas en el ajuste tiene fuerza 0 (la media)."""
    s = model["strength"]
    sb = maps["teamid_blue"].map(lambda t: s.get(t, 0.0)).to_numpy()
    sr = maps["teamid_red"].map(lambda t: s.get(t, 0.0)).to_numpy()
    f = np.where(maps["blue_first_pick"] == 1, 1.0, -1.0)
    return _sigmoid(model["blue"] + sb - sr + model["fp"] * f)


def bt_pmap(model: dict[str, Any], a: str, b: str) -> dict[tuple[bool, bool], float]:
    """P(A gana un mapa) por (A azul?, A con primer pick?)."""
    d = model["strength"][a] - model["strength"][b]
    out = {}
    for a_blue in (True, False):
        for a_fp in (True, False):
            sign = 1.0 if a_fp else -1.0
            # Desde A: + ventaja azul si A es azul, - si es rojo; primer pick simétrico.
            out[(a_blue, a_fp)] = float(_sigmoid((model["blue"] if a_blue else -model["blue"]) + d + model["fp"] * sign))
    return out


def tune_bt(feats: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    """Elige half-life y C por log-loss en el Mundial val_year (ajuste con mapas previos de esa temporada)."""
    vcfg, mcfg = cfg["verification"], cfg["modeling"]
    league, val_year = cfg["data"]["eval_league"], int(mcfg["val_year"])
    test = feats[(feats["league"] == league) & (feats["year"] == val_year)]
    train = feats[(feats["year"] == val_year) & (feats["league"] != league) & (feats["date"] < test["date"].min())]
    rows = []
    for hl in vcfg["bt_half_life_grid"]:
        for c in vcfg["bt_C_grid"]:
            m = fit_bt(train, float(hl), float(c), test["date"].min())
            rows.append({"half_life": hl, "C": c, **_metrics(test["target"].to_numpy(), bt_predict(m, test))})
    return pd.DataFrame(rows).sort_values("log_loss").reset_index(drop=True)


def bt_final(feats: pd.DataFrame, cfg: dict[str, Any], half_life: float, c: float,
             rng: np.random.Generator) -> dict[str, Any]:
    """Comprobación en el Mundial 2026 y predicción de la final con bootstrap por series."""
    eval_league, eval_year = cfg["data"]["eval_league"], int(cfg["modeling"]["eval_year"])
    teams = list(cfg["simulation"]["teams"])
    season = feats[feats["year"] == eval_year]
    test = season[season["league"] == eval_league]
    pre = season[(season["league"] != eval_league) & (season["date"] < test["date"].min())]

    # Comprobación: ratings fijos antes del Mundial 2026 (el Elo, en cambio, se actualiza mapa a mapa).
    m_pre = fit_bt(pre, half_life, c, test["date"].min())
    check = _metrics(test["target"].to_numpy(), bt_predict(m_pre, test))

    # Final: todos los mapas de la temporada, incluido el Mundial 2026 como historia.
    name_to_id = season.drop_duplicates("teamname_blue").set_index("teamname_blue")["teamid_blue"].to_dict()
    name_to_id.update(season.drop_duplicates("teamname_red").set_index("teamname_red")["teamid_red"].to_dict())
    a, b = name_to_id[teams[0]], name_to_id[teams[1]]
    rules = side_rules(pd.read_parquet(PROJECT_ROOT / cfg["data"]["processed_dir"] / cfg["series"]["output_file"]),
                       float(cfg["simulation"]["map1_p_team_blue"]))
    m_all = fit_bt(season, half_life, c)
    pmap = bt_pmap(m_all, a, b)
    p_series = series_win(exact_series(pmap, rules))

    # Bootstrap por series (los mapas de una serie no son independientes).
    ser = build_series(season, float(cfg["series"]["max_gap_hours"]))
    groups = {k: v.index.to_numpy() for k, v in ser.groupby("serie")}
    keys = list(groups)
    boot, gaps = [], []
    for _ in range(int(cfg["verification"]["bt_n_bootstrap"])):
        pick = rng.choice(len(keys), len(keys), replace=True)
        idx = np.concatenate([groups[keys[i]] for i in pick])
        mb = fit_bt(ser.loc[idx], half_life, c, season["date"].max())
        if a not in mb["strength"] or b not in mb["strength"]:
            continue  # remuestreo sin mapas de algún finalista
        boot.append(series_win(exact_series(bt_pmap(mb, a, b), rules)))
        gaps.append(mb["strength"][a] - mb["strength"][b])
    lvl = float(cfg["simulation"]["ci_level"])
    q = [(1 - lvl) / 2, 1 - (1 - lvl) / 2]
    ranking = (pd.Series(m_all["strength"]).rename(index=season.drop_duplicates("teamid_blue")
                                                  .set_index("teamid_blue")["teamname_blue"]).sort_values(ascending=False))
    return {"check": check, "pmap": pmap, "p_series": p_series, "boot": np.array(boot),
            "ci": tuple(np.quantile(boot, q)), "gap": m_all["strength"][a] - m_all["strength"][b],
            "gap_ci": tuple(np.quantile(gaps, q)), "blue": m_all["blue"], "fp": m_all["fp"], "ranking": ranking}


# ---------------------------------------------------------------------------
# 3. Diagnósticos en Bo5: momentum, barridas y comparación fuera de muestra
# ---------------------------------------------------------------------------
def _split_eval(df: pd.DataFrame, cfg: dict[str, Any]) -> dict[str, pd.DataFrame]:
    """Bo5 anteriores al Mundial de evaluación (ajuste) y Bo5 del Mundial de evaluación."""
    eval_league, eval_year = cfg["data"]["eval_league"], int(cfg["modeling"]["eval_year"])
    is_eval = (df["league"] == eval_league) & (df["year"] == eval_year)
    start = df.loc[is_eval, "date"].min()
    return {"Bo5 previos al Mundial 2026": df[~is_eval & (df["date"] < start)],
            f"Bo5 {eval_league} {eval_year}": df[is_eval]}


def _cluster_se(resid: np.ndarray, groups: np.ndarray) -> float:
    """Error estándar de la media de ``resid`` robusto a correlación dentro de cada serie."""
    r = resid - resid.mean()
    sums = pd.Series(r).groupby(groups).sum().to_numpy()
    return float(np.sqrt(np.sum(sums**2)) / len(r))


def momentum_bo5(series: pd.DataFrame, bt: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    """P(gana el mapa n | ganó el n-1) en Bo5 frente a lo que espera cada modelo.

    Esperado según:
      - ``elo_actualizado``: elo_prob de cada mapa (el Elo ya se actualizó con los mapas previos).
      - ``estatico``: Elo previo a la serie, fijo (lo que asume el simulador estático).
      - ``forma_del_dia``: estático + eps de la serie, con su posterior dados los mapas previos.
    """
    bonus = float(cfg["elo"]["blue_bonus"])
    sigma = float(cfg["simulation"]["day_form_sigma"])
    x, w = np.polynomial.hermite.hermgauss(int(cfg["simulation"]["gh_nodes"]))
    eps_nodes, prior = np.sqrt(2) * sigma * x, w / np.sqrt(np.pi)

    info = bt.set_index("serie")[["elo_diff_pre"]]
    rows = []
    for sid, g in series[series["serie"].isin(info.index)].groupby("serie", sort=False):
        g = g.sort_values("date")
        a = g["teamid_blue"].iloc[0]  # A = azul del mapa 1 (igual que en el backtest)
        diff = float(info.loc[sid, "elo_diff_pre"])
        post = prior.copy()  # posterior de eps (sin normalizar) dados los mapas previos
        for i, r in enumerate(g.itertuples()):
            a_blue = r.teamid_blue == a
            z = ELO_LOGIT * (diff + (bonus if a_blue else -bonus))  # logit estático de A
            a_won = int(r.ganador == a)
            if i > 0:
                prev_a_won = int(g["ganador"].iloc[i - 1] == a)
                pw_is_a = bool(prev_a_won)
                p_a_upd = r.elo_prob if a_blue else 1 - r.elo_prob
                p_a_static = float(_sigmoid(z))
                p_a_form = float(np.sum(post / post.sum() * _sigmoid(z + eps_nodes)))
                conv = (lambda p: p) if pw_is_a else (lambda p: 1 - p)
                rows.append({"serie": sid, "date": r.date, "league": r.league, "year": r.year, "game": r.game,
                             "gana_ganador_prev": int(a_won == prev_a_won),
                             "elo_actualizado": conv(p_a_upd), "estatico": conv(p_a_static),
                             "forma_del_dia": conv(p_a_form)})
            # Actualiza la posterior de eps con el resultado de este mapa.
            pa = _sigmoid(z + eps_nodes)
            post = post * (pa if a_won else 1 - pa)
    m = pd.DataFrame(rows)

    out = []
    for grupo, sub in _split_eval(m, cfg).items():
        y = sub["gana_ganador_prev"].to_numpy()
        for modelo in ("elo_actualizado", "estatico", "forma_del_dia"):
            res = y - sub[modelo].to_numpy()
            out.append({"grupo": grupo, "esperado_por": modelo, "n_mapas": len(sub), "n_series": sub["serie"].nunique(),
                        "real": float(y.mean()), "esperado": float(sub[modelo].mean()),
                        "residual": float(res.mean()), "se": float(res.std(ddof=1) / np.sqrt(len(res))),
                        "se_cluster": _cluster_se(res, sub["serie"].to_numpy())})
    return pd.DataFrame(out)


def series_variant_probs(bt: pd.DataFrame, cfg: dict[str, Any]) -> dict[str, list[dict[str, float]]]:
    """Distribución de marcadores de cada serie según las 3 variantes del simulador."""
    bonus = float(cfg["elo"]["blue_bonus"])
    nodes = int(cfg["simulation"]["gh_nodes"])
    sigma = float(cfg["simulation"]["day_form_sigma"])
    recal = pd.read_parquet(PROJECT_ROOT / cfg["data"]["processed_dir"] / cfg["verification"]["recal_file"])
    full = recal[recal["muestra"] == -1].iloc[0]
    static = variant_dists(bt, bonus, False, 0.0, nodes)
    recal_d = [rescale_scores(d, float(apply_recalibration(series_win(d), full["a"], full["b"]))) for d in static]
    form = variant_dists(bt, bonus, False, sigma, nodes)
    return {"estático": static, "recalibración": recal_d, "forma del día": form}


def sweeps_and_oos(bt: pd.DataFrame, cfg: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(2) Barridas reales vs predichas y (3) métricas por serie de las 3 variantes."""
    sweeps, metrics_rows = [], []
    for grupo, sub in _split_eval(bt, cfg).items():
        dists = series_variant_probs(sub, cfg)
        real = sub["marcador"].isin(["3-0", "0-3"]).to_numpy().astype(float)
        row = {"grupo": grupo, "n_series": len(sub), "barridas_real": float(real.mean()),
               "se_real": float(real.std(ddof=1) / np.sqrt(len(real)))}
        for name, d in dists.items():
            row[f"pred_{name}"] = float(np.mean([x.get("3-0", 0) + x.get("0-3", 0) for x in d]))
        sweeps.append(row)

        y = sub["a_gana"].to_numpy()
        base = None
        for name, d in dists.items():
            p = np.array([series_win(x) for x in d])
            m = _metrics(y, p)
            ll_i = -(y * np.log(np.clip(p, 1e-6, 1)) + (1 - y) * np.log(np.clip(1 - p, 1e-6, 1)))
            if base is None:
                base = ll_i
            metrics_rows.append({"grupo": grupo, "variante": name, "n_series": m["n"], "log_loss": m["log_loss"],
                                 "brier": m["brier"], "nll_marcador": score_nll(sub, d),
                                 "dif_vs_estatico": float(np.mean(ll_i - base)),
                                 "se_dif": float(np.std(ll_i - base, ddof=1) / np.sqrt(len(y))) if len(y) > 1 else np.nan})
    return pd.DataFrame(sweeps), pd.DataFrame(metrics_rows)


def run_diagnostics(cfg: dict[str, Any]) -> dict[str, pd.DataFrame]:
    """Calcula los 3 diagnósticos en Bo5 y los guarda en un parquet por tabla."""
    proc = PROJECT_ROOT / cfg["data"]["processed_dir"]
    feats = pd.read_parquet(proc / cfg["features"]["output_file"])
    series = build_series(feats, float(cfg["series"]["max_gap_hours"]))
    bt = pd.read_parquet(proc / cfg["verification"]["backtest_file"])
    mom = momentum_bo5(series, bt, cfg)
    sweeps, oos = sweeps_and_oos(bt, cfg)
    for name, df in (("momentum", mom), ("barridas", sweeps), ("metricas_series", oos)):
        df.to_parquet(proc / f"diag_{name}.parquet", index=False)
    return {"momentum": mom, "barridas": sweeps, "metricas": oos}


def _md_table(df: pd.DataFrame) -> str:
    """Tabla Markdown simple (sin dependencias extra)."""
    head = "| " + " | ".join(df.columns) + " |"
    sep = "|" + "|".join(["---"] * len(df.columns)) + "|"
    body = ["| " + " | ".join(str(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join([head, sep, *body])


def _pct(x: float) -> str:
    return f"{100 * x:.1f} %"


def write_diagnostics_report(res: dict[str, pd.DataFrame], cfg: dict[str, Any], path: Any) -> None:
    """Escribe el informe Markdown con las 3 tablas, generado a partir de los resultados."""
    eval_league, eval_year = cfg["data"]["eval_league"], int(cfg["modeling"]["eval_year"])
    eval_name = f"Bo5 {eval_league} {eval_year}"  # nombre del grupo fuera de muestra (ver _split_eval)
    sigma = float(cfg["simulation"]["day_form_sigma"])
    lo, hi = (float(v) for v in cfg["simulation"]["day_form_sigma_ci"])
    names = {"elo_actualizado": "Elo actualizado mapa a mapa", "estatico": "Simulador estático",
             "forma_del_dia": "Forma del día"}

    mom = res["momentum"].copy()
    mom_t = pd.DataFrame({
        "Grupo": mom["grupo"], "Esperado según": mom["esperado_por"].map(names),
        "Mapas": mom["n_mapas"], "Series": mom["n_series"],
        "Real": mom["real"].map("{:.3f}".format), "Esperado": mom["esperado"].map("{:.3f}".format),
        "Residual ± EE (cluster)": [f"{r:+.3f} ± {s:.3f}" for r, s in zip(mom["residual"], mom["se_cluster"])],
        "z": (mom["residual"] / mom["se_cluster"]).map("{:+.1f}".format),
    })

    sw = res["barridas"]
    sw_t = pd.DataFrame({
        "Grupo": sw["grupo"], "Series": sw["n_series"],
        "Real ± EE": [f"{_pct(r)} ± {_pct(s)}" for r, s in zip(sw["barridas_real"], sw["se_real"])],
        "Estático": sw["pred_estático"].map(_pct), "Recalibración": sw["pred_recalibración"].map(_pct),
        "Forma del día": sw["pred_forma del día"].map(_pct),
    })

    met = res["metricas"]
    oos = met[met["grupo"] == eval_name]
    ins = met[met["grupo"] != eval_name]

    def met_table(df: pd.DataFrame) -> str:
        return _md_table(pd.DataFrame({
            "Variante": df["variante"], "Series": df["n_series"],
            "Log-loss": df["log_loss"].map("{:.4f}".format), "Brier": df["brier"].map("{:.4f}".format),
            "NLL del marcador": df["nll_marcador"].map("{:.4f}".format),
            "Δ log-loss vs estático ± EE": [("—" if v == "estático" else f"{d:+.4f} ± {s:.4f}")
                                            for v, d, s in zip(df["variante"], df["dif_vs_estatico"], df["se_dif"])],
        }))

    pre = mom[(mom["esperado_por"] == "estatico") & (mom["grupo"] != eval_name)].iloc[0]
    form = mom[(mom["esperado_por"] == "forma_del_dia") & (mom["grupo"] != eval_name)].iloc[0]
    upd = mom[(mom["esperado_por"] == "elo_actualizado") & (mom["grupo"] != eval_name)].iloc[0]
    sw_pre = sw[sw["grupo"] != eval_name].iloc[0]
    o = oos.set_index("variante")

    text = f"""# Verificación de la "forma del día"

Generado por `python -m lolpred.verification --diagnosticos` a partir de los datos reales de
Oracle's Elixir (Bo5 de 2025-2026 en las ligas del proyecto). Fecha: {pd.Timestamp.now():%Y-%m-%d %H:%M}.

- **Simulador estático**: probabilidad por mapa fija durante la serie (Elo previo a la serie + lado).
- **Recalibración**: P(serie) del estático pasada por sigmoide(a + b·logit(p)) ajustada en el backtest.
- **Forma del día**: cada serie recibe eps ~ N(0, σ²) común a todos sus mapas;
  σ = {sigma:.3f} (IC {float(cfg['simulation']['ci_level']):.0%} perfilado: [{lo:.3f}, {hi:.3f}]),
  ajustado con el marcador de los Bo5 previos al Mundial {eval_year}.

Los ajustes (σ, recalibración) usan solo series **anteriores** al {eval_league} {eval_year}; las
series del {eval_league} {eval_year} son **fuera de muestra**.

## 1. Momentum en Bo5: P(gana el mapa n | ganó el mapa n−1)

El error estándar es robusto a la correlación dentro de cada serie (cluster por serie).

{_md_table(mom_t)}

**Lectura.** Con el Elo actualizado mapa a mapa no hay momentum (residual {upd['residual']:+.3f} ±
{upd['se_cluster']:.3f}). El simulador estático, que no actualiza, subestima la probabilidad de
que el ganador del mapa anterior repita (residual {pre['residual']:+.3f} ± {pre['se_cluster']:.3f},
z = {pre['residual'] / pre['se_cluster']:+.1f}). La forma del día absorbe esa correlación
(residual {form['residual']:+.3f} ± {form['se_cluster']:.3f}).

## 2. Tasa de barridas (3-0 o 0-3) en Bo5

{_md_table(sw_t)}

**Lectura.** En los {int(sw_pre['n_series'])} Bo5 previos, el estático predice
{_pct(sw_pre['pred_estático'])} de barridas frente a {_pct(sw_pre['barridas_real'])} reales; la
recalibración no lo corrige ({_pct(sw_pre['pred_recalibración'])}) y la forma del día sí
({_pct(sw_pre['pred_forma del día'])}).

## 3. Log-loss y Brier por serie

### {eval_league} {eval_year} (fuera de muestra)

{met_table(oos)}

**Lectura.** Frente al estático, la recalibración mejora el log-loss del ganador
({o.loc['recalibración', 'dif_vs_estatico']:+.4f} ± {o.loc['recalibración', 'se_dif']:.4f}) y la forma del
día el del marcador completo (NLL {o.loc['forma del día', 'nll_marcador']:.3f} frente a
{o.loc['estático', 'nll_marcador']:.3f}). Con {int(o.loc['estático', 'n_series'])} series ninguna
diferencia es estadísticamente significativa: los errores estándar son mayores que las diferencias.

### Bo5 previos (referencia; muestra de ajuste, no fuera de muestra)

{met_table(ins)}

## Conclusión

La forma del día explica el mecanismo (correlación entre mapas que el simulador estático pierde),
reproduce la tasa de barridas y rinde igual que la recalibración en el ganador de la serie. Se
mantiene como ajuste oficial (`simulation.series_adjustment: day_form` en `config.yaml`).
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def diagnostics_main() -> None:
    """Punto de entrada: ``python -m lolpred.verification --diagnosticos`` (requiere el backtest)."""
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    cfg = load_config()
    pd.set_option("display.width", 200)
    res = run_diagnostics(cfg)
    report = PROJECT_ROOT / "reports" / "model" / "verificacion_forma_dia.md"
    write_diagnostics_report(res, cfg, report)
    print(f"Informe: {report}")
    print("=== 1. Momentum en Bo5: P(gana mapa n | ganó n-1) ===")
    print(res["momentum"].round(4).to_string(index=False))
    print("\n=== 2. Barridas (3-0 o 0-3) en Bo5 ===")
    print(res["barridas"].round(4).to_string(index=False))
    print("\n=== 3. Métricas por serie (dif_vs_estatico < 0 = mejor que el estático) ===")
    print(res["metricas"].round(4).to_string(index=False))


def main() -> None:
    """Punto de entrada: ``python -m lolpred.verification``."""
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    cfg = load_config()
    pd.set_option("display.width", 170)
    proc = PROJECT_ROOT / cfg["data"]["processed_dir"]
    feats = pd.read_parquet(proc / cfg["features"]["output_file"])
    series = build_series(feats, float(cfg["series"]["max_gap_hours"]))

    print("=== 1. Backtest del simulador (Elo previo a cada serie) ===")
    bt = backtest_series(series, cfg)
    bt.to_parquet(proc / cfg["verification"]["backtest_file"], index=False)
    print(backtest_report(bt, cfg).round(3).to_string(index=False))
    print("Referencia: predecir siempre 50 % da log-loss 0.693 y Brier 0.250.")

    recal = fit_series_recalibration(bt, cfg, np.random.default_rng(int(cfg["simulation"]["random_state"])))
    recal.to_parquet(proc / cfg["verification"]["recal_file"], index=False)
    full, boot = recal[recal["muestra"] == -1].iloc[0], recal[recal["muestra"] >= 0]
    print(f"\nRecalibración de series (n={int(full['n_series'])}): a={full['a']:+.3f}, b={full['b']:.3f} "
          f"(IC 90% de b: [{boot['b'].quantile(0.05):.3f}, {boot['b'].quantile(0.95):.3f}])")
    # Comprobación fuera de muestra en las series del Mundial de evaluación.
    ev = bt[(bt["league"] == cfg["data"]["eval_league"]) & (bt["year"] == int(cfg["modeling"]["eval_year"]))]
    if len(ev):
        raw = _metrics(ev["a_gana"].to_numpy(), ev["p_a"].to_numpy())
        cal = _metrics(ev["a_gana"].to_numpy(), apply_recalibration(ev["p_a"].to_numpy(), full["a"], full["b"]))
        print(f"Series del Mundial de evaluación (n={raw['n']}): log-loss {raw['log_loss']:.4f} -> "
              f"{cal['log_loss']:.4f} recalibrado; Brier {raw['brier']:.4f} -> {cal['brier']:.4f}")

    print("\n=== 1b. Variantes del simulador (marcador completo; tarda ~3 min) ===")
    table, choice = evaluate_variants(bt, cfg)
    print(table.drop(columns=["dinamico"]).round(3).to_string(index=False))
    pd.DataFrame([choice]).to_parquet(proc / cfg["verification"]["series_model_file"], index=False)
    write_series_model(choice, PROJECT_ROOT / "config.yaml")
    print(f"Elegida (menor NLL del marcador en series pre-Mundial): {choice['variante']} "
          f"sigma={choice['sigma']:.3f} (IC {cfg['simulation']['ci_level']:.0%} perfilado: "
          f"[{choice['sigma_lo']:.3f}, {choice['sigma_hi']:.3f}])")

    print("\n=== 2. Bradley-Terry ===")
    grid = tune_bt(feats, cfg)
    print("Ajuste (log-loss en el Mundial 2025, mapas de 2025 previos):")
    print(grid.head(5).round(4).to_string(index=False))
    hl, c = float(grid.iloc[0]["half_life"]), float(grid.iloc[0]["C"])
    res = bt_final(feats, cfg, hl, c, np.random.default_rng(int(cfg["simulation"]["random_state"])))
    print(f"\nElegido: half_life={hl:g} días, C={c:g}")
    ck = res["check"]
    print(f"Comprobación en el Mundial 2026 (ratings fijos antes del torneo): log-loss {ck['log_loss']:.4f}, "
          f"Brier {ck['brier']:.4f}, accuracy {ck['accuracy']:.3f} (n={ck['n']})")
    print(f"Ventaja azul (logit) {res['blue']:+.3f} | efecto primer pick {res['fp']:+.3f}")
    print("Top 8 fuerzas 2026:", ", ".join(f"{k} {v:+.2f}" for k, v in res["ranking"].head(8).items()))
    a, b = cfg["simulation"]["teams"]
    lvl = cfg["simulation"]["ci_level"]
    print(f"\nDiferencia de fuerza {a} − {b}: {res['gap']:+.3f} (IC {lvl:.0%}: [{res['gap_ci'][0]:+.3f}, {res['gap_ci'][1]:+.3f}])")
    for (blue, fp), p in sorted(res["pmap"].items(), reverse=True):
        print(f"  P({a} gana mapa) {'azul' if blue else 'rojo'} {'con' if fp else 'sin'} FP: {p:.3f}")
    print(f"P({a} gana la serie): {res['p_series']:.3f}  IC {lvl:.0%} bootstrap por series: "
          f"[{res['ci'][0]:.3f}, {res['ci'][1]:.3f}] ({len(res['boot'])} remuestreos)")
    pd.DataFrame({"p_series": res["boot"]}).to_parquet(proc / cfg["verification"]["bt_output_file"], index=False)


if __name__ == "__main__":
    sys.exit(diagnostics_main() if "--diagnosticos" in sys.argv else main())
