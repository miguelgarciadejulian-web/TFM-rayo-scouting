# -*- coding: utf-8 -*-
"""
lateral_position.py
===================
Infiere la posicion lateral especifica de cada jugador (LI, LD, DC, MC, MI, MD,
EI, ED, DC-fwd, PO) a partir de leftside_passes / rightside_passes del dataset
enriquecido, y una tipologia simplificada de rol (Lateral ofensivo, Central
dominador, Mediocentro recuperador, etc.) usando los datos de master_players.

Ambas funciones se cachean en memoria para no leer disco en cada callback.
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd

# ── Etiquetas legibles ────────────────────────────────────────────────────────
LATERAL_LABELS = {
    "LI":  "Lateral izquierdo (LI)",
    "LD":  "Lateral derecho (LD)",
    "DC":  "Defensa central (DC)",
    "MC":  "Mediocentro (MC)",
    "MI":  "Mediocampista izq. (MI)",
    "MD":  "Mediocampista der. (MD)",
    "EI":  "Extremo izquierdo (EI)",
    "ED":  "Extremo derecho (ED)",
    "DL":  "Delantero centro (DL)",
    "PO":  "Portero (PO)",
}

# Roles simplificados mostrados en el filtro "Tipo de jugador"
ROLE_TYPE_LABELS = {
    "lateral_ofensivo":        "Lateral ofensivo",
    "lateral_defensivo":       "Lateral defensivo",
    "central_dominador":       "Central dominador",
    "central_corrector":       "Central organizador",
    "mediocentro_organizador": "Mediocentro organizador",
    "mediocentro_recuperador": "Mediocentro recuperador",
    "interior_llegador":       "Interior llegador",
    "extremo_vertical":        "Extremo vertical",
    "extremo_asociativo":      "Extremo asociativo",
    "delantero_rematador":     "Delantero rematador",
    "delantero_movil":         "Delantero movil",
    "portero":                 "Portero",
}

# Roles disponibles por posicion lateral (para filtros dependientes)
LATERAL_TO_ROLES: dict[str, list[str]] = {
    "LI": ["lateral_ofensivo", "lateral_defensivo"],
    "LD": ["lateral_ofensivo", "lateral_defensivo"],
    "DC": ["central_dominador", "central_corrector"],
    "MC": ["mediocentro_organizador", "mediocentro_recuperador", "interior_llegador"],
    "MI": ["mediocentro_organizador", "mediocentro_recuperador", "interior_llegador"],
    "MD": ["mediocentro_organizador", "mediocentro_recuperador", "interior_llegador"],
    "EI": ["extremo_vertical", "extremo_asociativo"],
    "ED": ["extremo_vertical", "extremo_asociativo"],
    "DL": ["delantero_rematador", "delantero_movil"],
    "PO": ["portero"],
}

_CACHE: dict = {}


def clear_cache() -> None:
    """Limpia la caché en memoria (útil tras cambios de configuración o datos)."""
    _CACHE.clear()


def _infer_pos_code(group: str, ratio: float) -> str:
    """
    ratio = leftside_passes / (leftside_passes + rightside_passes).

    NOTA: 'leftside_passes' en OPTA mide la DIRECCIÓN del pase (hacia la izquierda),
    no el lado del campo donde está el jugador. Por tanto:
      - Lateral DERECHO (LD): está en el lado derecho, pasa hacia el interior (izquierda)
        → ratio ALTO (muchos leftside_passes).
      - Lateral IZQUIERDO (LI): está en el lado izquierdo, pasa hacia el interior (derecha)
        → ratio BAJO (muchos rightside_passes).
    La lógica es la inversa de lo que parece intuitivo.
    """
    if group == "GK":
        return "PO"
    if group == "DEF":
        if ratio > 0.60:
            return "LD"   # pasa hacia izquierda → está en el lado DERECHO
        if ratio < 0.40:
            return "LI"   # pasa hacia derecha → está en el lado IZQUIERDO
        return "DC"
    if group == "MID":
        if ratio > 0.62:
            return "MD"   # pasa hacia izquierda → mediocampista por la DERECHA
        if ratio < 0.38:
            return "MI"   # pasa hacia derecha → mediocampista por la IZQUIERDA
        return "MC"
    if group == "FWD":
        if ratio > 0.62:
            return "ED"   # pasa hacia izquierda → extremo por la DERECHA
        if ratio < 0.38:
            return "EI"   # pasa hacia derecha → extremo por la IZQUIERDA
        return "DL"
    return "?"


def _infer_role_type(row: pd.Series) -> str | None:
    """
    Tipologia simplificada usando columnas de master_players (career aggregates).
    Solo necesita: minutes, crosses_completed, tackles_won, interceptions,
    key_passes, goals, assists, passes_completed_pct.
    """
    lat  = row.get("lateral_pos", "")
    mins = float(row.get("minutes") or 0) or 1

    if lat in ("LI", "LD"):
        crosses_p90 = float(row.get("crosses_completed") or 0) / mins * 90
        # Umbral empírico: laterales ofensivos suelen dar > 1.0 centros/90'
        return "lateral_ofensivo" if crosses_p90 >= 1.0 else "lateral_defensivo"

    if lat == "DC":
        # Central organizador vs dominador: más pases completados % → organizador
        pct = float(row.get("passes_completed_pct") or 0)
        return "central_corrector" if pct >= 75 else "central_dominador"

    if lat in ("MC", "MI", "MD"):
        kp  = float(row.get("key_passes") or 0) / mins * 90
        tk  = float(row.get("tackles_won") or 0) / mins * 90
        if kp >= 0.8:
            return "mediocentro_organizador"
        if tk >= 2.5:
            return "mediocentro_recuperador"
        return "interior_llegador"

    if lat in ("EI", "ED"):
        goals   = float(row.get("goals") or 0) / mins * 90
        assists = float(row.get("assists") or 0) / mins * 90
        return "extremo_vertical" if goals >= assists else "extremo_asociativo"

    if lat == "DL":
        goals   = float(row.get("goals") or 0) / mins * 90
        assists = float(row.get("assists") or 0) / mins * 90
        return "delantero_rematador" if goals >= assists else "delantero_movil"

    if lat == "PO":
        return "portero"

    return None


def build_lateral_map(enriched_path: Path, master_path: Path) -> pd.DataFrame:
    """
    Devuelve un DataFrame con columnas:
      name, lateral_pos, role_type
    indexado por nombre canonico (minusculas sin acentos).

    Cacheado en memoria — se llama una vez por arranque.
    """
    key = str(enriched_path)
    if key in _CACHE:
        return _CACHE[key]

    # ── 1. Inferir lateral_pos desde enriched ────────────────────────────────
    try:
        enr = pd.read_parquet(
            enriched_path,
            columns=["name", "position_group", "leftside_passes",
                     "rightside_passes", "minutes"],
        )
        enr["leftside_passes"]  = pd.to_numeric(enr["leftside_passes"],  errors="coerce").fillna(0)
        enr["rightside_passes"] = pd.to_numeric(enr["rightside_passes"], errors="coerce").fillna(0)
        enr["_total_side"]      = enr["leftside_passes"] + enr["rightside_passes"]

        # Agregar por jugador: suma de pases por lado en toda la carrera
        agg = (
            enr[enr["_total_side"] >= 1]
            .groupby("name", as_index=False)
            .agg(
                position_group=("position_group", "last"),
                left_sum=("leftside_passes",  "sum"),
                right_sum=("rightside_passes", "sum"),
            )
        )
        agg["_ratio"] = agg["left_sum"] / (agg["left_sum"] + agg["right_sum"] + 1e-9)

        # Filtrar jugadores con pocos pases registrados (< 50 total) → lateral_pos = None
        agg["_valid"] = (agg["left_sum"] + agg["right_sum"]) >= 50
        agg["lateral_pos"] = agg.apply(
            lambda r: _infer_pos_code(r["position_group"], r["_ratio"])
            if r["_valid"] else None,
            axis=1,
        )
        lateral_df = agg[["name", "lateral_pos"]].copy()
    except Exception:
        lateral_df = pd.DataFrame(columns=["name", "lateral_pos"])

    # ── 2. Inferir role_type desde master_players ─────────────────────────────
    try:
        mp = pd.read_parquet(
            master_path,
            columns=["name", "minutes", "crosses_completed", "tackles_won",
                     "interceptions", "key_passes", "goals", "assists",
                     "passes_completed_pct"],
        )
        # Tomar la fila con más minutos por jugador (temporada más representativa)
        mp["minutes"] = pd.to_numeric(mp["minutes"], errors="coerce").fillna(0)
        mp = mp.loc[mp.groupby("name")["minutes"].idxmax()].copy()

        merged = lateral_df.merge(mp, on="name", how="left")
        merged["role_type"] = merged.apply(_infer_role_type, axis=1)
        result = merged[["name", "lateral_pos", "role_type"]].copy()
    except Exception:
        result = lateral_df.copy()
        result["role_type"] = None

    _CACHE[key] = result
    return result


def lateral_pos_label(code: str | None) -> str:
    """Convierte 'LI' → 'Lateral izquierdo (LI)', etc."""
    if not code:
        return "n/d"
    return LATERAL_LABELS.get(code, code)


def role_type_label(code: str | None) -> str:
    if not code:
        return "n/d"
    return ROLE_TYPE_LABELS.get(code, code)


def roles_for_lateral(lat_code: str | None) -> list[str]:
    """Devuelve lista de role_type keys válidos para un lateral_pos dado."""
    if not lat_code:
        return list(ROLE_TYPE_LABELS.keys())
    return LATERAL_TO_ROLES.get(lat_code, list(ROLE_TYPE_LABELS.keys()))
