# -*- coding: utf-8 -*-
"""
Decisiones deportivas - Rayo 2026/27.
Rankings AUTOMATICOS (fichar / vender / ceder / renovar) y recomendacion de
entrenador, derivados por reglas en src/fit/decisions.py y los perfiles
precalculados. Nada escrito a mano.
"""
from __future__ import annotations
import json
import sys
import yaml
from pathlib import Path

import dash
from dash import html, dcc, callback, Input, Output, clientside_callback, ClientsideFunction
import dash_bootstrap_components as dbc
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dashboard.components.criteria_block import criteria_accordion  # noqa: E402
from src.utils.config import settings  # noqa: E402
from src.utils.leagues import league_name as _league_name  # noqa: E402
from src.fit.decisions import squad_decisions  # noqa: E402
from src.profiling.player_profile import (  # noqa: E402
    rank_players_for_role, ROLE_LABELS, detect_latest_seasons, CURRENT_SEASONS,
)
from src.fit.renewal_engine import (  # noqa: E402
    load_and_analyze, RECOMMENDATION_LABELS, RECOMMENDATION_COLORS,
    RECOMMENDATION_ICONS,
)
import time

_ENRICHED_CACHE: dict = {"data": None, "t": 0.0}
_SQUAD_CACHE:    dict = {"data": None, "t": 0.0}
_COACHES_CACHE:  dict = {"data": None, "t": 0.0}
_SHORT_CACHE:    dict = {"data": None, "t": 0.0}
_FLAT_CACHE:     dict = {"data": None, "t": 0.0}
_FIT_SCORER_CACHE: dict = {}
_POS_OPT_CACHE: list = []
_CACHE_TTL = 120


def _get_fit_scorer():
    if "scorer" not in _FIT_SCORER_CACHE:
        try:
            from src.scouting.comparator import load_scorer
            club_yaml = PROC.parents[1] / "config" / "club_profile.yaml"
            with open(club_yaml, encoding="utf-8") as f:
                import yaml as _yaml_local
                club = _yaml_local.safe_load(f)
            squad = []
            for section in club.get("squad_2025_26", {}).values():
                if isinstance(section, list):
                    squad.extend(section)
            _FIT_SCORER_CACHE["scorer"] = load_scorer(PROC, squad)
        except Exception:
            _FIT_SCORER_CACHE["scorer"] = None
    return _FIT_SCORER_CACHE.get("scorer")


def _fit_scores_for(names: list[str], teams: list[str] | None = None) -> dict[str, dict]:
    """Fit Rayo completo — devuelve {name: {fit, rend, adn}} para cada jugador."""
    scorer = _get_fit_scorer()
    if not scorer or not names:
        return {}
    try:
        results = scorer.compare(names, player_teams=teams)
        return {r.name: {"fit": r.fit_score,
                         "rend": r.score_rendimiento,
                         "adn": r.score_adn_tactico} for r in results}
    except Exception:
        return {}


def _enriched():
    if _ENRICHED_CACHE["data"] is not None and time.time() - _ENRICHED_CACHE["t"] < _CACHE_TTL:
        return _ENRICHED_CACHE["data"]
    p = PROC / "player_seasons_enriched.parquet"
    data = pd.read_parquet(p) if p.exists() else pd.DataFrame()
    _ENRICHED_CACHE.update({"data": data, "t": time.time()})
    return data


def _season_options() -> list[dict]:
    _ORDER = {
        "2026": 7, "2025-2026": 6, "2025/2026": 6, "2025": 5,
        "2024-2025": 4, "2024": 4, "2023-2024": 3, "2023": 3,
        "2022-2023": 2, "2022": 1, "2021-2022": 1, "2021": 0,
    }
    enr = _enriched()
    if enr.empty:
        return [{"label": s, "value": s} for s in CURRENT_SEASONS]
    seasons = sorted(
        enr["season"].dropna().astype(str).unique(),
        key=lambda s: _ORDER.get(s, 0),
        reverse=True,
    )
    labels = {
        "2026": "2025/26 (cal. 2026)", "2025-2026": "2025/26",
        "2025/2026": "2025/26", "2025": "2024/25 (cal. 2025)",
        "2024-2025": "2024/25", "2024": "2023/24 (cal. 2024)",
        "2023-2024": "2023/24", "2023": "2022/23 (cal. 2023)",
    }
    return [{"label": labels.get(s, s), "value": s} for s in seasons]


ROLE_OPTIONS = [{"label": v, "value": k} for k, v in ROLE_LABELS.items()]

_LAT_ORDER = ["LI", "LD", "DC", "MC", "MI", "MD", "EI", "ED", "DL", "PO"]


def _pos_filter_options() -> list[dict]:
    """Opciones del filtro de posición — mismo sistema que scouting (lateral_pos)."""
    from src.utils.lateral_position import build_lateral_map, LATERAL_LABELS as _LL
    try:
        _enr_p    = PROC / "player_seasons_enriched.parquet"
        _master_p = PROC / "master_players.parquet"
        _lat = build_lateral_map(_enr_p, _master_p)
        present = set(_lat["lateral_pos"].dropna()) - {"?"}
    except Exception:
        present = set(_LAT_ORDER)
    opts = [{"label": "Todas las posiciones", "value": ""}]
    for k in _LAT_ORDER:
        if k in present:
            opts.append({"label": _LL.get(k, k), "value": k})
    return opts
LEAGUE_OPTIONS = [
    {"label": "LaLiga", "value": "Spain_Primera_Division"},
    {"label": "Segunda", "value": "Spain_Segunda_Division"},
    {"label": "Ligue 1", "value": "France_Ligue_1"},
    {"label": "Primeira (POR)", "value": "Portugal_Primeira_Liga"},
    {"label": "Eredivisie", "value": "Netherlands_Eredivisie"},
    {"label": "Belgica", "value": "Belgium_First_Division_A"},
    {"label": "Argentina", "value": "Argentina_Liga_Profesional"},
    {"label": "Liga MX", "value": "Mexico_Liga_MX"},
]

dash.register_page(__name__, path="/decisiones", name="Decisiones")
PROC = Path(settings()["paths"]["data_processed"])

COLS = {
    "fichar":  ("Fichar", "ti-plus", "#166534", "#F0FDF4"),
    "renovar": ("Renovar", "ti-refresh", "#1D4ED8", "#EFF6FF"),
    "vender":  ("Vender", "ti-cash", "#9A3412", "#FFF7ED"),
    "ceder":   ("Ceder", "ti-arrow-right", "#854D0E", "#FFFBEB"),
}


def _load_squad():
    if _SQUAD_CACHE["data"] is not None and time.time() - _SQUAD_CACHE["t"] < _CACHE_TTL:
        return _SQUAD_CACHE["data"]
    p = PROC / "squad_profile.json"
    data = json.load(open(p, encoding="utf-8")) if p.exists() else {"squad": [], "needs": {}}
    _SQUAD_CACHE.update({"data": data, "t": time.time()})
    return data


def _flatten_squad() -> list[dict]:
    if _FLAT_CACHE["data"] is not None and time.time() - _FLAT_CACHE["t"] < _CACHE_TTL:
        return _FLAT_CACHE["data"]
    config_dir = Path(__file__).resolve().parents[2] / "config"
    yaml_path  = config_dir / "club_profile.yaml"
    if not yaml_path.exists():
        return []
    try:
        raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        players = []
        for group_players in raw.get("squad_2025_26", {}).values():
            if isinstance(group_players, list):
                for p in group_players:
                    if isinstance(p, dict):
                        players.append(p)
        _FLAT_CACHE.update({"data": players, "t": time.time()})
        return players
    except Exception:
        return []


def _load_coaches():
    if _COACHES_CACHE["data"] is not None and time.time() - _COACHES_CACHE["t"] < _CACHE_TTL:
        return _COACHES_CACHE["data"]
    p = PROC / "coach_profiles.json"
    data = json.load(open(p, encoding="utf-8")) if p.exists() else []
    _COACHES_CACHE.update({"data": data, "t": time.time()})
    return data


def _load_shortlists():
    if _SHORT_CACHE["data"] is not None and time.time() - _SHORT_CACHE["t"] < _CACHE_TTL:
        return _SHORT_CACHE["data"]
    p = PROC / "signing_shortlists.json"
    try:
        data = json.load(open(p, encoding="utf-8")) if p.exists() else {}
    except Exception:
        data = {}
    _SHORT_CACHE.update({"data": data, "t": time.time()})
    return data


def _item_row(it):
    title = it.get("name") or it.get("role")
    meta = []
    if it.get("role") and it.get("name"):
        meta.append(it["role"])
    if it.get("age"):
        meta.append(f"{int(it['age'])} anos")
    if it.get("priority"):
        meta.append(f"prioridad {it['priority']}")
    if it.get("market_value"):
        meta.append(f"{it['market_value']/1e6:.1f}M EUR")
    return html.Div([
        html.Div([
            html.Strong(title, style={"fontSize": "12px", "color": "#1A1A2E"}),
            html.Span("  " + " · ".join(meta), style={"fontSize": "10px", "color": "#6B7280"}),
        ]),
    ], style={"padding": "8px 0", "borderBottom": "1px solid #F3F4F6"})


def _candidate_chips(cands, fit_map: dict | None = None):
    if not cands:
        return html.Span()
    if fit_map:
        cands = sorted(cands, key=lambda c: (fit_map.get(c["name"], {}).get("fit", 0)
                                             if isinstance(fit_map.get(c["name"]), dict)
                                             else fit_map.get(c["name"], 0)), reverse=True)
    chips = []
    for c in cands[:6]:
        name = c["name"]
        fm = fit_map.get(name) if fit_map else None
        fit_val = fm["fit"] if isinstance(fm, dict) else fm
        score_str = f"{fit_val:.0f}" if fit_val is not None else f"{c.get('role_score', 0):.0f}"
        chips.append(html.Span(
            f"{name} ({score_str})",
            title=f"{c.get('team', '')} · {c.get('season', '')} · Fit Rayo {score_str}",
            style={"fontSize": "10px", "background": "#F0FDF4", "color": "#166534",
                   "borderRadius": "6px", "padding": "2px 7px", "marginRight": "4px",
                   "marginBottom": "4px", "display": "inline-block"},
        ))
    return html.Div([
        html.Span("Candidatos (Fit Rayo): ", style={"fontSize": "9px", "color": "#9CA3AF", "fontWeight": "700"}),
        *chips,
    ], style={"marginTop": "4px"})


def _fichar_row(it, shortlists):
    cands = shortlists.get(it.get("role"), [])
    names = [c["name"] for c in cands] if cands else []
    fit_map = _fit_scores_for(names) if names else {}

    cands_sorted = sorted(cands, key=lambda c: (fit_map.get(c["name"], {}).get("fit", 0)
                                                if isinstance(fit_map.get(c["name"]), dict)
                                                else fit_map.get(c["name"], 0)), reverse=True)

    return html.Div([
        html.Div([
            html.Strong(it.get("role"), style={"fontSize": "12px", "color": "#1A1A2E"}),
            html.Span(f"  prioridad {it.get('priority','')}",
                      style={"fontSize": "10px", "color": "#6B7280"}),
        ]),
        _candidate_chips(cands_sorted, fit_map=fit_map),
    ], style={"padding": "8px 0", "borderBottom": "1px solid #F3F4F6"})


def _decision_col(key, items, shortlists=None):
    label, icon, fg, bg = COLS[key]
    if key == "fichar":
        body = [_fichar_row(it, shortlists or {}) for it in items]
    else:
        body = [_item_row(it) for it in items]
    return dbc.Col(html.Div([
        html.Div([
            html.I(className=f"ti {icon}", style={"color": fg, "fontSize": "15px", "marginRight": "7px"}),
            html.Span(label, style={"fontSize": "13px", "fontWeight": "700", "color": fg}),
            html.Span(f" {len(items)}", style={"fontSize": "11px", "color": "#9CA3AF", "marginLeft": "4px"}),
        ], style={"marginBottom": "8px", "borderBottom": f"2px solid {fg}", "paddingBottom": "6px"}),
        html.Div(body or [html.P("Sin recomendaciones", style={"fontSize": "11px", "color": "#9CA3AF"})]),
    ], style={"background": "#fff", "border": "1px solid #E5E7EB", "borderRadius": "10px",
              "padding": "14px 16px", "height": "100%"}), md=3)


def _criteria_badge(text, color="#1D4ED8", bg="#EFF6FF"):
    return html.Div([
        html.I(className="ti ti-info-circle",
               style={"color": color, "marginRight": "6px", "fontSize": "13px"}),
        html.Span(text, style={"fontSize": "11px", "color": "#374151"}),
    ], style={"background": bg, "border": f"1px solid {color}30",
              "borderRadius": "8px", "padding": "8px 12px",
              "marginBottom": "14px", "display": "flex", "alignItems": "flex-start"})



def _load_needs():
    p = PROC / "squad_profile.json"
    if p.exists():
        return json.load(open(p, encoding="utf-8")).get("needs", {})
    return {}


def _needs_panel() -> html.Div:
    """Panel de necesidades de plantilla visible en la pestaña Fichar de Decisiones."""
    needs = _load_needs()
    if not needs:
        return html.Span()

    squad_p = PROC / "squad_profile.json"
    n_total = 0
    if squad_p.exists():
        try:
            n_total = len(json.load(open(squad_p, encoding="utf-8")).get("squad", []))
        except Exception:
            pass

    cap        = needs.get("squad_cap", 25)
    n_profiled = needs.get("n_profiled", n_total)
    missing    = needs.get("missing", [])
    reinforce  = needs.get("reinforce", [])
    aging      = needs.get("aging_or_expiring", [])
    formation  = needs.get("formation_used", "4-2-3-1")
    slots_free = cap - n_total

    def _chip(label, bg, fg, icon=""):
        return html.Span(
            [html.Span(icon + " ", style={"marginRight": "2px"}) if icon else "", label],
            style={"fontSize": "10px", "fontWeight": "600", "padding": "2px 8px",
                   "borderRadius": "99px", "background": bg, "color": fg,
                   "marginRight": "4px", "marginBottom": "4px", "display": "inline-block"},
        )

    pct_full = min(n_total / cap * 100, 100)
    bar_color = "#DC2626" if slots_free > 3 else "#F59E0B" if slots_free > 0 else "#10B981"

    return html.Div([
        html.Div([
            html.Div([
                html.I(className="ti ti-users-group",
                       style={"fontSize": "14px", "color": "#B8960C", "marginRight": "6px"}),
                html.Strong("Plantilla 2026/27 \u2014 an\u00e1lisis de necesidades",
                            style={"fontSize": "12px", "color": "#1A1A2E"}),
                html.Span(f"  formaci\u00f3n base: {formation}",
                          style={"fontSize": "10px", "color": "#9CA3AF", "marginLeft": "8px"}),
            ], style={"display": "flex", "alignItems": "center", "marginBottom": "6px"}),

            html.Div([
                html.Div([
                    html.Div(style={"height": "6px", "borderRadius": "99px",
                                    "width": f"{pct_full:.0f}%", "background": bar_color}),
                ], style={"flex": "1", "height": "6px", "background": "#F3F4F6",
                          "borderRadius": "99px", "overflow": "hidden", "alignSelf": "center"}),
                html.Span(
                    f"{n_total} / {cap} jugadores  \u00b7  {slots_free} hueco{'s' if slots_free != 1 else ''} libre{'s' if slots_free != 1 else ''}",
                    style={"fontSize": "11px", "fontWeight": "700",
                           "color": bar_color, "marginLeft": "10px", "whiteSpace": "nowrap"},
                ),
            ], style={"display": "flex", "alignItems": "center", "gap": "8px",
                      "marginBottom": "10px"}),
        ]),

        dbc.Row([
            dbc.Col([
                html.Div("Sin cobertura",
                         style={"fontSize": "10px", "fontWeight": "700", "color": "#991B1B",
                                "marginBottom": "4px"}),
                html.Div(
                    [_chip(r, "#FEE2E2", "#991B1B", "\u25cf") for r in missing]
                    or [html.Span("Ninguna", style={"fontSize": "10px", "color": "#9CA3AF"})],
                    style={"display": "flex", "flexWrap": "wrap"},
                ),
            ], md=4),
            dbc.Col([
                html.Div("A reforzar",
                         style={"fontSize": "10px", "fontWeight": "700", "color": "#92400E",
                                "marginBottom": "4px"}),
                html.Div(
                    [_chip(r, "#FEF3C7", "#92400E", "\u25b2") for r in reinforce]
                    or [html.Span("Ninguna", style={"fontSize": "10px", "color": "#9CA3AF"})],
                    style={"display": "flex", "flexWrap": "wrap"},
                ),
            ], md=4),
            dbc.Col([
                html.Div("Veteranos / fin contrato 2026",
                         style={"fontSize": "10px", "fontWeight": "700", "color": "#1E40AF",
                                "marginBottom": "4px"}),
                html.Div(
                    [_chip(
                        f"{a['name'].split()[-1]} ({a.get('role_label', a.get('role', '?'))})",
                        "#EFF6FF", "#1E40AF"
                    ) for a in aging[:5]]
                    or [html.Span("Ninguno", style={"fontSize": "10px", "color": "#9CA3AF"})],
                    style={"display": "flex", "flexWrap": "wrap"},
                ),
            ], md=4),
        ], className="g-2"),

        html.P(
            f"Plantilla objetivo ({cap} jugadores) derivada autom\u00e1ticamente de la formaci\u00f3n base. "
            "La compatibilidad de cada t\u00e9cnico se pondera contra estas carencias.",
            style={"fontSize": "9px", "color": "#9CA3AF", "margin": "8px 0 0",
                   "fontStyle": "italic"},
        ),
    ], style={
        "background": "#FFFBEB", "border": "1px solid #FDE68A", "borderRadius": "10px",
        "padding": "12px 16px", "marginBottom": "14px",
    })


def layout(**_params):
    data = _load_squad()
    dec = squad_decisions(data.get("squad", []), data.get("needs", {}))
    coaches = _load_coaches()
    top3 = coaches[:3]
    needs = data.get("needs", {})

    tab_fichajes = html.Div([
        _criteria_badge(
            "Criterios aplicados: encaje tactico (presion, posesion, verticalidad) · "
            "encaje economico (valor de mercado vs presupuesto) · riesgo contractual "
            "(duracion + clausula). Candidatos generados automaticamente por rol."
        ),
        _needs_panel(),

        html.Div([
            html.Div([
                html.I(className="ti ti-search",
                       style={"fontSize":"14px","color":"#F59E0B","marginRight":"7px"}),
                html.Span("EXPLORADOR DE CANDIDATOS", style={"fontSize":"9px","fontWeight":"700",
                    "color":"#F59E0B","letterSpacing":".10em"}),
            ], style={"marginBottom":"10px","display":"flex","alignItems":"center"}),
            html.P("Elige un perfil y las ligas y obtén el ranking de candidatos al instante.",
                   style={"fontSize": "11px", "color": "#6B7280", "marginBottom": "10px"}),
            dbc.Row([
                dbc.Col([html.Span("Perfil / necesidad", className="filter-label"),
                    dcc.Dropdown(ROLE_OPTIONS, value="central_dominador", id="exp-role",
                                 clearable=False)], md=4),
                dbc.Col([html.Span("Ligas", className="filter-label"),
                    dcc.Dropdown(LEAGUE_OPTIONS, multi=True, id="exp-leagues",
                                 value=["Spain_Primera_Division", "Spain_Segunda_Division"],
                                 placeholder="Todas")], md=5),
                dbc.Col([html.Span("Minutos min.", className="filter-label"),
                    html.Div(dcc.Slider(300, 2500, 100, value=900, id="exp-min",
                               marks={300:"300", 900:"900", 1500:"1.5k", 2500:"2.5k"},
                               tooltip={"placement": "bottom", "always_visible": False},
                               updatemode="mouseup"),
                             className="slider-modern")], md=3),
            ], className="g-2"),
            dbc.Row([

                dbc.Col([html.Span("Valor max (M€) — Rayo ≤ 15M€", className="filter-label"),
                    html.Div(dcc.Slider(0, 200, 5, value=15, id="exp-maxval",
                               marks={0:"0", 15:"15M", 30:"30", 50:"50", 100:"100", 200:"200+"},
                               tooltip={"placement": "bottom", "always_visible": False},
                               updatemode="mouseup"),
                             className="slider-modern")], md=4),
                dbc.Col(dcc.Checklist(
                    options=[{"label": "  Excluir grandes clubes", "value": "big"},
                             {"label": "  Solo acaban contrato 2026", "value": "exp"}],
                    value=["big"], id="exp-flags", inline=True,
                    style={"fontSize": "12px", "marginTop": "18px"}), md=5),
            ], className="g-2", style={"marginTop": "4px"}),
            dbc.Row([
                dbc.Col([html.Span("Edad max.", className="filter-label"),
                    html.Div(dcc.Slider(18, 38, 1, value=32, id="exp-maxage",
                               marks={18:"18", 22:"22", 25:"25", 28:"28", 30:"30", 33:"33", 38:"38"},
                               tooltip={"placement": "bottom", "always_visible": False},
                               updatemode="mouseup"),
                             className="slider-modern")], md=4),
                dbc.Col([html.Span("Contrato restante max (años)", className="filter-label"),
                    html.Div(dcc.Slider(0, 6, 1, value=6, id="exp-maxcontract",
                               marks={0:"libre", 1:"1", 2:"2", 3:"3", 4:"4", 5:"5", 6:"∞"},
                               tooltip={"placement": "bottom", "always_visible": False},
                               updatemode="mouseup"),
                             className="slider-modern")], md=5),
            ], className="g-2", style={"marginTop": "4px"}),
            dbc.Row([
                dbc.Col([html.Span("Posición", className="filter-label"),
                    dcc.Dropdown(
                        options=_pos_filter_options(),
                        value="", id="exp-pos", clearable=False,
                    )], md=4),
                dbc.Col([html.Span("Ordenar por", className="filter-label"),
                    dcc.Dropdown(
                        options=[
                            {"label": "Fit Rayo", "value": "fit"},
                            {"label": "Rendimiento", "value": "rend"},
                            {"label": "ADN Táctico", "value": "adn"},
                        ],
                        value="fit", id="exp-sort", clearable=False,
                    )], md=3),
            ], className="g-2", style={"marginTop": "4px"}),

            html.Div(id="exp-results", style={"marginTop": "12px"}),
        ], style={"background": "#fff", "border": "1px solid #E5E7EB",
                  "borderRadius": "12px", "padding": "18px 20px"}),
    ])

    tab_renovaciones = html.Div([
        _criteria_badge(
            "Criterios de renovacion: score 0-100 ponderado sobre rendimiento deportivo "
            "reciente + valor de mercado + edad del jugador + duracion de contrato restante. "
            "Umbrales: Renovar (>=70) · Negociar (50-70) · Valorar salida (35-50) · No renovar (<35)."
        ),
        html.Div([
            html.I(className="ti ti-contract", style={"fontSize": "18px", "color": "#B8960C",
                   "marginRight": "10px", "verticalAlign": "middle"}),
            html.Span("Sistema de decision de renovaciones",
                      style={"fontSize": "14px", "fontWeight": "700", "color": "#1A1A2E"}),
        ], style={"display": "inline-flex", "alignItems": "center", "marginBottom": "8px"}),
        html.P("Analisis automatico de jugadores con contrato proximo a vencer. "
               "Score 0-100 · 5 recomendaciones · confianza y argumentacion.",
               style={"fontSize": "11px", "color": "#6B7280", "marginBottom": "12px"}),
        dbc.Row([
            dbc.Col([
                html.Span("Horizonte temporal", className="filter-label"),
                dcc.Dropdown(
                    options=[
                        {"label": "Contratos que vencen en <= 6 meses",  "value": 6},
                        {"label": "Contratos que vencen en <= 12 meses", "value": 12},
                        {"label": "Contratos que vencen en <= 18 meses", "value": 18},
                        {"label": "Contratos que vencen en <= 24 meses", "value": 24},
                    ],
                    value=18, clearable=False, id="renewal-horizon",
                    style={"fontSize": "12px"},
                ),
            ], md=4),
            dbc.Col(
                html.Div(id="renewal-summary-badge",
                         style={"fontSize": "11px", "color": "#6B7280", "marginTop": "24px"}),
                md=8,
            ),
        ], className="g-2"),
        dcc.Loading(html.Div(id="renewal-results", style={"marginTop": "16px"}),
                    type="dot", color="#FFD600"),
    ], style={"background": "#fff", "border": "1px solid #E5E7EB",
              "borderRadius": "12px", "padding": "18px 20px"})

    tab_entrenadores = html.Div([
        _criteria_badge(
            "Criterios de seleccion de entrenador: compatibilidad tactica (presion, posesion, "
            "verticalidad vs ADN del Rayo) · ajuste presupuestario (salario estimado) · "
            "experiencia en LaLiga · disponibilidad (libre vs con contrato)."
        ),
        html.P("Top candidatos al banquillo (encaje calculado automaticamente)",
               style={"fontSize": "10px", "fontWeight": "700", "color": "#9CA3AF",
                      "textTransform": "uppercase", "letterSpacing": ".05em", "marginBottom": "10px"}),
        dbc.Row([
            dbc.Col(html.Div([
                html.Div([
                    html.Strong(c["name"], style={"fontSize": "13px"}),
                    html.Span(f"{c['evaluation'].get('score_10')}/10",
                              style={"float": "right", "fontWeight": "700", "color": "#B8960C"}),
                ]),
                html.P(c.get("style_main", ""), style={"fontSize": "11px", "color": "#1D4ED8",
                       "margin": "2px 0"}),
                html.P(f"{c.get('laliga_seasons',0)} temp. LaLiga · "
                       f"{'Libre' if c.get('available') else 'Con equipo'}",
                       style={"fontSize": "10px", "color": "#6B7280", "margin": "0"}),
            ], style={"background": "#fff",
                      "border": f"2px solid {'#166534' if i==0 else '#E5E7EB'}",
                      "borderRadius": "10px", "padding": "12px 14px"}), md=4)
            for i, c in enumerate(top3)
        ], className="g-2"),
        html.Div([
            html.I(className="ti ti-external-link",
                   style={"marginRight": "6px", "fontSize": "12px"}),
            html.A("Ver analisis completo de entrenadores →", href="/entrenadores",
                   style={"fontSize": "12px", "color": "#1D4ED8", "textDecoration": "none"}),
        ], style={"marginTop": "14px"}),
    ], style={"background": "#fff", "border": "1px solid #E5E7EB",
              "borderRadius": "12px", "padding": "18px 20px"})

    n_fichar   = len(dec.get("fichar", []))
    n_renovar  = sum(1 for p in dec.get("renovar", []) if p.get("score",100) < 70)
    n_vender   = len(dec.get("vender", []))

    _tab_label = {"fontWeight":"700","fontSize":"12px"}
    _tab_sel   = {"fontWeight":"700","fontSize":"12px","color":"#F59E0B",
                  "borderBottom":"2px solid #F59E0B"}

    return html.Div([

        # ── Hero ──────────────────────────────────────────────────────────────
        html.Div([
            html.Div([
                html.Div([html.I(className="ti ti-clipboard-check",
                           style={"fontSize":"26px","color":"#fff"})],
                    style={"background":"rgba(227,6,19,.20)","borderRadius":"12px",
                           "padding":"10px","marginRight":"18px","flexShrink":"0",
                           "border":"1px solid rgba(227,6,19,.30)"}),
                html.Div([
                    html.Div("PLANIFICACIÓN DEPORTIVA", style={"fontSize":"9px","fontWeight":"700",
                        "color":"rgba(255,255,255,.45)","letterSpacing":".14em","marginBottom":"3px"}),
                    html.H1("Decisiones Deportivas", style={"fontSize":"22px","fontWeight":"900",
                        "color":"#fff","margin":"0 0 2px","letterSpacing":"-.02em"}),
                    html.Div("Rankings automáticos 2026/27 derivados de datos reales",
                        style={"fontSize":"10.5px","color":"rgba(255,255,255,.45)"}),
                ]),
            ], style={"display":"flex","alignItems":"center","flex":"1"}),
            html.Div([
                *[html.Div([
                    html.Div(v, style={"fontSize":"22px","fontWeight":"900","color":"#fff","lineHeight":"1"}),
                    html.Div(l, style={"fontSize":"9px","color":"rgba(255,255,255,.45)","fontWeight":"600","marginTop":"2px"}),
                ], style={"textAlign":"center","padding":"0 16px","borderRight":s})
                  for v,l,s in [
                    (str(n_fichar), "fichas urgentes", "1px solid rgba(255,255,255,.12)"),
                    (str(n_renovar), "renovaciones críticas", "1px solid rgba(255,255,255,.12)"),
                    (str(n_vender), "candidatos salida", "none"),
                ]],
            ], style={"display":"flex","alignItems":"center","flexShrink":"0"}),
        ], style={"background":"linear-gradient(135deg,#0A0B0E 0%,#1E2028 60%,#141519 100%)",
                  "borderRadius":"18px","padding":"20px 26px","marginBottom":"18px",
                  "display":"flex","justifyContent":"space-between","alignItems":"center",
                  "boxShadow":"0 8px 32px rgba(0,0,0,.28)","borderLeft":"4px solid #E30613"}),

        dbc.Tabs([
            dbc.Tab(tab_fichajes,     label="🎯  Fichajes",     tab_id="tab-fichajes",
                    label_style=_tab_label),
            dbc.Tab(tab_renovaciones, label="📋  Renovaciones",  tab_id="tab-renovaciones",
                    label_style=_tab_label),
            dbc.Tab(tab_entrenadores, label="🧑‍🏫  Entrenadores", tab_id="tab-entrenadores",
                    label_style=_tab_label),
        ], active_tab="tab-fichajes", style={"marginBottom":"16px",
            "background":"#fff","borderRadius":"14px","border":"1px solid #E5E7EB",
            "padding":"4px","boxShadow":"0 2px 8px rgba(0,0,0,.05)"}),
    ])


def _fmt_val(v):
    if v is None or pd.isna(v):
        return "n/d"
    v = float(v)
    return f"{v/1e6:.0f}M" if v >= 1e6 else f"{v/1e3:.0f}K"


_SALARY_CFG_CACHE: dict = {}


def _load_salary_cfg() -> dict:
    """Carga salary_estimates.yaml (cacheado en memoria)."""
    if _SALARY_CFG_CACHE:
        return _SALARY_CFG_CACHE
    try:
        yaml_path = PROC.parents[1] / "config" / "salary_estimates.yaml"
        with open(yaml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        _SALARY_CFG_CACHE.update(data or {})
    except Exception:
        pass
    return _SALARY_CFG_CACHE


def _est_salary(market_value_eur, league: str = "", minutes: float = 0,
                age: int = 25, position: str = "", team: str = "") -> str:
    """
    Estimación salarial bruta anual desde salary_estimates.yaml.

    Método:
      base = max(floor, min(top, mv × ratio_liga))
      × multiplicador_club (Real Madrid, Barça, etc.)
      × factor_titularidad (minutos jugados)
      × factor_edad (pico 24-28, penalización veteranos/jóvenes)

    Referencia: FIFPRO Global Employment Report 2023 + LaLiga Economic Report 2024.
    """
    try:
        mv = float(market_value_eur or 0)
        if mv <= 0:
            return "n/d"

        cfg = _load_salary_cfg()
        leagues_cfg = cfg.get("leagues", {})

        # ── 1. Configuración de liga ──
        lc = None
        league_l = str(league).lower()
        for k, v in leagues_cfg.items():
            if k.lower() in league_l or league_l in k.lower():
                lc = v
                break
        if lc is None:
            lc = leagues_cfg.get("default", {
                "floor_eur": 60000, "top_eur": 1000000, "ratio_of_mv": 0.09
            })

        floor_s = float(lc.get("floor_eur", 60000))
        top_s   = float(lc.get("top_eur", 1000000))
        ratio   = float(lc.get("ratio_of_mv", 0.09))

        # ── 2. Base salarial clampeada al rango de la liga ──
        base = max(floor_s, min(top_s, mv * ratio))

        # ── 3. Multiplicador de club ──
        club_mults = cfg.get("club_multipliers", {})
        club_mult = 1.0
        if team:
            team_l = str(team).lower()
            for club, mult in club_mults.items():
                if club.lower() in team_l or team_l in club.lower():
                    club_mult = float(mult)
                    break

        # ── 4. Factor de titularidad (minutos) ──
        mins = float(minutes or 0)
        if mins >= 2500:
            min_mult = 1.12
        elif mins >= 1800:
            min_mult = 1.05
        elif mins >= 900:
            min_mult = 0.95
        elif mins >= 450:
            min_mult = 0.85
        else:
            min_mult = 0.75

        # ── 5. Factor de edad ──
        age_i = int(float(age or 25))
        if 24 <= age_i <= 28:
            age_mult = 1.06
        elif 22 <= age_i <= 23 or 29 <= age_i <= 30:
            age_mult = 1.00
        elif age_i <= 21:
            age_mult = 0.88
        elif 31 <= age_i <= 33:
            age_mult = 0.92
        else:
            age_mult = 0.82

        sal = base * club_mult * min_mult * age_mult
        if sal >= 1_000_000:
            return f"~{sal/1e6:.1f}M€/año"
        return f"~{sal/1e3:.0f}K€/año"
    except (TypeError, ValueError):
        return "n/d"




# Lateral filter passed to rank_players_for_role (DEF only; others filtered post-ranking)
_POS_LATERAL = {"LI": "LI", "LD": "LD", "DC": "DC",
                "MC": "MC", "MI": "MI", "MD": "MD",
                "EI": "EI", "ED": "ED", "DL": "DL", "PO": "PO"}

_LATERAL_MAP_CACHE: dict = {}


def _get_lateral_map():
    """Devuelve (lat_dict, role_type_dict) cacheados."""
    if "data" in _LATERAL_MAP_CACHE:
        return _LATERAL_MAP_CACHE["data"]
    try:
        from src.utils.lateral_position import build_lateral_map
        _enr_p    = PROC / "player_seasons_enriched.parquet"
        _master_p = PROC / "master_players.parquet"
        _lat = build_lateral_map(_enr_p, _master_p)
        lat_d = dict(zip(_lat["name"], _lat["lateral_pos"]))
        rt_d  = dict(zip(_lat["name"], _lat["role_type"]))
    except Exception:
        lat_d, rt_d = {}, {}
    _LATERAL_MAP_CACHE["data"] = (lat_d, rt_d)
    return lat_d, rt_d


# ── Clientside: limpiar resultados al cambiar filtro (evita ver datos viejos) ──
clientside_callback(
    """function() { return "⏳ Cargando candidatos…"; }""",
    Output("exp-results", "children", allow_duplicate=True),
    Input("exp-role", "value"), Input("exp-leagues", "value"), Input("exp-min", "value"),
    Input("exp-maxval", "value"), Input("exp-flags", "value"),
    Input("exp-maxage", "value"), Input("exp-maxcontract", "value"),
    Input("exp-pos", "value"), Input("exp-sort", "value"),
    prevent_initial_call=True,
)


@callback(Output("exp-results", "children"),
          Input("exp-role", "value"), Input("exp-leagues", "value"), Input("exp-min", "value"),
          Input("exp-maxval", "value"), Input("exp-flags", "value"),
          Input("exp-maxage", "value"), Input("exp-maxcontract", "value"),
          Input("exp-pos", "value"), Input("exp-sort", "value"))
def _explore(role, leagues, min_min, maxval, flags, max_age, max_contract, pos_filter, sort_by):
    enr = _enriched()
    if enr.empty:
        return html.P("Sin datos enriquecidos.", style={"fontSize": "12px", "color": "#9CA3AF"})
    flags = flags or []
    max_value_eur = None if (maxval is None or maxval >= 200) else maxval * 1e6
    seasons_filter = CURRENT_SEASONS  # 2026 + 2025-2026: todas las ligas actuales
    # Lateral filter: passed to rank_players_for_role for DEF (LI/LD/DC);
    # for MID/FWD/GK positions lateral_filter is ignored by rank_players_for_role
    # and applied post-ranking via lateral map.
    _lat_f = _POS_LATERAL.get(pos_filter or "", None) if pos_filter in ("LI", "LD", "DC") else None
    rk = rank_players_for_role(enr, role, top_n=200, min_minutes=int(min_min or 900),
                               leagues=leagues or None, seasons=seasons_filter,
                               max_value_eur=max_value_eur,
                               exclude_big_clubs=("big" in flags),
                               only_expiring=("exp" in flags),
                               lateral_filter=_lat_f)

    # ── Lateral map: lateral_pos + role_type por jugador ──────────────────────
    _lat_dict, _rt_dict = _get_lateral_map()

    # ── Filtro por lateral_pos (para posiciones MID/FWD/GK no cubiertas arriba) ─
    if pos_filter and pos_filter not in ("", "LI", "LD", "DC") and not rk.empty:
        rk = rk[rk["name"].map(lambda n: _lat_dict.get(n) == pos_filter
                               or n not in _lat_dict)]

    # ── Filtro por role_type: cada jugador solo pertenece a 1 estilo de juego ──
    if role and _rt_dict and not rk.empty:
        rk = rk[rk["name"].map(
            lambda n: _rt_dict.get(n) == role or _rt_dict.get(n) is None
        )]

    # Filtros post-ranking: edad y contrato restante
    if not rk.empty and max_age and max_age < 38:
        if "age" in rk.columns:
            rk = rk[(rk["age"].isna()) | (pd.to_numeric(rk["age"], errors="coerce") <= max_age)]
    if not rk.empty and max_contract is not None and max_contract < 6:
        if "contract_years_remaining" in rk.columns:
            rk = rk[(rk["contract_years_remaining"].isna()) |
                    (rk["contract_years_remaining"] <= max_contract)]
    rk = rk.head(30)  # top 30 candidatos para Fit Rayo
    if rk.empty:
        return html.P("Sin candidatos con esos filtros.", style={"fontSize": "12px", "color": "#9CA3AF"})

    # Calcular Fit Rayo real (mismo scorer que el perfil del jugador)
    names_list = list(rk["name"].dropna())
    teams_list = list(rk.loc[rk["name"].notna(), "team"]) if "team" in rk.columns else None
    fit_map = _fit_scores_for(names_list, teams=teams_list)

    # Reordenar según criterio seleccionado, mostrar top 20
    sort_by = sort_by or "fit"
    rk = rk.copy()
    rk["_fit_rayo"] = rk["name"].map(lambda n: fit_map.get(n, {}).get("fit", -1))
    rk["_rend"]     = rk["name"].map(lambda n: fit_map.get(n, {}).get("rend", -1))
    rk["_adn"]      = rk["name"].map(lambda n: fit_map.get(n, {}).get("adn", -1))
    _sort_col = {"fit": "_fit_rayo", "rend": "_rend", "adn": "_adn"}.get(sort_by, "_fit_rayo")
    rk = rk.sort_values(_sort_col, ascending=False).head(20).reset_index(drop=True)

    cols_h = ["#", "Jugador", "Pos.", "Equipo", "Liga", "Edad", "Min", "Valor", "Sal. est.",
              "Contrato", "Rend.", "ADN", "Fit Rayo"]
    head = html.Tr([html.Th(h, style={"fontSize": "10px", "color": "#9CA3AF", "padding": "5px 10px",
                    "textAlign": "left"}) for h in cols_h])
    body = []
    for i, r in enumerate(rk.itertuples(), 1):
        contract = getattr(r, "contract_until", None)
        exp = getattr(r, "expiring_2026", False)
        _scores = fit_map.get(r.name, {})
        fit_val  = _scores.get("fit") if _scores else None
        rend_val = _scores.get("rend") if _scores else None
        adn_val  = _scores.get("adn") if _scores else None

        def _score_color(v):
            if v is None: return "#9CA3AF"
            return "#166534" if v >= 70 else "#92400E" if v >= 50 else "#991B1B"

        fit_cell = html.Td(
            f"{fit_val:.0f}" if fit_val is not None else f"{r.role_score:.0f}*",
            title="*Rendimiento (Fit Rayo no disponible)" if fit_val is None else f"Fit Rayo: {fit_val:.1f}/100",
            style={"fontSize": "13px", "padding": "5px 10px",
                   "fontWeight": "700", "color": _score_color(fit_val)},
        )
        rend_cell = html.Td(
            f"{rend_val:.0f}" if rend_val is not None else "—",
            title=f"Rendimiento: {rend_val:.1f}/100" if rend_val is not None else "",
            style={"fontSize": "12px", "padding": "5px 10px",
                   "fontWeight": "600", "color": _score_color(rend_val)},
        )
        adn_cell = html.Td(
            f"{adn_val:.0f}" if adn_val is not None else "—",
            title=f"ADN Táctico: {adn_val:.1f}/100" if adn_val is not None else "",
            style={"fontSize": "12px", "padding": "5px 10px",
                   "fontWeight": "600", "color": _score_color(adn_val)},
        )
        _pos_label = _lat_dict.get(r.name, "—")
        body.append(html.Tr([
            html.Td(str(i), style={"fontSize": "11px", "padding": "5px 10px", "color": "#9CA3AF"}),
            html.Td(html.A(r.name, href=f"/jugador?name={r.name}&team={r.team}",
                    style={"color": "#1A1A2E", "fontWeight": "600", "textDecoration": "none"}),
                    style={"fontSize": "12px", "padding": "5px 10px"}),
            html.Td(html.Span(_pos_label, style={
                    "fontSize": "10px", "fontWeight": "700", "color": "#1D4ED8",
                    "background": "#EFF6FF", "borderRadius": "4px", "padding": "1px 6px"}),
                    style={"padding": "5px 10px"}),
            html.Td(r.team, style={"fontSize": "11px", "padding": "5px 10px", "color": "#374151"}),
            html.Td(_league_name(str(r.league)),
                    style={"fontSize": "10px", "padding": "5px 10px", "color": "#6B7280"}),
            html.Td(
                str(int(float(getattr(r, "age", None) or 0))) if pd.notna(getattr(r, "age", None)) else "—",
                style={"fontSize": "11px", "padding": "5px 10px", "color": "#374151"}),
            html.Td(str(int(r.minutes)) if pd.notna(r.minutes) else "—",
                    style={"fontSize": "11px", "padding": "5px 10px", "color": "#374151"}),
            html.Td(_fmt_val(getattr(r, "value_eur", None)),
                    style={"fontSize": "11px", "padding": "5px 10px", "color": "#374151"}),
            html.Td(_est_salary(
                        getattr(r, "value_eur", None),
                        league=str(getattr(r, "league", "") or ""),
                        minutes=float(r.minutes) if pd.notna(r.minutes) else 0,
                        age=int(a) if (a := pd.to_numeric(getattr(r, "age", None), errors="coerce")) == a else 25,
                        position=str(getattr(r, "position_primary", "") or ""),
                        team=str(getattr(r, "team", "") or ""),
                    ), style={"fontSize": "10px", "padding": "5px 10px", "color": "#6B7280",
                           "fontStyle": "italic"}),
            html.Td(html.Span((str(contract)[:4] if contract else "n/d"),
                    style={"fontWeight": "700" if exp else "400",
                           "color": "#DC2626" if exp else "#6B7280"}),
                    style={"fontSize": "11px", "padding": "5px 10px"}),
            rend_cell,
            adn_cell,
            fit_cell,
        ], style={"borderTop": "1px solid #F3F4F6"}))
    # Data freshness: check when player_economic.parquet was last modified
    import os as _os, datetime as _dt
    eco_path = PROC / "player_economic.parquet"
    if eco_path.exists():
        mtime = _dt.datetime.fromtimestamp(eco_path.stat().st_mtime)
        days_old = (_dt.datetime.now() - mtime).days
        freshness_color = "#991B1B" if days_old > 30 else "#166534" if days_old < 7 else "#92400E"
        freshness_note = (
            f"Datos Transfermarkt actualizados hace {days_old} días "
            f"({mtime.strftime('%d/%m/%Y')}) · "
            "Para actualizar: python scripts/fetch_tm_data.py · "
            "Sobreescribe con datos manuales en el perfil del jugador"
        )
    else:
        freshness_color = "#6B7280"
        freshness_note = "Fuente: config/market_values.csv (legacy) · Para datos actualizados ejecuta fetch_tm_data.py"

    return html.Div([
        html.Div([
            html.I(className="ti ti-clock", style={"color": freshness_color, "marginRight": "4px",
                                                    "fontSize": "10px"}),
            html.Span(freshness_note, style={"fontSize": "9px", "color": freshness_color}),
        ], style={"marginBottom": "4px"}),
        html.P(
            "Salario estimado: rango salarial real por liga × titularidad × edad × club. "
            "Fuente: salary_estimates.yaml (FIFPRO 2023). Estimación orientativa — no contractual.",
            style={"fontSize": "9px", "color": "#9CA3AF", "marginBottom": "6px",
                   "fontStyle": "italic"}
        ),
        html.Table([html.Thead(head), html.Tbody(body)],
                   style={"width": "100%", "borderCollapse": "collapse"}),
    ])


def _renewal_score_bar(score: float):
    if score >= 70:
        color = "#166534"; bg = "#DCFCE7"
    elif score >= 50:
        color = "#1D4ED8"; bg = "#EFF6FF"
    elif score >= 35:
        color = "#92400E"; bg = "#FEF9C3"
    else:
        color = "#991B1B"; bg = "#FEE2E2"
    return html.Div([
        html.Div([
            html.Span(f"{score:.0f}", style={"fontSize": "14px", "fontWeight": "700", "color": color}),
            html.Span("/100", style={"fontSize": "10px", "color": "#9CA3AF"}),
        ], style={"marginBottom": "3px"}),
        html.Div(
            html.Div(style={"height": "5px", "width": f"{score:.0f}%",
                            "background": color, "borderRadius": "3px"}),
            style={"background": bg, "borderRadius": "3px", "height": "5px"},
        ),
    ])


def _renewal_card(result):
    bg_rec, fg_rec = RECOMMENDATION_COLORS.get(result.recommendation, ("#F3F4F6", "#374151"))
    icon_rec  = RECOMMENDATION_ICONS.get(result.recommendation, "ti-question-mark")
    label_rec = RECOMMENDATION_LABELS.get(result.recommendation, result.recommendation)
    m = result.months_remaining
    if m <= 6:
        uc = "#991B1B"; ub = "#FEE2E2"; ut = f"URGENTE — {m}m"
    elif m <= 12:
        uc = "#92400E"; ub = "#FEF9C3"; ut = f"Pronto — {m}m"
    else:
        uc = "#374151"; ub = "#F3F4F6"; ut = f"{m}m restantes"
    conf_map = {"alto": ("#166534", "#DCFCE7"), "medio": ("#1D4ED8", "#EFF6FF"),
                "bajo": ("#9CA3AF", "#F3F4F6")}
    cf, cb = conf_map.get(result.confidence, ("#9CA3AF", "#F3F4F6"))
    mv_str = (f"{result.market_value_eur/1e6:.1f}M"
              if result.market_value_eur and result.market_value_eur > 0 else "n/d")
    items = []
    for t in result.positivos[:2]:
        items.append(html.Li(t, style={"color": "#166534", "fontSize": "10px"}))
    for t in result.negativos[:1]:
        items.append(html.Li(t, style={"color": "#991B1B", "fontSize": "10px"}))
    for t in result.riesgos[:1]:
        items.append(html.Li(t, style={"color": "#92400E", "fontSize": "10px"}))
    return html.Div([
        html.Div([
            html.Div([
                html.Strong(result.name, style={"fontSize": "12px", "color": "#1A1A2E"}),
                html.Div([
                    html.Span(result.position, style={
                        "fontSize": "9px", "fontWeight": "700", "background": "#E5E7EB",
                        "color": "#374151", "borderRadius": "4px", "padding": "1px 6px",
                        "marginRight": "5px",
                    }),
                    html.Span(f"{result.age:.0f}a", style={"fontSize": "10px", "color": "#6B7280"}),
                ], style={"marginTop": "2px"}),
            ], style={"flex": "1"}),
            html.Div([
                html.I(className=f"ti {icon_rec}",
                       style={"fontSize": "11px", "marginRight": "4px", "color": fg_rec}),
                html.Span(label_rec, style={"fontSize": "10px", "fontWeight": "700", "color": fg_rec}),
            ], style={"background": bg_rec, "borderRadius": "8px", "padding": "4px 8px",
                      "display": "inline-flex", "alignItems": "center"}),
        ], style={"display": "flex", "justifyContent": "space-between",
                  "alignItems": "flex-start", "marginBottom": "8px"}),
        _renewal_score_bar(result.renewal_score),
        html.Div([
            html.Span(ut, style={"fontSize": "10px", "fontWeight": "600", "background": ub,
                                 "color": uc, "borderRadius": "6px", "padding": "2px 7px",
                                 "marginRight": "5px"}),
            html.Span(mv_str, style={"fontSize": "10px", "color": "#374151", "marginRight": "5px"}),
            html.Span(_est_salary(
                          result.market_value_eur,
                          league=str(getattr(result, "league", "") or ""),
                          minutes=float(getattr(result, "minutes", 0) or 0),
                          age=int(float(getattr(result, "age", 25) or 25)),
                          position=str(getattr(result, "position_primary", "") or ""),
                          team=str(getattr(result, "team", "") or ""),
                      ), style={"fontSize": "9px", "color": "#6B7280", "marginRight": "5px",
                             "fontStyle": "italic"}),
            html.Span(f"Conf: {result.confidence}", style={
                "fontSize": "9px", "fontWeight": "600", "background": cb,
                "color": cf, "borderRadius": "6px", "padding": "1px 6px"}),
        ], style={"marginTop": "7px", "marginBottom": "7px"}),
        html.Ul(items, style={"paddingLeft": "14px", "margin": "0", "lineHeight": "1.6"})
        if items else html.Span(),
        html.Div(f"Datos: {result.data_quality}", style={
            "fontSize": "9px", "color": "#D1D5DB", "marginTop": "6px", "textAlign": "right"}),
    ], style={"background": "#FAFAFA", "border": "1px solid #E5E7EB",
              "borderRadius": "10px", "padding": "12px 14px", "height": "100%"})


@callback(
    Output("renewal-results", "children"),
    Output("renewal-summary-badge", "children"),
    Input("renewal-horizon", "value"),
)
def _renewal_analysis(horizon):
    squad = _flatten_squad()
    if not squad:
        return (html.P("No se encontro config/club_profile.yaml.",
                       style={"fontSize": "12px", "color": "#9CA3AF"}), "")
    results = load_and_analyze(PROC, squad, horizon_months=horizon or 18)
    if not results:
        return (html.P(f"Ningun jugador con contrato en los proximos {horizon} meses.",
                       style={"fontSize": "12px", "color": "#9CA3AF"}), "")
    from collections import Counter
    rc = Counter(r.recommendation for r in results)
    urgent = sum(1 for r in results if r.months_remaining <= 6)
    summary = html.Div([
        html.Span(f"{len(results)} jugadores analizados  |  ", style={"color": "#374151"}),
        html.Span(f"{urgent} urgentes (<=6m)  |  ",
                  style={"color": "#991B1B", "fontWeight": "600"} if urgent else {"color": "#374151"}),
        *[html.Span(f"{RECOMMENDATION_LABELS.get(k,k)}: {v}  ", style={"color": "#6B7280"})
          for k, v in rc.most_common()],
        criteria_accordion("decisiones"),
    ])
    g0 = [r for r in results if r.months_remaining <= 6]
    g1 = [r for r in results if 6 < r.months_remaining <= 12]
    g2 = [r for r in results if r.months_remaining > 12]

    def _sec(title, players, bc):
        if not players:
            return None
        return html.Div([
            html.P(title, style={
                "fontSize": "10px", "fontWeight": "700", "color": bc,
                "textTransform": "uppercase", "letterSpacing": ".08em",
                "borderLeft": f"3px solid {bc}", "paddingLeft": "8px",
                "marginBottom": "10px",
            }),
            dbc.Row([
                dbc.Col(_renewal_card(r), md=4, style={"marginBottom": "12px"})
                for r in players
            ], className="g-2"),
        ], style={"marginBottom": "16px"})

    secs = [
        _sec("Vencen en <= 6 meses — DECISION URGENTE", g0, "#991B1B"),
        _sec("Vencen en 7-12 meses", g1, "#92400E"),
           _sec("Vencen en 13-18 meses", g2, "#166534"),
    ]
    secs = [s for s in secs if s is not None]
    if not secs:
        return (html.Div("Ningun contrato en el horizonte seleccionado.",
                         style={"fontSize": "12px", "color": "#9CA3AF"}), "")
    return (
        html.Div([summary, *secs]),
        f"{len(results)} jugadores analizados",
    )
