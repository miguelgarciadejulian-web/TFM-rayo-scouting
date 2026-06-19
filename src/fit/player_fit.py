# -*- coding: utf-8 -*-
"""
player_fit.py
=============
Encaje AUTOMATICO de un fichaje potencial con el Rayo, por reglas en Python:

  - compatibilidad_plantilla   : cubre un hueco (rol que falta/escaso) vs sobra
  - compatibilidad_entrenador  : afinidad del rol con el estilo del tecnico
  - valor_estrategico          : hueco + potencial/edad + nivel del rol
  - impacto_deportivo          : nivel del rol (percentil) + necesidad cubierta

Todo deriva de los roles inferidos (player_profile) y del analisis de plantilla
(squad.needs); nada se escribe a mano.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from src.profiling.player_profile import ROLE_LABELS
from src.fit.dynamic_dna import get_coach_affinity


def evaluate_player_fit(player_profile: dict, squad_needs_dict: dict,
                        coach_style_main: str | None = None) -> dict:
    """
    Encaje de un jugador potencial con el Rayo.

    La afinidad con el entrenador se deriva dinamicamente desde los ejes reales
    del tecnico actual (coach_profiles.json via dynamic_dna.get_coach_affinity),
    eliminando el diccionario estatico COACH_ROLE_AFFINITY anterior.
    """
    role = player_profile.get("primary_role")
    role_label = ROLE_LABELS.get(role, "n/d") if role else "n/d"
    primary_score = player_profile.get("primary_score")
    if primary_score is None or pd.isna(primary_score):
        primary_score = 50.0

    missing = set(squad_needs_dict.get("missing", []))
    reinforce = set(squad_needs_dict.get("reinforce", []))
    over = set(squad_needs_dict.get("over_represented", []))

    # ── Compatibilidad con la plantilla ──────────────────────────────────────
    if role_label in missing:
        squad_compat, need_txt = 95.0, "cubre un perfil INEXISTENTE en la plantilla"
    elif role_label in reinforce:
        squad_compat, need_txt = 82.0, "refuerza un perfil escaso"
    elif role_label in over:
        squad_compat, need_txt = 35.0, "perfil ya sobre-representado"
    else:
        squad_compat, need_txt = 60.0, "perfil cubierto pero ampliable"

    # ── Compatibilidad con el estilo del entrenador (dinamico) ───────────────
    # Se obtiene del entrenador actual via coach_profiles.json + club_profile.yaml
    try:
        affinity_map = get_coach_affinity()
        aff = affinity_map.get(role, 0.5)
    except Exception:
        aff = 0.5   # neutro si falla la carga de datos
    coach_compat = float(np.clip(aff * 100, 0, 100))

    # ── Potencial/edad ───────────────────────────────────────────────────────
    pot = player_profile.get("potential", "")
    pot_score = {"muy alto": 95, "alto": 80, "estable": 65, "en meseta": 50,
                 "veterania": 35}.get(pot, 55)

    # ── Valor estrategico e impacto ──────────────────────────────────────────
    valor = round(0.45 * squad_compat + 0.30 * primary_score + 0.25 * pot_score, 1)
    impacto = round(0.6 * primary_score + 0.4 * squad_compat, 1)

    global_fit = round(0.4 * squad_compat + 0.25 * coach_compat +
                       0.2 * primary_score + 0.15 * pot_score, 1)

    return {
        "role_label": role_label,
        "compatibilidad_plantilla": squad_compat,
        "compatibilidad_plantilla_txt": need_txt,
        "compatibilidad_entrenador": coach_compat,
        "valor_estrategico": valor,
        "impacto_deportivo": impacto,
        "global_fit": global_fit,
        "global_fit_10": round(global_fit / 10, 1),
    }
