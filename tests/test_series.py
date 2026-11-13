"""Pruebas de la reconstrucción de series con datos SINTÉTICOS (tests/fixtures)."""

from __future__ import annotations

from fixtures.synthetic import SYNTHETIC_CFG, series_feats

from lolpred.series import build_series, side_choice


def test_concurrent_series_are_not_mixed() -> None:
    """Dos series simultáneas quedan separadas (regresión del contador global)."""
    s = build_series(series_feats()).set_index("gameid")
    assert s.loc["S1", "serie"] == s.loc["S3", "serie"] == s.loc["S5", "serie"]
    assert s.loc["S2", "serie"] == s.loc["S4", "serie"]
    assert s.loc["S1", "serie"] != s.loc["S2", "serie"]
    assert set(s["formato"]) == {"Bo3"}
    # El ganador previo de S3 es A (ganó S1), no C (que ganó S2, en la otra serie).
    assert s.loc["S3", "ganador_prev"] == "syn:A"


def test_side_choice_counts_loser_side_and_first_pick() -> None:
    """Mapas 2+: S3 perdedor B en azul sin FP; S4 perdedor D en azul sin FP; S5 perdedor A en azul con FP."""
    out = side_choice(build_series(series_feats()), SYNTHETIC_CFG)
    m2 = out[out["contexto"] == "mapa2+"].set_index(["azul", "primer_pick"])["prob"]
    assert m2.loc[(True, False)] == 2 / 3
    assert m2.loc[(True, True)] == 1 / 3
    m1 = out[(out["contexto"] == "mapa1") & out["primer_pick"]]["prob"].iloc[0]
    assert m1 == 0.5  # S1 azul con FP, S2 azul sin FP
