"""Comprueba los JSON que lee la web (salida real del pipeline: scripts/run_pipeline.py)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).resolve().parents[1] / "web" / "src" / "assets" / "data"
FILES = ["prediction.json", "elo_history.json", "top_elo.json", "shap.json", "metrics.json", "mvp.json", "draft.json", "scoreboard.json"]


def _load(name: str) -> dict:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", FILES)
def test_json_exists_and_parses(name: str) -> None:
    path = DATA_DIR / name
    assert path.exists(), f"Falta {name}: corre scripts/run_pipeline.py"
    assert _load(name)


@pytest.mark.parametrize("key", ["scores", "scores_static"])
def test_score_probabilities_sum_to_one(key: str) -> None:
    scores = _load("prediction.json")[key]
    assert {s["score"] for s in scores} == {"3-0", "3-1", "3-2", "2-3", "1-3", "0-3"}
    assert all(0 <= s["p"] <= 1 for s in scores)
    assert sum(s["p"] for s in scores) == pytest.approx(1.0, abs=0.001)


def test_series_probability_is_valid_and_consistent() -> None:
    pred = _load("prediction.json")
    p = pred["p_series_a"]
    assert 0 <= p <= 1 and 0 <= pred["p_series_a_static"] <= 1
    lo, hi = pred["ci"]
    assert 0 <= lo <= hi <= 1
    # P(serie) = suma de los marcadores ganados por A (redondeo a 4 decimales).
    won = sum(s["p"] for s in pred["scores"] if int(s["score"][0]) > int(s["score"][2]))
    assert won == pytest.approx(p, abs=0.001)
    assert all(0 <= m["p_a"] <= 1 for m in pred["maps"]) and len(pred["maps"]) == 4


def test_other_json_have_expected_content() -> None:
    top = _load("top_elo.json")["teams"]
    assert len(top) == 15 and [t["rank"] for t in top] == list(range(1, 16))
    assert all(top[i]["elo"] >= top[i + 1]["elo"] for i in range(14))
    hist = _load("elo_history.json")["teams"]
    assert len(hist) == 2 and all(len(t["points"]) > 0 for t in hist.values())
    shap = _load("shap.json")
    assert shap["global"] and len(shap["matchup"]) == 2
    metrics = _load("metrics.json")
    assert {"modelos_mapa", "backtest_series", "variantes_series"} <= set(metrics)


def test_scoreboard_consistent_with_prediction() -> None:
    sb, pred = _load("scoreboard.json"), _load("prediction.json")
    assert [m["map"] for m in sb["maps"]] == [1, 2, 3, 4, 5]
    by = {s["score"]: s["p"] for s in pred["scores"]}
    # Mapa 4 se juega si no hay barrida; mapa 5 si la serie llega a 3-2 / 2-3.
    assert sb["maps"][3]["p_played"] == pytest.approx(1 - by["3-0"] - by["0-3"], abs=0.002)
    assert sb["maps"][4]["p_played"] == pytest.approx(by["3-2"] + by["2-3"], abs=0.002)
    for team in (sb["team_a"], sb["team_b"]):
        t = sb["teams"][team]
        assert t["wins"] + t["losses"] == t["maps"] > 0
        starters = [p for p in t["players"] if p["starter"]]
        assert sorted(p["role"] for p in starters) == sorted(["top", "jng", "mid", "bot", "sup"])
        assert all(0 <= p["kp"] <= 1 for p in t["players"] if p["kp"] is not None)
