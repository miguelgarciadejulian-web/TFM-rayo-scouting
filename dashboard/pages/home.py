# -*- coding: utf-8 -*-
"""
Página de inicio — Dashboard ejecutivo de la dirección deportiva.
Muestra KPIs reales de la plantilla, gráficos automáticos y navegación rápida.
"""
from __future__ import annotations
import json
import sys
from datetime import date
from pathlib import Path

import dash
from dash import html, dcc
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from dashboard.components.chart_theme import apply_theme, RAYO_RED, RAYO_DARK, C_POSITIVE, C_WARNING, GRAPH_CONFIG_SIMPLE, hex_to_rgba, sequential_reds
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.utils.config import settings  # noqa: E402

dash.register_page(__name__, path="/", name="Inicio")
PROC   = Path(settings()["paths"]["data_processed"])
ROOT   = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "club_profile.yaml"

_ROJO = "#E30613"
_AZUL = "#1A1A2E"
_GRAY = "#6B7280"


# ---------------------------------------------------------------------------
# Carga de datos
# ---------------------------------------------------------------------------

def _load_squad_data() -> dict:
    defaults = {
        "n_players": 0, "avg_age": 0.0, "total_mv": 0,
        "expiring_1y": 0, "expiring_6m": 0, "loans_in": 0, "loans_out": 0,
        "positions": {}, "ages": [], "contract_years": [],
        "expiring_names": [], "loan_names": [],
    }
    if not CONFIG.exists():
        return defaults
    try:
        data = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
        squad = data.get("squad_2025_26", {})
        today = date.today()
        players: list[dict] = []
        for group in squad.values():
            if isinstance(group, list):
                for p in group:
                    if isinstance(p, dict) and p.get("name"):
                        players.append(p)
        if not players:
            return defaults
        ages = [p["age"] for p in players if p.get("age")]
        mvs  = [p.get("market_value", 0) or 0 for p in players]
        positions: dict[str, int] = {}
        expiring: list[str] = []
        expiring_6m: list[str] = []
        loans: list[str] = []
        for p in players:
            pos = p.get("position", "?")
            positions[pos] = positions.get(pos, 0) + 1
            if p.get("loan_from"):
                loans.append(p["name"])
            ce = p.get("contract_end") or ""
            if ce:
                try:
                    ce_date = date.fromisoformat(str(ce)[:10])
                    days_left = (ce_date - today).days
                    if days_left <= 365:
                        expiring.append(p["name"])
                    if days_left <= 182:
                        expiring_6m.append(p["name"])
                except (ValueError, TypeError):
                    pass
        return {
            "n_players": len(players),
            "avg_age": round(sum(ages) / len(ages), 1) if ages else 0.0,
            "total_mv": sum(mvs),
            "expiring_1y": len(expiring),
            "expiring_6m": len(expiring_6m),
            "loans_in": len(loans),
            "loans_out": 0,
            "positions": positions,
            "ages": sorted(ages),
            "expiring_names": expiring,
            "loan_names": loans,
        }
    except Exception:
        return defaults


def _load_scouting_kpis() -> dict:
    k = {"candidates": 0, "ligas": 0, "entrenadores": 0}
    try:
        mp = PROC / "master_players.parquet"
        if mp.exists():
            df = pd.read_parquet(mp, columns=["name", "league"])
            k["candidates"] = df["name"].nunique()
            k["ligas"]      = df["league"].nunique()
    except Exception:
        pass
    try:
        cp = PROC / "coach_profiles.json"
        if cp.exists():
            k["entrenadores"] = len(json.load(open(cp, encoding="utf-8")))
    except Exception:
        pass
    return k


# ---------------------------------------------------------------------------
# Componentes visuales
# ---------------------------------------------------------------------------

def _kpi(label, value, sub, color="#E30613", icon=None, border_color=None):
    bc = border_color or color
    return html.Div([
        html.Div([
            html.I(className=f"ti {icon}", style={"fontSize": "18px", "color": bc,
                   "marginRight": "6px"}) if icon else html.Span(),
            html.P(label, className="kpi-label"),
        ], style={"display": "flex", "alignItems": "center"}),
        html.P(str(value), className="kpi-value", style={"color": bc}),
        html.P(sub, className="kpi-sub"),
    ], className="kpi-modern", style={"borderTop": f"3px solid {bc}"})


def _badge(text, color="#E30613"):
    return html.Span(text, style={
        "background": f"{color}18", "color": color,
        "fontSize": "10px", "fontWeight": "700", "borderRadius": "12px",
        "padding": "2px 8px", "marginTop": "6px", "display": "inline-block",
    })


def _nav_card(icon, title, desc, href, color, badge_text=None):
    return dcc.Link(html.Div([
        html.Div([
            html.I(className=f"ti {icon}", style={"fontSize": "22px", "color": color}),
        ], style={"background": f"{color}15", "borderRadius": "10px", "padding": "10px",
                  "marginBottom": "10px", "display": "inline-block"}),
        html.Strong(title, style={"fontSize": "14px", "color": _AZUL, "display": "block",
                                   "marginBottom": "4px"}),
        html.P(desc, style={"fontSize": "11px", "color": _GRAY, "margin": "0",
                             "lineHeight": "1.5"}),
        html.Div([
            _badge(badge_text, color) if badge_text else html.Span(),
            html.Span("Abrir →", style={"fontSize": "11px", "fontWeight": "700",
                                         "color": color, "display": "inline-block"}),
        ], style={"display": "flex", "justifyContent": "space-between",
                  "alignItems": "center", "marginTop": "8px"}),
    ], style={"background": "#fff", "border": "1px solid #E5E7EB", "borderRadius": "14px",
              "padding": "16px 18px", "height": "100%",
              "boxShadow": "0 1px 4px rgba(0,0,0,.06)",
              "transition": "box-shadow .2s", "cursor": "pointer"}),
        href=href, style={"textDecoration": "none"})


def _priority_card(icon, title, desc, urgency="medium"):
    colors = {"high": "#991B1B", "medium": "#92400E", "low": "#1D4ED8"}
    bg     = {"high": "#FEF2F2", "medium": "#FFFBEB", "low": "#EFF6FF"}
    border = {"high": "#FECACA", "medium": "#FDE68A", "low": "#BFDBFE"}
    c = colors[urgency]
    return html.Div([
        html.I(className=f"ti {icon}",
               style={"fontSize": "20px", "color": c, "marginBottom": "8px",
                      "display": "block"}),
        html.Strong(title, style={"fontSize": "13px", "color": c, "display": "block",
                                   "marginBottom": "4px"}),
        html.P(desc, style={"fontSize": "11px", "color": "#374151", "margin": "0",
                             "lineHeight": "1.5"}),
    ], style={"background": bg[urgency], "border": f"1px solid {border[urgency]}",
              "borderRadius": "12px", "padding": "14px 16px", "height": "100%"})


def _alert_strip(sq: dict) -> html.Div | None:
    alerts = []
    if sq["expiring_1y"] > 0:
        alerts.append(html.Span([
            html.I(className="ti ti-alert-triangle",
                   style={"marginRight": "4px", "color": "#991B1B"}),
            html.Strong(f"{sq['expiring_1y']} contratos", style={"color": "#991B1B"}),
            html.Span(" vencen en ≤12 meses: " + ", ".join(sq["expiring_names"][:4]) +
                      ("..." if len(sq["expiring_names"]) > 4 else ""),
                      style={"fontSize": "11px", "color": "#374151"}),
        ], style={"marginRight": "18px"}))
    if sq["loans_in"] > 0:
        alerts.append(html.Span([
            html.I(className="ti ti-arrow-right-circle",
                   style={"marginRight": "4px", "color": "#1D4ED8"}),
            html.Strong(f"{sq['loans_in']} cedidos", style={"color": "#1D4ED8"}),
            html.Span(" en plantilla: " + ", ".join(sq["loan_names"]),
                      style={"fontSize": "11px", "color": "#374151"}),
        ], style={"marginRight": "18px"}))
    if not alerts:
        return None
    return html.Div(
        [html.I(className="ti ti-bell",
                style={"fontSize": "14px", "color": _ROJO, "marginRight": "10px"}),
         *alerts],
        style={"background": "#FFF1F2", "border": "1px solid #FECACA",
               "borderRadius": "10px", "padding": "10px 14px",
               "display": "flex", "alignItems": "center", "flexWrap": "wrap",
               "marginBottom": "18px"},
    )


def _build_priority_actions(sq: dict, sk: dict) -> list:
    """Genera hasta 3 tarjetas de acción prioritaria basadas en datos reales."""
    cards = []
    if sq["expiring_6m"] > 0:
        cards.append(("ti-urgent", "Renovaciones urgentes",
                      f"{sq['expiring_6m']} jugadores con contrato que vence en ≤6 meses. "
                      "Decisión inmediata requerida.", "high"))
    elif sq["expiring_1y"] > 0:
        cards.append(("ti-calendar-exclamation", "Contratos próximos a vencer",
                      f"{sq['expiring_1y']} jugadores con contrato terminando en ≤12 meses.",
                      "medium"))
    if sk["candidates"] > 0:
        cards.append(("ti-search", "Base de scouting activa",
                      f"{sk['candidates']:,} jugadores en {sk['ligas']} ligas disponibles "
                      "para búsqueda y comparación.", "low"))
    if sq["loans_in"] > 0:
        cards.append(("ti-transfer-in", "Cesiones a revisar",
                      f"{sq['loans_in']} jugadores cedidos en plantilla. "
                      "Evaluar continuidad para 2026/27.", "medium"))
    # Rellenar con genéricos si faltan
    if len(cards) < 2:
        cards.append(("ti-chart-bar", "Análisis de plantilla disponible",
                      "Consulta los gráficos de edad, posición y valor de mercado actualizados.",
                      "low"))
    return cards[:3]


# ---------------------------------------------------------------------------
# Gráficos
# ---------------------------------------------------------------------------

def _chart_age_distribution(ages: list[int]) -> go.Figure:
    if not ages:
        return go.Figure()
    avg = sum(ages) / len(ages)
    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=ages, xbins=dict(start=16, end=42, size=1),
        marker=dict(color=RAYO_RED, line=dict(color="white", width=0.5)),
        opacity=0.85,
        hovertemplate="<b>Edad %{x}</b><br>%{y} jugadores<extra></extra>",
        name="Jugadores",
    ))
    fig.add_vline(
        x=avg, line_dash="dot", line_color=RAYO_DARK, line_width=2,
        annotation_text=f"  Media: {avg:.1f}a",
        annotation_position="top right",
        annotation_font=dict(size=11, color=RAYO_DARK, family="Inter"),
    )
    apply_theme(fig, height=240, title="Distribución de edades", compact=True)
    fig.update_layout(
        showlegend=False,
        xaxis_title="Edad", yaxis_title="Nº jugadores",
        bargap=0.05,
    )
    return fig


def _chart_positions(positions: dict[str, int]) -> go.Figure:
    if not positions:
        return go.Figure()
    pos_order = ["GK", "RB", "CB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"]
    labels = [p for p in pos_order if p in positions] +              [p for p in positions if p not in pos_order]
    values = [positions[p] for p in labels]
    max_v = max(values) if values else 1
    colors = sequential_reds(len(values))
    # orden: más jugadores → más saturado
    sorted_pairs = sorted(zip(values, labels, range(len(labels))), reverse=True)
    sorted_labels = [p[1] for p in sorted_pairs]
    sorted_values = [p[0] for p in sorted_pairs]
    bar_colors = sequential_reds(len(sorted_values))
    bar_colors.reverse()
    fig = go.Figure(go.Bar(
        x=sorted_labels, y=sorted_values,
        marker=dict(
            color=bar_colors,
            line=dict(color="white", width=0.5),
        ),
        hovertemplate="<b>%{x}</b>: %{y} jugadores<extra></extra>",
        text=sorted_values, textposition="outside",
        textfont=dict(size=11, color=RAYO_DARK),
    ))
    apply_theme(fig, height=240, title="Distribución por posición", compact=True)
    fig.update_layout(showlegend=False, yaxis_title="Jugadores")
    return fig


def _chart_contracts(players_raw: list[dict]) -> go.Figure:
    if not players_raw:
        return go.Figure()
    today = date.today()
    year_counts: dict[int, int] = {}
    for p in players_raw:
        ce = str(p.get("contract_end") or "")[:10]
        try:
            yr = date.fromisoformat(ce).year
            year_counts[yr] = year_counts.get(yr, 0) + 1
        except (ValueError, TypeError):
            pass
    if not year_counts:
        return go.Figure()
    years = sorted(year_counts.keys())
    counts = [year_counts[y] for y in years]
    # Color semáforo: urgente=rojo, próximo=ámbar, ok=verde
    colors = []
    for y in years:
        if y <= today.year:
            colors.append(RAYO_RED)
        elif y <= today.year + 1:
            colors.append(C_WARNING)
        else:
            colors.append(C_POSITIVE)
    fig = go.Figure(go.Bar(
        x=[str(y) for y in years], y=counts,
        marker=dict(color=colors, line=dict(color="white", width=0.5)),
        hovertemplate="<b>Vence %{x}</b>: %{y} jugadores<extra></extra>",
        text=counts, textposition="outside",
        textfont=dict(size=11, color=RAYO_DARK),
    ))
    apply_theme(fig, height=240, title="Vencimientos de contrato", compact=True)
    fig.update_layout(showlegend=False, yaxis_title="Jugadores")
    return fig


def _chart_market_value(players_raw: list[dict]) -> go.Figure:
    if not players_raw:
        return go.Figure()
    top = sorted(
        [p for p in players_raw if (p.get("market_value") or 0) > 0],
        key=lambda p: p.get("market_value", 0), reverse=True
    )[:14]
    if not top:
        return go.Figure()
    labels = [p["name"].split()[-1] for p in top]
    values = [p["market_value"] for p in top]
    texts  = [f"{v/1e6:.1f}M€" for v in values]
    fig = go.Figure(go.Treemap(
        labels=labels, parents=[""] * len(labels), values=values,
        text=texts, textinfo="label+text",
        marker=dict(
            colors=values,
            colorscale=[[0, "#FEE2E2"], [0.4, "#F87171"], [0.7, RAYO_RED], [1.0, RAYO_DARK]],
            showscale=False,
        ),
        textfont=dict(family="Inter", size=11),
        hovertemplate="<b>%{label}</b><br>Valor: %{text}<extra></extra>",
    ))
    apply_theme(fig, height=240, title="Valor de mercado — top jugadores")
    fig.update_layout(margin=dict(l=8, r=8, t=44, b=8))
    return fig


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

def layout(**_p):
    sq = _load_squad_data()
    sk = _load_scouting_kpis()

    players_raw: list[dict] = []
    try:
        data = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
        for group in data.get("squad_2025_26", {}).values():
            if isinstance(group, list):
                players_raw.extend(p for p in group if isinstance(p, dict))
    except Exception:
        pass

    mv_fmt = (f"{sq['total_mv']/1e6:.0f}M€"
              if sq["total_mv"] >= 1e6 else f"{sq['total_mv']:,}€")
    today_str = date.today().strftime("%d %b %Y").lstrip("0")
    alert = _alert_strip(sq)
    actions = _build_priority_actions(sq, sk)

    return html.Div([
        # ── Hero ──
        html.Div([
            html.Div([
                html.Img(
                    src="https://upload.wikimedia.org/wikipedia/en/d/d8/Rayo_Vallecano_logo.svg",
                    style={"height": "56px", "marginRight": "16px", "flexShrink": "0"}),
                html.Div([
                    html.H1("Dashboard de Dirección Deportiva",
                            style={"fontSize": "24px", "fontWeight": "800",
                                   "color": _AZUL, "margin": "0 0 4px"}),
                    html.P("Rayo Vallecano · Temporada 2025/26 · Panel ejecutivo automático",
                           style={"fontSize": "12px", "color": _GRAY, "margin": "0"}),
                ]),
            ], style={"display": "flex", "alignItems": "center", "flex": "1"}),
            html.Div([
                html.Span(today_str, style={"fontSize": "11px", "color": _GRAY,
                                            "fontWeight": "600"}),
                html.Div(style={"width": "1px", "height": "16px", "background": "#E5E7EB",
                                "margin": "0 10px", "display": "inline-block"}),
                html.I(className="ti ti-database", style={"fontSize": "11px", "color": _GRAY,
                                                            "marginRight": "4px"}),
                html.Span(f"{sk['candidates']:,} jugadores en base de datos",
                          style={"fontSize": "11px", "color": _GRAY}),
            ], style={"display": "flex", "alignItems": "center", "flexShrink": "0"}),
        ], style={"background": "linear-gradient(135deg,#FFF1F2,#FFFFFF)",
                  "border": "1px solid #FECACA", "borderRadius": "16px",
                  "padding": "20px 24px", "marginBottom": "16px",
                  "display": "flex", "justifyContent": "space-between",
                  "alignItems": "center"}),

        # ── KPIs ──
        html.P("PLANTILLA ACTUAL", style={"fontSize": "10px", "fontWeight": "700",
               "color": _GRAY, "letterSpacing": ".07em", "marginBottom": "8px"}),
        dbc.Row([
            dbc.Col(_kpi("Jugadores", sq["n_players"],
                         "Rayo Vallecano 2025/26", _AZUL, "ti-users", _AZUL), md=2),
            dbc.Col(_kpi("Edad media", f"{sq['avg_age']}",
                         "años en plantilla", _AZUL, "ti-calendar", _AZUL), md=2),
            dbc.Col(_kpi("Valor de mercado", mv_fmt,
                         "valor total Transfermarkt", _AZUL, "ti-coin-euro", _AZUL), md=2),
            dbc.Col(_kpi("Contratos urgentes", sq["expiring_1y"],
                         "vencen en ≤12 meses", "#991B1B", "ti-alert-triangle", "#991B1B"), md=2),
            dbc.Col(_kpi("Vencen en 6m", sq["expiring_6m"],
                         "decisión inmediata", "#B45309", "ti-clock-exclamation", "#B45309"), md=2),
            dbc.Col(_kpi("Candidatos scouting", f"{sk['candidates']:,}",
                         f"en {sk['ligas']} ligas", "#166534", "ti-search", "#166534"), md=2),
        ], className="g-2 mb-3"),

        # ── Alertas ──
        *(([alert]) if alert else []),

        # ── Acciones prioritarias ──
        html.P("ACCIÓN REQUERIDA", style={"fontSize": "10px", "fontWeight": "700",
               "color": _GRAY, "letterSpacing": ".07em", "marginBottom": "8px"}),
        dbc.Row([
            dbc.Col(_priority_card(ic, ti, de, ur), md=4, className="mb-3")
            for ic, ti, de, ur in actions
        ], className="g-3 mb-3"),

        # ── Gráficos ──
        html.P("ANÁLISIS VISUAL", style={"fontSize": "10px", "fontWeight": "700",
               "color": _GRAY, "letterSpacing": ".07em", "marginBottom": "8px"}),
        dbc.Row([
            dbc.Col(html.Div([
                dcc.Graph(figure=_chart_age_distribution(sq["ages"]),
                          config={"displayModeBar": False}, style={"height": "230px"}),
            ], className="card-modern"), md=3),
            dbc.Col(html.Div([
                dcc.Graph(figure=_chart_positions(sq["positions"]),
                          config={"displayModeBar": False}, style={"height": "230px"}),
            ], className="card-modern"), md=3),
            dbc.Col(html.Div([
                dcc.Graph(figure=_chart_contracts(players_raw),
                          config={"displayModeBar": False}, style={"height": "230px"}),
            ], className="card-modern"), md=3),
            dbc.Col(html.Div([
                dcc.Graph(figure=_chart_market_value(players_raw),
                          config={"displayModeBar": False}, style={"height": "230px"}),
            ], className="card-modern"), md=3),
        ], className="g-3 mb-4"),

        # ── Módulos ──
        html.P("MÓDULOS", style={"fontSize": "10px", "fontWeight": "700",
               "color": _GRAY, "letterSpacing": ".07em", "marginBottom": "8px"}),
        dbc.Row([
            dbc.Col(_nav_card("ti-users-group", "Plantilla",
                              "Plantilla actual por líneas, contratos y valor de mercado.",
                              "/plantilla", "#1D4ED8",
                              f"{sq['n_players']} jugadores"), md=2, className="mb-3"),
            dbc.Col(_nav_card("ti-search", "Scouting",
                              "Buscador fuzzy de jugadores con filtros avanzados y perfil completo.",
                              "/scouting", "#166534",
                              f"{sk['candidates']:,} candidatos"), md=2, className="mb-3"),
            dbc.Col(_nav_card("ti-git-compare", "Comparador",
                              "Compara candidatos y calcula su Fit Rayo 0–100.",
                              "/comparador", "#7C3AED"), md=2, className="mb-3"),
            dbc.Col(_nav_card("ti-chalkboard", "Entrenadores",
                              "Casting de técnicos con estilo calculado y encaje táctico.",
                              "/entrenadores", "#9A3412",
                              f"{sk['entrenadores']} perfiles"), md=2, className="mb-3"),
            dbc.Col(_nav_card("ti-clipboard-check", "Decisiones",
                              "Rankings automáticos: fichar, renovar, vender, ceder.",
                              "/decisiones", "#854D0E",
                              f"{sq['expiring_1y']} urgentes" if sq["expiring_1y"] else None),
                    md=2, className="mb-3"),
            dbc.Col(_nav_card("ti-coins", "Finanzas",
                              "Masa salarial, simulación presupuestaria y análisis de costes.",
                              "/finanzas", "#065F46"), md=2, className="mb-3"),
            dbc.Col(_nav_card("ti-list-check", "Criterios",
                              "Metodología y pesos usados en todos los modelos.",
                              "/criterios", _ROJO), md=2, className="mb-3"),
        ], className="g-3"),

        html.P(
            "Datos de mercado y contratos: Transfermarkt · Métricas deportivas: OPTA · "
            "Scores calculados automáticamente.",
            style={"fontSize": "10px", "color": "#9CA3AF",
                   "marginTop": "8px", "textAlign": "center"},
        ),
    ])
