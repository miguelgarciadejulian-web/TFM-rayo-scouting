"""Perfil completo de un jugador: foto, percentiles, evolución, radar, encaje y notas."""
from __future__ import annotations
import json
import sys
import urllib.parse
from pathlib import Path
from datetime import date as _date

import dash
from dash import Input, Output, State, callback, dcc, html, no_update
import dash_bootstrap_components as dbc

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.utils.config import settings  # noqa: E402
from dashboard.components.player_detail import build_detail, player_options  # noqa: E402
from dashboard.components.criteria_block import criteria_accordion  # noqa: E402
from src.fit.clause_risk import evaluate_clause_risk, RISK_COLORS  # noqa: E402

dash.register_page(__name__, path="/jugador", name="Perfil Jugador")

PROC = Path(settings()["paths"]["data_processed"])
NOTES = PROC / "player_notes.json"
PHOTOS = PROC / "player_photos.json"
OVERRIDES = PROC / "player_overrides.json"

import unicodedata as _ud
import yaml as _yaml
from src.utils.market import get_value  # noqa: E402


def _norm(x):
    return _ud.normalize("NFKD", str(x)).encode("ascii", "ignore").decode().lower().strip()


def _load_overrides():
    if OVERRIDES.exists():
        try:
            return json.load(open(OVERRIDES, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_overrides(d):
    OVERRIDES.parent.mkdir(parents=True, exist_ok=True)
    json.dump(d, open(OVERRIDES, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def _load_notes():
    if NOTES.exists():
        return json.load(open(NOTES, encoding="utf-8"))
    return {}


def _save_notes(d):
    NOTES.parent.mkdir(parents=True, exist_ok=True)
    json.dump(d, open(NOTES, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def _load_photos():
    if PHOTOS.exists():
        try:
            return json.load(open(PHOTOS, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_photos(d):
    PHOTOS.parent.mkdir(parents=True, exist_ok=True)
    json.dump(d, open(PHOTOS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def _years_remaining(contract_until) -> float | None:
    """Años de contrato restantes desde hoy."""
    if not contract_until:
        return None
    try:
        end = _date.fromisoformat(str(contract_until)[:10])
        diff = (end - _date.today()).days / 365.25
        return round(max(diff, 0), 2)
    except Exception:
        return None


def _clause_risk_card(name: str, overrides: dict) -> html.Div:
    """Tarjeta de riesgo de clausula de rescision."""
    key_norm = _norm(name)
    ov = overrides.get(key_norm, {})

    clause_m = ov.get("clause_eur_millions")
    if not clause_m:
        return html.Div()  # No clause set -> nothing to show

    clause_eur = float(clause_m) * 1_000_000
    cv = get_value(name)
    mv = ov.get("value_eur") or cv.get("value_eur")
    contract = ov.get("contract_until") or cv.get("contract_until")
    age_raw = ov.get("age") or cv.get("age")
    age = int(float(age_raw)) if age_raw else None
    years = _years_remaining(contract)

    try:
        club_yaml = PROC.parents[1] / "config" / "club_profile.yaml"
        club = _yaml.safe_load(open(club_yaml, encoding="utf-8"))
        budget = club.get("finances_eur", {}).get("transfer_budget_net_eur", 10_000_000)
    except Exception:
        budget = 10_000_000

    result = evaluate_clause_risk(
        clause_eur=clause_eur,
        market_value_eur=float(mv) if mv else None,
        age=age,
        contract_years_remaining=years,
        rayo_budget_eur=budget,
    )

    bg, fg = RISK_COLORS[result.level]

    def _pct_bar(label, score):
        bar_color = (
            "#E30613" if score >= 75 else
            "#F97316" if score >= 55 else
            "#EAB308" if score >= 30 else
            "#22C55E"
        )
        return html.Div([
            html.Div([
                html.Span(label, style={"fontSize": "10px", "color": "#6B7280", "minWidth": "170px"}),
                html.Span(f"{score:.0f}", style={
                    "fontSize": "10px", "fontWeight": "700",
                    "color": bar_color, "marginLeft": "auto",
                }),
            ], style={"display": "flex", "marginBottom": "2px"}),
            html.Div(
                html.Div(style={"width": f"{score}%", "height": "4px",
                                "background": bar_color, "borderRadius": "2px"}),
                style={"background": "#E5E7EB", "borderRadius": "2px",
                       "height": "4px", "marginBottom": "6px"},
            ),
        ])

    FACTOR_LABELS = {
        "coste_relativo_presupuesto": "Coste relativo al presupuesto",
        "ratio_clausula_mercado":     "Ratio clausula / valor mercado",
        "edad_potencial":             "Potencial por edad",
        "contrato_restante":          "Urgencia contractual",
        "coste_absoluto":             "Coste absoluto",
    }

    bars = [_pct_bar(FACTOR_LABELS.get(k, k), v) for k, v in result.breakdown.items()]

    return html.Div([
        # Header
        html.Div([
            html.I(className="ti ti-shield-exclamation me-2",
                   style={"color": fg, "fontSize": "14px"}),
            html.Span("Riesgo de clausula de rescision", style={
                "fontSize": "11px", "fontWeight": "700",
                "color": "#9CA3AF", "textTransform": "uppercase",
                "letterSpacing": ".06em",
            }),
        ], style={"marginBottom": "10px"}),

        dbc.Row([
            # Badge de nivel + score
            dbc.Col([
                html.Div([
                    html.Span(result.level, style={
                        "fontSize": "1.5rem", "fontWeight": "800",
                        "color": fg, "lineHeight": "1",
                    }),
                    html.Div(f"Score: {result.score:.0f}/100", style={
                        "fontSize": "11px", "color": "#6B7280", "marginTop": "2px",
                    }),
                ], style={
                    "background": bg, "border": f"1px solid {fg}",
                    "borderRadius": "10px", "padding": "10px 16px",
                    "display": "inline-block", "marginBottom": "10px",
                }),
                html.Div([
                    html.Span(f"Clausula: {clause_m:.1f}M€", style={
                        "fontSize": "11px", "fontWeight": "600", "color": "#1A1A2E",
                        "marginRight": "12px",
                    }),
                    html.Span(
                        f"Valor mercado: {float(mv)/1e6:.1f}M€" if mv else "",
                        style={"fontSize": "11px", "color": "#6B7280"},
                    ),
                ]),
            ], md=4),

            # Barras de desglose
            dbc.Col(bars, md=4),

            # Narrativa
            dbc.Col([
                html.Div("Analisis", style={
                    "fontSize": "10px", "fontWeight": "700", "color": "#374151",
                    "textTransform": "uppercase", "letterSpacing": ".04em",
                    "marginBottom": "6px",
                }),
                html.P(result.narrative, style={
                    "fontSize": "11px", "color": "#555",
                    "lineHeight": "1.5", "margin": "0",
                }),
            ], md=4),
        ]),
    ], style={
        "background": "#fff", "border": "1px solid #E5E7EB", "borderRadius": "12px",
        "padding": "16px 18px", "marginTop": "16px",
        "boxShadow": "0 1px 3px rgba(0,0,0,.06)",
    })


def _notes_box(key, notes, photos, overrides):
    txt = notes.get(key, "")
    name = key.split("|")[0]
    key_norm = _norm(name)
    ov_entry = overrides.get(key_norm, {})
    _cv = get_value(name)
    _mk = {
        "val": round(float(ov_entry.get("value_eur") or _cv.get("value_eur")) / 1e6, 1)
               if (ov_entry.get("value_eur") or _cv.get("value_eur")) else None,
        "clause": ov_entry.get("clause_eur_millions"),
        "con": str(ov_entry.get("contract_until") or _cv.get("contract_until") or "")[:10] or None,
        "foot": ov_entry.get("foot") or _cv.get("foot") or None,
        "height": (float(ov_entry["height"]) if ov_entry.get("height") else
                   float(_cv["height"]) if _cv.get("height") else None),
    }
    return html.Div([
        html.P("Notas de scouting (se guardan)", style={
            "fontSize": "11px", "fontWeight": "700",
            "color": "#9CA3AF", "textTransform": "uppercase", "margin": "16px 0 8px",
        }),
        dcc.Textarea(id="player-note", value=txt,
                     placeholder="Escribe tus observaciones sobre el jugador...",
                     style={"width": "100%", "minHeight": "80px", "fontSize": "12px",
                            "padding": "10px", "border": "1px solid #D1D5DB",
                            "borderRadius": "8px"}),
        html.Div([
            html.Button("Guardar nota", id="save-note", n_clicks=0, style={
                "background": "#E30613", "color": "#fff", "border": "none",
                "borderRadius": "8px", "padding": "7px 16px",
                "fontSize": "12px", "fontWeight": "600", "cursor": "pointer",
                "marginTop": "8px",
            }),
            html.Span(id="note-status", style={
                "fontSize": "11px", "color": "#166534", "marginLeft": "10px",
            }),
        ]),
        dcc.Store(id="player-note-key", data=key),
        html.Hr(style={"margin": "14px 0", "borderColor": "#F3F4F6"}),
        html.P("Foto manual (pega la URL de la imagen si no sale automatica)", style={
            "fontSize": "11px", "fontWeight": "700", "color": "#9CA3AF",
            "textTransform": "uppercase", "margin": "0 0 6px",
        }),
        html.Div([
            dcc.Input(id="player-photo-url", type="text",
                      placeholder="https://img.a.transfermarkt.technology/portrait/big/...jpg",
                      value=photos.get(key, ""),
                      style={"flex": "1", "fontSize": "12px", "padding": "7px 10px",
                             "border": "1px solid #D1D5DB", "borderRadius": "8px"}),
            html.Button("Guardar foto", id="save-photo", n_clicks=0, style={
                "background": "#1A1A2E", "color": "#fff", "border": "none",
                "borderRadius": "8px", "padding": "7px 14px",
                "fontSize": "12px", "fontWeight": "600", "cursor": "pointer",
                "marginLeft": "8px",
            }),
        ], style={"display": "flex"}),
        html.Span(id="photo-status", style={"fontSize": "11px", "color": "#166534"}),
        html.Hr(style={"margin": "14px 0", "borderColor": "#F3F4F6"}),
        html.P("Datos de mercado y clausula (manual)", style={
            "fontSize": "11px", "fontWeight": "700", "color": "#9CA3AF",
            "textTransform": "uppercase", "margin": "0 0 6px",
        }),
        dbc.Row([
            dbc.Col([
                html.Span("Valor (M€)", style={"fontSize": "10px", "color": "#6B7280"}),
                dcc.Input(id="mkt-value", type="number", min=0, step=0.5,
                          value=_mk.get("val"), placeholder="ej. 8.0",
                          style={"width": "100%", "fontSize": "12px", "padding": "7px 10px",
                                 "border": "1px solid #D1D5DB", "borderRadius": "8px"}),
            ], md=2),
            dbc.Col([
                html.Span("Clausula (M€)", style={"fontSize": "10px", "color": "#6B7280"}),
                dcc.Input(id="mkt-clause", type="number", min=0, step=0.5,
                          value=_mk.get("clause"), placeholder="ej. 30.0",
                          style={"width": "100%", "fontSize": "12px", "padding": "7px 10px",
                                 "border": "1px solid #D1D5DB", "borderRadius": "8px"}),
            ], md=2),
            dbc.Col([
                html.Span("Fin contrato (AAAA-MM-DD)", style={"fontSize": "10px", "color": "#6B7280"}),
                dcc.Input(id="mkt-contract", type="text", value=_mk.get("con"),
                          placeholder="2028-06-30",
                          style={"width": "100%", "fontSize": "12px", "padding": "7px 10px",
                                 "border": "1px solid #D1D5DB", "borderRadius": "8px"}),
            ], md=3),
            dbc.Col([
                html.Span("Pie", style={"fontSize": "10px", "color": "#6B7280"}),
                dcc.Input(id="mkt-foot", type="text", value=_mk.get("foot"),
                          placeholder="Derecho",
                          style={"width": "100%", "fontSize": "12px", "padding": "7px 10px",
                                 "border": "1px solid #D1D5DB", "borderRadius": "8px"}),
            ], md=2),
            dbc.Col([
                html.Span("Altura (m)", style={"fontSize": "10px", "color": "#6B7280"}),
                dcc.Input(id="mkt-height", type="number", step=0.01, value=_mk.get("height"),
                          placeholder="1.85",
                          style={"width": "100%", "fontSize": "12px", "padding": "7px 10px",
                                 "border": "1px solid #D1D5DB", "borderRadius": "8px"}),
            ], md=3),
        ], className="g-2"),
        html.Div([
            html.Button("Guardar datos de mercado", id="save-market", n_clicks=0, style={
                "background": "#166534", "color": "#fff", "border": "none",
                "borderRadius": "8px", "padding": "7px 16px", "fontSize": "12px",
                "fontWeight": "600", "cursor": "pointer", "marginTop": "8px",
            }),
            html.Span(id="market-status", style={
                "fontSize": "11px", "color": "#166534", "marginLeft": "10px",
            }),
        ]),
    ], style={
        "background": "#fff", "border": "1px solid #E5E7EB", "borderRadius": "12px",
        "padding": "16px 18px", "marginTop": "16px",
    })


# ---------------------------------------------------------------------------
# FitRayo block
# ---------------------------------------------------------------------------

_FIT_SCORER_CACHE: dict = {}


def _get_fit_scorer():
    if "scorer" not in _FIT_SCORER_CACHE:
        try:
            from src.scouting.comparator import load_scorer
            club_yaml = PROC.parents[1] / "config" / "club_profile.yaml"
            with open(club_yaml, encoding="utf-8") as f:
                club = _yaml.safe_load(f)
            squad = []
            for section in club.get("squad_2025_26", {}).values():
                if isinstance(section, list):
                    squad.extend(section)
            _FIT_SCORER_CACHE["scorer"] = load_scorer(PROC, squad)
        except Exception:
            _FIT_SCORER_CACHE["scorer"] = None
    return _FIT_SCORER_CACHE["scorer"]


def _fit_rayo_card(name: str) -> html.Div:
    """Tarjeta FitRayo con puntuacion y narrativa para el jugador dado."""
    scorer = _get_fit_scorer()
    if scorer is None:
        return html.Div()
    try:
        results = scorer.compare([name])
    except Exception:
        return html.Div()
    if not results:
        return html.Div()

    r = results[0]

    def _color(v):
        if v >= 70: return "#166534"
        if v >= 50: return "#1D4ED8"
        if v >= 30: return "#92400E"
        return "#991B1B"

    def _bar(label, val, icon):
        c = _color(val)
        return html.Div([
            html.Div([
                html.I(className=f"ti {icon}",
                       style={"color": c, "marginRight": "5px", "fontSize": "12px"}),
                html.Span(label, style={
                    "fontSize": "11px", "fontWeight": "600", "color": "#374151",
                    "minWidth": "130px",
                }),
                html.Span(f"{val:.0f}/100", style={
                    "fontSize": "11px", "color": c, "fontWeight": "700",
                    "marginLeft": "auto",
                }),
            ], style={"display": "flex", "alignItems": "center", "marginBottom": "3px"}),
            html.Div(
                html.Div(style={"width": f"{val}%", "height": "5px",
                                "background": c, "borderRadius": "3px",
                                "transition": "width 0.3s"}),
                style={"background": "#E5E7EB", "borderRadius": "3px",
                       "height": "5px", "marginBottom": "8px"},
            ),
        ])

    ICONS = {"rendimiento": "ti-run", "economico": "ti-coin-euro",
             "edad": "ti-calendar", "disponibilidad": "ti-door-enter"}
    LABELS = {"rendimiento": "Rendimiento", "economico": "Encaje economico",
              "edad": "Perfil de edad", "disponibilidad": "Disponibilidad"}

    bars = [
        _bar("Rendimiento",    r.score_rendimiento,    "ti-run"),
        _bar("Enc. economico", r.score_economico,      "ti-coin-euro"),
        _bar("Perfil de edad", r.score_edad,           "ti-calendar"),
        _bar("Disponibilidad", r.score_disponibilidad, "ti-door-enter"),
    ]

    narrative_items = []
    for key, text in (r.narrative or {}).items():
        narrative_items.append(html.Div([
            html.Div([
                html.I(className=f"ti {ICONS.get(key,'ti-info-circle')}",
                       style={"color": "#E30613", "marginRight": "5px", "fontSize": "11px"}),
                html.Span(LABELS.get(key, key), style={
                    "fontWeight": "700", "fontSize": "11px", "color": "#1A1A2E",
                }),
            ], style={"marginBottom": "2px"}),
            html.P(text, style={"fontSize": "11px", "color": "#555",
                                "margin": "0 0 8px", "lineHeight": "1.45",
                                "paddingLeft": "16px"}),
        ]))

    score_color = _color(r.fit_score)

    loan_badge = (
        dbc.Badge(f"CEDIDO · {r.loan_from}", color="warning", text_color="dark",
                  pill=True, className="ms-2", style={"fontSize": "0.7rem"})
        if r.loan_from else None
    )

    # Desglose de la fórmula (transparencia total)
    formula_items = [
        ("Rendimiento",    r.score_rendimiento,    "35%", "#1A1A2E"),
        ("Enc. económico", r.score_economico,      "25%", "#1A1A2E"),
        ("Perfil de edad", r.score_edad,           "20%", "#1A1A2E"),
        ("Disponibilidad", r.score_disponibilidad, "20%", "#1A1A2E"),
    ]
    formula_rows = []
    for label, val, weight, _ in formula_items:
        c = _color(val)
        formula_rows.append(html.Tr([
            html.Td(label,    style={"fontSize": "10px", "color": "#6B7280", "paddingRight": "8px"}),
            html.Td(weight,   style={"fontSize": "10px", "color": "#9CA3AF", "textAlign": "right", "paddingRight": "8px"}),
            html.Td(f"{val:.0f}", style={"fontSize": "10px", "fontWeight": "700", "color": c, "textAlign": "right"}),
        ]))
    formula_rows.append(html.Tr([
        html.Td("FIT RAYO", style={"fontSize": "10px", "fontWeight": "800", "color": "#1A1A2E",
                                   "paddingTop": "4px", "borderTop": "1px solid #E5E7EB"}),
        html.Td("100%",     style={"fontSize": "10px", "color": "#9CA3AF", "textAlign": "right",
                                   "paddingTop": "4px", "borderTop": "1px solid #E5E7EB"}),
        html.Td(f"{r.fit_score:.0f}", style={"fontSize": "10px", "fontWeight": "800",
                                              "color": score_color, "textAlign": "right",
                                              "paddingTop": "4px", "borderTop": "1px solid #E5E7EB"}),
    ]))

    formula_panel = html.Div([
        html.Div("Fórmula del Fit Rayo", style={
            "fontSize": "9px", "fontWeight": "700", "color": "#9CA3AF",
            "textTransform": "uppercase", "letterSpacing": ".05em", "marginBottom": "6px",
        }),
        html.Div("Score = 0.35 × Rendimiento + 0.25 × Económico + 0.20 × Edad + 0.20 × Disponibilidad",
                 style={"fontSize": "9px", "color": "#6B7280", "fontStyle": "italic",
                        "marginBottom": "8px", "fontFamily": "monospace"}),
        html.Table(formula_rows, style={"width": "100%", "borderCollapse": "collapse"}),
    ], style={
        "background": "#F9FAFB", "borderRadius": "8px", "padding": "10px 12px",
        "marginTop": "14px", "border": "1px solid #F3F4F6",
    })

    return html.Div([
        html.Div([
            html.I(className="ti ti-heart-rate-monitor me-2",
                   style={"color": "#E30613", "fontSize": "14px"}),
            html.Span("Fit Rayo Vallecano", style={
                "fontSize": "11px", "fontWeight": "700",
                "color": "#9CA3AF", "textTransform": "uppercase",
                "letterSpacing": ".06em",
            }),
            html.Span("  ·  calculado automáticamente desde datos Opta + Transfermarkt",
                      style={"fontSize": "9px", "color": "#9CA3AF", "fontStyle": "italic"}),
        ], style={"marginBottom": "10px"}),

        # Score principal
        html.Div([
            html.Span(f"{r.fit_score:.0f}", style={
                "fontSize": "2.5rem", "fontWeight": "800",
                "color": score_color, "lineHeight": "1",
            }),
            html.Span("/100", style={"fontSize": "1rem", "color": "#9CA3AF",
                                     "marginLeft": "4px"}),
            loan_badge,
        ], style={"display": "flex", "alignItems": "baseline",
                  "marginBottom": "14px", "gap": "4px"}),

        # Barras por componente + narrativa
        dbc.Row([
            dbc.Col(bars, md=5),
            dbc.Col([
                html.Div("¿Por qué esta puntuación?", style={
                    "fontSize": "11px", "fontWeight": "700", "color": "#374151",
                    "marginBottom": "8px", "textTransform": "uppercase",
                    "letterSpacing": ".04em",
                }),
                *narrative_items,
            ], md=7),
        ]),

        # Fórmula con pesos y valores reales
        formula_panel,
    ], style={
        "background": "#fff", "border": "1px solid #E5E7EB", "borderRadius": "12px",
        "padding": "16px 18px", "marginTop": "16px",
        "boxShadow": "0 1px 3px rgba(0,0,0,.06)",
    })


def layout(**_params):
    return html.Div([
        dcc.Location(id="jugador-loc"),
        html.Div([
            html.P("SCOUTING", style={"fontSize": "10px", "fontWeight": "600",
                   "color": "#6B7280", "letterSpacing": ".08em", "margin": "0 0 3px"}),
            html.H1("Perfil de jugador", className="page-title"),
            html.Div([
                html.Span("Buscar jugador: ", style={"fontSize": "12px", "color": "#6B7280",
                          "marginRight": "8px"}),
                dcc.Dropdown(id="jugador-search", options=[],
                             placeholder="Escribe un nombre...",
                             style={"width": "360px", "fontSize": "13px"}),
                html.Button([
                    html.I(className="ti ti-file-download", style={"marginRight": "6px"}),
                    "Descargar PDF",
                ], id="dl-pdf-btn", n_clicks=0, style={
                    "marginLeft": "12px", "background": "#1A1A2E", "color": "#fff",
                    "border": "none", "borderRadius": "8px", "padding": "8px 16px",
                    "fontSize": "13px", "fontWeight": "600", "cursor": "pointer",
                }),
                dcc.Download(id="dl-pdf"),
                dcc.Store(id="current-player"),
            ], style={"display": "flex", "alignItems": "center", "marginTop": "6px"}),
            html.Div(id="pdf-error-msg", style={"marginTop": "6px"}),
        ], className="page-header"),
        dcc.Loading(html.Div(id="jugador-content"), type="circle", color="#E30613"),
        criteria_accordion("jugador"),
    ])


@callback(Output("jugador-search", "options"), Input("jugador-loc", "pathname"))
def _fill_search(_):
    return player_options()


@callback(Output("jugador-content", "children"),
          Input("jugador-loc", "search"), Input("jugador-search", "value"))
def render_player(search, picked):
    name, team = "", ""
    if picked and "|||" in picked:
        name, team = picked.split("|||", 1)
    elif search and search.startswith("?"):
        params = dict(urllib.parse.parse_qsl(search[1:]))
        name = params.get("name", "")
        team = params.get("team", "")
    if not name:
        return html.Div(
            "Usa el buscador de arriba o selecciona un jugador desde Scouting.",
            style={"color": "#6B7280", "fontSize": "13px", "padding": "20px"},
        )
    try:
        detail = build_detail(name, team=team or None)
    except Exception as exc:
        return dbc.Alert(f"No se pudo construir el perfil: {exc}", color="warning")
    key = f"{name}|{team}"
    ovs = _load_overrides()
    fit_card = _fit_rayo_card(name)
    risk_card = _clause_risk_card(name, ovs)
    return html.Div([detail, fit_card, risk_card,
                     _notes_box(key, _load_notes(), _load_photos(), ovs)])


@callback(Output("current-player", "data"),
          Input("jugador-loc", "search"), Input("jugador-search", "value"))
def _track_player(search, picked):
    if picked and "|||" in picked:
        n, t = picked.split("|||", 1)
        return {"name": n, "team": t}
    if search and search.startswith("?"):
        import urllib.parse as _u
        pr = dict(_u.parse_qsl(search[1:]))
        return {"name": pr.get("name", ""), "team": pr.get("team", "")}
    return None


_PDF_BTN_DEFAULT = [
    html.I(className="ti ti-file-download", style={"marginRight": "6px"}),
    "Descargar PDF",
]
_PDF_BTN_LOADING = [
    html.I(className="ti ti-loader-2", style={"marginRight": "6px",
           "animation": "spin 1s linear infinite"}),
    "Generando...",
]


_BTN_STYLE_DEFAULT = {
    "marginLeft": "12px", "background": "#1A1A2E", "color": "#fff",
    "border": "none", "borderRadius": "8px", "padding": "8px 16px",
    "fontSize": "13px", "fontWeight": "600", "cursor": "pointer",
}
_BTN_STYLE_LOADING = {
    **_BTN_STYLE_DEFAULT,
    "background": "#6B7280", "cursor": "not-allowed",
}


@callback(
    Output("dl-pdf", "data"),
    Output("pdf-error-msg", "children"),
    Output("dl-pdf-btn", "disabled"),
    Output("dl-pdf-btn", "children"),
    Output("dl-pdf-btn", "style"),
    Input("dl-pdf-btn", "n_clicks"),
    State("current-player", "data"),
    prevent_initial_call=True,
)
def _download_pdf(n, cur):
    if not n or not cur or not cur.get("name"):
        return no_update, no_update, no_update, no_update, no_update
    # Indicar carga — devolvemos estado "loading" + generamos PDF en la misma llamada
    from src.reports.player_dossier import build_player_dossier
    try:
        fname, data = build_player_dossier(cur["name"], team=cur.get("team") or None)
        return dcc.send_bytes(data, fname), "", False, _PDF_BTN_DEFAULT, _BTN_STYLE_DEFAULT
    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        err_msg = html.Div([
            html.I(className="ti ti-alert-circle",
                   style={"color": "#E30613", "marginRight": "6px"}),
            html.Span(f"Error generando PDF: {exc}",
                      style={"fontSize": "11px", "color": "#E30613"}),
            html.Span(" — Vuelve a intentarlo",
                      style={"fontSize": "11px", "color": "#6B7280"}),
        ], style={"display": "flex", "alignItems": "center"})
        return no_update, err_msg, False, _PDF_BTN_DEFAULT, _BTN_STYLE_DEFAULT


@callback(Output("note-status", "children"),
          Input("save-note", "n_clicks"),
          State("player-note", "value"), State("player-note-key", "data"),
          prevent_initial_call=True)
def save_note(n, text, key):
    if not n or not key:
        return no_update
    notes = _load_notes()
    notes[key] = (text or "").strip()
    _save_notes(notes)
    return "Guardada"


@callback(Output("photo-status", "children"),
          Input("save-photo", "n_clicks"),
          State("player-photo-url", "value"), State("player-note-key", "data"),
          prevent_initial_call=True)
def save_photo(n, url, key):
    if not n or not key:
        return no_update
    photos = _load_photos()
    photos[key] = (url or "").strip()
    _save_photos(photos)
    return "Foto guardada — recarga la pagina para verla"


@callback(Output("market-status", "children"),
          Input("save-market", "n_clicks"),
          State("mkt-value", "value"), State("mkt-clause", "value"),
          State("mkt-contract", "value"),
          State("mkt-foot", "value"), State("mkt-height", "value"),
          State("player-note-key", "data"),
          prevent_initial_call=True)
def save_market(n, value_m, clause_m, contract, foot, height, key):
    if not n or not key:
        return no_update
    name = key.split("|")[0]
    ov = _load_overrides()
    entry = ov.get(_norm(name), {})
    if value_m not in (None, ""):
        entry["value_eur"] = float(value_m) * 1_000_000
    if clause_m not in (None, ""):
        entry["clause_eur_millions"] = float(clause_m)
    if contract:
        entry["contract_until"] = str(contract).strip()
    if foot:
        entry["foot"] = str(foot).strip()
    if height not in (None, ""):
        entry["height"] = height
    ov[_norm(name)] = entry
    _save_overrides(ov)
    return "Guardado — recarga la pagina para verlo"
