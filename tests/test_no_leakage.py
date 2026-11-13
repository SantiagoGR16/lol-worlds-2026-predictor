"""Pruebas anti-leakage con datos SINTÉTICOS (tests/fixtures)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fixtures.synthetic import SYNTHETIC_CFG, elo_games

from lolpred.elo import compute_elo
from lolpred.features import build_features
from lolpred.modeling import temporal_split


@pytest.mark.parametrize("target", ["SYN000", "SYN003", "SYN005", "SYN009"])
def test_flipping_result_does_not_change_own_elo_pre(target: str) -> None:
    """Cambiar el resultado de un mapa no altera su propio elo_pre ni el de mapas anteriores."""
    base = compute_elo(elo_games(), SYNTHETIC_CFG["elo"])

    flipped_in = elo_games()
    mask = flipped_in["gameid"] == target
    flipped_in.loc[mask, "result"] = 1 - flipped_in.loc[mask, "result"]
    flipped = compute_elo(flipped_in, SYNTHETIC_CFG["elo"])

    target_date = base.loc[base["gameid"] == target, "date"].iloc[0]
    upto = base["date"] <= target_date
    np.testing.assert_allclose(base.loc[upto, "elo_pre"], flipped.loc[upto, "elo_pre"])
    np.testing.assert_allclose(base.loc[upto, "elo_prob"], flipped.loc[upto, "elo_prob"])

    # Control: si el mapa no es el último, el cambio sí debe propagarse hacia adelante.
    if (~upto).any():
        assert not np.allclose(base.loc[~upto, "elo_pre"], flipped.loc[~upto, "elo_pre"])


def test_first_map_elo_pre_is_initial() -> None:
    """El elo_pre de cada equipo en su primer mapa es el Elo inicial."""
    out = compute_elo(elo_games(), SYNTHETIC_CFG["elo"])
    first = out.groupby("teamid").head(1)
    assert (first["elo_pre"] == SYNTHETIC_CFG["elo"]["initial"]).all()


def test_elo_pair_is_consistent() -> None:
    """elo_opp_pre es el elo_pre del rival y las probabilidades del mapa suman 1."""
    out = compute_elo(elo_games(), SYNTHETIC_CFG["elo"])
    for _, g in out.groupby("gameid"):
        assert g["elo_pre"].iloc[0] == g["elo_opp_pre"].iloc[1]
        assert g["elo_prob"].sum() == pytest.approx(1.0)


def test_eval_league_never_in_train() -> None:
    """Ninguna fila del Mundial (de ningún año) entra al train, y el test es posterior al train."""
    df = compute_elo(elo_games(), SYNTHETIC_CFG["elo"])
    train, test = temporal_split(df, SYNTHETIC_CFG)
    eval_league = SYNTHETIC_CFG["data"]["eval_league"]
    assert not (train["league"] == eval_league).any()
    assert (test["league"] == eval_league).all()
    assert train["date"].max() < test["date"].min()
    assert len(train) > 0 and len(test) > 0


# ---------------------------------------------------------------------------
# Features (rolling con shift(1)) — datos SINTÉTICOS
# ---------------------------------------------------------------------------

def _features_of(games: pd.DataFrame) -> pd.DataFrame:
    ge = compute_elo(games, SYNTHETIC_CFG["elo"])
    return build_features(ge, SYNTHETIC_CFG["features"]).set_index("gameid")


@pytest.mark.parametrize("target", ["SYN001", "SYN003", "SYN007"])
def test_changing_map_stats_does_not_change_own_or_past_features(target: str) -> None:
    """Cambiar las stats (y el resultado) de un mapa no altera sus features ni las de mapas anteriores."""
    games = elo_games()
    base = _features_of(games)

    tampered = games.copy()
    m = tampered["gameid"] == target
    tampered.loc[m, "golddiffat15"] = tampered.loc[m, "golddiffat15"] * -50 + 12345
    tampered.loc[m, "gamelength"] = 4000
    tampered.loc[m, "kills"] = 99
    tampered.loc[m, "deaths"] = 0
    tampered.loc[m, "firsttower"] = 1 - tampered.loc[m, "firsttower"]
    tampered.loc[m, "result"] = 1 - tampered.loc[m, "result"]
    changed = _features_of(tampered)

    feat_cols = [c for c in base.columns if c not in ("target",) and pd.api.types.is_numeric_dtype(base[c])]
    upto = base.index[base["date"] <= base.loc[target, "date"]]
    pd.testing.assert_frame_equal(base.loc[upto, feat_cols], changed.loc[upto, feat_cols])

    # Control: algún mapa posterior de esos equipos sí debe cambiar.
    later = base.index[base["date"] > base.loc[target, "date"]]
    if len(later):
        assert not base.loc[later, feat_cols].equals(changed.loc[later, feat_cols])


def test_first_map_features_are_nan_and_counts_zero() -> None:
    """En el primer mapa de un equipo no hay historia: rolling NaN y contadores en 0."""
    f = _features_of(elo_games())
    first = f.loc["SYN001"]  # primer mapa de C y D
    assert np.isnan(first["result_r2_blue"]) and np.isnan(first["result_r2_red"])
    assert first["n_mapas_r2_blue"] == 0 and first["n_validos15_r2_blue"] == 0
    assert np.isnan(first["dias_desde_ultimo_blue"])


def test_warmup_is_history_but_never_a_row() -> None:
    """El mapa de calentamiento (SYN000) no es fila de features ni de train/test, pero sí historia."""
    f = _features_of(elo_games())
    assert "SYN000" not in f.index
    # SYN002 (A vs B) ve SYN000 como mapa previo de ambos equipos.
    assert f.loc["SYN002", "n_mapas_r2_blue"] == 1
    df = compute_elo(elo_games(), SYNTHETIC_CFG["elo"])
    train, test = temporal_split(df, SYNTHETIC_CFG)
    assert not train["is_warmup"].any() and not test["is_warmup"].any()


def test_first_pick_feature_matches_blue_row() -> None:
    """blue_first_pick es el firstPick de la fila azul (decidido antes del draft)."""
    f = _features_of(elo_games())
    raw = elo_games()
    fp = raw[raw["side"] == "Blue"].set_index("gameid")["firstPick"]
    assert (f["blue_first_pick"] == fp.loc[f.index]).all()


def test_partial_map_is_not_filled_and_not_counted() -> None:
    """El mapa 'partial' (SYN002, A vs B) no cuenta como válido @15 en el siguiente mapa de A."""
    f = _features_of(elo_games())
    # SYN003 (A azul): A jugó SYN000 (calentamiento, válido) y SYN002 (partial) antes.
    row = f.loc["SYN003"]
    assert row["n_mapas_r2_blue"] == 2
    assert row["n_validos15_r2_blue"] == 1
    # La media @15 solo usa SYN000: +500 de oro para A (azul en SYN000).
    assert row["golddiffat15_r2_blue"] == pytest.approx(500.0)


def test_target_is_blue_result() -> None:
    f = _features_of(elo_games())
    raw = elo_games()
    blue = raw[raw["side"] == "Blue"].set_index("gameid")["result"]
    assert (f["target"] == blue.loc[f.index]).all()
