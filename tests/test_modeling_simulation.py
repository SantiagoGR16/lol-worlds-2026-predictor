"""Pruebas de modelado y simulación con datos SINTÉTICOS (tests/fixtures)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fixtures.synthetic import SYNTHETIC_CFG, elo_games

from lolpred.elo import compute_elo
from lolpred.features import build_features
from lolpred.modeling import LeakageAlarm, check_leakage, temporal_split, time_blocks
from lolpred.simulation import (
    SIM_GAMEID,
    exact_series,
    hypothetical_map,
    monte_carlo,
    series_win,
    side_rules,
)

# Reglas de lado SINTÉTICAS (mismo formato que side_choice.parquet).
_SIDE = pd.DataFrame(
    [
        {"contexto": "mapa1", "azul": True, "primer_pick": True, "prob": 0.4},
        {"contexto": "mapa1", "azul": True, "primer_pick": False, "prob": 0.6},
        {"contexto": "mapa2+", "azul": False, "primer_pick": True, "prob": 0.5},
        {"contexto": "mapa2+", "azul": False, "primer_pick": False, "prob": 0.3},
        {"contexto": "mapa2+", "azul": True, "primer_pick": True, "prob": 0.1},
        {"contexto": "mapa2+", "azul": True, "primer_pick": False, "prob": 0.1},
    ]
)


# --------------------------------------------------------------------------- modelado
def test_folds_are_temporal_and_exclude_worlds() -> None:
    df = compute_elo(elo_games(), SYNTHETIC_CFG["elo"])
    for year in (2025, 2026):
        train, test = temporal_split(df, SYNTHETIC_CFG, year)
        assert (test["league"] == "WLDs").all() and (test["year"] == year).all()
        assert not (train["league"] == "WLDs").any()
        assert train["date"].max() < test["date"].min()


def test_time_blocks_keep_order_and_cover_train() -> None:
    train = pd.DataFrame({"date": pd.date_range("2026-01-01", periods=100, freq="D"),
                          "gameid": [f"G{i:03d}" for i in range(100)]})  # SINTÉTICO
    core, es, cal = time_blocks(train.sample(frac=1, random_state=0), 0.15, 0.15)
    assert len(core) + len(es) + len(cal) == 100
    assert core["date"].max() < es["date"].min() and es["date"].max() < cal["date"].min()


def test_leakage_alarm_triggers_above_threshold() -> None:
    ok = pd.DataFrame({"model": ["a"], "accuracy": [0.65]})
    check_leakage(ok, 0.72)
    with pytest.raises(LeakageAlarm):
        check_leakage(pd.DataFrame({"model": ["a"], "accuracy": [0.80]}), 0.72)


# --------------------------------------------------------------------------- simulación
def _pmap(p: float) -> dict[tuple[bool, bool], float]:
    return {(b, f): p for b in (True, False) for f in (True, False)}


def test_score_distribution_sums_to_one_and_symmetric_at_half() -> None:
    rules = side_rules(_SIDE, 0.5)
    dist = exact_series(_pmap(0.5), rules)
    assert sum(dist.values()) == pytest.approx(1.0)
    assert set(dist) == {"3-0", "3-1", "3-2", "2-3", "1-3", "0-3"}
    assert series_win(dist) == pytest.approx(0.5)
    # Con p fija, P(3-0) = p^3.
    assert exact_series(_pmap(0.6), rules)["3-0"] == pytest.approx(0.6**3)


def test_exact_matches_binomial_bo5_when_p_constant() -> None:
    p = 0.65
    expected = p**3 * (1 + 3 * (1 - p) + 6 * (1 - p) ** 2)
    assert series_win(exact_series(_pmap(p), side_rules(_SIDE, 0.5))) == pytest.approx(expected)


def test_monte_carlo_agrees_with_exact_when_side_matters() -> None:
    pmap = {(True, True): 0.75, (True, False): 0.68, (False, True): 0.55, (False, False): 0.45}
    rules = side_rules(_SIDE, 0.5)
    exact = series_win(exact_series(pmap, rules))
    mc = series_win(monte_carlo(pmap, rules, 200_000, np.random.default_rng(0)))
    assert mc == pytest.approx(exact, abs=0.005)


def test_loser_choice_is_mirrored_for_the_other_team() -> None:
    """Si el perdedor siempre elige azul, ganar con ventaja de lado alarga las series."""
    always_blue = _SIDE.copy()
    always_blue.loc[always_blue["contexto"] == "mapa2+", "prob"] = [0.0, 0.0, 1.0, 0.0]
    pmap = {(True, True): 0.8, (True, False): 0.8, (False, True): 0.4, (False, False): 0.4}
    dist = exact_series(pmap, side_rules(always_blue, 1.0))
    # Mapa 1: A en azul (0.8). Si A gana, B elige azul -> A juega en rojo (0.4).
    assert dist["3-0"] == pytest.approx(0.8 * 0.4 * 0.4)


def test_hypothetical_map_features_only_use_past_maps() -> None:
    """La fila hipotética ve toda la historia pero sus propios marcadores no afectan a nada previo."""
    games = elo_games()
    hyp = hypothetical_map(games, "Equipo A", "Equipo C", "WLDs", 2026)
    assert set(hyp["gameid"]) == {SIM_GAMEID} and hyp["date"].min() > games["date"].max()
    g = pd.concat([games, hyp], ignore_index=True)
    f = build_features(compute_elo(g, SYNTHETIC_CFG["elo"]), SYNTHETIC_CFG["features"]).set_index("gameid")
    base = build_features(compute_elo(games, SYNTHETIC_CFG["elo"]), SYNTHETIC_CFG["features"]).set_index("gameid")
    cols = [c for c in base.columns if pd.api.types.is_numeric_dtype(base[c])]
    pd.testing.assert_frame_equal(f.loc[base.index, cols], base[cols])
    # Equipo A jugó 4 mapas (incluido el de calentamiento): ventana de 2 llena.
    assert f.loc[SIM_GAMEID, "n_mapas_r2_blue"] == 2


# --------------------------------------------------------------------------- forma del día / Elo dinámico
def test_day_form_zero_sigma_equals_static() -> None:
    from lolpred.simulation import exact_series_day_form

    pmap = {(True, True): 0.7, (True, False): 0.66, (False, True): 0.58, (False, False): 0.55}
    rules = side_rules(_SIDE, 0.5)
    static = exact_series(pmap, rules)
    assert exact_series_day_form(pmap, rules, 0.0) == static


def test_day_form_shrinks_favourite_and_adds_sweeps() -> None:
    """Con forma del día el favorito gana menos series y hay más 3-0/0-3 (lo que mostró el backtest)."""
    from lolpred.simulation import exact_series_day_form

    pmap = {(True, True): 0.7, (True, False): 0.66, (False, True): 0.58, (False, False): 0.55}
    rules = side_rules(_SIDE, 0.5)
    static = exact_series(pmap, rules)
    mixed = exact_series_day_form(pmap, rules, 0.8)
    assert sum(mixed.values()) == pytest.approx(1.0)
    assert 0.5 < series_win(mixed) < series_win(static)
    assert mixed["3-0"] + mixed["0-3"] > static["3-0"] + static["0-3"]


def test_monte_carlo_with_day_form_matches_exact() -> None:
    from lolpred.simulation import exact_series_day_form

    pmap = {(True, True): 0.7, (True, False): 0.66, (False, True): 0.58, (False, False): 0.55}
    rules = side_rules(_SIDE, 0.5)
    exact = exact_series_day_form(pmap, rules, 0.8, n_nodes=20)
    mc = monte_carlo(pmap, rules, 200_000, np.random.default_rng(1), sigma=0.8)
    assert series_win(mc) == pytest.approx(series_win(exact), abs=0.005)
    assert mc["3-0"] == pytest.approx(exact["3-0"], abs=0.005)


def test_dynamic_elo_with_zero_k_equals_static_elo() -> None:
    from lolpred.simulation import exact_series_elo
    from lolpred.verification import elo_pmap

    rules = {"map1": {(True, True): 1.0, (True, False): 0.0, (False, True): 0.0, (False, False): 0.0},
             "loser": {(True, True): 0.3, (True, False): 0.0, (False, True): 0.7, (False, False): 0.0}}
    static = exact_series(elo_pmap(1580, 1500, 30), rules)
    dyn0 = exact_series_elo(80, 30, 0.0, 1.0, 0.3)
    for k in static:
        assert dyn0[k] == pytest.approx(static[k])
    # Con K>0, una victoria sube la probabilidad del siguiente mapa: más barridas.
    dyn = exact_series_elo(80, 30, 64.0, 1.0, 0.3)
    assert dyn["3-0"] + dyn["0-3"] > static["3-0"] + static["0-3"]
