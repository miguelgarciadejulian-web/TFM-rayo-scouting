# -*- coding: utf-8 -*-
"""
Criterios de puntuación — explica TODOS los cálculos de la herramienta,
organizados por pestañas. Generado automáticamente desde los pesos reales.
"""
from __future__ import annotations
import sys
from pathlib import Path

import dash
from dash import html, dcc, callback, Input, Output
import dash_bootstrap_components as dbc
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.profiling.player_profile import (  # noqa: E402
    ROLE_DEFINITIONS, ROLE_LABELS, METRIC_LABELS, STYLE_BY_ROLE, DEFAULT_MIN_MINUTES)
from src.profiling.coach_style import AXES as COACH_AXES, AXIS_LABELS  # noqa: E402

dash.register_page(__name__, path="/criterios", name="Criterios")

ROOT = Path(__file__).resolve().parents[2]
DNA = yaml.safe_load(open(ROOT / "config" / "rayo_dna.yaml", encoding="utf-8"))

# ─── Estilos ────────────────────────────────────────────────────────────────
CARD  = {"background":"#fff","border":"1px solid #E5E7EB","borderRadius":"12px",
         "padding":"16px 20px","marginBottom":"14px"}
CARD2 = {"background":"#F9FAFB","border":"1px solid #E5E7EB","borderRadius":"10px",
         "padding":"12px 16px","marginBottom":"10px"}
TH = {"fontSize":"10px","fontWeight":"700","color":"#9CA3AF","textTransform":"uppercase",
      "padding":"5px 10px","textAlign":"left","borderBottom":"2px solid #E30613"}
TD = {"fontSize":"12px","padding":"5px 10px","color":"#374151","borderBottom":"1px solid #F3F4F6"}
FMT = {"background":"#1A1A2E","borderRadius":"8px","padding":"10px 14px",
       "fontFamily":"monospace","fontSize":"12px","color":"#A5F3FC","marginBottom":"8px"}
NOTE = {"background":"#FFFDE7","border":"1px solid #FDE68A","borderRadius":"8px",
        "padding":"8px 12px","fontSize":"11px","color":"#78350F","marginBottom":"8px"}
GREEN_BOX = {"background":"#F0FDF4","border":"1px solid #BBF7D0","borderRadius":"8px",
             "padding":"10px 14px","marginBottom":"8px"}


# ─── Helpers ────────────────────────────────────────────────────────────────
def _tbl(headers, rows, compact=False):
    sz = "10px" if compact else "12px"
    th_s = {**TH, "fontSize":"9px" if compact else "10px"}
    td_s = {**TD, "fontSize":sz}
    head = html.Tr([html.Th(h, style=th_s) for h in headers])
    body = [html.Tr([html.Td(c, style={**td_s, **(extra if isinstance(c, str) else {})})
                     for c, extra in ([(c,{}) for c in row] if all(isinstance(x,str) for x in row)
                                       else row)])
            for row in rows]
    return html.Table([html.Thead(head), html.Tbody(body)],
                      style={"width":"100%","borderCollapse":"collapse","marginBottom":"10px"})


def _formula(text):
    return html.Div(text, style=FMT)


def _note(text):
    return html.Div([
        html.I(className="ti ti-info-circle",
               style={"fontSize":"13px","color":"#92400E","marginRight":"6px"}),
        html.Span(text, style={"fontSize":"11px","color":"#78350F"}),
    ], style={**NOTE, "display":"flex","alignItems":"flex-start"})


def _section(num, title):
    return html.Div([
        html.Div(str(num), style={"background":"linear-gradient(135deg,#E30613,#C4000F)",
            "color":"#fff","borderRadius":"50%","width":"26px","height":"26px","flexShrink":"0",
            "display":"flex","alignItems":"center","justifyContent":"center",
            "fontWeight":"900","fontSize":"12px","marginRight":"10px"}),
        html.Span(title, style={"fontSize":"16px","fontWeight":"800","color":"#1A1A2E"}),
    ], style={"display":"flex","alignItems":"center","marginBottom":"10px"})


def _subsection(title):
    return html.Div([
        html.Div(style={"width":"4px","height":"16px","background":"#E30613",
                        "borderRadius":"2px","marginRight":"8px","flexShrink":"0"}),
        html.Span(title, style={"fontSize":"13px","fontWeight":"700","color":"#1A1A2E"}),
    ], style={"display":"flex","alignItems":"center","marginBottom":"8px","marginTop":"10px"})


def _chip(text, color="#E30613"):
    return html.Span(text, style={"background":color,"color":"#fff","borderRadius":"20px",
        "padding":"2px 10px","fontSize":"10px","fontWeight":"700","marginRight":"4px"})


def _weights_table(weights):
    items = sorted(weights.items(), key=lambda x: -abs(x[1]))
    head = html.Tr([html.Th("Métrica (por 90 min)", style=TH), html.Th("Peso", style=TH)])
    body = [html.Tr([
        html.Td(METRIC_LABELS.get(m, m), style=TD),
        html.Td(f"{w:+.0%}", style={**TD,"fontWeight":"700",
                "color":"#166534" if w > 0 else "#991B1B"}),
    ]) for m, w in items]
    return html.Table([html.Thead(head), html.Tbody(body)],
                      style={"width":"100%","borderCollapse":"collapse"})


def _role_block(role):
    d = ROLE_DEFINITIONS[role]
    return html.Div([
        html.Div([
            html.Strong(ROLE_LABELS.get(role, role),
                        style={"fontSize":"13px","color":"#1A1A2E"}),
            html.Span(f"  grupo {d['group']}",
                      style={"fontSize":"10px","color":"#9CA3AF"}),
        ], style={"marginBottom":"4px"}),
        html.P(STYLE_BY_ROLE.get(role, ""),
               style={"fontSize":"11px","color":"#E30613","margin":"0 0 6px"}),
        _weights_table(d["weights"]),
    ], style={**CARD,"marginBottom":"10px"})


def _dna_table():
    ts = DNA["target_style"]
    head = html.Tr([html.Th("Eje",style=TH),html.Th("Valor ideal",style=TH),html.Th("Peso Fit Rayo",style=TH)])
    body = [html.Tr([
        html.Td(AXIS_LABELS.get(k,k),style=TD),
        html.Td(str(v["ideal"]),style={**TD,"fontWeight":"700"}),
        html.Td(f"{v['weight']:.0%}",style=TD),
    ]) for k,v in ts.items()]
    return html.Table([html.Thead(head),html.Tbody(body)],
                      style={"width":"100%","borderCollapse":"collapse"})


def _coach_axes_table():
    head = html.Tr([html.Th("Eje de estilo",style=TH),html.Th("Métricas de equipo y peso",style=TH)])
    body = []
    for axis, weights in COACH_AXES.items():
        ws = ", ".join(f"{m} ({w:+.0%})" for m,w in weights.items())
        body.append(html.Tr([
            html.Td(AXIS_LABELS.get(axis,axis),style={**TD,"fontWeight":"700","color":"#1A1A2E"}),
            html.Td(ws,style={**TD,"fontSize":"11px"}),
        ]))
    return html.Table([html.Thead(head),html.Tbody(body)],
                      style={"width":"100%","borderCollapse":"collapse"})


# ═══════════════════════════════════════════════════════════════════════════
# TAB 1 — PLANTILLA
# ═══════════════════════════════════════════════════════════════════════════
def _tab_plantilla():
    return html.Div([
        html.Div([
            _section("1a", "Valor de mercado"),
            html.P("El valor total de la plantilla es la suma de los valores TM (Transfermarkt) "
                   "de todos los jugadores activos. Se calcula un subtotal exclusivo para jugadores "
                   "sub-21 como indicador del potencial de cantera y futura reventa.",
                   style={"fontSize":"12px","color":"#374151","marginBottom":"6px"}),
            _formula("Valor total = Σ TM_value(jugador)  para jugador ∈ plantilla_activa\n"
                     "Valor sub-21 = Σ TM_value(jugador)  para jugador con edad ≤ 21"),
            _note("Los valores TM se actualizan manualmente o vía API de Transfermarkt. "
                  "Son orientativos, no precios de mercado garantizados."),
        ], style=CARD),

        html.Div([
            _section("1b", "Distribución de edad"),
            html.P("Los jugadores se agrupan en cuatro franjas que determinan el perfil "
                   "de madurez de la plantilla:", style={"fontSize":"12px","color":"#374151"}),
            html.Table([
                html.Thead(html.Tr([html.Th("Franja",style=TH),html.Th("Edad",style=TH),
                                    html.Th("Etiqueta",style=TH),html.Th("Ref. Rayo",style=TH)])),
                html.Tbody([
                    html.Tr([html.Td("Cantera/Futuro",style=TD),html.Td("≤ 21",style=TD),
                             html.Td("Potencial sin explotar",style=TD),html.Td("3-5 jugadores",style=TD)]),
                    html.Tr([html.Td("Proyección",style=TD),html.Td("22-26",style=TD),
                             html.Td("Crecimiento + rendimiento",style=TD),html.Td("10-12 jugadores",style=TD)]),
                    html.Tr([html.Td("Peak",style=TD),html.Td("27-30",style=TD),
                             html.Td("Pleno rendimiento",style=TD),html.Td("8-10 jugadores",style=TD)]),
                    html.Tr([html.Td("Veteranía",style=TD),html.Td("> 30",style=TD),
                             html.Td("Experiencia + liderazgo",style=TD),html.Td("2-3 jugadores",style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse","marginBottom":"8px"}),
            _formula("Edad media plantilla = Σ edad(j) / N  →  ideal Rayo ≈ 25-26 años"),
        ], style=CARD),

        html.Div([
            _section("1c", "Estados de contrato"),
            html.P("Se clasifican por año de expiración y se marcan como urgentes "
                   "los que finalizan en ≤ 12 meses:", style={"fontSize":"12px","color":"#374151"}),
            html.Table([
                html.Thead(html.Tr([html.Th("Estado",style=TH),html.Th("Criterio",style=TH),
                                    html.Th("Acción sugerida",style=TH)])),
                html.Tbody([
                    html.Tr([html.Td("🔴 Urgente",style={**TD,"color":"#991B1B","fontWeight":"700"}),
                             html.Td("Expira ≤ 12 meses",style=TD),
                             html.Td("Renovar o vender este mercado",style=TD)]),
                    html.Tr([html.Td("🟡 Próximo",style={**TD,"color":"#92400E","fontWeight":"700"}),
                             html.Td("Expira ≤ 24 meses",style=TD),
                             html.Td("Iniciar negociación",style=TD)]),
                    html.Tr([html.Td("🟢 Margen",style={**TD,"color":"#166534","fontWeight":"700"}),
                             html.Td("Expira > 24 meses",style=TD),
                             html.Td("Sin urgencia",style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse","marginBottom":"8px"}),
            _note("Los contratos cedidos se marcan de forma diferente: "
                  "se muestra la fecha de fin de cesión, no la del contrato original."),
        ], style=CARD),

        html.Div([
            _section("1d", "Perfil posicional y necesidades"),
            html.P("Los jugadores se asignan a grupos posicionales según su posición principal (pos). "
                   "Se cuentan titulares probables (> 900 min) por grupo y se comparan con la "
                   "cobertura mínima parametrizada:", style={"fontSize":"12px","color":"#374151"}),
            html.Table([
                html.Thead(html.Tr([html.Th("Grupo",style=TH),html.Th("Posiciones incluidas",style=TH),
                                    html.Th("Cobertura mínima",style=TH)])),
                html.Tbody([
                    html.Tr([html.Td("Porteros",style=TD),html.Td("GK",style=TD),html.Td("2",style=TD)]),
                    html.Tr([html.Td("Centrales",style=TD),html.Td("CB",style=TD),html.Td("3",style=TD)]),
                    html.Tr([html.Td("Laterales",style=TD),html.Td("LB, RB",style=TD),html.Td("2",style=TD)]),
                    html.Tr([html.Td("Mediocampo",style=TD),html.Td("DM, CM, AM",style=TD),html.Td("4",style=TD)]),
                    html.Tr([html.Td("Extremos",style=TD),html.Td("LW, RW",style=TD),html.Td("2",style=TD)]),
                    html.Tr([html.Td("Delanteros",style=TD),html.Td("CF, ST",style=TD),html.Td("2",style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse","marginBottom":"8px"}),
            _formula("Estado posición = 'sin_cobertura'  si titulares < mínimo\n"
                     "                  'a_reforzar'      si titulares == mínimo\n"
                     "                  'cubierta'        si titulares > mínimo"),
            _note("Las necesidades calculadas aparecen automáticamente en la pestaña Inicio "
                  "y en la sección Fichar de Decisiones."),
        ], style=CARD),

        html.Div([
            _section("1e", "Gráficos de plantilla"),
            html.P("La página Plantilla incluye los siguientes visuales:",
                   style={"fontSize":"12px","color":"#374151"}),
            html.Ul([
                html.Li("Donut de distribución de edad (4 franjas, colores semáforo).",
                        style={"fontSize":"12px","color":"#374151","marginBottom":"4px"}),
                html.Li("Barra de grupos posicionales con conteo y colores por estado de cobertura.",
                        style={"fontSize":"12px","color":"#374151","marginBottom":"4px"}),
                html.Li("Barra de contratos por año de expiración (urgentes en rojo).",
                        style={"fontSize":"12px","color":"#374151","marginBottom":"4px"}),
                html.Li("Tabla de plantilla completa con valor TM, salario, contrato y score de rol.",
                        style={"fontSize":"12px","color":"#374151","marginBottom":"4px"}),
            ], style={"paddingLeft":"20px","marginTop":"4px"}),
        ], style=CARD),
    ])


# ═══════════════════════════════════════════════════════════════════════════
# TAB 2 — SCOUTING
# ═══════════════════════════════════════════════════════════════════════════
def _tab_scouting():
    return html.Div([
        # Paso 1 Percentiles
        html.Div([
            _section("2a", "Percentiles por posición y liga"),
            html.P(f"Cada métrica se convierte en un percentil 0-100 comparando el jugador "
                   f"con todos los jugadores del mismo grupo posicional y liga con al menos "
                   f"{DEFAULT_MIN_MINUTES} minutos. El percentil 100 = mejor de la muestra.",
                   style={"fontSize":"12px","color":"#374151"}),
            _formula("percentil(m, j) = rank(j, m, grupo, liga) / N_grupo  × 100\n\n"
                     "Donde N_grupo = nº de jugadores del mismo grupo con ≥ min_minutos"),
            _note(f"Solo se puntúan jugadores con ≥ {DEFAULT_MIN_MINUTES} minutos. "
                  "Con menos minutos el perfil aparece como 'insuficiente'."),

            _subsection("Niveles de confianza"),
            html.Table([
                html.Thead(html.Tr([html.Th("Nivel",style=TH),html.Th("Minutos jugados",style=TH),
                                    html.Th("Implicación",style=TH)])),
                html.Tbody([
                    html.Tr([html.Td("🟢 Alta",style={**TD,"color":"#166534","fontWeight":"700"}),
                             html.Td("≥ 1800 min",style=TD),html.Td("Muestra representativa",style=TD)]),
                    html.Tr([html.Td("🟡 Media",style={**TD,"color":"#92400E","fontWeight":"700"}),
                             html.Td("≥ 900 min",style=TD),html.Td("Suficiente con cautela",style=TD)]),
                    html.Tr([html.Td("🟠 Baja",style={**TD,"color":"#C2410C","fontWeight":"700"}),
                             html.Td("≥ 450 min",style=TD),html.Td("Señal inicial",style=TD)]),
                    html.Tr([html.Td("⚫ Insuficiente",style={**TD,"color":"#374151","fontWeight":"700"}),
                             html.Td(f"< 450 min",style=TD),html.Td("No se rankea",style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse","marginBottom":"8px"}),

            _subsection("Potencial por edad"),
            html.Table([
                html.Thead(html.Tr([html.Th("Etiqueta",style=TH),html.Th("Edad",style=TH),
                                    html.Th("Interpretación",style=TH)])),
                html.Tbody([
                    html.Tr([html.Td("🚀 Muy alto",style=TD),html.Td("≤ 21",style=TD),
                             html.Td("Margen máximo de crecimiento",style=TD)]),
                    html.Tr([html.Td("⬆ Alto",style=TD),html.Td("22-24",style=TD),
                             html.Td("Curva ascendente",style=TD)]),
                    html.Tr([html.Td("→ Estable",style=TD),html.Td("25-28",style=TD),
                             html.Td("Peak o cerca",style=TD)]),
                    html.Tr([html.Td("↘ Meseta",style=TD),html.Td("29-31",style=TD),
                             html.Td("Rendimiento sostenido con declive leve",style=TD)]),
                    html.Tr([html.Td("↓ Veteranía",style=TD),html.Td("> 31",style=TD),
                             html.Td("Experiencia, poco margen físico",style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse"}),
        ], style=CARD),

        # Paso 2 Scores de rol
        html.Div([
            _section("2b", "Score de rol"),
            html.P("Cada rol es una combinación lineal de percentiles. "
                   "El rol con puntuación más alta = rol PRINCIPAL.",
                   style={"fontSize":"12px","color":"#374151"}),
            _formula("score_rol(r, j) = Σ  peso(r, m) × percentil(m, j)\n\n"
                     "Rol principal  = argmax_r [ score_rol(r, j) ]\n"
                     "Roles secundarios = roles con score ≥ max(55, principal − 12)"),
            html.P("Fortalezas: métricas con percentil ≥ 60. "
                   "Debilidades: métricas con percentil ≤ 40.",
                   style={"fontSize":"12px","color":"#374151","marginTop":"6px"}),
            html.P("Pesos de cada rol (generados desde el código):",
                   style={"fontSize":"12px","fontWeight":"600","color":"#1A1A2E","margin":"8px 0 6px"}),
            dbc.Row([dbc.Col(_role_block(r), md=6) for r in ROLE_DEFINITIONS if r != "portero"]),
        ], style=CARD),

        # Score por sub-posición
        html.Div([
            _section("2c", "Score de rendimiento por sub-posición"),
            html.P("Para el Fit Rayo, el rendimiento se calcula con pesos específicos por sub-posición. "
                   "Este es el score único que aparece en Scouting, Comparador, Decisiones y PDF export.",
                   style={"fontSize":"12px","color":"#374151"}),
            html.Table([
                html.Thead(html.Tr([html.Th("Sub-posición",style=TH),
                                    html.Th("Dimensiones y peso",style={**TH,"width":"65%"})])),
                html.Tbody([
                    html.Tr([html.Td("Portero",style={**TD,"fontWeight":"700"}),
                             html.Td("Paradas/90 (45%) · Limpiezas (30%) · Juego con balón (15%) · Duelos aéreos (10%)",style=TD)]),
                    html.Tr([html.Td("Central",style={**TD,"fontWeight":"700"}),
                             html.Td("Defensiva: entradas+int+rec+bloqueos (40%) · Duelo aéreo (25%) · Duelo 1v1 (20%) · Construcción (15%)",style=TD)]),
                    html.Tr([html.Td("Lateral",style={**TD,"fontWeight":"700"}),
                             html.Td("Defensiva (30%) · Proyección: centros+pases (30%) · Duelos (20%) · Ataque (20%)",style=TD)]),
                    html.Tr([html.Td("Pivote",style={**TD,"fontWeight":"700"}),
                             html.Td("Recuperación (40%) · Pase (30%) · Presión/duelos (20%) · Contribución ofensiva (10%)",style=TD)]),
                    html.Tr([html.Td("Medio Centro",style={**TD,"fontWeight":"700"}),
                             html.Td("Pase (30%) · Recuperación (30%) · Creación (25%) · Contribución (15%)",style=TD)]),
                    html.Tr([html.Td("Mediapunta",style={**TD,"fontWeight":"700"}),
                             html.Td("Creación (35%) · Gol/Remate (30%) · Pase en profundidad (20%) · Pressing (15%)",style=TD)]),
                    html.Tr([html.Td("Extremo",style={**TD,"fontWeight":"700"}),
                             html.Td("Regates/Desborde (30%) · Gol/Remate (30%) · Creación (25%) · Pressing (15%)",style=TD)]),
                    html.Tr([html.Td("Delantero Centro",style={**TD,"fontWeight":"700"}),
                             html.Td("Gol/Remate (45%) · Duelos área: aéreos+1v1 (20%) · Creación (20%) · Pressing (15%)",style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse","marginBottom":"10px"}),
        ], style=CARD),

        # Factor dificultad de liga
        html.Div([
            _section("2d", "Factor de dificultad de liga"),
            html.P("Los percentiles se ajustan por la competitividad de la liga donde actúa el jugador. "
                   "LaLiga = referencia (1.00). Ligas menores se escalan hacia abajo.",
                   style={"fontSize":"12px","color":"#374151"}),
            _formula("score_ajustado = score_bruto × factor_liga"),
            html.Table([
                html.Thead(html.Tr([html.Th("Liga",style=TH),html.Th("Factor",style=TH),
                                    html.Th("Liga",style=TH),html.Th("Factor",style=TH)])),
                html.Tbody([
                    html.Tr([html.Td("LaLiga (España)",style=TD),html.Td("1.00",style={**TD,"fontWeight":"700","color":"#166534"}),
                             html.Td("Bundesliga (Alemania)",style=TD),html.Td("0.97",style=TD)]),
                    html.Tr([html.Td("Premier League",style=TD),html.Td("1.00",style={**TD,"fontWeight":"700","color":"#166534"}),
                             html.Td("Ligue 1 (Francia)",style=TD),html.Td("0.92",style=TD)]),
                    html.Tr([html.Td("Serie A (Italia)",style=TD),html.Td("0.97",style=TD),
                             html.Td("Eredivisie (Países Bajos)",style=TD),html.Td("0.88",style=TD)]),
                    html.Tr([html.Td("Segunda División",style=TD),html.Td("0.82",style=TD),
                             html.Td("Primera RFEF",style=TD),html.Td("0.70",style=TD)]),
                    html.Tr([html.Td("Primeira Liga (Portugal)",style=TD),html.Td("0.88",style=TD),
                             html.Td("Otras ligas",style=TD),html.Td("0.65-0.80",style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse","marginBottom":"8px"}),
        ], style=CARD),

        # Fit Rayo global de scouting
        html.Div([
            _section("2e", "Fit Rayo global (0-100)"),
            html.P("El Fit Rayo sintetiza el encaje de un candidato externo en cuatro dimensiones:",
                   style={"fontSize":"12px","color":"#374151"}),
            _formula("Fit_Rayo = 0.40 × Rendimiento\n"
                     "         + 0.30 × Encaje_económico\n"
                     "         + 0.20 × Perfil_de_edad\n"
                     "         + 0.10 × Disponibilidad"),
            html.Table([
                html.Thead(html.Tr([html.Th("Dimensión",style=TH),html.Th("Peso",style=TH),
                                    html.Th("Cómo se calcula",style=TH)])),
                html.Tbody([
                    html.Tr([html.Td("Rendimiento",style={**TD,"fontWeight":"700"}),
                             html.Td("40%",style={**TD,"color":"#166534","fontWeight":"700"}),
                             html.Td("Score por sub-posición ajustado por dificultad de liga",style=TD)]),
                    html.Tr([html.Td("Encaje económico",style={**TD,"fontWeight":"700"}),
                             html.Td("30%",style={**TD,"color":"#166534","fontWeight":"700"}),
                             html.Td("Valor TM vs horquilla de inversión del Rayo (0.5–5M€)",style=TD)]),
                    html.Tr([html.Td("Perfil de edad",style={**TD,"fontWeight":"700"}),
                             html.Td("20%",style={**TD,"color":"#166534","fontWeight":"700"}),
                             html.Td("Curva óptima por posición; prime (24-28) = máximo",style=TD)]),
                    html.Tr([html.Td("Disponibilidad",style={**TD,"fontWeight":"700"}),
                             html.Td("10%",style={**TD,"color":"#166534","fontWeight":"700"}),
                             html.Td("Contrato expirante=100, libre=90, cedido con opción=80, atado=0",style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse","marginBottom":"8px"}),
            html.Table([
                html.Thead(html.Tr([html.Th("Fit Rayo",style=TH),html.Th("Valoración",style=TH),html.Th("Color",style=TH)])),
                html.Tbody([
                    html.Tr([html.Td("≥ 80",style=TD),html.Td("Excelente encaje",style=TD),html.Td("🟢 Verde oscuro",style=TD)]),
                    html.Tr([html.Td("65-79",style=TD),html.Td("Muy bueno",style=TD),html.Td("🟢 Verde",style=TD)]),
                    html.Tr([html.Td("50-64",style=TD),html.Td("Bueno",style=TD),html.Td("🔵 Azul",style=TD)]),
                    html.Tr([html.Td("35-49",style=TD),html.Td("Dudoso",style=TD),html.Td("🟡 Ámbar",style=TD)]),
                    html.Tr([html.Td("< 35",style=TD),html.Td("No encaja",style=TD),html.Td("🔴 Rojo",style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse"}),
        ], style=CARD),

        # Explorador
        html.Div([
            _section("2f", "Filtros del explorador de scouting"),
            html.P("El explorador permite combinar cualquier subconjunto de estos filtros:",
                   style={"fontSize":"12px","color":"#374151"}),
            html.Table([
                html.Thead(html.Tr([html.Th("Filtro",style=TH),html.Th("Valores posibles",style=TH)])),
                html.Tbody([
                    html.Tr([html.Td("Liga / País",style=TD),html.Td("Selector múltiple de ligas cubiertas",style=TD)]),
                    html.Tr([html.Td("Edad mín/máx",style=TD),html.Td("Rango numérico (15-40)",style=TD)]),
                    html.Tr([html.Td("Minutos mínimos",style=TD),html.Td(f"Por defecto {DEFAULT_MIN_MINUTES}",style=TD)]),
                    html.Tr([html.Td("Posición",style=TD),html.Td("Sub-posición (GK, CB, LB, RB, DM, CM, AM, LW, RW, CF, ST)",style=TD)]),
                    html.Tr([html.Td("Pierna dominante",style=TD),html.Td("Derecha / Izquierda / Ambas",style=TD)]),
                    html.Tr([html.Td("Fit Rayo mínimo",style=TD),html.Td("Slider 0-100",style=TD)]),
                    html.Tr([html.Td("Valor TM máximo",style=TD),html.Td("Slider en M€",style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse"}),
        ], style=CARD),
    ])


# ═══════════════════════════════════════════════════════════════════════════
# TAB 3 — COMPARADOR
# ═══════════════════════════════════════════════════════════════════════════
def _tab_comparador():
    return html.Div([
        html.Div([
            _section("3a", "Comparación head-to-head por percentiles"),
            html.P("La comparación es siempre dentro del mismo grupo posicional y liga, "
                   "para que los percentiles sean directamente comparables. "
                   "No se puede comparar un delantero con un lateral.",
                   style={"fontSize":"12px","color":"#374151"}),
            _formula("Diferencia(m) = percentil(m, jugador_A) − percentil(m, jugador_B)\n\n"
                     "Δ > 0  →  A superior en esa métrica\n"
                     "Δ < 0  →  B superior en esa métrica"),
        ], style=CARD),

        html.Div([
            _section("3b", "Radar chart — ejes por grupo posicional"),
            html.P("Los vértices del radar se eligen para reflejar las dimensiones más "
                   "relevantes de cada grupo posicional:",
                   style={"fontSize":"12px","color":"#374151"}),
            html.Table([
                html.Thead(html.Tr([html.Th("Grupo posicional",style=TH),
                                    html.Th("Ejes del radar",style={**TH,"width":"70%"})])),
                html.Tbody([
                    html.Tr([html.Td("Porteros",style={**TD,"fontWeight":"700"}),
                             html.Td("Paradas %, Goles encajados/90, Salidas, Duelos aéreos, Pases largos %",style=TD)]),
                    html.Tr([html.Td("Defensas centrales",style={**TD,"fontWeight":"700"}),
                             html.Td("Entradas ganadas, Duelos aéreos, Interceptaciones, Construcción, Duelos 1v1",style=TD)]),
                    html.Tr([html.Td("Laterales",style={**TD,"fontWeight":"700"}),
                             html.Td("Centros, Pases clave, Entradas, Regates, Contribución gol",style=TD)]),
                    html.Tr([html.Td("Pivotes / Mediocentros defensivos",style={**TD,"fontWeight":"700"}),
                             html.Td("Recuperaciones, Entradas, Pases completados %, Presión, Pases progresivos",style=TD)]),
                    html.Tr([html.Td("Mediocentros",style={**TD,"fontWeight":"700"}),
                             html.Td("Pases clave, Pases progresivos, Recuperaciones, Duelos, Gol+Asistencia",style=TD)]),
                    html.Tr([html.Td("Mediapuntas / Extremos",style={**TD,"fontWeight":"700"}),
                             html.Td("Goles/90, Asistencias/90, Regates, Pases clave, Presión",style=TD)]),
                    html.Tr([html.Td("Delanteros",style={**TD,"fontWeight":"700"}),
                             html.Td("Goles/90, Remates/90, xG/90, Duelos aéreos, Pases clave",style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse"}),
        ], style=CARD),

        html.Div([
            _section("3c", "Veredicto automático"),
            html.P("Se calcula la diferencia media de percentiles en todas las métricas "
                   "comunes del grupo posicional:",
                   style={"fontSize":"12px","color":"#374151"}),
            _formula("Δ_media = mean( |percentil(m,A) − percentil(m,B)| )  sobre todas las métricas\n\n"
                     "Si A_media > B_media:\n"
                     "  Δ < 5 pts   →  'Equivalentes'\n"
                     "  5-15 pts    →  'Ligera ventaja A'\n"
                     "  > 15 pts    →  'Claro favorito A'"),
            _note("El veredicto es orientativo. La elección final depende de contexto táctico, "
                  "precio y situación contractual."),
        ], style=CARD),

        html.Div([
            _section("3d", "Exportación PDF del comparador"),
            html.P("El PDF generado incluye:", style={"fontSize":"12px","color":"#374151"}),
            html.Ul([
                html.Li("Radar charts superpuestos de ambos jugadores.", style={"fontSize":"12px","color":"#374151","marginBottom":"3px"}),
                html.Li("Tabla de métricas comparadas con Δ por columna.", style={"fontSize":"12px","color":"#374151","marginBottom":"3px"}),
                html.Li("Scores de Fit Rayo y desglose por dimensión.", style={"fontSize":"12px","color":"#374151","marginBottom":"3px"}),
                html.Li("Datos contractuales: valor TM, salario, expiración, cláusula.", style={"fontSize":"12px","color":"#374151","marginBottom":"3px"}),
                html.Li("Veredicto final con justificación textual.", style={"fontSize":"12px","color":"#374151","marginBottom":"3px"}),
            ], style={"paddingLeft":"20px","marginTop":"4px"}),
        ], style=CARD),
    ])


# ═══════════════════════════════════════════════════════════════════════════
# TAB 4 — ENTRENADORES
# ═══════════════════════════════════════════════════════════════════════════
def _tab_entrenadores():
    cw = DNA["context_weights"]
    return html.Div([
        html.Div([
            _section("4a", "Ejes de estilo de juego"),
            html.P("Para describir el estilo de un entrenador comparamos cómo han jugado sus equipos "
                   "con el resto de equipos de la misma liga y temporada. "
                   "Así el contexto es siempre justo: rendir en Segunda no penaliza vs Primera.",
                   style={"fontSize":"12px","color":"#374151"}),
            html.P("Se calculan cinco ejes (0-100 = percentil en su liga):",
                   style={"fontSize":"12px","color":"#374151","marginTop":"6px"}),
            html.Table([
                html.Thead(html.Tr([html.Th("Eje",style=TH),html.Th("Qué mide",style=TH),
                                    html.Th("< 40",style=TH),html.Th("40-66",style=TH),html.Th("≥ 66",style=TH)])),
                html.Tbody([
                    html.Tr([html.Td("Tendencia ofensiva",style={**TD,"fontWeight":"700"}),
                             html.Td("Disparos, xG, goles, pases clave, posesión rival",style=TD),
                             html.Td("Bajo",style={**TD,"color":"#991B1B"}),html.Td("Medio",style={**TD,"color":"#92400E"}),
                             html.Td("Alto",style={**TD,"color":"#166534"})]),
                    html.Tr([html.Td("Solidez defensiva",style={**TD,"fontWeight":"700"}),
                             html.Td("Goles encajados (−), porterías a cero",style=TD),
                             html.Td("Bajo",style={**TD,"color":"#991B1B"}),html.Td("Medio",style={**TD,"color":"#92400E"}),
                             html.Td("Alto",style={**TD,"color":"#166534"})]),
                    html.Tr([html.Td("Presión alta",style={**TD,"fontWeight":"700"}),
                             html.Td("Recuperaciones en campo rival, robos, faltas cometidas",style=TD),
                             html.Td("Bajo",style={**TD,"color":"#991B1B"}),html.Td("Medio",style={**TD,"color":"#92400E"}),
                             html.Td("Alto",style={**TD,"color":"#166534"})]),
                    html.Tr([html.Td("Intensidad defensiva",style={**TD,"fontWeight":"700"}),
                             html.Td("Entradas, interceptaciones, duelos, faltas, duelos aéreos",style=TD),
                             html.Td("Bajo",style={**TD,"color":"#991B1B"}),html.Td("Medio",style={**TD,"color":"#92400E"}),
                             html.Td("Alto",style={**TD,"color":"#166534"})]),
                    html.Tr([html.Td("Verticalidad",style={**TD,"fontWeight":"700"}),
                             html.Td("Pases largos completados, balones campo contrario, regates",style=TD),
                             html.Td("Bajo",style={**TD,"color":"#991B1B"}),html.Td("Medio",style={**TD,"color":"#92400E"}),
                             html.Td("Alto",style={**TD,"color":"#166534"})]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse","marginBottom":"8px"}),
        ], style=CARD),

        html.Div([
            _section("4b", "Métricas detalladas por eje"),
            html.P("Pesos reales del código para cada eje (generados desde coach_style.py):",
                   style={"fontSize":"12px","color":"#374151","marginBottom":"8px"}),
            _coach_axes_table(),
        ], style=CARD),

        html.Div([
            _section("4c", "Fit Rayo del entrenador (score /10)"),
            html.P("Combina cuatro sub-scores ponderados:", style={"fontSize":"12px","color":"#374151"}),
            _formula(
                f"Fit_entrenador = w_style × Score_estilo\n"
                f"               + {cw['laliga_experience']:.0%} × Experiencia_LaLiga\n"
                f"               + {cw['budget_fit']:.0%} × Encaje_presupuesto\n"
                f"               + {cw['squad_compatibility']:.0%} × Compatibilidad_plantilla\n\n"
                f"(donde w_style = 1 − {cw['laliga_experience']:.2f} − {cw['budget_fit']:.2f} − {cw['squad_compatibility']:.2f})"
            ),
            html.Table([
                html.Thead(html.Tr([html.Th("Sub-score",style=TH),html.Th("Peso",style=TH),html.Th("Cómo se calcula",style=TH)])),
                html.Tbody([
                    html.Tr([html.Td("Score de estilo",style=TD),
                             html.Td("Restante",style={**TD,"fontWeight":"700"}),
                             html.Td("Distancia euclidiana entre ejes del entrenador y ADN objetivo Rayo",style=TD)]),
                    html.Tr([html.Td("Experiencia LaLiga",style=TD),
                             html.Td(f"{cw['laliga_experience']:.0%}",style={**TD,"fontWeight":"700","color":"#166534"}),
                             html.Td("0 temp=0, 1-3 temp= proporcional, ≥4 temp=máximo",style=TD)]),
                    html.Tr([html.Td("Encaje presupuesto",style=TD),
                             html.Td(f"{cw['budget_fit']:.0%}",style={**TD,"fontWeight":"700","color":"#166534"}),
                             html.Td("Salario entrenador vs referencia club; superar 1.5× penaliza",style=TD)]),
                    html.Tr([html.Td("Compatibilidad plantilla",style=TD),
                             html.Td(f"{cw['squad_compatibility']:.0%}",style={**TD,"fontWeight":"700","color":"#166534"}),
                             html.Td("Penaliza si su estilo exige perfiles ausentes en la plantilla actual",style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse","marginBottom":"8px"}),
            _note("Con solo 1 temporada de datos el score se penaliza ×0.90."),

            _subsection("ADN objetivo del Rayo (parámetros reales del config)"),
            _dna_table(),

            _subsection("Bandas de Fit entrenador"),
            html.Table([
                html.Thead(html.Tr([html.Th("Score",style=TH),html.Th("Interpretación",style=TH)])),
                html.Tbody([
                    html.Tr([html.Td("8.0 - 10.0",style={**TD,"color":"#166534","fontWeight":"700"}),html.Td("Encaje excelente",style=TD)]),
                    html.Tr([html.Td("6.5 - 7.9",style=TD),html.Td("Muy buen candidato",style=TD)]),
                    html.Tr([html.Td("5.0 - 6.4",style=TD),html.Td("Candidato viable",style=TD)]),
                    html.Tr([html.Td("3.5 - 4.9",style={**TD,"color":"#92400E","fontWeight":"700"}),html.Td("Dudoso",style=TD)]),
                    html.Tr([html.Td("< 3.5",style={**TD,"color":"#991B1B","fontWeight":"700"}),html.Td("No encaja con el proyecto",style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse"}),
        ], style=CARD),

        html.Div([
            _section("4d", "Pros, contras y riesgos — lógica de reglas"),
            html.P("Se generan automáticamente por reglas a partir de los ejes y el contexto:",
                   style={"fontSize":"12px","color":"#374151"}),
            html.Table([
                html.Thead(html.Tr([html.Th("Condición",style=TH),html.Th("Tipo",style=TH),html.Th("Mensaje generado",style=TH)])),
                html.Tbody([
                    html.Tr([html.Td("Solidez defensiva ≥ 66",style=TD),html.Td("✅ Pro",style={**TD,"color":"#166534"}),
                             html.Td("Equipo muy sólido defensivamente",style=TD)]),
                    html.Tr([html.Td("Tendencia ofensiva ≥ 66",style=TD),html.Td("✅ Pro",style={**TD,"color":"#166534"}),
                             html.Td("Alto potencial generador de juego ofensivo",style=TD)]),
                    html.Tr([html.Td("Presión alta ≥ 66",style=TD),html.Td("✅ Pro",style={**TD,"color":"#166534"}),
                             html.Td("Pressing intenso, compatible con ADN Rayo",style=TD)]),
                    html.Tr([html.Td("0 temporadas en LaLiga",style=TD),html.Td("⚠ Contra",style={**TD,"color":"#92400E"}),
                             html.Td("Sin experiencia en LaLiga — riesgo de adaptación alto",style=TD)]),
                    html.Tr([html.Td("Salario > 1.5× referencia",style=TD),html.Td("⚠ Contra",style={**TD,"color":"#92400E"}),
                             html.Td("Coste salarial por encima del rango del club",style=TD)]),
                    html.Tr([html.Td("Eje exige perfil ausente",style=TD),html.Td("⚠ Contra",style={**TD,"color":"#92400E"}),
                             html.Td("Incompatibilidad con la plantilla actual en posición X",style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse"}),
        ], style=CARD),
    ])


# ═══════════════════════════════════════════════════════════════════════════
# TAB 5 — DECISIONES
# ═══════════════════════════════════════════════════════════════════════════
def _tab_decisiones():
    return html.Div([
        html.Div([
            _section("5a", "Score de recomendación de fichaje (0-100)"),
            _formula("Score_fichaje = 0.50 × Fit_Rayo\n"
                     "              + 0.20 × Score_contractual\n"
                     "              + 0.20 × Viabilidad_económica\n"
                     "              + 0.10 × Afinidad_entrenador"),
            html.Table([
                html.Thead(html.Tr([html.Th("Factor",style=TH),html.Th("Peso",style=TH),
                                    html.Th("Cómo se puntúa",style=TH)])),
                html.Tbody([
                    html.Tr([html.Td("Fit Rayo",style={**TD,"fontWeight":"700"}),
                             html.Td("50%",style={**TD,"color":"#166534","fontWeight":"700"}),
                             html.Td("Directamente el score 0-100 del scouting",style=TD)]),
                    html.Tr([html.Td("Situación contractual",style={**TD,"fontWeight":"700"}),
                             html.Td("20%",style={**TD,"color":"#166534","fontWeight":"700"}),
                             html.Td("Libre=100, expira 1 año=75, expira 2 años=50, cláusula >2×MV=−20pts",style=TD)]),
                    html.Tr([html.Td("Viabilidad económica",style={**TD,"fontWeight":"700"}),
                             html.Td("20%",style={**TD,"color":"#166534","fontWeight":"700"}),
                             html.Td("MV < 50% presupuesto=100, 50-100%=50, > 100%=0",style=TD)]),
                    html.Tr([html.Td("Afinidad entrenador",style={**TD,"fontWeight":"700"}),
                             html.Td("10%",style={**TD,"color":"#166534","fontWeight":"700"}),
                             html.Td("Distancia entre percentiles del jugador y el estilo demandado",style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse","marginBottom":"8px"}),
            html.Table([
                html.Thead(html.Tr([html.Th("Score",style=TH),html.Th("Recomendación",style=TH)])),
                html.Tbody([
                    html.Tr([html.Td("≥ 70",style={**TD,"color":"#166534","fontWeight":"700"}),
                             html.Td("🟢 FICHAR — candidato prioritario",style=TD)]),
                    html.Tr([html.Td("50-69",style={**TD,"color":"#92400E","fontWeight":"700"}),
                             html.Td("🟡 ESTUDIAR — requiere análisis adicional",style=TD)]),
                    html.Tr([html.Td("< 50",style={**TD,"color":"#991B1B","fontWeight":"700"}),
                             html.Td("🔴 DESCARTAR",style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse"}),
        ], style=CARD),

        html.Div([
            _section("5b", "Explorador de candidatos"),
            html.P("El explorador de la pestaña Fichar aplica estos criterios en cascada:",
                   style={"fontSize":"12px","color":"#374151"}),
            _formula("1. Filtra por posición(es) necesitada(s) según estado de cobertura\n"
                     "2. Aplica filtros del usuario (liga, edad, minutos, Fit mín, MV máx)\n"
                     "3. Ordena por Score_fichaje DESC\n"
                     "4. Muestra top-N candidatos con panel de detalle expandible"),
            _note("La necesidad de posición viene del cálculo automático de la plantilla (sección 1d). "
                  "Si no hay necesidad, el explorador muestra todos los jugadores con Fit ≥ 50."),
        ], style=CARD),

        html.Div([
            _section("5c", "Motor de renovaciones"),
            html.P("Clasifica a cada jugador de la plantilla en tres niveles de acción:",
                   style={"fontSize":"12px","color":"#374151"}),
            _formula("renewal_score(j) = 0.40 × Fit_rendimiento\n"
                     "                 + 0.30 × Titularidad  (minutos/90 vs umbral)\n"
                     "                 + 0.20 × Meses_contrato_restantes  (normalizado 0-36)\n"
                     "                 + 0.10 × Relación_salario/MV"),
            html.Table([
                html.Thead(html.Tr([html.Th("Nivel",style=TH),html.Th("Criterio principal",style=TH),
                                    html.Th("Acción",style=TH)])),
                html.Tbody([
                    html.Tr([html.Td("🔴 Renovar URGENTE",style={**TD,"color":"#991B1B","fontWeight":"700"}),
                             html.Td("Contrato ≤ 12 meses + titular (>1500 min) + Fit ≥ 65",style=TD),
                             html.Td("Iniciar negociación inmediata",style=TD)]),
                    html.Tr([html.Td("🟡 Evaluar",style={**TD,"color":"#92400E","fontWeight":"700"}),
                             html.Td("Contrato ≤ 24 meses o minutos 900-1499",style=TD),
                             html.Td("Valorar en próxima ventana",style=TD)]),
                    html.Tr([html.Td("⚫ No renovar",style={**TD,"color":"#374151","fontWeight":"700"}),
                             html.Td("< 900 min, Fit < 50 o salario > 2× MV estimado",style=TD),
                             html.Td("Planificar salida o no accionar",style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse"}),
        ], style=CARD),

        html.Div([
            _section("5d", "Candidatos a salida"),
            html.P("Algoritmo en tres pasos:", style={"fontSize":"12px","color":"#374151"}),
            _formula("Paso 1: Fit_rendimiento < 40  →  candidato a salida\n"
                     "Paso 2: Cedido con < 900 min en club destino  →  candidato a salida\n"
                     "Paso 3: salario_anual > 2 × MV_estimado  →  candidato a salida\n\n"
                     "Tipo de salida sugerido:\n"
                     "  Contrato expira ≤ 12m  →  'Dejar salir libre'\n"
                     "  MV > 0.5M€            →  'Vender'\n"
                     "  MV ≤ 0.5M€            →  'Ceder'"),
        ], style=CARD),

        html.Div([
            _section("5e", "Estimación de salario y cláusula"),
            html.P("Para jugadores sin dato confirmado la herramienta usa salary_estimates.yaml:",
                   style={"fontSize":"12px","color":"#374151"}),
            _formula("salario_estimado = referencia_base(liga, posición, edad)\n"
                     "                × factor_rol  (titular=1.0, suplente=0.75)\n"
                     "                × factor_liga (LaLiga=1.0, Segunda=0.60...)\n\n"
                     "cláusula_estimada ≈ MV × 1.5  (sin dato real)"),
            _note("Los valores de SalaryLeaks y Capology tienen siempre prioridad sobre las estimaciones."),
        ], style=CARD),

        html.Div([
            _section("5f", "Interés externo (Score 0-100)"),
            html.P("Determina qué jugadores del Rayo pueden recibir ofertas:",
                   style={"fontSize":"12px","color":"#374151"}),
            html.Table([
                html.Thead(html.Tr([html.Th("Factor",style=TH),html.Th("Peso",style=TH),html.Th("Detalle",style=TH)])),
                html.Tbody([
                    html.Tr([html.Td("Meses restantes contrato",style=TD),html.Td("30%",style={**TD,"fontWeight":"700"}),
                             html.Td("≤6m=30, ≤12m=20, ≤24m=10, >24m=0",style=TD)]),
                    html.Tr([html.Td("Ratio cláusula / MV",style=TD),html.Td("30%",style={**TD,"fontWeight":"700"}),
                             html.Td("<1×=30, 1-2×=15, >3×=0",style=TD)]),
                    html.Tr([html.Td("Edad (pico demanda 24-28)",style=TD),html.Td("20%",style={**TD,"fontWeight":"700"}),
                             html.Td("24-28=20, 22-23=12, <22 o >31=0",style=TD)]),
                    html.Tr([html.Td("Interés confirmado (prensa/agente)",style=TD),html.Td("20%",style={**TD,"fontWeight":"700"}),
                             html.Td("Confirmado=20, Sondeado=10, Sin noticias=0",style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse","marginBottom":"8px"}),
            html.Table([
                html.Thead(html.Tr([html.Th("Score",style=TH),html.Th("Nivel de riesgo",style=TH)])),
                html.Tbody([
                    html.Tr([html.Td("≥ 70",style={**TD,"color":"#991B1B","fontWeight":"700"}),html.Td("MUY ALTO",style=TD)]),
                    html.Tr([html.Td("50-69",style={**TD,"color":"#C2410C","fontWeight":"700"}),html.Td("ALTO",style=TD)]),
                    html.Tr([html.Td("30-49",style={**TD,"color":"#92400E","fontWeight":"700"}),html.Td("MEDIO",style=TD)]),
                    html.Tr([html.Td("< 30",style={**TD,"color":"#166534","fontWeight":"700"}),html.Td("BAJO",style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse"}),
        ], style=CARD),
    ])


# ═══════════════════════════════════════════════════════════════════════════
# TAB 6 — FINANZAS
# ═══════════════════════════════════════════════════════════════════════════
def _tab_finanzas():
    return html.Div([
        html.Div([
            _section("6a", "Masa salarial y límite LaLiga"),
            _formula("Masa_salarial_bruta = Σ salary_annual(j)  para j ∈ plantilla_activa\n\n"
                     "% Límite_FFP = Masa_salarial_bruta / Límite_LaLiga × 100"),
            html.Table([
                html.Thead(html.Tr([html.Th("% del límite",style=TH),html.Th("Estado",style=TH),html.Th("Color",style=TH)])),
                html.Tbody([
                    html.Tr([html.Td("< 75%",style=TD),html.Td("Margen salarial amplio",style=TD),html.Td("🟢 Verde",style=TD)]),
                    html.Tr([html.Td("75-90%",style=TD),html.Td("Precaución — margen limitado",style=TD),html.Td("🟡 Ámbar",style=TD)]),
                    html.Tr([html.Td("> 90%",style=TD),html.Td("Zona de riesgo FFP",style=TD),html.Td("🔴 Rojo",style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse"}),
        ], style=CARD),

        html.Div([
            _section("6b", "Presupuesto estimado"),
            html.P("Estructura de ingresos y gastos usada en la pestaña Finanzas > Presupuesto:",
                   style={"fontSize":"12px","color":"#374151"}),
            html.Div([
                html.Div([
                    _subsection("Ingresos estimados"),
                    html.Table([
                        html.Thead(html.Tr([html.Th("Concepto",style=TH),html.Th("Estimación (M€)",style=TH)])),
                        html.Tbody([
                            html.Tr([html.Td("Derechos TV LaLiga",style=TD),html.Td("~30-35",style=TD)]),
                            html.Tr([html.Td("UEFA (competición europea)",style=TD),html.Td("Variable (0 si no clasifica)",style=TD)]),
                            html.Tr([html.Td("Matchday (taquilla, abonados)",style=TD),html.Td("~4-6",style=TD)]),
                            html.Tr([html.Td("Ingresos comerciales",style=TD),html.Td("~3-5",style=TD)]),
                            html.Tr([html.Td("Traspasos / ventas",style=TD),html.Td("Variable — ingresado en sim.",style=TD)]),
                        ]),
                    ], style={"width":"100%","borderCollapse":"collapse"}),
                ], style={"flex":"1","marginRight":"8px"}),
                html.Div([
                    _subsection("Gastos estimados"),
                    html.Table([
                        html.Thead(html.Tr([html.Th("Concepto",style=TH),html.Th("Cálculo",style=TH)])),
                        html.Tbody([
                            html.Tr([html.Td("Masa salarial bruta",style=TD),html.Td("Desde datos plantilla",style=TD)]),
                            html.Tr([html.Td("Amortización de traspasos",style=TD),html.Td("fee / años_contrato por jugador",style=TD)]),
                            html.Tr([html.Td("Costes operativos",style=TD),html.Td("~10-15% ingresos totales",style=TD)]),
                            html.Tr([html.Td("Nuevas compras (sim.)",style=TD),html.Td("Σ fee + salario × años",style=TD)]),
                        ]),
                    ], style={"width":"100%","borderCollapse":"collapse"}),
                ], style={"flex":"1"}),
            ], style={"display":"flex","gap":"8px"}),
            _formula("Balance = Ingresos_totales − Gastos_totales\n\n"
                     "Caja_neta = Balance + Caja_inicial − Amortizaciones_pagadas"),
        ], style=CARD),

        html.Div([
            _section("6c", "Riesgo de cláusula (score 0-100 por jugador)"),
            _formula("Riesgo_cláusula(j) = 0.30 × Score_meses_contrato\n"
                     "                   + 0.30 × Score_ratio_cláusula_MV\n"
                     "                   + 0.20 × Score_edad\n"
                     "                   + 0.20 × Score_interés_externo"),
            html.Table([
                html.Thead(html.Tr([html.Th("Factor",style=TH),html.Th("Peso",style=TH),
                                    html.Th("Puntuación",style=TH)])),
                html.Tbody([
                    html.Tr([html.Td("Meses restantes contrato",style=TD),html.Td("30%",style={**TD,"fontWeight":"700"}),
                             html.Td("≤6m=30 · ≤12m=20 · ≤24m=10 · >24m=0",style=TD)]),
                    html.Tr([html.Td("Ratio cláusula / MV",style=TD),html.Td("30%",style={**TD,"fontWeight":"700"}),
                             html.Td("<1×=30 · 1-2×=15 · 2-3×=7 · >3×=0",style=TD)]),
                    html.Tr([html.Td("Edad (pico 24-28)",style=TD),html.Td("20%",style={**TD,"fontWeight":"700"}),
                             html.Td("24-28=20 · 22-23=12 · 29-30=8 · resto=0",style=TD)]),
                    html.Tr([html.Td("Interés externo confirmado",style=TD),html.Td("20%",style={**TD,"fontWeight":"700"}),
                             html.Td("Confirmado=20 · Sondeado=10 · Ninguno=0",style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse","marginBottom":"8px"}),
            html.Table([
                html.Thead(html.Tr([html.Th("Score",style=TH),html.Th("Nivel",style=TH),html.Th("Color",style=TH)])),
                html.Tbody([
                    html.Tr([html.Td("≥ 70",style=TD),html.Td("MUY ALTO",style={**TD,"color":"#991B1B","fontWeight":"700"}),html.Td("🔴 Rojo",style=TD)]),
                    html.Tr([html.Td("50-69",style=TD),html.Td("ALTO",style={**TD,"color":"#C2410C","fontWeight":"700"}),html.Td("🟠 Naranja",style=TD)]),
                    html.Tr([html.Td("30-49",style=TD),html.Td("MEDIO",style={**TD,"color":"#92400E","fontWeight":"700"}),html.Td("🟡 Ámbar",style=TD)]),
                    html.Tr([html.Td("< 30",style=TD),html.Td("BAJO",style={**TD,"color":"#166534","fontWeight":"700"}),html.Td("🟢 Verde",style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse"}),
        ], style=CARD),

        html.Div([
            _section("6d", "Scatter: Cláusula vs Valor de mercado"),
            html.P("El gráfico de dispersión de la pestaña Finanzas muestra cada jugador como un punto:",
                   style={"fontSize":"12px","color":"#374151"}),
            html.Table([
                html.Thead(html.Tr([html.Th("Eje / Elemento",style=TH),html.Th("Qué representa",style=TH)])),
                html.Tbody([
                    html.Tr([html.Td("Eje X",style=TD),html.Td("Valor de mercado TM (M€)",style=TD)]),
                    html.Tr([html.Td("Eje Y",style=TD),html.Td("Cláusula de rescisión (M€)",style=TD)]),
                    html.Tr([html.Td("Tamaño del punto",style=TD),html.Td("Salario anual bruto",style=TD)]),
                    html.Tr([html.Td("Color",style=TD),html.Td("Score de riesgo de cláusula (verde→rojo)",style=TD)]),
                    html.Tr([html.Td("Línea diagonal",style=TD),html.Td("Cláusula = MV (ratio 1×); puntos por encima = cláusula cara",style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse"}),
        ], style=CARD),

        html.Div([
            _section("6e", "Simulador Económico — fórmulas"),
            html.P("El simulador acumula múltiples ventas y compras y calcula el impacto en tiempo real:",
                   style={"fontSize":"12px","color":"#374151"}),
            _formula(
                "# Ventas acumuladas\n"
                "saved_salary = Σ salary_annual(j)  para j ∈ ventas\n"
                "income       = Σ fee_venta(j)       para j ∈ ventas\n\n"
                "# Compras acumuladas\n"
                "new_salary   = Σ salary_compra(j)   para j ∈ compras\n"
                "fee_total    = Σ fee_compra(j)       para j ∈ compras\n"
                "new_amort    = Σ fee(j) / años_contrato(j)  para j ∈ compras\n\n"
                "# Impacto\n"
                "delta_masa_salarial = new_salary − saved_salary\n"
                "delta_amort         = new_amort − amort_salidas\n"
                "delta_caja          = income − fee_total\n\n"
                "# LaLiga FFP tras operación\n"
                "nueva_masa = masa_actual + delta_masa_salarial\n"
                "pct_limite = nueva_masa / limite_laliga"
            ),
            _note("La caja incluye el coste de traspaso completo desembolsado, "
                  "no solo la amortización anual."),
        ], style=CARD),

        html.Div([
            _section("6f", "Simulador de Fichajes — dimensiones del score"),
            html.P("El score de viabilidad de un fichaje individual (en pestaña Simulador de Fichajes) "
                   "combina tres dimensiones:",
                   style={"fontSize":"12px","color":"#374151"}),
            _formula("Score_viabilidad = 0.40 × Impacto_masa_salarial\n"
                     "                 + 0.35 × Retorno_MV_esperado  (proyección 3 años)\n"
                     "                 + 0.25 × Liberación_salarial  (si hay salida asociada)\n\n"
                     "Retorno_MV = MV_actual × factor_crecimiento_edad\n"
                     "  factor: ≤21→1.40, 22-24→1.25, 25-27→1.10, 28-30→0.95, >30→0.80"),
        ], style=CARD),
    ])


# ═══════════════════════════════════════════════════════════════════════════
# TAB 7 — FUENTES DE DATOS
# ═══════════════════════════════════════════════════════════════════════════
def _tab_fuentes():
    return html.Div([
        html.Div([
            _section("7a", "Estadísticas de rendimiento"),
            html.Table([
                html.Thead(html.Tr([html.Th("Proveedor",style=TH),html.Th("Datos",style=TH),html.Th("Cobertura",style=TH)])),
                html.Tbody([
                    html.Tr([html.Td("OPTA / Stats Perform",style={**TD,"fontWeight":"700"}),
                             html.Td("Métricas avanzadas por 90 min: pases, disparos, duelos, presión, xG, xA...",style=TD),
                             html.Td("LaLiga, Segunda, principales ligas europeas",style=TD)]),
                    html.Tr([html.Td("Understat",style={**TD,"fontWeight":"700"}),
                             html.Td("xG, xA, tiros, npxG",style=TD),
                             html.Td("6 ligas top europeas",style=TD)]),
                    html.Tr([html.Td("FBref / StatsBomb",style={**TD,"fontWeight":"700"}),
                             html.Td("Métricas de presión, portería, pase progresivo",style=TD),
                             html.Td("Ligas principales",style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse"}),
        ], style=CARD),

        html.Div([
            _section("7b", "Valores de mercado"),
            html.Table([
                html.Thead(html.Tr([html.Th("Proveedor",style=TH),html.Th("Qué aporta",style=TH),html.Th("Actualización",style=TH)])),
                html.Tbody([
                    html.Tr([html.Td("Transfermarkt",style={**TD,"fontWeight":"700"}),
                             html.Td("Valor de mercado (MV) individual, historial, cláusula si disponible",style=TD),
                             html.Td("~2 veces por temporada",style=TD)]),
                    html.Tr([html.Td("TM API (no oficial)",style={**TD,"fontWeight":"700"}),
                             html.Td("Scraping estructurado vía fetch_tm_ids.py",style=TD),
                             html.Td("Manual o script programado",style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse"}),
            _note("Los valores TM son orientativos. No constituyen precios de transacción garantizados."),
        ], style=CARD),

        html.Div([
            _section("7c", "Salarios"),
            html.Table([
                html.Thead(html.Tr([html.Th("Fuente",style=TH),html.Th("Qué aporta",style=TH),html.Th("Prioridad",style=TH)])),
                html.Tbody([
                    html.Tr([html.Td("SalaryLeaks",style={**TD,"fontWeight":"700"}),
                             html.Td("Salarios publicados LaLiga",style=TD),
                             html.Td("🥇 Máxima (dato real)",style=TD)]),
                    html.Tr([html.Td("Capology",style={**TD,"fontWeight":"700"}),
                             html.Td("Salarios estimados y confirmados por liga",style=TD),
                             html.Td("🥈 Alta (dato verificado)",style=TD)]),
                    html.Tr([html.Td("salary_estimates.yaml",style={**TD,"fontWeight":"700"}),
                             html.Td("Estimaciones por liga, posición y edad",style=TD),
                             html.Td("🥉 Fallback (cuando no hay dato real)",style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse"}),
        ], style=CARD),

        html.Div([
            _section("7d", "Datos de entrenadores"),
            html.Table([
                html.Thead(html.Tr([html.Th("Fuente",style=TH),html.Th("Qué aporta",style=TH)])),
                html.Tbody([
                    html.Tr([html.Td("OPTA / Stats Perform",style={**TD,"fontWeight":"700"}),
                             html.Td("Estadísticas de equipo por temporada para calcular ejes de estilo",style=TD)]),
                    html.Tr([html.Td("Transfermarkt",style={**TD,"fontWeight":"700"}),
                             html.Td("Historial de clubes dirigidos, fechas, ligas",style=TD)]),
                    html.Tr([html.Td("Wikipedia / prensa",style={**TD,"fontWeight":"700"}),
                             html.Td("Datos biográficos, palmarés, contratos publicados",style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse"}),
        ], style=CARD),

        html.Div([
            _section("7e", "Ligas cubiertas"),
            html.P("Cobertura principal (percentiles y scouting completos):",
                   style={"fontSize":"12px","color":"#374151","fontWeight":"600"}),
            html.Table([
                html.Thead(html.Tr([html.Th("Liga",style=TH),html.Th("País",style=TH),html.Th("Factor",style=TH)])),
                html.Tbody([
                    html.Tr([html.Td("LaLiga",style=TD),html.Td("España",style=TD),html.Td("1.00",style=TD)]),
                    html.Tr([html.Td("Segunda División",style=TD),html.Td("España",style=TD),html.Td("0.82",style=TD)]),
                    html.Tr([html.Td("Premier League",style=TD),html.Td("Inglaterra",style=TD),html.Td("1.00",style=TD)]),
                    html.Tr([html.Td("Bundesliga",style=TD),html.Td("Alemania",style=TD),html.Td("0.97",style=TD)]),
                    html.Tr([html.Td("Serie A",style=TD),html.Td("Italia",style=TD),html.Td("0.97",style=TD)]),
                    html.Tr([html.Td("Ligue 1",style=TD),html.Td("Francia",style=TD),html.Td("0.92",style=TD)]),
                    html.Tr([html.Td("Primeira Liga",style=TD),html.Td("Portugal",style=TD),html.Td("0.88",style=TD)]),
                    html.Tr([html.Td("Eredivisie",style=TD),html.Td("Países Bajos",style=TD),html.Td("0.88",style=TD)]),
                    html.Tr([html.Td("Primera RFEF",style=TD),html.Td("España",style=TD),html.Td("0.70",style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse","marginBottom":"8px"}),
            _note("Para ligas no listadas se usa factor 0.65 como valor conservador. "
                  "La cobertura ampliada (ligas sudamericanas, MLS) tiene datos limitados."),
        ], style=CARD),
    ])


# ═══════════════════════════════════════════════════════════════════════════
# LAYOUT Y CALLBACK
# ═══════════════════════════════════════════════════════════════════════════
TAB_CONTENT = {
    "plantilla":    _tab_plantilla,
    "scouting":     _tab_scouting,
    "comparador":   _tab_comparador,
    "entrenadores": _tab_entrenadores,
    "decisiones":   _tab_decisiones,
    "finanzas":     _tab_finanzas,
    "fuentes":      _tab_fuentes,
}

TAB_LABELS = {
    "plantilla":    ("ti-users-group", "Plantilla"),
    "scouting":     ("ti-search",      "Scouting"),
    "comparador":   ("ti-arrows-left-right", "Comparador"),
    "entrenadores": ("ti-chalkboard",  "Entrenadores"),
    "decisiones":   ("ti-checklist",   "Decisiones"),
    "finanzas":     ("ti-coin",        "Finanzas"),
    "fuentes":      ("ti-database",    "Fuentes"),
}


def _tab_btn(key, active):
    icon, label = TAB_LABELS[key]
    is_active = key == active
    return dcc.Tab(
        label=label,
        value=key,
        style={"padding":"10px 16px","fontSize":"12px","fontWeight":"600",
               "color":"#6B7280","border":"none","borderBottom":"2px solid transparent",
               "background":"transparent","cursor":"pointer"},
        selected_style={"padding":"10px 16px","fontSize":"12px","fontWeight":"700",
                        "color":"#E30613","border":"none","borderBottom":"2px solid #E30613",
                        "background":"transparent"},
    )


def layout(**_p):
    return html.Div([
        # Hero
        html.Div([
            html.Div([
                html.Div([html.I(className="ti ti-list-check",
                           style={"fontSize":"28px","color":"#fff"})],
                    style={"background":"rgba(255,255,255,.15)","borderRadius":"12px",
                           "padding":"10px","marginRight":"18px","flexShrink":"0"}),
                html.Div([
                    html.Div("TRANSPARENCIA", style={"fontSize":"9px","fontWeight":"700",
                        "color":"rgba(255,255,255,.55)","letterSpacing":".14em","marginBottom":"3px"}),
                    html.H1("Criterios y Cálculos", style={"fontSize":"22px","fontWeight":"900",
                        "color":"#fff","margin":"0 0 2px"}),
                    html.Div("Todas las fórmulas y pesos reales del código, organizados por módulo",
                        style={"fontSize":"10px","color":"rgba(255,255,255,.5)"}),
                ]),
            ], style={"display":"flex","alignItems":"center"}),
        ], style={"background":"linear-gradient(135deg,#0D0D0D 0%,#1A1A1A 55%,#2D2D2D 100%)",
                  "borderRadius":"18px","padding":"20px 26px","marginBottom":"18px",
                  "boxShadow":"0 8px 24px rgba(159,18,57,.25)"}),

        # Info banner
        html.Div([
            html.I(className="ti ti-info-circle",
                   style={"fontSize":"18px","color":"#FFD600","marginRight":"12px","flexShrink":"0"}),
            html.P("Las tablas se generan automáticamente desde los mismos pesos que usa la herramienta. "
                   "Si el código cambia, esta página lo refleja al instante. Sin datos manuales.",
                   style={"fontSize":"12px","color":"#374151","margin":"0"}),
        ], style={"background":"#FFFDE7","border":"1px solid #FFD600","borderRadius":"12px",
                  "padding":"14px 16px","marginBottom":"20px","display":"flex","alignItems":"flex-start"}),

        # Tabs
        dcc.Tabs(
            id="crit-tabs",
            value="plantilla",
            children=[_tab_btn(k, "plantilla") for k in TAB_CONTENT],
            style={"borderBottom":"1px solid #E5E7EB","marginBottom":"16px"},
        ),

        # Contenido de la tab activa
        html.Div(id="crit-content"),
    ])


@callback(Output("crit-content", "children"), Input("crit-tabs", "value"))
def _render_tab(tab):
    fn = TAB_CONTENT.get(tab, _tab_plantilla)
    return fn()
