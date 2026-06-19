# -*- coding: utf-8 -*-
"""
comparador.py
=============
Página Dash — Comparador de Fichajes.
Ruta: /comparador
"""
from __future__ import annotations

from pathlib import Path

import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from dashboard.components.chart_theme import RAYO_RED, RAYO_DARK, GRAPH_CONFIG_SIMPLE
from dash import Input, Output, State, callback, dcc, html
from dash.exceptions import PreventUpdate
from src.utils.leagues import league_name
from dashboard.components.criteria_block import criteria_accordion  # noqa: E402

dash.register_page(__name__, path="/comparador", name="Comparador")

# ---------------------------------------------------------------------------
# Rutas datos
# ---------------------------------------------------------------------------

_BASE = Path(__file__).parents[2]
_PROC = _BASE / "data" / "processed"
_CLUB_YAML = _BASE / "config" / "club_profile.yaml"

# ---------------------------------------------------------------------------
# Cache de datos
# ---------------------------------------------------------------------------

_CACHE: dict = {}


def _master() -> pd.DataFrame:
    if "master" not in _CACHE:
        _CACHE["master"] = pd.read_parquet(_PROC / "master_players.parquet")
    return _CACHE["master"]


def _squad_info() -> list[dict]:
    if "squad" not in _CACHE:
        import yaml
        with open(_CLUB_YAML, encoding="utf-8") as f:
            club = yaml.safe_load(f)
        players = []
        for section in club.get("squad_2025_26", {}).values():
            if isinstance(section, list):
                players.extend(section)
        _CACHE["squad"] = players
    return _CACHE["squad"]


def _scorer():
    if "scorer" not in _CACHE:
        from src.scouting.comparator import load_scorer
        _CACHE["scorer"] = load_scorer(_PROC, _squad_info())
    return _CACHE["scorer"]


def _player_options() -> list[dict]:
    """Opciones del dropdown de búsqueda (precargadas, deduplicadas por nombre)."""
    if "opts" not in _CACHE:
        df = _master()
        ORDER = {"2026": 7, "2025-2026": 6, "2025/2026": 6, "2025": 5,
                 "2024-2025": 4, "2024": 4, "2023-2024": 3}
        df = df.copy()
        df["_o"] = df["season"].map(ORDER).fillna(0)
        best = df.loc[df.groupby("name")["_o"].idxmax()].sort_values("name")
        opts = []
        for _, row in best.iterrows():
            label = f"{row['name']}  ·  {row.get('team','?')}  ({league_name(row.get('league',''))})"
            opts.append({"label": label, "value": row["name"]})
        _CACHE["opts"] = opts
    return _CACHE["opts"]


# ---------------------------------------------------------------------------
# Colores FitRayo
# ---------------------------------------------------------------------------

def _fit_color(score: float) -> str:
    if score >= 70:
        return "#166534"
    if score >= 50:
        return "#1D4ED8"
    if score >= 30:
        return "#92400E"
    return "#991B1B"


def _fit_badge(score: float) -> html.Span:
    return html.Span(
        f"{score:.0f}",
        style={
            "background": _fit_color(score),
            "color": "#fff",
            "borderRadius": "12px",
            "padding": "2px 10px",
            "fontWeight": "bold",
            "fontSize": "1.1rem",
        },
    )


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

def layout():
    return dbc.Container(
        fluid=True,
        children=[
            # Cabecera
            dbc.Row(
                dbc.Col(
                    html.Div(
                        [
                            html.I(className="ti ti-git-compare me-2",
                                   style={"fontSize": "1.5rem", "color": "#E30613"}),
                            html.H4("Comparador de Fichajes",
                                    className="d-inline mb-0 fw-bold"),
                        ],
                        className="d-flex align-items-center mb-3 mt-3",
                    )
                )
            ),

            # Selector de jugadores
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.Label("Selecciona jugadores (2-6)",
                                       className="fw-semibold mb-1"),
                            dcc.Dropdown(
                                id="comp-player-select",
                                options=_player_options(),
                                multi=True,
                                placeholder="Busca por nombre, equipo...",
                                style={"fontSize": "0.88rem"},
                                className="mb-2",
                            ),
                        ],
                        md=9,
                    ),
                    dbc.Col(
                        [
                            html.Label("Añadir plantilla actual",
                                       className="fw-semibold mb-1"),
                            dcc.Dropdown(
                                id="comp-rayo-select",
                                options=[
                                    {"label": _rayo_label(p), "value": p["name"]}
                                    for p in _squad_info()
                                ],
                                multi=True,
                                placeholder="Jugadores Rayo...",
                                style={"fontSize": "0.88rem"},
                            ),
                        ],
                        md=3,
                    ),
                ],
                className="mb-3",
            ),

            dbc.Row(
                dbc.Col(
                    dbc.Button(
                        [html.I(className="ti ti-chart-radar me-2"), "Comparar"],
                        id="comp-run-btn",
                        color="danger",
                        size="sm",
                        className="me-2",
                    ),
                    width="auto",
                )
            ),

            html.Hr(),

            # Resultados
            html.Div(id="comp-results"),
            criteria_accordion("comparador"),
        ],
    )


def _rayo_label(p: dict) -> str:
    name = p.get("name", "")
    tags = []
    if p.get("loan_from"):
        tags.append(f"CEDIDO · {p['loan_from']}")
    if p.get("homegrown"):
        tags.append("Cantera")
    if tags:
        return f"{name}  [{', '.join(tags)}]"
    return name


# ---------------------------------------------------------------------------
# Callback principal
# ---------------------------------------------------------------------------

@callback(
    Output("comp-results", "children"),
    Input("comp-run-btn", "n_clicks"),
    State("comp-player-select", "value"),
    State("comp-rayo-select", "value"),
    prevent_initial_call=True,
)
def _run_comparison(n, ext_players, rayo_players):
    if not n:
        raise PreventUpdate

    names = list(ext_players or []) + list(rayo_players or [])
    names = list(dict.fromkeys(names))  # dedup preservando orden

    if len(names) < 2:
        return dbc.Alert("Selecciona al menos 2 jugadores.", color="warning")
    if len(names) > 6:
        return dbc.Alert("Máximo 6 jugadores.", color="warning")

    scorer = _scorer()
    results = scorer.compare(names)

    if not results:
        return dbc.Alert("No se encontraron datos para los jugadores seleccionados.",
                         color="danger")

    return html.Div(
        [
            _radar_section(results),
            html.Hr(),
            _cards_section(results),
            html.Hr(),
            _table_section(results),
            html.Hr(),
            _export_section(results),
        ]
    )


# ---------------------------------------------------------------------------
# Secciones de resultado
# ---------------------------------------------------------------------------

RADAR_LABELS = {
    "goal_contrib_p90":    "G+A / 90",
    "key_passes_p90":      "Creación",
    "dribbles_p90":        "Regates",
    "ball_recoveries_p90": "Recuperación",
    "tackles_won_p90":     "Duelos",
    "pass_accuracy":       "Precisión pase",
}

PLAYER_COLORS = [
    "#E30613", "#1D4ED8", "#166534", "#92400E", "#6B21A8", "#0E7490",
]


def _hex_to_rgba(hex_color: str, alpha: float = 0.15) -> str:
    """Convierte '#RRGGBB' a 'rgba(r,g,b,alpha)'."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _radar_section(results) -> html.Div:
    keys   = list(RADAR_LABELS.keys())
    labels = [RADAR_LABELS[k] for k in keys] + [RADAR_LABELS[keys[0]]]

    # Valores reales p90 para mostrar en el hover junto al percentil
    _RAW_LABELS = {
        "goal_contrib_p90":    ("G+A/90",   lambda r: f"{r.goal_contrib_p90:.2f}"),
        "key_passes_p90":      ("KC/90",    lambda r: f"{r.key_passes_p90:.2f}"),
        "dribbles_p90":        ("Reg/90",   lambda r: f"{r.dribbles_p90:.2f}"),
        "ball_recoveries_p90": ("Rec/90",   lambda r: f"{r.ball_recoveries_p90:.2f}"),
        "tackles_won_p90":     ("Duel/90",  lambda r: f"{r.tackles_won_p90:.2f}"),
        "pass_accuracy":       ("Prec%",    lambda r: f"{r.pass_accuracy:.1f}%"),
    }

    traces = []
    for i, r in enumerate(results):
        vals = [r.radar.get(k, 0) for k in keys]
        vals += [vals[0]]
        color = PLAYER_COLORS[i % len(PLAYER_COLORS)]
        # Texto hover: "Etiqueta · percentil · valor real"
        htexts = []
        for k, label in zip(keys, [RADAR_LABELS[k] for k in keys]):
            pct = r.radar.get(k, 0)
            raw_lbl, raw_fn = _RAW_LABELS[k]
            htexts.append(f"<b>{label}</b><br>Percentil: {pct:.0f}<br>{raw_lbl}: {raw_fn(r)}")
        htexts += [htexts[0]]
        traces.append(
            go.Scatterpolar(
                r=vals,
                theta=labels,
                fill="toself",
                name=r.name,
                text=htexts,
                hovertemplate="%{text}<extra></extra>",
                line=dict(color=color, width=2.5),
                fillcolor=_hex_to_rgba(color, 0.15),
                opacity=0.9,
            )
        )

    fig = go.Figure(
        data=traces,
        layout=go.Layout(
            polar=dict(
                radialaxis=dict(
                    visible=True, range=[0, 100],
                    tickfont=dict(size=9, color="#9CA3AF"),
                    gridcolor="#E5E7EB", linecolor="#E5E7EB",
                    tickvals=[25, 50, 75, 100],
                ),
                angularaxis=dict(
                    tickfont=dict(size=11, family="Inter", color=RAYO_DARK),
                    linecolor="#D1D5DB",
                ),
                bgcolor="rgba(249,250,251,0.4)",
            ),
            showlegend=True,
            legend=dict(
                orientation="h", y=-0.12,
                font=dict(size=11, family="Inter"),
                bgcolor="rgba(255,255,255,0.9)",
                bordercolor="#E5E7EB", borderwidth=1,
            ),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=30, r=30, t=30, b=70),
            height=420,
            hoverlabel=dict(bgcolor=RAYO_DARK, font=dict(size=11, color="white")),
        ),
    )

    return html.Div(
        [
            html.H6("Radar de Rendimiento", className="fw-bold mb-2"),
            html.P(
                "Percentil vs. jugadores de la misma posición (0 = peor, 100 = mejor de su grupo).",
                style={"fontSize": "11px", "color": "#6B7280", "marginBottom": "8px"},
            ),
            dcc.Graph(figure=fig, config={"displayModeBar": False}),
        ]
    )


def _cards_section(results) -> html.Div:
    cards = []
    for i, r in enumerate(results):
        color = PLAYER_COLORS[i % len(PLAYER_COLORS)]

        # Badges de estado
        badges = []
        if r.at_rayo:
            if r.loan_from:
                badges.append(
                    dbc.Badge(
                        f"CEDIDO · {r.loan_from}",
                        color="warning",
                        text_color="dark",
                        className="me-1 mb-1",
                        pill=True,
                    )
                )
            else:
                badges.append(
                    dbc.Badge("EN PLANTILLA", color="success",
                              className="me-1 mb-1", pill=True)
                )
        if r.homegrown:
            badges.append(
                dbc.Badge("CANTERA", color="info", text_color="dark",
                          className="me-1 mb-1", pill=True)
            )

        # Barra FitRayo
        bar_color = _fit_color(r.fit_score)
        bar = html.Div(
            [
                html.Div("Fit Rayo", style={"fontSize": "0.72rem", "color": "#666"}),
                html.Div(
                    [
                        html.Div(
                            style={
                                "width": f"{r.fit_score}%",
                                "background": bar_color,
                                "height": "8px",
                                "borderRadius": "4px",
                                "transition": "width 0.4s",
                            }
                        )
                    ],
                    style={
                        "background": "#e5e7eb",
                        "borderRadius": "4px",
                        "height": "8px",
                        "margin": "4px 0",
                        "width": "100%",
                    },
                ),
                html.Div(
                    [
                        html.Small(f"{r.fit_score:.0f}/100",
                                   style={"color": bar_color, "fontWeight": "bold"}),
                    ]
                ),
            ],
            className="mb-2",
        )

        sub_scores = html.Div(
            [
                _mini_stat("Rendimiento", r.score_rendimiento),
                _mini_stat("Económico",   r.score_economico),
                _mini_stat("Edad",        r.score_edad),
                _mini_stat("Disponib.",   r.score_disponibilidad),
            ],
            style={"display": "flex", "gap": "6px", "flexWrap": "wrap"},
        )

        cards.append(
            dbc.Col(
                dbc.Card(
                    [
                        dbc.CardHeader(
                            html.Div(
                                [
                                    html.Span(
                                        r.name,
                                        style={"fontWeight": "bold",
                                               "color": color,
                                               "fontSize": "0.95rem"},
                                    ),
                                    html.Br(),
                                    html.Small(
                                        f"{r.position} · {r.age:.0f}a · {r.team}",
                                        style={"color": "#555"},
                                    ),
                                ]
                            )
                        ),
                        dbc.CardBody(
                            [
                                html.Div(badges) if badges else None,
                                bar,
                                sub_scores,
                                html.Hr(style={"margin": "8px 0"}),
                                _stat_row("Minutos",         r.minutes),
                                _stat_row("G+A",             f"{r.goals}G / {r.assists}A"),
                                _stat_row("G+A / 90",        f"{r.goal_contrib_p90:.2f}"),
                                _stat_row("Pases clave/90",  f"{r.key_passes_p90:.2f}"),
                                _stat_row("Regates/90",      f"{r.dribbles_p90:.2f}"),
                                _stat_row("Recuperación/90", f"{r.ball_recoveries_p90:.2f}"),
                                _stat_row("Duelos/90",       f"{r.tackles_won_p90:.2f}"),
                                _stat_row("Precisión pase",  f"{r.pass_accuracy:.1f}%"),
                                html.Hr(style={"margin": "8px 0"}),
                                html.Small(
                                    f"Valor mercado: {_fmt_mv(r.market_value_eur)}",
                                    style={"color": "#555"},
                                ),
                                html.Br(),
                                html.Small(
                                    f"Contrato hasta: {r.contract_until or 'N/D'}",
                                    style={"color": "#555"},
                                ),
                            ]
                        ),
                    ],
                    style={"borderTop": f"3px solid {color}", "height": "100%"},
                ),
                xs=12, md=6, lg=4, className="mb-3",
            )
        )

    return html.Div(
        [
            html.H6("Ficha por Jugador", className="fw-bold mb-3"),
            dbc.Row(cards),
        ]
    )


def _table_section(results) -> html.Div:
    header = dbc.Row(
        [
            dbc.Col(html.Small("Jugador",       className="fw-bold"), md=3),
            dbc.Col(html.Small("Fit",          className="fw-bold text-center"), md=1),
            dbc.Col(html.Small("Min",          className="fw-bold text-center"), md=1),
            dbc.Col(html.Small("G+A",          className="fw-bold text-center"), md=1),
            dbc.Col(html.Small("G+A/90",       className="fw-bold text-center"), md=1),
            dbc.Col(html.Small("KC/90",        className="fw-bold text-center", title="Pases clave / 90"), md=1),
            dbc.Col(html.Small("Rec/90",       className="fw-bold text-center", title="Recuperaciones / 90"), md=1),
            dbc.Col(html.Small("V. Mercado",   className="fw-bold text-center"), md=3),
        ],
        className="px-2 py-1",
        style={"background": "#f3f4f6", "borderRadius": "4px"},
    )

    rows = [header]
    for i, r in enumerate(results):
        color = PLAYER_COLORS[i % len(PLAYER_COLORS)]
        loan_tag = (
            dbc.Badge(f"CEDIDO", color="warning", text_color="dark",
                      pill=True, className="ms-1", style={"fontSize":"0.65rem"})
            if r.loan_from else None
        )
        rows.append(
            dbc.Row(
                [
                    dbc.Col(
                        html.Div([
                            html.Span(r.name, style={"color": color, "fontWeight":"600",
                                                     "fontSize":"0.85rem"}),
                            loan_tag,
                            html.Br(),
                            html.Small(f"{r.position} · {r.age:.0f}a",
                                       style={"color":"#888","fontSize":"0.75rem"}),
                        ]),
                        md=3,
                    ),
                    dbc.Col(_fit_badge(r.fit_score),
                            md=1, className="text-center d-flex align-items-center justify-content-center"),
                    dbc.Col(html.Small(str(r.minutes)),
                            md=1, className="text-center d-flex align-items-center justify-content-center"),
                    dbc.Col(html.Small(f"{r.goals}G+{r.assists}A"),
                            md=1, className="text-center d-flex align-items-center justify-content-center"),
                    dbc.Col(html.Small(f"{r.goal_contrib_p90:.2f}"),
                            md=1, className="text-center d-flex align-items-center justify-content-center"),
                    dbc.Col(html.Small(f"{r.key_passes_p90:.2f}"),
                            md=1, className="text-center d-flex align-items-center justify-content-center"),
                    dbc.Col(html.Small(f"{r.ball_recoveries_p90:.2f}"),
                            md=1, className="text-center d-flex align-items-center justify-content-center"),
                    dbc.Col(html.Small(_fmt_mv(r.market_value_eur)),
                            md=3, className="text-center d-flex align-items-center justify-content-center"),
                ],
                className="px-2 py-2 border-bottom align-items-center",
            )
        )

    return html.Div(
        [
            html.H6("Tabla Comparativa", className="fw-bold mb-3"),
            html.Div(rows),
        ]
    )


def _export_section(results) -> html.Div:
    rows = []
    for r in results:
        rows.append({
            "nombre":         r.name,
            "posicion":       r.position,
            "edad":           r.age,
            "equipo":         r.team,
            "liga":           r.league,
            "temporada":      r.season,
            "minutos":        r.minutes,
            "goles":          r.goals,
            "asistencias":    r.assists,
            "disparos":       r.shots_on_target,
            "duelos_ganados": r.tackles_won,
            "pases":          r.passes_completed,
            "valor_mercado":  r.market_value_eur,
            "contrato_hasta": r.contract_until,
            "fit_rayo":       r.fit_score,
            "fit_rendimiento":r.score_rendimiento,
            "fit_economico":  r.score_economico,
            "fit_edad":       r.score_edad,
            "fit_disponib":   r.score_disponibilidad,
            "cedido_de":      r.loan_from,
            "cantera":        r.homegrown,
        })

    import json
    data_json = json.dumps(rows, ensure_ascii=False, default=str)

    return html.Div(
        [
            html.H6("Exportar", className="fw-bold mb-2"),
            html.Button(
                [html.I(className="ti ti-download me-2"), "Descargar CSV"],
                id="comp-export-btn",
                n_clicks=0,
                className="btn btn-outline-secondary btn-sm",
            ),
            dcc.Store(id="comp-export-data", data=data_json),
            dcc.Download(id="comp-download"),
        ]
    )


# ---------------------------------------------------------------------------
# Callback export
# ---------------------------------------------------------------------------

@callback(
    Output("comp-download", "data"),
    Input("comp-export-btn", "n_clicks"),
    State("comp-export-data", "data"),
    prevent_initial_call=True,
)
def _download(n, data_json):
    if not n or not data_json:
        raise PreventUpdate
    import io
    import json
    rows = json.loads(data_json)
    df   = pd.DataFrame(rows)
    buf  = io.StringIO()
    df.to_csv(buf, index=False, sep=";", encoding="utf-8-sig")
    return dcc.send_string(buf.getvalue(), "comparacion_fichajes.csv")


# ---------------------------------------------------------------------------
# Helpers visuales
# ---------------------------------------------------------------------------


def _narrative_block(narrative: dict) -> html.Div:
    """Sección colapsable con la explicación del Fit Rayo."""
    if not narrative:
        return html.Div()

    ICONS = {
        "rendimiento":   "ti-run",
        "economico":     "ti-coin-euro",
        "edad":          "ti-calendar",
        "disponibilidad":"ti-door-enter",
    }
    LABELS = {
        "rendimiento":   "Rendimiento",
        "economico":     "Encaje económico",
        "edad":          "Perfil de edad",
        "disponibilidad":"Disponibilidad",
    }

    items = []
    for key, text in narrative.items():
        icon  = ICONS.get(key, "ti-info-circle")
        label = LABELS.get(key, key.capitalize())
        items.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.I(className=f"ti {icon}",
                                   style={"marginRight": "5px", "color": "#E30613"}),
                            html.Span(label,
                                      style={"fontWeight": "600", "fontSize": "0.75rem"}),
                        ],
                        style={"marginBottom": "2px"},
                    ),
                    html.P(text, style={"fontSize": "0.73rem", "color": "#555",
                                        "margin": "0 0 6px", "lineHeight": "1.45"}),
                ]
            )
        )

    return html.Details(
        [
            html.Summary(
                "¿Por qué este Fit Rayo?",
                style={"cursor": "pointer", "fontSize": "0.75rem",
                       "color": "#E30613", "fontWeight": "600",
                       "marginBottom": "6px", "marginTop": "4px"},
            ),
            html.Div(items, style={"paddingLeft": "4px"}),
        ]
    )

def _mini_stat(label: str, val: float) -> html.Div:
    color = _fit_color(val)
    if val >= 70:
        bg, border = "#F0FDF4", "#86EFAC"
        icon = "▲"
    elif val <= 35:
        bg, border = "#FFF1F2", "#FECACA"
        icon = "▼"
    else:
        bg, border = "#f9fafb", "#e5e7eb"
        icon = ""
    return html.Div(
        [
            html.Div(label, style={"fontSize": "0.65rem", "color": "#555"}),
            html.Div(
                f"{icon}{val:.0f}",
                style={"fontWeight": "bold", "fontSize": "0.8rem", "color": color},
            ),
        ],
        style={
            "background": bg,
            "border": f"1px solid {border}",
            "borderRadius": "6px",
            "padding": "4px 8px",
            "textAlign": "center",
            "minWidth": "58px",
        },
    )


def _stat_row(label: str, val) -> html.Div:
    return html.Div(
        [
            html.Span(label, style={"color": "#555", "fontSize": "0.78rem"}),
            html.Span(str(val), style={"fontWeight": "600", "fontSize": "0.78rem"}),
        ],
        style={"display": "flex", "justifyContent": "space-between",
               "padding": "1px 0"},
    )


def _fmt_mv(v) -> str:
    if v is None or (isinstance(v, float) and (v != v or v <= 0)):
        return "N/D"
    v = float(v)
    if v >= 1_000_000:
        return f"€{v/1_000_000:.1f}M"
    if v >= 1_000:
        return f"€{v/1_000:.0f}K"
    return f"€{v:.0f}"
