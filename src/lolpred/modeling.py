"""Modelado con validación estrictamente temporal.

Folds (el Mundial NUNCA entra a entrenar):
  - Validación: train = todo lo anterior al Mundial ``val_year`` (sin WLDs, sin
    calentamiento); test = WLDs ``val_year``. Aquí se eligen la calibración y el modelo.
  - Evaluación: train = todo lo anterior al Mundial ``eval_year``; test = WLDs ``eval_year``.

Dentro de cada train se reservan los bloques más recientes (orden temporal, nunca
aleatorio): ``es`` para el early stopping de LightGBM y ``cal`` para calibrar.

Modelos: (a) solo ``elo_prob``; (b) regresión logística; (c) LightGBM poco profundo.
"""

from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib
import lightgbm as lgb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.calibration import CalibratedClassifierCV  # noqa: E402
from sklearn.frozen import FrozenEstimator  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import brier_score_loss, log_loss  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from lolpred.etl import PROJECT_ROOT, load_config  # noqa: E402

logger = logging.getLogger(__name__)

MODEL_NAMES: tuple[str, ...] = ("elo", "logreg", "lgbm")


class LeakageAlarm(RuntimeError):
    """La accuracy en un Mundial supera lo plausible: hay que buscar leakage antes de seguir."""


# ---------------------------------------------------------------------------
# Cortes temporales
# ---------------------------------------------------------------------------
def temporal_split(
    df: pd.DataFrame, cfg: dict[str, Any], year: int | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Separa train y test con un corte temporal, nunca aleatorio.

    - test: mapas de ``eval_league`` en ``year`` (por defecto ``eval_year``).
    - train: mapas anteriores al primer mapa de test y que NO son de ``eval_league``
      (ningún Mundial entra a entrenar, ni siquiera el del año anterior).
    """
    eval_league: str = cfg["data"]["eval_league"]
    year = int(cfg["modeling"]["eval_year"]) if year is None else int(year)

    # Las filas de calentamiento (2024) nunca entran ni a train ni a test.
    if "is_warmup" in df.columns:
        df = df.loc[~df["is_warmup"]]
    is_eval = df["league"] == eval_league
    test = df.loc[is_eval & (df["year"] == year)]
    if test.empty:
        raise ValueError(f"No hay mapas de {eval_league} {year} para evaluar")
    cutoff = test["date"].min()
    train = df.loc[~is_eval & (df["date"] < cutoff)]
    return train.copy(), test.copy()


def time_blocks(
    train: pd.DataFrame, es_frac: float, cal_frac: float
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Divide el train en (núcleo, early stopping, calibración) por orden de fecha."""
    t = train.sort_values(["date", "gameid"], kind="mergesort")
    n = len(t)
    n_cal, n_es = int(round(n * cal_frac)), int(round(n * es_frac))
    core = t.iloc[: n - n_es - n_cal]
    es = t.iloc[n - n_es - n_cal : n - n_cal]
    cal = t.iloc[n - n_cal :]
    assert core["date"].max() <= es["date"].min() <= es["date"].max() <= cal["date"].min()
    return core, es, cal


# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------
def feature_columns(df: pd.DataFrame, mcfg: dict[str, Any]) -> list[str]:
    """Features del LightGBM: columnas con los prefijos de config más las extras."""
    prefixes = tuple(mcfg["lgbm_feature_prefixes"])
    cols = [c for c in df.columns if c.startswith(prefixes)]
    return list(dict.fromkeys([*mcfg["lgbm_extra_features"], *cols]))


@dataclass
class FittedModel:
    """Modelo listo para predecir P(gana el azul) a partir de la tabla de features."""

    name: str
    features: list[str]
    estimator: Any = None  # None = usa elo_prob directamente
    calibration: str = "none"
    info: dict[str, Any] = field(default_factory=dict)

    def predict_proba(self, df: pd.DataFrame) -> np.ndarray:
        if self.estimator is None:
            return df["elo_prob"].to_numpy(dtype=float)
        return self.estimator.predict_proba(df[self.features])[:, 1]


def _fit_base(name: str, core: pd.DataFrame, es: pd.DataFrame, cfg: dict[str, Any]) -> tuple[Any, list[str], dict]:
    """Ajusta el estimador base (sin calibrar) de un modelo."""
    mcfg = cfg["modeling"]
    if name == "logreg":
        feats = list(mcfg["logreg_features"])
        fit = pd.concat([core, es])  # la logística no necesita early stopping
        est = make_pipeline(StandardScaler(), LogisticRegression(C=float(mcfg["logreg_C"]), max_iter=1000))
        est.fit(fit[feats], fit["target"])
        return est, feats, {}
    if name == "lgbm":
        feats = feature_columns(core, mcfg)
        est = lgb.LGBMClassifier(**mcfg["lgbm_params"])
        est.fit(
            core[feats], core["target"],
            eval_X=(es[feats],), eval_y=(es["target"],), eval_metric="binary_logloss",
            callbacks=[lgb.early_stopping(int(mcfg["early_stopping_rounds"]), verbose=False)],
        )
        return est, feats, {"best_iteration": int(est.best_iteration_ or est.n_estimators)}
    raise ValueError(name)


def fit_models(train: pd.DataFrame, cfg: dict[str, Any]) -> dict[tuple[str, str], FittedModel]:
    """Ajusta los 3 modelos con todas las calibraciones. Clave: (modelo, calibración)."""
    mcfg = cfg["modeling"]
    core, es, cal = time_blocks(train, float(mcfg["es_frac"]), float(mcfg["cal_frac"]))
    out: dict[tuple[str, str], FittedModel] = {("elo", "none"): FittedModel("elo", ["elo_prob"])}
    for name in ("logreg", "lgbm"):
        base, feats, info = _fit_base(name, core, es, cfg)
        info = {**info, "n_core": len(core), "n_es": len(es), "n_cal": len(cal)}
        out[(name, "none")] = FittedModel(name, feats, base, "none", info)
        for method in mcfg["calibration_methods"]:
            # FrozenEstimator = el antiguo cv='prefit': el modelo NO se reentrena, solo
            # se ajusta el calibrador sobre el bloque temporal más reciente.
            calib = CalibratedClassifierCV(FrozenEstimator(base), method=method)
            calib.fit(cal[feats], cal["target"])
            out[(name, method)] = FittedModel(name, feats, calib, method, info)
    return out


# ---------------------------------------------------------------------------
# Métricas
# ---------------------------------------------------------------------------
def metrics(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    """log-loss, Brier y accuracy (umbral 0.5)."""
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return {
        "log_loss": float(log_loss(y, p, labels=[0, 1])),
        "brier": float(brier_score_loss(y, p)),
        "accuracy": float(np.mean((p > 0.5) == (y == 1))),
        "n": int(len(y)),
    }


def check_leakage(table: pd.DataFrame, threshold: float) -> None:
    """Detiene el proceso si algún modelo supera la accuracy plausible en un Mundial."""
    bad = table[table["accuracy"] > threshold]
    if len(bad):
        raise LeakageAlarm(
            f"Accuracy > {threshold:.0%} en un Mundial: revisar leakage antes de reportar.\n{bad.to_string()}"
        )


def calibration_plot(preds: pd.DataFrame, chosen: dict[str, str], out_path: Path) -> None:
    """Curvas de fiabilidad por Mundial (quintiles de probabilidad predicha)."""
    colors = {"elo": "#2a78d6", "logreg": "#eb6834", "lgbm": "#1baf7a"}
    labels = {"elo": "(a) Solo Elo", "logreg": "(b) Logística", "lgbm": "(c) LightGBM"}
    folds = sorted(preds["fold"].unique())
    fig, axes = plt.subplots(1, len(folds), figsize=(5.2 * len(folds), 4.8), sharey=True)
    for ax, fold in zip(np.atleast_1d(axes), folds):
        ax.plot([0, 1], [0, 1], color="#52514e", linestyle="--", linewidth=1)
        for name in MODEL_NAMES:
            s = preds[(preds["fold"] == fold) & (preds["model"] == name) & (preds["calibration"] == chosen[name])]
            q = pd.qcut(s["p"], 5, duplicates="drop")
            cal = s.groupby(q, observed=True).agg(p=("p", "mean"), y=("target", "mean"))
            ax.plot(cal["p"], cal["y"], marker="o", linewidth=2, markersize=6, color=colors[name],
                    label=f"{labels[name]} ({chosen[name]})")
        ax.set_title(f"WLDs {fold} (n={preds[(preds['fold'] == fold)]['gameid'].nunique()})", fontweight="bold")
        ax.set_xlabel("P(gana el azul) predicha")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.grid(color="#e4e3df")
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    np.atleast_1d(axes)[0].set_ylabel("Frecuencia real (quintiles)")
    np.atleast_1d(axes)[0].legend(loc="upper left", frameon=False, fontsize=8)
    fig.suptitle("Calibración de los modelos en los Mundiales", fontweight="bold")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def write_choice(cfg_path: Path, best_model: str, best_calibration: str) -> None:
    """Escribe best_model y best_calibration en la sección modeling de config.yaml."""
    text = cfg_path.read_text(encoding="utf-8")
    for key, val in (("best_model", best_model), ("best_calibration", best_calibration)):
        text, n = re.subn(rf"(\n  {key}: )[^\n#]*", rf"\g<1>{val}", text)
        if n != 1:
            raise ValueError(f"No se encontró '{key}' en config.yaml")
    cfg_path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Orquestación
# ---------------------------------------------------------------------------
def run_modeling(cfg: dict[str, Any], cfg_path: Path | None = None) -> dict[str, Any]:
    """Entrena y evalúa en los dos folds, elige con el de validación y guarda el mejor."""
    mcfg = cfg["modeling"]
    proc = PROJECT_ROOT / cfg["data"]["processed_dir"]
    feats = pd.read_parquet(proc / cfg["features"]["output_file"])
    val_year, eval_year = int(mcfg["val_year"]), int(mcfg["eval_year"])

    rows, pred_rows, fitted = [], [], {}
    for fold in (val_year, eval_year):
        train, test = temporal_split(feats, cfg, fold)
        models = fit_models(train, cfg)
        fitted[fold] = models
        for (name, calib), m in models.items():
            p = m.predict_proba(test)
            rows.append({"fold": fold, "model": name, "calibration": calib, "n_train": len(train),
                         **metrics(test["target"].to_numpy(), p), **m.info})
            pred_rows.append(pd.DataFrame({"fold": fold, "model": name, "calibration": calib,
                                           "gameid": test["gameid"].to_numpy(), "p": p,
                                           "target": test["target"].to_numpy()}))
    table = pd.DataFrame(rows)
    preds = pd.concat(pred_rows, ignore_index=True)
    check_leakage(table, float(mcfg["max_plausible_accuracy"]))

    # Decisiones SOLO con el fold de validación (Mundial val_year).
    val = table[table["fold"] == val_year]
    chosen = {n: val[val["model"] == n].sort_values("log_loss").iloc[0]["calibration"] for n in MODEL_NAMES}
    best_name = min(MODEL_NAMES, key=lambda n: val[(val["model"] == n) & (val["calibration"] == chosen[n])]["log_loss"].iloc[0])
    best = fitted[eval_year][(best_name, chosen[best_name])]

    # Guardado.
    models_dir = PROJECT_ROOT / mcfg["models_dir"]
    models_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(best, models_dir / mcfg["model_file"])
    # También los 3 modelos (fold de evaluación, calibración elegida) para análisis de sensibilidad.
    for name in MODEL_NAMES:
        joblib.dump(fitted[eval_year][(name, chosen[name])], models_dir / f"model_{name}.joblib")
    table.to_parquet(proc / mcfg["metrics_file"], index=False)
    preds.to_parquet(proc / mcfg["predictions_file"], index=False)
    out_dir = PROJECT_ROOT / "reports" / "model"
    out_dir.mkdir(parents=True, exist_ok=True)
    calibration_plot(preds, chosen, out_dir / "calibracion_modelos.png")
    write_choice(cfg_path or PROJECT_ROOT / "config.yaml", best_name, chosen[best_name])
    logger.info("Mejor modelo: %s (%s) -> %s", best_name, chosen[best_name], models_dir / mcfg["model_file"])
    return {"table": table, "chosen": chosen, "best": (best_name, chosen[best_name]), "preds": preds}


def main() -> None:
    """Punto de entrada: ``python -m lolpred.modeling``."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = load_config()
    res = run_modeling(cfg)
    t, chosen = res["table"], res["chosen"]
    pd.set_option("display.width", 160)
    sel = t[[chosen[m] == c for m, c in zip(t["model"], t["calibration"])]]
    print("\nMétricas en los Mundiales (calibración elegida con WLDs "
          f"{cfg['modeling']['val_year']}):")
    print(sel[["fold", "model", "calibration", "n_train", "n", "log_loss", "brier", "accuracy"]]
          .round(4).to_string(index=False))
    print("\nTodas las variantes:")
    print(t[["fold", "model", "calibration", "log_loss", "brier", "accuracy", "best_iteration"]]
          .round(4).to_string(index=False))
    print(f"\nMejor modelo (por log-loss en WLDs {cfg['modeling']['val_year']}): {res['best']}")


if __name__ == "__main__":
    # Se ejecuta desde el módulo IMPORTADO: así FittedModel se guarda en el joblib como
    # 'lolpred.modeling.FittedModel' y no como '__main__.FittedModel' (no se podría cargar).
    from lolpred.modeling import main as _main

    sys.exit(_main())
