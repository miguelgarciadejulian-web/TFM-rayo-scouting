# -*- coding: utf-8 -*-
"""
coach_fit.py — Evaluación automática de entrenadores candidatos
===============================================================

PROPÓSITO:
    Calcula un SCORE DE COMPATIBILIDAD (0-100) para cada entrenador
    candidato al banquillo del Rayo Vallecano. Todo se infiere por
    reglas cuantitativas, sin opiniones subjetivas.

FACTORES EVALUADOS:
    1. ESTILO DE JUEGO (peso 40%): Compara los ejes de estilo del técnico
       (calculados en coach_style.py desde métricas Opta de sus equipos)
       con el ADN objetivo del Rayo (presión, verticalidad, intensidad).

    2. EXPERIENCIA LaLiga (peso 20%): Bonus por temporadas previas en
       Primera o Segunda División española (adaptación cultural).

    3. COMPATIBILIDAD CON PLANTILLA (peso 20%): Evalúa si los roles
       que favorece el técnico coinciden con los perfiles disponibles.

    4. CONTEXTO ECONÓMICO (peso 10%): Salario del técnico vs presupuesto
       del club, duración de contrato, cláusula de salida.

    5. RIESGOS (peso 10%): Factores negativos (despidos recientes,
       conflictos públicos, incompatibilidad con estrellas).

SALIDA:
    dict con: score, pros[], contras[], riesgos{deportivo, economico,
    clausula, adaptacion_laliga, incompatibilidad_plantilla}

DATOS DE ENTRADA:
    - src/profiling/coach_style.py (ejes de estilo calculados)
    - config/coach_history.yaml (historial de equipos)
    - config/rayo_dna.yaml / dynamic_dna.py (ADN objetivo)
    - config/coaches.yaml (datos contractuales)
    - src/squad/needs.py (necesidades de plantilla)

CONSUMIDO POR:
    - scripts/build_profiles.py → genera coach_profiles.json
    - dashboard/pages/entrenadores.py → visualización de scores
"""
from __future__ import annotations
import numpy as np
import pandas as pd

SPAIN_TOP = "Spain_Primera_Division"


def coach_laliga_seasons(history_entry: dict) -> int:
    n = 0
    for st in history_entry.get("stints", []):
        # se asume que el mapeo de equipo a liga se valida fuera; aqui contamos
        # por marca de equipo conocida de LaLiga via coverage si se pasa.
        n += len(st.get("seasons", [])) if st.get("_laliga") else 0
    return n


def _score_style(axes: dict, target: dict) -> tuple[float, dict]:
    """Score 0-100 de cercania del estilo al ADN objetivo (1 - dist normalizada)."""
    acc, wsum, detail = 0.0, 0.0, {}
    for axis, spec in target.items():
        v = axes.get(axis)
        if v is None or pd.isna(v):
            continue
        ideal, w = spec["ideal"], spec["weight"]
        closeness = 100 - min(abs(float(v) - ideal), 100)  # 100 = identico
        acc += w * closeness
        wsum += w
        detail[axis] = round(closeness, 1)
    return (round(acc / wsum, 1) if wsum else float("nan")), detail


def _laliga_seasons_from_coverage(coverage: dict) -> int:
    """Cuenta temporadas en equipos de LaLiga a partir del coverage calculado."""
    # coverage['matched'] = [(team_match, season), ...]; LaLiga si el team esta
    # en la lista de equipos LaLiga del coverage['teams'] no es trivial aqui,
    # por eso se calcula en build_profiles y se pasa como context['laliga_seasons'].
    return coverage.get("laliga_seasons", 0)


def evaluate_coach(name: str, profile: dict, context: dict, dna: dict,
                   squad_summary: dict | None = None) -> dict:
    """Evaluacion completa de un entrenador candidato."""
    axes = profile.get("axes", {})
    coverage = profile.get("coverage", {})
    target = dna["target_style"]
    cw = dna["context_weights"]
    eco = dna["economics"]

    style_score, style_detail = _score_style(axes, target)

    # ── Experiencia LaLiga ───────────────────────────────────────────────────
    laliga_seasons = int(context.get("laliga_seasons", 0))
    laliga_score = float(np.clip(laliga_seasons / 4 * 100, 0, 100))

    # ── Encaje presupuesto (salario) ─────────────────────────────────────────
    salary = context.get("salary_estimate_eur") or 0
    if salary <= 0:
        budget_score = 60.0
    elif salary <= eco["target_salary_eur"]:
        budget_score = 100.0
    elif salary <= eco["max_salary_eur"]:
        budget_score = float(np.clip(100 - (salary - eco["target_salary_eur"]) /
                                     (eco["max_salary_eur"] - eco["target_salary_eur"]) * 50, 0, 100))
    else:
        budget_score = 30.0

    # ── Compatibilidad con plantilla ─────────────────────────────────────────
    squad_compat = _squad_compatibility(axes, squad_summary)

    # ── Score global ponderado ───────────────────────────────────────────────
    style_w = 1 - (cw["laliga_experience"] + cw["budget_fit"] + cw["squad_compatibility"])
    parts = [(style_score, style_w), (laliga_score, cw["laliga_experience"]),
             (budget_score, cw["budget_fit"]), (squad_compat, cw["squad_compatibility"])]
    num = sum(s * w for s, w in parts if pd.notna(s))
    den = sum(w for s, w in parts if pd.notna(s))
    global_score = round(num / den, 1) if den else float("nan")

    # penalizacion por cobertura de datos parcial
    n_rows = coverage.get("n_rows", 0)
    if n_rows <= 1:
        global_score = round(global_score * 0.9, 1)

    pros, cons = _pros_cons(axes, style_detail, context, laliga_seasons,
                            budget_score, squad_compat, n_rows)
    risks = _risks(axes, context, laliga_seasons, salary, eco, squad_compat, n_rows)

    return {
        "name": name,
        "global_score": global_score,
        "score_10": round(global_score / 10, 1) if pd.notna(global_score) else None,
        "subscores": {
            "estilo": style_score, "experiencia_laliga": round(laliga_score, 1),
            "encaje_presupuesto": round(budget_score, 1), "compatibilidad_plantilla": squad_compat,
        },
        "style_detail": style_detail,
        "pros_auto": pros,
        "contras_auto": cons,
        "risks": risks,
        "data_partial": profile.get("data_partial", False),
        "coverage_n": n_rows,
    }


def _squad_compatibility(axes: dict, squad_summary: dict | None) -> float:
    """Compatibilidad del estilo del técnico con la plantilla actual (0-100).

    Penalizaciones cuando el técnico exige perfiles de los que la plantilla carece:
      - Alta posesión → necesita constructores (central dominador, organizador)
      - Extremos asociativos → si faltan
      - Alta presión → beneficia si hay recuperadores
      - Juego directo/vertical → compatible con delanteros móviles
    Bonificaciones cuando el estilo encaja con lo que hay disponible.

    Plantilla de referencia: 25 jugadores (SQUAD_CAP de needs.py).
    """
    if not squad_summary:
        return 60.0

    poss   = axes.get("posesion")
    trans  = axes.get("uso_transiciones")
    press  = axes.get("presion_alta")
    vert   = axes.get("verticalidad")
    off    = axes.get("tendencia_ofensiva")

    missing  = set(squad_summary.get("missing", []))
    reinforce = set(squad_summary.get("reinforce", []))
    gap_roles = missing | reinforce  # roles con carencia total o parcial

    base = 68.0

    # ── Penalizaciones por desajuste estilo ↔ carencias ──────────────────────
    # Posesión alta → necesita central dominador + organizador para la salida
    needs_buildup = bool(
        {"Central dominador", "Mediocentro organizador"} & gap_roles
    )
    if needs_buildup and pd.notna(poss) and poss >= 66:
        base -= 20
    elif needs_buildup and pd.notna(poss) and poss >= 55:
        base -= 10

    # Extremos asociativos: si el técnico los exige (posesión alta + baja verticalidad)
    needs_assoc_wide = "Extremo asociativo" in gap_roles
    if needs_assoc_wide and pd.notna(poss) and poss >= 60 and (vert is None or vert < 55):
        base -= 8

    # Pocas llegadas desde segunda línea (interior) y técnico ofensivo
    needs_interior = "Interior llegador" in gap_roles
    if needs_interior and pd.notna(off) and off >= 65:
        base -= 8

    # ── Bonificaciones por compatibilidad ────────────────────────────────────
    # Transiciones y presión → aprovecha recuperadores que sí hay
    has_recovery = "Mediocentro recuperador" not in gap_roles
    if has_recovery and pd.notna(press) and press >= 60:
        base += 10
    if pd.notna(trans) and trans >= 60:
        base += 10

    # Posesión media (45-60): encaja con perfil de plantilla equilibrada
    if pd.notna(poss) and 45 <= poss <= 62:
        base += 8

    # Juego vertical → compatible con delantero móvil que suele haber
    has_mobile_fw = "Delantero móvil" not in gap_roles
    if has_mobile_fw and pd.notna(vert) and vert >= 58:
        base += 6

    return float(np.clip(base, 0, 100))


def _pros_cons(axes, style_detail, context, laliga_seasons, budget_score,
               squad_compat, n_rows):
    pros, cons = [], []

    def band(v):
        return None if v is None or pd.isna(v) else ("alto" if v >= 60 else ("bajo" if v < 42 else "medio"))

    if band(axes.get("solidez_defensiva")) == "alto":
        pros.append("Equipos con marcada solidez defensiva (encaja con la prioridad del Rayo).")
    if band(axes.get("presion_alta")) == "alto":
        pros.append("Presion alta e intensa, identidad afin a Vallecas.")
    if band(axes.get("uso_transiciones")) == "alto":
        pros.append("Genera mucho peligro en transiciones rapidas.")
    if laliga_seasons >= 3:
        pros.append(f"Amplia experiencia en LaLiga ({laliga_seasons} temporadas en los datos).")
    if budget_score >= 85:
        pros.append("Coste salarial compatible con la masa salarial reducida del club.")
    if context.get("available"):
        pros.append("Disponible / libre: sin coste de rescision.")
    if squad_compat >= 75:
        pros.append("Estilo compatible con el perfil de la plantilla actual.")

    if band(axes.get("tendencia_ofensiva")) == "bajo":
        cons.append("Produccion ofensiva baja en sus equipos; poca generacion.")
    if band(axes.get("solidez_defensiva")) == "bajo":
        cons.append("Sus equipos encajan con facilidad; riesgo defensivo.")
    if laliga_seasons == 0:
        cons.append("Sin experiencia reciente en LaLiga (mayor riesgo de adaptacion).")
    if budget_score < 60:
        cons.append("Salario por encima de la referencia del club.")
    if squad_compat < 55:
        cons.append("Su estilo exige perfiles de los que la plantilla anda escasa.")
    if n_rows <= 1:
        cons.append("Cobertura de datos limitada (pocas temporadas en el dataset): perfil menos fiable.")
    if not context.get("available", True):
        cons.append("Bajo contrato: requeriria negociacion/indemnizacion.")
    return pros, cons


def _risks(axes, context, laliga_seasons, salary, eco, squad_compat, n_rows):
    def lvl(score):  # score 0(malo)-100(bueno) -> riesgo invertido
        if score >= 75:
            return "bajo"
        if score >= 55:
            return "medio"
        if score >= 35:
            return "medio-alto"
        return "alto"

    # deportivo
    dep = 70
    if n_rows <= 1:
        dep -= 25
    flex = axes.get("flexibilidad_tactica")
    if pd.notna(flex) and flex < 10:
        dep -= 5
    deportivo = lvl(dep)

    # economico
    if salary <= eco["target_salary_eur"]:
        economico = "bajo"
    elif salary <= eco["max_salary_eur"]:
        economico = "medio"
    else:
        economico = "alto"

    # clausula
    if context.get("available"):
        clausula = "bajo"
    else:
        clause = context.get("release_clause_eur")
        if clause and clause > 3_000_000:
            clausula = "alto"
        elif clause and clause > 0:
            clausula = "medio"
        else:
            clausula = "medio"  # bajo contrato sin clausula publica

    # adaptacion LaLiga
    adaptacion = "bajo" if laliga_seasons >= 3 else ("medio" if laliga_seasons >= 1 else "alto")

    # incompatibilidad plantilla
    incompat = lvl(squad_compat)

    return {
        "deportivo": deportivo,
        "economico": economico,
        "clausula": clausula,
        "adaptacion_laliga": adaptacion,
        "incompatibilidad_plantilla": incompat,
    }
