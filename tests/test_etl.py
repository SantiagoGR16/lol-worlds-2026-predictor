"""Pruebas del ETL con datos SINTÉTICOS (tests/fixtures; nunca entran al pipeline)."""

from __future__ import annotations

from fixtures.synthetic import etl_rows, warmup_raw

from lolpred.etl import filter_team_rows, parse_and_sort, select_rows, validate_games


def test_filter_keeps_only_team_rows_of_selected_leagues_and_years() -> None:
    out = filter_team_rows(etl_rows(), ["LCK"], [2025, 2026])
    assert set(out["position"]) == {"team"}
    assert set(out["league"]) == {"LCK"}
    # G5 está etiquetada como temporada 2027 y debe quedar fuera.
    assert "G5" not in set(out["gameid"])


def test_sort_is_temporal_and_blue_first() -> None:
    out = parse_and_sort(filter_team_rows(etl_rows(), ["LCK"], [2026]))
    assert out["date"].is_monotonic_increasing
    assert list(out.loc[out["gameid"] == "G1", "side"]) == ["Blue", "Red"]


def test_validate_drops_incomplete_games() -> None:
    out = validate_games(parse_and_sort(filter_team_rows(etl_rows(), ["LCK"], [2026])))
    assert set(out["gameid"]) == {"G1", "G2"}
    assert (out.groupby("gameid").size() == 2).all()


def test_select_rows_marks_warmup_by_file_not_by_season() -> None:
    """Filas del archivo de calentamiento se marcan is_warmup aunque su 'year' sea de un año modelado."""
    dcfg = {"years": [2025], "leagues": ["LCK"], "warmup_years": [2024], "warmup_leagues": ["LCK", "PCS"]}
    out = select_rows(warmup_raw(), dcfg).set_index("gameid")
    assert set(out.index) == {"W1", "W2", "M1"}
    assert out.loc["W1", "is_warmup"] and out.loc["W2", "is_warmup"]
    assert not out.loc["M1", "is_warmup"]
