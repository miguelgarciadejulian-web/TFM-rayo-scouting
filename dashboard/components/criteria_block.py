# -*- coding: utf-8 -*-
"""
criteria_block.py
=================
Bloque colapsable "¿Cómo se calcula esto?" para insertar inline en cualquier
página. Usa dbc.Accordion (un solo item, cerrado por defecto).

Uso::

    from dashboard.components.criteria_block import criteria_accordion
    # En el layout:
    criteria_accordion("scouting")
    criteria_accordion("plantilla")
    criteria_accordion("entrenadores")
    criteria_accordion("decisiones")
    criteria_accordion("finanzas")
    criteria_accordion("comparador")
    criteria_accordion("jugador")
"""
from __future__ import annotations
import sys
from pathlib import Path

from dash import html
import dash_bootstrap_components as dbc

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# ---------------------------------------------------------------------------
# Estilos internos
# ---------------------------------------------------------------------------
_TH = {
    "fontSize": "10px", "fontWeight": "700", "color": "#9CA3AF",
    "textTransform": "uppercase", "padding": "4px 10px", "textAlign": "left",
    "borderBottom": "2px solid #E30613",
}
_TD = {
    "fontSize": "11px", "padding": "4px 10px", "color": "#374151",
    "borderBottom": "1px solid #F3F4F6",
}
_TABLE_STYLE = {"width": "100%", "borderCollapse": "collapse"}
_CARD = {
    "background": "#F9FAFB", "border": "1px solid #E5E7EB",
    "borderRadius": "8px", "padding": "12px 16px", "marginBottom": "10px",
}
_H = {"fontSize": "12px", "fontWeight": "700", "color": "#1A1A2E", "margin": "0 0 6px"}
_P = {"fontSize": "11px", "color": "#374151", "margin": "0 0 6px", "lineHeight": "1.5"}


def _p(text): return html.P(text, style=_P)
def _h(text): return html.P(text, style=_H)
def _card(*children): return html.Div(children, style=_CARD)


def _simple_table(headers, rows):
    head = html.Tr([html.Th(h, style=_TH) for h in headers])
    body = [html.Tr([html.Td(c, style=_TD) for c in row]) for row in rows]
    return html.Table([html.Thead(head), html.Tbody(body)], style=_TABLE_STYLE)


# ---------------------------------------------------------------------------
# Bloques de contenido por sección
# ---------------------------------------------------------------------------

def _block_scouting():
    return [
        _h("Puntuación de rendimiento por rol (score 0-100)"),
        _card(
            _p("Cada métrica se convierte en percentil 0-100 dentro del mismo grupo posicional "
               "y liga. Solo se incluyen jugadores con >= 450 minutos."),
            _p("El rol principal es la combinación ponderada de métricas con mayor puntuación total. "
               "Roles secundarios = aquellos a menos de 12 puntos del principal."),
            _simple_table(
                ["Umbral minutos", "Confianza del perfil"],
                [(">=1800 min", "Alta"), (">=900 min", "Media"),
                 (">=450 min", "Baja"), ("<450 min", "Insuficiente — no se muestra")],
            ),
        ),
        _h("Fit Rayo (0-100) — pesos reales del modelo"),
        _card(
            _simple_table(
                ["Componente", "Peso", "Qué mide"],
                [
                    ("Rendimiento en rol",  "35%", "Percentil del jugador en su grupo posicional"),
                    ("Encaje económico",    "25%", "Valor de mercado vs presupuesto del club"),
                    ("ADN táctico",         "20%", "Similitud con el estilo objetivo del Rayo"),
                    ("Disponibilidad",      "20%", "Duración del contrato + integración en plantilla"),
                ],
            ),
        ),
        _h("Datos económicos"),
        _card(
            _p("Valor de mercado y contrato provienen de Transfermarkt (actualización manual "
               "o vía ETL). Los datos pueden editarse en la ficha de cada jugador."),
        ),
        _h("Buscador con autocompletado y fuzzy fallback"),
        _card(
            _p("El dropdown muestra hasta 15 sugerencias en tiempo real al escribir. "
               "Si no hay coincidencia directa aplica similitud de texto (umbral 0.55). "
               "Útil para nombres con tildes o abreviaturas."),
        ),
    ]


def _block_plantilla():
    return [
        _h("Fuente de datos"),
        _card(
            _p("La plantilla se carga desde config/club_profile.yaml. "
               "Los campos clave son: name, position, age, contract_end, market_value, loan_from."),
            _p("Un jugador aparece como 'cedido' si tiene el campo loan_from relleno."),
        ),
        _h("Valor de mercado agregado"),
        _card(
            _p("El valor total se suma directamente de los market_value del YAML. "
               "Se muestra en millones de euros (M€)."),
        ),
        _h("Contratos urgentes"),
        _card(
            _p("Se marca como 'urgente' (rojo) un contrato que vence antes del 30-jun del año en curso. "
               "'Próximo' (amarillo) si vence en menos de 12 meses."),
        ),
        _h("Contratos editables"),
        _card(
            _p("Despliega el panel 'Editar contratos y valores' para modificar fechas de contrato "
               "y valores de mercado. Los cambios se guardan en club_profile.yaml."),
        ),
    ]


def _block_entrenadores():
    return [
        _h("Ejes de estilo (0-100)"),
        _card(
            _p("Los 8 ejes (Ofensivo, Defensivo, Presión, Posesión, Verticalidad, Intensidad, "
               "Transiciones, Flexibilidad) se calculan agregando métricas de equipo-temporada "
               "de todos los clubes que ha dirigido el técnico, percentilando dentro de su liga."),
            _simple_table(
                ["Eje", "Interpretación"],
                [
                    ("< 40", "Bajo — el técnico no prioriza este aspecto"),
                    ("40-66", "Medio — uso moderado"),
                    (">=66", "Alto — característica distintiva del técnico"),
                ],
            ),
        ),
        _h("Score de Fit Rayo /10"),
        _card(
            _p("Combina 4 sub-scores ponderados:"),
            _simple_table(
                ["Sub-score", "Peso", "Descripción"],
                [
                    ("Estilo",               "~55%", "Cercanía de sus ejes al ADN objetivo del Rayo"),
                    ("Exp. LaLiga",          "15%",   "4+ temporadas en LaLiga = máximo"),
                    ("Encaje presupuesto",   "15%",   "Salario estimado vs referencia del club"),
                    ("Compatib. plantilla",  "15%",   "Penaliza si exige perfiles que faltan"),
                ],
            ),
            _p("Si solo hay 1 temporada de datos, el score se penaliza un 10%."),
        ),
        _h("ADN objetivo del Rayo"),
        _card(
            _p("Definido en config/rayo_dna.yaml. "
               "El radar del panel de detalle superpone el perfil del técnico (rojo) "
               "con el ADN objetivo (línea punteada oscura)."),
            _p("Usa el botón 'Calcular desde datos reales' para sugerir valores de ADN "
               "basados en estadísticas reales del Rayo de la última temporada disponible."),
        ),
    ]


def _block_decisiones():
    return [
        _h("Pestaña Fichajes — Fit Rayo"),
        _card(
            _p("El 'Fit Rayo' usa los mismos 4 componentes ponderados que en la ficha individual "
               "(35% rendimiento · 25% económico · 20% ADN táctico · 20% disponibilidad). "
               "Los candidatos se ordenan por ese score dentro de cada rol."),
        ),
        _h("Pestaña Renovaciones — Score de renovación (0-100)"),
        _card(
            _p("Fórmula aplicada a cada jugador con contrato activo:"),
            _simple_table(
                ["Componente", "Peso", "Descripción"],
                [
                    ("Rendimiento",   "40%", "Score de rol calculado desde el histórico completo"),
                    ("Edad",          "20%", "Curva de rendimiento esperado por posición y edad"),
                    ("Económico",     "20%", "Valor de mercado relativo a la media de plantilla"),
                    ("Contractual",   "20%", "Meses restantes + clausula vs valor de mercado"),
                ],
            ),
            _simple_table(
                ["Score", "Recomendación"],
                [
                    (">=70", "Renovar"),
                    ("50-69", "Negociar"),
                    ("35-49", "Valorar salida"),
                    ("<35", "No renovar"),
                ],
            ),
        ),
        _h("Estimación de salario"),
        _card(
            _p("El salario anual estimado se calcula como ~10% del valor de mercado (Transfermarkt). "
               "Es una referencia orientativa basada en ratios habituales del mercado de LaLiga."),
        ),
        _h("Pestaña Entrenadores"),
        _card(
            _p("Muestra el top-3 de entrenadores por score de Fit Rayo (0-10). "
               "El criterio es idéntico al de la página de Entrenadores."),
        ),
    ]


def _block_finanzas():
    return [
        _h("Fuente de datos financieros"),
        _card(
            _p("Los datos base (salary_mass_target, transfer_budget_net_eur, límite LaLiga) "
               "se leen de config/club_profile.yaml y config/finances.yaml. "
               "Los ajustes del usuario se guardan en data/processed/finances_custom.json."),
        ),
        _h("Riesgo de cláusula (score 0-100)"),
        _card(
            _p("5 factores ponderados por jugador:"),
            _simple_table(
                ["Factor", "Peso aprox.", "Descripción"],
                [
                    ("Contrato restante", "25 pts",  "1 año = 25 · 2 años = 15 · 3-4 años = 8"),
                    ("Edad del jugador",  "25 pts",  "22-26 años (peak) = máximo riesgo"),
                    ("Ratio clausula/TM", "20 pts",  "< 1.5x = 20 pts · > 4x = 2 pts"),
                    ("Interés real",      "30 pts",  "Confirmado = 30 · Sondeado = 18"),
                    ("Posición de valor", "5 pts",   "Lateral o atacante con valor > 8M"),
                ],
            ),
            _simple_table(
                ["Score", "Nivel"],
                [("<25", "BAJO"), ("25-44", "MEDIO"), ("45-64", "ALTO"), (">=65", "MUY ALTO")],
            ),
        ),
        _h("Simulador de mercado"),
        _card(
            _p("Calcula el impacto de una operación sobre el límite de coste LaLiga "
               "(= masa salarial + amortizaciones) y sobre la caja disponible."),
            _p("El coste amortizable se reparte linealmente en los años de contrato pactados. "
               "El presupuesto de caja se obtiene de finances_eur.transfer_budget_net_eur."),
        ),
        _h("Salarios editables"),
        _card(
            _p("En la pestaña Salarios puedes editar el salario de cualquier jugador (columna 'Editar'). "
               "El impacto se muestra en tiempo real en la barra de uso del límite LaLiga. "
               "Los cambios son solo para simulación, no modifican el YAML."),
        ),
    ]


def _block_comparador():
    return [
        _h("Radar de comparación (percentiles)"),
        _card(
            _p("El radar superpone hasta 6 jugadores en los mismos ejes posicionales. "
               "Los valores son percentiles 0-100 dentro del mismo grupo posicional y liga. "
               "Para comparaciones cross-liga, el percentil es relativo a la liga de cada jugador."),
        ),
        _h("Fit Rayo en el comparador — mismos pesos que en ficha individual"),
        _card(
            _simple_table(
                ["Componente", "Peso"],
                [
                    ("Rendimiento en rol",  "35%"),
                    ("Encaje económico",    "25%"),
                    ("ADN táctico",         "20%"),
                    ("Disponibilidad",      "20%"),
                ],
            ),
            _p("Los jugadores del Rayo reciben +10 puntos en disponibilidad por integración "
               "ya consolidada, con un máximo de 85 puntos en ese componente."),
        ),
        _h("Indicadores fortaleza / debilidad"),
        _card(
            _simple_table(
                ["Icono", "Umbral", "Significado"],
                [
                    ("▲ verde",  ">=70",  "Fortaleza clara en ese componente"),
                    ("— neutro", "36-69", "Nivel competitivo estándar"),
                    ("▼ rojo",   "<=35",  "Debilidad relativa vs. su grupo posicional"),
                ],
            ),
        ),
    ]


def _block_jugador():
    return [
        _h("Perfil de rendimiento (percentiles)"),
        _card(
            _p("Los percentiles se calculan sobre TODO el histórico del jugador "
               "(no una sola temporada). Se compara contra jugadores del mismo grupo posicional y liga. "
               "Confianza: >=1800 min = alta · >=900 = media · >=450 = baja · <450 = insuficiente."),
        ),
        _h("Fit Rayo (0-100) — pesos reales del modelo"),
        _card(
            _simple_table(
                ["Componente", "Peso", "Cómo se calcula"],
                [
                    ("Rendimiento",   "35%", "Percentil del jugador en su rol principal"),
                    ("Económico",     "25%", "Valor de mercado vs presupuesto de fichajes del club"),
                    ("ADN táctico",   "20%", "Similitud métricas del jugador con estilo objetivo Rayo"),
                    ("Disponibilidad","20%", "Meses de contrato restantes (+10 bonus si ya es del Rayo, max 85)"),
                ],
            ),
        ),
        _h("Riesgo de cláusula"),
        _card(
            _p("Se activa cuando hay cláusula registrada en 'Datos de mercado'. "
               "Pondera 5 factores: contrato restante · edad del jugador · "
               "ratio clausula/valor TM · interés real de clubes · posición de alto valor."),
            _simple_table(
                ["Nivel", "Score", "Interpretación"],
                [
                    ("Bajo",    "<25",   "Clausula poco atractiva para rivales"),
                    ("Medio",   "25-44", "Riesgo moderado; requiere planificación"),
                    ("Alto",    "45-64", "Riesgo real de que se active"),
                    ("Crítico", ">=65",  "Un rival con recursos podría activarla"),
                ],
            ),
        ),
    ]


# ---------------------------------------------------------------------------
# Mapa sección → función
# ---------------------------------------------------------------------------
_BLOCKS = {
    "scouting":     _block_scouting,
    "plantilla":    _block_plantilla,
    "entrenadores": _block_entrenadores,
    "decisiones":   _block_decisiones,
    "finanzas":     _block_finanzas,
    "comparador":   _block_comparador,
    "jugador":      _block_jugador,
}


def criteria_accordion(section: str) -> dbc.Accordion:
    """
    Devuelve un dbc.Accordion colapsado con los criterios de la sección dada.

    Parámetros
    ----------
    section : str
        Una de: 'scouting', 'plantilla', 'entrenadores', 'decisiones',
                'finanzas', 'comparador', 'jugador'.
    """
    block_fn = _BLOCKS.get(section)
    content = block_fn() if block_fn else [
        _p("Sección no reconocida. Consulta la página de Criterios para la metodología completa."),
    ]

    return dbc.Accordion([
        dbc.AccordionItem(
            html.Div(content),
            title=[
                html.I(className="ti ti-info-circle",
                       style={"color": "#E30613", "marginRight": "8px", "fontSize": "14px"}),
                html.Span("¿Cómo se calcula esto?",
                           style={"fontSize": "12px", "fontWeight": "600", "color": "#374151"}),
            ],
        ),
    ],
        start_collapsed=True,
        style={"marginTop": "24px"},
    )
