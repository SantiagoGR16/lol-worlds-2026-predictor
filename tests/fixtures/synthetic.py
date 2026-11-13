"""DATOS SINTÉTICOS, solo para tests.

Nada de este módulo es real ni debe entrar al pipeline ni a la web.
Los equipos, ligas y resultados son inventados para probar la lógica.
"""

from __future__ import annotations

import pandas as pd

# Config mínima SINTÉTICA para los tests (mismas claves que config.yaml).
SYNTHETIC_CFG: dict = {
    "data": {"eval_league": "WLDs"},
    "elo": {
        "initial": 1500,
        "k": 32,
        "season_regression": 0.75,
        "international_leagues": ["MSI", "WLDs"],
        "k_international": 1.5,
        "blue_bonus": 15,
    },
    "modeling": {"eval_year": 2026},
    "features": {
        "windows": [2, 3],
        "stats": ["result", "golddiffat15", "firsttower", "gamelength", "kills_pm"],
        "stats_at15": ["golddiffat15"],
    },
}


def etl_rows() -> pd.DataFrame:
    """SINTÉTICO: filas crudas para el ETL; G3 está incompleta y G4 es de una liga no pedida."""
    rows = []
    for gid, date in [("G2", "2026-01-02"), ("G1", "2026-01-01")]:
        for side in ("Red", "Blue"):
            rows.append({"gameid": gid, "date": date, "side": side, "position": "team", "league": "LCK", "year": 2026})
        rows.append({"gameid": gid, "date": date, "side": "Blue", "position": "top", "league": "LCK", "year": 2026})
    rows.append({"gameid": "G3", "date": "2026-01-03", "side": "Blue", "position": "team", "league": "LCK", "year": 2026})
    for side in ("Blue", "Red"):
        rows.append({"gameid": "G4", "date": "2026-01-03", "side": side, "position": "team", "league": "LJL", "year": 2026})
    for side in ("Blue", "Red"):
        rows.append({"gameid": "G5", "date": "2026-10-05", "side": side, "position": "team", "league": "LCK", "year": 2027})
    return pd.DataFrame(rows)


# SINTÉTICO: (fecha, liga, año temporada, equipo azul, equipo rojo, gana azul)
_MAPS = [
    ("2025-01-10", "LCK", 2025, "A", "B", 1),
    ("2025-01-11", "LPL", 2025, "C", "D", 0),
    ("2025-01-12", "LCK", 2025, "A", "B", 1),
    ("2025-05-01", "MSI", 2025, "A", "C", 0),
    ("2025-10-01", "WLDs", 2025, "B", "D", 1),
    ("2026-01-15", "LCK", 2026, "B", "A", 0),
    ("2026-02-01", "LPL", 2026, "D", "C", 1),
    ("2026-03-01", "LCK", 2026, "A", "E", 1),
    ("2026-10-01", "WLDs", 2026, "A", "C", 1),
    ("2026-10-02", "WLDs", 2026, "D", "B", 0),
]


def elo_games() -> pd.DataFrame:
    """SINTÉTICO: tabla de mapas con el formato de games.parquet (2 filas por gameid).

    Las stats son números inventados y deterministas. El mapa SYN002 simula una
    partida 'partial' (golddiffat15 = NaN en ambos lados).
    """
    rows = []
    for n, (date, league, year, blue, red, blue_win) in enumerate(_MAPS):
        gid = f"SYN{n:03d}"
        gd = float(500 + 100 * n)  # oro a favor del azul al minuto 15 (inventado)
        for side, team, res, sign in (("Blue", blue, blue_win, 1), ("Red", red, 1 - blue_win, -1)):
            rows.append(
                {
                    "gameid": gid,
                    "date": pd.Timestamp(date),
                    "league": league,
                    "year": year,
                    "side": side,
                    "teamid": f"syn:{team}",
                    "teamname": f"Equipo {team}",
                    "result": res,
                    "golddiffat15": float("nan") if gid == "SYN002" else sign * gd,
                    "firsttower": res,
                    "gamelength": 1800 + 60 * n,
                    "kills": 10 + n + 5 * res,
                    "deaths": 12 + n - 5 * res,
                    "datacompleteness": "partial" if gid == "SYN002" else "complete",
                    # Primer pick inventado: alterna entre azul y rojo según el mapa.
                    "firstPick": int((side == "Blue") == (n % 2 == 0)),
                    # SYN000 simula una fila de calentamiento (solo historia, nunca una fila del modelo).
                    "is_warmup": gid == "SYN000",
                }
            )
    return pd.DataFrame(rows)


def series_feats() -> pd.DataFrame:
    """SINTÉTICO: dos series Bo3 SIMULTÁNEAS (A-B y C-D) con mapas intercalados en el tiempo.

    Sirve de regresión para el bug del contador global de series.
    A-B: A gana m1 (A azul), B gana m2 (B azul), A gana m3 (A azul)   -> Bo3 2-1
    C-D: C gana m1 (C azul), C gana m2 (D azul)                        -> Bo3 2-0
    """
    rows = [
        ("S1", "2026-03-01 10:00", 1, "A", "B", 1, 1),
        ("S2", "2026-03-01 10:30", 1, "C", "D", 1, 0),
        ("S3", "2026-03-01 11:00", 2, "B", "A", 1, 0),
        ("S4", "2026-03-01 11:30", 2, "D", "C", 0, 0),
        ("S5", "2026-03-01 12:00", 3, "A", "B", 1, 1),
    ]
    return pd.DataFrame(
        [
            {"gameid": g, "date": pd.Timestamp(d), "game": n, "teamid_blue": f"syn:{b}",
             "teamid_red": f"syn:{r}", "target": t, "blue_first_pick": fp, "year": 2026, "league": "LCK"}
            for g, d, n, b, r, t, fp in rows
        ]
    )


def warmup_raw() -> pd.DataFrame:
    """SINTÉTICO: filas crudas de dos archivos (2024 = calentamiento, 2025 = modelo).

    W2 viene del archivo de 2024 pero está etiquetada como temporada 2025.
    """
    return pd.DataFrame(
        [
            {"gameid": "W1", "position": "team", "league": "PCS", "year": 2024, "source_year": 2024},
            {"gameid": "W2", "position": "team", "league": "LCK", "year": 2025, "source_year": 2024},
            {"gameid": "W3", "position": "team", "league": "LJL", "year": 2024, "source_year": 2024},
            {"gameid": "M1", "position": "team", "league": "LCK", "year": 2025, "source_year": 2025},
            {"gameid": "M2", "position": "team", "league": "PCS", "year": 2025, "source_year": 2025},
        ]
    )


# ---------------------------------------------------------------------------
# Scouting (SINTÉTICO): 3 equipos inventados X, Y, Z; 2 jugadores por equipo
# (mid y bot) para mantenerlo pequeño. Mapas: M1 = X vs Y, M2 = X vs Z, M3 = Y vs Z.
# ---------------------------------------------------------------------------
_SC_MAPS = [("M1", "X", "Y"), ("M2", "X", "Z"), ("M3", "Y", "Z")]
# Bans inventados por (mapa, equipo).
_SC_BANS = {
    ("M1", "X"): ["Ahri", "Azir", "Jinx", "Ezreal", "Orianna"],
    ("M1", "Y"): ["Akali", "Corki", "Varus", "Sylas", "Kaisa"],
    ("M2", "X"): ["Ahri", "Taliyah", "Jinx", "Zeri", "Viktor"],
    ("M2", "Z"): ["Akali", "Lucian", "Xayah", "Rumble", "Yone"],
    ("M3", "Y"): ["Ahri", "Azir", "Jinx", "Ezreal", "Orianna"],
    ("M3", "Z"): ["Corki", "Varus", "Sylas", "Kaisa", "Akali"],
}
# Campeón inventado por (mapa, jugador).
_SC_CHAMPS = {
    "x_mid": ["Akali", "Corki"], "x_bot": ["Kaisa", "Varus"],
    "y_mid": ["Azir", "Ahri"], "y_bot": ["Jinx", "Ezreal"],
    "z_mid": ["Orianna", "Taliyah"], "z_bot": ["Zeri", "Xayah"],
}


def scouting_team_rows() -> pd.DataFrame:
    """SINTÉTICO: filas de equipo con bans y Elo previo del rival."""
    rows = []
    for gid, a, b in _SC_MAPS:
        for side, team, opp in (("Blue", a, b), ("Red", b, a)):
            bans = dict(zip(["ban1", "ban2", "ban3", "ban4", "ban5"], _SC_BANS[(gid, team)]))
            rows.append({"gameid": gid, "side": side, "teamid": f"syn:{team}", "teamname": f"Equipo {team}",
                         "elo_opp_pre": {"X": 1600.0, "Y": 1500.0, "Z": 1400.0}[opp], **bans})
    return pd.DataFrame(rows)


def scouting_player_rows() -> pd.DataFrame:
    """SINTÉTICO: filas de jugador; K+A <= kills del equipo en cada mapa."""
    rows = []
    used: dict[str, int] = {}
    for n, (gid, a, b) in enumerate(_SC_MAPS):
        for team in (a, b):
            kills = {"mid": 3 + n, "bot": 4}
            teamkills = sum(kills.values()) + 1  # +1: kill de otro jugador (no modelado)
            for role in ("mid", "bot"):
                pid = f"{team.lower()}_{role}"
                i = used.get(pid, 0)
                used[pid] = i + 1
                rows.append({
                    "gameid": gid, "playerid": f"syn:{pid}", "playername": pid.upper(), "teamid": f"syn:{team}",
                    "teamname": f"Equipo {team}", "position": role, "champion": _SC_CHAMPS[pid][i % 2],
                    "kills": kills[role], "deaths": 2 + n, "assists": teamkills - kills[role] - 1,
                    "teamkills": teamkills, "dpm": 500.0 + 50 * n, "golddiffat15": 100.0 * (n - 1),
                    "csdiffat15": 5.0, "damageshare": 0.25, "earnedgoldshare": 0.22, "vspm": 1.1,
                })
    return pd.DataFrame(rows)


def bt_maps(n_per_pair: int = 40, seed: int = 0) -> pd.DataFrame:
    """SINTÉTICO: mapas entre 4 equipos inventados con fuerzas conocidas (A > B > C > D).

    Los resultados se sortean con un Bradley-Terry verdadero (ventaja azul 0.2, sin efecto
    del primer pick) para comprobar que el ajuste recupera el orden de fuerzas.
    """
    import numpy as np

    rng = np.random.default_rng(seed)
    strength = {"syn:A": 1.0, "syn:B": 0.4, "syn:C": -0.2, "syn:D": -1.2}
    teams = list(strength)
    rows = []
    day = 0
    for i, a in enumerate(teams):
        for b in teams[i + 1:]:
            for k in range(n_per_pair):
                blue, red = (a, b) if k % 2 == 0 else (b, a)
                p = 1 / (1 + np.exp(-(0.2 + strength[blue] - strength[red])))
                rows.append({"gameid": f"BT{day:04d}", "date": pd.Timestamp("2026-01-01") + pd.Timedelta(days=day),
                             "teamid_blue": blue, "teamid_red": red, "blue_first_pick": int(k % 3 == 0),
                             "target": int(rng.random() < p)})
                day += 1
    return pd.DataFrame(rows)


def backtest_rows(n: int = 3000, true_a: float = 0.0, true_b: float = 0.5, seed: int = 1) -> pd.DataFrame:
    """SINTÉTICO: backtest de series con un simulador sobreconfiado conocido.

    El resultado real se sortea con sigmoide(true_a + true_b·logit(p_a)): la recalibración
    debe recuperar (true_a, true_b). Incluye 20 series del "Mundial de evaluación" (WLDs
    2026) que NO deben entrar al ajuste.
    """
    import numpy as np

    rng = np.random.default_rng(seed)
    p = rng.uniform(0.15, 0.85, n)
    logit = np.log(p / (1 - p))
    y = (rng.random(n) < 1 / (1 + np.exp(-(true_a + true_b * logit)))).astype(int)
    dates = pd.Timestamp("2025-01-01") + pd.to_timedelta(np.arange(n) % 600, unit="D")
    df = pd.DataFrame({"p_a": p, "a_gana": y, "date": dates, "league": "LCK", "year": 2025})
    ev = pd.DataFrame({"p_a": [0.99] * 20, "a_gana": [0] * 20, "date": pd.Timestamp("2026-10-01"),
                       "league": "WLDs", "year": 2026})
    return pd.concat([df, ev], ignore_index=True)
