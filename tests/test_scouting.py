"""Pruebas del scouting con datos SINTÉTICOS (tests/fixtures; nunca entran a la web)."""

from __future__ import annotations

import pandas as pd
import pytest
from fixtures.synthetic import scouting_player_rows, scouting_team_rows

from lolpred.scouting import (
    aggregate_players,
    bans_against,
    bans_by,
    mvp_scores,
    pick_probabilities,
    player_map_stats,
    presence,
)


def _agg() -> pd.DataFrame:
    return aggregate_players(player_map_stats(scouting_player_rows(), scouting_team_rows()))


def test_kp_between_0_and_1() -> None:
    pm = player_map_stats(scouting_player_rows(), scouting_team_rows())
    assert pm["kp_map"].between(0, 1).all()
    assert _agg()["kp"].between(0, 1).all()


def test_opponent_weight_has_mean_one() -> None:
    pm = player_map_stats(scouting_player_rows(), scouting_team_rows())
    assert pm["weight"].mean() == pytest.approx(1.0)


def test_mvp_z_scores_are_centered_within_role() -> None:
    scored = mvp_scores(_agg(), ["kda", "dpm"], min_maps=1)
    for _, g in scored.groupby("role"):
        assert g["z_kda"].mean() == pytest.approx(0.0, abs=1e-9)


def test_pick_probabilities_sum_at_most_one() -> None:
    players = scouting_player_rows()
    ev = players[players["gameid"] == "M1"]  # "Mundial" sintético: X vs Y (Z no juega)
    prior = players  # "todo el año" sintético
    p = pick_probabilities(ev, prior, players["playerid"].unique().tolist(), prior_weight=0.3)
    sums = p.groupby("playerid")["p"].sum()
    assert (sums <= 1 + 1e-9).all()
    assert (p["p"] >= 0).all()
    # Los jugadores de Z no tienen mapas en el "Mundial": solo reciben el peso del prior (0.3).
    assert sums[sums.index.str.startswith("syn:z_")].tolist() == pytest.approx([0.3, 0.3])
    assert sums[~sums.index.str.startswith("syn:z_")].tolist() == pytest.approx([1.0] * 4)


def test_bans_against_are_rival_bans() -> None:
    teams = scouting_team_rows()
    against_x = bans_against(teams, "Equipo X").set_index("champion")
    # X jugó M1 (rival Y) y M2 (rival Z): los bans en contra son los de Y en M1 y Z en M2.
    expected = set(teams[(teams["gameid"] == "M1") & (teams["teamname"] == "Equipo Y")][["ban1", "ban2", "ban3", "ban4", "ban5"]].iloc[0]) \
        | set(teams[(teams["gameid"] == "M2") & (teams["teamname"] == "Equipo Z")][["ban1", "ban2", "ban3", "ban4", "ban5"]].iloc[0])
    assert set(against_x.index) == expected
    # Akali la banean Y (M1) y Z (M2): 2 de 2 mapas.
    assert against_x.loc["Akali", "rate"] == pytest.approx(1.0)
    # Nunca aparecen los bans propios de X que el rival no hizo.
    own_only = set(bans_by(teams, "Equipo X")["champion"]) - expected
    assert own_only.isdisjoint(against_x.index)


def test_presence_counts_picks_and_bans_once_per_map() -> None:
    pres = presence(scouting_team_rows(), scouting_player_rows()).set_index("champion")
    assert (pres["presence"] <= 1).all()
    # Akali: elegida por x_mid en M1 y baneada en M1 (Y), M2 (Z) y M3 (Z) -> 3 de 3 mapas.
    assert pres.loc["Akali", "presence"] == pytest.approx(1.0)


def test_prior_patch_set_adds_previous_patches_in_numeric_order() -> None:
    """Parches como texto: 16.16 es anterior a 16.17 y 16.2 (enero) no se confunde con 16.20."""
    from lolpred.scouting import prior_patch_set

    all_p = ["16.2", "16.9", "16.15", "16.16", "16.17", "16.20"]  # SINTÉTICO
    assert prior_patch_set(all_p, ["16.17", "16.20"], 0) == ["16.17", "16.20"]
    assert prior_patch_set(all_p, ["16.17", "16.20"], 1) == ["16.16", "16.17", "16.20"]
    assert prior_patch_set(all_p, ["16.17", "16.20"], 2) == ["16.15", "16.16", "16.17", "16.20"]
