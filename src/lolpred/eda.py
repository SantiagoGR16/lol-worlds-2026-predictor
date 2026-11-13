"""Análisis exploratorio (EDA) sobre los parquet procesados y las filas de jugadores.

Genera gráficos PNG en ``reports/eda/`` e imprime las cifras clave. No modifica
ningún dato del pipeline. El Mundial 2026 aparece solo como descripción (cuántos
mapas, historial previo de cada equipo); no se usa para elegir nada.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # sin ventana: solo archivos
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from lolpred.etl import PROJECT_ROOT, load_config  # noqa: E402
from lolpred.series import build_series  # noqa: E402

logger = logging.getLogger(__name__)

# Paleta (instancia de referencia de la guía de visualización, modo claro).
C_BLUE = "#2a78d6"
C_RED = "#e34948"
C_ACCENT = "#1baf7a"
C_TEXT = "#0b0b0b"
C_TEXT2 = "#52514e"
C_GRID = "#e4e3df"
C_SURF = "#fcfcfb"
SEQ = "Blues"


def _style() -> None:
    """Estilo común: ejes y rejilla discretos, texto en tinta neutra."""
    plt.rcParams.update(
        {
            "figure.facecolor": C_SURF,
            "axes.facecolor": C_SURF,
            "axes.edgecolor": C_GRID,
            "axes.labelcolor": C_TEXT2,
            "axes.titlecolor": C_TEXT,
            "axes.titlesize": 12,
            "axes.titleweight": "bold",
            "axes.grid": True,
            "grid.color": C_GRID,
            "grid.linewidth": 0.8,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "xtick.color": C_TEXT2,
            "ytick.color": C_TEXT2,
            "font.size": 10,
            "legend.frameon": False,
        }
    )


def _save(fig: plt.Figure, out_dir: Path, name: str) -> None:
    fig.tight_layout()
    fig.savefig(out_dir / name, dpi=150)
    plt.close(fig)
    logger.info("Gráfico: %s", out_dir / name)


def _wilson(k: float, n: float, z: float = 1.96) -> tuple[float, float]:
    """Intervalo de Wilson al 95 % para una proporción."""
    if n == 0:
        return (np.nan, np.nan)
    p = k / n
    den = 1 + z**2 / n
    c = (p + z**2 / (2 * n)) / den
    h = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / den
    return (c - h, c + h)


# ---------------------------------------------------------------------------
# 1. Lado azul
# ---------------------------------------------------------------------------
def blue_side(feats: pd.DataFrame, out_dir: Path) -> pd.DataFrame:
    """Winrate del lado azul por liga (ambos años juntos) con IC 95 %."""
    rows = []
    for lg, s in feats.groupby("league"):
        lo, hi = _wilson(s["target"].sum(), len(s))
        rows.append({"league": lg, "mapas": len(s), "wr_azul": s["target"].mean(), "lo": lo, "hi": hi})
    lo, hi = _wilson(feats["target"].sum(), len(feats))
    rows.append({"league": "TODAS", "mapas": len(feats), "wr_azul": feats["target"].mean(), "lo": lo, "hi": hi})
    t = pd.DataFrame(rows).sort_values("wr_azul")

    fig, ax = plt.subplots(figsize=(7, 4.2))
    y = np.arange(len(t))
    colors = [C_TEXT2 if lg == "TODAS" else C_BLUE for lg in t["league"]]
    ax.hlines(y, t["lo"], t["hi"], color=colors, linewidth=2)
    ax.scatter(t["wr_azul"], y, color=colors, s=40, zorder=3)
    ax.axvline(0.5, color=C_TEXT2, linewidth=1, linestyle="--")
    ax.set_yticks(y, [f"{lg}  (n={n})" for lg, n in zip(t["league"], t["mapas"])])
    ax.set_xlabel("Winrate del lado azul (IC 95 %)")
    ax.set_title("El lado azul gana más de la mitad de los mapas")
    ax.grid(axis="y", visible=False)
    _save(fig, out_dir, "01_lado_azul_por_liga.png")
    return t


# ---------------------------------------------------------------------------
# 2. Completitud de datos
# ---------------------------------------------------------------------------
def completeness(games: pd.DataFrame, out_dir: Path) -> pd.DataFrame:
    """Proporción de mapas 'partial' por liga y trimestre."""
    g = games[games["side"] == "Blue"].copy()
    g["trimestre"] = g["date"].dt.to_period("Q").astype(str)
    t = g.assign(partial=g["datacompleteness"].eq("partial")).pivot_table(
        index="league", columns="trimestre", values="partial", aggfunc="mean"
    )
    fig, ax = plt.subplots(figsize=(8, 3.8))
    im = ax.imshow(t.to_numpy(dtype=float), cmap=SEQ, vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(t.shape[1]), t.columns, rotation=45, ha="right")
    ax.set_yticks(range(t.shape[0]), t.index)
    for i in range(t.shape[0]):
        for j in range(t.shape[1]):
            v = t.iat[i, j]
            if pd.notna(v):
                ax.text(j, i, f"{v:.0%}", ha="center", va="center", fontsize=8,
                        color="white" if v > 0.55 else C_TEXT)
    ax.grid(False)
    ax.set_title("Mapas con datos parciales (sin stats @15) por liga y trimestre")
    fig.colorbar(im, ax=ax, fraction=0.025, format=matplotlib.ticker.PercentFormatter(1.0))
    _save(fig, out_dir, "02_datos_parciales.png")
    return t


# ---------------------------------------------------------------------------
# 3. Calibración del Elo
# ---------------------------------------------------------------------------
def _logloss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def elo_calibration(feats: pd.DataFrame, cfg: dict[str, Any], out_dir: Path) -> pd.DataFrame:
    """Curva de fiabilidad del elo_prob (fila azul) fuera del Mundial y en el Mundial 2025."""
    eval_league = cfg["data"]["eval_league"]
    eval_year = int(cfg["modeling"]["eval_year"])
    # Se excluyen los primeros mapas de cada equipo, donde el Elo aún no tiene información.
    warm = feats[(feats["n_mapas_r20_blue"] >= 10) & (feats["n_mapas_r20_red"] >= 10)]
    sets = {
        "Ligas (sin Mundial)": warm[warm["league"] != eval_league],
        f"{eval_league} 2025": feats[(feats["league"] == eval_league) & (feats["year"] != eval_year)],
    }
    bins = np.linspace(0, 1, 11)
    fig, ax = plt.subplots(figsize=(5.2, 5))
    ax.plot([0, 1], [0, 1], color=C_TEXT2, linestyle="--", linewidth=1)
    rows = []
    for (name, s), color in zip(sets.items(), [C_BLUE, C_RED]):
        idx = np.digitize(s["elo_prob"], bins) - 1
        cal = s.groupby(idx).agg(p=("elo_prob", "mean"), y=("target", "mean"), n=("target", "size"))
        cal = cal[cal["n"] >= 10]
        ax.plot(cal["p"], cal["y"], marker="o", color=color, linewidth=2, markersize=6, label=name)
        rows.append({
            "conjunto": name, "mapas": len(s),
            "log_loss": _logloss(s["elo_prob"].to_numpy(), s["target"].to_numpy()),
            "brier": float(np.mean((s["elo_prob"] - s["target"]) ** 2)),
            "acc": float(((s["elo_prob"] > 0.5) == (s["target"] == 1)).mean()),
            "p_media": float(s["elo_prob"].mean()), "y_media": float(s["target"].mean()),
        })
    ax.set_xlabel("Probabilidad del Elo (lado azul)")
    ax.set_ylabel("Frecuencia real de victoria azul")
    ax.set_title("Calibración del Elo")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend(loc="upper left")
    _save(fig, out_dir, "03_calibracion_elo.png")

    by_league = warm[warm["league"] != eval_league].groupby("league").apply(
        lambda s: pd.Series({"mapas": len(s), "log_loss": _logloss(s["elo_prob"].to_numpy(), s["target"].to_numpy())})
    )
    print("\nLog-loss del Elo por liga (equipos con >=10 mapas previos):")
    print(by_league.round(4).to_string())
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 4. Series: reconstrucción, regla de lado y "momentum"
# ---------------------------------------------------------------------------
def side_rule(series: pd.DataFrame, games: pd.DataFrame, out_dir: Path) -> pd.DataFrame:
    """¿Qué elige el perdedor del mapa anterior: lado azul y/o primer pick? Por año y formato.

    Desde 2026 el primer pick está separado del lado (``firstPick`` puede ser del rojo).
    """
    fp = games.loc[games["side"] == "Blue", ["gameid", "firstPick"]].rename(columns={"firstPick": "fp_azul"})
    s = series.merge(fp, on="gameid", how="left")
    m = s[(s["game"] >= 2) & s["ganador_prev"].notna()].copy()
    # Dentro de una serie el par de equipos es fijo: el perdedor previo es el que no ganó.
    m["perdedor_en_azul"] = m["teamid_blue"] != m["ganador_prev"]
    m["perdedor_con_fp"] = np.where(m["perdedor_en_azul"], m["fp_azul"] == 1, m["fp_azul"] == 0)
    m["anio"] = m["date"].dt.year
    t = m.groupby(["anio", "formato"])[["perdedor_en_azul", "perdedor_con_fp"]].mean()
    t["n"] = m.groupby(["anio", "formato"]).size()
    print("\nMapas 2+ de una serie: ¿el perdedor del mapa anterior juega en azul / tiene primer pick?")
    print(t.round(3).to_string())
    print("Bo5 2026, combinación elegida por el perdedor (azul?, primer pick?):")
    b5 = m[(m["anio"] == m["anio"].max()) & (m["formato"] == "Bo5")]
    print(b5.groupby(["perdedor_en_azul", "perdedor_con_fp"]).size().to_string())

    # Momentum: residual del ganador del mapa anterior (resultado - prob Elo).
    m = m.assign(
        prob_gan_prev=np.where(m["teamid_blue"] == m["ganador_prev"], m["elo_prob"], 1 - m["elo_prob"]),
        gana_gan_prev=np.where(m["teamid_blue"] == m["ganador_prev"], m["target"], 1 - m["target"]),
    )
    res = m["gana_gan_prev"] - m["prob_gan_prev"]
    se = res.std() / np.sqrt(len(res))
    print(
        f"\nMomentum: el ganador del mapa anterior gana el siguiente {m['gana_gan_prev'].mean():.3f} "
        f"(Elo esperaba {m['prob_gan_prev'].mean():.3f}); residual {res.mean():+.3f} ± {1.96 * se:.3f} (IC95)"
    )
    # Ventaja azul real en mapas 2+ (el perdedor elige azul): ¿cuánto gana el azul?
    print(f"Winrate azul en mapas 1: {series.loc[series['game'] == 1, 'target'].mean():.3f}  |  "
          f"en mapas 2+: {m['target'].mean():.3f}")

    # Gráfico: % del perdedor previo en azul vs con primer pick, por año (Bo3+Bo5).
    bo = m[m["formato"].isin(["Bo3", "Bo5"])]
    yr = bo.groupby("anio")[["perdedor_en_azul", "perdedor_con_fp"]].mean()
    n_yr = bo.groupby("anio").size()
    fig, ax = plt.subplots(figsize=(6.2, 3.4))
    x = np.arange(len(yr))
    w = 0.36
    b1 = ax.bar(x - w / 2 - 0.01, yr["perdedor_en_azul"], w, color=C_BLUE, label="Juega en lado azul")
    b2 = ax.bar(x + w / 2 + 0.01, yr["perdedor_con_fp"], w, color=C_ACCENT, label="Tiene el primer pick")
    for bars in (b1, b2):
        for rect in bars:
            ax.text(rect.get_x() + rect.get_width() / 2, rect.get_height() + 0.02, f"{rect.get_height():.0%}",
                    ha="center", fontsize=9, color=C_TEXT)
    ax.set_xticks(x, [f"{a}\n(n={n_yr[a]})" for a in yr.index])
    ax.set_ylim(0, 1.1)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.set_ylabel("Mapas 2+ en Bo3/Bo5")
    ax.set_title("Qué obtiene el perdedor del mapa anterior")
    ax.legend(loc="upper right", ncols=2)
    ax.grid(axis="x", visible=False)
    _save(fig, out_dir, "04_regla_lado_series.png")
    return t


def first_pick(games: pd.DataFrame) -> pd.DataFrame:
    """Winrate del lado azul según quién tiene el primer pick, por año."""
    b = games[games["side"] == "Blue"]
    t = b.groupby(["year", "firstPick"])["result"].agg(["mean", "size"])
    print("\nWinrate del AZUL según si el azul tiene el primer pick (por temporada):")
    print(t.round(3).to_string())
    return t


# ---------------------------------------------------------------------------
# 5. Regiones e historial previo al Mundial
# ---------------------------------------------------------------------------
def home_league(games: pd.DataFrame, intl: list[str]) -> pd.Series:
    """Liga local de cada teamid: su liga no internacional más frecuente."""
    dom = games[~games["league"].isin(intl)]
    return dom.groupby("teamid")["league"].agg(lambda s: s.value_counts().index[0])


def regions(games: pd.DataFrame, cfg: dict[str, Any], out_dir: Path) -> pd.DataFrame:
    """Winrate entre regiones en MSI y Mundial 2025 (sin el Mundial de evaluación)."""
    intl = list(cfg["elo"]["international_leagues"])
    eval_league, eval_year = cfg["data"]["eval_league"], int(cfg["modeling"]["eval_year"])
    home = home_league(games, intl)
    g = games[games["league"].isin(intl) & ~((games["league"] == eval_league) & (games["year"] == eval_year))].copy()
    g["region"] = g["teamid"].map(home).fillna("?")
    g["region"] = g["region"].replace({"LTA N": "LCS/LTA N", "LCS": "LCS/LTA N", "LTA S": "LTA S"})
    opp = g.groupby("gameid")["region"].transform(lambda s: s.iloc[::-1].to_numpy())
    g["region_opp"] = opp
    g = g[g["region"] != g["region_opp"]]
    wr = g.pivot_table(index="region", columns="region_opp", values="result", aggfunc="mean")
    n = g.pivot_table(index="region", columns="region_opp", values="result", aggfunc="size")
    order = [r for r in ["LCK", "LPL", "LEC", "LCP", "LCS/LTA N", "LTA S"] if r in wr.index]
    wr, n = wr.reindex(index=order, columns=order), n.reindex(index=order, columns=order)

    fig, ax = plt.subplots(figsize=(6.4, 5))
    im = ax.imshow(wr.to_numpy(dtype=float), cmap="RdBu", vmin=0, vmax=1)
    for i in range(len(order)):
        for j in range(len(order)):
            if pd.notna(wr.iat[i, j]):
                v = wr.iat[i, j]
                ax.text(j, i, f"{v:.0%}\n(n={int(n.iat[i, j])})", ha="center", va="center", fontsize=8,
                        color="white" if abs(v - 0.5) > 0.3 else C_TEXT)
    ax.set_xticks(range(len(order)), order, rotation=30, ha="right")
    ax.set_yticks(range(len(order)), order)
    ax.set_xlabel("Rival")
    ax.set_ylabel("Región")
    ax.grid(False)
    ax.set_title("Winrate por mapa entre regiones\n(MSI 2025-26 y Mundial 2025)")
    fig.colorbar(im, ax=ax, fraction=0.04, format=matplotlib.ticker.PercentFormatter(1.0))
    _save(fig, out_dir, "05_regiones.png")
    return wr


def worlds_history(games: pd.DataFrame, cfg: dict[str, Any], out_dir: Path) -> pd.DataFrame:
    """Mapas previos al Mundial de evaluación de cada participante (descriptivo)."""
    intl = list(cfg["elo"]["international_leagues"])
    eval_league, eval_year = cfg["data"]["eval_league"], int(cfg["modeling"]["eval_year"])
    w = games[(games["league"] == eval_league) & (games["year"] == eval_year)]
    start = w["date"].min()
    prev = games[games["date"] < start]
    t = pd.DataFrame({"teamname": w.groupby("teamid")["teamname"].first()})
    t["mapas_previos"] = prev.groupby("teamid").size().reindex(t.index).fillna(0).astype(int)
    t["mapas_intl_previos"] = prev[prev["league"].isin(intl)].groupby("teamid").size().reindex(t.index).fillna(0).astype(int)
    t["mapas_2026"] = prev[prev["date"].dt.year == eval_year].groupby("teamid").size().reindex(t.index).fillna(0).astype(int)
    t = t.sort_values("mapas_previos")

    fig, ax = plt.subplots(figsize=(7, 5.5))
    y = np.arange(len(t))
    ax.barh(y, t["mapas_previos"] - t["mapas_intl_previos"], color=C_BLUE, height=0.7, label="Liga local")
    ax.barh(y, t["mapas_intl_previos"], left=t["mapas_previos"] - t["mapas_intl_previos"], color=C_ACCENT,
            height=0.7, label="MSI 2025-26 / Mundial 2025")
    ax.set_yticks(y, t["teamname"])
    for i, v in enumerate(t["mapas_previos"]):
        ax.text(v + 3, i, str(v), va="center", fontsize=8, color=C_TEXT2)
    ax.set_xlabel("Mapas en los datos antes del Mundial 2026")
    ax.set_title("Historial disponible de cada participante")
    ax.legend(loc="lower right")
    ax.grid(axis="y", visible=False)
    _save(fig, out_dir, "06_historial_participantes.png")
    return t


# ---------------------------------------------------------------------------
# 6. Plantillas (filas de jugadores del CSV crudo)
# ---------------------------------------------------------------------------
def rosters(cfg: dict[str, Any], out_dir: Path) -> pd.DataFrame:
    """Cambios de titulares mapa a mapa por equipo, leyendo las filas de jugadores."""
    dcfg = cfg["data"]
    frames = []
    for y in dcfg["years"]:
        p = PROJECT_ROOT / dcfg["raw_dir"] / dcfg["file_pattern"].format(year=y)
        frames.append(pd.read_csv(p, usecols=["gameid", "date", "league", "year", "position", "teamid",
                                              "teamname", "playerid"], low_memory=False))
    r = pd.concat(frames, ignore_index=True)
    r = r[(r["position"] != "team") & r["league"].isin(dcfg["leagues"]) & r["year"].isin(dcfg["years"])]
    r["date"] = pd.to_datetime(r["date"])
    lineup = (r.sort_values("position").groupby(["teamid", "gameid"])
              .agg(date=("date", "first"), teamname=("teamname", "first"), jugadores=("playerid", frozenset))
              .reset_index().sort_values(["teamid", "date"]))
    lineup["prev"] = lineup.groupby("teamid")["jugadores"].shift(1)
    lineup["cambios"] = [len(a - b) if isinstance(b, frozenset) else np.nan
                         for a, b in zip(lineup["jugadores"], lineup["prev"])]
    # Titulares distintos usados en los últimos 20 mapas (estabilidad de plantilla).
    tot = lineup.groupby("teamid").agg(teamname=("teamname", "last"), mapas=("gameid", "size"),
                                       mapas_con_cambio=("cambios", lambda s: int((s > 0).sum())))
    tot["pct_mapas_con_cambio"] = tot["mapas_con_cambio"] / (tot["mapas"] - 1)
    print(f"\nMapas (por equipo) con al menos un titular distinto al mapa anterior: "
          f"{(lineup['cambios'] > 0).mean():.1%}")
    focus = tot[tot["teamname"].isin(["Gen.G", "Bilibili Gaming", "T1", "Anyone's Legend", "Hanwha Life Esports"])]
    print(focus.sort_values("pct_mapas_con_cambio").round(3).to_string())

    # Gráfico: % de mapas con cambio, equipos con >= 40 mapas.
    big = tot[tot["mapas"] >= 40].sort_values("pct_mapas_con_cambio")
    fig, ax = plt.subplots(figsize=(6, 3.4))
    ax.hist(big["pct_mapas_con_cambio"], bins=np.linspace(0, 0.4, 21), color=C_BLUE, edgecolor=C_SURF, linewidth=2)
    for name, color in [("Gen.G", C_ACCENT), ("Bilibili Gaming", C_RED)]:
        v = tot.loc[tot["teamname"] == name, "pct_mapas_con_cambio"]
        if len(v):
            ax.axvline(v.iloc[0], color=color, linewidth=2)
            ax.text(v.iloc[0], ax.get_ylim()[1] * 0.92, f" {name} {v.iloc[0]:.0%}", color=C_TEXT, fontsize=9)
    ax.set_xlabel("% de mapas con algún titular distinto al mapa anterior")
    ax.set_ylabel("Equipos (≥40 mapas)")
    ax.set_title("Estabilidad de plantillas 2025-2026")
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    _save(fig, out_dir, "07_estabilidad_plantillas.png")
    return lineup


# ---------------------------------------------------------------------------
# 7. Features
# ---------------------------------------------------------------------------
def features_overview(feats: pd.DataFrame, cfg: dict[str, Any], out_dir: Path) -> pd.DataFrame:
    """Correlación con el target por ventana y correlación entre features (fuera del Mundial)."""
    eval_league = cfg["data"]["eval_league"]
    f = feats[feats["league"] != eval_league]
    stats = cfg["features"]["stats"]
    t = pd.DataFrame({
        f"r{n}": [f[f"diff_{s}_r{n}"].corr(f["target"]) for s in stats] for n in cfg["features"]["windows"]
    }, index=stats)
    t.loc["elo_diff"] = f["elo_diff"].corr(f["target"])
    print("\nCorrelación con el target por ventana (sin Mundial):")
    print(t.round(3).to_string())

    n = max(cfg["features"]["windows"])
    cols = ["elo_diff", *[f"diff_{s}_r{n}" for s in stats], "diff_dias_desde_ultimo"]
    c = f[cols].corr()
    labels = [x.replace("diff_", "").replace(f"_r{n}", "") for x in cols]
    fig, ax = plt.subplots(figsize=(7.5, 6.5))
    im = ax.imshow(c.to_numpy(), cmap="RdBu", vmin=-1, vmax=1)
    for i in range(len(cols)):
        for j in range(len(cols)):
            ax.text(j, i, f"{c.iat[i, j]:.2f}", ha="center", va="center", fontsize=7,
                    color="white" if abs(c.iat[i, j]) > 0.6 else C_TEXT)
    ax.set_xticks(range(len(cols)), labels, rotation=45, ha="right")
    ax.set_yticks(range(len(cols)), labels)
    ax.grid(False)
    ax.set_title(f"Correlación entre features (Blue − Red, ventana {n})")
    fig.colorbar(im, ax=ax, fraction=0.04)
    _save(fig, out_dir, "08_correlacion_features.png")
    return c


def main() -> None:
    """Punto de entrada: ``python -m lolpred.eda``."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    _style()
    cfg = load_config()
    proc = PROJECT_ROOT / cfg["data"]["processed_dir"]
    out_dir = PROJECT_ROOT / "reports" / "eda"
    out_dir.mkdir(parents=True, exist_ok=True)

    # El EDA describe solo los años del modelo (el calentamiento de 2024 queda fuera).
    games = pd.read_parquet(proc / cfg["data"]["games_file"])
    games = games[~games["is_warmup"]]
    feats = pd.read_parquet(proc / cfg["features"]["output_file"])
    pd.set_option("display.width", 160)

    print("\n=== 1. Lado azul ===")
    print(blue_side(feats, out_dir).round(3).to_string(index=False))
    print("\n=== 2. Datos parciales (proporción por liga y trimestre) ===")
    print(completeness(games, out_dir).round(2).to_string())
    print("\n=== 3. Calibración del Elo ===")
    print(elo_calibration(feats, cfg, out_dir).round(4).to_string(index=False))
    print("\n=== 4. Series ===")
    series = build_series(feats)
    print(series.drop_duplicates("serie")["formato"].value_counts().to_string())
    side_rule(series, games, out_dir)
    first_pick(games)
    print("\n=== 5. Regiones ===")
    print(regions(games, cfg, out_dir).round(3).to_string())
    print("\n=== 6. Historial de los participantes del Mundial 2026 ===")
    print(worlds_history(games, cfg, out_dir).to_string())
    print("\n=== 7. Plantillas ===")
    rosters(cfg, out_dir)
    print("\n=== 8. Features ===")
    features_overview(feats, cfg, out_dir)


if __name__ == "__main__":
    sys.exit(main())
