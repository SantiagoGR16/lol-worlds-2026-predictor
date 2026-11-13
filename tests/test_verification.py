"""Pruebas de la verificación (backtest y Bradley-Terry) con datos SINTÉTICOS."""

from __future__ import annotations

import numpy as np
import pytest
from fixtures.synthetic import bt_maps

from lolpred.verification import bt_design, bt_pmap, bt_predict, elo_pmap, fit_bt


def test_elo_pmap_side_bonus_and_symmetry() -> None:
    p = elo_pmap(1600, 1600, 30)
    assert p[(True, True)] == p[(True, False)] > 0.5 > p[(False, True)] == p[(False, False)]
    assert p[(True, True)] + p[(False, True)] == pytest.approx(1.0)


def test_bt_design_rows_have_plus_minus_one() -> None:
    maps = bt_maps(4)
    teams = sorted(set(maps["teamid_blue"]) | set(maps["teamid_red"]))
    x = bt_design(maps, teams).toarray()
    assert x.shape == (len(maps), len(teams) + 1)
    assert np.allclose(x[:, :-1].sum(axis=1), 0)  # +1 azul, -1 rojo
    assert set(np.unique(x[:, -1])) == {-1.0, 1.0}


def test_bt_recovers_strength_order() -> None:
    m = fit_bt(bt_maps(60), half_life=0, c=10.0)
    s = m["strength"]
    assert s["syn:A"] > s["syn:B"] > s["syn:C"] > s["syn:D"]
    assert m["blue"] > 0


def test_bt_pmap_is_consistent_with_predict() -> None:
    """P(A gana) con A azul + FP coincide con predict en un mapa A(azul, FP) vs B."""
    import pandas as pd

    m = fit_bt(bt_maps(30), half_life=0, c=1.0)
    row = pd.DataFrame({"teamid_blue": ["syn:A"], "teamid_red": ["syn:B"], "blue_first_pick": [1]})
    assert bt_pmap(m, "syn:A", "syn:B")[(True, True)] == pytest.approx(float(bt_predict(m, row)[0]))
    row_red = pd.DataFrame({"teamid_blue": ["syn:B"], "teamid_red": ["syn:A"], "blue_first_pick": [1]})
    # A en rojo y SIN primer pick (lo tiene el azul B).
    assert bt_pmap(m, "syn:A", "syn:B")[(False, False)] == pytest.approx(1 - float(bt_predict(m, row_red)[0]))


def test_series_recalibration_recovers_slope_and_ignores_eval_worlds() -> None:
    from fixtures.synthetic import SYNTHETIC_CFG, backtest_rows

    from lolpred.verification import fit_series_recalibration

    cfg = {**SYNTHETIC_CFG, "verification": {"recal_n_bootstrap": 50}}
    recal = fit_series_recalibration(backtest_rows(), cfg, np.random.default_rng(0))
    full = recal[recal["muestra"] == -1].iloc[0]
    # Las 20 series "WLDs 2026" (p=0.99 y todas perdidas) habrían hundido la pendiente.
    assert full["n_series"] == 3000
    assert full["b"] == pytest.approx(0.5, abs=0.12)
    assert full["a"] == pytest.approx(0.0, abs=0.1)
    assert len(recal) == 51


def test_rescale_scores_keeps_shape_and_hits_target() -> None:
    from lolpred.simulation import recalibrate, rescale_scores

    dist = {"3-0": 0.25, "3-1": 0.27, "3-2": 0.2, "2-3": 0.12, "1-3": 0.1, "0-3": 0.06}  # SINTÉTICO
    out = rescale_scores(dist, 0.6)
    assert sum(out.values()) == pytest.approx(1.0)
    assert out["3-0"] + out["3-1"] + out["3-2"] == pytest.approx(0.6)
    assert out["3-0"] / out["3-1"] == pytest.approx(dist["3-0"] / dist["3-1"])
    # Recalibración identidad (a=0, b=1) no cambia nada; b<1 acerca a 0.5.
    assert float(recalibrate(0.7, 0.0, 1.0)) == pytest.approx(0.7)
    assert 0.5 < float(recalibrate(0.7, 0.0, 0.6)) < 0.7


def test_cluster_se_matches_naive_with_singletons_and_grows_with_clusters() -> None:
    from lolpred.verification import _cluster_se

    rng = np.random.default_rng(3)
    r = rng.normal(size=400)  # SINTÉTICO
    naive = r.std(ddof=0) / np.sqrt(len(r))
    assert _cluster_se(r, np.arange(400)) == pytest.approx(naive, rel=1e-9)
    # Residuos idénticos dentro de cada grupo (correlación perfecta): el SE robusto crece.
    shared = np.repeat(rng.normal(size=100), 4)
    groups = np.repeat(np.arange(100), 4)
    assert _cluster_se(shared, groups) > shared.std() / np.sqrt(len(shared)) * 1.5
