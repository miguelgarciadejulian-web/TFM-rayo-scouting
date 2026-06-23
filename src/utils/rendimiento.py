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
                              "successful_passes_opposition_half_p90"],             0.28),
        ("Creación",        ["key_passes_attempt_assists_p90",
                              "goal_assists_p90",
                              "through_balls_p90"],                                 0.25),
        ("Recuperación",    ["tackles_won_p90", "interceptions_p90",
                              "recoveries_p90"],                                    0.25),
        ("Ataque",          ["goals_p90", "total_shots_p90",
                              "total_touches_in_opposition_box_p90"],               0.22),
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

# ── Texto metodológico (para criterios.py) ───────────────────────────────────
REND_METHODOLOGY: dict[str, str] = {
    "GK":  "Paradas/90 + big chances salvadas (45%) · Limpiezas + goles encajados invertido (30%) · Juego con balón (15%) · Duelos aéreos (10%)",
    "CB":  "Acciones defensivas/90: entradas+intercepciones+recuperaciones+bloqueos+despejes (40%) · Duelo aéreo (25%) · Duelo 1v1 (20%) · Construcción de juego (15%)",
    "FB":  "Defensiva (30%) · Proyección ofensiva: centros+pases adelante (30%) · Duelos (20%) · Contribución en ataque (20%)",
    "DM":  "Recuperación de balón (40%) · Pase (30%) · Presión y duelos (20%) · Contribución ofensiva (10%)",
    "CM":  "Pase (28%) · Creación de juego (25%) · Recuperación (25%) · Ataque (22%)",
    "AM":  "Creación (35%) · Gol/Remate (30%) · Pase en profundidad (20%) · Pressing (15%)",
    "WG":  "Regates/Desborde (30%) · Gol/Remate (30%) · Creación (25%) · Pressing (15%)",
    "ST":  "Gol/Remate (45%) · Juego de área: duelos aéreos y 1v1 (20%) · Creación (20%) · Pressing (15%)",
}

# ── Helper ────────────────────────────────────────────────────────────────────
def _n(s: str) -> str:
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().strip()


def get_subposition(
    name: str,
    overrides: dict | None = None,
    mv_df: pd.DataFrame | None = None,
    position_group: str | None = None,
) -> str:
    """
    Determina la sub-posición de un jugador con cascada de fuentes:
    1. player_overrides.json  →  campo 'position'
    2. market_values.csv      →  campo 'position'
    3. enriched position_group (fallback)
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

    # Fallback
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


def compute_rendimiento(
    player_row: pd.Series,
    enriched_df: pd.DataFrame,
    subpos: str | None = None,
    min_minutes: int = 450,
) -> dict:
    """
    Calcula el score de Rendimiento para un jugador.

    Devuelve:
        {
          "score":      float 0-100,
          "raw_score":  float (sin ajuste de liga),
          "subpos":     str  (p.ej. "WG"),
          "subpos_label": str (p.ej. "Extremo"),
          "pool_grp":   str  (p.ej. "FWD"),
          "pool_size":  int,
          "dims":       [{"label":..., "score":..., "weight":...}, ...],
          "league_diff": float,
          "league":     str,
        }
    """
    from src.utils.rendimiento import (
        REND_DIMS, SUBPOS_TO_POOL, SUBPOS_LABELS, _add_gk_derived
    )

    if subpos is None:
        grp = str(player_row.get("position_group", "") or "MID").upper()
        subpos = OPTA_GRP_TO_SUBPOS.get(grp, "CM")

    pool_grp  = SUBPOS_TO_POOL.get(subpos, "MID")
    dims_def  = REND_DIMS.get(subpos, REND_DIMS["CM"])
    mins_val  = float(player_row.get("minutes") or 0)

    if mins_val < 90:
        return {
            "score": 10.0, "raw_score": 10.0, "subpos": subpos,
            "subpos_label": SUBPOS_LABELS.get(subpos, subpos),
            "pool_grp": pool_grp, "pool_size": 0, "dims": [],
            "league_diff": 1.0, "league": str(player_row.get("league") or ""),
        }

    # Pool: misma grupo posicional, ≥ min_minutes
    pool = enriched_df[
        enriched_df["position_group"].str.upper() == pool_grp
    ].copy()
    pool = pool[pd.to_numeric(pool["minutes"], errors="coerce").fillna(0) >= min_minutes]

    if subpos == "GK":
        pool = _add_gk_derived(pool)
        # Añadir métricas derivadas para la fila del jugador también
        tmp = pd.DataFrame([player_row])
        tmp = _add_gk_derived(tmp)
        player_row = tmp.iloc[0]

    pool_size = len(pool)

    def _pct(col: str, val: float) -> float | None:
        if col not in pool.columns:
            return None
        series = pd.to_numeric(pool[col], errors="coerce").dropna()
        if len(series) < 5:
            return None
        return float((series < val).sum() / len(series) * 100)

    dim_results, total_w, total_ws = [], 0.0, 0.0
    for label, metrics, weight in dims_def:
        scores = []
        for m in metrics:
            val = float(player_row.get(m) or 0)
            pct = _pct(m, val)
            if pct is not None:
                scores.append(pct)
        if scores:
            ds = round(sum(scores) / len(scores), 1)
            dim_results.append({"label": label, "score": ds, "weight": weight})
            total_ws += weight * ds
            total_w  += weight

    raw = round(total_ws / total_w, 1) if total_w > 0 else 10.0

    # Ajuste por dificultad de liga
    try:
        from src.scouting.comparator import _league_difficulty
        diff = _league_difficulty(player_row.get("league"))
    except Exception:
        diff = 1.0

    return {
        "score":       round(raw * diff, 1),
        "raw_score":   raw,
        "subpos":      subpos,
        "subpos_label": SUBPOS_LABELS.get(subpos, subpos),
        "pool_grp":    pool_grp,
        "pool_size":   pool_size,
        "dims":        dim_results,
        "league_diff": diff,
        "league":      str(player_row.get("league") or ""),
    }
