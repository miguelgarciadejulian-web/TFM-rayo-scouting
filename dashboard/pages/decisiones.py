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
from dash import html, dcc, callback, Input, Output
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
_CACHE_TTL = 120


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
    data = json.load(open(p, encoding="utf-8")) if p.exists() else {}
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
        html.P(it["reason"], style={"fontSize": "11px", "color": "#374151", "margin": "2px 0 0",
               "lineHeight": "1.4"}),
    ], style={"padding": "8px 0", "borderBottom": "1px solid #F3F4F6"})


def _candidate_chips(cands):
    if not cands:
        return html.Span()
    return html.Div([
        html.Span("Candidatos: ", style={"fontSize": "9px", "color": "#9CA3AF", "fontWeight": "700"}),
        *[html.Span(f"{c['name']} ({c.get('role_score','')})",
            title=f"{c.get('team','')} · {c.get('season','')}",
            style={"fontSize": "10px", "background": "#F0FDF4", "color": "#166534",
                   "borderRadius": "6px", "padding": "2px 7px", "marginRight": "4px",
                   "marginBottom": "4px", "display": "inline-block"})
          for c in cands[:6]],
    ], style={"marginTop": "4px"})


def _fichar_row(it, shortlists):
    cands = shortlists.get(it.get("role"), [])
    return html.Div([
        html.Div([
            html.Strong(it.get("role"), style={"fontSize": "12px", "color": "#1A1A2E"}),
            html.Span(f"  prioridad {it.get('priority','')}",
                      style={"fontSize": "10px", "color": "#6B7280"}),
        ]),
        html.P(it["reason"], style={"fontSize": "11px", "color": "#374151", "margin": "2px 0 0"}),
        _candidate_chips(cands),
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


def layout(**_params):
    data = _load_squad()
    dec = squad_decisions(data.get("squad", []), data.get("needs", {}))
    shortlists = _load_shortlists()
    coaches = _load_coaches()
    top3 = coaches[:3]
    needs = data.get("needs", {})

    tab_fichajes = html.Div([
        _criteria_badge(
            "Criterios aplicados: encaje tactico (presion, posesion, verticalidad) · "
            "encaje economico (valor de mercado vs presupuesto) · riesgo contractual "
            "(duracion + clausula). Candidatos generados automaticamente por rol."
        ),
        html.Div([
            html.Span("Necesidades detectadas: ", style={"fontSize": "12px", "fontWeight": "600"}),
            html.Span("Faltan: " + (", ".join(needs.get("missing", [])) or "—"),
                      style={"fontSize": "12px", "color": "#991B1B", "marginRight": "14px"}),
            html.Span("Reforzar: " + (", ".join(needs.get("reinforce", [])) or "—"),
                      style={"fontSize": "12px", "color": "#92400E", "marginRight": "14px"}),
            html.Span("Sobran: " + (", ".join(needs.get("over_represented", [])) or "—"),
                      style={"fontSize": "12px", "color": "#6B7280"}),
        ], style={"background": "#F9FAFB", "border": "1px solid #E5E7EB",
                  "borderRadius": "10px", "padding": "12px 16px", "marginBottom": "16px"}),
        dbc.Row([
            _decision_col("fichar", dec["fichar"], shortlists),
            _decision_col("renovar", dec["renovar"]),
            _decision_col("vender", dec["vender"]),
            _decision_col("ceder", dec["ceder"]),
        ], className="g-3 mb-3"),
        html.Div([
            html.P("Explorador de candidatos por perfil",
                   style={"fontSize": "13px", "fontWeight": "700", "color": "#1A1A2E", "marginBottom": "4px"}),
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
                    dcc.Slider(300, 2500, 100, value=900, id="exp-min",
                               marks={300:"300",1200:"1200",2500:"2500"},
                               tooltip={"placement":"bottom"})], md=3),
            ], className="g-2"),
            dbc.Row([

                dbc.Col([html.Span("Valor max (M€)", className="filter-label"),
                    dcc.Slider(0,100,5, value=100, id="exp-maxval",
                               marks={0:"0",25:"25",50:"50",100:"sin tope"},
                               tooltip={"placement":"bottom"})], md=4),
                dbc.Col(dcc.Checklist(
                    options=[{"label": "  Excluir grandes clubes", "value": "big"},
                             {"label": "  Solo acaban contrato 2026", "value": "exp"}],
                    value=["big"], id="exp-flags", inline=True,
                    style={"fontSize": "12px", "marginTop": "18px"}), md=5),
            ], className="g-2", style={"marginTop": "4px"}),
            dbc.Row([
                dbc.Col([html.Span("Edad max.", className="filter-label"),
                    dcc.Slider(18, 38, 1, value=32, id="exp-maxage",
                               marks={18:"18", 25:"25", 30:"30", 35:"35", 38:"38"},
                               tooltip={"placement": "bottom"})], md=4),
                dbc.Col([html.Span("Contrato restante max (años)", className="filter-label"),
                    dcc.Slider(0, 6, 1, value=6, id="exp-maxcontract",
                               marks={0:"libre", 1:"1", 2:"2", 3:"3", 4:"4", 5:"5", 6:"sin tope"},
                               tooltip={"placement": "bottom"})], md=5),
            ], className="g-2", style={"marginTop": "4px"}),

            dcc.Loading(html.Div(id="exp-results", style={"marginTop": "12px"}),
                        type="dot", color="#E30613"),
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
            html.I(className="ti ti-contract", style={"fontSize": "18px", "color": "#E30613",
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
                    type="dot", color="#E30613"),
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
                              style={"float": "right", "fontWeight": "700", "color": "#E30613"}),
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

    return html.Div([
        html.Div([
            html.P("PLANIFICACION DEPORTIVA", style={"fontSize": "10px", "fontWeight": "600",
                   "color": "#6B7280", "letterSpacing": ".08em", "margin": "0 0 3px"}),
            html.H1("Decisiones deportivas", className="page-title"),
            html.P("Rankings automaticos del mercado 2026/27 derivados de los perfiles",
                   className="page-subtitle"),
        ], className="page-header"),

        dbc.Tabs([
            dbc.Tab(tab_fichajes,     label="Fichajes",    tab_id="tab-fichajes",
                    label_style={"fontWeight": "600", "fontSize": "13px"}),
            dbc.Tab(tab_renovaciones, label="Renovaciones", tab_id="tab-renovaciones",
                    label_style={"fontWeight": "600", "fontSize": "13px"}),
            dbc.Tab(tab_entrenadores, label="Entrenadores", tab_id="tab-entrenadores",
                    label_style={"fontWeight": "600", "fontSize": "13px"}),
        ], active_tab="tab-fichajes", style={"marginBottom": "16px"}),
    ])


def _fmt_val(v):
    if v is None or pd.isna(v):
        return "n/d"
    v = float(v)
    return f"{v/1e6:.0f}M" if v >= 1e6 else f"{v/1e3:.0f}K"


def _est_salary(market_value_eur, league: str = "", minutes: float = 0,
                age: int = 25, position: str = "") -> str:
    """
    Estimación salarial bruta anual con modelo multi-factor.

    Factores (pesos aproximados en el ratio base sobre VM):
      Liga         35% → ratio base sobre valor de mercado
      VM           25% → base absoluta (progresión no lineal)
      Minutos      20% → multiplicador de titularidad
      Edad         10% → pico 24-28 → penalización fuera del rango
      Posición     10% → delanteros/centrocampistas atacantes reciben +5-10%

    Rangos de referencia LaLiga 2024/25:
      LaLiga1 titular → ~12-18% del VM bruto/año
      LaLiga2 titular → ~8-12% del VM bruto/año
      Otras ligas top → ~10-15% del VM bruto/año
    """
    try:
        mv = float(market_value_eur or 0)
        if mv <= 0:
            return "n/d"

        # ── 1. Ratio base según liga (peso 35%) ──
        league_l = str(league).lower()
        if any(x in league_l for x in ["primera", "laliga", "la liga", "spain"]):
            base_ratio = 0.15   # LaLiga Primera
        elif any(x in league_l for x in ["segunda", "segunda division", "spain 2"]):
            base_ratio = 0.10   # LaLiga Segunda
        elif any(x in league_l for x in ["premier", "england"]):
            base_ratio = 0.18   # Premier League (mercado más inflado)
        elif any(x in league_l for x in ["bundesliga", "germany"]):
            base_ratio = 0.14
        elif any(x in league_l for x in ["serie a", "italy"]):
            base_ratio = 0.13
        elif any(x in league_l for x in ["ligue 1", "france"]):
            base_ratio = 0.12
        else:
            base_ratio = 0.11   # Otras ligas europeas

        # ── 2. Ajuste de escala no lineal por VM (peso 25%) ──
        # Jugadores de alto valor tienen ratio ligeramente menor (negociación)
        if mv >= 30_000_000:
            scale = 0.90
        elif mv >= 15_000_000:
            scale = 0.95
        elif mv >= 5_000_000:
            scale = 1.00
        elif mv >= 1_000_000:
            scale = 1.08   # Jugadores de medio valor, ratio algo mayor
        else:
            scale = 1.15   # Jugadores de bajo VM (sueldos relativamente altos)

        # ── 3. Multiplicador titularidad por minutos (peso 20%) ──
        min_mult = 1.0
        mins = float(minutes or 0)
        if mins >= 2500:
            min_mult = 1.10   # Titular indiscutible
        elif mins >= 1800:
            min_mult = 1.05   # Titular habitual
        elif mins >= 900:
            min_mult = 0.95   # Rotación / suplente habitual
        elif mins >= 450:
            min_mult = 0.85   # Poco minutos
        else:
            min_mult = 0.75   # Sin apenas participación

        # ── 4. Ajuste de edad (peso 10%) ──
        age_mult = 1.0
        if 24 <= age <= 28:
            age_mult = 1.05   # Pico de rendimiento
        elif 22 <= age <= 23 or 29 <= age <= 30:
            age_mult = 1.00
        elif age <= 21:
            age_mult = 0.88   # Joven — sueldo moderado aunque tenga proyección
        elif 31 <= age <= 33:
            age_mult = 0.92   # Inicio declive
        else:
            age_mult = 0.82   # Veterano (>33)

        # ── 5. Ajuste por posición (peso 10%) ──
        pos_mult = 1.0
        pos_u = str(position).upper()
        if pos_u in ("ST", "LW", "RW"):
            pos_mult = 1.08   # Atacantes: mayor demanda
        elif pos_u in ("AM", "CM"):
            pos_mult = 1.03
        elif pos_u in ("GK",):
            pos_mult = 0.95   # Porteros: mercado más limitado

        sal = mv * base_ratio * scale * min_mult * age_mult * pos_mult
        if sal >= 1_000_000:
            return f"~{sal/1e6:.1f}M€/año"
        return f"~{sal/1e3:.0f}K€/año"
    except (TypeError, ValueError):
        return "n/d"




@callback(Output("exp-results", "children"),
          Input("exp-role", "value"), Input("exp-leagues", "value"), Input("exp-min", "value"),
          Input("exp-maxval", "value"), Input("exp-flags", "value"),
          Input("exp-maxage", "value"), Input("exp-maxcontract", "value"))
def _explore(role, leagues, min_min, maxval, flags, max_age, max_contract):
    enr = _enriched()
    if enr.empty:
        return html.P("Sin datos enriquecidos.", style={"fontSize": "12px", "color": "#9CA3AF"})
    flags = flags or []
    max_value_eur = None if (maxval is None or maxval >= 100) else maxval * 1e6
    seasons_filter = CURRENT_SEASONS  # 2026 + 2025-2026: todas las ligas actuales
    rk = rank_players_for_role(enr, role, top_n=200, min_minutes=int(min_min or 900),
                               leagues=leagues or None, seasons=seasons_filter,
                               max_value_eur=max_value_eur,
                               exclude_big_clubs=("big" in flags),
                               only_expiring=("exp" in flags))
    # Filtros post-ranking: edad y contrato restante
    if not rk.empty and max_age and max_age < 38:
        if "age" in rk.columns:
            rk = rk[(rk["age"].isna()) | (pd.to_numeric(rk["age"], errors="coerce") <= max_age)]
    if not rk.empty and max_contract is not None and max_contract < 6:
        if "contract_years_remaining" in rk.columns:
            rk = rk[(rk["contract_years_remaining"].isna()) |
                    (rk["contract_years_remaining"] <= max_contract)]
    rk = rk.head(25)
    if rk.empty:
        return html.P("Sin candidatos con esos filtros.", style={"fontSize": "12px", "color": "#9CA3AF"})
    cols_h = ["#", "Jugador", "Equipo", "Liga", "Edad", "Min", "Valor", "Sal. est.", "Contrato", "Score"]
    head = html.Tr([html.Th(h, style={"fontSize": "10px", "color": "#9CA3AF", "padding": "5px 10px",
                    "textAlign": "left"}) for h in cols_h])
    body = []
    for i, r in enumerate(rk.itertuples(), 1):
        contract = getattr(r, "contract_until", None)
        exp = getattr(r, "expiring_2026", False)
        body.append(html.Tr([
            html.Td(str(i), style={"fontSize": "11px", "padding": "5px 10px", "color": "#9CA3AF"}),
            html.Td(html.A(r.name, href=f"/jugador?name={r.name}&team={r.team}",
                    style={"color": "#1A1A2E", "fontWeight": "600", "textDecoration": "none"}),
                    style={"fontSize": "12px", "padding": "5px 10px"}),
            html.Td(r.team, style={"fontSize": "11px", "padding": "5px 10px", "color": "#374151"}),
            html.Td(_league_name(str(r.league)),
                    style={"fontSize": "10px", "padding": "5px 10px", "color": "#6B7280"}),
            html.Td(
                str(int(float(getattr(r, "age", None) or 0))) if getattr(r, "age", None) else "—",
                style={"fontSize": "11px", "padding": "5px 10px", "color": "#374151"}),
            html.Td(str(int(r.minutes)) if pd.notna(r.minutes) else "—",
                    style={"fontSize": "11px", "padding": "5px 10px", "color": "#374151"}),
            html.Td(_fmt_val(getattr(r, "value_eur", None)),
                    style={"fontSize": "11px", "padding": "5px 10px", "color": "#374151"}),
            html.Td(_est_salary(
                        getattr(r, "value_eur", None),
                        league=str(getattr(r, "league", "") or ""),
                        minutes=float(r.minutes) if pd.notna(r.minutes) else 0,
                        age=int(float(getattr(r, "age", 25) or 25)),
                        position=str(getattr(r, "position_primary", "") or ""),
                    ), style={"fontSize": "10px", "padding": "5px 10px", "color": "#6B7280",
                           "fontStyle": "italic"}),
            html.Td(html.Span((str(contract)[:4] if contract else "n/d"),
                    style={"fontWeight": "700" if exp else "400",
                           "color": "#E30613" if exp else "#6B7280"}),
                    style={"fontSize": "11px", "padding": "5px 10px"}),
            html.Td(f"{r.role_score:.0f}", style={"fontSize": "12px", "padding": "5px 10px",
                    "fontWeight": "700", "color": "#E30613"}),
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
            "Salario estimado: ratio base por liga (LaLiga ~15% VM) × ajuste VM × minutos × edad × posición. "
            "Estimación orientativa — no contractual.",
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
        _sec("Vencen en 13-24 meses", g2, "#1D4ED8"),
    ]
    return html.Div([s for s in secs if s is not None]), summary
