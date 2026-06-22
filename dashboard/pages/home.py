# -*- coding: utf-8 -*-
"""
Página de inicio — Panel de control moderno de la dirección deportiva.
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

_CORP_GRAD  = "linear-gradient(135deg,#0D0D0D 0%,#1A1A1A 100%)"
_CORP_LIGHT = "#FFFFFF"
_CORP_ACC   = "#B8960C"   # amarillo oscuro — legible sobre fondo claro

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
    icon_bg    = "linear-gradient(135deg,#DC2626,#EF4444)" if danger else "linear-gradient(135deg,#0D0D0D,#2A2A2A)"
    top_border = "#DC2626" if danger else "#FFD600"
    return html.Div([
        html.Div([
            html.I(className=f"ti {icon}",
                   style={"fontSize": "20px", "color": "#FFD600" if not danger else _WHITE}),
        ], style={
            "background": icon_bg, "borderRadius": "10px",
            "width": "42px", "height": "42px",
            "display": "flex", "alignItems": "center", "justifyContent": "center",
            "flexShrink": "0", "marginBottom": "12px",
            "boxShadow": "0 4px 10px rgba(0,0,0,.18)",
        }),
        html.Div(value, style={
            "fontSize": "26px", "fontWeight": "900", "color": _DARK,
            "lineHeight": "1", "marginBottom": "3px",
        }),
        html.Div(label, style={
            "fontSize": "11px", "fontWeight": "700", "color": _DARK,
            "marginBottom": "2px",
        }),
        html.Div(sub, style={"fontSize": "10px", "color": _GRAY}),
    ], style={
        "background": _WHITE,
        "border": "1px solid rgba(0,0,0,.07)",
        "borderTop": f"3px solid {top_border}",
        "borderRadius": "14px",
        "padding": "16px 18px",
        "height": "100%",
        "boxShadow": "0 2px 8px rgba(0,0,0,.05)",
    })


def _module_card(icon: str, title: str, desc: str, href: str,
                 key: str, badge: str | None = None) -> dcc.Link:
    grad, light, accent = MODULE_META.get(
        key, (_RED, "#FFF1F2", _RED))
    return dcc.Link(
        html.Div([
            html.Div([
                html.I(className=f"ti {icon}",
                       style={"fontSize": "24px", "color": _WHITE}),
                *([ html.Span(badge, style={
                        "background": "rgba(255,255,255,.22)",
                        "color": _WHITE, "fontSize": "9px", "fontWeight": "700",
                        "borderRadius": "20px", "padding": "2px 7px",
                    }) ] if badge else []),
            ], style={
                "background": grad, "borderRadius": "12px 12px 0 0",
                "padding": "16px 16px 14px",
                "display": "flex", "justifyContent": "space-between",
                "alignItems": "flex-start", "minHeight": "66px",
            }),
            html.Div([
                html.Strong(title, style={
                    "fontSize": "13px", "fontWeight": "800",
                    "color": _DARK, "display": "block", "marginBottom": "4px",
                }),
                html.P(desc, style={
                    "fontSize": "10px", "color": _GRAY,
                    "margin": "0 0 8px", "lineHeight": "1.5",
                }),
                html.Span("Abrir →", style={
                    "fontSize": "10px", "fontWeight": "700", "color": accent,
                }),
            ], style={"padding": "12px 14px"}),
        ], style={
            "background": _WHITE,
            "border": "1px solid #E5E7EB",
            "borderRadius": "14px",
            "overflow": "hidden",
            "height": "100%",
            "boxShadow": "0 2px 8px rgba(0,0,0,.06)",
            "cursor": "pointer",
        }),
        href=href, style={"textDecoration": "none"},
    )


def _alert_pill(icon: str, text: str, color: str, bg: str) -> html.Span:
    return html.Span([
        html.I(className=f"ti {icon}",
               style={"fontSize": "12px", "marginRight": "5px", "color": color}),
        html.Span(text, style={"fontSize": "11px", "color": color, "fontWeight": "600"}),
    ], style={
        "background": bg, "border": f"1px solid {color}40",
        "borderRadius": "20px", "padding": "5px 12px",
        "display": "inline-flex", "alignItems": "center",
        "marginRight": "8px", "marginBottom": "8px",
    })


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
        marker=dict(color="#FFD600", line=dict(color=_WHITE, width=0.5)),
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

    pills = []
    if sq["expiring_6m"] > 0:
        pills.append(_alert_pill("ti-urgent",
                                 f"{sq['expiring_6m']} contratos críticos ≤6m",
                                 "#991B1B", "#FEF2F2"))
    if sq["expiring_1y"] > 0:
        pills.append(_alert_pill("ti-alert-triangle",
                                 f"{sq['expiring_1y']} contratos vencen en ≤12 meses",
                                 "#92400E", "#FFFBEB"))
    if sq["loans_in"] > 0:
        pills.append(_alert_pill("ti-transfer-in",
                                 f"{sq['loans_in']} cedidos en plantilla",
                                 "#1D4ED8", "#EFF6FF"))

    return html.Div([

        # ── Hero ─────────────────────────────────────────────────────────────
        html.Div([
            html.Div([
                html.Img(
                    src="https://upload.wikimedia.org/wikipedia/en/d/d8/Rayo_Vallecano_logo.svg",
                    style={"height": "58px", "marginRight": "20px", "flexShrink": "0"},
                ),
                html.Div([
                    html.Div("PANEL DE DIRECCIÓN DEPORTIVA", style={
                        "fontSize": "9px", "fontWeight": "700",
                        "color": "rgba(255,255,255,.55)",
                        "letterSpacing": ".14em", "marginBottom": "4px",
                    }),
                    html.H1("Rayo Vallecano · 2026/27", style={
                        "fontSize": "24px", "fontWeight": "900",
                        "color": _WHITE, "margin": "0 0 3px",
                    }),
                    html.Div(f"Datos actualizados · {today_str}", style={
                        "fontSize": "10px", "color": "rgba(255,255,255,.5)",
                    }),
                ]),
            ], style={"display": "flex", "alignItems": "center", "flex": "1"}),

            html.Div([
                *[html.Div([
                    html.Div(val, style={
                        "fontSize": "26px", "fontWeight": "900", "color": _WHITE,
                        "lineHeight": "1",
                    }),
                    html.Div(lbl, style={
                        "fontSize": "9px", "color": "rgba(255,255,255,.55)",
                        "fontWeight": "600", "marginTop": "2px",
                    }),
                ], style={"textAlign": "center", "padding": "0 18px",
                          "borderRight": sep})
                  for val, lbl, sep in [
                    (str(sq["n_players"]), "jugadores",
                     "1px solid rgba(255,255,255,.15)"),
                    (mv_fmt, "valor mercado",
                     "1px solid rgba(255,255,255,.15)"),
                    (f"{sk['candidates']:,}", "candidatos", "none"),
                ]],
            ], style={"display": "flex", "alignItems": "center", "flexShrink": "0"}),

        ], style={
            "background": "linear-gradient(135deg,#0D0D0D 0%,#1A1A1A 60%,#2A2A2A 100%)",
            "borderRadius": "18px", "padding": "22px 28px",
            "marginBottom": "18px",
            "display": "flex", "justifyContent": "space-between", "alignItems": "center",
            "boxShadow": "0 8px 28px rgba(255,214,0,.18)",
        }),

        # ── Alertas ──────────────────────────────────────────────────────────
        *([html.Div(pills, style={
               "display": "flex", "flexWrap": "wrap", "marginBottom": "16px",
           })] if pills else []),

        # ── KPIs ─────────────────────────────────────────────────────────────
        html.P("RESUMEN DE PLANTILLA", style={
            "fontSize": "9px", "fontWeight": "700", "color": _GRAY,
            "letterSpacing": ".08em", "marginBottom": "10px",
        }),
        dbc.Row([
            dbc.Col(_kpi_card(
                "ti-users", "Jugadores", str(sq["n_players"]),
                "Rayo Vallecano 2026/27",
            ), md=2),
            dbc.Col(_kpi_card(
                "ti-calendar", "Edad media", f"{sq['avg_age']}a",
                "años en primera plantilla",
            ), md=2),
            dbc.Col(_kpi_card(
                "ti-coin-euro", "Valor de mercado", mv_fmt,
                "valor total Transfermarkt",
            ), md=2),
            dbc.Col(_kpi_card(
                "ti-alert-triangle", "Contratos urgentes", str(sq["expiring_1y"]),
                "vencen en ≤12 meses",
                danger=True,
            ), md=2),
            dbc.Col(_kpi_card(
                "ti-clock-exclamation", "Críticos ≤6m", str(sq["expiring_6m"]),
                "decisión inmediata",
                danger=True,
            ), md=2),
            dbc.Col(_kpi_card(
                "ti-search", "Scouting", f"{sk['candidates']:,}",
                f"candidatos en {sk['ligas']} ligas",
            ), md=2),
        ], className="g-3 mb-4"),

        # ── Gráficos + Módulos ────────────────────────────────────────────────
        dbc.Row([

            # Gráficos (izquierda, 8 cols)
            dbc.Col([
                html.P("ANÁLISIS VISUAL", style={
                    "fontSize": "9px", "fontWeight": "700", "color": _GRAY,
                    "letterSpacing": ".08em", "marginBottom": "10px",
                }),
                dbc.Row([
                    dbc.Col(html.Div(dcc.Graph(
                        figure=_chart_age(sq["ages"]),
                        config=GRAPH_CONFIG_SIMPLE,
                        style={"height": "200px"},
                    ), style={"background": _WHITE, "borderRadius": "12px",
                               "border": "1px solid #E5E7EB", "overflow": "hidden",
                               "boxShadow": "0 1px 5px rgba(0,0,0,.05)"}), md=6),
                    dbc.Col(html.Div(dcc.Graph(
                        figure=_chart_positions(sq["positions"]),
                        config=GRAPH_CONFIG_SIMPLE,
                        style={"height": "200px"},
                    ), style={"background": _WHITE, "borderRadius": "12px",
                               "border": "1px solid #E5E7EB", "overflow": "hidden",
                               "boxShadow": "0 1px 5px rgba(0,0,0,.05)"}), md=6),
                ], className="g-3 mb-3"),
                dbc.Row([
                    dbc.Col(html.Div(dcc.Graph(
                        figure=_chart_contracts(players_raw),
                        config=GRAPH_CONFIG_SIMPLE,
                        style={"height": "200px"},
                    ), style={"background": _WHITE, "borderRadius": "12px",
                               "border": "1px solid #E5E7EB", "overflow": "hidden",
                               "boxShadow": "0 1px 5px rgba(0,0,0,.05)"}), md=6),
                    dbc.Col(html.Div(dcc.Graph(
                        figure=_chart_mv(players_raw),
                        config=GRAPH_CONFIG_SIMPLE,
                        style={"height": "200px"},
                    ), style={"background": _WHITE, "borderRadius": "12px",
                               "border": "1px solid #E5E7EB", "overflow": "hidden",
                               "boxShadow": "0 1px 5px rgba(0,0,0,.05)"}), md=6),
                ], className="g-3"),
            ], md=8),

            # Módulos (derecha, 4 cols)
            dbc.Col([
                html.P("MÓDULOS", style={
                    "fontSize": "9px", "fontWeight": "700", "color": _GRAY,
                    "letterSpacing": ".08em", "marginBottom": "10px",
                }),
                dbc.Row([
                    dbc.Col(_module_card(
                        "ti-users-group", "Plantilla",
                        "Líneas, contratos y valor de mercado.",
                        "/plantilla", "plantilla",
                        f"{sq['n_players']} jugadores",
                    ), md=6, className="mb-3"),
                    dbc.Col(_module_card(
                        "ti-search", "Scouting",
                        "Buscador fuzzy con perfil completo.",
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
                        "Rankings: fichar, renovar, vender, ceder.",
                        "/decisiones", "decisiones",
                        f"{sq['expiring_1y']} urgentes" if sq["expiring_1y"] else None,
                    ), md=6, className="mb-3"),
                    dbc.Col(_module_card(
                        "ti-coins", "Finanzas",
                        "Masa salarial y simulación presupuestaria.",
                        "/finanzas", "finanzas",
                    ), md=6, className="mb-3"),
                ], className="g-3"),
            ], md=4),

        ], className="g-4 mb-3"),

        html.P(
            "Datos: Transfermarkt · OPTA · Scores calculados automáticamente.",
            style={"fontSize": "10px", "color": "#9CA3AF",
                   "textAlign": "center", "marginTop": "4px"},
        ),
    ])
