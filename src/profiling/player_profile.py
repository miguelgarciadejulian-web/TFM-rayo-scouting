# -*- coding: utf-8 -*-
"""
player_profile.py
=================
Perfilado AUTOMATICO de jugadores por reglas en Python (sin texto manual).

A partir de las metricas Opta por-90 de `player_seasons_enriched.parquet`, calcula
para cada jugador:

  - primary_role  : rol principal entre los 11 perfiles canonicos
  - secondary_roles: roles secundarios compatibles
  - style_label   : etiqueta de estilo legible
  - role_scores   : score 0-100 de encaje en cada rol
  - strengths     : metricas en las que destaca (percentil alto vs su grupo)
  - weaknesses    : metricas flojas (percentil bajo)
  - risk_level    : riesgo (muestra de minutos + edad si se conoce)
  - potential     : potencial de desarrollo (edad si se conoce; si no, proxy)
  - confidence    : fiabilidad del perfil segun minutos jugados

Logica:
  1. Se normaliza cada metrica a percentil 0-100 dentro del grupo posicional
     (GK/DEF/MID/FWD) y la liga, comparando peras con peras.
  2. Cada rol es una combinacion ponderada de percentiles (ROLE_DEFINITIONS).
  3. El rol con mayor score es el principal; los siguientes por encima de un
     umbral son secundarios.
  4. Fortalezas/debilidades = metricas con percentil mas alto/bajo.

Las reglas estan documentadas y son configurables (solo editar los pesos).
"""
from __future__ import annotations
from typing import Iterable
import numpy as np
import pandas as pd

# ── Metricas usadas para el perfilado (claves _p90 del parquet enriquecido) ──
# Etiqueta legible para fortalezas/debilidades y descripcion.
METRIC_LABELS = {
    "goals_p90": "goles",
    "total_shots_p90": "volumen de tiro",
    "shots_on_target_inc_goals_p90": "tiros a puerta",
    "total_touches_in_opposition_box_p90": "presencia en area rival",
    "key_passes_attempt_assists_p90": "pases clave",
    "goal_assists_p90": "asistencias",
    "successful_dribbles_p90": "regate",
    "successful_crosses_open_play_p90": "centros",
    "successful_passes_opposition_half_p90": "juego en campo rival",
    "forward_passes_p90": "pase hacia delante",
    "total_successful_passes_excl_crosses_corners_p90": "volumen de pase",
    "through_balls_p90": "pase entre lineas",
    "tackles_won_p90": "entradas ganadas",
    "total_tackles_p90": "entradas",
    "interceptions_p90": "intercepciones",
    "recoveries_p90": "recuperaciones",
    "blocks_p90": "bloqueos",
    "total_clearances_p90": "despejes",
    "aerial_duels_won_p90": "juego aereo",
    "ground_duels_won_p90": "duelos en suelo",
    "total_losses_of_possession_p90": "perdidas de balon",
}

# Metricas donde MENOS es mejor (se invierte el percentil).
NEGATIVE_METRICS = {"total_losses_of_possession_p90"}

# ── Definicion de roles: rol -> (grupo_posicional, {metrica_p90: peso}) ──────
# Los pesos son relativos; se normalizan internamente. Documentado y editable.
ROLE_DEFINITIONS: dict[str, dict] = {
    # ---- Delanteros ----
    "delantero_rematador": {
        "group": "FWD",
        "weights": {
            "goals_p90": 0.28, "shots_on_target_inc_goals_p90": 0.22,
            "total_shots_p90": 0.18, "total_touches_in_opposition_box_p90": 0.20,
            "aerial_duels_won_p90": 0.12,
        },
    },
    "delantero_movil": {
        "group": "FWD",
        "weights": {
            "successful_dribbles_p90": 0.24, "key_passes_attempt_assists_p90": 0.22,
            "successful_passes_opposition_half_p90": 0.18,
            "total_touches_in_opposition_box_p90": 0.18, "goals_p90": 0.18,
        },
    },
    "extremo_vertical": {
        "group": "FWD",
        "weights": {
            "successful_dribbles_p90": 0.30, "successful_crosses_open_play_p90": 0.22,
            "total_touches_in_opposition_box_p90": 0.20, "goals_p90": 0.14,
            "total_shots_p90": 0.14,
        },
    },
    "extremo_asociativo": {
        "group": "FWD",
        "weights": {
            "key_passes_attempt_assists_p90": 0.30,
            "successful_passes_opposition_half_p90": 0.26,
            "goal_assists_p90": 0.20, "successful_dribbles_p90": 0.14,
            "through_balls_p90": 0.10,
        },
    },
    # ---- Centrocampistas ----
    "mediocentro_organizador": {
        "group": "MID",
        "weights": {
            "total_successful_passes_excl_crosses_corners_p90": 0.30,
            "forward_passes_p90": 0.22, "successful_passes_opposition_half_p90": 0.22,
            "key_passes_attempt_assists_p90": 0.14, "through_balls_p90": 0.12,
        },
    },
    "mediocentro_recuperador": {
        "group": "MID",
        "weights": {
            "recoveries_p90": 0.26, "interceptions_p90": 0.24,
            "tackles_won_p90": 0.24, "aerial_duels_won_p90": 0.14,
            "ground_duels_won_p90": 0.12,
        },
    },
    "interior_llegador": {
        "group": "MID",
        "weights": {
            "total_touches_in_opposition_box_p90": 0.26, "goals_p90": 0.22,
            "total_shots_p90": 0.20, "key_passes_attempt_assists_p90": 0.18,
            "successful_dribbles_p90": 0.14,
        },
    },
    # ---- Defensas centrales ----
    "central_dominador": {
        "group": "DEF",
        "weights": {
            "total_successful_passes_excl_crosses_corners_p90": 0.26,
            "forward_passes_p90": 0.24, "successful_passes_opposition_half_p90": 0.22,
            "aerial_duels_won_p90": 0.16, "interceptions_p90": 0.12,
        },
    },
    "central_corrector": {
        "group": "DEF",
        "weights": {
            "total_clearances_p90": 0.28, "blocks_p90": 0.22,
            "aerial_duels_won_p90": 0.22, "interceptions_p90": 0.16,
            "tackles_won_p90": 0.12,
        },
    },
    # ---- Laterales (dentro del grupo DEF) ----
    "lateral_ofensivo": {
        "group": "DEF",
        "weights": {
            "successful_crosses_open_play_p90": 0.28,
            "total_touches_in_opposition_box_p90": 0.22,
            "successful_dribbles_p90": 0.20,
            "successful_passes_opposition_half_p90": 0.18,
            "key_passes_attempt_assists_p90": 0.12,
        },
    },
    "lateral_defensivo": {
        "group": "DEF",
        "weights": {
            "tackles_won_p90": 0.28, "interceptions_p90": 0.24,
            "recoveries_p90": 0.20, "total_clearances_p90": 0.16,
            "ground_duels_won_p90": 0.12,
        },
    },
    # ---- Portero ----
    # Portero estilo Rayo: salida de balón + portero-libero + reflejos
    "portero": {
        "group": "GK",
        "weights": {
            "recoveries_p90": 0.26,                       # intervención activa / sweeper
            "successful_passes_opposition_half_p90": 0.22, # construcción desde atrás
            "forward_passes_p90": 0.20,                    # juego largo / distribución
            "aerial_duels_won_p90": 0.18,                  # dominio aéreo del área
            "interceptions_p90": 0.14,                     # portero-libero fuera del área
        },
    },
}

ROLE_LABELS = {
    "delantero_rematador": "Delantero rematador",
    "delantero_movil": "Delantero movil",
    "extremo_vertical": "Extremo vertical",
    "extremo_asociativo": "Extremo asociativo",
    "mediocentro_organizador": "Mediocentro organizador",
    "mediocentro_recuperador": "Mediocentro recuperador",
    "interior_llegador": "Interior llegador",
    "central_dominador": "Central dominador",
    "central_corrector": "Central corrector",
    "lateral_ofensivo": "Lateral ofensivo",
    "lateral_defensivo": "Lateral defensivo",
    "portero": "Portero",
}

# Estilo legible derivado del rol principal.
STYLE_BY_ROLE = {
    "delantero_rematador": "Killer de area / referencia ofensiva",
    "delantero_movil": "Delantero asociativo y movil",
    "extremo_vertical": "Extremo de desborde y profundidad",
    "extremo_asociativo": "Extremo de juego interior y ultimo pase",
    "mediocentro_organizador": "Cerebro / pausa y distribucion",
    "mediocentro_recuperador": "Pivote de recuperacion e intensidad",
    "interior_llegador": "Interior de llegada y gol",
    "central_dominador": "Central con salida de balon",
    "central_corrector": "Central de corte y juego aereo",
    "lateral_ofensivo": "Carrilero ofensivo de banda",
    "lateral_defensivo": "Lateral solido y posicional",
    "portero": "Portero",
}

DEFAULT_MIN_MINUTES = 450


def _role_metrics() -> list[str]:
    cols = set()
    for d in ROLE_DEFINITIONS.values():
        cols.update(d["weights"].keys())
    return sorted(cols)


def add_role_percentiles(
    df: pd.DataFrame,
    group_cols: Iterable[str] = ("position_group", "league"),
    min_minutes: int = DEFAULT_MIN_MINUTES,
) -> pd.DataFrame:
    """Anade columnas <metrica>__pct (0-100) por grupo posicional x liga.

    Solo se rankean jugadores con minutos suficientes para que el percentil sea
    representativo; el resto recibe NaN en los percentiles.
    """
    out = df.copy()
    group_cols = [c for c in group_cols if c in out.columns]
    mins = pd.to_numeric(out.get("minutes"), errors="coerce").fillna(0)
    mask = mins >= min_minutes

    for m in _role_metrics():
        if m not in out.columns:
            out[m] = np.nan
        vals = pd.to_numeric(out[m], errors="coerce")
        ranked = vals.where(mask)
        pct = ranked.groupby([out[c] for c in group_cols]).rank(pct=True) * 100
        if m in NEGATIVE_METRICS:
            pct = 100 - pct
        out[f"{m}__pct"] = pct
    return out


def _score_roles(row: pd.Series, pos_group: str) -> dict[str, float]:
    scores = {}
    for role, d in ROLE_DEFINITIONS.items():
        if d["group"] != pos_group:
            continue
        wsum, acc = 0.0, 0.0
        for metric, w in d["weights"].items():
            pct = row.get(f"{metric}__pct")
            if pd.notna(pct):
                acc += w * float(pct)
                wsum += w
        scores[role] = round(acc / wsum, 1) if wsum > 0 else float("nan")
    return scores


def _strengths_weaknesses(row: pd.Series, pos_group: str, n: int = 4):
    rel = set()
    for role, d in ROLE_DEFINITIONS.items():
        if d["group"] == pos_group:
            rel.update(d["weights"].keys())
    pcts = []
    for m in rel:
        v = row.get(f"{m}__pct")
        if pd.notna(v):
            pcts.append((METRIC_LABELS.get(m, m), float(v)))
    pcts.sort(key=lambda x: x[1], reverse=True)
    strengths = [f"{lab} (top {100 - int(p)}%)" for lab, p in pcts[:n] if p >= 60]
    weaknesses = [f"{lab} (percentil {int(p)})" for lab, p in pcts[::-1][:n] if p <= 40]
    return strengths, weaknesses


def _confidence(minutes: float) -> str:
    if minutes >= 1800:
        return "alta"
    if minutes >= 900:
        return "media"
    if minutes >= DEFAULT_MIN_MINUTES:
        return "baja"
    return "insuficiente"


def _risk_potential(age, minutes: float, primary_pct: float):
    """Riesgo y potencial. Edad opcional (no esta en los datos Opta)."""
    # Potencial
    if age is not None and not pd.isna(age):
        age = float(age)
        if age <= 21:
            potential = "muy alto"
        elif age <= 24:
            potential = "alto"
        elif age <= 28:
            potential = "estable"
        elif age <= 31:
            potential = "en meseta"
        else:
            potential = "veterania"
    else:
        potential = "n/d (sin edad)"

    # Riesgo deportivo (combina muestra y nivel del rol)
    risk = 0
    if minutes < 900:
        risk += 2
    elif minutes < 1500:
        risk += 1
    if pd.notna(primary_pct) and primary_pct < 45:
        risk += 1
    if age is not None and not pd.isna(age) and float(age) >= 33:
        risk += 1
    level = ["bajo", "bajo", "medio", "medio-alto", "alto"][min(risk, 4)]
    return level, potential


def profile_player_row(row: pd.Series, age=None) -> dict:
    """Devuelve el perfil completo de un jugador (fila ya con percentiles)."""
    pos = row.get("position_group", "?")
    minutes = float(pd.to_numeric(pd.Series([row.get("minutes")]), errors="coerce").fillna(0).iloc[0])
    scores = _score_roles(row, pos)
    valid = {k: v for k, v in scores.items() if pd.notna(v)}

    if not valid:
        return {
            "primary_role": None, "primary_role_label": "Sin datos suficientes",
            "primary_score": float("nan"),
            "secondary_roles": [], "secondary_roles_labels": [], "style_label": "n/d",
            "role_scores": {}, "strengths": [], "weaknesses": [],
            "risk_level": "n/d", "potential": "n/d",
            "confidence": _confidence(minutes), "position_group": pos,
        }

    ranked = sorted(valid.items(), key=lambda x: x[1], reverse=True)
    primary, primary_score = ranked[0]
    secondary = [r for r, s in ranked[1:] if s >= max(55, primary_score - 12)][:2]
    strengths, weaknesses = _strengths_weaknesses(row, pos)
    risk, potential = _risk_potential(age, minutes, primary_score)

    return {
        "primary_role": primary,
        "primary_role_label": ROLE_LABELS.get(primary, primary),
        "primary_score": primary_score,
        "secondary_roles": secondary,
        "secondary_roles_labels": [ROLE_LABELS.get(r, r) for r in secondary],
        "style_label": STYLE_BY_ROLE.get(primary, "n/d"),
        "role_scores": {ROLE_LABELS.get(k, k): v for k, v in ranked},
        "strengths": strengths,
        "weaknesses": weaknesses,
        "risk_level": risk,
        "potential": potential,
        "confidence": _confidence(minutes),
        "position_group": pos,
    }


def profile_dataframe(
    df: pd.DataFrame,
    ages: dict | None = None,
    min_minutes: int = DEFAULT_MIN_MINUTES,
) -> pd.DataFrame:
    """Perfila un DataFrame completo. `ages` opcional: {name -> edad}."""
    enr = add_role_percentiles(df, min_minutes=min_minutes)
    records = []
    for _, row in enr.iterrows():
        age = None
        if ages:
            age = ages.get(row.get("name"))
        prof = profile_player_row(row, age=age)
        prof["name"] = row.get("name")
        prof["team"] = row.get("team")
        prof["league"] = row.get("league")
        prof["season"] = row.get("season")
        records.append(prof)
    return pd.DataFrame(records)


# ── Conveniencia: perfilar un jugador concreto contra el pool de su liga ─────
# Columnas crudas que se suman para agregar la CARRERA del jugador.
_CAREER_RAW = [
    "goals", "goal_assists", "total_shots", "shots_on_target_inc_goals",
    "key_passes_attempt_assists", "successful_dribbles", "total_touches_in_opposition_box",
    "tackles_won", "total_tackles", "interceptions", "recoveries", "blocks",
    "total_clearances", "aerial_duels_won", "aerial_duels", "ground_duels_won",
    "successful_crosses_open_play", "successful_passes_opposition_half",
    "successful_long_passes", "forward_passes", "through_balls",
    "total_successful_passes_excl_crosses_corners", "total_losses_of_possession",
]

_SEASON_ORDER = {"2025-2026": 6, "2025": 5, "2024-2025": 4, "2023-2024": 3,
                 "2022-2023": 2, "2022": 1, "2021-2022": 1}

_CAREER_CACHE = {}


def most_recent_team(rows: pd.DataFrame) -> str:
    """Equipo más reciente de un jugador.

    Si en la temporada más reciente jugó en dos equipos (traspaso a mitad de
    temporada), devuelve el DESTINO nuevo: el equipo que no aparecía en
    temporadas anteriores. Si ambos son nuevos o ninguno, el de más minutos.
    """
    if rows.empty:
        return ""
    g = rows.copy()
    g["_o"] = g["season"].map(_SEASON_ORDER).fillna(0)
    g["_min"] = pd.to_numeric(g.get("minutes"), errors="coerce").fillna(0)
    mx = g["_o"].max()
    latest = g[g["_o"] == mx]
    if latest["team"].nunique() <= 1:
        return latest.sort_values("_min", ascending=False).iloc[0]["team"]
    earlier_teams = set(g[g["_o"] < mx]["team"])
    new = latest[~latest["team"].isin(earlier_teams)]
    pool = new if not new.empty else latest
    return pool.sort_values("_min", ascending=False).iloc[0]["team"]


def career_aggregate(enriched: pd.DataFrame) -> pd.DataFrame:
    """Agrega TODO el histórico de cada jugador en una sola fila (suma de partidos).

    Suma las métricas crudas y los minutos de todas sus temporadas y recalcula los
    por-90 sobre el total. El grupo posicional es el más frecuente y la liga la de
    más minutos. Así el perfil refleja la carrera, no una temporada concreta.
    """
    key = (id(enriched), len(enriched))
    if key in _CAREER_CACHE:
        return _CAREER_CACHE[key]

    df = enriched.copy()
    df["minutes"] = pd.to_numeric(df.get("minutes"), errors="coerce").fillna(0)
    raw = [c for c in _CAREER_RAW if c in df.columns]
    agg = df.groupby("name", as_index=False).agg(
        {**{c: "sum" for c in raw}, "minutes": "sum"}
    )
    # grupo posicional más frecuente
    grp = df.groupby("name")["position_group"].agg(
        lambda s: s.mode().iloc[0] if not s.mode().empty else "?")
    agg["position_group"] = agg["name"].map(grp)
    # liga dominante (más minutos)
    lg = (df.groupby(["name", "league"])["minutes"].sum().reset_index()
            .sort_values("minutes", ascending=False).drop_duplicates("name")
            .set_index("name")["league"])
    agg["league"] = agg["name"].map(lg)
    # equipo más reciente (vectorizado; gestiona 2 equipos en la última temporada)
    df["_o"] = df["season"].map(_SEASON_ORDER).fillna(0)
    df["_min"] = pd.to_numeric(df.get("minutes"), errors="coerce").fillna(0)
    maxo = df.groupby("name")["_o"].transform("max")
    latest = df[df["_o"] == maxo].copy()
    earlier_set = df[df["_o"] < maxo].groupby("name")["team"].agg(set).to_dict()
    latest["_isnew"] = [t not in earlier_set.get(n, set())
                        for n, t in zip(latest["name"], latest["team"])]
    latest = latest.sort_values(["_isnew", "_min"], ascending=[False, False])
    team_map = latest.drop_duplicates("name").set_index("name")["team"]
    agg["team"] = agg["name"].map(team_map)
    agg["seasons_played"] = agg["name"].map(df.groupby("name")["season"].nunique())
    agg["season"] = "histórico"
    # recomputar por-90 sobre minutos totales
    mins = agg["minutes"].replace(0, pd.NA)
    for c in raw:
        agg[f"{c}_p90"] = agg[c] / mins * 90
    _CAREER_CACHE[key] = agg
    return agg


def profile_single_player(enriched: pd.DataFrame, name: str, team: str | None = None,
                          league: str | None = None, age=None) -> dict | None:
    """Perfil del jugador a partir de TODO su histórico agregado (no una temporada).

    Suma todos sus partidos del histórico disponible, y compara sus percentiles
    contra el resto de jugadores también agregados por carrera (peras con peras).
    """
    import unicodedata as _u

    def _n(s):
        return _u.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()

    career = career_aggregate(enriched)
    cand = career[career["name"].map(_n) == _n(name)]
    if cand.empty:
        cand = career[career["name"].map(_n).str.contains(_n(name).split()[-1], na=False)]
    if cand.empty:
        return None
    target_name = cand.iloc[0]["name"]

    # percentiles dentro del pool de carrera, por grupo posicional × liga dominante
    enr = add_role_percentiles(career)
    prow = enr[enr["name"] == target_name]
    if prow.empty:
        return None
    row = prow.iloc[0]
    prof = profile_player_row(row, age=age)
    prof["name"] = target_name
    prof["team"] = row.get("team")
    prof["league"] = row.get("league")
    prof["season"] = "histórico"
    prof["minutes"] = row.get("minutes")
    prof["seasons_played"] = int(row.get("seasons_played", 0) or 0)
    return prof


# ── Ranking de objetivos de fichaje para un rol concreto ────────────────────
# Temporadas consideradas "actuales":
#   "2026"      → ligas de calendario natural (Brasil, MLS, Escocia, etc.)
#   "2025-2026" → ligas de temporada europea (La Liga, Premier, Bundesliga, etc.)
# Se incluyen AMBAS para no perder jugadores de ninguna competición vigente.
CURRENT_SEASONS = ["2026", "2025-2026"]

# Umbral de orden: se consideran "actuales" las dos prioridades más altas del ciclo.
_SEASON_ORDER = {
    "2026": 7, "2025-2026": 6, "2025/2026": 6,
    "2025": 5, "2024-2025": 4, "2024": 4,
    "2023-2024": 3, "2023": 3,
}
_CURRENT_MIN_ORDER = 6  # incluye orden 6 (2025-2026) y 7 (2026)


def detect_latest_seasons(enriched: pd.DataFrame) -> list[str]:
    """Detecta dinámicamente las temporadas actuales del parquet.

    Devuelve TODAS las temporadas correspondientes al ciclo en curso:
    tanto las de calendario natural ("2026") como las de temporada europea
    ("2025-2026"), de modo que no se pierdan jugadores de ninguna liga.
    """
    available = enriched["season"].dropna().astype(str).unique()
    current = [s for s in available if _SEASON_ORDER.get(s, 0) >= _CURRENT_MIN_ORDER]
    return current if current else list(available[:1])


def rank_players_for_role(enriched: pd.DataFrame, role: str, top_n: int = 10,
                          min_minutes: int = 900, exclude_team: str | None = "rayo",
                          leagues: list[str] | None = None,
                          seasons: list[str] | None = None,
                          max_value_eur: float | None = None,
                          exclude_big_clubs: bool = False,
                          only_expiring: bool = False) -> pd.DataFrame:
    """Ranking automatico de candidatos para un rol (score del rol 0-100).

    Por defecto SOLO jugadores con datos en temporadas actuales (en activo),
    para no proponer fichar a jugadores retirados/sin datos recientes.
    Percentila dentro del grupo posicional del rol y devuelve los mejores.
    """
    import unicodedata as _u
    if role not in ROLE_DEFINITIONS:
        return pd.DataFrame()
    spec = ROLE_DEFINITIONS[role]
    grp = spec["group"]

    df = enriched.copy()
    seasons = seasons if seasons is not None else CURRENT_SEASONS
    if seasons:
        df = df[df["season"].astype(str).isin(seasons)]
    if leagues:
        df = df[df["league"].isin(leagues)]
    df = df[df["position_group"] == grp]
    if df.empty:
        return pd.DataFrame()

    enr = add_role_percentiles(df, min_minutes=min_minutes)
    # score vectorizado del rol
    wsum = sum(spec["weights"].values())
    score = pd.Series(0.0, index=enr.index)
    valid = pd.Series(0.0, index=enr.index)
    for metric, w in spec["weights"].items():
        col = f"{metric}__pct"
        if col in enr.columns:
            vals = enr[col]
            score = score.add(vals.fillna(0) * w, fill_value=0)
            valid = valid.add(vals.notna() * w, fill_value=0)
    enr = enr.assign(role_score=(score / wsum).round(1), _valid=valid / wsum)
    enr = enr[enr["_valid"] >= 0.5]  # exigir cobertura de metricas

    if exclude_team:
        ex = _u.normalize("NFKD", exclude_team).encode("ascii", "ignore").decode().lower()
        enr = enr[~enr["team"].astype(str).str.lower().str.contains(ex, na=False)]

    if exclude_big_clubs:
        try:
            from src.utils.market import is_big_club as _ibc
            enr = enr[~enr["team"].map(lambda t: _ibc(str(t)))]
        except Exception:
            pass

    # quedarse con la mejor temporada de cada jugador
    enr = enr.sort_values("role_score", ascending=False)
    enr = enr.drop_duplicates(subset=["name", "team"], keep="first")

    cols = ["name", "team", "league", "season", "minutes", "role_score"]
    cols = [c for c in cols if c in enr.columns]
    out = enr[cols].reset_index(drop=True)

    # Adjuntar valor de mercado / contrato / edad (si estan en market_values.csv)
    try:
        from src.utils.market import get_value, is_big_club, expires_2026
        from datetime import date as _date

        def _mkt(n):
            return get_value(n)

        out["value_eur"]      = out["name"].map(lambda n: _mkt(n).get("value_eur"))
        out["contract_until"] = out["name"].map(lambda n: _mkt(n).get("contract_until"))
        out["age"]            = out["name"].map(lambda n: _mkt(n).get("age"))
        out["expiring_2026"]  = out["contract_until"].map(expires_2026)

        # contract_years_remaining: float, años hasta fin de contrato desde hoy
        def _years(c):
            if not c:
                return None
            try:
                end = _date.fromisoformat(str(c)[:10])
                return round(max((end - _date.today()).days / 365.25, 0), 1)
            except Exception:
                return None

        out["contract_years_remaining"] = out["contract_until"].map(_years)

        out["role"]       = role
        out["role_label"] = ROLE_LABELS.get(role, role)

    except Exception:
        out["value_eur"]               = None
        out["contract_until"]          = None
        out["expiring_2026"]           = None
        out["age"]                     = None
        out["contract_years_remaining"] = None
        out["role"]       = role
        out["role_label"] = ROLE_LABELS.get(role, role)

    # Filtros post-market
    out = out.sort_values("role_score", ascending=False).reset_index(drop=True)

    if max_value_eur is not None:
        try:
            import pandas as _pd
            mask = out["value_eur"].isna() | (_pd.to_numeric(out["value_eur"], errors="coerce") <= max_value_eur)
            out = out[mask]
        except Exception:
            pass

    if only_expiring:
        try:
            mask = out["expiring_2026"].fillna(False).astype(bool)
            out = out[mask]
        except Exception:
            pass

    out = out.head(top_n).reset_index(drop=True)
    return out
