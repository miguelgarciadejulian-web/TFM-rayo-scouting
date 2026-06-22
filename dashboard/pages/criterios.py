# -*- coding: utf-8 -*-
"""
Criterios de puntuación — explica cómo se calculan los scores de jugadores y
entrenadores. Las tablas se generan desde los pesos REALES del código
(ROLE_DEFINITIONS, AXES, rayo_dna.yaml), así que siempre cuadran con el output.
"""
from __future__ import annotations
import sys
from pathlib import Path

import dash
from dash import html, dcc
import dash_bootstrap_components as dbc
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.profiling.player_profile import (  # noqa: E402
    ROLE_DEFINITIONS, ROLE_LABELS, METRIC_LABELS, STYLE_BY_ROLE, DEFAULT_MIN_MINUTES)
from src.profiling.coach_style import AXES as COACH_AXES, AXIS_LABELS  # noqa: E402

dash.register_page(__name__, path="/criterios", name="Criterios")

ROOT = Path(__file__).resolve().parents[2]
DNA = yaml.safe_load(open(ROOT / "config" / "rayo_dna.yaml", encoding="utf-8"))

CARD = {"background": "#fff", "border": "1px solid #E5E7EB", "borderRadius": "12px",
        "padding": "16px 20px", "marginBottom": "14px"}
TH = {"fontSize": "10px", "fontWeight": "700", "color": "#9CA3AF", "textTransform": "uppercase",
      "padding": "5px 10px", "textAlign": "left", "borderBottom": "2px solid #E30613"}
TD = {"fontSize": "12px", "padding": "5px 10px", "color": "#374151", "borderBottom": "1px solid #F3F4F6"}


def _weights_table(weights):
    items = sorted(weights.items(), key=lambda x: -abs(x[1]))
    head = html.Tr([html.Th("Métrica (por 90 min)", style=TH), html.Th("Peso", style=TH)])
    body = [html.Tr([
        html.Td(METRIC_LABELS.get(m, m), style=TD),
        html.Td(f"{w:+.0%}", style={**TD, "fontWeight": "700",
                "color": "#166534" if w > 0 else "#991B1B"}),
    ]) for m, w in items]
    return html.Table([html.Thead(head), html.Tbody(body)],
                      style={"width": "100%", "borderCollapse": "collapse"})


def _role_block(role):
    d = ROLE_DEFINITIONS[role]
    return html.Div([
        html.Div([
            html.Strong(ROLE_LABELS.get(role, role), style={"fontSize": "13px", "color": "#1A1A2E"}),
            html.Span(f"  grupo {d['group']}", style={"fontSize": "10px", "color": "#9CA3AF"}),
        ], style={"marginBottom": "4px"}),
        html.P(STYLE_BY_ROLE.get(role, ""), style={"fontSize": "11px", "color": "#E30613", "margin": "0 0 6px"}),
        _weights_table(d["weights"]),
    ], style={**CARD, "marginBottom": "10px"})


def _coach_axis_table():
    head = html.Tr([html.Th("Eje de estilo", style=TH), html.Th("Métricas de equipo y peso", style=TH)])
    body = []
    for axis, weights in COACH_AXES.items():
        ws = ", ".join(f"{m} ({w:+.0%})" for m, w in weights.items())
        body.append(html.Tr([
            html.Td(AXIS_LABELS.get(axis, axis), style={**TD, "fontWeight": "700", "color": "#1A1A2E"}),
            html.Td(ws, style={**TD, "fontSize": "11px"}),
        ]))
    return html.Table([html.Thead(head), html.Tbody(body)], style={"width": "100%", "borderCollapse": "collapse"})


def _dna_table():
    ts = DNA["target_style"]
    head = html.Tr([html.Th("Eje", style=TH), html.Th("Valor ideal", style=TH), html.Th("Peso en el Fit Rayo", style=TH)])
    body = [html.Tr([
        html.Td(AXIS_LABELS.get(k, k), style=TD),
        html.Td(str(v["ideal"]), style={**TD, "fontWeight": "700"}),
        html.Td(f"{v['weight']:.0%}", style=TD),
    ]) for k, v in ts.items()]
    return html.Table([html.Thead(head), html.Tbody(body)], style={"width": "100%", "borderCollapse": "collapse"})


def _section_chip(icon, text, color):
    return html.Div([
        html.I(className=f"ti {icon}",
               style={"fontSize":"14px","color":color,"marginRight":"7px"}),
        html.Span(text, style={"fontSize":"9px","fontWeight":"700",
            "color":color,"letterSpacing":".10em"}),
    ], style={"display":"flex","alignItems":"center","marginBottom":"14px"})


def layout(**_p):
    cw = DNA["context_weights"]
    return html.Div([

        # ── Hero ──────────────────────────────────────────────────────────────
        html.Div([
            html.Div([
                html.Div([html.I(className="ti ti-list-check",
                           style={"fontSize":"28px","color":"#fff"})],
                    style={"background":"rgba(255,255,255,.15)","borderRadius":"12px",
                           "padding":"10px","marginRight":"18px","flexShrink":"0"}),
                html.Div([
                    html.Div("TRANSPARENCIA", style={"fontSize":"9px","fontWeight":"700",
                        "color":"rgba(255,255,255,.55)","letterSpacing":".14em","marginBottom":"3px"}),
                    html.H1("Criterios de Puntuación", style={"fontSize":"22px","fontWeight":"900",
                        "color":"#fff","margin":"0 0 2px"}),
                    html.Div("Pesos y fórmulas reales del código · siempre sincronizados con el output",
                        style={"fontSize":"10px","color":"rgba(255,255,255,.5)"}),
                ]),
            ], style={"display":"flex","alignItems":"center"}),
        ], style={"background":"linear-gradient(135deg,#0D0D0D 0%,#1A1A1A 55%,#2D2D2D 100%)",
                  "borderRadius":"18px","padding":"20px 26px","marginBottom":"18px",
                  "boxShadow":"0 8px 24px rgba(159,18,57,.25)"}),

        # ── Descripción ───────────────────────────────────────────────────────
        html.Div([
            html.Div([
                html.I(className="ti ti-info-circle",
                       style={"fontSize":"18px","color":"#FFD600","marginRight":"12px","flexShrink":"0"}),
                html.P("Todas las tablas de esta página se generan automáticamente desde los mismos "
                       "pesos que usa la herramienta internamente — si el código cambia, esta página "
                       "lo refleja al instante. Sin datos manuales.",
                       style={"fontSize":"12px","color":"#374151","margin":"0"}),
            ], style={"display":"flex","alignItems":"flex-start"}),
        ], style={"background":"#FFFDE7","border":"1px solid #FFD600","borderRadius":"12px",
                  "padding":"14px 16px","marginBottom":"20px"}),

        # ═══════════════════════════════════════════════════════════════
        # 1 · PLANTILLA
        # ═══════════════════════════════════════════════════════════════
        _section_chip("ti-users-group", "1 · METODOLOGÍA — PLANTILLA", "#E30613"),
        html.Div([
            html.Div([
                html.Div("1", style={"background":"linear-gradient(135deg,#E30613,#C4000F)",
                    "color":"#fff","borderRadius":"50%","width":"28px","height":"28px",
                    "display":"flex","alignItems":"center","justifyContent":"center",
                    "fontWeight":"900","fontSize":"14px","marginRight":"10px","flexShrink":"0"}),
                html.Span("Plantilla", style={"fontSize":"18px","fontWeight":"800","color":"#1A1A2E"}),
            ], style={"display":"flex","alignItems":"center","marginBottom":"10px"}),
            html.P("Valor de mercado total: suma de los valores TM (Transfermarkt) de los jugadores "
                   "de la plantilla actual. Los sub-21 tienen su propio subtotal.",
                   style={"fontSize":"12px","color":"#374151"}),
            html.P("Contratos por expirar: se marcan como urgentes los que finalizan en ≤ 12 meses. "
                   "Se diferencian tres estados: 2026 (inminente), 2027 (próximo), 2028+ (margen).",
                   style={"fontSize":"12px","color":"#374151","marginTop":"6px"}),
            html.P("Distribución de edad: < 21 cantera/futuro · 21-26 proyección · 27-30 peak · "
                   "> 30 veteranía. El equilibrio ideal del Rayo es ≈ 25-26 años de media.",
                   style={"fontSize":"12px","color":"#374151","marginTop":"6px"}),
            html.P("Perfil posicional: los jugadores se asignan a un grupo (portero, defensa central, "
                   "lateral, mediocentro, extremo, delantero) según su posición principal. "
                   "El conteo determina si hay superávit o déficit en cada línea.",
                   style={"fontSize":"12px","color":"#374151","marginTop":"6px"}),
            html.P("Necesidades de la plantilla: se calculan comparando la plantilla actual con la "
                   "plantilla ideal parametrizada en needs.py (25 jugadores, distribución posicional "
                   "y rangos de edad objetivo). Los huecos generan alertas en Inicio y Decisiones.",
                   style={"fontSize":"12px","color":"#374151","marginTop":"6px"}),
        ], style=CARD),

        # ═══════════════════════════════════════════════════════════════
        # 2 · SCOUTING + JUGADORES (perfil individual)
        # ═══════════════════════════════════════════════════════════════
        _section_chip("ti-search", "2 · METODOLOGÍA — SCOUTING Y PERFIL DE JUGADOR", "#E30613"),
        html.Div([
            html.Div([
                html.Div("2", style={"background":"linear-gradient(135deg,#E30613,#C4000F)",
                    "color":"#fff","borderRadius":"50%","width":"28px","height":"28px",
                    "display":"flex","alignItems":"center","justifyContent":"center",
                    "fontWeight":"900","fontSize":"14px","marginRight":"10px","flexShrink":"0"}),
                html.Span("Perfil de jugador — cálculo de percentiles y roles", style={"fontSize":"18px","fontWeight":"800","color":"#1A1A2E"}),
            ], style={"display":"flex","alignItems":"center","marginBottom":"10px"}),
            html.P("Paso 1 — Percentiles. Cada métrica del jugador se convierte en un percentil 0-100 "
                   "comparándolo con los jugadores de su MISMO grupo posicional y liga (peras con peras). "
                   f"Solo se rankean jugadores con al menos {DEFAULT_MIN_MINUTES} minutos.", style={"fontSize": "12px", "color": "#374151"}),
            html.P("Paso 2 — Roles. Cada rol es una suma ponderada de esos percentiles (pesos abajo). "
                   "El rol con mayor puntuación es el PRINCIPAL; los que quedan por encima de max(55, principal−12) "
                   "son SECUNDARIOS.", style={"fontSize": "12px", "color": "#374151"}),
            html.P("Paso 3 — Fortalezas/Debilidades. Fortalezas = métricas con percentil ≥ 60; "
                   "debilidades = percentil ≤ 40.", style={"fontSize": "12px", "color": "#374151"}),
            html.P("Confianza: alta ≥ 1800 min · media ≥ 900 · baja ≥ 450 · si no, insuficiente. "
                   "Potencial por edad: ≤21 muy alto, ≤24 alto, ≤28 estable, ≤31 meseta, +31 veteranía.",
                   style={"fontSize": "12px", "color": "#374151"}),
        ], style=CARD),
        html.P("Pesos de cada rol (lo que más puntúa para clasificar a un jugador en ese perfil):",
               style={"fontSize": "12px", "fontWeight": "600", "color": "#1A1A2E", "margin": "6px 0"}),
        dbc.Row([dbc.Col(_role_block(r), md=6) for r in ROLE_DEFINITIONS if r != "portero"]),
        html.Div([
            html.Div([
                html.Div("2b", style={"background":"linear-gradient(135deg,#E30613,#C4000F)",
                    "color":"#fff","borderRadius":"50%","width":"28px","height":"28px",
                    "display":"flex","alignItems":"center","justifyContent":"center",
                    "fontWeight":"900","fontSize":"13px","marginRight":"10px","flexShrink":"0"}),
                html.Span("Fit Rayo de scouting (0-100)", style={"fontSize":"18px","fontWeight":"800","color":"#1A1A2E"}),
            ], style={"display":"flex","alignItems":"center","marginBottom":"10px"}),
            html.P("El Fit Rayo global de un fichaje combina cuatro dimensiones:",
                   style={"fontSize":"12px","color":"#374151"}),
            html.Table([
                html.Thead(html.Tr([html.Th("Dimensión", style=TH), html.Th("Peso", style=TH), html.Th("Cálculo", style=TH)])),
                html.Tbody([
                    html.Tr([html.Td("Rendimiento (rol principal)", style=TD), html.Td("40 %", style={**TD,"fontWeight":"700","color":"#166534"}), html.Td("Percentil del rol principal · 0→0, 100→40 pts", style=TD)]),
                    html.Tr([html.Td("Cobertura de necesidad en plantilla", style=TD), html.Td("30 %", style={**TD,"fontWeight":"700","color":"#166534"}), html.Td("1.0 si el perfil está sub-representado · 0.0 si ya sobra", style=TD)]),
                    html.Tr([html.Td("Afinidad de estilo con el ADN del Rayo", style=TD), html.Td("20 %", style={**TD,"fontWeight":"700","color":"#166534"}), html.Td("Distancia euclidiana entre percentiles y el ADN objetivo", style=TD)]),
                    html.Tr([html.Td("Potencial por edad", style=TD), html.Td("10 %", style={**TD,"fontWeight":"700","color":"#166534"}), html.Td("≤21→10 · ≤24→8 · ≤28→5 · ≤31→2 · +31→0 pts", style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse","marginBottom":"8px"}),
            html.P("Bandas de Fit: ≥ 80 Excelente · 65-79 Muy bueno · 50-64 Bueno · 35-49 Dudoso · < 35 No encaja.",
                   style={"fontSize":"11px","color":"#6B7280"}),
            html.P("Filtros del explorador de scouting: liga/país, edad mín/máx, minutos mínimos, posición, "
                   "pierna dominante, tipología de jugador, Fit mínimo y valor TM máximo. Los jugadores "
                   "mostrados siempre son externos a la plantilla actual del Rayo.",
                   style={"fontSize":"12px","color":"#374151","marginTop":"6px"}),
        ], style=CARD),

        # ═══════════════════════════════════════════════════════════════
        # 3 · COMPARADOR
        # ═══════════════════════════════════════════════════════════════
        _section_chip("ti-arrows-left-right", "3 · METODOLOGÍA — COMPARADOR", "#E30613"),
        html.Div([
            html.Div([
                html.Div("3", style={"background":"linear-gradient(135deg,#E30613,#C4000F)",
                    "color":"#fff","borderRadius":"50%","width":"28px","height":"28px",
                    "display":"flex","alignItems":"center","justifyContent":"center",
                    "fontWeight":"900","fontSize":"14px","marginRight":"10px","flexShrink":"0"}),
                html.Span("Comparador de jugadores", style={"fontSize":"18px","fontWeight":"800","color":"#1A1A2E"}),
            ], style={"display":"flex","alignItems":"center","marginBottom":"10px"}),
            html.P("La comparación es siempre head-to-head por percentiles dentro del MISMO grupo "
                   "posicional y liga. Ambos jugadores se muestran sobre los mismos ejes para que "
                   "los valores sean directamente comparables (peras con peras).",
                   style={"fontSize":"12px","color":"#374151"}),
            html.P("Radar chart: cada vértice es una métrica clave del grupo posicional. El área "
                   "rellenada refleja el percentil (0 = centro, 100 = borde externo).",
                   style={"fontSize":"12px","color":"#374151","marginTop":"6px"}),
            html.P("Veredicto automático: suma ponderada de diferencias de percentil en las métricas "
                   "del rol principal de cada jugador. Diferencia < 5 pts = equivalentes; "
                   "> 15 pts = claro favorito.",
                   style={"fontSize":"12px","color":"#374151","marginTop":"6px"}),
            html.P("Exportación PDF: incluye radar charts de ambos jugadores, tabla de métricas "
                   "comparadas, scores de Fit Rayo, datos contractuales y veredicto final.",
                   style={"fontSize":"12px","color":"#374151","marginTop":"6px"}),
        ], style=CARD),

        # ═══════════════════════════════════════════════════════════════
        # 4 · ENTRENADORES
        # ═══════════════════════════════════════════════════════════════
        _section_chip("ti-chalkboard", "4 · METODOLOGÍA — ENTRENADORES", "#E30613"),
        html.Div([
            html.Div([
                html.Div("4", style={"background":"linear-gradient(135deg,#E30613,#C4000F)",
                    "color":"#fff","borderRadius":"50%","width":"28px","height":"28px",
                    "display":"flex","alignItems":"center","justifyContent":"center",
                    "fontWeight":"900","fontSize":"14px","marginRight":"10px","flexShrink":"0"}),
                html.Span("Entrenadores", style={"fontSize":"18px","fontWeight":"800","color":"#1A1A2E"}),
            ], style={"display":"flex","alignItems":"center","marginBottom":"12px"}),
            html.P("Paso 1 — Estilo. Se agregan las métricas (por partido) de todos los equipos-temporada "
                   "que dirigió el técnico y se percentilan dentro de su liga. Cada eje de estilo (0-100) es "
                   "una combinación ponderada de esas métricas:", style={"fontSize": "12px", "color": "#374151"}),
            _coach_axis_table(),
            html.P("Bandas de lectura: < 40 bajo · 40-66 medio · ≥ 66 alto. La posesión se toma directa del % "
                   "real. La descripción textual se genera por umbrales sobre estos ejes.",
                   style={"fontSize": "11px", "color": "#6B7280", "marginTop": "8px"}),
        ], style=CARD),
        html.Div([
            html.P("Paso 2 — Fit Rayo (score /10). Mezcla cuatro sub-scores:", style={"fontSize": "12px", "color": "#374151"}),
            html.Ul([
                html.Li(f"Estilo — cercanía de sus ejes al ADN objetivo del club (peso restante).", style={"fontSize": "12px"}),
                html.Li(f"Experiencia en LaLiga — {cw['laliga_experience']:.0%} (4+ temporadas = máximo).", style={"fontSize": "12px"}),
                html.Li(f"Encaje de presupuesto — {cw['budget_fit']:.0%} (salario vs referencia del club).", style={"fontSize": "12px"}),
                html.Li(f"Compatibilidad con la plantilla — {cw['squad_compatibility']:.0%} (penaliza si exige perfiles que faltan).", style={"fontSize": "12px"}),
            ]),
            html.P("Si solo hay 1 temporada de datos, el score se penaliza un 10%.", style={"fontSize": "11px", "color": "#6B7280"}),
            html.P("ADN objetivo del club (valor ideal de cada eje y su peso en el Fit Rayo):",
                   style={"fontSize": "12px", "fontWeight": "600", "color": "#1A1A2E", "margin": "8px 0 6px"}),
            _dna_table(),
        ], style=CARD),
        html.Div([
            html.P("Pros / contras y riesgos (deportivo, económico, cláusula, adaptación a LaLiga, "
                   "incompatibilidad con la plantilla) se generan por reglas a partir de esos ejes y del "
                   "contexto. Ej.: solidez defensiva alta → pro; sin experiencia en LaLiga → contra y "
                   "riesgo de adaptación alto; salario por encima de la referencia → riesgo económico.",
                   style={"fontSize": "12px", "color": "#374151"}),
        ], style=CARD),

        # ═══════════════════════════════════════════════════════════════
        # 5 · DECISIONES
        # ═══════════════════════════════════════════════════════════════
        _section_chip("ti-checklist", "5 · METODOLOGÍA — DECISIONES", "#E30613"),
        html.Div([
            html.Div([
                html.Div("5", style={"background":"linear-gradient(135deg,#E30613,#C4000F)",
                    "color":"#fff","borderRadius":"50%","width":"28px","height":"28px",
                    "display":"flex","alignItems":"center","justifyContent":"center",
                    "fontWeight":"900","fontSize":"14px","marginRight":"10px","flexShrink":"0"}),
                html.Span("Decisiones — Fichajes, Renovaciones, Salidas", style={"fontSize":"18px","fontWeight":"800","color":"#1A1A2E"}),
            ], style={"display":"flex","alignItems":"center","marginBottom":"12px"}),
            html.P("Recomendación de fichaje — score 0-100 (4 factores):",
                   style={"fontSize":"12px","color":"#374151","fontWeight":"600"}),
            html.Table([
                html.Thead(html.Tr([html.Th("Factor", style=TH), html.Th("Peso", style=TH), html.Th("Umbral", style=TH)])),
                html.Tbody([
                    html.Tr([html.Td("Fit Rayo (rol + cobertura + estilo + edad)", style=TD), html.Td("50 %", style={**TD,"fontWeight":"700","color":"#166534"}), html.Td("≥ 70 → fichar · 50-69 → estudiar · < 50 → descartar", style=TD)]),
                    html.Tr([html.Td("Situación contractual (libre, 1 año, cláusula asequible)", style=TD), html.Td("20 %", style={**TD,"fontWeight":"700","color":"#166534"}), html.Td("Libre = máx · 1 año = alto · cláusula > 2×MV = penaliza", style=TD)]),
                    html.Tr([html.Td("Viabilidad económica (MV vs presupuesto disponible)", style=TD), html.Td("20 %", style={**TD,"fontWeight":"700","color":"#166534"}), html.Td("MV ≤ 50% presupuesto = verde · MV > 100% = rojo", style=TD)]),
                    html.Tr([html.Td("Afinidad entrenador (perfil típico del técnico)", style=TD), html.Td("10 %", style={**TD,"fontWeight":"700","color":"#166534"}), html.Td("Distancia entre percentiles del jugador y el estilo demandado", style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse","marginBottom":"12px"}),
            html.P("Recomendación de renovación — 3 niveles:",
                   style={"fontSize":"12px","color":"#374151","fontWeight":"600","marginTop":"6px"}),
            html.Table([
                html.Thead(html.Tr([html.Th("Nivel", style=TH), html.Th("Criterios", style=TH)])),
                html.Tbody([
                    html.Tr([html.Td("🟢 Renovar (urgente)", style={**TD,"color":"#166534","fontWeight":"700"}), html.Td("Contrato ≤ 1 año + titular indiscutible (> 1500 min) + Fit Rayo ≥ 65", style=TD)]),
                    html.Tr([html.Td("🟡 Evaluar", style={**TD,"color":"#92400E","fontWeight":"700"}), html.Td("Contrato ≤ 2 años o rendimiento en zona media (900-1499 min)", style=TD)]),
                    html.Tr([html.Td("🔴 No renovar / salida", style={**TD,"color":"#991B1B","fontWeight":"700"}), html.Td("< 900 min + Fit < 50 o salario anual > 2× valor de mercado estimado", style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse","marginBottom":"12px"}),
            html.P("Candidatos a salida: jugadores con Fit < 40, cedidos con rendimiento bajo, "
                   "o cuyo coste salarial anual supera 2× su valor de mercado estimado.",
                   style={"fontSize":"11px","color":"#6B7280"}),
            html.P("Estimación salarial: para jugadores sin dato confirmado se usa "
                   "salary_estimates.yaml — referencias por liga, club, posición y edad. "
                   "Los valores confirmados de SalaryLeaks/Capology tienen prioridad.",
                   style={"fontSize":"12px","color":"#374151","marginTop":"8px"}),
        ], style=CARD),

        # ═══════════════════════════════════════════════════════════════
        # 6 · FINANZAS
        # ═══════════════════════════════════════════════════════════════
        _section_chip("ti-coin", "6 · METODOLOGÍA — FINANZAS", "#E30613"),
        html.Div([
            html.Div([
                html.Div("6", style={"background":"linear-gradient(135deg,#E30613,#C4000F)",
                    "color":"#fff","borderRadius":"50%","width":"28px","height":"28px",
                    "display":"flex","alignItems":"center","justifyContent":"center",
                    "fontWeight":"900","fontSize":"14px","marginRight":"10px","flexShrink":"0"}),
                html.Span("Finanzas", style={"fontSize":"18px","fontWeight":"800","color":"#1A1A2E"}),
            ], style={"display":"flex","alignItems":"center","marginBottom":"12px"}),
            html.P("Masa salarial base: suma de salary_annual de todos los jugadores de la plantilla "
                   "(salary_estimates.yaml + datos de SalaryLeaks/Capology). Bonus sumados aparte.",
                   style={"fontSize":"12px","color":"#374151"}),
            html.P("Límite salarial LaLiga (FFP): dato publicado por LaLiga para la temporada actual. "
                   "% de uso = masa_salarial_base / límite × 100. Verde < 75% · Ámbar 75-90% · Rojo > 90%.",
                   style={"fontSize":"12px","color":"#374151","marginTop":"6px"}),
            html.P("Presupuesto — ingresos estimados: TV LaLiga (reparto según clasificación previa), "
                   "UEFA (primas de ronda), matchday (aforo × precio medio × partidos), "
                   "comercial/patrocinio y otros. Gastos: masa salarial bruta, amortizaciones de "
                   "traspasos (coste ÷ años de contrato) y costes operativos.",
                   style={"fontSize":"12px","color":"#374151","marginTop":"6px"}),
            html.P("Score de riesgo de cláusula (0-100 por jugador):",
                   style={"fontSize":"12px","color":"#374151","fontWeight":"600","marginTop":"8px"}),
            html.Table([
                html.Thead(html.Tr([html.Th("Factor", style=TH), html.Th("Peso", style=TH), html.Th("Detalle", style=TH)])),
                html.Tbody([
                    html.Tr([html.Td("Meses restantes de contrato", style=TD), html.Td("30 %", style={**TD,"fontWeight":"700"}), html.Td("≤ 6m = 30 pts · ≤ 12m = 20 pts · ≤ 24m = 10 pts · > 24m = 0 pts", style=TD)]),
                    html.Tr([html.Td("Ratio cláusula / valor TM", style=TD), html.Td("30 %", style={**TD,"fontWeight":"700"}), html.Td("< 1× = 30 pts (cláusula barata) · 1-2× = 15 pts · > 3× = 0 pts", style=TD)]),
                    html.Tr([html.Td("Edad (pico de demanda 24-28)", style=TD), html.Td("20 %", style={**TD,"fontWeight":"700"}), html.Td("24-28 = 20 pts · 22-23 = 12 pts · < 22 o > 31 = 0 pts", style=TD)]),
                    html.Tr([html.Td("Interés real confirmado (noticias)", style=TD), html.Td("20 %", style={**TD,"fontWeight":"700"}), html.Td("Confirmado = 20 pts · Sondeado = 10 pts · Sin noticias = 0 pts", style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse","marginBottom":"8px"}),
            html.P("Niveles: ≥ 70 MUY ALTO · 50-69 ALTO · 30-49 MEDIO · < 30 BAJO.",
                   style={"fontSize":"11px","color":"#6B7280"}),
            html.P("Simulador de fichajes: el score de viabilidad (0-100) combina el impacto en la masa "
                   "salarial (Δ vs límite FFP), el retorno esperado de valor de mercado a 3 años "
                   "(potencial × años de contrato) y la liberación de salario si hay una salida asociada.",
                   style={"fontSize":"12px","color":"#374151","marginTop":"8px"}),
        ], style=CARD),
    ])
