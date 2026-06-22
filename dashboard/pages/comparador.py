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


def _lateral_lookup() -> dict[str, str]:
    """Devuelve {nombre_jugador: lateral_pos} desde el parquet enriquecido."""
    if "lat_dict" not in _CACHE:
        try:
            from src.utils.lateral_position import build_lateral_map as _blm
            enr_path = _PROC / "player_seasons_enriched.parquet"
            lat_df = _blm(enr_path, enr_path)[["name", "lateral_pos"]]
            _CACHE["lat_dict"] = dict(zip(lat_df["name"], lat_df["lateral_pos"]))
        except Exception:
            _CACHE["lat_dict"] = {}
    return _CACHE["lat_dict"]


def _position_filter_options() -> list[dict]:
    """Opciones de filtro de posición dinámicas (position_primary + lateral_pos)."""
    if "pos_filter_opts" not in _CACHE:
        df = _master()
        POS_LABELS = {
            "CB": "CB — Defensa central",
            "CM": "CM — Mediocentro",
            "GK": "GK — Portero",
            "ST": "ST — Delantero",
        }
        positions = sorted(df["position_primary"].dropna().unique())
        opts: list[dict] = [{"label": "Todas las posiciones", "value": "all"}]
        for p in positions:
            opts.append({"label": POS_LABELS.get(p, p), "value": f"pos:{p}"})
            if p == "CB":
                lat = _lateral_lookup()
                lat_vals = sorted(set(v for v in lat.values() if v))
                LAT_LABELS = {"LI": "└ LI — Lateral izquierdo",
                              "LD": "└ LD — Lateral derecho",
                              "DC": "└ DC — Central puro"}
                for lv in lat_vals:
                    opts.append({"label": LAT_LABELS.get(lv, f"└ {lv}"), "value": f"lat:{lv}"})
        _CACHE["pos_filter_opts"] = opts
    return _CACHE["pos_filter_opts"]


def _player_options(pos_filter: str | None = None) -> list[dict]:
    """Opciones del dropdown de búsqueda (precargadas, deduplicadas por nombre)."""
    if "opts_raw_with_pos" not in _CACHE:
        df = _master()
        ORDER = {"2026": 7, "2025-2026": 6, "2025/2026": 6, "2025": 5,
                 "2024-2025": 4, "2024": 4, "2023-2024": 3}
        df = df.copy()
        df["_o"] = df["season"].map(ORDER).fillna(0)
        best = df.loc[df.groupby("name")["_o"].idxmax()].sort_values("name")
        opts = []
        for _, row in best.iterrows():
            label = f"{row['name']}  ·  {row.get('team','?')}  ({league_name(row.get('league',''))})"
            opts.append({"label": label, "value": row["name"],
                         "_pos": str(row.get("position_primary", "") or "")})
        _CACHE["opts_raw_with_pos"] = opts
    opts = _CACHE["opts_raw_with_pos"]
    if not pos_filter or pos_filter == "all":
        return [{"label": o["label"], "value": o["value"]} for o in opts]
    if pos_filter.startswith("pos:"):
        target_pos = pos_filter[4:]
        return [{"label": o["label"], "value": o["value"]}
                for o in opts if o["_pos"] == target_pos]
    if pos_filter.startswith("lat:"):
        target_lat = pos_filter[4:]
        lat = _lateral_lookup()
        return [{"label": o["label"], "value": o["value"]}
                for o in opts if o["_pos"] == "CB" and lat.get(o["value"]) == target_lat]
    return [{"label": o["label"], "value": o["value"]} for o in opts]


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
    _label_style = {"fontSize":"11px","fontWeight":"600","color":"#374151","marginBottom":"4px"}
    return html.Div([

        # ── Hero ──────────────────────────────────────────────────────────────
        html.Div([
            html.Div([
                html.Div([html.I(className="ti ti-git-compare",
                           style={"fontSize":"28px","color":"#fff"})],
                    style={"background":"rgba(255,255,255,.15)","borderRadius":"12px",
                           "padding":"10px","marginRight":"18px","flexShrink":"0"}),
                html.Div([
                    html.Div("ANÁLISIS COMPARATIVO", style={"fontSize":"9px","fontWeight":"700",
                        "color":"rgba(255,255,255,.55)","letterSpacing":".14em","marginBottom":"3px"}),
                    html.H1("Comparador de Fichajes", style={"fontSize":"22px","fontWeight":"900",
                        "color":"#fff","margin":"0 0 2px"}),
                    html.Div("Compara hasta 6 jugadores · Fit Rayo 0–100 calculado automáticamente",
                        style={"fontSize":"10px","color":"rgba(255,255,255,.5)"}),
                ]),
            ], style={"display":"flex","alignItems":"center"}),
        ], style={"background":"linear-gradient(135deg,#5B21B6 0%,#6D28D9 60%,#7C3AED 100%)",
                  "borderRadius":"18px","padding":"20px 26px","marginBottom":"18px",
                  "boxShadow":"0 8px 24px rgba(91,33,182,.25)"}),

        # ── Panel de selección ────────────────────────────────────────────────
        html.Div([
            html.Div([
                html.I(className="ti ti-users",
                       style={"fontSize":"14px","color":"#7C3AED","marginRight":"7px"}),
                html.Span("SELECCIÓN DE JUGADORES", style={"fontSize":"9px","fontWeight":"700",
                    "color":"#7C3AED","letterSpacing":".10em"}),
            ], style={"marginBottom":"14px","display":"flex","alignItems":"center"}),
            dbc.Row([
                dbc.Col([
                    html.Div("Filtrar por posición", style=_label_style),
                    dcc.Dropdown(
                        id="comp-lateral",
                        options=_position_filter_options(),
                        value="all", clearable=False,
                        style={"fontSize":"0.82rem"},
                    ),
                ], md=3),
                dbc.Col([
                    html.Div("Candidatos externos (2–6)", style=_label_style),
                    dcc.Dropdown(
                        id="comp-player-select",
                        options=_player_options(),
                        multi=True,
                        placeholder="Busca por nombre o equipo...",
                        style={"fontSize":"0.88rem"},
                    ),
                ], md=6),
                dbc.Col([
                    html.Div("Jugadores del Rayo", style=_label_style),
                    dcc.Dropdown(
                        id="comp-rayo-select",
                        options=[{"label": _rayo_label(p), "value": p["name"]}
                                  for p in _squad_info()],
                        multi=True,
                        placeholder="Jugadores Rayo...",
                        style={"fontSize":"0.88rem"},
                    ),
                ], md=3),
            ], className="g-3 mb-3"),
            dbc.Button(
                [html.I(className="ti ti-chart-radar", style={"marginRight":"6px"}),
                 "Comparar jugadores"],
                id="comp-run-btn",
                style={"background":"linear-gradient(135deg,#5B21B6,#7C3AED)",
                       "border":"none","borderRadius":"10px","fontWeight":"700",
                       "fontSize":"13px","padding":"9px 20px","color":"#fff",
                       "boxShadow":"0 4px 12px rgba(91,33,182,.3)"},
            ),
        ], style={"background":"#fff","border":"1px solid #E5E7EB","borderRadius":"14px",
                  "padding":"18px 20px","marginBottom":"18px",
                  "boxShadow":"0 2px 8px rgba(0,0,0,.05)"}),

        # ── Resultados ───────────────────────────────────────────────────────
        html.Div(id="comp-results"),
        criteria_accordion("comparador"),
    ])


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
    Output("comp-player-select", "options"),
    Input("comp-lateral", "value"),
)
def _filter_player_options(pos_filter):
    return _player_options(pos_filter=pos_filter)


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

    lat_dict = _lateral_lookup()
    return html.Div(
        [
            _radar_section(results),
            html.Hr(),
            _cards_section(results, lat_dict=lat_dict),
            html.Hr(),
            _table_section(results, lat_dict=lat_dict),
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


def _cards_section(results, lat_dict: dict | None = None) -> html.Div:
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
                                        f"{r.position}"
                                        + (f" ({(lat_dict or {}).get(r.name, '')})" if (lat_dict or {}).get(r.name) else "")
                                        + f" · {r.age:.0f}a · {r.team}",
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


def _table_section(results, lat_dict: dict | None = None) -> html.Div:
    header = dbc.Row(
        [
            dbc.Col(html.Small("Jugador",       className="fw-bold"), md=3),
            dbc.Col(html.Small("Pos.",          className="fw-bold text-center", title="Posición lateral"), md=1),
            dbc.Col(html.Small("Fit",          className="fw-bold text-center"), md=1),
            dbc.Col(html.Small("Min",          className="fw-bold text-center"), md=1),
            dbc.Col(html.Small("G+A",          className="fw-bold text-center"), md=1),
            dbc.Col(html.Small("G+A/90",       className="fw-bold text-center"), md=1),
            dbc.Col(html.Small("KC/90",        className="fw-bold text-center", title="Pases clave / 90"), md=1),
            dbc.Col(html.Small("Rec/90",       className="fw-bold text-center", title="Recuperaciones / 90"), md=1),
            dbc.Col(html.Small("V. Mercado",   className="fw-bold text-center"), md=2),
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
        lat_pos = (lat_dict or {}).get(r.name, "—")
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
                    dbc.Col(html.Small(lat_pos, style={"fontWeight": "600"}),
                            md=1, className="text-center d-flex align-items-center justify-content-center"),
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
                            md=2, className="text-center d-flex align-items-center justify-content-center"),
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
    """PDF export button — stores serialized result names for callback."""
    import json
    names_json = json.dumps([getattr(r, "name", "") for r in results])

    return html.Div([
        html.Div([
            html.I(className="ti ti-file-description",
                   style={"fontSize":"16px","color":"#E30613","marginRight":"8px"}),
            html.Span("Exportar comparativa",
                      style={"fontSize":"13px","fontWeight":"700","color":"#1A1A2E"}),
        ], style={"display":"flex","alignItems":"center","marginBottom":"10px"}),
        dcc.Loading(html.Div([
            html.Button([
                html.I(className="ti ti-file-download",
                       style={"marginRight":"6px"}),
                "Descargar PDF",
            ], id="comp-export-btn", n_clicks=0, style={
                "background":"#1A1A2E","color":"#fff","border":"none",
                "borderRadius":"8px","padding":"9px 18px",
                "fontSize":"13px","fontWeight":"600","cursor":"pointer",
            }),
            dcc.Download(id="comp-download"),
        ]), type="circle", color="#E30613"),
        dcc.Store(id="comp-export-data", data=names_json),
        html.Div(id="comp-export-error", style={"marginTop":"6px"}),
    ], style={"background":"#fff","border":"1px solid #E5E7EB","borderRadius":"12px",
              "padding":"16px 20px"})


# ---------------------------------------------------------------------------
# Callback export — genera PDF comparativo
# ---------------------------------------------------------------------------

@callback(
    Output("comp-download", "data"),
    Output("comp-export-error", "children"),
    Input("comp-export-btn", "n_clicks"),
    State("comp-export-data", "data"),
    prevent_initial_call=True,
)
def _download(n, names_json):
    if not n or not names_json:
        raise PreventUpdate
    import json, sys
    from pathlib import Path as _P
    sys.path.insert(0, str(_P(__file__).resolve().parents[2]))
    try:
        names = json.loads(names_json)
        scorer = _scorer()
        results = scorer.compare(names)
        if not results:
            raise ValueError("No hay datos para los jugadores seleccionados")

        # Build percentile map for each player
        from src.profiling.player_profile import career_aggregate, add_role_percentiles
        from src.utils.config import settings
        enr_path = settings.data_dir / "processed" / "player_seasons_enriched.parquet"
        pct_map: dict = {}
        if enr_path.exists():
            enr_all = pd.read_parquet(enr_path)
            for r in results:
                try:
                    agg = career_aggregate(enr_all, r.name)
                    if agg is not None and not agg.empty:
                        grp = str(getattr(r, "position_group", "") or "MID")
                        pool = enr_all[enr_all["position_group"] == grp].copy()
                        pool_agg = pool.groupby("name").agg({
                            c: "sum" for c in pool.select_dtypes("number").columns
                        }).reset_index()
                        pm: dict = {}
                        for col in pool_agg.select_dtypes("number").columns:
                            if col + "_p90" in enr_all.columns or col.endswith("_p90"):
                                continue
                            vals = pool_agg[col].dropna()
                            player_v = pool_agg.loc[pool_agg["name"] == r.name, col]
                            if len(player_v) > 0 and len(vals) > 5:
                                rank = (vals < float(player_v.iloc[0])).sum() / len(vals) * 100
                                pm[col] = round(rank, 1)
                        # also try _p90 cols from enriched directly
                        p90_cols = [c for c in enr_all.columns if c.endswith("_p90")]
                        latest = enr_all[enr_all["name"] == r.name].sort_values("season",
                                         ascending=False).head(1)
                        if not latest.empty:
                            for col in p90_cols:
                                v = latest.iloc[0].get(col)
                                if v is not None and not pd.isna(v):
                                    pool_col = enr_all.loc[
                                        enr_all["position_group"] == grp, col].dropna()
                                    if len(pool_col) > 5:
                                        pm[col] = round(
                                            (pool_col < float(v)).sum() / len(pool_col) * 100, 1)
                        pct_map[r.name] = pm
                except Exception:
                    pct_map[r.name] = {}

        from src.reports.comparador_dossier import build_comparador_dossier
        fname, data = build_comparador_dossier(results, pct_map=pct_map)
        return dcc.send_bytes(data, fname), ""
    except Exception as exc:
        import traceback; traceback.print_exc()
        err = html.Div([
            html.I(className="ti ti-alert-circle",
                   style={"color":"#E30613","marginRight":"6px"}),
            html.Span(f"Error: {exc}",
                      style={"fontSize":"11px","color":"#E30613"}),
        ], style={"display":"flex","alignItems":"center"})
        return no_update, err


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
