# -*- coding: utf-8 -*-
"""
home.py — Panel de control principal (Dashboard Home)
=====================================================

PROPÓSITO:
    Página de inicio que muestra un resumen ejecutivo del estado de la
    plantilla y del mercado. Diseñada para que un director deportivo vea
    de un vistazo los KPIs más relevantes.

CONTENIDO:
    - KPIs principales: nº jugadores, edad media, valor total, presupuesto
    - Alertas: contratos que expiran, jugadores sub-rendimiento
    - Resumen de necesidades detectadas por posición
    - Accesos rápidos a las secciones de scouting y decisiones
    - Última actualización de datos

NAVEGACIÓN:
    Ruta: / (página principal)
    Accesible desde el logo y el enlace "Inicio" del sidebar.
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
from dashboard.components.chart_theme import (
    apply_theme, RAYO_RED, RAYO_DARK, C_POSITIVE, C_WARNING,
    GRAPH_CONFIG_SIMPLE, sequential_reds,
)
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.utils.config import settings  # noqa: E402

dash.register_page(__name__, path="/", name="Inicio")
PROC   = Path(settings()["paths"]["data_processed"])
ROOT   = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "club_profile.yaml"

_RED   = "#DC2626"
_DARK  = "#1A1A2E"
_GRAY  = "#6B7280"
_WHITE = "#FFFFFF"

_CORP_GRAD  = "linear-gradient(135deg,#E30613 0%,#C4000F 100%)"
_CORP_LIGHT = "#FFFFFF"
_CORP_ACC   = "#E30613"   # rojo corporativo Rayo

MODULE_META = {
    "plantilla":    (_CORP_GRAD, _CORP_LIGHT, _CORP_ACC),
    "scouting":     (_CORP_GRAD, _CORP_LIGHT, _CORP_ACC),
    "comparador":   (_CORP_GRAD, _CORP_LIGHT, _CORP_ACC),
    "entrenadores": (_CORP_GRAD, _CORP_LIGHT, _CORP_ACC),
    "decisiones":   (_CORP_GRAD, _CORP_LIGHT, _CORP_ACC),
    "finanzas":     (_CORP_GRAD, _CORP_LIGHT, _CORP_ACC),
}

# ─────────────────────────────────────────────────────────────────────────────
# Carga de datos
# ─────────────────────────────────────────────────────────────────────────────

def _load_squad_data() -> dict:
    defaults = {
        "n_players": 0, "avg_age": 0.0, "total_mv": 0,
        "expiring_1y": 0, "expiring_6m": 0, "loans_in": 0,
        "positions": {}, "ages": [], "expiring_names": [], "loan_names": [],
    }
    if not CONFIG.exists():
        return defaults
    try:
        data  = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
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
                    days    = (ce_date - today).days
                    if days <= 365:
                        expiring.append(p["name"])
                    if days <= 182:
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


# ─────────────────────────────────────────────────────────────────────────────
# Componentes visuales
# ─────────────────────────────────────────────────────────────────────────────

def _kpi_card(icon: str, label: str, value: str, sub: str,
              danger: bool = False) -> html.Div:
    variant = "danger" if danger else ""
    return html.Div([
        html.Div([
            html.I(className=f"ti {icon}"),
        ], className=f"kpi-icon {variant}"),
        html.Div(value, className="kpi-value"),
        html.Div(label, className="kpi-label"),
        html.Div(sub, className="kpi-sub"),
    ], className=f"kpi-modern {variant}")


def _module_card(icon: str, title: str, desc: str, href: str,
                 key: str, badge: str | None = None) -> dcc.Link:
    return dcc.Link(
        html.Div([
            html.Div([
                html.I(className=f"ti {icon}"),
                *([ html.Span(badge, style={
                        "background": "rgba(255,255,255,.18)",
                        "color": "rgba(255,255,255,.9)",
                        "fontSize": "9px", "fontWeight": "700",
                        "borderRadius": "20px", "padding": "2px 8px",
                        "border": "1px solid rgba(255,255,255,.15)",
                    }) ] if badge else []),
            ], className="module-card-head"),
            html.Div([
                html.Div(title, className="module-card-title"),
                html.Div(desc, className="module-card-desc"),
                html.Div([
                    "Abrir módulo",
                    html.I(className="ti ti-arrow-right", style={"fontSize": "11px"}),
                ], className="module-card-cta"),
            ], className="module-card-body"),
        ], style={"height": "100%"}),
        href=href, className="module-card",
    )


def _alert_pill(icon: str, text: str, variant: str = "warning") -> html.Span:
    cls = f"alert-pill alert-pill-{variant}"
    return html.Span([
        html.I(className=f"ti {icon}", style={"fontSize": "12px"}),
        html.Span(text, style={"fontSize": "11px", "fontWeight": "600"}),
    ], className=cls)


# ─────────────────────────────────────────────────────────────────────────────
# Gráficos
# ─────────────────────────────────────────────────────────────────────────────

def _chart_age(ages: list[int]) -> go.Figure:
    if not ages:
        return go.Figure()
    avg = sum(ages) / len(ages)
    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=ages, xbins=dict(start=16, end=42, size=1),
        marker=dict(color="#E30613", line=dict(color=_WHITE, width=0.5)),
        opacity=0.85,
        hovertemplate="<b>Edad %{x}</b><br>%{y} jugadores<extra></extra>",
    ))
    fig.add_vline(x=avg, line_dash="dot", line_color=_DARK, line_width=2,
                  annotation_text=f"  Media {avg:.1f}a",
                  annotation_font=dict(size=10, color=_DARK, family="Inter"))
    apply_theme(fig, height=210, title="Distribución de edades", compact=True)
    fig.update_layout(showlegend=False, xaxis_title="Edad", yaxis_title="Jugadores",
                      bargap=0.05)
    return fig


def _chart_positions(positions: dict[str, int]) -> go.Figure:
    if not positions:
        return go.Figure()
    pos_order = ["GK", "RB", "CB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"]
    labels = [p for p in pos_order if p in positions] + \
             [p for p in positions if p not in pos_order]
    values = [positions[p] for p in labels]
    pairs  = sorted(zip(values, labels), reverse=True)
    sl, sv = [p[1] for p in pairs], [p[0] for p in pairs]
    colors = sequential_reds(len(sv)); colors.reverse()
    fig = go.Figure(go.Bar(
        x=sl, y=sv,
        marker=dict(color=colors, line=dict(color=_WHITE, width=0.5)),
        text=sv, textposition="outside",
        hovertemplate="<b>%{x}</b>: %{y} jugadores<extra></extra>",
    ))
    apply_theme(fig, height=210, title="Distribución por posición", compact=True)
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
    years  = sorted(year_counts.keys())
    counts = [year_counts[y] for y in years]
    colors = [_RED if y <= today.year else C_WARNING if y <= today.year + 1
              else C_POSITIVE for y in years]
    fig = go.Figure(go.Bar(
        x=[str(y) for y in years], y=counts,
        marker=dict(color=colors, line=dict(color=_WHITE, width=0.5)),
        text=counts, textposition="outside",
        hovertemplate="<b>Vence %{x}</b>: %{y} jugadores<extra></extra>",
    ))
    apply_theme(fig, height=210, title="Vencimientos de contrato", compact=True)
    fig.update_layout(showlegend=False, yaxis_title="Jugadores")
    return fig


def _chart_mv(players_raw: list[dict]) -> go.Figure:
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
            colorscale=[[0, "#FEE2E2"], [0.4, "#F87171"], [0.7, _RED], [1.0, _DARK]],
            showscale=False,
        ),
        textfont=dict(family="Inter", size=11),
        hovertemplate="<b>%{label}</b><br>%{text}<extra></extra>",
    ))
    apply_theme(fig, height=210, title="Valor de mercado — top jugadores")
    fig.update_layout(margin=dict(l=8, r=8, t=44, b=8))
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Layout
# ─────────────────────────────────────────────────────────────────────────────

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

    mv_fmt    = f"{sq['total_mv']/1e6:.0f}M€" if sq["total_mv"] >= 1e6 else f"{sq['total_mv']:,}€"
    today_str = date.today().strftime("%d %b %Y").lstrip("0")

    # ── Alertas activas ───────────────────────────────────────────────────────
    pills = []
    if sq["expiring_6m"] > 0:
        pills.append(_alert_pill("ti-urgent",
                                 f"{sq['expiring_6m']} contratos críticos ≤6 meses",
                                 "danger"))
    if sq["expiring_1y"] > 0:
        pills.append(_alert_pill("ti-alert-triangle",
                                 f"{sq['expiring_1y']} contratos vencen en ≤12 meses",
                                 "warning"))
    if sq["loans_in"] > 0:
        pills.append(_alert_pill("ti-transfer-in",
                                 f"{sq['loans_in']} cedidos en plantilla",
                                 "info"))

    # ── Helpers de stats en hero ──────────────────────────────────────────────
    def _hero_stat(val, lbl, sep=True):
        border = "1px solid rgba(255,255,255,.12)" if sep else "none"
        return html.Div([
            html.Div(val, style={
                "fontSize": "28px", "fontWeight": "900", "color": _WHITE,
                "lineHeight": "1", "letterSpacing": "-.03em",
            }),
            html.Div(lbl, style={
                "fontSize": "9px", "color": "rgba(255,255,255,.45)",
                "fontWeight": "600", "marginTop": "3px", "textTransform": "uppercase",
                "letterSpacing": ".06em",
            }),
        ], style={"textAlign": "center", "padding": "0 22px", "borderRight": border})

    return html.Div([

        # ── Hero ─────────────────────────────────────────────────────────────
        html.Div([
            # Izquierda: logo + título
            html.Div([
                html.Img(
                    src="https://upload.wikimedia.org/wikipedia/en/d/d8/Rayo_Vallecano_logo.svg",
                    style={"height": "60px", "marginRight": "20px", "flexShrink": "0",
                           "filter": "drop-shadow(0 3px 10px rgba(227,6,19,.45))"},
                ),
                html.Div([
                    html.Div("PANEL DE DIRECCIÓN DEPORTIVA", style={
                        "fontSize": "8.5px", "fontWeight": "700",
                        "color": "rgba(255,255,255,.38)",
                        "letterSpacing": ".16em", "marginBottom": "5px",
                    }),
                    html.H1("Rayo Vallecano", style={
                        "fontSize": "26px", "fontWeight": "900",
                        "color": _WHITE, "margin": "0", "letterSpacing": "-.03em",
                    }),
                    html.Div([
                        html.Span("Temporada 2026/27", style={
                            "fontSize": "12px", "color": "rgba(255,255,255,.55)",
                            "fontWeight": "500",
                        }),
                        html.Span(" · ", style={"color": "rgba(255,255,255,.2)", "margin": "0 6px"}),
                        html.Span(f"Actualizado {today_str}", style={
                            "fontSize": "11px", "color": "rgba(255,255,255,.35)",
                        }),
                    ], style={"marginTop": "4px"}),
                ]),
            ], style={"display": "flex", "alignItems": "center", "flex": "1"}),

            # Derecha: stats clave
            html.Div([
                _hero_stat(str(sq["n_players"]), "Jugadores"),
                _hero_stat(mv_fmt, "Valor mercado"),
                _hero_stat(f"{sk['candidates']:,}", "Candidatos scouting", sep=False),
            ], style={"display": "flex", "alignItems": "center", "flexShrink": "0"}),

        ], className="hero-dashboard"),

        # ── Alertas ──────────────────────────────────────────────────────────
        *([html.Div(pills, style={"display": "flex", "flexWrap": "wrap", "marginBottom": "20px"})] if pills else []),

        # ── KPIs ─────────────────────────────────────────────────────────────
        html.Div("Resumen de plantilla", className="section-label", style={"marginBottom": "14px"}),
        dbc.Row([
            dbc.Col(_kpi_card("ti-users",            "Jugadores",         str(sq["n_players"]),   "Rayo Vallecano 2026/27"),     md=2),
            dbc.Col(_kpi_card("ti-calendar",          "Edad media",        f"{sq['avg_age']}a",    "años · primera plantilla"),   md=2),
            dbc.Col(_kpi_card("ti-coin-euro",         "Valor de mercado",  mv_fmt,                  "Transfermarkt total"),        md=2),
            dbc.Col(_kpi_card("ti-alert-triangle",    "Contratos urgentes",str(sq["expiring_1y"]), "vencen en ≤12 meses", danger=True), md=2),
            dbc.Col(_kpi_card("ti-clock-exclamation", "Críticos ≤6m",      str(sq["expiring_6m"]), "decisión inmediata",  danger=True), md=2),
            dbc.Col(_kpi_card("ti-search",            "Scouting",          f"{sk['candidates']:,}", f"{sk['ligas']} ligas"),       md=2),
        ], className="g-3 mb-4 stagger animate-fade"),

        # ── Gráficos + Módulos ────────────────────────────────────────────────
        dbc.Row([

            # Gráficos (izquierda)
            dbc.Col([
                html.Div("Análisis visual de plantilla", className="section-label", style={"marginBottom": "14px"}),
                dbc.Row([
                    dbc.Col(html.Div(dcc.Graph(
                        figure=_chart_age(sq["ages"]),
                        config=GRAPH_CONFIG_SIMPLE,
                        style={"height": "210px"},
                    ), className="chart-wrap"), md=6),
                    dbc.Col(html.Div(dcc.Graph(
                        figure=_chart_positions(sq["positions"]),
                        config=GRAPH_CONFIG_SIMPLE,
                        style={"height": "210px"},
                    ), className="chart-wrap"), md=6),
                ], className="g-3 mb-3"),
                dbc.Row([
                    dbc.Col(html.Div(dcc.Graph(
                        figure=_chart_contracts(players_raw),
                        config=GRAPH_CONFIG_SIMPLE,
                        style={"height": "210px"},
                    ), className="chart-wrap"), md=6),
                    dbc.Col(html.Div(dcc.Graph(
                        figure=_chart_mv(players_raw),
                        config=GRAPH_CONFIG_SIMPLE,
                        style={"height": "210px"},
                    ), className="chart-wrap"), md=6),
                ], className="g-3"),
            ], md=8),

            # Módulos (derecha)
            dbc.Col([
                html.Div("Módulos", className="section-label", style={"marginBottom": "14px"}),
                dbc.Row([
                    dbc.Col(_module_card(
                        "ti-users-group", "Plantilla",
                        "Líneas, contratos y valor de mercado.",
                        "/plantilla", "plantilla",
                        f"{sq['n_players']} jugadores",
                    ), md=6, className="mb-3"),
                    dbc.Col(_module_card(
                        "ti-search", "Scouting",
                        "Buscador con perfil y percentiles completos.",
                        "/scouting", "scouting",
                        f"{sk['candidates']:,} candidatos",
                    ), md=6, className="mb-3"),
                    dbc.Col(_module_card(
                        "ti-git-compare", "Comparador",
                        "Compara candidatos y calcula Fit Rayo.",
                        "/comparador", "comparador",
                    ), md=6, className="mb-3"),
                    dbc.Col(_module_card(
                        "ti-chalkboard", "Entrenadores",
                        "Casting de técnicos y encaje táctico.",
                        "/entrenadores", "entrenadores",
                        f"{sk['entrenadores']} perfiles",
                    ), md=6, className="mb-3"),
                    dbc.Col(_module_card(
                        "ti-clipboard-check", "Decisiones",
                        "Rankings automáticos: fichar, renovar, vender.",
                        "/decisiones", "decisiones",
                        f"{sq['expiring_1y']} urgentes" if sq["expiring_1y"] else None,
                    ), md=6, className="mb-3"),
                    dbc.Col(_module_card(
                        "ti-report-money", "Finanzas",
                        "Masa salarial y simulación presupuestaria.",
                        "/finanzas", "finanzas",
                    ), md=6, className="mb-3"),
                ], className="g-3"),
            ], md=4),

        ], className="g-4 mb-3"),

        # Footer
        html.Div(
            "Datos: Transfermarkt · OPTA · Scores calculados automáticamente por el sistema.",
            style={"fontSize": "10px", "color": "#9CA3AF",
                   "textAlign": "center", "marginTop": "8px", "paddingBottom": "4px"},
        ),
    ])
