# -*- coding: utf-8 -*-
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
from src.utils.lateral_position import LATERAL_LABELS, ROLE_TYPE_LABELS, LATERAL_TO_ROLES  # noqa: E402

# Pre-importar el modulo de PDF en el arranque para evitar error en primer intento
try:
    from src.reports.player_dossier import build_player_dossier as _pdf_preload  # noqa: F401
except Exception:
    pass

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
            "#F59E0B" if score >= 75 else
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


def _get_tm_id_for_player(name, opta_id=None):
    """Devuelve el tm_id actual del jugador desde entity_map o market_values."""
    entity_map_path = PROC / "player_entity_map.csv"
    try:
        import pandas as pd
        if opta_id and entity_map_path.exists():
            em = pd.read_csv(entity_map_path)
            row = em[em["opta_id"].astype(str) == str(opta_id)]
            if not row.empty:
                tid = str(row.iloc[0].get("tm_id", "")).replace(".0", "").strip()
                if tid.isdigit():
                    return tid
        # Fallback: market_values por nombre
        mv_path = PROC.parent / "config" / "market_values.csv"
        if mv_path.exists():
            mv = pd.read_csv(mv_path)
            match = mv[mv["name"].apply(_norm) == _norm(name)]
            if not match.empty:
                tid = str(match.iloc[0].get("tm_id", "")).replace(".0", "").strip()
                if tid.isdigit():
                    return tid
    except Exception:
        pass
    return ""


def _tm_strip(key, opta_id=None):
    """Bloque TM compacto para incrustar en el header del perfil (a la izq. de Volver)."""
    name = key.split("|")[0]
    current_tm_id = _get_tm_id_for_player(name, opta_id)
    tm_profile_url = (
        "https://www.transfermarkt.es/spieler/profil/spieler/{}".format(current_tm_id)
        if current_tm_id else "https://www.transfermarkt.es/"
    )
    return html.Div([
        dcc.Store(id="player-note-key", data=key),
        dcc.Store(id="player-opta-id", data=opta_id or ""),
        # Link "Comprobar en TM"
        html.A(
            [html.I(className="ti ti-external-link",
                    style={"fontSize": "11px", "marginRight": "4px"}),
             "Comprobar en Transfermarkt"],
            href=tm_profile_url, target="_blank",
            style={"fontSize": "12px", "color": "#1D4ED8", "textDecoration": "none",
                   "fontWeight": "600", "display": "block", "marginBottom": "6px",
                   "whiteSpace": "nowrap"},
        ),
        # Fila: ID input + botón
        html.Div([
            dcc.Input(
                id="tm-id-input", type="text",
                value=current_tm_id,
                placeholder="ID TM (ej. 258923)",
                style={"width": "130px", "fontSize": "11px", "padding": "4px 8px",
                       "border": "1px solid #D1D5DB", "borderRadius": "6px",
                       "marginRight": "5px"},
            ),
            html.Button(
                [html.I(className="ti ti-refresh", style={"marginRight": "3px"}),
                 "Actualizar"],
                id="btn-fetch-tm", n_clicks=0,
                style={"background": "#1D4ED8", "color": "#fff", "border": "none",
                       "borderRadius": "6px", "padding": "4px 10px",
                       "fontSize": "11px", "fontWeight": "600", "cursor": "pointer",
                       "whiteSpace": "nowrap"},
            ),
        ], style={"display": "flex", "alignItems": "center"}),
        html.Span(id="tm-fetch-status", style={
            "fontSize": "10px", "color": "#166534", "marginTop": "4px", "display": "block",
        }),
    ], style={
        "background": "#F0F4FF", "border": "1px solid #C7D7FD",
        "borderRadius": "10px", "padding": "10px 14px",
        "minWidth": "190px", "alignSelf": "flex-start",
    })


def _notes_box(key, notes, overrides):
    txt = notes.get(key, "")
    name = key.split("|")[0]
    key_norm = _norm(name)
    ov_entry = overrides.get(key_norm, {})
    _mk = {
        "lateral_pos": ov_entry.get("lateral_pos"),
        "role_type": ov_entry.get("role_type"),
    }

    return html.Div([
        # ── Notas ────────────────────────────────────────────────────────────
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
                "background": "#FFD600", "color": "#0D0D0D", "border": "none",
                "borderRadius": "8px", "padding": "7px 16px",
                "fontSize": "12px", "fontWeight": "600", "cursor": "pointer",
                "marginTop": "8px",
            }),
            html.Span(id="note-status", style={
                "fontSize": "11px", "color": "#166534", "marginLeft": "10px",
            }),
        ]),
        html.Hr(style={"margin": "14px 0", "borderColor": "#F3F4F6"}),
        html.P("Posición y tipología (override manual)", style={
            "fontSize": "11px", "fontWeight": "700", "color": "#9CA3AF",
            "textTransform": "uppercase", "margin": "0 0 6px",
        }),
        dbc.Row([
            dbc.Col([
                html.Span("Posición lateral", style={"fontSize": "10px", "color": "#6B7280"}),
                dcc.Dropdown(
                    id="mkt-lateral-pos",
                    options=[{"label": v, "value": k} for k, v in LATERAL_LABELS.items()],
                    value=_mk.get("lateral_pos"),
                    placeholder="Inferida automáticamente",
                    clearable=True,
                    style={"fontSize": "12px"},
                ),
            ], md=4),
            dbc.Col([
                html.Span("Tipo de jugador", style={"fontSize": "10px", "color": "#6B7280"}),
                dcc.Dropdown(
                    id="mkt-role-type",
                    options=[{"label": v, "value": k} for k, v in ROLE_TYPE_LABELS.items()],
                    value=_mk.get("role_type"),
                    placeholder="Inferido automáticamente",
                    clearable=True,
                    style={"fontSize": "12px"},
                ),
            ], md=4),
        ], className="g-2"),
        html.Div([
            html.Button("Guardar posición y tipología", id="save-lateral", n_clicks=0, style={
                "background": "#1A1A2E", "color": "#fff", "border": "none",
                "borderRadius": "8px", "padding": "7px 16px", "fontSize": "12px",
                "fontWeight": "600", "cursor": "pointer", "marginTop": "8px",
            }),
            html.Span(id="lateral-status", style={
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
        if v is None: return "#9CA3AF"
        if v >= 70: return "#166534"
        if v >= 50: return "#1D4ED8"
        if v >= 30: return "#92400E"
        return "#991B1B"

    def _bar(label, val, icon):
        if val is None:
            return html.Div([
                html.Div([
                    html.I(className=f"ti {icon}",
                           style={"color": "#9CA3AF", "marginRight": "5px", "fontSize": "12px"}),
                    html.Span(label, style={
                        "fontSize": "11px", "fontWeight": "600", "color": "#374151",
                        "minWidth": "130px",
                    }),
                    html.Span("N/A", style={
                        "fontSize": "11px", "color": "#9CA3AF", "fontWeight": "600",
                        "marginLeft": "auto",
                    }),
                ], style={"display": "flex", "alignItems": "center", "marginBottom": "3px"}),
                html.Div(
                    html.Div(style={"width": "0%", "height": "5px",
                                    "background": "#9CA3AF", "borderRadius": "3px"}),
                    style={"background": "#E5E7EB", "borderRadius": "3px",
                           "height": "5px", "marginBottom": "8px"},
                ),
            ])
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
                       style={"color": "#B8960C", "marginRight": "5px", "fontSize": "11px"}),
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

    # ── Desglose por sub-score (transparencia total) ─────────────────────
    def _mini_row(label, weight, value, note=""):
        c = _color(value)
        return html.Div([
            html.Div([
                html.Span(label, style={"fontSize": "10px", "color": "#374151",
                                        "fontWeight": "600", "minWidth": "120px"}),
                html.Span(f"×{weight}", style={"fontSize": "9px", "color": "#9CA3AF",
                                                "marginLeft": "6px", "minWidth": "30px"}),
                html.Span(f"{value:.0f}", style={"fontSize": "10px", "fontWeight": "800",
                                                   "color": c, "marginLeft": "auto"}),
            ], style={"display": "flex", "alignItems": "center", "marginBottom": "2px"}),
            html.Div(html.Div(style={"width": f"{value}%", "height": "3px",
                                     "background": c, "borderRadius": "2px"}),
                     style={"background": "#E5E7EB", "borderRadius": "2px",
                            "height": "3px", "marginBottom": "4px"}),
            (html.Div(note, style={"fontSize": "9px", "color": "#6B7280",
                                   "marginBottom": "6px", "fontStyle": "italic"}) if note else html.Span()),
        ])

    # --- Rendimiento ---
    scorer = _get_fit_scorer()
    rend_bd = disp_bd = eco_bd = edad_bd = {}
    if scorer:
        try:
            row_data = scorer._best_row(r.name)
            if row_data is not None:
                rend_bd = scorer.score_rendimiento_breakdown(row_data)
                eco_bd  = scorer.score_economico_breakdown(r.market_value_eur or 0)
                # Edad: fallback a TM/overrides si OPTA no tiene el dato
                _age_for_fit = r.age or 0
                if not _age_for_fit:
                    _cv_age = get_value(r.name)
                    _ov_age = _load_overrides().get(
                        __import__("unicodedata").normalize("NFKD", r.name.lower())
                        .encode("ascii", "ignore").decode().strip(), {}
                    ).get("age")
                    _age_for_fit = float(_ov_age or _cv_age.get("age") or 0)
                edad_bd = scorer.score_edad_breakdown(_age_for_fit, r.position)
                disp_bd = scorer.score_disponibilidad_breakdown(
                    r.contract_until, r.name,
                    loan_from=r.loan_from,
                )
        except Exception:
            pass

    def _sub_panel(title, icon, items, formula_line):
        """Panel colapsable de desglose de un sub-score."""
        return html.Details([
            html.Summary([
                html.I(className=f"ti {icon}",
                       style={"fontSize": "11px", "marginRight": "5px", "color": "#B8960C"}),
                html.Span(title, style={"fontSize": "10px", "fontWeight": "700",
                                        "color": "#374151", "cursor": "pointer"}),
            ], style={"listStyle": "none", "display": "flex", "alignItems": "center",
                      "padding": "6px 0", "cursor": "pointer"}),
            html.Div([
                html.Div(formula_line,
                         style={"fontSize": "9px", "fontFamily": "monospace",
                                "color": "#6B7280", "marginBottom": "8px",
                                "padding": "4px 8px", "background": "#F3F4F6",
                                "borderRadius": "4px"}),
                *items,
            ], style={"paddingLeft": "16px"}),
        ], style={"borderBottom": "1px solid #F3F4F6", "paddingBottom": "4px"})

    # Paneles de cada sub-score
    if rend_bd and rend_bd.get("dims"):
        _subpos_lbl  = rend_bd.get("subpos_label", rend_bd.get("pos_grp", "—"))
        _pool_n      = rend_bd.get("pool_size", 0)
        _ld          = rend_bd.get("league_diff", 1.0)
        _raw         = rend_bd.get("raw_score", 0)
        _ld_note     = f" · dif. liga ×{_ld:.2f}" if _ld != 1.0 else ""
        rend_items = [
            html.Div(
                f"{_subpos_lbl}  ·  {_pool_n} jugadores ≥450 min{_ld_note}",
                style={"fontSize": "9px", "fontFamily": "monospace", "color": "#6B7280",
                       "marginBottom": "8px", "padding": "4px 8px",
                       "background": "#F3F4F6", "borderRadius": "4px"},
            ),
            *[
                _mini_row(
                    d["label"],
                    f"×{d['weight']:.0%}",
                    d["score"],
                    f"Percentil {d['score']:.0f}/100 vs {_subpos_lbl.lower()}s con ≥450 min",
                )
                for d in rend_bd["dims"]
            ],
            html.Div(
                f"Bruto: {_raw:.1f}{_ld_note} → {rend_bd.get('score', 0):.1f}/100",
                style={"fontSize": "8px", "color": "#9CA3AF", "fontStyle": "italic",
                       "marginTop": "6px", "paddingTop": "6px",
                       "borderTop": "1px dashed #E5E7EB"},
            ),
        ]
    else:
        rend_items = [html.Div("Sin datos disponibles", style={"fontSize": "10px", "color": "#9CA3AF"})]

    eco_items = ([
        html.Div([
            html.Span("Valor mercado: ", style={"fontSize": "10px", "color": "#6B7280"}),
            html.Span(f"€{eco_bd.get('mv_eur',0)/1e6:.1f}M" if eco_bd.get('mv_eur') else "Sin datos",
                      style={"fontSize": "10px", "fontWeight": "700", "color": "#1A1A2E"}),
        ], style={"marginBottom": "4px"}),
        html.Div(eco_bd.get("tramo", ""), style={"fontSize": "9px", "color": "#6B7280",
                                                   "fontStyle": "italic", "marginBottom": "6px"}),
        html.Div([
            html.Span("Horquilla Rayo: ", style={"fontSize": "9px", "color": "#9CA3AF"}),
            html.Span(f"Min {eco_bd.get('mv_min',0)/1e6:.1f}M · Ideal ≤{eco_bd.get('mv_sweet',0)/1e6:.0f}M · Máx {eco_bd.get('mv_max',0)/1e6:.0f}M",
                      style={"fontSize": "9px", "color": "#6B7280"}),
        ]),
    ] if eco_bd else [html.Div("Sin datos disponibles", style={"fontSize": "10px", "color": "#9CA3AF"})])

    edad_items = ([
        html.Div([
            html.Span(f"Edad: {edad_bd.get('age',0):.0f} años  ·  Posición: {edad_bd.get('pos','')}",
                      style={"fontSize": "10px", "color": "#374151", "fontWeight": "600"}),
        ], style={"marginBottom": "4px"}),
        html.Div(edad_bd.get("fase", ""), style={"fontSize": "9px", "color": "#6B7280",
                                                   "fontStyle": "italic", "marginBottom": "4px"}),
        html.Div([
            html.Span("Curva: ", style={"fontSize": "9px", "color": "#9CA3AF"}),
            html.Span(f"Prime {edad_bd.get('prime',0)} años · Declive >{edad_bd.get('decline',0)} años",
                      style={"fontSize": "9px", "color": "#6B7280"}),
        ]),
    ] if edad_bd else [html.Div("Sin datos disponibles", style={"fontSize": "10px", "color": "#9CA3AF"})])

    disp_items = ([
        html.Div(disp_bd.get("situacion", ""), style={"fontSize": "10px", "color": "#374151",
                                                        "fontWeight": "600", "marginBottom": "4px"}),
        html.Div([
            html.Span("Contrato hasta: ", style={"fontSize": "9px", "color": "#9CA3AF"}),
            html.Span(str(disp_bd.get("contract_until","Sin datos") or "Sin datos")[:10],
                      style={"fontSize": "9px", "color": "#374151"}),
        ], style={"marginBottom": "4px"}),
        (html.Div(disp_bd.get("bonus_rayo", ""),
                  style={"fontSize": "9px", "color": "#166534", "fontStyle": "italic"})
         if disp_bd.get("bonus_rayo") else html.Span()),
    ] if disp_bd else [html.Div("Sin datos disponibles", style={"fontSize": "10px", "color": "#9CA3AF"})])

    breakdown_panel = html.Div([
        html.Div([
            html.Div("Desglose de sub-scores", style={
                "fontSize": "9px", "fontWeight": "700", "color": "#9CA3AF",
                "textTransform": "uppercase", "letterSpacing": ".05em", "marginBottom": "8px",
            }),
            html.Div("Fit Rayo = 0.40 × Rendimiento + 0.30 × Económico + 0.15 × Edad + 0.15 × Disponibilidad",
                     style={"fontSize": "9px", "color": "#6B7280", "fontStyle": "italic",
                            "marginBottom": "10px", "fontFamily": "monospace"}),

            dbc.Row([
                dbc.Col(_sub_panel(
                    "Rendimiento (40%)", "ti-run", rend_items,
                    "Percentiles por dimensión vs misma posición · ≥50 min",
                ), md=6),
                dbc.Col(_sub_panel(
                    "Encaje económico (30%)", "ti-coin-euro", eco_items,
                    "Curva progresiva: ≤7M→90 · 10M→70 · 20M→20 · >70M→0",
                ), md=6),
            ], className="g-2"),
            dbc.Row([
                dbc.Col(_sub_panel(
                    "Perfil de edad (15%)", "ti-calendar", edad_items,
                    "Joven ≤21→95 · 22-25→90 · 26-28→90→78 · 29-30→60 · >33→10",
                ), md=6),
                dbc.Col(_sub_panel(
                    "Disponibilidad (15%)", "ti-door-enter", disp_items,
                    "Meses contrato restantes: ≤6→95 / ≤12→75 / ≤24→50 / >24→25",
                ), md=6),
            ], className="g-2 mt-1"),
        ]),
    ], style={
        "background": "#F9FAFB", "borderRadius": "8px", "padding": "12px 14px",
        "marginTop": "14px", "border": "1px solid #F3F4F6",
    })

    # Tabla resumen fórmula
    formula_items = [
        ("Rendimiento",    r.score_rendimiento,    "40%"),
        ("Enc. económico", r.score_economico,      "30%"),
        ("Perfil de edad", r.score_edad,           "15%"),
        ("Disponibilidad", r.score_disponibilidad, "15%"),
    ]
    formula_rows = []
    for lbl, val, weight in formula_items:
        c        = _color(val)
        val_txt  = f"{val:.0f}" if val is not None else "N/A"
        wt_txt   = "—" if val is None else weight
        formula_rows.append(html.Tr([
            html.Td(lbl,     style={"fontSize": "10px", "color": "#6B7280", "paddingRight": "8px"}),
            html.Td(wt_txt,  style={"fontSize": "10px", "color": "#9CA3AF", "textAlign": "right", "paddingRight": "8px"}),
            html.Td(val_txt, style={"fontSize": "10px", "fontWeight": "700", "color": c, "textAlign": "right"}),
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
        html.Table(formula_rows, style={"width": "100%", "borderCollapse": "collapse"}),
    ], style={
        "background": "#F9FAFB", "borderRadius": "8px", "padding": "10px 12px",
        "marginTop": "14px", "border": "1px solid #F3F4F6",
    })

    return html.Div([
        html.Div([
            html.I(className="ti ti-heart-rate-monitor me-2",
                   style={"color": "#B8960C", "fontSize": "14px"}),
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

        # Fórmula resumen + desglose por sub-score
        formula_panel,
        breakdown_panel,
    ], style={
        "background": "#fff", "border": "1px solid #E5E7EB", "borderRadius": "12px",
        "padding": "16px 18px", "marginTop": "16px",
        "boxShadow": "0 1px 3px rgba(0,0,0,.06)",
    })


def layout(**_params):
    return html.Div([
        dcc.Location(id="jugador-loc"),
        dcc.Store(id="tm-reload-trigger", data=None),
        html.Div(id="tm-reload-dummy", style={"display": "none"}),
        html.Div([
            html.P("SCOUTING", style={"fontSize": "10px", "fontWeight": "600",
                   "color": "#6B7280", "letterSpacing": ".08em", "margin": "0 0 3px"}),
            html.H1("Perfil de jugador", className="page-title"),
            html.Div([
                html.Span("Buscar jugador: ", style={"fontSize": "12px", "color": "#6B7280",
                          "marginRight": "8px"}),
                dcc.Dropdown(id="jugador-search", options=[],
                             placeholder="Escribe un nombre...",
                             search_value="",
                             style={"width": "360px", "fontSize": "13px"}),
                dcc.Loading(html.Div([
                    html.Button([
                        html.I(className="ti ti-file-download", style={"marginRight": "6px"}),
                        "Descargar PDF",
                    ], id="dl-pdf-btn", n_clicks=0, style={
                        "background": "#1A1A2E", "color": "#fff",
                        "border": "none", "borderRadius": "8px", "padding": "8px 16px",
                        "fontSize": "13px", "fontWeight": "600", "cursor": "pointer",
                    }),
                    dcc.Download(id="dl-pdf"),
                ], style={"marginLeft": "12px"}), type="circle", color="#FFD600"),
                dcc.Store(id="current-player"),
                dcc.Store(id="jugador-picked-store"),
            ], style={"display": "flex", "alignItems": "center", "marginTop": "6px"}),
            html.Div(id="pdf-error-msg", style={"marginTop": "6px"}),
        ], className="page-header"),
        dcc.Loading(html.Div(id="jugador-content"), type="circle", color="#FFD600"),
        criteria_accordion("jugador"),
    ])


@callback(Output("jugador-search", "options"), Input("jugador-search", "search_value"))
def _fill_search(search):
    return player_options(search or "")


@callback(Output("jugador-picked-store", "data"),
          Input("jugador-search", "value"),
          prevent_initial_call=True)
def _save_pick(val):
    if val and "|||" in val:
        return val
    return no_update


# Cuando el dropdown selecciona un jugador → actualizar la URL
# Así la URL es siempre la única fuente de verdad para el PDF y el render
@callback(Output("jugador-loc", "search"),
          Input("jugador-search", "value"),
          prevent_initial_call=True)
def _sync_url_from_dropdown(val):
    if val and "|||" in val:
        parts = val.split("|||", 1)
        name = parts[0].strip()
        team = parts[1].strip() if len(parts) > 1 else ""
        return f"?name={urllib.parse.quote(name)}&team={urllib.parse.quote(team)}"
    return no_update


@callback(Output("jugador-content", "children"),
          Input("jugador-loc", "search"))
def render_player(search):
    # URL es la única fuente de verdad — siempre actualizada tanto desde
    # Scouting (navegación) como desde el dropdown (_sync_url_from_dropdown)
    name, team = "", ""
    if search and search.startswith("?"):
        params = dict(urllib.parse.parse_qsl(search[1:]))
        name = params.get("name", "")
        team = params.get("team", "")
    if not name:
        return html.Div(
            "Usa el buscador de arriba o selecciona un jugador desde Scouting.",
            style={"color": "#6B7280", "fontSize": "13px", "padding": "20px"},
        )
    key = f"{name}|{team}"
    ovs = _load_overrides()
    # Obtener opta_id para lookup de tm_id
    opta_id = params.get("id", "") if search and search.startswith("?") else ""
    if not opta_id:
        try:
            import pandas as pd
            enr = pd.read_parquet(PROC / "player_seasons_enriched.parquet",
                                  columns=["player_id_src", "name"])
            match = enr[enr["name"] == name]
            if not match.empty:
                opta_id = str(match.iloc[0]["player_id_src"])
        except Exception:
            pass
    try:
        tm_elem = _tm_strip(key, opta_id)
        detail = build_detail(name, team=team or None, extra_header_right=tm_elem)
    except Exception as exc:
        return dbc.Alert(f"No se pudo construir el perfil: {exc}", color="warning")
    fit_card = _fit_rayo_card(name)
    risk_card = _clause_risk_card(name, ovs)
    return html.Div([detail, fit_card, risk_card,
                     _notes_box(key, _load_notes(), ovs)])


@callback(Output("current-player", "data"),
          Input("jugador-loc", "search"))
def _track_player(search):
    # URL es la única fuente — siempre correcta
    if search and search.startswith("?"):
        import urllib.parse as _u
        pr = dict(_u.parse_qsl(search[1:]))
        if pr.get("name"):
            return {"name": pr["name"], "team": pr.get("team", "")}
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
    State("jugador-loc", "search"),
    prevent_initial_call=True,
)
def _download_pdf(n, search):
    if not n:
        return no_update, no_update, False, _PDF_BTN_DEFAULT, _BTN_STYLE_DEFAULT

    # URL es la única fuente — siempre refleja el jugador visible
    # (actualizada tanto por navegación como por _sync_url_from_dropdown)
    name, team = "", ""
    if search and search.startswith("?"):
        import urllib.parse as _up
        pr = dict(_up.parse_qsl(search[1:]))
        name = pr.get("name", "")
        team = pr.get("team", "")

    if not name:
        err = html.Div([
            html.I(className="ti ti-alert-circle",
                   style={"color": "#F59E0B", "marginRight": "6px"}),
            html.Span("Selecciona un jugador primero",
                      style={"fontSize": "11px", "color": "#92400E"}),
        ], style={"display": "flex", "alignItems": "center"})
        return no_update, err, False, _PDF_BTN_DEFAULT, _BTN_STYLE_DEFAULT

    try:
        from src.reports.player_dossier import build_player_dossier
        fname, data = build_player_dossier(name, team=team or None)
        return dcc.send_bytes(data, fname), "", False, _PDF_BTN_DEFAULT, _BTN_STYLE_DEFAULT
    except BaseException as exc:
        import traceback
        traceback.print_exc()
        err_msg = html.Div([
            html.I(className="ti ti-alert-circle",
                   style={"color": "#B8960C", "marginRight": "6px"}),
            html.Span(f"Error generando PDF: {exc}",
                      style={"fontSize": "11px", "color": "#B8960C"}),
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


@callback(
    Output("tm-fetch-status", "children"),
    Output("tm-reload-trigger", "data"),
    Input("btn-fetch-tm", "n_clicks"),
    State("tm-id-input", "value"),
    State("player-note-key", "data"),
    State("player-opta-id", "data"),
    prevent_initial_call=True,
)
def fetch_from_tm(n, tm_id_raw, key, opta_id):
    """Guarda el tm_id y obtiene datos frescos de la API de TM."""
    if not n or not key:
        return no_update, no_update
    tm_id = str(tm_id_raw or "").strip().replace(".0", "")
    if not tm_id.isdigit():
        return "ID invalido — debe ser un numero (ej. 258923)", no_update

    name = key.split("|")[0]

    # 1. Actualizar entity_map
    try:
        import pandas as pd
        from datetime import datetime, timezone
        entity_map_path = PROC / "player_entity_map.csv"
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        if entity_map_path.exists():
            em = pd.read_csv(entity_map_path)
        else:
            em = pd.DataFrame(columns=["opta_id", "tm_id", "match_type", "match_confidence", "updated_at"])
        if opta_id:
            mask = em["opta_id"].astype(str) == str(opta_id)
            if mask.any():
                em.loc[mask, "tm_id"] = tm_id
                em.loc[mask, "match_type"] = "manual"
                em.loc[mask, "updated_at"] = now
            else:
                em = pd.concat([em, pd.DataFrame([{
                    "opta_id": opta_id, "tm_id": tm_id,
                    "match_type": "manual", "match_confidence": 1.0, "updated_at": now,
                }])], ignore_index=True)
            em.to_csv(entity_map_path, index=False)
    except Exception as e:
        return f"Error actualizando entity_map: {e}", no_update

    # 2. Llamar API TM alpha
    try:
        import requests
        api_url = "https://tmapi-alpha.transfermarkt.technology/player/{}".format(tm_id)
        r = requests.get(api_url, headers={"Accept": "application/json",
                         "User-Agent": "RayoScoutingTool/1.0"}, timeout=12)
        if r.status_code == 404:
            return "tm_id guardado, pero no encontrado en la API de TM (ID incorrecto?)", no_update
        if r.status_code != 200:
            return "tm_id guardado. API respondio {}, reintenta mas tarde".format(r.status_code), no_update
        data = r.json()
        d = data.get("data", data)
    except Exception as e:
        return "tm_id guardado. Error conectando con TM API: {}".format(str(e)[:60]), no_update

    # 3. Parsear respuesta
    def _safe(fn):
        try: return fn()
        except Exception: return None

    mv    = _safe(lambda: float(d["marketValueDetails"]["current"]["value"]))
    con   = _safe(lambda: str(d["attributes"]["contractUntil"])[:10])
    foot  = _safe(lambda: d["attributes"]["preferredFoot"]["name"])
    h     = _safe(lambda: str(d["attributes"]["height"]))
    photo = _safe(lambda: d["portraitUrl"] if str(d.get("portraitUrl","")).startswith("http") else None)
    rc    = _safe(lambda: float(d["attributes"]["releaseClause"]))

    # 4. Actualizar overrides
    ov = _load_overrides()
    entry = ov.get(_norm(name), {})
    if mv:    entry["value_eur"] = mv
    if con:   entry["contract_until"] = con
    if foot:  entry["foot"] = foot
    if h:     entry["height"] = float(h)
    if photo: entry["photo_url"] = photo
    if rc:    entry["release_clause_eur"] = rc
    ov[_norm(name)] = entry
    _save_overrides(ov)

    # 5. Actualizar market_values.csv
    try:
        import pandas as pd
        mv_path = PROC.parent / "config" / "market_values.csv"
        mv_df = pd.read_csv(mv_path) if mv_path.exists() else pd.DataFrame()
        row_data = {"name": name, "tm_id": tm_id,
                    "market_value_eur": mv or "",
                    "contract_until": con or "",
                    "tm_photo_url": photo or ""}
        if not mv_df.empty and "name" in mv_df.columns:
            idx = mv_df[mv_df["name"].apply(_norm) == _norm(name)].index
            if not idx.empty:
                for col, val in row_data.items():
                    if col in mv_df.columns and val:
                        mv_df.loc[idx[0], col] = val
            else:
                mv_df = pd.concat([mv_df, pd.DataFrame([row_data])], ignore_index=True)
        else:
            mv_df = pd.DataFrame([row_data])
        mv_df.to_csv(mv_path, index=False)
    except Exception:
        pass

    # 6. Invalidar cache
    try:
        from src.utils.market import invalidate_cache
        invalidate_cache()
    except Exception:
        pass

    parts = []
    if mv:    parts.append("Valor: {:.1f}M EUR".format(mv / 1e6))
    if con:   parts.append("Contrato: {}".format(con))
    if photo: parts.append("Foto OK")
    msg = " · ".join(parts) if parts else "Datos guardados"
    return "Actualizando... {}".format(msg), 1


# ---------------------------------------------------------------------------
# Callback: guardar posicion lateral y tipo de rol
# ---------------------------------------------------------------------------
@callback(
    Output("lateral-status", "children"),
    Input("save-lateral", "n_clicks"),
    State("mkt-lateral-pos", "value"),
    State("mkt-role-type", "value"),
    State("player-note-key", "data"),
    prevent_initial_call=True,
)
def save_lateral(n_clicks, lateral_pos, role_type, key):
    if not key:
        return "Sin jugador cargado"
    ov = _load_overrides()
    entry = ov.get(_norm(key), {})
    if lateral_pos is not None:
        entry["lateral_pos"] = lateral_pos
    elif "lateral_pos" in entry:
        del entry["lateral_pos"]
    if role_type is not None:
        entry["role_type"] = role_type
    elif "role_type" in entry:
        del entry["role_type"]
    ov[_norm(key)] = entry
    _save_overrides(ov)
    return "Guardado correctamente"

# ---------------------------------------------------------------------------
# Clientside callback: recargar página tras actualizar TM
# ---------------------------------------------------------------------------
from dash import clientside_callback

clientside_callback(
    """
    function(trigger) {
        if (trigger) {
            setTimeout(function() { window.location.reload(); }, 800);
        }
        return '';
    }
    """,
    Output("tm-reload-dummy", "children"),
    Input("tm-reload-trigger", "data"),
    prevent_initial_call=True,
)
