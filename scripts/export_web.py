"""Exporta los JSON que lee la web (web/src/assets/data/).

Genera: prediction.json, elo_history.json, top_elo.json, shap.json y metrics.json.
Conserva mvp.json y draft.json (lolpred.scouting) y scoreboard.json (lolpred.scoreboard);
aquí solo se comprueba que existan.
Requiere haber corrido antes el pipeline (ver scripts/run_pipeline.py).

Uso: ``py scripts/export_web.py``
"""

from __future__ import annotations

import json
import logging
import math
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from lolpred.elo import final_ratings  # noqa: E402
from lolpred.etl import PROJECT_ROOT, load_config  # noqa: E402
from lolpred.simulation import run_simulation, save_prediction  # noqa: E402

logger = logging.getLogger("export_web")


def _clean(obj: Any, digits: int = 4) -> Any:
    """Convierte a tipos JSON: NaN -> null, numpy -> python, floats redondeados."""
    if isinstance(obj, dict):
        return {str(k): _clean(v, digits) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v, digits) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        return None if math.isnan(float(obj)) else round(float(obj), digits)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, pd.Timestamp):
        return f"{obj:%Y-%m-%d}"
    return obj


def _records(df: pd.DataFrame, digits: int = 4) -> list[dict[str, Any]]:
    return _clean(df.to_dict("records"), digits)


def _write(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Guardado %s", path)


def _team_ids(ge: pd.DataFrame, names: list[str]) -> dict[str, str]:
    """teamid de cada nombre (el último usado en los datos)."""
    out = {}
    for n in names:
        ids = ge.loc[ge["teamname"] == n].sort_values("date")["teamid"]
        if ids.empty:
            raise ValueError(f"No se encontró el equipo '{n}' en los datos")
        out[n] = ids.iloc[-1]
    return out


# ---------------------------------------------------------------------------
def export_prediction(cfg: dict[str, Any]) -> None:
    """prediction.json: P(serie) e IC, marcadores (forma del día y estático), P(mapa), sigma y fecha."""
    save_prediction(run_simulation(cfg), cfg)


def export_elo_history(cfg: dict[str, Any], ge: pd.DataFrame, out_dir: Path) -> None:
    """elo_history.json: Elo previo a cada mapa de los finalistas en las temporadas modeladas."""
    teams = list(cfg["simulation"]["teams"])
    ids = _team_ids(ge, teams)
    model = ge[~ge["is_warmup"]]
    opp = model[["gameid", "teamid", "teamname"]].rename(columns={"teamid": "opp_id", "teamname": "rival"})
    series = {}
    for name, tid in ids.items():
        t = model[model["teamid"] == tid].merge(opp, on="gameid")
        t = t[t["opp_id"] != tid].sort_values("date")
        pts = [{"date": f"{r.date:%Y-%m-%d %H:%M}", "elo": round(float(r.elo_pre), 1), "league": r.league,
                "rival": r.rival, "result": int(r.result)} for r in t.itertuples()]
        last = final_ratings(ge[ge["teamid"] == tid], cfg["elo"]).iloc[0]
        series[name] = {"teamid": tid, "points": pts,
                        "elo_actual": round(float(last["elo_post"]), 1),
                        "fecha_actual": f"{last['date']:%Y-%m-%d %H:%M}"}
    _write(out_dir / "elo_history.json", {
        "nota": "Elo previo a cada mapa (temporadas 2025-2026; 2024 solo como calentamiento). "
                "elo_actual = Elo tras el último mapa jugado.",
        "teams": series,
    })


def export_top_elo(cfg: dict[str, Any], ge: pd.DataFrame, out_dir: Path, top_n: int = 15) -> None:
    """top_elo.json: top N de Elo justo antes de la final (tras el último mapa del Mundial)."""
    from lolpred.eda import home_league

    eval_league, eval_year = cfg["data"]["eval_league"], int(cfg["modeling"]["eval_year"])
    cutoff = ge.loc[(ge["league"] == eval_league) & (ge["year"] == eval_year), "date"].max()
    r = final_ratings(ge[ge["date"] <= cutoff], cfg["elo"]).head(top_n).reset_index(drop=True)
    home = home_league(ge[~ge["is_warmup"]], cfg["elo"]["international_leagues"])
    r["region"] = r["teamid"].map(home)
    r["rank"] = np.arange(1, len(r) + 1)
    _write(out_dir / "top_elo.json", {
        "fecha_corte": f"{cutoff:%Y-%m-%d %H:%M}",
        "nota": f"Elo tras el último mapa del {eval_league} {eval_year} (antes de la final).",
        "teams": _records(r[["rank", "teamname", "region", "elo_post"]].rename(columns={"elo_post": "elo"}), 1),
    })


def export_shap(cfg: dict[str, Any], out_dir: Path) -> None:
    """shap.json: importancias globales por grupo y desglose del enfrentamiento."""
    proc = PROJECT_ROOT / cfg["data"]["processed_dir"]
    glob = pd.read_parquet(proc / cfg["explain"]["global_file"])
    mt = pd.read_parquet(proc / cfg["explain"]["matchup_file"])
    team, rival = cfg["simulation"]["teams"]
    matchup = []
    for sc, d in mt.groupby("escenario", sort=False):
        first = d.iloc[0]
        matchup.append({
            "escenario": sc, "team_a_blue": bool(first["team_a_blue"]), "team_a_first_pick": bool(first["team_a_fp"]),
            "base_logit": first["base_equipo"], "p": first["p_equipo"],
            "contribuciones": _records(d.sort_values("shap_equipo", key=abs, ascending=False)[["grupo", "shap_equipo"]]
                                       .rename(columns={"shap_equipo": "shap"})),
        })
    _write(out_dir / "shap.json", _clean({
        "modelo": "LightGBM calibrado (Platt). El modelo oficial de la predicción es el Elo (una sola feature).",
        "unidad": "contribución al logit de la probabilidad",
        "team_a": team, "team_b": rival,
        "global": _records(glob[["grupo", "importancia", "features"]]),
        "matchup": matchup,
    }))


def export_metrics(cfg: dict[str, Any], out_dir: Path) -> None:
    """metrics.json: modelos de mapa, backtest de series y las 3 variantes de la verificación."""
    from lolpred.verification import backtest_report

    proc = PROJECT_ROOT / cfg["data"]["processed_dir"]
    mcfg = cfg["modeling"]
    table = pd.read_parquet(proc / mcfg["metrics_file"])
    val = table[table["fold"] == int(mcfg["val_year"])]
    chosen = {m: val[val["model"] == m].sort_values("log_loss").iloc[0]["calibration"] for m in val["model"].unique()}
    sel = table[[chosen[m] == c for m, c in zip(table["model"], table["calibration"])]]
    labels = {"elo": "(a) Solo Elo", "logreg": "(b) Regresión logística", "lgbm": "(c) LightGBM"}
    sel = sel.assign(modelo=sel["model"].map(labels), mundial=sel["fold"].map(lambda y: f"{cfg['data']['eval_league']} {y}"))

    bt = pd.read_parquet(proc / cfg["verification"]["backtest_file"])
    bt_table = backtest_report(bt, cfg)
    variants = pd.read_parquet(proc / "diag_metricas_series.parquet")
    sweeps = pd.read_parquet(proc / "diag_barridas.parquet")
    momentum = pd.read_parquet(proc / "diag_momentum.parquet")

    _write(out_dir / "metrics.json", {
        "mejor_modelo": f"{mcfg['best_model']} ({mcfg['best_calibration']})",
        "regla": f"Mejor log-loss en el {cfg['data']['eval_league']} {mcfg['val_year']}; "
                 f"el {mcfg['eval_year']} solo se usa para evaluar.",
        "modelos_mapa": _records(sel[["mundial", "modelo", "calibration", "n_train", "n", "log_loss", "brier", "accuracy"]]),
        "backtest_series": _records(bt_table),
        "variantes_series": _records(variants),
        "barridas": _records(sweeps),
        "momentum_bo5": _records(momentum),
    })


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = load_config()
    out_dir = PROJECT_ROOT / cfg["scouting"]["web_data_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    ge = pd.read_parquet(PROJECT_ROOT / cfg["data"]["processed_dir"] / cfg["elo"]["output_file"])

    export_prediction(cfg)
    export_elo_history(cfg, ge, out_dir)
    export_top_elo(cfg, ge, out_dir)
    export_shap(cfg, out_dir)
    export_metrics(cfg, out_dir)
    for keep, mod in (("mvp.json", "scouting"), ("draft.json", "scouting"), ("scoreboard.json", "scoreboard")):
        if not (out_dir / keep).exists():
            raise FileNotFoundError(f"Falta {keep}: ejecuta lolpred.{mod}")
    print("JSON en", out_dir, "->", ", ".join(sorted(p.name for p in out_dir.glob("*.json"))))


if __name__ == "__main__":
    main()
