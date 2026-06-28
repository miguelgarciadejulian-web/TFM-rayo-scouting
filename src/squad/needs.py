# -*- coding: utf-8 -*-
"""
needs.py — Análisis automático de necesidades de la plantilla
=============================================================

PROPÓSITO:
    Determina qué PERFILES FALTAN en la plantilla del Rayo y cuáles están
    sobre-representados, comparando la plantilla actual con una plantilla
    tipo objetivo generada dinámicamente desde la formación del club.

ALGORITMO:
    1. Se lee la formación base del club de config/club_profile.yaml
       (ej: "4-2-3-1").
    2. Se genera un TARGET_TEMPLATE: roles mínimos necesarios
       (1 titular + 1 suplente para roles críticos).
    3. Se infiere el rol de CADA jugador actual usando player_profile.py.
    4. Se compara actual vs objetivo:
       - HUECO: rol necesitado con 0 jugadores → prioridad ALTA
       - ESCASO: rol con 1 jugador sin suplente → prioridad MEDIA
       - CUBIERTO: rol con titular + suplente → OK
       - EXCESO: rol con más jugadores de los necesarios → candidatos a venta

SALIDA:
    analyze_needs() → dict con:
        - gaps: list[dict] roles que faltan (prioridad alta)
        - thin: list[dict] roles escasos (prioridad media)
        - excess: list[dict] roles sobre-representados
        - summary: resumen ejecutivo

CONSUMIDO POR:
    - src/fit/player_fit.py  → compatibilidad_plantilla
    - src/fit/decisions.py   → recomendaciones de fichar/vender
    - dashboard/pages/home.py → alertas de necesidades
    - dashboard/pages/decisiones.py → explorador de fichajes

DATOS DE ENTRADA:
    - config/squad_2526.yaml (plantilla con 30 jugadores)
    - config/club_profile.yaml (formación base, presupuesto)
    - player_seasons_enriched.parquet (perfiles inferidos)
"""
from __future__ import annotations
import unicodedata
from pathlib import Path

import pandas as pd

from src.profiling.player_profile import (
    add_role_percentiles, profile_player_row, ROLE_LABELS,
)

# ── Mapeo formacion → necesidades minimas por rol ─────────────────────────────
# Cada formacion define cuantos jugadores de cada rol necesita la plantilla
# (titular + suplente donde aplica). Fuente: club_profile.yaml → base_formation.
# Cada template define la plantilla COMPLETA de 25 jugadores por formación:
# 1 titular + profundidad de banca según importancia táctica del rol.
# Total garantizado: 25 jugadores por formación.
SQUAD_CAP = 25

_FORMATION_TEMPLATES: dict[str, dict[str, int]] = {
    "4-2-3-1": {  # suma = 25
        "portero": 3,
        "central_dominador": 1,
        "central_corrector": 3,
        "lateral_ofensivo": 2,
        "lateral_defensivo": 2,
        "mediocentro_organizador": 2,
        "mediocentro_recuperador": 2,
        "interior_llegador": 2,
        "extremo_vertical": 2,
        "extremo_asociativo": 2,
        "delantero_rematador": 2,
        "delantero_movil": 2,
    },
    "4-3-3": {  # suma = 25
        "portero": 3,
        "central_dominador": 1,
        "central_corrector": 3,
        "lateral_ofensivo": 2,
        "lateral_defensivo": 2,
        "mediocentro_organizador": 2,
        "mediocentro_recuperador": 2,
        "interior_llegador": 3,
        "extremo_vertical": 3,
        "extremo_asociativo": 2,
        "delantero_rematador": 1,
        "delantero_movil": 1,
    },
    "4-4-2": {  # suma = 25
        "portero": 3,
        "central_dominador": 1,
        "central_corrector": 3,
        "lateral_ofensivo": 2,
        "lateral_defensivo": 2,
        "mediocentro_organizador": 2,
        "mediocentro_recuperador": 2,
        "interior_llegador": 2,
        "extremo_vertical": 2,
        "extremo_asociativo": 2,
        "delantero_rematador": 2,
        "delantero_movil": 2,
    },
    "3-5-2": {  # suma = 25
        "portero": 3,
        "central_dominador": 2,
        "central_corrector": 3,
        "lateral_ofensivo": 2,
        "lateral_defensivo": 1,
        "mediocentro_organizador": 2,
        "mediocentro_recuperador": 2,
        "interior_llegador": 2,
        "extremo_vertical": 2,
        "extremo_asociativo": 2,
        "delantero_rematador": 2,
        "delantero_movil": 2,
    },
}

_DEFAULT_FORMATION = "4-2-3-1"


def build_target_template(club_profile: dict | None = None) -> tuple[dict[str, int], str]:
    """
    Construye el TARGET_TEMPLATE dinamicamente desde la formacion del club.

    Retorna (template_dict, formation_str) para poder mostrar la formacion
    usada en la UI y auditar de donde vienen los numeros.

    Fuente de datos:
      1. club_profile["tactics"]["base_formation"]  (club_profile.yaml)
      2. Fallback: DEFAULT_FORMATION si la formacion no esta mapeada
    """
    formation = _DEFAULT_FORMATION
    if club_profile:
        formation = (club_profile.get("tactics", {}) or {}).get(
            "base_formation", _DEFAULT_FORMATION
        ) or _DEFAULT_FORMATION

    # Normalizar: "4 2 3 1" → "4-2-3-1", etc.
    formation = str(formation).strip().replace(" ", "-")

    template = _FORMATION_TEMPLATES.get(formation)
    if template is None:
        # Formacion desconocida: intentar con solo los primeros 5 chars
        for key in _FORMATION_TEMPLATES:
            if key in formation or formation in key:
                template = _FORMATION_TEMPLATES[key]
                formation = key
                break
    if template is None:
        template = _FORMATION_TEMPLATES[_DEFAULT_FORMATION]
        formation = _DEFAULT_FORMATION

    return dict(template), formation


# Compatibilidad con importaciones antiguas: TARGET_TEMPLATE estatico como fallback.
# Reemplazado dinamicamente en squad_needs() usando build_target_template().
TARGET_TEMPLATE = _FORMATION_TEMPLATES[_DEFAULT_FORMATION]


CFG_POS_GROUP = {
    "GK": "GK",
    "CB": "DEF", "RB": "DEF", "LB": "DEF", "RWB": "DEF", "LWB": "DEF",
    "DM": "MID", "CM": "MID", "AM": "MID",
    "RW": "FWD", "LW": "FWD", "ST": "FWD", "CF": "FWD",
}


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()


def _surname(name: str) -> str:
    n = _norm(name).replace(".", " ").strip()
    parts = [p for p in n.split() if len(p) > 1]
    return parts[-1] if parts else n


def match_squad_to_enriched(squad_players: list[dict], enriched: pd.DataFrame) -> pd.DataFrame:
    """Empareja cada jugador del club_profile con su fila Opta mas reciente.

    Devuelve un DataFrame con columnas del enriquecido + age/contract del club.
    """
    enr = enriched.copy()
    enr["_surname"] = enr["name"].map(_surname)
    # priorizar temporada mas reciente
    season_order = {"2025-2026": 5, "2025": 4, "2024-2025": 3, "2023-2024": 2, "2022-2023": 1}
    enr["_so"] = enr["season"].map(season_order).fillna(0)

    rows = []
    for p in squad_players:
        sn = _surname(p["name"])
        want_grp = CFG_POS_GROUP.get(str(p.get("position", "")).upper())
        cand = enr[enr["_surname"] == sn]
        if cand.empty:
            # intento por nombre contiene
            cand = enr[enr["name"].map(_norm).str.contains(sn, na=False)]
        # desambiguar por grupo posicional esperado (evita colisiones de apellido)
        if want_grp and "position_group" in cand.columns:
            same_grp = cand[cand["position_group"] == want_grp]
            if not same_grp.empty:
                cand = same_grp
        if cand.empty:
            rows.append({"name": p["name"], "matched": False, "age": p.get("age"),
                         "position_cfg": p.get("position"), "contract_end": p.get("contract_end"),
                         "market_value": p.get("market_value")})
            continue
        # preferir filas del propio Rayo; si no hay, la temporada mas reciente
        rayo = cand[cand["team"].map(_norm).str.contains("rayo", na=False)]
        pick_from = rayo if not rayo.empty else cand
        best = pick_from.sort_values("_so", ascending=False).iloc[0]
        r = best.to_dict()
        r.update({"name": p["name"], "matched": True, "age": p.get("age"),
                  "position_cfg": p.get("position"), "contract_end": p.get("contract_end"),
                  "market_value": p.get("market_value")})
        rows.append(r)
    return pd.DataFrame(rows)


def profile_squad(club_profile: dict, enriched: pd.DataFrame,
                  league: str = "Spain_Primera_Division") -> pd.DataFrame:
    """Perfila cada jugador del Rayo (rol inferido) usando el pool de su liga."""
    squad = club_profile.get("squad_2025_26", {})
    players = [p for grp in squad.values() for p in grp]

    pool = enriched[enriched["league"] == league].copy()
    enr_pct = add_role_percentiles(pool)
    matched = match_squad_to_enriched(players, enr_pct)

    out = []
    for _, row in matched.iterrows():
        rec = {"name": row["name"], "age": row.get("age"),
               "position_cfg": row.get("position_cfg"),
               "contract_end": row.get("contract_end"),
               "market_value": row.get("market_value"),
               "matched": row.get("matched", False)}
        if row.get("matched") and pd.notna(row.get("position_group")):
            prof = profile_player_row(row, age=row.get("age"))
            rec.update({
                "primary_role": prof["primary_role"],
                "primary_role_label": prof["primary_role_label"],
                "secondary_roles": prof["secondary_roles"],
                "style_label": prof["style_label"],
                "strengths": prof["strengths"],
                "weaknesses": prof["weaknesses"],
                "risk_level": prof["risk_level"],
                "potential": prof["potential"],
                "confidence": prof["confidence"],
                "minutes": row.get("minutes"),
            })
        else:
            rec.update({"primary_role": None, "primary_role_label": "Sin datos Opta",
                        "secondary_roles": [], "style_label": "n/d",
                        "strengths": [], "weaknesses": [], "risk_level": "n/d",
                        "potential": "n/d", "confidence": "insuficiente", "minutes": None})
        out.append(rec)
    return pd.DataFrame(out)


def squad_needs(squad_profile: pd.DataFrame, club_profile: dict | None = None) -> dict:
    """
    Compara la plantilla perfilada con la plantilla tipo objetivo.

    El objetivo se deriva DINAMICAMENTE de club_profile["tactics"]["base_formation"].
    Si club_profile es None, usa la formacion por defecto (4-2-3-1).
    """
    target, formation_used = build_target_template(club_profile)

    counts: dict[str, int] = {}
    for _, r in squad_profile.iterrows():
        role = r.get("primary_role")
        if role:
            counts[role] = counts.get(role, 0) + 1

    present, over, missing, reinforce = {}, [], [], []
    for role, need in target.items():
        have = counts.get(role, 0)
        present[role] = have
        if have == 0:
            missing.append(role)
        elif have > need + 1:
            over.append(role)
        elif have < need:
            reinforce.append(role)

    # refuerzo por edad: roles cuyo titular es veterano (>=31) o contrato acaba 2026
    aging = []
    for _, r in squad_profile.iterrows():
        age = r.get("age")
        end = str(r.get("contract_end") or "")
        role = r.get("primary_role")
        if role and ((age and float(age) >= 31) or end[:4] == "2026"):
            aging.append({"name": r["name"], "role": role,
                          "role_label": ROLE_LABELS.get(role, role),
                          "age": age, "contract_end": end[:10]})

    n_players = sum(counts.values())
    return {
        "role_counts": {ROLE_LABELS.get(k, k): v for k, v in sorted(counts.items())},
        "present": present,
        "over_represented": [ROLE_LABELS.get(r, r) for r in over],
        "missing": [ROLE_LABELS.get(r, r) for r in missing],
        "reinforce": [ROLE_LABELS.get(r, r) for r in reinforce],
        "aging_or_expiring": aging,
        # Metadatos para transparencia / UI
        "formation_used": formation_used,
        "target_template": {ROLE_LABELS.get(k, k): v for k, v in target.items()},
        "squad_cap": SQUAD_CAP,
        "n_profiled": n_players,
    }
