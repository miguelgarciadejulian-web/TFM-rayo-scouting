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
        html.P(STYLE_BY_ROLE.get(role, ""), style={"fontSize": "11px", "color": "#1D4ED8", "margin": "0 0 6px"}),
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


def layout(**_p):
    cw = DNA["context_weights"]
    return html.Div([
        html.Div([
            html.P("METODOLOGÍA", style={"fontSize": "10px", "fontWeight": "600", "color": "#6B7280",
                   "letterSpacing": ".08em", "margin": "0 0 3px"}),
            html.H1("Criterios de puntuación", className="page-title"),
            html.P("Cómo se calculan, por código, los perfiles y scores. Estas tablas salen de los "
                   "mismos pesos que usa la herramienta, así que cuadran con lo que ves.",
                   className="page-subtitle"),
        ], className="page-header"),

        # ── JUGADORES ──
        html.H2("1. Jugadores", style={"color": "#E30613", "fontSize": "20px", "margin": "8px 0 10px"}),
        html.Div([
            html.P("Paso 1 — Percentiles. Cada métrica del jugador se convierte en un percentil 0-100 "
                   "comparándolo con los jugadores de su MISMO grupo posicional y liga (peras con peras). "
                   f"Solo se rankean jugadores con al menos {DEFAULT_MIN_MINUTES} minutos.", style={"fontSize": "12px", "color": "#374151"}),
            html.P("Paso 2 — Roles. Cada rol es una suma ponderada de esos percentiles (pesos abajo). "
                   "El rol con mayor puntuación es el PRINCIPAL; los que quedan por encima de max(55, principal−12) "
                   "son SECUNDARIOS.", style={"fontSize": "12px", "color": "#374151"}),
            html.P("Paso 3 — Fortalezas/Debilidades. Fortalezas = métricas con percentil ≥ 60; "
                   "debilidades = percentil ≤ 40.", style={"fontSize": "12px", "color": "#374151"}),
            html.P("Confianza: alta ≥ 1800 min · media ≥ 900 · baja ≥ 450 · si no, insuficiente. "
                   "Potencial por edad: ≤21 muy alto, ≤24 alto, ≤28 estable, ≤31 meseta, +31 veteranía. "
                   "El perfil se calcula sobre TODO el histórico del jugador agregado (no una sola temporada).",
                   style={"fontSize": "12px", "color": "#374151"}),
        ], style=CARD),
        html.P("Pesos de cada rol (lo que más puntúa para clasificar a un jugador en ese perfil):",
               style={"fontSize": "12px", "fontWeight": "600", "color": "#1A1A2E", "margin": "6px 0"}),
        dbc.Row([dbc.Col(_role_block(r), md=6) for r in ROLE_DEFINITIONS if r != "portero"]),

        html.Div([
            html.P("Fit Rayo de un fichaje (página Decisiones / ficha): combina la "
                   "compatibilidad con la plantilla (cubre un hueco = alto; perfil sobre-representado = bajo), "
                   "la afinidad con el estilo del entrenador, el nivel del rol y el potencial por edad.",
                   style={"fontSize": "12px", "color": "#374151"}),
        ], style=CARD),

        # ── ENTRENADORES ──
        html.H2("2. Entrenadores", style={"color": "#E30613", "fontSize": "20px", "margin": "16px 0 10px"}),
        html.Div([
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
    ])
