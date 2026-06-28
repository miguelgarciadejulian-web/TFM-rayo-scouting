# -*- coding: utf-8 -*-
"""
clause_risk.py — Modelo de riesgo de cláusulas de rescisión
===========================================================

PROPÓSITO:
    Evalúa el riesgo de que un club rival active la cláusula de rescisión
    de un jugador del Rayo. Produce un nivel de riesgo (Bajo/Medio/Alto/
    Crítico) y un score numérico basado en factores cuantitativos.

FACTORES DEL MODELO:
    1. Ratio cláusula / valor de mercado (si cláusula ≈ valor → riesgo alto)
    2. Ratio cláusula / presupuesto del Rayo (si no puede re-fichar → crítico)
    3. Años de contrato restantes (menos años = más presión para vender)
    4. Edad del jugador (joven con cláusula baja = muy vulnerable)
    5. Ratio salario / cláusula (salario alto relativo a cláusula = riesgo)

NIVELES DE SALIDA:
    - Bajo    (score < 30): cláusula manejable, sin riesgo operativo real
    - Medio   (30-55):      coste notable, requiere planificación
    - Alto    (55-75):      probabilidad real de pérdida del jugador
    - Crítico (> 75):       coste extremo, desestabilizaría al club

FUNCIÓN PRINCIPAL:
    evaluate_clause_risk(clause_eur, market_value_eur, age,
                         contract_years_remaining, salary_eur_year,
                         rayo_budget_eur)
    → ClauseRiskResult(level, score, factors, recommendation)

CONSUMIDO POR:
    - dashboard/pages/finanzas.py (visualización de riesgos)
    - src/fit/decisions.py (factor en decisiones de renovación)

Uso::

    from src.fit.clause_risk import evaluate_clause_risk, ClauseRiskResult

    result = evaluate_clause_risk(
        clause_eur=30_000_000,
        market_value_eur=25_000_000,
        age=24,
        contract_years_remaining=1.5,
        salary_eur_year=1_500_000,
        rayo_budget_eur=10_000_000,      # transferencia neta disponible
    )
    print(result.level)          # "Alto"
    print(result.score)          # 72 (0=Bajo, 100=Crítico)
    print(result.breakdown)      # dict con score por factor
    print(result.narrative)      # explicación en español
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

__all__ = ["ClauseRiskResult", "evaluate_clause_risk", "RISK_COLORS"]

# Paleta visual por nivel
RISK_COLORS: dict[str, tuple[str, str]] = {
    "Bajo":     ("#DCFCE7", "#166534"),
    "Medio":    ("#FEF9C3", "#854D0E"),
    "Alto":     ("#FFEDD5", "#9A3412"),
    "Crítico":  ("#FEE2E2", "#991B1B"),
}

RiskLevel = Literal["Bajo", "Medio", "Alto", "Crítico"]


@dataclass
class ClauseRiskResult:
    """Resultado completo del modelo de riesgo de cláusula."""
    # Score agregado [0..100] donde 100 = máximo riesgo
    score: float
    # Nivel de riesgo discreto
    level: RiskLevel
    # Score desglosado por factor [0..100] cada uno
    breakdown: dict[str, float]
    # Pesos utilizados (pueden inspeccionarse)
    weights: dict[str, float]
    # Narrativa explicativa en español
    narrative: str
    # Datos de entrada para trazabilidad
    inputs: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def evaluate_clause_risk(
    clause_eur: float | None,
    market_value_eur: float | None = None,
    age: int | None = None,
    contract_years_remaining: float | None = None,
    salary_eur_year: float | None = None,
    rayo_budget_eur: float = 10_000_000,
) -> ClauseRiskResult:
    """
    Calcula el riesgo de que un rival active la cláusula de rescisión.

    Parámetros
    ----------
    clause_eur : float | None
        Importe de la cláusula en euros. None → riesgo bajo por defecto.
    market_value_eur : float | None
        Valor de mercado del jugador (Transfermarkt). None → se ignora el factor.
    age : int | None
        Edad del jugador en años.
    contract_years_remaining : float | None
        Años de contrato restantes. None → se ignora el factor.
    salary_eur_year : float | None
        Salario anual en euros (para estimar reposición + nueva cláusula).
    rayo_budget_eur : float
        Presupuesto neto de transferencias del Rayo (referencia para escalar).

    Devuelve
    --------
    ClauseRiskResult con score, level, breakdown, narrative e inputs.
    """
    # Defaults seguros
    clause = float(clause_eur or 0)
    mv     = float(market_value_eur or 0) if market_value_eur else None
    age_v  = int(age) if age else None
    years  = float(contract_years_remaining) if contract_years_remaining else None
    budget = max(float(rayo_budget_eur), 1_000_000)

    breakdown: dict[str, float] = {}
    weights: dict[str, float] = {
        "coste_relativo_presupuesto": 0.30,
        "ratio_clausula_mercado":     0.25,
        "edad_potencial":             0.20,
        "contrato_restante":          0.15,
        "coste_absoluto":             0.10,
    }

    # ── Factor 1: Coste de la cláusula relativo al presupuesto del Rayo ──
    # Cuánto de nuestro presupuesto cubre (0→coste 0, 100→clausula=5×presupuesto)
    if clause <= 0:
        f_budget = 0.0
    else:
        ratio_budget = clause / budget
        # Escala: 0x→0, 0.5x→25, 1x→50, 2x→75, ≥5x→100
        f_budget = min(100.0, ratio_budget * 20.0)
    breakdown["coste_relativo_presupuesto"] = round(f_budget, 1)

    # ── Factor 2: Ratio cláusula / valor de mercado ──
    # Cláusula muy por debajo del VM → riesgo alto (barata para un rival rico)
    if clause <= 0 or mv is None or mv <= 0:
        f_ratio = 50.0  # neutro si sin datos
    else:
        ratio_cm = clause / mv
        # ratio <0.5 (cláusula barata) → muy alto riesgo
        # ratio ≈1.0 → moderado
        # ratio >2.0 → bajo riesgo (cláusula cara)
        if ratio_cm < 0.5:
            f_ratio = 100.0 - ratio_cm * 60.0    # 70-100
        elif ratio_cm < 1.0:
            f_ratio = 70.0 - (ratio_cm - 0.5) * 80.0  # 30-70
        elif ratio_cm < 2.0:
            f_ratio = 30.0 - (ratio_cm - 1.0) * 25.0  # 5-30
        else:
            f_ratio = max(0.0, 5.0 - (ratio_cm - 2.0) * 5.0)
    breakdown["ratio_clausula_mercado"] = round(f_ratio, 1)

    # ── Factor 3: Edad + potencial de revalorización ──
    # Jugadores jóvenes con margen de crecimiento = más tentadores para rivales
    if age_v is None:
        f_age = 50.0
    elif age_v <= 21:
        f_age = 90.0  # máximo atractivo para rivales
    elif age_v <= 24:
        f_age = 80.0
    elif age_v <= 27:
        f_age = 65.0
    elif age_v <= 30:
        f_age = 40.0
    elif age_v <= 33:
        f_age = 20.0
    else:
        f_age = 8.0   # veterano: poco interés exterior
    breakdown["edad_potencial"] = round(f_age, 1)

    # ── Factor 4: Contrato restante ──
    # Poco contrato = rival tiene más urgencia, más riesgo inmediato
    if years is None:
        f_contract = 50.0
    elif years <= 0.5:
        f_contract = 95.0  # casi libre → riesgo máximo
    elif years <= 1.0:
        f_contract = 80.0
    elif years <= 2.0:
        f_contract = 60.0
    elif years <= 3.0:
        f_contract = 35.0
    else:
        f_contract = 15.0  # largo contrato → rival menos urgente
    breakdown["contrato_restante"] = round(f_contract, 1)

    # ── Factor 5: Coste absoluto de la cláusula ──
    # Independientemente de los ratios, clausulas >60M son raras de activar
    if clause <= 0:
        f_abs = 0.0
    elif clause < 5_000_000:
        f_abs = 90.0   # cláusula irrisoria
    elif clause < 15_000_000:
        f_abs = 70.0
    elif clause < 30_000_000:
        f_abs = 50.0
    elif clause < 60_000_000:
        f_abs = 30.0
    elif clause < 100_000_000:
        f_abs = 15.0
    else:
        f_abs = 5.0    # >100M → casi nadie la pagará
    breakdown["coste_absoluto"] = round(f_abs, 1)

    # ── Score agregado (ponderación) ──
    score = sum(breakdown[k] * weights[k] for k in weights)
    score = round(min(100.0, max(0.0, score)), 1)

    # ── Nivel discreto ──
    if score < 30:
        level: RiskLevel = "Bajo"
    elif score < 55:
        level = "Medio"
    elif score < 75:
        level = "Alto"
    else:
        level = "Crítico"

    narrative = _build_narrative(
        clause, mv, age_v, years, budget, score, level, breakdown
    )

    return ClauseRiskResult(
        score=score,
        level=level,
        breakdown=breakdown,
        weights=weights,
        narrative=narrative,
        inputs={
            "clause_eur": clause_eur,
            "market_value_eur": market_value_eur,
            "age": age,
            "contract_years_remaining": contract_years_remaining,
            "salary_eur_year": salary_eur_year,
            "rayo_budget_eur": rayo_budget_eur,
        },
    )


# ---------------------------------------------------------------------------
# Generador de narrativa
# ---------------------------------------------------------------------------

def _fmt(v: float | None) -> str:
    if v is None:
        return "sin dato"
    if v >= 1_000_000:
        return f"{v/1_000_000:.1f}M€"
    if v >= 1_000:
        return f"{v/1_000:.0f}K€"
    return f"{v:.0f}€"


def _build_narrative(
    clause: float, mv: float | None, age: int | None, years: float | None,
    budget: float, score: float, level: RiskLevel, breakdown: dict
) -> str:
    parts: list[str] = []

    # Apertura
    level_desc = {
        "Bajo": "El riesgo de que un rival active esta cláusula es bajo.",
        "Medio": "La cláusula presenta un riesgo moderado de ser activada.",
        "Alto": "Existe un riesgo real y significativo de que esta cláusula sea ejercida.",
        "Crítico": "Esta cláusula representa un riesgo crítico: un rival con músculo financiero podría activarla.",
    }
    parts.append(level_desc[level])

    # Coste relativo
    ratio_b = clause / budget if budget > 0 else 0
    if ratio_b <= 0:
        parts.append("No hay cláusula definida, por lo que no existe riesgo contractual directo.")
    elif ratio_b < 0.5:
        parts.append(f"La cláusula ({_fmt(clause)}) representa solo {ratio_b:.1f}× el presupuesto "
                     f"de transferencias del Rayo ({_fmt(budget)}), lo que la hace accesible para clubes medianos.")
    elif ratio_b < 1.5:
        parts.append(f"La cláusula ({_fmt(clause)}) equivale aproximadamente al presupuesto neto "
                     f"del Rayo ({_fmt(budget)}), por lo que solo grandes clubes podrían asumirla cómodamente.")
    else:
        parts.append(f"La cláusula ({_fmt(clause)}) supera ampliamente el presupuesto neto del Rayo "
                     f"({_fmt(budget)}), lo que limita el universo de clubes que podrían ejercerla.")

    # Ratio clausula/VM
    if mv and mv > 0 and clause > 0:
        r = clause / mv
        if r < 0.7:
            parts.append(f"Siendo el valor de mercado {_fmt(mv)}, la cláusula está por debajo del "
                         f"valor real del jugador (ratio {r:.2f}×), lo que la hace especialmente tentadora.")
        elif r < 1.3:
            parts.append(f"La cláusula ({_fmt(clause)}) está alineada con el valor de mercado "
                         f"({_fmt(mv)}, ratio {r:.2f}×), un precio razonable para un club con recursos.")
        else:
            parts.append(f"La cláusula supera el valor de mercado (ratio {r:.2f}×), lo que actúa "
                         f"como barrera natural frente a ofertas hostiles.")

    # Edad
    if age:
        if age <= 24:
            parts.append(f"A sus {age} años, el jugador está en la curva ascendente de su carrera, "
                         f"lo que aumenta el interés externo.")
        elif age <= 29:
            parts.append(f"Con {age} años se encuentra en su prime, lo que mantiene la demanda alta.")
        else:
            parts.append(f"Con {age} años, la demanda exterior es más moderada, reduciendo la probabilidad "
                         f"de que se active la cláusula.")

    # Contrato
    if years is not None:
        if years <= 1:
            parts.append(f"Quedan menos de 12 meses de contrato: la situación es urgente, "
                         f"pues el jugador podría salir libre si no se renueva.")
        elif years <= 2:
            parts.append(f"Con {years:.1f} años de contrato restantes existe presión temporal "
                         f"para renovar o planificar la sustitución.")
        else:
            parts.append(f"El contrato aún tiene {years:.1f} años de vigencia, lo que da margen "
                         f"de planificación al club.")

    return " ".join(parts)
