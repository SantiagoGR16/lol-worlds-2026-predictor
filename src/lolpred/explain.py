"""Explicación SHAP del modelo de mapa calibrado.

- Modelo: el de ``explain.model_file`` (LightGBM + calibración Platt). El modelo oficial
  de la predicción es el Elo, que tiene una sola feature y no necesita SHAP.
- Se explica el LOGIT de la probabilidad CALIBRADA, P(gana el azul), con un explicador
  de permutaciones (independiente del modelo) y un fondo tomado del train.
- Las features se suman por grupos (config ``explain.groups``) para que variables muy
  correlacionadas (p. ej. oro y experiencia a los 15') no se repartan la importancia.

Salidas: ``reports/model/shap_importancia_global.png``, ``reports/model/shap_genG_vs_blg.png``
y los parquet ``shap_global`` y ``shap_matchup``.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import shap  # noqa: E402

from lolpred.etl import PROJECT_ROOT, load_config  # noqa: E402
from lolpred.modeling import FittedModel, temporal_split  # noqa: E402
from lolpred.simulation import scenario_features  # noqa: E402

logger = logging.getLogger(__name__)

C_POS, C_NEG, C_TEXT, C_TEXT2, C_GRID, C_SURF = "#2a78d6", "#e34948", "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


def feature_groups(features: list[str], groups_cfg: dict[str, list[str]]) -> dict[str, list[str]]:
    """Asigna cada feature a un grupo por prefijo. Las que no encajan quedan como grupo propio."""
    out: dict[str, list[str]] = {g: [] for g in groups_cfg}
    for f in features:
        for g, prefixes in groups_cfg.items():
            if any(f == p or f.startswith(p) for p in prefixes):
                out[g].append(f)
                break
        else:
            out[f] = [f]
    return {g: fs for g, fs in out.items() if fs}


def grouped_shap(values: np.ndarray, features: list[str], groups: dict[str, list[str]]) -> pd.DataFrame:
    """Suma los SHAP de las features de cada grupo (SHAP es aditivo: la suma es la del grupo)."""
    idx = {f: i for i, f in enumerate(features)}
    return pd.DataFrame({g: values[:, [idx[f] for f in fs]].sum(axis=1) for g, fs in groups.items()})


def explain_model(model: FittedModel, background: pd.DataFrame, rows: pd.DataFrame,
                  max_evals: int, seed: int) -> tuple[np.ndarray, float]:
    """SHAP por permutaciones del logit de la probabilidad calibrada. Devuelve (valores, base)."""
    feats = model.features

    def f(x: np.ndarray) -> np.ndarray:
        p = model.predict_proba(pd.DataFrame(x, columns=feats))
        p = np.clip(p, 1e-6, 1 - 1e-6)
        return np.log(p / (1 - p))

    masker = shap.maskers.Independent(background[feats].to_numpy(dtype=float), max_samples=len(background))
    explainer = shap.PermutationExplainer(f, masker, seed=seed)
    sv = explainer(rows[feats].to_numpy(dtype=float), max_evals=max_evals, silent=True)
    base = float(np.mean(sv.base_values))
    return np.asarray(sv.values), base


def _sigmoid(x: float) -> float:
    return float(1 / (1 + np.exp(-x)))


def plot_global(imp: pd.Series, title: str, path: Any) -> None:
    """Barras horizontales de importancia media |SHAP| por grupo."""
    imp = imp.sort_values()
    fig, ax = plt.subplots(figsize=(7, 4.2), facecolor=C_SURF)
    ax.set_facecolor(C_SURF)
    ax.barh(imp.index, imp.values, color=C_POS, height=0.6)
    for i, v in enumerate(imp.values):
        ax.text(v + imp.max() * 0.01, i, f"{v:.3f}", va="center", fontsize=8, color=C_TEXT2)
    ax.set_xlabel("Importancia media |SHAP| (logit de P(gana el azul))", color=C_TEXT2)
    ax.set_title(title, fontweight="bold", color=C_TEXT, fontsize=11)
    ax.grid(axis="x", color=C_GRID)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_matchup(mt: pd.DataFrame, team: str, rival: str, path: Any) -> None:
    """Desglose SHAP del enfrentamiento (perspectiva de ``team``) para cada lado."""
    scen = list(mt["escenario"].unique())
    # Misma escala en ambos paneles (para compararlos) y margen para las etiquetas de valor.
    fig, axes = plt.subplots(1, len(scen), figsize=(6.4 * len(scen), 4.6), sharey=True, sharex=True, facecolor=C_SURF)
    order = mt.groupby("grupo")["shap_equipo"].apply(lambda s: s.abs().max()).sort_values().index
    lo, hi = min(mt["shap_equipo"].min(), 0.0), max(mt["shap_equipo"].max(), 0.0)
    span = hi - lo
    np.atleast_1d(axes)[0].set_xlim(lo - 0.22 * span, hi + 0.18 * span)
    for ax, sc in zip(np.atleast_1d(axes), scen):
        ax.set_facecolor(C_SURF)
        d = mt[mt["escenario"] == sc].set_index("grupo").loc[order]
        colors = [C_POS if v >= 0 else C_NEG for v in d["shap_equipo"]]
        ax.barh(d.index, d["shap_equipo"], color=colors, height=0.6)
        ax.axvline(0, color=C_TEXT2, linewidth=0.8)
        for i, v in enumerate(d["shap_equipo"]):
            # Signo y valor como texto: no se depende solo del color.
            ax.text(v + (0.005 if v >= 0 else -0.005), i, f"{v:+.3f}", va="center",
                    ha="left" if v >= 0 else "right", fontsize=8, color=C_TEXT)
        r = d.iloc[0]
        ax.set_title(f"{sc}\nbase {_sigmoid(r['base_equipo']):.3f} → P({team}) {r['p_equipo']:.3f}",
                     fontsize=10, color=C_TEXT)
        ax.set_xlabel(f"Contribución al logit de P({team} gana el mapa)", color=C_TEXT2)
        ax.grid(axis="x", color=C_GRID)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    fig.suptitle(f"Desglose SHAP: {team} vs {rival} (modelo LightGBM calibrado)", fontweight="bold", color=C_TEXT)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def run_explain(cfg: dict[str, Any]) -> dict[str, Any]:
    """Calcula SHAP global (mapas del Mundial de evaluación) y del enfrentamiento de la final."""
    ecfg = cfg["explain"]
    proc = PROJECT_ROOT / cfg["data"]["processed_dir"]
    model: FittedModel = joblib.load(PROJECT_ROOT / cfg["modeling"]["models_dir"] / ecfg["model_file"])
    feats = pd.read_parquet(proc / cfg["features"]["output_file"])
    train, test = temporal_split(feats, cfg)
    background = train.sample(n=min(int(ecfg["background_n"]), len(train)), random_state=int(ecfg["random_state"]))
    groups = feature_groups(model.features, ecfg["groups"])

    # Global: mapas del Mundial de evaluación.
    sv, base = explain_model(model, background, test, int(ecfg["max_evals"]), int(ecfg["random_state"]))
    g = grouped_shap(sv, model.features, groups)
    imp = g.abs().mean().sort_values(ascending=False)
    glob = pd.DataFrame({"grupo": imp.index, "importancia": imp.values,
                         "features": [", ".join(groups[k]) for k in imp.index]})

    # Enfrentamiento: el equipo A en azul y en rojo, con blue_first_pick fijo.
    team, rival = cfg["simulation"]["teams"]
    games = pd.read_parquet(proc / cfg["data"]["games_file"])
    scen = scenario_features(games, cfg, [team, rival])
    scen = scen[scen["blue_first_pick"] == int(ecfg["matchup_blue_first_pick"])].reset_index(drop=True)
    sv_m, base_m = explain_model(model, background, scen, int(ecfg["max_evals"]), int(ecfg["random_state"]))
    gm = grouped_shap(sv_m, model.features, groups)
    p_blue = model.predict_proba(scen)
    rows = []
    for i, r in scen.iterrows():
        sign = 1.0 if r["team_a_blue"] else -1.0  # perspectiva de A: si A es rojo, se invierte
        name = f"{team} en {'azul' if r['team_a_blue'] else 'rojo'} ({'con' if r['team_a_fp'] else 'sin'} primer pick)"
        for grp in gm.columns:
            rows.append({"escenario": name, "team_a_blue": bool(r["team_a_blue"]), "team_a_fp": bool(r["team_a_fp"]),
                         "grupo": grp, "shap_azul": float(gm.loc[i, grp]), "shap_equipo": sign * float(gm.loc[i, grp]),
                         "base_azul": base_m, "base_equipo": sign * base_m,
                         "p_azul": float(p_blue[i]), "p_equipo": float(p_blue[i] if r["team_a_blue"] else 1 - p_blue[i])})
    mt = pd.DataFrame(rows)

    out = PROJECT_ROOT / "reports" / "model"
    out.mkdir(parents=True, exist_ok=True)
    plot_global(imp, f"Importancia SHAP por grupo: mapas del WLDs {cfg['modeling']['eval_year']} "
                     f"(n={len(test)})\nmodelo LightGBM calibrado", out / "shap_importancia_global.png")
    plot_matchup(mt, team, rival, out / "shap_genG_vs_blg.png")
    glob.to_parquet(proc / ecfg["global_file"], index=False)
    mt.to_parquet(proc / ecfg["matchup_file"], index=False)

    # Comprobación de aditividad: base + suma de SHAP = logit predicho.
    logit = np.log(np.clip(p_blue, 1e-6, 1 - 1e-6) / (1 - np.clip(p_blue, 1e-6, 1 - 1e-6)))
    max_err = float(np.max(np.abs(base_m + sv_m.sum(axis=1) - logit)))
    return {"global": glob, "matchup": mt, "base": base, "n_maps": len(test), "max_additivity_error": max_err,
            "model": f"{model.name} ({model.calibration})"}


def main() -> None:
    """Punto de entrada: ``python -m lolpred.explain``."""
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    cfg = load_config()
    res = run_explain(cfg)
    pd.set_option("display.width", 160)
    print(f"Modelo explicado: {res['model']} | mapas del Mundial: {res['n_maps']} | "
          f"error de aditividad máx.: {res['max_additivity_error']:.2e}")
    print("\nImportancia global (media |SHAP| por grupo, logit):")
    print(res["global"][["grupo", "importancia"]].round(4).to_string(index=False))
    print("\nDesglose del enfrentamiento (contribución al logit de P(equipo A gana el mapa)):")
    piv = res["matchup"].pivot(index="grupo", columns="escenario", values="shap_equipo")
    print(piv.round(3).to_string())
    for sc, d in res["matchup"].groupby("escenario"):
        print(f"  {sc}: base {_sigmoid(d['base_equipo'].iloc[0]):.3f} -> P = {d['p_equipo'].iloc[0]:.3f}")


if __name__ == "__main__":
    from lolpred.explain import main as _main

    sys.exit(_main())
