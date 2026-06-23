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
    head = html.Tr([html.Th("Metrica (por 90 min)", style=TH), html.Th("Peso", style=TH)])
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
    head = html.Tr([html.Th("Eje de estilo", style=TH), html.Th("Metricas de equipo y peso", style=TH)])
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
                    html.H1("Criterios de Puntuacion", style={"fontSize":"22px","fontWeight":"900",
                        "color":"#fff","margin":"0 0 2px"}),
                    html.Div("Pesos y formulas reales del codigo, siempre sincronizados con el output",
                        style={"fontSize":"10px","color":"rgba(255,255,255,.5)"}),
                ]),
            ], style={"display":"flex","alignItems":"center"}),
        ], style={"background":"linear-gradient(135deg,#0D0D0D 0%,#1A1A1A 55%,#2D2D2D 100%)",
                  "borderRadius":"18px","padding":"20px 26px","marginBottom":"18px",
                  "boxShadow":"0 8px 24px rgba(159,18,57,.25)"}),

        # Descripcion
        html.Div([
            html.Div([
                html.I(className="ti ti-info-circle",
                       style={"fontSize":"18px","color":"#FFD600","marginRight":"12px","flexShrink":"0"}),
                html.P("Todas las tablas de esta pagina se generan automaticamente desde los mismos "
                       "pesos que usa la herramienta internamente. Si el codigo cambia, esta pagina "
                       "lo refleja al instante. Sin datos manuales.",
                       style={"fontSize":"12px","color":"#374151","margin":"0"}),
            ], style={"display":"flex","alignItems":"flex-start"}),
        ], style={"background":"#FFFDE7","border":"1px solid #FFD600","borderRadius":"12px",
                  "padding":"14px 16px","marginBottom":"20px"}),

        # 1 PLANTILLA
        _section_chip("ti-users-group", "1 - METODOLOGIA -- PLANTILLA", "#E30613"),
        html.Div([
            html.Div([
                html.Div("1", style={"background":"linear-gradient(135deg,#E30613,#C4000F)",
                    "color":"#fff","borderRadius":"50%","width":"28px","height":"28px",
                    "display":"flex","alignItems":"center","justifyContent":"center",
                    "fontWeight":"900","fontSize":"14px","marginRight":"10px","flexShrink":"0"}),
                html.Span("Plantilla", style={"fontSize":"18px","fontWeight":"800","color":"#1A1A2E"}),
            ], style={"display":"flex","alignItems":"center","marginBottom":"10px"}),
            html.P("Valor de mercado total: suma de los valores TM de los jugadores de la plantilla actual. "
                   "Los sub-21 tienen su propio subtotal.",
                   style={"fontSize":"12px","color":"#374151"}),
            html.P("Contratos por expirar: se marcan como urgentes los que finalizan en 12 meses o menos. "
                   "Se diferencian tres estados: 2026 (inminente), 2027 (proximo), 2028+ (margen).",
                   style={"fontSize":"12px","color":"#374151","marginTop":"6px"}),
            html.P("Distribucion de edad: menor de 21 cantera/futuro, 21-26 proyeccion, 27-30 peak, "
                   "mayor de 30 veterania. El equilibrio ideal del Rayo es aprox 25-26 anos de media.",
                   style={"fontSize":"12px","color":"#374151","marginTop":"6px"}),
            html.P("Perfil posicional: los jugadores se asignan a un grupo segun su posicion principal. "
                   "El conteo determina si hay superavit o deficit en cada linea.",
                   style={"fontSize":"12px","color":"#374151","marginTop":"6px"}),
            html.P("Necesidades de la plantilla: se calculan comparando la plantilla actual con la "
                   "plantilla ideal parametrizada en needs.py. Los huecos generan alertas en Inicio y Decisiones.",
                   style={"fontSize":"12px","color":"#374151","marginTop":"6px"}),
        ], style=CARD),

        # 2 SCOUTING
        _section_chip("ti-search", "2 - METODOLOGIA -- SCOUTING Y PERFIL DE JUGADOR", "#E30613"),
        html.Div([
            html.Div([
                html.Div("2", style={"background":"linear-gradient(135deg,#E30613,#C4000F)",
                    "color":"#fff","borderRadius":"50%","width":"28px","height":"28px",
                    "display":"flex","alignItems":"center","justifyContent":"center",
                    "fontWeight":"900","fontSize":"14px","marginRight":"10px","flexShrink":"0"}),
                html.Span("Perfil de jugador -- calculo de percentiles y roles", style={"fontSize":"18px","fontWeight":"800","color":"#1A1A2E"}),
            ], style={"display":"flex","alignItems":"center","marginBottom":"10px"}),
            html.P(f"Paso 1 -- Percentiles. Cada metrica del jugador se convierte en un percentil 0-100 "
                   f"comparandolo con los jugadores de su mismo grupo posicional y liga. "
                   f"Solo se rankean jugadores con al menos {DEFAULT_MIN_MINUTES} minutos.", style={"fontSize": "12px", "color": "#374151"}),
            html.P("Paso 2 -- Roles. Cada rol es una suma ponderada de esos percentiles. "
                   "El rol con mayor puntuacion es el PRINCIPAL; los que quedan por encima de max(55, principal-12) "
                   "son SECUNDARIOS.", style={"fontSize": "12px", "color": "#374151"}),
            html.P("Paso 3 -- Fortalezas/Debilidades. Fortalezas = metricas con percentil mayor o igual a 60; "
                   "debilidades = percentil menor o igual a 40.", style={"fontSize": "12px", "color": "#374151"}),
            html.P("Confianza: alta mayor o igual a 1800 min, media mayor o igual a 900, baja mayor o igual a 450, si no, insuficiente. "
                   "Potencial por edad: 21 o menos muy alto, 24 o menos alto, 28 o menos estable, 31 o menos meseta, mas de 31 veterania.",
                   style={"fontSize": "12px", "color": "#374151"}),
        ], style=CARD),
        html.P("Pesos de cada rol:",
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
                html.Thead(html.Tr([html.Th("Dimension", style=TH), html.Th("Peso", style=TH), html.Th("Calculo", style=TH)])),
                html.Tbody([
                    html.Tr([html.Td("Rendimiento", style=TD), html.Td("40 %", style={**TD,"fontWeight":"700","color":"#166534"}), html.Td("Percentiles por sub-posicion, ajuste por dificultad de liga", style=TD)]),
                    html.Tr([html.Td("Encaje economico", style=TD), html.Td("30 %", style={**TD,"fontWeight":"700","color":"#166534"}), html.Td("Valor TM vs horquilla de inversion del Rayo", style=TD)]),
                    html.Tr([html.Td("Perfil de edad", style=TD), html.Td("20 %", style={**TD,"fontWeight":"700","color":"#166534"}), html.Td("Curva optima por posicion, prime / declive / potencial", style=TD)]),
                    html.Tr([html.Td("Disponibilidad", style=TD), html.Td("10 %", style={**TD,"fontWeight":"700","color":"#166534"}), html.Td("Contrato expirante, agente libre, cedido con opcion", style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse","marginBottom":"12px"}),
            html.Div([
                html.Div([
                    html.I(className="ti ti-run",
                           style={"color":"#166534","fontSize":"14px","marginRight":"8px"}),
                    html.Span(
                        "Como se calcula el Rendimiento "
                        "(fuente unica, identico en Perfil, Comparador, Decisiones y PDF)",
                        style={"fontSize":"11px","fontWeight":"700","color":"#166534"},
                    ),
                ], style={"display":"flex","alignItems":"center","marginBottom":"8px"}),
                html.P(
                    "Para cada jugador se determina su sub-posicion (Portero, Central, Lateral, "
                    "Pivote, Medio Centro, Mediapunta, Extremo o Delantero Centro). "
                    "El score es la media ponderada de percentiles en las dimensiones relevantes "
                    "para esa sub-posicion, calculados contra jugadores de la misma familia posicional "
                    "y liga con 450 minutos o mas. "
                    "Se aplica un factor de dificultad de liga (La Liga = 1.00, Segunda = 0.82...).",
                    style={"fontSize":"11px","color":"#374151","marginBottom":"8px"},
                ),
                html.Table([
                    html.Thead(html.Tr([
                        html.Th("Sub-posicion", style=TH),
                        html.Th("Dimensiones (peso)", style={**TH,"width":"60%"}),
                    ])),
                    html.Tbody([
                        html.Tr([html.Td("Portero",         style=TD), html.Td("Paradas/90 (45%), Limpiezas (30%), Juego con balon (15%), Duelos aereos (10%)", style=TD)]),
                        html.Tr([html.Td("Central",         style=TD), html.Td("Defensiva: entradas+int+rec+bloqueos (40%), Duelo aereo (25%), Duelo 1v1 (20%), Construccion (15%)", style=TD)]),
                        html.Tr([html.Td("Lateral",         style=TD), html.Td("Defensiva (30%), Proyeccion ofensiva: centros+pases (30%), Duelos (20%), Ataque (20%)", style=TD)]),
                        html.Tr([html.Td("Pivote",          style=TD), html.Td("Recuperacion (40%), Pase (30%), Presion/duelos (20%), Contribucion ofensiva (10%)", style=TD)]),
                        html.Tr([html.Td("Medio Centro",    style=TD), html.Td("Pase (30%), Recuperacion (30%), Creacion (25%), Contribucion (15%)", style=TD)]),
                        html.Tr([html.Td("Mediapunta",      style=TD), html.Td("Creacion (35%), Gol/Remate (30%), Pase en profundidad (20%), Pressing (15%)", style=TD)]),
                        html.Tr([html.Td("Extremo",         style=TD), html.Td("Regates/Desborde (30%), Gol/Remate (30%), Creacion (25%), Pressing (15%)", style=TD)]),
                        html.Tr([html.Td("Delantero Centro",style=TD), html.Td("Gol/Remate (45%), Juego de area: duelos aereos+1v1 (20%), Creacion (20%), Pressing (15%)", style=TD)]),
                    ]),
                ], style={"width":"100%","borderCollapse":"collapse","fontSize":"10px"}),
            ], style={"background":"#F0FDF4","border":"1px solid #BBF7D0",
                      "borderRadius":"8px","padding":"12px 14px","marginBottom":"8px"}),
            html.P("Bandas de Fit: 80 o mas Excelente, 65-79 Muy bueno, 50-64 Bueno, 35-49 Dudoso, menos de 35 No encaja.",
                   style={"fontSize":"11px","color":"#6B7280"}),
            html.P("Filtros del explorador de scouting: liga/pais, edad min/max, minutos minimos, posicion, "
                   "pierna dominante, tipologia de jugador, Fit minimo y valor TM maximo.",
                   style={"fontSize":"12px","color":"#374151","marginTop":"6px"}),
        ], style=CARD),

        # 3 COMPARADOR
        _section_chip("ti-arrows-left-right", "3 - METODOLOGIA -- COMPARADOR", "#E30613"),
        html.Div([
            html.Div([
                html.Div("3", style={"background":"linear-gradient(135deg,#E30613,#C4000F)",
                    "color":"#fff","borderRadius":"50%","width":"28px","height":"28px",
                    "display":"flex","alignItems":"center","justifyContent":"center",
                    "fontWeight":"900","fontSize":"14px","marginRight":"10px","flexShrink":"0"}),
                html.Span("Comparador de jugadores", style={"fontSize":"18px","fontWeight":"800","color":"#1A1A2E"}),
            ], style={"display":"flex","alignItems":"center","marginBottom":"10px"}),
            html.P("La comparacion es siempre head-to-head por percentiles dentro del mismo grupo "
                   "posicional y liga. Ambos jugadores se muestran sobre los mismos ejes para que "
                   "los valores sean directamente comparables.",
                   style={"fontSize":"12px","color":"#374151"}),
            html.P("Radar chart: cada vertice es una metrica clave del grupo posicional. El area "
                   "rellenada refleja el percentil (0 = centro, 100 = borde externo).",
                   style={"fontSize":"12px","color":"#374151","marginTop":"6px"}),
            html.P("Veredicto automatico: suma ponderada de diferencias de percentil. "
                   "Diferencia menor de 5 pts = equivalentes; mayor de 15 pts = claro favorito.",
                   style={"fontSize":"12px","color":"#374151","marginTop":"6px"}),
            html.P("Exportacion PDF: incluye radar charts, tabla de metricas comparadas, "
                   "scores de Fit Rayo, datos contractuales y veredicto final.",
                   style={"fontSize":"12px","color":"#374151","marginTop":"6px"}),
        ], style=CARD),

        # 4 ENTRENADORES
        _section_chip("ti-chalkboard", "4 - METODOLOGIA -- ENTRENADORES", "#E30613"),
        html.Div([
            html.Div([
                html.Div("4", style={"background":"linear-gradient(135deg,#E30613,#C4000F)",
                    "color":"#fff","borderRadius":"50%","width":"28px","height":"28px",
                    "display":"flex","alignItems":"center","justifyContent":"center",
                    "fontWeight":"900","fontSize":"14px","marginRight":"10px","flexShrink":"0"}),
                html.Span("Entrenadores", style={"fontSize":"18px","fontWeight":"800","color":"#1A1A2E"}),
            ], style={"display":"flex","alignItems":"center","marginBottom":"12px"}),
            html.P("Para describir el estilo de un entrenador miramos como han jugado sus equipos a lo largo "
                   "de su carrera. Tomamos los datos de cada temporada que ha dirigido y los comparamos con el "
                   "resto de equipos de esa misma liga, de forma que el contexto siempre sea justo: "
                   "no es lo mismo dominar en Segunda que en Primera.",
                   style={"fontSize": "12px", "color": "#374151"}),
            html.P("De esa comparacion sacamos cinco caracteristicas, cada una expresada de 0 a 100 respecto a su liga:",
                   style={"fontSize": "12px", "color": "#374151", "marginTop": "8px"}),
            html.Ul([
                html.Li("Tendencia ofensiva: si sus equipos disparan mucho, generan ocasiones claras, meten goles y circulan el balon en campo rival.", style={"fontSize": "12px", "color": "#374151", "marginBottom": "4px"}),
                html.Li("Solidez defensiva: si encajan pocos goles y mantienen la porteria a cero con frecuencia.", style={"fontSize": "12px", "color": "#374151", "marginBottom": "4px"}),
                html.Li("Presion alta: si sus equipos recuperan el balon arriba, roban, interceptan y presionan aunque eso implique cometer faltas.", style={"fontSize": "12px", "color": "#374151", "marginBottom": "4px"}),
                html.Li("Intensidad defensiva: cuanto pelean sus equipos por el balon en duelos, entradas, interceptaciones y duelos aereos.", style={"fontSize": "12px", "color": "#374151", "marginBottom": "4px"}),
                html.Li("Verticalidad: si juega directo, con pases largos, juego en campo rival y conducciones hacia adelante.", style={"fontSize": "12px", "color": "#374151", "marginBottom": "4px"}),
            ], style={"paddingLeft": "20px", "marginTop": "4px", "marginBottom": "8px"}),
            html.Table([
                html.Thead(html.Tr([
                    html.Th("Caracteristica", style=TH),
                    html.Th("Que mide", style=TH),
                ])),
                html.Tbody([
                    html.Tr([html.Td("Tendencia ofensiva", style={**TD, "fontWeight": "700"}), html.Td("Disparos totales, disparos a puerta, goles, pases clave y balones en campo rival", style=TD)]),
                    html.Tr([html.Td("Solidez defensiva",  style={**TD, "fontWeight": "700"}), html.Td("Goles encajados (negativo) y porterias a cero", style=TD)]),
                    html.Tr([html.Td("Presion alta",       style={**TD, "fontWeight": "700"}), html.Td("Recuperaciones, entradas ganadas, interceptaciones y faltas cometidas (como indicador de presion agresiva)", style=TD)]),
                    html.Tr([html.Td("Intensidad defensiva", style={**TD, "fontWeight": "700"}), html.Td("Entradas, interceptaciones, duelos totales, faltas cometidas y duelos aereos ganados", style=TD)]),
                    html.Tr([html.Td("Verticalidad",       style={**TD, "fontWeight": "700"}), html.Td("Pases largos completados, balones en campo contrario y regates exitosos", style=TD)]),
                ]),
            ], style={"width": "100%", "borderCollapse": "collapse", "marginTop": "6px", "marginBottom": "8px"}),
            html.P("Cada caracteristica se puntua de 0 a 100 respecto al resto de equipos de la misma liga esa temporada. "
                   "Menos de 40 = bajo, 40-66 = medio, 66 o mas = alto.",
                   style={"fontSize": "11px", "color": "#6B7280", "marginTop": "4px"}),
        ], style=CARD),
        html.Div([
            html.P("Paso 2 -- Fit Rayo (score /10). Mezcla cuatro sub-scores:", style={"fontSize": "12px", "color": "#374151"}),
            html.Ul([
                html.Li(f"Estilo -- cercania de sus ejes al ADN objetivo del club (peso restante).", style={"fontSize": "12px"}),
                html.Li(f"Experiencia en LaLiga -- {cw['laliga_experience']:.0%} (4 o mas temporadas = maximo).", style={"fontSize": "12px"}),
                html.Li(f"Encaje de presupuesto -- {cw['budget_fit']:.0%} (salario vs referencia del club).", style={"fontSize": "12px"}),
                html.Li(f"Compatibilidad con la plantilla -- {cw['squad_compatibility']:.0%} (penaliza si exige perfiles que faltan).", style={"fontSize": "12px"}),
            ]),
            html.P("Si solo hay 1 temporada de datos, el score se penaliza un 10%.", style={"fontSize": "11px", "color": "#6B7280"}),
            html.P("ADN objetivo del club (valor ideal de cada eje y su peso en el Fit Rayo):",
                   style={"fontSize": "12px", "fontWeight": "600", "color": "#1A1A2E", "margin": "8px 0 6px"}),
            _dna_table(),
        ], style=CARD),
        html.Div([
            html.P("Pros, contras y riesgos (deportivo, economico, clausula, adaptacion a LaLiga, "
                   "incompatibilidad con la plantilla) se generan por reglas a partir de esos ejes y del "
                   "contexto. Por ejemplo: solidez defensiva alta genera un pro; sin experiencia en LaLiga "
                   "genera un contra y riesgo de adaptacion alto; salario por encima de la referencia genera riesgo economico.",
                   style={"fontSize": "12px", "color": "#374151"}),
        ], style=CARD),

        # 5 DECISIONES
        _section_chip("ti-checklist", "5 - METODOLOGIA -- DECISIONES", "#E30613"),
        html.Div([
            html.Div([
                html.Div("5", style={"background":"linear-gradient(135deg,#E30613,#C4000F)",
                    "color":"#fff","borderRadius":"50%","width":"28px","height":"28px",
                    "display":"flex","alignItems":"center","justifyContent":"center",
                    "fontWeight":"900","fontSize":"14px","marginRight":"10px","flexShrink":"0"}),
                html.Span("Decisiones -- Fichajes, Renovaciones, Salidas", style={"fontSize":"18px","fontWeight":"800","color":"#1A1A2E"}),
            ], style={"display":"flex","alignItems":"center","marginBottom":"12px"}),
            html.P("Recomendacion de fichaje -- score 0-100 (4 factores):",
                   style={"fontSize":"12px","color":"#374151","fontWeight":"600"}),
            html.Table([
                html.Thead(html.Tr([html.Th("Factor", style=TH), html.Th("Peso", style=TH), html.Th("Umbral", style=TH)])),
                html.Tbody([
                    html.Tr([html.Td("Fit Rayo", style=TD), html.Td("50 %", style={**TD,"fontWeight":"700","color":"#166534"}), html.Td("70 o mas fichar, 50-69 estudiar, menos de 50 descartar", style=TD)]),
                    html.Tr([html.Td("Situacion contractual", style=TD), html.Td("20 %", style={**TD,"fontWeight":"700","color":"#166534"}), html.Td("Libre = max, 1 ano = alto, clausula mayor de 2xMV = penaliza", style=TD)]),
                    html.Tr([html.Td("Viabilidad economica", style=TD), html.Td("20 %", style={**TD,"fontWeight":"700","color":"#166534"}), html.Td("MV menor de 50% presupuesto = verde, MV mayor de 100% = rojo", style=TD)]),
                    html.Tr([html.Td("Afinidad entrenador", style=TD), html.Td("10 %", style={**TD,"fontWeight":"700","color":"#166534"}), html.Td("Distancia entre percentiles del jugador y el estilo demandado", style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse","marginBottom":"12px"}),
            html.P("Recomendacion de renovacion -- 3 niveles:",
                   style={"fontSize":"12px","color":"#374151","fontWeight":"600","marginTop":"6px"}),
            html.Table([
                html.Thead(html.Tr([html.Th("Nivel", style=TH), html.Th("Criterios", style=TH)])),
                html.Tbody([
                    html.Tr([html.Td("Renovar (urgente)", style={**TD,"color":"#166534","fontWeight":"700"}), html.Td("Contrato de 1 ano o menos, titular indiscutible (mas de 1500 min) y Fit Rayo 65 o mas", style=TD)]),
                    html.Tr([html.Td("Evaluar", style={**TD,"color":"#92400E","fontWeight":"700"}), html.Td("Contrato de 2 anos o menos o rendimiento en zona media (900-1499 min)", style=TD)]),
                    html.Tr([html.Td("No renovar / salida", style={**TD,"color":"#991B1B","fontWeight":"700"}), html.Td("Menos de 900 min, Fit menor de 50 o salario anual mayor de 2x valor de mercado estimado", style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse","marginBottom":"12px"}),
            html.P("Candidatos a salida: jugadores con Fit menor de 40, cedidos con rendimiento bajo, "
                   "o cuyo coste salarial anual supera 2 veces su valor de mercado estimado.",
                   style={"fontSize":"11px","color":"#6B7280"}),
            html.P("Estimacion salarial: para jugadores sin dato confirmado se usa "
                   "salary_estimates.yaml con referencias por liga, club, posicion y edad. "
                   "Los valores confirmados de SalaryLeaks/Capology tienen prioridad.",
                   style={"fontSize":"12px","color":"#374151","marginTop":"8px"}),
        ], style=CARD),

        # 6 FINANZAS
        _section_chip("ti-coin", "6 - METODOLOGIA -- FINANZAS", "#E30613"),
        html.Div([
            html.Div([
                html.Div("6", style={"background":"linear-gradient(135deg,#E30613,#C4000F)",
                    "color":"#fff","borderRadius":"50%","width":"28px","height":"28px",
                    "display":"flex","alignItems":"center","justifyContent":"center",
                    "fontWeight":"900","fontSize":"14px","marginRight":"10px","flexShrink":"0"}),
                html.Span("Finanzas", style={"fontSize":"18px","fontWeight":"800","color":"#1A1A2E"}),
            ], style={"display":"flex","alignItems":"center","marginBottom":"12px"}),
            html.P("Masa salarial base: suma de salary_annual de todos los jugadores de la plantilla.",
                   style={"fontSize":"12px","color":"#374151"}),
            html.P("Limite salarial LaLiga (FFP): dato publicado por LaLiga para la temporada actual. "
                   "Verde menor de 75%, Ambar 75-90%, Rojo mayor de 90%.",
                   style={"fontSize":"12px","color":"#374151","marginTop":"6px"}),
            html.P("Presupuesto: ingresos estimados (TV LaLiga, UEFA, matchday, comercial) "
                   "menos gastos (masa salarial bruta, amortizaciones de traspasos y costes operativos).",
                   style={"fontSize":"12px","color":"#374151","marginTop":"6px"}),
            html.P("Score de riesgo de clausula (0-100 por jugador):",
                   style={"fontSize":"12px","color":"#374151","fontWeight":"600","marginTop":"8px"}),
            html.Table([
                html.Thead(html.Tr([html.Th("Factor", style=TH), html.Th("Peso", style=TH), html.Th("Detalle", style=TH)])),
                html.Tbody([
                    html.Tr([html.Td("Meses restantes de contrato", style=TD), html.Td("30 %", style={**TD,"fontWeight":"700"}), html.Td("6m o menos = 30 pts, 12m o menos = 20 pts, 24m o menos = 10 pts, mas de 24m = 0 pts", style=TD)]),
                    html.Tr([html.Td("Ratio clausula / valor TM", style=TD), html.Td("30 %", style={**TD,"fontWeight":"700"}), html.Td("menor de 1x = 30 pts, 1-2x = 15 pts, mayor de 3x = 0 pts", style=TD)]),

                    html.Tr([html.Td("Edad (pico de demanda 24-28)", style=TD), html.Td("20 %", style={**TD,"fontWeight":"700"}), html.Td("24-28 = 20 pts, 22-23 = 12 pts, menor de 22 o mayor de 31 = 0 pts", style=TD)]),
                    html.Tr([html.Td("Interes real confirmado", style=TD), html.Td("20 %", style={**TD,"fontWeight":"700"}), html.Td("Confirmado = 20 pts, Sondeado = 10 pts, Sin noticias = 0 pts", style=TD)]),
                ]),
            ], style={"width":"100%","borderCollapse":"collapse","marginBottom":"8px"}),
            html.P("Niveles: 70 o mas MUY ALTO, 50-69 ALTO, 30-49 MEDIO, menos de 30 BAJO.",
                   style={"fontSize":"11px","color":"#6B7280"}),
            html.P("Simulador de fichajes: el score de viabilidad combina el impacto en la masa salarial, "
                   "el retorno esperado de valor de mercado a 3 anos y la liberacion de salario si hay una salida asociada.",
                   style={"fontSize":"12px","color":"#374151","marginTop":"8px"}),
        ], style=CARD),
    ])
