"""
decisions.py
============
Decisiones deportivas AUTOMATICAS por reglas en Python a partir de la plantilla
perfilada (squad_profile.json) y las necesidades detectadas:

  - renovar : jugadores clave con contrato proximo a expirar
  - vender  : veteranos amortizables / perfiles sobre-representados con valor
  - ceder   : jovenes con pocos minutos que necesitan rodaje
  - fichar  : roles que faltan o hay que reforzar (necesidades)

Cada recomendacion incluye un motivo generado por reglas. Configurable.
"""
from __future__ import annotations
import pandas as pd

from src.profiling.player_profile import ROLE_LABELS


def _year(end) -> int:
    try:
        return int(str(end)[:4])
    except (TypeError, ValueError):
        return 9999


def _age(a) -> float:
    try:
        return float(a)
    except (TypeError, ValueError):
        return 0.0


def squad_decisions(squad: list[dict], needs: dict, season_end: int = 2026) -> dict:
    """Genera las cuatro listas de decisiones sobre la plantilla actual."""
    over = set(needs.get("over_represented", []))
    renovar, vender, ceder = [], [], []

    for p in squad:
        name = p.get("name")
        age = _age(p.get("age"))
        end = _year(p.get("contract_end"))
        mv = p.get("market_value") or 0
        role = p.get("primary_role")
        role_lbl = p.get("primary_role_label", "n/d")
        conf = p.get("confidence", "insuficiente")
        minutes = p.get("minutes") or 0

        # CEDER: joven con pocos minutos
        if age and age <= 21 and (minutes or 0) < 900 and conf in ("insuficiente", "baja"):
            ceder.append({"name": name, "role": role_lbl, "age": age,
                          "reason": "Joven con pocos minutos: cesion para acumular rodaje."})
            continue

        # VENDER: veterano amortizable o perfil sobrante con valor
        if age >= 32 and end <= season_end + 1:
            vender.append({"name": name, "role": role_lbl, "age": age, "market_value": mv,
                           "reason": f"Veterano ({int(age)}) con contrato hasta {end}: amortizable."})
            continue
        if role_lbl in over and mv >= 3_000_000 and age >= 28:
            vender.append({"name": name, "role": role_lbl, "age": age, "market_value": mv,
                           "reason": f"Perfil sobre-representado ({role_lbl}) con valor de venta."})
            continue

        # RENOVAR: clave (buen rol, no sobrante, edad util) con contrato corto
        if end <= season_end + 1 and age and 22 <= age <= 30 and conf in ("alta", "media") \
                and role_lbl not in over:
            renovar.append({"name": name, "role": role_lbl, "age": age, "contract_end": end,
                            "reason": f"Titular util ({role_lbl}, {int(age)} anos) con contrato hasta {end}: blindar."})

    # FICHAR: necesidades
    fichar = []
    for r in needs.get("missing", []):
        fichar.append({"role": r, "priority": "alta",
                       "reason": "Perfil inexistente en la plantilla."})
    for r in needs.get("reinforce", []):
        fichar.append({"role": r, "priority": "media",
                       "reason": "Perfil escaso: conviene reforzar."})

    return {"renovar": renovar, "vender": vender, "ceder": ceder, "fichar": fichar}
