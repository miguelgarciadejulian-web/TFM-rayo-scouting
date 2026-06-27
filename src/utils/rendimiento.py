# -*- coding: utf-8 -*-
"""
rendimiento.py
==============
Fuente única de verdad para el score de Rendimiento.

Usado por:
  - src/scouting/comparator.py   (FitRayoScorer)
  - dashboard/components/player_detail.py  (tarjeta de perfil)
  - dashboard/pages/jugador.py   (desglose)
  - dashboard/pages/criterios.py (metodología)
  - src/reports/player_dossier.py (PDF)

Sub-posiciones disponibles:
  GK  → Portero
  CB  → Central
  FB  → Lateral (RB / LB)
  DM  → Pivote / MD Defensivo
  CM  → Medio Centro
  AM  → Mediapunta / Interior
  WG  → Extremo (RW / LW)
  ST  → Delantero Centro / Segundo delantero
"""
from __future__ import annotations
import unicodedata
from pathlib import Path
import pandas as pd

# ── Mapeo TM position → sub-posición ─────────────────────────────────────────
TM_TO_SUBPOS: dict[str, str] = {
    # Porteros
    "Goalkeeper": "GK", "Portero": "GK",
    # Centrales
    "Centre-Back": "CB", "Central": "CB",
    # Laterales
    "Right-Back": "FB", "Left-Back": "FB",
    "Lateral derecho": "FB", "Lateral izquierdo": "FB",
    # Pivotes
    "Defensive Midfield": "DM", "Pivote": "DM", "Mediocentro defensivo": "DM",
    # Medios centros
    "Central Midfield": "CM", "Left Midfield": "CM", "Right Midfield": "CM",
    "Mediocentro": "CM",
    # Mediapuntas / interiores
    "Attacking Midfield": "AM", "Mediapunta": "AM",
    "Interior derecho": "AM", "Interior izquierdo": "AM",
    # Extremos
    "Right Winger": "WG", "Left Winger": "WG",
    "Extremo derecho": "WG", "Extremo izquierdo": "WG",
    # Delanteros
    "Centre-Forward": "ST", "Second Striker": "ST",
    "Striker": "ST", "Delantero centro": "ST", "Segundo delantero": "ST",
    # Genéricos (fallback)
    "Defender": "CB", "Midfielder": "CM", "Forward": "ST",
}

# Sub-posición por defecto cuando solo tenemos el grupo OPTA
OPTA_GRP_TO_SUBPOS: dict[str, str] = {
    "GK": "GK", "DEF": "CB", "MID": "CM", "FWD": "ST",
}

# Mapeo lateral_pos → sub-posición (inferida de build_lateral_map — más preciso que el grupo OPTA)
LATERAL_TO_SUBPOS: dict[str, str] = {
    "PO": "GK",
    "DC": "CB",
    "LI": "FB", "LD": "FB",
    "MC": "CM", "MI": "CM", "MD": "CM",
    "EI": "WG", "ED": "WG",
    "DL": "ST",
}

# Refinamiento de centrocampistas por tipología de rol
ROLE_TYPE_TO_SUBPOS: dict[str, str] = {
    "mediocentro_recuperador": "DM",
    "mediocentro_organizador": "CM",
    "interior_llegador":       "AM",
}

# ── Descripción legible ───────────────────────────────────────────────────────
SUBPOS_LABELS: dict[str, str] = {
    "GK": "Portero",
    "CB": "Central",
    "FB": "Lateral",
    "DM": "Pivote",
    "CM": "Medio Centro",
    "AM": "Mediapunta",
    "WG": "Extremo",
    "ST": "Delantero Centro",
}

# Pool OPTA a usar para cada sub-posición
SUBPOS_TO_POOL: dict[str, str] = {
    "GK": "GK",
    "CB": "DEF", "FB": "DEF",
    "DM": "MID", "CM": "MID", "AM": "MID",
    "WG": "FWD", "ST": "FWD",
}

# ── Dimensiones por sub-posición ─────────────────────────────────────────────
# Cada entrada: (etiqueta, [columnas_p90], peso)
# Columnas especiales calculadas al vuelo: saves_p90, big_chances_saved_p90,
# clean_sheets_rate, goals_conceded_p90_inv

# Pesos BASE por sub-posición (se usan cuando no hay role_type o no hay override)
REND_DIMS: dict[str, list] = {
    "GK": [
        ("Paradas",         ["saves_p90", "big_chances_saved_p90"],               0.45),
        ("Limpieza",        ["clean_sheets_rate", "goals_conceded_p90_inv"],       0.30),
        ("Juego con balón", ["total_successful_passes_excl_crosses_corners_p90",
                              "successful_long_passes_p90"],                        0.15),
        ("Área",            ["aerial_duels_won_p90", "recoveries_p90"],             0.10),
    ],
    "CB": [
        ("Defensiva",       ["tackles_won_p90", "interceptions_p90",
                              "recoveries_p90", "blocks_p90",
                              "total_clearances_p90"],                              0.40),
        ("Duelo aéreo",     ["aerial_duels_won_p90"],                               0.25),
        ("Duelo 1v1",       ["ground_duels_won_p90", "interceptions_p90"],          0.20),
        ("Construcción",    ["total_successful_passes_excl_crosses_corners_p90",
                              "successful_long_passes_p90",
                              "forward_passes_p90"],                                0.15),
    ],
    "FB": [
        ("Defensiva",       ["tackles_won_p90", "interceptions_p90",
                              "recoveries_p90"],                                    0.30),
        ("Proyección",      ["successful_crosses_open_play_p90",
                              "forward_passes_p90",
                              "total_successful_passes_excl_crosses_corners_p90"], 0.30),
        ("Duelos",          ["aerial_duels_won_p90", "ground_duels_won_p90"],       0.20),
        ("Ataque",          ["goal_assists_p90", "successful_dribbles_p90",
                              "total_touches_in_opposition_box_p90"],               0.20),
    ],
    "DM": [
        ("Recuperación",    ["tackles_won_p90", "interceptions_p90",
                              "recoveries_p90", "blocks_p90"],                      0.40),
        ("Pase",            ["total_successful_passes_excl_crosses_corners_p90",
                              "forward_passes_p90",
                              "successful_long_passes_p90"],                        0.30),
        ("Presión",         ["total_tackles_p90", "ground_duels_won_p90"],          0.20),
        ("Contribución ofensiva", ["goals_p90", "goal_assists_p90"],                0.10),
    ],
    "CM": [
        ("Pase",            ["total_successful_passes_excl_crosses_corners_p90",
                              "forward_passes_p90",
                              "successful_long_passes_p90",
                              "successful_passes_opposition_half_p90"],             0.30),
        ("Recuperación",    ["tackles_won_p90", "interceptions_p90",
                              "recoveries_p90"],                                    0.30),
        ("Creación",        ["key_passes_attempt_assists_p90",
                              "goal_assists_p90",
                              "through_balls_p90"],                                 0.25),
        ("Contribución",   ["goals_p90", "goal_assists_p90"],                 0.15),
    ],
    "AM": [
        ("Creación",        ["key_passes_attempt_assists_p90",
                              "goal_assists_p90",
                              "through_balls_p90",
                              "successful_dribbles_p90"],                           0.35),
        ("Gol",             ["goals_p90", "total_shots_p90",
                              "shots_on_target_inc_goals_p90",
                              "total_touches_in_opposition_box_p90"],               0.30),
        ("Pase en profundidad", ["forward_passes_p90",
                              "successful_passes_opposition_half_p90",
                              "total_successful_passes_excl_crosses_corners_p90"], 0.20),
        ("Pressing",        ["recoveries_p90", "tackles_won_p90"],                  0.15),
    ],
    "WG": [
        ("Regates / Desborde", ["successful_dribbles_p90",
                              "total_touches_in_opposition_box_p90"],               0.30),
        ("Gol / Remate",    ["goals_p90", "total_shots_p90",
                              "shots_on_target_inc_goals_p90"],                     0.30),
        ("Creación",        ["key_passes_attempt_assists_p90",
                              "goal_assists_p90",
                              "successful_crosses_open_play_p90"],                  0.25),
        ("Pressing",        ["recoveries_p90", "tackles_won_p90"],                  0.15),
    ],
    "ST": [
        ("Gol / Remate",    ["goals_p90", "total_shots_p90",
                              "shots_on_target_inc_goals_p90",
                              "total_touches_in_opposition_box_p90"],               0.45),
        ("Juego de área",   ["aerial_duels_won_p90", "ground_duels_won_p90"],       0.20),
        ("Creación",        ["key_passes_attempt_assists_p90",
                              "goal_assists_p90",
                              "successful_dribbles_p90"],                           0.20),
        ("Pressing",        ["recoveries_p90", "tackles_won_p90",
                              "interceptions_p90"],                                 0.15),
    ],
}

# ── Pesos ADAPTATIVOS por role_type ──────────────────────────────────────────
# Override de pesos cuando conocemos el estilo de juego exacto del jugador.
# Solo se modifican los pesos (peso_dim); las métricas siguen siendo las mismas
# de la sub-posición base para mantener la comparación justa dentro del pool.
REND_DIMS_BY_ROLE: dict[str, dict[str, float]] = {
    # Delanteros
    "delantero_rematador": {
        "Gol / Remate": 0.60, "Juego de área": 0.25, "Creación": 0.10, "Pressing": 0.05,
    },
    "delantero_movil": {
        "Gol / Remate": 0.30, "Juego de área": 0.15, "Creación": 0.35, "Pressing": 0.20,
    },
    # Extremos
    "extremo_vertical": {
        "Regates / Desborde": 0.40, "Gol / Remate": 0.35, "Creación": 0.15, "Pressing": 0.10,
    },
    "extremo_asociativo": {
        "Regates / Desborde": 0.20, "Gol / Remate": 0.15, "Creación": 0.50, "Pressing": 0.15,
    },
    # Centrocampistas
    "mediocentro_organizador": {
        "Pase": 0.45, "Recuperación": 0.20, "Creación": 0.25, "Contribución": 0.10,
    },
    "mediocentro_recuperador": {
        "Pase": 0.15, "Recuperación": 0.50, "Creación": 0.10, "Contribución": 0.25,
    },
    "interior_llegador": {
        "Creación": 0.30, "Gol": 0.35, "Pase en profundidad": 0.15, "Pressing": 0.20,
    },
    # Defensas
    "central_dominador": {
        "Defensiva": 0.25, "Duelo aéreo": 0.15, "Duelo 1v1": 0.15, "Construcción": 0.45,
    },
    "central_corrector": {
        "Defensiva": 0.50, "Duelo aéreo": 0.25, "Duelo 1v1": 0.20, "Construcción": 0.05,
    },
    "lateral_ofensivo": {
        "Defensiva": 0.15, "Proyección": 0.40, "Duelos": 0.15, "Ataque": 0.30,
    },
    "lateral_defensivo": {
        "Defensiva": 0.45, "Proyección": 0.15, "Duelos": 0.30, "Ataque": 0.10,
    },
}

# ── Texto metodológico (para criterios.py) ───────────────────────────────────
REND_METHODOLOGY: dict[str, str] = {
    "GK":  "Paradas/90 + big chances salvadas (45%) · Limpieza (30%) · Juego con balón (15%) · Área (10%) — z-score global × coef. liga",
    "CB":  "Defensiva (40%) · Duelo aéreo (25%) · Duelo 1v1 (20%) · Construcción (15%) — z-score global × coef. liga",
    "FB":  "Defensiva (30%) · Proyección (30%) · Duelos (20%) · Ataque (20%) — z-score global × coef. liga",
    "DM":  "Recuperación (40%) · Pase (30%) · Presión (20%) · Contribución ofensiva (10%) — z-score global × coef. liga",
    "CM":  "Pase (30%) · Recuperación (30%) · Creación (25%) · Contribución (15%) — z-score global × coef. liga",
    "AM":  "Creación (35%) · Gol (30%) · Pase en profundidad (20%) · Pressing (15%) — z-score global × coef. liga",
    "WG":  "Regates/Desborde (30%) · Gol/Remate (30%) · Creación (25%) · Pressing (15%) — z-score global × coef. liga",
    "ST":  "Gol/Remate (45%) · Juego de área (20%) · Creación (20%) · Pressing (15%) — z-score global × coef. liga",
}

# ── Helper ────────────────────────────────────────────────────────────────────
def _n(s: str) -> str:
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().strip()


def get_subposition(
    name: str,
    overrides: dict | None = None,
    mv_df: pd.DataFrame | None = None,
    position_group: str | None = None,
    lateral_pos: str | None = None,
    role_type: str | None = None,
) -> str:
    """
    Determina la sub-posición de un jugador con cascada de fuentes:
    1. player_overrides.json  →  campo 'position'
    2. market_values.csv      →  campo 'position'
    3. lateral_pos + role_type (de build_lateral_map — más fino que el grupo OPTA)
    4. enriched position_group (fallback)
    """
    if overrides:
        ov = overrides.get(_n(name), {})
        tm_pos = ov.get("position", "")
        if tm_pos and tm_pos in TM_TO_SUBPOS:
            return TM_TO_SUBPOS[tm_pos]

    if mv_df is not None and not mv_df.empty:
        nl = _n(name)
        name_col = "name" if "name" in mv_df.columns else mv_df.columns[0]
        mask = mv_df[name_col].apply(_n) == nl
        rows = mv_df[mask]
        if not rows.empty:
            tm_pos = str(rows.iloc[0].get("position", ""))
            if tm_pos in TM_TO_SUBPOS:
                return TM_TO_SUBPOS[tm_pos]

    # Fallback desde lateral_pos + role_type (inferidos de build_lateral_map)
    if lateral_pos and lateral_pos in LATERAL_TO_SUBPOS:
        subpos = LATERAL_TO_SUBPOS[lateral_pos]
        # Refinar centrocampistas según su tipología específica de rol
        if subpos == "CM" and role_type and role_type in ROLE_TYPE_TO_SUBPOS:
            return ROLE_TYPE_TO_SUBPOS[role_type]
        return subpos

    # Fallback final: grupo OPTA
    grp = str(position_group or "MID").upper()
    return OPTA_GRP_TO_SUBPOS.get(grp, "CM")


def _add_gk_derived(pool: pd.DataFrame) -> pd.DataFrame:
    """Añade columnas derivadas para porteros."""
    pool = pool.copy()
    mins = pd.to_numeric(pool.get("minutes"), errors="coerce").fillna(0)
    p90  = mins.clip(lower=1) / 90

    if "saves_made" in pool.columns:
        pool["saves_p90"] = pd.to_numeric(pool["saves_made"], errors="coerce").fillna(0) / p90
    else:
        pool["saves_p90"] = 0.0

    if "total_big_chances_saved" in pool.columns:
        pool["big_chances_saved_p90"] = pd.to_numeric(pool["total_big_chances_saved"], errors="coerce").fillna(0) / p90
    else:
        pool["big_chances_saved_p90"] = 0.0

    if "clean_sheets" in pool.columns and "matches" in pool.columns:
        m = pd.to_numeric(pool["matches"], errors="coerce").fillna(1).clip(lower=1)
        pool["clean_sheets_rate"] = pd.to_numeric(pool["clean_sheets"], errors="coerce").fillna(0) / m * 100
    else:
        pool["clean_sheets_rate"] = 0.0

    if "goals_conceded" in pool.columns:
        gc_p90 = pd.to_numeric(pool["goals_conceded"], errors="coerce").fillna(0) / p90
        # Invertir: menos goles encajados = mejor
        max_gc = gc_p90.quantile(0.95) if len(gc_p90) > 10 else gc_p90.max()
        pool["goals_conceded_p90_inv"] = (max_gc - gc_p90).clip(lower=0)
    else:
        pool["goals_conceded_p90_inv"] = 0.0

    return pool


# ── Coeficientes de calidad de liga ───────────────────────────────────────────
# Reflejan la dificultad competitiva real. Un mismo valor bruto p90 en una liga
# top vale más que en una liga inferior. Centrado en 1.0 aprox.
LEAGUE_QUALITY: dict[str, float] = {
    "England_Premier_League":       1.07,
    "Spain_Primera_Division":       1.05,
    "Germany_Bundesliga":           1.03,
    "Italy_Serie_A":                1.03,
    "France_Ligue_1":               0.98,
    "Netherlands_Eredivisie":       0.92,
    "Portugal_Primeira_Liga":       0.92,
    "Belgium_First_Division_A":     0.88,
    "Türkiye_Süper_Lig":            0.87,
    "England_Championship":         0.86,
    "Denmark_Superliga":            0.84,
    "Spain_Segunda_Division":       0.83,
    "France_Ligue_2":               0.81,
    "Germany_2_Bundesliga":         0.84,
    "Mexico_Liga_MX":               0.82,
    "Argentina_Liga_Profesional":   0.80,
}


def precompute_pool_stats(
    enriched_df: pd.DataFrame,
    pool_grp: str,
    min_minutes: int = 450,
) -> dict:
    """
    Pre-calcula media y std de cada métrica para un pool posicional.
    Devuelve: {"metric_name": (mean, std, n), ...}
    Usar con compute_rendimiento(pool_stats=...) para evitar recálculos.
    """
    pool = enriched_df[
        enriched_df["position_group"].str.upper() == pool_grp
    ].copy()
    pool = pool[pd.to_numeric(pool["minutes"], errors="coerce").fillna(0) >= min_minutes]

    if pool_grp == "GK":
        pool = _add_gk_derived(pool)

    stats: dict[str, tuple[float, float, int]] = {}
    # Recoger todas las métricas posibles de todas las sub-posiciones de este pool
    all_metrics = set()
    for subpos, sp_pool in SUBPOS_TO_POOL.items():
        if sp_pool == pool_grp:
            for _, metrics, _ in REND_DIMS.get(subpos, []):
                all_metrics.update(metrics)

    for col in all_metrics:
        if col not in pool.columns:
            continue
        series = pd.to_numeric(pool[col], errors="coerce").dropna()
        if len(series) >= 10:
            stats[col] = (float(series.mean()), float(series.std()), len(series))

    stats["__pool_size__"] = (float(len(pool)), 0.0, len(pool))
    return stats


def compute_rendimiento(
    player_row: pd.Series,
    enriched_df: pd.DataFrame,
    subpos: str | None = None,
    min_minutes: int = 450,
    role_type: str | None = None,
    pool_stats: dict | None = None,
) -> dict:
    """
    Calcula el score de Rendimiento basado en datos brutos p90.

    Método:
      1. Pool GLOBAL (todas las ligas, mismo grupo posicional, ≥ min_minutes)
      2. Para cada métrica: z-score vs pool global → escala 0-100
      3. Media ponderada de dimensiones (pesos según role_type)
      4. Coeficiente de liga multiplicativo (Premier/Liga > Segunda/Ligue2)

    Args:
      pool_stats: dict pre-computado por precompute_pool_stats(). Si se pasa,
                  evita recalcular el pool completo (10-50x más rápido en batch).

    Devuelve:
        {
          "score":        float 0-100 (ajustado por liga),
          "raw_score":    float 0-100 (antes de ajuste de liga),
          "subpos":       str,
          "subpos_label": str,
          "pool_grp":     str,
          "pool_size":    int,
          "dims":         [{"label":..., "score":..., "weight":...}, ...],
          "league_coef":  float,
          "league":       str,
          "role_type":    str | None,
        }
    """
    if subpos is None:
        grp = str(player_row.get("position_group", "") or "MID").upper()
        subpos = OPTA_GRP_TO_SUBPOS.get(grp, "CM")

    pool_grp  = SUBPOS_TO_POOL.get(subpos, "MID")
    dims_def  = REND_DIMS.get(subpos, REND_DIMS["CM"])
    mins_val  = float(player_row.get("minutes") or 0)

    player_league = str(player_row.get("league") or "")
    league_coef = LEAGUE_QUALITY.get(player_league, 0.85)

    if mins_val < 90:
        return {
            "score": 5.0, "raw_score": 5.0, "subpos": subpos,
            "subpos_label": SUBPOS_LABELS.get(subpos, subpos),
            "pool_grp": pool_grp, "pool_size": 0, "dims": [],
            "league_coef": league_coef, "league": player_league,
            "role_type": role_type,
        }

    # ── Pool stats: usar pre-computados si están disponibles ──────────────────
    if pool_stats is not None:
        _stats = pool_stats
        pool_size = int(_stats.get("__pool_size__", (0, 0, 0))[0])
        # GK derived: calcular para la fila del jugador si es portero
        if subpos == "GK":
            tmp = pd.DataFrame([player_row])
            tmp = _add_gk_derived(tmp)
            player_row = tmp.iloc[0]
    else:
        # Calcular pool desde cero (lento, evitar en batch)
        pool = enriched_df[
            enriched_df["position_group"].str.upper() == pool_grp
        ].copy()
        pool = pool[pd.to_numeric(pool["minutes"], errors="coerce").fillna(0) >= min_minutes]

        if subpos == "GK":
            pool = _add_gk_derived(pool)
            tmp = pd.DataFrame([player_row])
            tmp = _add_gk_derived(tmp)
            player_row = tmp.iloc[0]

        pool_size = len(pool)
        # Construir stats inline
        _stats = {}
        all_metrics = set()
        for _, metrics, _ in dims_def:
            all_metrics.update(metrics)
        for col in all_metrics:
            if col not in pool.columns:
                continue
            series = pd.to_numeric(pool[col], errors="coerce").dropna()
            if len(series) >= 10:
                _stats[col] = (float(series.mean()), float(series.std()), len(series))

    # Role_type → pesos adaptativos
    role_weight_override = REND_DIMS_BY_ROLE.get(role_type, {}) if role_type else {}

    def _z_to_score(col: str, val: float) -> float | None:
        """Convierte valor bruto a score 0-100 via z-score contra pool global."""
        if col not in _stats:
            return None
        mean, std, n = _stats[col]
        if n < 10 or std < 1e-9:
            return 50.0
        z = (val - mean) / std
        score = 50.0 + z * 17.0
        return max(3.0, min(97.0, score))

    dim_results, total_w, total_ws = [], 0.0, 0.0
    for label, metrics, base_weight in dims_def:
        weight = role_weight_override.get(label, base_weight)
        scores = []
        for m in metrics:
            val = float(player_row.get(m) or 0)
            s = _z_to_score(m, val)
            if s is not None:
                scores.append(s)
        if scores:
            ds = round(sum(scores) / len(scores), 1)
            dim_results.append({"label": label, "score": ds, "weight": weight})
            total_ws += weight * ds
            total_w  += weight

    raw = round(total_ws / total_w, 1) if total_w > 0 else 5.0

    # ── Aplicar coeficiente de liga (suavizado asimétrico) ──────────────────
    # Ligas fuertes (coef >= 1.0): se aplica el bonus completo.
    # Ligas más débiles (coef < 1.0): se suaviza la penalización con damping=0.55
    # para que un buen jugador de Segunda pueda aspirar a 60-65 (no aplastado a 45).
    # Ej: Primera 1.05 → 1.05, Segunda 0.83 → 0.907, Ligue 1 0.98 → 0.989
    if league_coef >= 1.0:
        effective_coef = league_coef
    else:
        effective_coef = 1.0 + (league_coef - 1.0) * 0.55
    adjusted = round(min(99.0, max(5.0, raw * effective_coef)), 1)

    return {
        "score":        adjusted,
        "raw_score":    raw,
        "subpos":       subpos,
        "subpos_label": SUBPOS_LABELS.get(subpos, subpos),
        "pool_grp":     pool_grp,
        "pool_size":    pool_size,
        "dims":         dim_results,
        "league_coef":  league_coef,
        "league":       player_league,
        "role_type":    role_type,
    }
