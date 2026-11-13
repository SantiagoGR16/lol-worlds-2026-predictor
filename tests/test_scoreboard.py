"""Pruebas del marcador de la previa con datos SINTÉTICOS (nunca entran a la web)."""

from __future__ import annotations

import pandas as pd
import pytest

from lolpred.scoreboard import map_marginals, map_marginals_day_form, player_averages
from lolpred.simulation import exact_series, exact_series_day_form

# Probabilidades de mapa y reglas de lado sintéticas: (A azul?, A con primer pick?).
PMAP = {(True, True): 0.66, (True, False): 0.62, (False, True): 0.58, (False, False): 0.55}
RULES = {
    "map1": {(True, True): 0.2, (True, False): 0.3, (False, True): 0.3, (False, False): 0.2},
    "loser": {(True, True): 0.13, (True, False): 0.10, (False, True): 0.50, (False, False): 0.27},
}


def _played_from_scores(dist: dict[str, float]) -> list[float]:
    """P(se juega el mapa k) deducida de la distribución de marcadores."""
    n_maps = {k: sum(int(x) for x in k.split("-")) for k in dist}
    return [sum(p for k, p in dist.items() if n_maps[k] >= m) for m in range(1, 6)]


def test_map_marginals_match_exact_series() -> None:
    dist = exact_series(PMAP, RULES)
    marg = map_marginals(PMAP, RULES)
    assert [m["p_played"] for m in marg] == pytest.approx(_played_from_scores(dist))
    # Mapas ganados esperados por A: suma de P(A gana mapa k) = E[victorias de A].
    expected_wins = sum(p * int(k.split("-")[0]) for k, p in dist.items())
    assert sum(m["p_a_win"] for m in marg) == pytest.approx(expected_wins)


def test_day_form_marginals_match_day_form_series() -> None:
    dist = exact_series_day_form(PMAP, RULES, sigma=0.8, n_nodes=12)
    marg = map_marginals_day_form(PMAP, RULES, sigma=0.8, n_nodes=12)
    assert [m["p_played"] for m in marg] == pytest.approx(_played_from_scores(dist))
    assert marg[0]["p_played"] == pytest.approx(1.0)
    assert all(0 <= m["p_a_win_if_played"] <= 1 for m in marg)


def _rows() -> pd.DataFrame:
    """Dos mapas sintéticos de un jugador: 20 y 40 minutos."""
    base = {"playerid": "p1", "playername": "Sintético", "position": "mid", "teamid": "t1",
            "date": pd.to_datetime(["2026-01-01", "2026-01-02"]), "champion": ["X", "Y"],
            "result": [1, 0], "gamelength": [1200, 2400], "kills": [2, 4], "deaths": [1, 2],
            "assists": [3, 3], "teamkills": [10, 10], "damagetochampions": [10000, 20000],
            "totalgold": [8000, 16000], "total cs": [200, 400], "csat15": [120, 140],
            "wardsplaced": [10, 20], "wardskilled": [3, 6], "visionscore": [20, 40]}
    return pd.DataFrame(base)


def test_player_averages_scale_per_minute() -> None:
    r = player_averages(_rows(), ref_minutes=30).iloc[0]
    # 6 kills en 60 minutos -> 3 por mapa de 30 minutos.
    assert r["kills"] == pytest.approx(3.0)
    assert r["dmg"] == pytest.approx(15000)
    assert r["gpm"] == pytest.approx(400)
    assert r["kp"] == pytest.approx(12 / 20)
    assert r["cs15"] == pytest.approx(130)
    assert r["maps"] == 2 and r["wins"] == 1 and bool(r["starter"])
