"""
decisions.py — Motor de decisiones deportivas automáticas
=========================================================

PROPÓSITO:
    Genera recomendaciones automáticas de gestión deportiva para CADA jugador
    de la plantilla: renovar, vender, ceder o fichar sustituto. Las decisiones
    se derivan 100% por reglas cuantitativas sin intervención manual.

REGLAS DE DECISIÓN:
    RENOVAR: jugador clave (rendimiento alto) + contrato ≤ 2 años restantes
             + rol escaso en plantilla.
    VENDER:  veterano > 30 años + rol sobre-representado + valor de mercado
             todavía aceptable (ventana de oportunidad).
    CEDER:   jugador joven (< 23) + < 500 minutos la temporada pasada +
             suplente detrás de un titular consolidado.
    FICHAR:  rol detectado como "necesidad" por squad/needs.py + no hay
             alternativa interna viable.

FUNCIÓN PRINCIPAL:
    generate_decisions(squad_profile, needs, enriched_df)
    → list[dict] con: jugador, decisión, motivo, prioridad, score

CONSUMIDO POR:
    - dashboard/pages/decisiones.py (visualización de recomendaciones)
    - dashboard/pages/home.py (alertas en el panel principal)

DATOS DE ENTRADA:
    - data/processed/squad_profile.json (perfiles de plantilla)
    - squad/needs.py (necesidades detectadas)
    - player_seasons_enriched.parquet (rendimiento actual)
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

    # FICHAR: necesidades — razones especificas con contexto de plantilla
    role_counts = needs.get("role_counts", {})
    target_tpl = needs.get("target_template", {})

    # Mapa role_label -> lista de jugadores aging/expiring para ese rol
    aging_by_role: dict[str, list[str]] = {}
    for ae in needs.get("aging_or_expiring", []):
        lbl = ae.get("role_label", "")
        if lbl:
            aging_by_role.setdefault(lbl, []).append(
                f"{ae['name']} ({int(ae['age'])} anios)"
            )

    _PLURAL = {
        "Portero": "porteros", "Central dominador": "centrales dominadores",
        "Central corrector": "centrales correctores",
        "Lateral ofensivo": "laterales ofensivos",
        "Lateral defensivo": "laterales defensivos",
        "Mediocentro organizador": "mediocentros organizadores",
        "Mediocentro recuperador": "mediocentros recuperadores",
        "Interior llegador": "interiores llegadores",
        "Extremo vertical": "extremos verticales",
        "Extremo asociativo": "extremos asociativos",
        "Delantero rematador": "delanteros rematadores",
        "Delantero movil": "delanteros moviles",
    }

    fichar = []
    for r in needs.get("missing", []):
        target = target_tpl.get(r, 1)
        aging_ref = aging_by_role.get(r, [])
        rpl = _PLURAL.get(r, r.lower())
        if aging_ref:
            reason = (f"Sin {rpl} en plantilla (objetivo: {target}). "
                      f"Referencia envejecida: {', '.join(aging_ref[:2])}.")
        else:
            reason = (f"Sin {rpl} en plantilla. "
                      f"Rol clave sin cobertura (objetivo: {target} jugadores).")
        fichar.append({"role": r, "priority": "alta", "reason": reason})

    for r in needs.get("reinforce", []):
        have = role_counts.get(r, 0)
        target = target_tpl.get(r, 2)
        aging_ref = aging_by_role.get(r, [])
        rpl = _PLURAL.get(r, r.lower() + "s")
        if aging_ref:
            reason = (f"Solo {have} de {target} {rpl} en plantilla. "
                      f"Referencia en declive: {', '.join(aging_ref[:2])}.")
        else:
            reason = (f"Solo {have} de {target} {rpl} en plantilla. "
                      f"Refuerzo necesario para garantizar cobertura.")
        fichar.append({"role": r, "priority": "media", "reason": reason})

    return {"renovar": renovar, "vender": vender, "ceder": ceder, "fichar": fichar}
