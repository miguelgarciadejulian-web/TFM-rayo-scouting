# -*- coding: utf-8 -*-
"""
profile_card.py — Tarjeta compacta de perfil y encaje automático
================================================================

PROPÓSITO:
    Componente reutilizable que genera una tarjeta resumen con:
    - Rol primario del jugador (inferido automáticamente)
    - Score de encaje con la plantilla (player_fit.py)
    - Fortalezas y debilidades principales
    - Compatibilidad con el entrenador y la plantilla
    Se usa en múltiples páginas para dar un vistazo rápido al jugador.

FUNCIÓN PRINCIPAL:
    build_profile_card(name) → dbc.Card con información de perfil

DEPENDENCIAS:
    - src/profiling/player_profile.py (perfil automático)
    - src/fit/player_fit.py (encaje con plantilla + entrenador)
"""
from __future__ import annotations
import json
from functools import lru_cache
from pathlib import Path

import pandas as pd
from dash import html
import dash_bootstrap_components as dbc

from src.utils.config import settings
from src.profiling.player_profile import profile_single_player, ROLE_LABELS
from src.fit.player_fit import evaluate_player_fit

PROC = Path(settings()["paths"]["data_processed"])


@lru_cache(maxsize=1)
def _enriched():
    p = PROC / "player_seasons_enriched.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()


def _needs():
    p = PROC / "squad_profile.json"
    if p.exists():
        return json.load(open(p, encoding="utf-8")).get("needs", {})
    return {}


def _bar(label, v, color="#378ADD"):
    v = 0 if v is None else max(0, min(100, v))
    return html.Div([
        html.Span(label, style={"fontSize": "10px", "color": "#6B7280", "width": "150px",
                                "display": "inline-block"}),
        html.Div(style={"height": "7px", "background": "#F3F4F6", "borderRadius": "99px",
                        "flex": "1", "overflow": "hidden"},
                 children=html.Div(style={"height": "100%", "width": f"{v}%",
                                          "background": color, "borderRadius": "99px"})),
        html.Span(str(int(v)), style={"fontSize": "10px", "color": "#374151",
                  "marginLeft": "6px", "width": "26px", "textAlign": "right"}),
    ], style={"display": "flex", "alignItems": "center", "gap": "6px", "marginBottom": "5px"})


def player_profile_section(name, team=None, league=None, age=None, coach_style="Bloque medio / Equilibrado"):
    """Devuelve un componente Dash con el perfil automatico y el encaje, o un aviso."""
    enr = _enriched()
    if enr.empty:
        return html.Div()
    prof = profile_single_player(enr, name, team=team, league=league, age=age)
    if not prof or not prof.get("primary_role"):
        return html.Div([
            html.Span("Perfil automatico no disponible (sin datos Opta suficientes en el scope actual).",
                      style={"fontSize": "12px", "color": "#92400E"}),
        ], style={"background": "#FFFBEB", "border": "1px solid #FDE68A", "borderRadius": "10px",
                  "padding": "12px 14px", "marginTop": "12px"})

    needs = _needs()
    fit = evaluate_player_fit(prof, needs, coach_style)
    sec = " · ".join(prof.get("secondary_roles_labels", [])) or "—"

    return html.Div([
        dbc.Row([
            dbc.Col([
                html.P("Perfil generado automaticamente", style={"fontSize": "9px", "fontWeight": "700",
                       "color": "#9CA3AF", "textTransform": "uppercase", "letterSpacing": ".05em",
                       "marginBottom": "6px"}),
                html.H4(prof["primary_role_label"], style={"fontSize": "17px", "color": "#1A1A2E",
                        "margin": "0 0 2px"}),
                html.P(prof["style_label"], style={"fontSize": "12px", "color": "#1D4ED8",
                       "fontWeight": "600", "margin": "0 0 2px"}),
                html.P(f"Roles secundarios: {sec}", style={"fontSize": "11px", "color": "#6B7280",
                       "margin": "0 0 8px"}),
                html.Div([
                    html.Span(f"Confianza: {prof['confidence']}", style={"fontSize": "10px",
                        "background": "#F3F4F6", "borderRadius": "99px", "padding": "2px 8px",
                        "marginRight": "5px"}),
                    html.Span(f"Riesgo: {prof['risk_level']}", style={"fontSize": "10px",
                        "background": "#FEF3C7", "borderRadius": "99px", "padding": "2px 8px",
                        "marginRight": "5px"}),
                    html.Span(f"Potencial: {prof['potential']}", style={"fontSize": "10px",
                        "background": "#DBEAFE", "borderRadius": "99px", "padding": "2px 8px"}),
                ], style={"marginBottom": "10px"}),
                html.P("Fortalezas", style={"fontSize": "10px", "fontWeight": "700", "color": "#166534",
                       "margin": "0 0 4px"}),
                html.Div([html.Span(s, style={"fontSize": "10px", "background": "#F0FDF4",
                    "color": "#166534", "borderRadius": "6px", "padding": "3px 8px", "marginRight": "4px",
                    "marginBottom": "4px", "display": "inline-block"}) for s in prof["strengths"]] or
                    [html.Span("—", style={"fontSize": "11px", "color": "#9CA3AF"})]),
                html.P("Debilidades", style={"fontSize": "10px", "fontWeight": "700", "color": "#991B1B",
                       "margin": "8px 0 4px"}),
                html.Div([html.Span(s, style={"fontSize": "10px", "background": "#FEF2F2",
                    "color": "#991B1B", "borderRadius": "6px", "padding": "3px 8px", "marginRight": "4px",
                    "marginBottom": "4px", "display": "inline-block"}) for s in prof["weaknesses"]] or
                    [html.Span("—", style={"fontSize": "11px", "color": "#9CA3AF"})]),
            ], md=6),
            dbc.Col([
                html.P("Fit Rayo (automático)", style={"fontSize": "9px", "fontWeight": "700",
                       "color": "#9CA3AF", "textTransform": "uppercase", "letterSpacing": ".05em",
                       "marginBottom": "6px"}),
                html.Div([
                    html.Span(f"{fit['global_fit_10']}", style={"fontSize": "30px", "fontWeight": "700",
                              "color": "#B8960C", "lineHeight": "1"}),
                    html.Span("/10 encaje global", style={"fontSize": "12px", "color": "#6B7280",
                              "marginLeft": "6px"}),
                ], style={"marginBottom": "10px"}),
                _bar("Compatibilidad plantilla", fit["compatibilidad_plantilla"], "#10B981"),
                _bar("Compatibilidad entrenador", fit["compatibilidad_entrenador"], "#378ADD"),
                _bar("Valor estrategico", fit["valor_estrategico"], "#8B5CF6"),
                _bar("Impacto deportivo esperado", fit["impacto_deportivo"], "#F59E0B"),
                html.P(fit["compatibilidad_plantilla_txt"], style={"fontSize": "11px",
                       "color": "#374151", "marginTop": "8px", "fontStyle": "italic"}),
                html.P(f"Datos: {prof['team']} · {prof['season']} · {int(prof['minutes'] or 0)} min",
                       style={"fontSize": "10px", "color": "#9CA3AF", "marginTop": "4px"}),
            ], md=6),
        ]),
    ], style={"background": "#fff", "border": "1px solid #E5E7EB", "borderRadius": "12px",
              "padding": "18px 20px", "marginTop": "16px", "marginBottom": "8px"})
