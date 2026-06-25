# -*- coding: utf-8 -*-
"""
Casting de Entrenadores - Rayo 2026/27.

El ESTILO DE JUEGO de cada tecnico y su EVALUACION (score, pros, contras y
riesgos) se calculan por codigo en src/profiling y src/fit y se leen desde
data/processed/coach_profiles.json (generado por scripts/build_profiles.py).
El usuario puede anadir pros/contras manuales que se guardan aparte sin borrar
los automaticos (coach_manual_notes.json).
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import dash
from dash import html, dcc, callback, Input, Output, State, ALL, no_update, ctx
import dash_bootstrap_components as dbc

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dashboard.components.criteria_block import criteria_accordion  # noqa: E402
import yaml  # noqa: E402
import plotly.graph_objects as go
from dashboard.components.chart_theme import RAYO_RED, RAYO_DARK, hex_to_rgba, GRAPH_CONFIG_SIMPLE  # noqa: E402
from src.utils.config import settings  # noqa: E402
from src.fit.coach_fit import evaluate_coach  # noqa: E402

dash.register_page(__name__, path="/entrenadores", name="Entrenadores")

ROOT = Path(__file__).resolve().parents[2]
PROC = Path(settings()["paths"]["data_processed"])
PROFILES = PROC / "coach_profiles.json"
MANUAL = PROC / "coach_manual_notes.json"

try:
    from src.fit.dynamic_dna import build_dynamic_dna as _build_dyn_dna
    _DNA_DEFAULTS = {axis: spec["ideal"]
                     for axis, spec in _build_dyn_dna()["target_style"].items()}
except Exception:
    # Fallback al YAML estatico si dynamic_dna no esta disponible
    try:
        _DNA_DEFAULTS = {axis: spec["ideal"] for axis, spec in
                         yaml.safe_load(open(ROOT / "config" / "rayo_dna.yaml"))["target_style"].items()}
    except Exception:
        _DNA_DEFAULTS = {}


import unicodedata as _ud
COACH_PHOTOS_CSV  = ROOT / "config" / "coach_photos.csv"
COACH_PHOTO_OVERRIDE = PROC / "coach_photo_overrides.json"
_COACH_SIL = ("data:image/svg+xml;utf8," + __import__("urllib.parse", fromlist=["quote"]).quote(
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 110'>"
    "<rect width='100' height='110' fill='#F1F3F5'/>"
    "<circle cx='50' cy='42' r='20' fill='#B6BCC4'/>"
    "<path d='M18 106 C18 78 82 78 82 106 Z' fill='#B6BCC4'/></svg>"))


def _cn(x):
    return _ud.normalize("NFKD", str(x)).encode("ascii", "ignore").decode().lower().strip()


def _load_photo_overrides() -> dict:
    """Lee el JSON de sobreescritura de fotos (guardado por el usuario)."""
    if COACH_PHOTO_OVERRIDE.exists():
        try:
            return json.load(open(COACH_PHOTO_OVERRIDE, encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_photo_override(name: str, data_url: str) -> None:
    """Guarda la foto subida por el usuario de forma persistente."""
    overrides = _load_photo_overrides()
    overrides[_cn(name)] = data_url
    COACH_PHOTO_OVERRIDE.parent.mkdir(parents=True, exist_ok=True)
    json.dump(overrides, open(COACH_PHOTO_OVERRIDE, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


def _coach_photos():
    """Devuelve dict {nombre_normalizado: url_foto}.
    Prioridad: 1) override manual del usuario · 2) CSV de fotos · 3) silueta."""
    overrides = _load_photo_overrides()
    d = {}
    if COACH_PHOTOS_CSV.exists():
        try:
            import csv as _csv
            for r in _csv.DictReader(open(COACH_PHOTOS_CSV, encoding="utf-8")):
                img = (r.get("imagen_local") or "").strip() or (r.get("imagen") or "").strip()
                if img:
                    d[_cn(r.get("entrenador"))] = img
        except Exception:
            pass
    # Las sobreescrituras del usuario tienen prioridad máxima
    d.update(overrides)
    return d


def _coach_avatar(name, size=38, radius="50%"):
    url = _coach_photos().get(_cn(name))
    src = url or _COACH_SIL
    return html.Img(src=src, alt=name, style={
        "width": f"{size}px", "height": f"{size}px", "objectFit": "cover",
        "borderRadius": radius, "flexShrink": "0",
        "border": "2px solid #E5E7EB", "background": "#F1F3F5"})

AXES_SHOW = [
    ("tendencia_ofensiva", "Ofensivo"),
    ("solidez_defensiva", "Defensivo"),
    ("presion_alta", "Presion"),
    ("posesion", "Posesion"),
    ("verticalidad", "Verticalidad"),
    ("intensidad_defensiva", "Intensidad"),
    ("uso_transiciones", "Transiciones"),
    ("flexibilidad_tactica", "Flexibilidad"),
]
RISK_LABELS = {
    "deportivo": "Deportivo", "economico": "Economico", "clausula": "Clausula",
    "adaptacion_laliga": "Adaptacion LaLiga", "incompatibilidad_plantilla": "Incompat. plantilla",
}
RISK_COLOR = {
    "bajo": ("#DCFCE7", "#166534"), "medio": ("#FEF9C3", "#854D0E"),
    "medio-alto": ("#FFEDD5", "#9A3412"), "alto": ("#FEE2E2", "#991B1B"),
    "n/d": ("#F3F4F6", "#6B7280"),
}


def _load_dna():
    """
    Carga el DNA del Rayo desde datos reales (dynamic_dna).
    Fallback al YAML estatico si el modulo dinamico falla.
    """
    try:
        from src.fit.dynamic_dna import build_dynamic_dna
        return build_dynamic_dna()
    except Exception:
        return yaml.safe_load(open(ROOT / "config" / "rayo_dna.yaml"))


def _load_needs():
    p = PROC / "squad_profile.json"
    if p.exists():
        return json.load(open(p, encoding="utf-8")).get("needs", {})
    return {}


# Estilos de tabla inline para la metodología ADN
_th = {"border": "1px solid #FECACA", "padding": "3px 6px", "background": "#FFF8F8",
       "fontWeight": "600", "color": "#1A1A2E", "textAlign": "left"}
_td = {"border": "1px solid #FECACA", "padding": "3px 6px", "color": "#374151",
       "verticalAlign": "top"}

# Ejes ajustables por el usuario (slider id -> (label, eje del ADN))
DNA_SLIDERS = [
    ("dna-presion", "Presión alta", "presion_alta"),
    ("dna-posesion", "Posesión", "posesion"),
    ("dna-solidez", "Solidez defensiva", "solidez_defensiva"),
    ("dna-ofensiva", "Tendencia ofensiva", "tendencia_ofensiva"),
    ("dna-vertical", "Verticalidad", "verticalidad"),
    ("dna-intensidad", "Intensidad defensiva", "intensidad_defensiva"),
    ("dna-transiciones", "Uso de transiciones", "uso_transiciones"),
]


def _reevaluate(profiles, ideals):
    """Recalcula el encaje de cada entrenador con los ideales de ADN del usuario."""
    dna = _load_dna()
    needs = _load_needs()
    if ideals:
        for axis, val in ideals.items():
            if axis in dna["target_style"] and val is not None:
                dna["target_style"][axis]["ideal"] = val
    out = []
    for c in profiles:
        ctx = {"laliga_seasons": c.get("laliga_seasons", 0),
               "salary_estimate_eur": c.get("salary_estimate_eur"),
               "available": c.get("available"),
               "release_clause_eur": c.get("release_clause_eur")}
        prof = {"axes": c.get("axes", {}), "coverage": c.get("coverage", {}),
                "data_partial": c.get("data_partial", False)}
        ev = evaluate_coach(c["name"], prof, ctx, dna, squad_summary=needs)
        c2 = dict(c)
        c2["evaluation"] = ev
        out.append(c2)
    out.sort(key=lambda r: (r["evaluation"].get("global_score") or 0), reverse=True)
    return out


_PROF_CACHE: dict = {"data": None, "t": 0.0}
_MAN_CACHE:  dict = {"data": None, "t": 0.0}
_CACHE_TTL = 120  # 2 min


def _load_profiles():
    import time
    if _PROF_CACHE["data"] is not None and time.time() - _PROF_CACHE["t"] < _CACHE_TTL:
        return _PROF_CACHE["data"]
    data = json.load(open(PROFILES, encoding="utf-8")) if PROFILES.exists() else []
    _PROF_CACHE.update({"data": data, "t": time.time()})
    return data


def _load_manual():
    import time
    if _MAN_CACHE["data"] is not None and time.time() - _MAN_CACHE["t"] < _CACHE_TTL:
        return _MAN_CACHE["data"]
    data = json.load(open(MANUAL, encoding="utf-8")) if MANUAL.exists() else {}
    _MAN_CACHE.update({"data": data, "t": time.time()})
    return data


def _save_manual(d):
    MANUAL.parent.mkdir(parents=True, exist_ok=True)
    json.dump(d, open(MANUAL, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    _MAN_CACHE["data"] = None  # invalidar cache



def _calc_adn_from_rayo_data() -> dict | None:
    """Calcula sugerencias de ADN desde estadísticas reales de Rayo en team_seasons.
    Devuelve dict simplificado eje -> percentil (0-100)."""
    result = _calc_adn_detail()
    if result is None:
        return None
    return {k: v["percentil"] for k, v in result.items() if k != "_meta"}


def _calc_adn_detail() -> dict | None:
    """
    Calcula el ADN Rayo con detalle completo para mostrar en la UI.

    Fuente de datos: team_seasons.parquet (estadísticas OPTA por equipo y temporada).
    Metodología:
      1. Filtra filas donde team contiene "Rayo" (case-insensitive).
      2. Toma la temporada más reciente disponible.
      3. Compara vs todos los equipos de la misma liga esa temporada.
      4. Para cada eje, calcula el percentil del Rayo (0-100):
           percentil = % de equipos con valor <= Rayo  (métricas directas)
           percentil = 100 - (% con valor <= Rayo)     (métricas invertidas)
      5. Si la liga tiene < 5 equipos, usa toda la base de datos.
    """
    try:
        import pandas as _pd
        _PROC = ROOT / "data" / "processed"
        df = _pd.read_parquet(_PROC / "team_seasons.parquet")
        rayo = df[df["team"].str.contains("Rayo", case=False, na=False)]
        if rayo.empty:
            return None
        latest = rayo.sort_values("season").iloc[-1]
        temporada = str(latest.get("season", "?"))
        liga_name = str(latest.get("league", "")).replace("_", " ")
        liga = df[(df["league"] == str(latest.get("league", ""))) &
                  (df["season"] == latest.get("season"))]
        if len(liga) < 5:
            liga = df
        n_equipos = len(liga)

        def _pct(col, val, invert=False):
            try:
                vals = _pd.to_numeric(liga[col], errors="coerce").dropna()
                if vals.empty or _pd.isna(val):
                    return 50.0
                rank = (vals <= float(val)).mean() * 100
                return round(100 - rank if invert else rank, 1)
            except Exception:
                return 50.0

        def _raw(col, per_game=False):
            try:
                v = latest.get(col)
                if v is None or _pd.isna(v):
                    return None
                gp = float(latest.get("games_played") or 1)
                return round(float(v) / gp, 2) if per_game else round(float(v), 2)
            except Exception:
                return None

        gp = float(latest.get("games_played") or 1)

        AXIS_META = [
            # (eje, col, invert, per_game, etiqueta_metrica, descripcion)
            ("presion_alta",         "ppda",                    True,  False,
             "PPDA", "Passes Allowed Per Defensive Action — menor = más presión"),
            ("posesion",             "possession_percentage",   False, False,
             "% posesión", "Porcentaje medio de posesión por partido"),
            ("solidez_defensiva",    "goals_conceded",          True,  True,
             "Goles encajados/p", "Goles encajados por partido — menor = más sólido"),
            ("tendencia_ofensiva",   "goals",                   False, True,
             "Goles marcados/p", "Goles marcados por partido"),
            ("verticalidad",         "successful_long_passes",  False, False,
             "Pases largos exitosos", "Total de pases largos completados en la temporada"),
            ("intensidad_defensiva", "tackles_won",             False, False,
             "Entradas ganadas", "Total de entradas ganadas en la temporada"),
            ("uso_transiciones",     "recoveries",              False, False,
             "Recuperaciones", "Total de recuperaciones de balón en la temporada"),
        ]

        result = {}
        for eje, col, invert, per_game, label_metrica, desc in AXIS_META:
            raw_val = _raw(col, per_game=per_game)
            pct_val = _pct(col,
                           float(latest.get("goals_conceded") or 99) / gp if (col == "goals_conceded") else
                           float(latest.get("goals") or 0) / gp if (col == "goals") else
                           latest.get(col),
                           invert=invert)
            result[eje] = {
                "percentil":       pct_val,
                "valor_rayo":      raw_val,
                "metrica_opta":    label_metrica,
                "columna":         col,
                "invertida":       invert,
                "descripcion":     desc,
            }

        result["_meta"] = {
            "temporada":  temporada,
            "liga":       liga_name,
            "n_equipos":  n_equipos,
            "equipo":     str(latest.get("team", "Rayo")),
        }
        return result
    except Exception:
        return None


def _needs_panel() -> html.Div:
    """Panel de necesidades de plantilla siempre visible en la página de entrenadores."""
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
        # Cabecera con ocupación
        html.Div([
            html.Div([
                html.I(className="ti ti-users-group",
                       style={"fontSize": "14px", "color": "#B8960C", "marginRight": "6px"}),
                html.Strong("Plantilla 2026/27 — análisis de necesidades",
                            style={"fontSize": "12px", "color": "#1A1A2E"}),
                html.Span(f"  formación base: {formation}",
                          style={"fontSize": "10px", "color": "#9CA3AF", "marginLeft": "8px"}),
            ], style={"display": "flex", "alignItems": "center", "marginBottom": "6px"}),

            html.Div([
                # Barra de ocupación
                html.Div([
                    html.Div(style={"height": "6px", "borderRadius": "99px",
                                    "width": f"{pct_full:.0f}%", "background": bar_color}),
                ], style={"flex": "1", "height": "6px", "background": "#F3F4F6",
                          "borderRadius": "99px", "overflow": "hidden", "alignSelf": "center"}),
                html.Span(
                    f"{n_total} / {cap} jugadores  ·  {slots_free} hueco{'s' if slots_free != 1 else ''} libre{'s' if slots_free != 1 else ''}",
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
                    [_chip(r, "#FEE2E2", "#991B1B", "●") for r in missing]
                    or [html.Span("Ninguna", style={"fontSize": "10px", "color": "#9CA3AF"})],
                    style={"display": "flex", "flexWrap": "wrap"},
                ),
            ], md=4),
            dbc.Col([
                html.Div("A reforzar",
                         style={"fontSize": "10px", "fontWeight": "700", "color": "#92400E",
                                "marginBottom": "4px"}),
                html.Div(
                    [_chip(r, "#FEF3C7", "#92400E", "▲") for r in reinforce]
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
            f"Plantilla objetivo ({cap} jugadores) derivada automáticamente de la formación base. "
            "La compatibilidad de cada técnico se pondera contra estas carencias.",
            style={"fontSize": "9px", "color": "#9CA3AF", "margin": "8px 0 0",
                   "fontStyle": "italic"},
        ),
    ], style={
        "background": "#FFFBEB", "border": "1px solid #FDE68A", "borderRadius": "10px",
        "padding": "12px 16px", "marginBottom": "14px",
    })


def _fmt_salary(v):
    if not v:
        return "Sin dato"
    return f"{v/1_000_000:.1f}M EUR/ano" if v >= 1_000_000 else f"{v/1_000:.0f}K EUR/ano"


def _score_color(s10):
    if s10 is None:
        return "#6B7280"
    if s10 >= 8.5:
        return "#166534"
    if s10 >= 7:
        return "#854D0E"
    if s10 >= 5:
        return "#1E40AF"
    return "#991B1B"


def _axis_bar(label, value):
    v = 0 if value is None else max(0, min(100, value))
    color = "#10B981" if v >= 60 else ("#F59E0B" if v >= 42 else "#DC2626")
    return html.Div([
        html.Span(label, style={"fontSize": "10px", "color": "#6B7280", "width": "92px",
                                "display": "inline-block"}),
        html.Div(style={"height": "6px", "background": "#F3F4F6", "borderRadius": "99px",
                        "flex": "1", "overflow": "hidden"},
                 children=html.Div(style={"height": "100%", "width": f"{v}%",
                                          "background": color, "borderRadius": "99px"})),
        html.Span("n/d" if value is None else str(int(v)),
                  style={"fontSize": "10px", "color": "#374151", "marginLeft": "6px",
                         "width": "26px", "textAlign": "right"}),
    ], style={"display": "flex", "alignItems": "center", "gap": "6px", "marginBottom": "4px"})



def _radar_chart(axes: dict, dna: dict | None = None):
    """Radar chart del perfil tactico del entrenador vs ADN del Rayo."""
    labels_map = {
        "tendencia_ofensiva": "Ofensivo",
        "solidez_defensiva":  "Defensivo",
        "presion_alta":       "Presion",
        "posesion":           "Posesion",
        "verticalidad":       "Verticalidad",
        "intensidad_defensiva": "Intensidad",
        "uso_transiciones":   "Transiciones",
        "flexibilidad_tactica": "Flexibilidad",
    }
    keys = list(labels_map.keys())
    labels = list(labels_map.values())
    vals_coach = [axes.get(k) or 0 for k in keys]
    # Close the polygon
    vals_coach_c = vals_coach + [vals_coach[0]]
    labels_c = labels + [labels[0]]

    traces = [go.Scatterpolar(
        r=vals_coach_c, theta=labels_c, fill="toself",
        fillcolor="rgba(255,214,0,0.12)", line=dict(color="#FFD600", width=2),
        name="Entrenador",
    )]

    if dna:
        vals_dna = [dna.get(k, 50) for k in keys]
        vals_dna_c = vals_dna + [vals_dna[0]]
        traces.append(go.Scatterpolar(
            r=vals_dna_c, theta=labels_c, fill="toself",
            fillcolor="rgba(26,26,46,0.08)", line=dict(color="#1A1A2E", width=1.5, dash="dot"),
            name="ADN Rayo",
        ))

    fig = go.Figure(data=traces)
    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True, range=[0, 100],
                tickfont=dict(size=8, color="#9CA3AF"),
                gridcolor="#E5E7EB", linecolor="#E5E7EB",
                tickvals=[25, 50, 75, 100],
                ticktext=["25", "50", "75", "100"],
            ),
            angularaxis=dict(
                tickfont=dict(size=10, family="Inter", color=RAYO_DARK),
                linecolor="#E5E7EB",
            ),
            bgcolor="rgba(249,250,251,0.5)",
        ),
        showlegend=True,
        legend=dict(
            font=dict(size=10, family="Inter"), x=0.82, y=1.18,
            bgcolor="rgba(255,255,255,0.9)", bordercolor="#E5E7EB", borderwidth=1,
        ),
        margin=dict(l=20, r=20, t=28, b=20),
        height=240,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hoverlabel=dict(bgcolor=RAYO_DARK, font=dict(size=10, color="white")),
    )
    return dcc.Graph(figure=fig, config={"displayModeBar": False},
                     style={"height": "220px"})

def _coach_card(c):
    ev = c.get("evaluation", {})
    s10 = ev.get("score_10")
    available = c.get("available")
    initials = "".join(w[0].upper() for w in c["name"].split()[:2])
    axes = c.get("axes", {})
    return html.Div([
        html.Div([
            _coach_avatar(c["name"], 40),
            html.Div([
                html.Div([
                    html.Strong(c["name"], style={"fontSize": "13px", "color": "#1A1A2E"}),
                    html.Span("Libre" if available else "Con equipo",
                        style={"fontSize": "9px", "fontWeight": "700", "padding": "2px 7px",
                               "borderRadius": "99px", "marginLeft": "8px",
                               "background": "#DCFCE7" if available else "#FEE2E2",
                               "color": "#166534" if available else "#991B1B"}),
                ]),
                html.Div(
                    " · ".join([x for x in [
                        (f"{c.get('age')} anos" if c.get('age') else None),
                        (c.get('nationality') or None),
                    ] if x]) or "Datos de ficha por completar",
                    style={"fontSize": "11px", "color": "#6B7280", "marginTop": "2px"}),
            ], style={"flex": "1"}),
            html.Div([
                html.Span(f"{s10}" if s10 is not None else "n/d",
                          style={"fontSize": "20px", "fontWeight": "700",
                                 "color": _score_color(s10), "lineHeight": "1"}),
                html.Span("/10", style={"fontSize": "10px", "color": _score_color(s10), "opacity": ".7"}),
            ], style={"textAlign": "center", "flexShrink": "0"}),
        ], style={"display": "flex", "alignItems": "center", "gap": "10px", "marginBottom": "8px"}),

        html.Div([
            html.Span(c.get("style_main", "?"), style={"fontSize": "10px", "fontWeight": "600",
                "padding": "2px 9px", "borderRadius": "99px", "background": "#EFF6FF", "color": "#1D4ED8"}),
            html.Span(f"  {c.get('laliga_seasons',0)} temp. LaLiga",
                      style={"fontSize": "10px", "color": "#6B7280", "marginLeft": "6px"}),
        ], style={"marginBottom": "8px"}),

        html.Div([_axis_bar(lab, axes.get(k)) for k, lab in AXES_SHOW[:4]]),

        html.Div([
            html.I(className="ti ti-building", style={"fontSize": "11px", "color": "#9CA3AF", "marginRight": "4px"}),
            html.Span(c.get("last_club", "?"), style={"fontSize": "11px", "color": "#374151"}),
            html.Span(" · " + _fmt_salary(c.get("salary_estimate_eur")),
                      style={"fontSize": "11px", "color": "#374151"}),
        ], style={"marginTop": "8px"}),

        (html.Div("Cobertura de datos parcial", style={"fontSize": "9px", "color": "#92400E",
            "background": "#FFFBEB", "borderRadius": "6px", "padding": "2px 7px", "marginTop": "6px",
            "display": "inline-block"}) if c.get("data_partial") else html.Span()),
    ], style={
        "background": "#fff",
        "border": f"2px solid {'#166534' if (s10 or 0) >= 8.5 else ('#F59E0B' if (s10 or 0) >= 7 else '#E5E7EB')}",
        "borderRadius": "12px", "padding": "14px 16px",
        "boxShadow": "0 2px 8px rgba(0,0,0,.06)",
    })


def _chip_list(items, color_bg, color_fg, removable_type=None):
    children = []
    for i, it in enumerate(items):
        row = [html.Span(it, style={"fontSize": "11px", "color": color_fg, "lineHeight": "1.4"})]
        if removable_type:
            row.append(html.Span("x", id={"type": removable_type, "index": i},
                style={"cursor": "pointer", "marginLeft": "8px", "color": "#9CA3AF",
                       "fontWeight": "700", "fontSize": "11px"}))
        children.append(html.Div(row, style={"display": "flex", "alignItems": "flex-start",
            "justifyContent": "space-between", "background": color_bg, "borderRadius": "7px",
            "padding": "6px 10px", "marginBottom": "5px"}))
    return children


_AXIS_LABELS_ES = {
    "presion_alta":         "Presión alta",
    "posesion":             "Posesión",
    "solidez_defensiva":    "Solidez defensiva",
    "tendencia_ofensiva":   "Tendencia ofensiva",
    "verticalidad":         "Verticalidad",
    "intensidad_defensiva": "Intensidad defensiva",
    "uso_transiciones":     "Uso de transiciones",
}


def _score_breakdown(ev: dict, c: dict, dna: dict) -> html.Details:
    """
    Panel colapsable que muestra de dónde sale cada número de la puntuación final.
    Abierto por defecto para que el usuario lo vea sin tener que expandirlo.
    """
    sub = ev.get("subscores", {})
    style_detail = ev.get("style_detail", {})
    axes = c.get("axes", {})
    target = dna.get("target_style", {})
    cw = dna.get("context_weights", {})
    eco = dna.get("economics", {})

    # Pesos reales
    laliga_w  = cw.get("laliga_experience", 0.2)
    budget_w  = cw.get("budget_fit", 0.15)
    squad_w   = cw.get("squad_compatibility", 0.15)
    style_w   = round(1.0 - laliga_w - budget_w - squad_w, 4)

    s_style  = sub.get("estilo") or 0
    s_laliga = sub.get("experiencia_laliga") or 0
    s_budget = sub.get("encaje_presupuesto") or 0
    s_squad  = sub.get("compatibilidad_plantilla") or 0
    score_10 = ev.get("score_10", "n/d")
    global_  = ev.get("global_score") or 0

    _th_s = {"fontSize": "9px", "fontWeight": "700", "color": "#6B7280",
             "padding": "3px 6px", "borderBottom": "1px solid #E5E7EB",
             "textAlign": "left", "background": "#F9FAFB"}
    _td_s = {"fontSize": "10px", "padding": "3px 6px", "color": "#374151",
             "borderBottom": "1px solid #F3F4F6"}
    _td_r = {**_td_s, "textAlign": "right"}

    def _cls_color(v):
        if v is None: return "#9CA3AF"
        if v >= 75:   return "#15803D"
        if v >= 55:   return "#B45309"
        return "#991B1B"

    def _badge(txt, bg, fg):
        return html.Span(txt, style={"fontSize": "8px", "fontWeight": "700",
            "padding": "1px 5px", "borderRadius": "99px",
            "background": bg, "color": fg, "marginLeft": "4px"})

    # ── 1. Fórmula global ────────────────────────────────────────────────────
    formula_row = html.Div([
        html.Span("Fórmula: ", style={"fontSize": "10px", "fontWeight": "700",
                                       "color": "#374151"}),
        html.Code(
            f"({s_style:.1f}×{style_w:.0%}) + ({s_laliga:.0f}×{laliga_w:.0%}) + "
            f"({s_budget:.0f}×{budget_w:.0%}) + ({s_squad:.0f}×{squad_w:.0%})"
            f" = {global_:.1f}  →  {score_10}/10",
            style={"fontSize": "10px", "background": "#F3F4F6", "padding": "4px 8px",
                   "borderRadius": "4px", "display": "inline-block", "marginLeft": "4px"},
        ),
    ], style={"marginBottom": "10px"})

    # ── 2. Desglose estilo (eje a eje) ───────────────────────────────────────
    total_w = sum(sp.get("weight", 0) for sp in target.values()) or 1.0
    axis_rows = []
    for axis, spec in sorted(target.items(), key=lambda x: x[1].get("weight", 0), reverse=True):
        label    = _AXIS_LABELS_ES.get(axis, axis)
        ideal    = spec.get("ideal")
        w        = spec.get("weight", 0)
        coach_v  = axes.get(axis)
        close_v  = style_detail.get(axis)
        descrip  = spec.get("descripcion", "")
        src_col  = spec.get("columna", "")

        def _fmt(v): return f"{v:.1f}" if isinstance(v, (int, float)) else "—"

        if close_v is not None:
            close_color = _cls_color(close_v)
            contib_txt  = f"{w/total_w*close_v:.1f}"
        else:
            close_color = "#9CA3AF"
            contib_txt  = "—"

        # Tooltip-like: fuente del dato
        src_note = (f" [{src_col}]" if src_col else "")
        axis_rows.append(html.Tr([
            html.Td([
                html.Span(label, style={"fontWeight": "600"}),
                html.Br(),
                html.Span(f"OPTA{src_note}", style={"fontSize": "8px", "color": "#9CA3AF"}),
            ], style=_td_s),
            html.Td(_fmt(w * 100) + "%", style=_td_r),
            html.Td(_fmt(ideal),          style=_td_r),
            html.Td(_fmt(coach_v),        style=_td_r),
            html.Td(
                _fmt(close_v),
                style={**_td_r, "fontWeight": "700", "color": close_color},
            ),
            html.Td(contib_txt, style={**_td_r, "color": "#6B7280"}),
        ]))

    style_section = html.Div([
        html.P([
            html.Span(f"① Estilo de juego — {s_style:.1f}/100",
                      style={"fontWeight": "700", "fontSize": "11px"}),
            html.Span(f" (peso {style_w:.0%} del total)",
                      style={"fontSize": "10px", "color": "#6B7280"}),
            _badge("datos OPTA", "#EFF6FF", "#1D4ED8"),
        ], style={"margin": "0 0 4px"}),
        html.P(
            "Cercanía del estilo del entrenador al ADN objetivo del Rayo. "
            "Cada eje = 100 − |valor_coach − ideal_Rayo|, ponderado por peso del eje.",
            style={"fontSize": "9px", "color": "#9CA3AF", "margin": "0 0 6px"}
        ),
        html.Table([
            html.Thead(html.Tr([
                html.Th("Eje",          style=_th_s),
                html.Th("Peso",         style={**_th_s, "textAlign": "right"}),
                html.Th("Ideal Rayo",   style={**_th_s, "textAlign": "right"}),
                html.Th("Coach",        style={**_th_s, "textAlign": "right"}),
                html.Th("Cercanía",     style={**_th_s, "textAlign": "right"}),
                html.Th("Contribución", style={**_th_s, "textAlign": "right"}),
            ])),
            html.Tbody(axis_rows),
        ], style={"width": "100%", "borderCollapse": "collapse", "marginBottom": "4px"}),
        html.P(
            f"Score estilo = Σ(Contribución) / Σ(Pesos) = {s_style:.1f}",
            style={"fontSize": "9px", "color": "#9CA3AF", "fontStyle": "italic", "margin": "0"},
        ),
    ], style={"background": "#F9FAFB", "border": "1px solid #E5E7EB",
               "borderRadius": "6px", "padding": "8px 10px", "marginBottom": "8px"})

    # ── 3. Exp. LaLiga ───────────────────────────────────────────────────────
    laliga_seasons = int(c.get("laliga_seasons") or 0)
    laliga_section = html.Div([
        html.P([
            html.Span(f"② Experiencia LaLiga — {s_laliga:.0f}/100",
                      style={"fontWeight": "700", "fontSize": "11px"}),
            html.Span(f" (peso {laliga_w:.0%})",
                      style={"fontSize": "10px", "color": "#6B7280"}),
            _badge("datos OPTA", "#EFF6FF", "#1D4ED8"),
        ], style={"margin": "0 0 4px"}),
        html.P([
            html.Span(f"{laliga_seasons} temporadas LaLiga en el dataset. ",
                      style={"fontSize": "10px", "color": "#374151"}),
            html.Span(f"Fórmula: min({laliga_seasons}/4 × 100, 100) = {s_laliga:.0f}.",
                      style={"fontSize": "10px", "color": "#6B7280"}),
        ], style={"margin": "0"}),
        html.P(
            "Equipos y temporadas cubiertos: " +
            "; ".join(f"{t} ({s})" for t, s in c.get("coverage", {}).get("matched", [])),
            style={"fontSize": "9px", "color": "#9CA3AF", "margin": "4px 0 0"},
        ),
    ], style={"background": "#F9FAFB", "border": "1px solid #E5E7EB",
               "borderRadius": "6px", "padding": "8px 10px", "marginBottom": "8px"})

    # ── 4. Presupuesto ───────────────────────────────────────────────────────
    salary = c.get("salary_estimate_eur") or 0
    target_sal = eco.get("target_salary_eur", 1_500_000)
    max_sal = eco.get("max_salary_eur", 2_500_000)
    def _fmt_eur(v): return f"{v/1e6:.1f}M€" if v >= 1e6 else (f"{v:,.0f}€" if v else "N/D")
    if salary <= 0:
        budget_logic = "Salario no disponible → puntuación neutra (60/100)."
    elif salary <= target_sal:
        budget_logic = f"Salario estimado {_fmt_eur(salary)} ≤ objetivo Rayo {_fmt_eur(target_sal)} → 100/100."
    elif salary <= max_sal:
        budget_logic = (f"Salario {_fmt_eur(salary)} entre objetivo ({_fmt_eur(target_sal)}) "
                        f"y máximo ({_fmt_eur(max_sal)}) → penalización proporcional.")
    else:
        budget_logic = f"Salario {_fmt_eur(salary)} supera el máximo {_fmt_eur(max_sal)} → 30/100."

    budget_section = html.Div([
        html.P([
            html.Span(f"③ Encaje presupuesto — {s_budget:.0f}/100",
                      style={"fontWeight": "700", "fontSize": "11px"}),
            html.Span(f" (peso {budget_w:.0%})",
                      style={"fontSize": "10px", "color": "#6B7280"}),
            _badge("coaches.yaml", "#FEF9C3", "#92400E"),
        ], style={"margin": "0 0 4px"}),
        html.P(budget_logic, style={"fontSize": "10px", "color": "#374151", "margin": "0"}),
    ], style={"background": "#F9FAFB", "border": "1px solid #E5E7EB",
               "borderRadius": "6px", "padding": "8px 10px", "marginBottom": "8px"})

    # ── 5. Compatibilidad plantilla ──────────────────────────────────────────
    needs = _load_needs()
    missing_roles  = set(needs.get("missing", []))
    reinforce_roles = set(needs.get("reinforce", []))
    gap_roles      = missing_roles | reinforce_roles
    cap            = needs.get("squad_cap", 25)
    n_profiled     = needs.get("n_profiled", 0)

    poss_v  = axes.get("posesion")
    trans_v = axes.get("uso_transiciones")
    press_v = axes.get("presion_alta")
    vert_v  = axes.get("verticalidad")

    def _fmt_ax(v): return f"{v:.0f}" if v is not None else "n/d"

    # Calcular qué penaliza y qué bonifica específicamente
    issues, goods = [], []
    if {"Central dominador", "Mediocentro organizador"} & gap_roles and poss_v and poss_v >= 55:
        issues.append(f"Posesión alta ({_fmt_ax(poss_v)}) sin constructores (faltan centrales/organizadores)")
    if "Extremo asociativo" in gap_roles and poss_v and poss_v >= 60 and (vert_v is None or vert_v < 55):
        issues.append("Exige extremos asociativos (carencia en plantilla)")
    if "Interior llegador" in gap_roles and axes.get("tendencia_ofensiva", 0) >= 65:
        issues.append("Tendencia ofensiva alta sin interiores llegadores")
    if "Mediocentro recuperador" not in gap_roles and press_v and press_v >= 60:
        goods.append(f"Presión alta ({_fmt_ax(press_v)}) compatible con recuperadores disponibles")
    if trans_v and trans_v >= 60:
        goods.append(f"Transiciones ({_fmt_ax(trans_v)}) encajan con el perfil de la plantilla")
    if poss_v and 45 <= poss_v <= 62:
        goods.append(f"Posesión equilibrada ({_fmt_ax(poss_v)}) — no exige constructores especializados")
    if "Delantero móvil" not in gap_roles and vert_v and vert_v >= 58:
        goods.append(f"Juego vertical ({_fmt_ax(vert_v)}) aprovecha delanteros móviles disponibles")

    def _mini_chip(txt, bg, fg):
        return html.Span(txt, style={"fontSize": "9px", "padding": "2px 7px", "borderRadius": "99px",
                                     "background": bg, "color": fg, "marginRight": "4px",
                                     "marginBottom": "3px", "display": "inline-block"})

    squad_section = html.Div([
        html.P([
            html.Span(f"④ Compatibilidad con la plantilla — {s_squad:.0f}/100",
                      style={"fontWeight": "700", "fontSize": "11px"}),
            html.Span(f" (peso {squad_w:.0%})",
                      style={"fontSize": "10px", "color": "#6B7280"}),
            _badge("squad_profile.json", "#EFF6FF", "#1D4ED8"),
        ], style={"margin": "0 0 4px"}),
        html.P(
            f"Plantilla de {cap} jugadores — {n_profiled} perfilados con datos OPTA. "
            "Penaliza si el estilo exige perfiles con carencia; bonifica si el estilo aprovecha lo disponible.",
            style={"fontSize": "10px", "color": "#374151", "margin": "0 0 6px"}
        ),
        # Tensiones
        html.Div(
            [_mini_chip(f"⚠ {t}", "#FEF2F2", "#991B1B") for t in issues]
            + [_mini_chip(f"✓ {g}", "#F0FDF4", "#166534") for g in goods]
            or [html.Span("Sin señales claras de desajuste o sintonía.", style={"fontSize": "9px", "color": "#9CA3AF"})],
            style={"display": "flex", "flexWrap": "wrap", "marginBottom": "4px"},
        ),
        # Roles faltantes en contexto
        html.Div([
            html.Span("Sin cobertura: ", style={"fontSize": "9px", "color": "#991B1B", "fontWeight": "700"}),
            html.Span(", ".join(sorted(missing_roles)) or "—", style={"fontSize": "9px", "color": "#374151"}),
            html.Span("  ·  A reforzar: ", style={"fontSize": "9px", "color": "#92400E", "fontWeight": "700", "marginLeft": "6px"}),
            html.Span(", ".join(sorted(reinforce_roles)) or "—", style={"fontSize": "9px", "color": "#374151"}),
        ], style={"marginTop": "2px"}),
    ], style={"background": "#F9FAFB", "border": "1px solid #E5E7EB",
               "borderRadius": "6px", "padding": "8px 10px", "marginBottom": "4px"})

    return html.Details([
        html.Summary(
            [html.I(className="ti ti-math-function",
                    style={"marginRight": "5px", "color": "#B8960C"}),
             "¿Cómo se calcula la puntuación? — desglose completo"],
            style={"fontSize": "11px", "fontWeight": "700", "color": "#1D4ED8",
                   "cursor": "pointer", "userSelect": "none", "marginBottom": "8px"},
        ),
        formula_row,
        style_section,
        laliga_section,
        budget_section,
        squad_section,
    ], open=True, style={"background": "#fff", "border": "1px solid #DBEAFE",
                          "borderRadius": "8px", "padding": "10px 12px", "marginBottom": "12px"})


def _detail_panel(c, manual):
    if not c:
        return html.Div("Selecciona un entrenador para ver el analisis completo.",
                        style={"color": "#6B7280", "fontSize": "13px", "padding": "20px"})
    ev = c.get("evaluation", {})
    axes = c.get("axes", {})
    name = c["name"]
    m = manual.get(name, {"pros": [], "contras": []})
    sub = ev.get("subscores", {})
    risks = ev.get("risks", {})

    bio = " · ".join([x for x in [
        (f"{c.get('age')} años" if c.get('age') else None),
        (c.get('nationality') or None),
        (c.get('last_club') or None),
        ("Libre" if c.get('available') else "Con equipo"),
        (f"{c.get('laliga_seasons',0)} temp. LaLiga"),
    ] if x])
    return html.Div([
        html.Div([
            html.Div([
                _coach_avatar(name, 84, radius="12px"),
                dcc.Upload(
                    id="upload-coach-photo",
                    children=html.Div([
                        html.I(className="ti ti-camera", style={"fontSize": "11px", "marginRight": "3px"}),
                        "Cambiar foto",
                    ]),
                    accept="image/*",
                    style={"background": "#F3F4F6", "border": "1px solid #D1D5DB",
                           "borderRadius": "6px", "padding": "4px 8px", "cursor": "pointer",
                           "fontSize": "10px", "fontWeight": "600", "color": "#374151",
                           "textAlign": "center", "marginTop": "6px", "display": "block"},
                    multiple=False,
                ),
                html.Div(id="photo-upload-status",
                         style={"fontSize": "9px", "color": "#6B7280", "marginTop": "3px",
                                "textAlign": "center"}),
            ], style={"display": "flex", "flexDirection": "column", "alignItems": "center",
                      "width": "90px", "flexShrink": "0"}),
            html.Div([
                html.Div([
                    html.H3(name, style={"margin": "0", "fontSize": "18px", "color": "#1A1A2E"}),
                    html.Span(f"{ev.get('score_10','n/d')}/10",
                              style={"fontSize": "22px", "fontWeight": "700",
                                     "color": _score_color(ev.get("score_10")), "marginLeft": "auto"}),
                ], style={"display": "flex", "alignItems": "center"}),
                html.P(c.get("style_main", ""), style={"fontSize": "12px", "color": "#1D4ED8",
                       "fontWeight": "600", "margin": "2px 0 2px"}),
                html.P(bio, style={"fontSize": "11px", "color": "#6B7280", "margin": "0"}),
                html.Button([html.I(className="ti ti-file-download", style={"marginRight": "6px"}),
                             "Descargar PDF"], id="dl-coach-btn", n_clicks=0,
                            style={"marginTop": "8px", "background": "#1A1A2E", "color": "#fff",
                                   "border": "none", "borderRadius": "8px", "padding": "6px 14px",
                                   "fontSize": "12px", "fontWeight": "600", "cursor": "pointer"}),
                dcc.Download(id="dl-coach"),
                dcc.Store(id="current-coach", data=name),
            ], style={"flex": "1"}),
        ], style={"display": "flex", "gap": "14px", "alignItems": "flex-start", "marginBottom": "10px"}),

        # Descripcion automatica
        html.Div([
            html.Span("Estilo generado automaticamente desde los datos",
                      style={"fontSize": "9px", "fontWeight": "700", "color": "#9CA3AF",
                             "textTransform": "uppercase", "letterSpacing": ".05em"}),
            html.P(c.get("description_auto", ""), style={"fontSize": "12px", "color": "#374151",
                   "lineHeight": "1.6", "margin": "4px 0 0"}),
        ], style={"background": "#F9FAFB", "borderRadius": "8px", "padding": "10px 12px",
                  "marginBottom": "12px"}),

        # ── Desglose del score ──────────────────────────────────────────────
        _score_breakdown(ev, c, _load_dna()),

        dbc.Row([
            dbc.Col([
                html.P("Ejes de estilo", style={"fontSize": "10px", "fontWeight": "700",
                       "color": "#9CA3AF", "textTransform": "uppercase", "marginBottom": "8px"}),
                _radar_chart(axes, _DNA_DEFAULTS),
                *[_axis_bar(lab, axes.get(k)) for k, lab in AXES_SHOW],
            ], md=6),
            dbc.Col([
                html.P("Sub-scores de encaje", style={"fontSize": "10px", "fontWeight": "700",
                       "color": "#9CA3AF", "textTransform": "uppercase", "marginBottom": "8px"}),
                *[_axis_bar({"estilo": "Estilo", "experiencia_laliga": "Exp. LaLiga",
                             "encaje_presupuesto": "Presupuesto", "compatibilidad_plantilla": "Plantilla"}[k], v)
                  for k, v in sub.items()],
                html.P("Riesgos", style={"fontSize": "10px", "fontWeight": "700", "color": "#9CA3AF",
                       "textTransform": "uppercase", "margin": "12px 0 8px"}),
                html.Div([
                    html.Span([html.Span(RISK_LABELS.get(k, k) + ": ", style={"color": "#6B7280"}),
                               html.Span(v, style={"fontWeight": "700",
                                   "color": RISK_COLOR.get(v, RISK_COLOR['n/d'])[1]})],
                        style={"fontSize": "10px", "padding": "3px 8px", "borderRadius": "99px",
                               "background": RISK_COLOR.get(v, RISK_COLOR['n/d'])[0],
                               "marginRight": "5px", "marginBottom": "5px", "display": "inline-block"})
                    for k, v in risks.items()
                ]),
            ], md=6),
        ]),

        html.Hr(style={"margin": "14px 0", "borderColor": "#F3F4F6"}),

        dbc.Row([
            dbc.Col([
                html.P("Pros", style={"fontSize": "11px", "fontWeight": "700", "color": "#166534",
                       "marginBottom": "6px"}),
                html.Div(_chip_list(ev.get("pros_auto", []), "#F0FDF4", "#166534")),
                html.Div(_chip_list(m.get("pros", []), "#ECFDF5", "#047857", removable_type="del-pro"),
                         id="manual-pros"),
                html.Div([
                    dcc.Input(id="inp-pro", placeholder="Anadir pro manual...", type="text",
                              style={"fontSize": "11px", "flex": "1", "padding": "5px 8px",
                                     "border": "1px solid #D1D5DB", "borderRadius": "6px"}),
                    html.Button("+", id="add-pro", n_clicks=0, style={"marginLeft": "5px",
                        "background": "#166534", "color": "#fff", "border": "none",
                        "borderRadius": "6px", "padding": "5px 12px", "cursor": "pointer"}),
                ], style={"display": "flex", "marginTop": "6px"}),
            ], md=6),
            dbc.Col([
                html.P("Contras", style={"fontSize": "11px", "fontWeight": "700", "color": "#991B1B",
                       "marginBottom": "6px"}),
                html.Div(_chip_list(ev.get("contras_auto", []), "#FEF2F2", "#991B1B")),
                html.Div(_chip_list(m.get("contras", []), "#FFF1F2", "#9F1239", removable_type="del-con"),
                         id="manual-contras"),
                html.Div([
                    dcc.Input(id="inp-con", placeholder="Anadir contra manual...", type="text",
                              style={"fontSize": "11px", "flex": "1", "padding": "5px 8px",
                                     "border": "1px solid #D1D5DB", "borderRadius": "6px"}),
                    html.Button("+", id="add-con", n_clicks=0, style={"marginLeft": "5px",
                        "background": "#991B1B", "color": "#fff", "border": "none",
                        "borderRadius": "6px", "padding": "5px 12px", "cursor": "pointer"}),
                ], style={"display": "flex", "marginTop": "6px"}),
            ], md=6),
        ]),
        html.P(["Cobertura: ", html.Span(", ".join(c.get("coverage", {}).get("teams", []) or ["-"])),
                f" · {c.get('coverage',{}).get('n_rows',0)} temporadas en datos"],
               style={"fontSize": "10px", "color": "#9CA3AF", "marginTop": "12px"}),
    ])


def layout(**_params):
    profiles = _load_profiles()
    if not profiles:
        return html.Div([
            html.H1("Casting de Entrenadores", className="page-title"),
            html.Div("No hay perfiles calculados. Ejecuta: python scripts/build_profiles.py",
                     style={"background": "#FFFBEB", "border": "1px solid #FDE68A",
                            "borderRadius": "10px", "padding": "16px", "color": "#92400E"}),
        ])
    names = [c["name"] for c in profiles]
    available_cnt = sum(1 for c in profiles if c.get("available"))
    top = profiles[0]
    styles = sorted({c.get("style_main", "") for c in profiles if c.get("style_main")})

    def _kpi(icon, label, value, sub, _grad=None, _light=None, variant=""):
        return html.Div([
            html.Div([html.I(className=f"ti {icon}")], className=f"kpi-icon {variant}"),
            html.Div(value, className="kpi-value"),
            html.Div(label, className="kpi-label"),
            html.Div(sub,   className="kpi-sub"),
        ], className=f"kpi-modern {variant}")

    top_score = top["evaluation"].get("score_10", "?")

    return html.Div([
        dcc.Store(id="manual-refresh", data=0),

        # ── Hero ──────────────────────────────────────────────────────────────
        html.Div([
            html.Div([
                html.Div([html.I(className="ti ti-chalkboard",
                           style={"fontSize":"26px","color":"#fff"})],
                    style={"background":"rgba(227,6,19,.20)","borderRadius":"12px",
                           "padding":"10px","marginRight":"18px","flexShrink":"0",
                           "border":"1px solid rgba(227,6,19,.30)"}),
                html.Div([
                    html.Div("PLANIFICACIÓN DEPORTIVA", style={"fontSize":"9px","fontWeight":"700",
                        "color":"rgba(255,255,255,.45)","letterSpacing":".14em","marginBottom":"3px"}),
                    html.H1("Casting de Entrenadores", style={"fontSize":"22px","fontWeight":"900",
                        "color":"#fff","margin":"0 0 2px","letterSpacing":"-.02em"}),
                    html.Div("Estilo y encaje calculados automáticamente · Rayo Vallecano 2026/27",
                        style={"fontSize":"10.5px","color":"rgba(255,255,255,.45)"}),
                ]),
            ], style={"display":"flex","alignItems":"center","flex":"1"}),
            html.Div([
                *[html.Div([
                    html.Div(v, style={"fontSize":"22px","fontWeight":"900","color":"#fff","lineHeight":"1"}),
                    html.Div(l, style={"fontSize":"9px","color":"rgba(255,255,255,.45)","fontWeight":"600","marginTop":"2px"}),
                ], style={"textAlign":"center","padding":"0 16px","borderRight":s})
                  for v,l,s in [
                    (str(len(profiles)), "técnicos", "1px solid rgba(255,255,255,.12)"),
                    (str(available_cnt), "libres", "1px solid rgba(255,255,255,.12)"),
                    (f"{top_score}/10", "mejor encaje", "none"),
                ]],
            ], style={"display":"flex","alignItems":"center","flexShrink":"0"}),
        ], style={"background":"linear-gradient(135deg,#0A0B0E 0%,#1E2028 60%,#141519 100%)",
                  "borderRadius":"18px","padding":"20px 26px","marginBottom":"18px",
                  "display":"flex","justifyContent":"space-between","alignItems":"center",
                  "boxShadow":"0 8px 32px rgba(0,0,0,.28)","borderLeft":"4px solid #E30613"}),

        # ── KPIs ──────────────────────────────────────────────────────────────
        html.Div("RESUMEN DEL CASTING", className="section-label"),
        dbc.Row([
            dbc.Col(_kpi("ti-chalkboard","Técnicos analizados",str(len(profiles)),"con estilo calculado"), md=3),
            dbc.Col(_kpi("ti-user-check","Sin equipo actual",str(available_cnt),"disponibles ahora","","","success"), md=3),
            dbc.Col(_kpi("ti-trophy","Mejor encaje",top["name"].split()[-1],f"Score: {top_score}/10","","","warning"), md=3),
            dbc.Col(_kpi("ti-target","Necesidad clave","Banquillo","sucesor de I. Pérez","","","danger"), md=3),
        ], className="g-3 mb-4"),

        # Panel de ADN editable
        html.Div([
            html.Div([
                html.Span("ADN Rayo — estilo objetivo del club",
                          style={"fontSize": "12px", "fontWeight": "700", "color": "#1A1A2E"}),
                html.Span("  calculado automáticamente · ajusta los sliders para personalizar",
                          style={"fontSize": "10px", "color": "#9CA3AF", "marginLeft": "6px"}),
            ], style={"marginBottom": "6px"}),

            # ── Caja metodología (siempre visible, compacta) ─────────────────
            html.Details([
                html.Summary("¿Cómo se calcula el ADN Rayo?",
                             style={"fontSize": "10px", "color": "#B8960C", "cursor": "pointer",
                                    "fontWeight": "600", "marginBottom": "6px"}),
                html.Div([
                    html.P([
                        html.Strong("Fuente: "),
                        "team_seasons.parquet (estadísticas OPTA por equipo y temporada).",
                    ], style={"fontSize": "10px", "color": "#374151", "margin": "0 0 4px"}),
                    html.P([
                        html.Strong("Proceso: "),
                        "Se toma la temporada más reciente disponible del Rayo Vallecano y se "
                        "compara con todos los equipos de la misma liga y temporada. Para cada "
                        "eje se calcula el ", html.Strong("percentil del Rayo (0-100)"),
                        " — un valor de 80 significa que el Rayo supera al 80% de los equipos "
                        "de su liga en esa métrica.",
                    ], style={"fontSize": "10px", "color": "#374151", "margin": "0 0 4px"}),
                    html.Table([
                        html.Thead(html.Tr([
                            html.Th("Eje ADN", style=_th),
                            html.Th("Métrica OPTA (columna)", style=_th),
                            html.Th("Dirección", style=_th),
                            html.Th("Descripción", style=_th),
                        ])),
                        html.Tbody([
                            html.Tr([html.Td(e, style=_td), html.Td(m, style=_td),
                                     html.Td(d, style=_td), html.Td(desc, style=_td)])
                            for e, m, d, desc in [
                                ("Presión alta",          "PPDA",                    "↓ menor = mejor",  "Pases permitidos por acción defensiva — cuanto menor el PPDA, más agresiva la presión"),
                                ("Posesión",              "possession_percentage",   "↑ mayor = mejor",  "% medio de posesión por partido"),
                                ("Solidez defensiva",     "goals_conceded / partido","↓ menor = mejor",  "Goles encajados por partido"),
                                ("Tendencia ofensiva",    "goals / partido",         "↑ mayor = mejor",  "Goles marcados por partido"),
                                ("Verticalidad",          "successful_long_passes",  "↑ mayor = mejor",  "Total de pases largos completados en la temporada"),
                                ("Intensidad defensiva",  "tackles_won",             "↑ mayor = mejor",  "Total de entradas ganadas en la temporada"),
                                ("Uso de transiciones",   "recoveries",              "↑ mayor = mejor",  "Total de recuperaciones de balón en la temporada"),
                            ]
                        ]),
                    ], style={"width": "100%", "borderCollapse": "collapse",
                              "fontSize": "9px", "marginTop": "4px"}),
                    html.P(
                        "Los percentiles se normalizan siempre de 0 a 100 "
                        "(100 = mejor de la liga en esa dimensión). "
                        "Las métricas invertidas (PPDA, goles encajados) se transforman como "
                        "percentil = 100 − rango original.",
                        style={"fontSize": "9px", "color": "#9CA3AF", "margin": "6px 0 0",
                               "fontStyle": "italic"}),
                ], style={"background": "white", "border": "1px solid #FECACA",
                          "borderRadius": "8px", "padding": "10px 12px", "marginBottom": "8px"}),
            ], style={"marginBottom": "10px"}),

            dbc.Row([
                dbc.Col([html.Span(lab, style={"fontSize": "10px", "color": "#6B7280"}),
                    dcc.Slider(0, 100, 1, value=_DNA_DEFAULTS.get(axis, 50), id=sid,
                               marks=None, tooltip={"placement": "bottom", "always_visible": False},
                               updatemode="mouseup")],
                    md=3, style={"marginBottom": "8px"})
                for sid, lab, axis in DNA_SLIDERS
            ], className="g-2"),
            html.Div([
                dbc.Button([
                    html.I(className="ti ti-refresh", style={"marginRight": "5px"}),
                    "Recalcular desde datos",
                ], id="btn-adn-suggest", color="light", size="sm",
                   style={"fontSize": "11px", "border": "1px solid #D1D5DB",
                          "marginTop": "8px"}),
                html.Div(id="adn-suggest-output",
                         style={"marginTop": "8px", "fontSize": "11px"}),
            ]),
        ], style={"background": "#FFF8F8", "border": "1px solid #FECACA", "borderRadius": "12px",
                  "padding": "14px 18px", "marginBottom": "14px"}),

        html.Div([
            html.Div([
                html.I(className="ti ti-adjustments-horizontal",
                       style={"fontSize":"14px","color":"#F97316","marginRight":"7px"}),
                html.Span("FILTROS", style={"fontSize":"9px","fontWeight":"700",
                    "color":"#F97316","letterSpacing":".10em"}),
            ], style={"marginBottom":"12px","display":"flex","alignItems":"center"}),
            dbc.Row([
                dbc.Col([html.Span("Disponibilidad", className="filter-label"),
                    dcc.Dropdown([{"label": "Todos", "value": "all"},
                                  {"label": "Solo libres", "value": "free"},
                                  {"label": "Con equipo", "value": "busy"}],
                                 value="all", id="f-avail", clearable=False)], md=3),
                dbc.Col([html.Span("Estilo (calculado)", className="filter-label"),
                    dcc.Dropdown([{"label": "Todos", "value": "all"}] +
                                 [{"label": s, "value": s} for s in styles],
                                 value="all", id="f-style", clearable=False)], md=4),
                dbc.Col([html.Span("Fit Rayo mínimo /10", className="filter-label"),
                    dcc.Slider(0, 10, 1, value=0, id="f-minscore",
                               marks={0: "0", 5: "5", 7: "7", 9: "9"},
                               tooltip={"placement": "bottom"})], md=5),
            ], className="g-2"),
        ], style={"background":"#fff","border":"1px solid #E5E7EB","borderRadius":"14px",
                  "padding":"18px 20px","marginBottom":"16px",
                  "boxShadow":"0 2px 8px rgba(0,0,0,.05)"}),

        html.Div(id="coaches-count", style={"fontSize": "12px", "color": "#6B7280", "margin": "8px 0"}),
        dcc.Loading(
            html.Div(id="coaches-grid"),
            type="dot",
            color=RAYO_RED,
            delay_show=300,
        ),

        html.Div([
            html.Div([
                html.I(className="ti ti-user-search",
                       style={"fontSize":"14px","color":"#F97316","marginRight":"7px"}),
                html.Span("ANÁLISIS DEL CANDIDATO", style={"fontSize":"9px","fontWeight":"700",
                    "color":"#F97316","letterSpacing":".10em"}),
            ], style={"marginBottom":"10px","display":"flex","alignItems":"center"}),
            dcc.Dropdown(names, value=names[0], id="coach-select", clearable=False,
                         style={"maxWidth": "360px", "marginBottom": "12px"}),
            dcc.Loading(
                html.Div(id="coach-detail"),
                type="circle",
                color=RAYO_RED,
                delay_show=200,
            ),
            html.Div(id="coach-pdf-error", style={"marginTop": "8px"}),
        ], style={"background": "#fff", "border": "1px solid #E5E7EB", "borderRadius": "12px",
                  "padding": "18px 20px", "marginTop": "18px"}),
        criteria_accordion("entrenadores"),
    ])


@callback(Output("coaches-grid", "children"), Output("coaches-count", "children"),
          Input("f-avail", "value"), Input("f-style", "value"), Input("f-minscore", "value"),
          *[Input(sid, "value") for sid, _, _ in DNA_SLIDERS])
def update_grid(avail, style, minscore, *slider_vals):
    profiles = _load_profiles()
    ideals = {axis: slider_vals[i] for i, (_, _, axis) in enumerate(DNA_SLIDERS)}
    if any(v != _DNA_DEFAULTS.get(a) for a, v in ideals.items()):
        profiles = _reevaluate(profiles, ideals)
    if avail == "free":
        profiles = [c for c in profiles if c.get("available")]
    elif avail == "busy":
        profiles = [c for c in profiles if not c.get("available")]
    if style and style != "all":
        profiles = [c for c in profiles if c.get("style_main") == style]
    profiles = [c for c in profiles if (c.get("evaluation", {}).get("score_10") or 0) >= (minscore or 0)]
    grid = html.Div([_coach_card(c) for c in profiles],
                    style={"display": "grid", "gridTemplateColumns": "repeat(auto-fill,minmax(330px,1fr))",
                           "gap": "14px"})
    return grid, f"{len(profiles)} entrenadores (ordenados por encaje)"


@callback(Output("coach-detail", "children"),
          Input("coach-select", "value"), Input("manual-refresh", "data"))
def update_detail(name, _refresh):
    profiles = {c["name"]: c for c in _load_profiles()}
    return _detail_panel(profiles.get(name), _load_manual())


@callback(Output("manual-refresh", "data"),
          Input("add-pro", "n_clicks"), Input("add-con", "n_clicks"),
          Input({"type": "del-pro", "index": ALL}, "n_clicks"),
          Input({"type": "del-con", "index": ALL}, "n_clicks"),
          State("coach-select", "value"), State("inp-pro", "value"), State("inp-con", "value"),
          State("manual-refresh", "data"), prevent_initial_call=True)
def edit_manual(add_pro, add_con, del_pro, del_con, name, pro_txt, con_txt, refresh):
    manual = _load_manual()
    entry = manual.setdefault(name, {"pros": [], "contras": []})
    trig = ctx.triggered_id
    changed = False
    if trig == "add-pro" and pro_txt:
        entry["pros"].append(pro_txt.strip()); changed = True
    elif trig == "add-con" and con_txt:
        entry["contras"].append(con_txt.strip()); changed = True
    elif isinstance(trig, dict) and trig.get("type") == "del-pro":
        idx = trig["index"]
        if 0 <= idx < len(entry["pros"]):
            entry["pros"].pop(idx); changed = True
    elif isinstance(trig, dict) and trig.get("type") == "del-con":
        idx = trig["index"]
        if 0 <= idx < len(entry["contras"]):
            entry["contras"].pop(idx); changed = True
    if changed:
        _save_manual(manual)
        return (refresh or 0) + 1
    return no_update


_COACH_PDF_BTN_DEFAULT = [
    html.I(className="ti ti-file-download", style={"marginRight": "6px"}),
    "Descargar PDF",
]
_COACH_PDF_BTN_STYLE = {
    "marginTop": "8px", "background": "#1A1A2E", "color": "#fff",
    "border": "none", "borderRadius": "8px", "padding": "6px 14px",
    "fontSize": "12px", "fontWeight": "600", "cursor": "pointer",
}


@callback(
    Output("dl-coach", "data"),
    Output("coach-pdf-error", "children"),
    Output("dl-coach-btn", "disabled"),
    Output("dl-coach-btn", "children"),
    Input("dl-coach-btn", "n_clicks"),
    State("current-coach", "data"),
    prevent_initial_call=True,
)
def _download_coach_pdf(n, name):
    if not n or not name:
        return no_update, no_update, no_update, no_update
    try:
        from src.reports.coach_dossier import build_coach_dossier
        fname, data = build_coach_dossier(name)
        return dcc.send_bytes(data, fname), "", False, _COACH_PDF_BTN_DEFAULT
    except BaseException as exc:
        import traceback
        traceback.print_exc()
        err = html.Div([
            html.I(className="ti ti-alert-circle",
                   style={"color": "#B8960C", "marginRight": "6px"}),
            html.Span(f"Error generando PDF: {exc}",
                      style={"fontSize": "11px", "color": "#B8960C"}),
            html.Span(" — Vuelve a intentarlo",
                      style={"fontSize": "11px", "color": "#6B7280"}),
        ], style={"display": "flex", "alignItems": "center"})
        return no_update, err, False, _COACH_PDF_BTN_DEFAULT


@callback(
    Output("photo-upload-status", "children"),
    Output("manual-refresh", "data", allow_duplicate=True),
    Input("upload-coach-photo", "contents"),
    State("current-coach", "data"),
    State("manual-refresh", "data"),
    prevent_initial_call=True,
)
def _save_coach_photo(contents, name, refresh):
    """Guarda la foto subida de forma persistente en coach_photo_overrides.json."""
    if not contents or not name:
        return no_update, no_update
    try:
        _save_photo_override(name, contents)
        return "Foto guardada", (refresh or 0) + 1
    except Exception as e:
        return f"Error: {e}", no_update


@callback(
    Output("adn-suggest-output", "children"),
    Input("btn-adn-suggest", "n_clicks"),
)
def _suggest_adn_from_data(n):
    detail = _calc_adn_detail()
    if not detail:
        return html.P("Sin datos suficientes en team_seasons.parquet",
                      style={"fontSize": "10px", "color": "#9CA3AF"})

    meta = detail.pop("_meta", {})
    temporada  = meta.get("temporada", "?")
    liga       = meta.get("liga", "?")
    n_equipos  = meta.get("n_equipos", "?")
    equipo     = meta.get("equipo", "Rayo")

    current = _load_dna()["target_style"]

    header_row = html.Tr([
        html.Th("Eje ADN",           style=_th),
        html.Th("Métrica OPTA",      style=_th),
        html.Th(f"Valor {equipo}",   style=_th),
        html.Th(f"Percentil vs {liga} ({n_equipos} eq.)", style=_th),
        html.Th("Slider actual",     style=_th),
        html.Th("Diferencia",        style=_th),
    ])

    table_rows = []
    for sid, lab, axis in DNA_SLIDERS:
        info     = detail.get(axis, {})
        pct      = info.get("percentil", 50)
        raw      = info.get("valor_rayo")
        metrica  = info.get("metrica_opta", axis)
        invertida = info.get("invertida", False)
        cur      = current.get(axis, {}).get("ideal", 50)
        diff     = pct - cur
        diff_color = "#166534" if diff > 8 else ("#991B1B" if diff < -8 else "#374151")
        raw_str  = f"{raw:.2f}" if raw is not None else "n/d"
        inv_note = " ↓inv." if invertida else ""
        table_rows.append(html.Tr([
            html.Td(lab,                          style=_td),
            html.Td(f"{metrica}{inv_note}",       style={**_td, "fontSize": "9px", "color": "#6B7280"}),
            html.Td(raw_str,                      style={**_td, "textAlign": "right"}),
            html.Td(f"{pct:.0f} / 100",           style={**_td, "fontWeight": "700",
                    "color": "#166534" if pct >= 70 else ("#F59E0B" if pct >= 45 else "#6B7280"),
                    "textAlign": "right"}),
            html.Td(f"{cur:.0f}",                 style={**_td, "textAlign": "right", "color": "#9CA3AF"}),
            html.Td(f"{diff:+.0f}",               style={**_td, "fontWeight": "700",
                    "color": diff_color, "textAlign": "right"}),
        ]))

    table = html.Table(
        [html.Thead(header_row), html.Tbody(table_rows)],
        style={"width": "100%", "borderCollapse": "collapse", "fontSize": "10px",
               "marginBottom": "6px"}
    )

    return html.Div([
        html.P([
            html.Strong(f"Temporada analizada: {temporada}  ·  "),
            f"Liga: {liga}  ·  Equipos comparados: {n_equipos}  ·  Equipo: {equipo}",
        ], style={"fontSize": "10px", "color": "#6B7280", "marginBottom": "6px"}),
        table,
        html.P(
            "Percentil = % de equipos de la liga con valor ≤ al del Rayo (0-100). "
            "Columnas ↓inv. se invierten: menor valor bruto → mayor percentil. "
            "Diferencia = percentil calculado − valor del slider.",
            style={"fontSize": "9px", "color": "#9CA3AF", "fontStyle": "italic", "margin": "0"}),
    ])
