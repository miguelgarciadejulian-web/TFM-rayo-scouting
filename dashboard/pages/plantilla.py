# -*- coding: utf-8 -*-
"""
plantilla.py — Visualización de la plantilla actual del Rayo Vallecano
======================================================================

PROPÓSITO:
    Muestra la plantilla completa del Rayo con tarjetas visuales por jugador,
    organizadas por posición (porteros, defensas, centrocampistas, delanteros).
    Cada tarjeta incluye foto, edad, posición lateral, score de rendimiento
    y valor de mercado.

FUNCIONALIDAD:
    - Vista de tarjetas (card grid) responsive con foto TM
    - Agrupación por línea (porteros / defensas / medios / delanteros)
    - Click en jugador → navega a la ficha completa (/jugador)
    - KPIs agregados: edad media, valor total plantilla, minutos promedio
    - Gráficos: distribución de edad, mapa de posiciones, balance salarial

DATOS:
    - config/squad_2526.yaml (lista de 30 jugadores de la plantilla)
    - master_players.parquet (datos estadísticos)
    - player_economic.parquet (valores de mercado y salarios)
    - player_overrides.json (fotos de TransferMarkt)
"""
import urllib.parse
import yaml
from datetime import date
from pathlib import Path
import sys

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, dcc, html, no_update
from dash import dash_table
import plotly.graph_objects as go
from dashboard.components.chart_theme import apply_theme, RAYO_RED, RAYO_DARK, C_POSITIVE, C_WARNING, GRAPH_CONFIG_SIMPLE, sequential_reds

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dashboard.components.criteria_block import criteria_accordion  # noqa: E402
from src.utils.config import club_profile, settings

dash.register_page(__name__, path="/plantilla", name="Plantilla")

ROOT   = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "club_profile.yaml"

POS_COLOR = {
    "GK": ("#EFF6FF", "#1D4ED8"),
    "CB": ("#F0FDF4", "#166634"), "RB": ("#F0FDF4", "#166534"), "LB": ("#F0FDF4", "#166534"),
    "DM": ("#FFFBEB", "#92400E"), "CM": ("#FFFBEB", "#92400E"), "AM": ("#FFFBEB", "#92400E"),
    "RW": ("#FFF1F2", "#9F1239"), "LW": ("#FFF1F2", "#9F1239"), "ST": ("#FFF1F2", "#9F1239"),
}
URGENCY_COLOR = {"alta": ("#FFF1F2", "#9F1239", "Alta"), "media": ("#FFFBEB", "#92400E", "Media")}
GROUP_LABELS = {
    "goalkeepers": ("Porteros",       "ti-shield"),
    "defenders":   ("Defensas",       "ti-shield-half"),
    "midfielders": ("Centrocampistas","ti-adjustments-horizontal"),
    "forwards":    ("Delanteros",     "ti-bolt"),
}
_ROJO = "#DC2626"
_AZUL = "#1A1A2E"
_POS_GROUP = {
    "GK": "Porteros", "CB": "Defensas", "RB": "Defensas", "LB": "Defensas",
    "DM": "Centrocampistas", "CM": "Centrocampistas", "AM": "Centrocampistas",
    "RW": "Delanteros", "LW": "Delanteros", "ST": "Delanteros",
}
_GROUP_COLOR = {
    "Porteros": "#1D4ED8", "Defensas": "#166534",
    "Centrocampistas": "#92400E", "Delanteros": "#9F1239",
}
# Estilo de juego por posición YAML como fallback cuando no hay datos estadísticos
_POS_STYLE_FALLBACK = {
    "GK": "Portero",
    "CB": "Central (sin datos)",
    "LB": "Lateral izq. (sin datos)",
    "RB": "Lateral dcho. (sin datos)",
    "DM": "Pivote (sin datos)",
    "CM": "Centrocampista (sin datos)",
    "AM": "Mediapunta (sin datos)",
    "LW": "Extremo izdo. (sin datos)",
    "RW": "Extremo dcho. (sin datos)",
    "ST": "Delantero (sin datos)",
}
th = {
    "fontSize": "10px", "fontWeight": "600", "color": "#9CA3AF",
    "textTransform": "uppercase", "letterSpacing": ".06em",
    "padding": "0 10px 8px", "textAlign": "left", "borderBottom": "none",
}


def pos_badge(pos):
    bg, fg = POS_COLOR.get(pos, ("#F3F4F6", "#374151"))
    return html.Span(pos, style={
        "background": bg, "color": fg, "padding": "2px 8px",
        "borderRadius": "99px", "fontSize": "10px", "fontWeight": "700",
    })


def contract_bar(end_date):
    year = int(str(end_date)[:4]) if end_date else 9999
    if year <= 2026:
        color, label = "#DC2626", "2026"
    elif year <= 2027:
        color, label = "#F59E0B", str(year)
    else:
        color, label = "#10B981", str(year)
    full_date = str(end_date)[:10] if end_date else "?"
    return html.Div([
        html.Div(style={"width": "8px", "height": "8px", "borderRadius": "50%",
                        "background": color, "display": "inline-block", "marginRight": "6px"}),
        html.Span(label, title=f"Vence: {full_date}",
                  style={"fontSize": "12px", "color": "#374151", "fontWeight": "500",
                         "cursor": "help", "borderBottom": "1px dashed #D1D5DB"}),
    ], style={"display": "flex", "alignItems": "center"})


def market_val(v):
    if not v: return "—"
    return f"{v/1e6:.1f}M€" if v >= 1e6 else f"{v/1e3:.0f}K€"


def _squad_role_map(players_all: list, role_map: dict, role_labels: dict) -> dict:
    """
    Devuelve {yaml_name: role_label} resolviendo nombres YAML completos
    a nombres abreviados OPTA (ej. "Pathé Ciss" → "P. Ciss").

    Algoritmo (por orden de prioridad):
      1. Coincidencia exacta
      2. Coincidencia exacta normalizada (sin acentos, minúsculas)
      3. Apellido + inicial del nombre coinciden
      4. Si solo hay un jugador OPTA con ese apellido, se asume que es el mismo
    """
    import unicodedata

    def _norm(s: str) -> str:
        return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip()

    # Índice: apellido_normalizado → [(opta_name, first_initial), ...]
    last_idx: dict[str, list] = {}
    for opta_name in role_map:
        parts = _norm(opta_name).split()
        if not parts:
            continue
        last      = parts[-1]
        first_ini = parts[0][0] if parts[0] else ""
        last_idx.setdefault(last, []).append((opta_name, first_ini))

    result: dict[str, str] = {}
    for p in players_all:
        yaml_name = p.get("name", "")
        if not yaml_name:
            continue
        # 1. Exacto
        if yaml_name in role_map:
            result[yaml_name] = role_labels.get(role_map[yaml_name], "")
            continue
        # 2. Normalizado exacto
        yn = _norm(yaml_name)
        found = next((k for k in role_map if _norm(k) == yn), None)
        if found:
            result[yaml_name] = role_labels.get(role_map[found], "")
            continue
        # 3. Apellido + inicial
        yparts = yn.split()
        if not yparts:
            continue
        y_last = yparts[-1]
        y_ini  = yparts[0][0] if yparts else ""
        cands  = last_idx.get(y_last, [])
        matched = None
        for opta_name, o_ini in cands:
            if o_ini == y_ini:
                matched = opta_name
                break
        # 4. Un solo candidato con ese apellido → asumir que es el mismo jugador
        if matched is None and len(cands) == 1:
            matched = cands[0][0]
        if matched:
            result[yaml_name] = role_labels.get(role_map.get(matched, ""), "")

    return result


def player_row(p, i, role_map=None, role_labels=None):
    name = p.get("name", "")
    pos  = p.get("position", "")
    age  = p.get("age", "")
    nat  = p.get("nationality", "")
    end  = p.get("contract_end", "")
    mv   = p.get("market_value", 0)
    loan = p.get("loan_from", "")
    loan_to = p.get("loan_to", "")
    initials = "".join(w[0].upper() for w in name.split()[:2] if w)
    year = int(str(end)[:4]) if end else 9999
    row_bg = "#FFF5F5" if year <= 2026 else ("#FFFFFF" if i % 2 == 0 else "#FAFAFA")
    if loan_to:
        row_bg = "#F0FDF4"  # verde claro: vuelve de cesión
    # role_map aquí ya es {yaml_name: label} (pre-resuelto por _squad_role_map)
    role_label  = (role_map or {}).get(name, "")
    is_inferred = bool(role_label)
    if not role_label:
        role_label = _POS_STYLE_FALLBACK.get(pos.upper(), "Sin datos")
    return html.Tr([
        html.Td(html.Div([
            html.Div(initials, style={
                "width": "32px", "height": "32px", "borderRadius": "50%",
                "background": "#16A34A" if loan_to else _AZUL, "color": "#fff",
                "display": "flex", "alignItems": "center", "justifyContent": "center",
                "fontSize": "11px", "fontWeight": "600", "flexShrink": "0",
            }),
            html.Span(name, style={"fontSize": "13px", "fontWeight": "600", "color": _AZUL,
                                   "whiteSpace": "nowrap"}),
            *([ html.Span(f"· {loan}", style={
                    "fontSize": "9px", "color": "#1D4ED8", "whiteSpace": "nowrap",
                }) ] if loan else
              [ html.Span(f"· {loan_to}", style={
                    "fontSize": "9px", "color": "#15803D", "fontWeight": "600",
                    "whiteSpace": "nowrap",
                }) ] if loan_to else []),
        ], style={"display": "flex", "alignItems": "center", "gap": "6px",
                  "whiteSpace": "nowrap"})),
        html.Td(pos_badge(pos)),
        html.Td(str(age), style={"fontSize": "13px", "color": "#374151", "textAlign": "center"}),
        html.Td(nat, style={"fontSize": "12px", "color": "#6B7280"}),
        html.Td(contract_bar(end)),
        html.Td(html.Span(market_val(mv), style={"fontSize": "13px", "fontWeight": "600", "color": _AZUL})),
        html.Td(
            html.Span(role_label, title="Estilo inferido de estadísticas" if is_inferred else "Posición estimada — sin datos suficientes", style={
                "fontSize": "10px",
                "color": "#1D4ED8" if is_inferred else "#6B7280",
                "background": "#EFF6FF" if is_inferred else "#F3F4F6",
                "borderRadius": "6px", "padding": "2px 7px",
                "fontStyle": "normal" if is_inferred else "italic",
            }),
        ),
    ], id={"type": "plantilla-row", "name": name}, n_clicks=0,
       style={"background": row_bg, "transition": "background .1s", "cursor": "pointer"})


def group_table(group_key, players, resolved_styles=None):
    label, icon = GROUP_LABELS[group_key]
    return html.Div([
        html.Div([
            html.I(className=f"ti {icon}", style={"fontSize": "16px", "color": _ROJO, "marginRight": "8px"}),
            html.Span(label, style={"fontSize": "13px", "fontWeight": "600", "color": _AZUL}),
            html.Span(f" — {len(players)}", style={"fontSize": "12px", "color": "#9CA3AF", "marginLeft": "4px"}),
        ], style={"display": "flex", "alignItems": "center", "marginBottom": "10px"}),
        html.Div([
            html.Table([
                html.Thead(html.Tr([
                    html.Th("Jugador", style=th),
                    html.Th("Pos.", style={**th, "width": "60px"}),
                    html.Th("Edad", style={**th, "width": "55px", "textAlign": "center"}),
                    html.Th("Nacionalidad", style=th),
                    html.Th("Contrato", style={**th, "width": "90px"}),
                    html.Th("Valor TM", style={**th, "width": "90px"}),
                    html.Th("Estilo de juego", style={**th, "width": "160px"}),
                ], style={"borderBottom": f"2px solid {_ROJO}"})),
                html.Tbody([player_row(p, i, resolved_styles) for i, p in enumerate(players)]),
            ], style={"width": "100%", "borderCollapse": "collapse"}),
        ], style={"overflowX": "auto"}),
    ], className="card-modern")


# ---------------------------------------------------------------------------
# Gráficos — versiones corregidas
# ---------------------------------------------------------------------------

def _chart_age_scatter(players_all):
    """Strip chart: cada jugador como punto en su edad, separado por línea."""
    groups = ["Porteros", "Defensas", "Centrocampistas", "Delanteros"]
    fig = go.Figure()
    avg_age = None
    ages_all = [p["age"] for p in players_all if p.get("age")]
    if ages_all:
        avg_age = sum(ages_all) / len(ages_all)
    for i, grp in enumerate(groups):
        ps = [p for p in players_all
              if _POS_GROUP.get(p.get("position", ""), "Centrocampistas") == grp
              and p.get("age")]
        if not ps:
            continue
        fig.add_trace(go.Scatter(
            x=[p["age"] for p in ps],
            y=[grp] * len(ps),
            mode="markers",
            name=grp,
            marker=dict(color=_GROUP_COLOR[grp], size=14, opacity=0.85,
                        line=dict(color="#fff", width=2)),
            hovertemplate="%{customdata}<br>Edad: %{x}<extra></extra>",
            customdata=[p["name"] for p in ps],
        ))
    if avg_age:
        fig.add_vline(x=avg_age, line_dash="dot", line_color="#6B7280", line_width=1.5,
                      annotation_text=f"Media {avg_age:.1f}",
                      annotation_font_size=9, annotation_position="top right")
    apply_theme(fig, height=240, title="Edades por línea", compact=True)
    fig.update_layout(
        showlegend=False,
        xaxis=dict(title="Edad", range=[17, 40]),
        yaxis=dict(title=""),
        margin=dict(l=120, r=16, t=40, b=24),
    )
    return fig


def _chart_position_donut(players_all):
    counts = {"Porteros": 0, "Defensas": 0, "Centrocampistas": 0, "Delanteros": 0}
    for p in players_all:
        g = _POS_GROUP.get(p.get("position", ""), "Centrocampistas")
        counts[g] += 1
    labels = [k for k, v in counts.items() if v > 0]
    values = [counts[k] for k in labels]
    colors = [_GROUP_COLOR[k] for k in labels]
    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.55,
        marker_colors=colors, textinfo="label+value", textfont_size=10,
        hovertemplate="%{label}: %{value}<extra></extra>",
    ))
    apply_theme(fig, height=240, title="Por línea", compact=True)
    fig.update_layout(showlegend=False, margin=dict(l=8, r=8, t=40, b=8))
    return fig


def _chart_contract_status(players_all):
    today = date.today()
    year_data: dict[int, list[str]] = {}
    for p in players_all:
        try:
            yr = int(str(p.get("contract_end", "9999"))[:4])
            year_data.setdefault(yr, []).append(p.get("name", "?").split()[-1])
        except (ValueError, TypeError):
            pass
    years = sorted(year_data.keys())
    counts = [len(year_data[y]) for y in years]
    colors = [_ROJO if y <= today.year + 1 else ("#F59E0B" if y <= today.year + 2 else "#10B981")
              for y in years]
    names_txt = ["<br>".join(year_data[y]) for y in years]
    fig = go.Figure(go.Bar(
        x=[str(y) for y in years], y=counts, marker_color=colors,
        text=counts, textposition="outside",
        hovertext=names_txt,
        hovertemplate="<b>%{x}</b>: %{y}<br>%{hovertext}<extra></extra>",
    ))
    apply_theme(fig, height=240, title="Vencimientos de contrato", compact=True)
    fig.update_layout(showlegend=False, yaxis_title="Jugadores")
    return fig


def _chart_mv_bars(players_all):
    top = sorted(
        [p for p in players_all if (p.get("market_value") or 0) > 0],
        key=lambda p: p.get("market_value", 0), reverse=True
    )[:12]
    if not top:
        return go.Figure()
    labels = [p["name"].split()[-1] for p in top]
    values = [p["market_value"] / 1e6 for p in top]
    colors = [_ROJO if i == 0 else _AZUL for i in range(len(top))]
    fig = go.Figure(go.Bar(
        y=labels, x=values, orientation="h", marker_color=colors, opacity=0.85,
        text=[f"{v:.1f}M" for v in values], textposition="auto",
        hovertemplate="%{y}: %{x:.1f}M€<extra></extra>",
    ))
    apply_theme(fig, height=290, title="Valor de mercado (top 12)", compact=True)
    fig.update_layout(
        showlegend=False,
        yaxis=dict(autorange="reversed"),
        margin=dict(l=80, r=16, t=40, b=16),
        xaxis_title="M€",
    )
    return fig


# ---------------------------------------------------------------------------
# Panel de transparencia de necesidades
# ---------------------------------------------------------------------------

_POS_LABEL = {
    "GK": "Portero", "CB": "Central", "RB": "Lat. derecho", "LB": "Lat. izquierdo",
    "DM": "Pivote", "CM": "Centrocampista", "AM": "Mediapunta",
    "RW": "Extremo dcho.", "LW": "Extremo izdo.", "ST": "Delantero centro",
}

# Mínimo de jugadores por posición según formación
_POS_TARGETS: dict[str, dict[str, int]] = {
    "4-2-3-1": {"GK": 2, "CB": 2, "RB": 1, "LB": 1, "DM": 2, "CM": 0, "AM": 1, "RW": 1, "LW": 1, "ST": 1},
    "4-3-3":   {"GK": 2, "CB": 2, "RB": 1, "LB": 1, "DM": 1, "CM": 2, "AM": 0, "RW": 1, "LW": 1, "ST": 1},
    "4-4-2":   {"GK": 2, "CB": 2, "RB": 1, "LB": 1, "DM": 1, "CM": 1, "AM": 0, "RW": 1, "LW": 1, "ST": 2},
    "3-5-2":   {"GK": 2, "CB": 3, "RB": 0, "LB": 0, "DM": 2, "CM": 1, "AM": 1, "RW": 1, "LW": 1, "ST": 2},
}


def _needs_panel(cp: dict, players_all: list[dict]) -> html.Div:
    """Panel de necesidades rediseñado: lista visual compacta por posición."""
    from datetime import date as _date
    today = _date.today()

    formation = (cp.get("tactics", {}) or {}).get("base_formation", "4-2-3-1") or "4-2-3-1"
    formation = str(formation).strip().replace(" ", "-")
    target = _POS_TARGETS.get(formation, _POS_TARGETS["4-2-3-1"])

    counts: dict[str, int] = {}
    pos_players: dict[str, list] = {}
    for p in players_all:
        pos = str(p.get("position", "")).upper()
        if pos in target:
            counts[pos] = counts.get(pos, 0) + 1
            pos_players.setdefault(pos, []).append(p)

    # Resumen global
    n_cubierto = sum(1 for pos, n in target.items() if n > 0 and counts.get(pos, 0) >= n)
    n_reforzar = sum(1 for pos, n in target.items() if n > 0 and counts.get(pos, 0) == n - 1)
    n_falta    = sum(1 for pos, n in target.items() if n > 0 and counts.get(pos, 0) < n - 1)

    def _pos_row(pos, needed):
        have  = counts.get(pos, 0)
        delta = have - needed
        if delta >= 0:
            st_color, st_bg, st_icon = "#166534", "#DCFCE7", "✓"
        elif delta == -1:
            st_color, st_bg, st_icon = "#92400E", "#FEF9C3", "⚠"
        else:
            st_color, st_bg, st_icon = "#991B1B", "#FEE2E2", "✗"

        # Chip de contratos urgentes solo si la posición está cubierta
        contract_chip = None
        if delta >= 0:
            _years = []
            for _p in pos_players.get(pos, []):
                try:
                    _years.append(int(str(_p.get("contract_end", "9999"))[:4]))
                except (ValueError, TypeError):
                    _years.append(9999)
            urgent = sum(1 for y in _years if y <= today.year)
            warn   = sum(1 for y in _years if today.year < y <= today.year + 1)
            if urgent > 0:
                contract_chip = html.Span(
                    f"⚡{urgent}",
                    title=f"{urgent} contrato(s) expiran en {today.year}",
                    style={"fontSize": "9px", "fontWeight": "700", "color": "#991B1B",
                           "background": "#FEE2E2", "borderRadius": "99px",
                           "padding": "1px 5px", "marginLeft": "3px"},
                )
            elif warn > 0:
                contract_chip = html.Span(
                    f"~{warn}",
                    title=f"{warn} contrato(s) vencen pronto",
                    style={"fontSize": "9px", "fontWeight": "700", "color": "#92400E",
                           "background": "#FEF9C3", "borderRadius": "99px",
                           "padding": "1px 5px", "marginLeft": "3px"},
                )

        bg, fg = POS_COLOR.get(pos, ("#F3F4F6", "#374151"))
        return html.Div([
            # Pos badge + nombre
            html.Div([
                html.Span(pos, style={
                    "background": bg, "color": fg,
                    "padding": "2px 7px", "borderRadius": "99px",
                    "fontSize": "10px", "fontWeight": "700",
                    "flexShrink": "0", "minWidth": "34px", "textAlign": "center",
                }),
                html.Span(_POS_LABEL.get(pos, pos), style={
                    "fontSize": "11px", "color": "#374151",
                    "marginLeft": "7px", "whiteSpace": "nowrap",
                    "overflow": "hidden", "textOverflow": "ellipsis",
                }),
            ], style={"display": "flex", "alignItems": "center",
                      "flex": "1", "minWidth": "0", "overflow": "hidden"}),
            # Contador + estado + chip
            html.Div([
                html.Span(str(have), style={
                    "fontSize": "15px", "fontWeight": "800",
                    "color": st_color, "lineHeight": "1",
                }),
                html.Span(f"/{needed}", style={
                    "fontSize": "10px", "color": "#9CA3AF", "marginRight": "6px",
                }),
                html.Span(st_icon, style={
                    "fontSize": "11px", "fontWeight": "700",
                    "color": st_color, "background": st_bg,
                    "borderRadius": "99px", "padding": "2px 7px",
                }),
                *([contract_chip] if contract_chip else []),
            ], style={"display": "flex", "alignItems": "center",
                      "gap": "2px", "flexShrink": "0"}),
        ], style={
            "display": "flex", "alignItems": "center",
            "justifyContent": "space-between",
            "padding": "5px 2px", "borderBottom": "1px solid #F3F4F6",
        })

    _GROUPS = [
        ("Portería",    ["GK"]),
        ("Defensa",     ["CB", "RB", "LB"]),
        ("Centrocampo", ["DM", "CM", "AM"]),
        ("Ataque",      ["RW", "LW", "ST"]),
    ]

    sections = []
    for grp_name, positions in _GROUPS:
        items = [_pos_row(pos, target[pos])
                 for pos in positions if target.get(pos, 0) > 0]
        if not items:
            continue
        sections.append(html.Div([
            html.Div(grp_name, style={
                "fontSize": "9px", "fontWeight": "700", "color": "#9CA3AF",
                "textTransform": "uppercase", "letterSpacing": ".08em",
                "padding": "6px 2px 3px",
            }),
            *items,
        ]))

    return html.Div([
        # Cabecera
        html.Div([
            html.Div([
                html.I(className="ti ti-layout-list",
                       style={"color": _ROJO, "fontSize": "14px", "marginRight": "7px"}),
                html.Span("Necesidades 2026/27", style={
                    "fontSize": "12px", "fontWeight": "700", "color": _AZUL,
                }),
            ], style={"display": "flex", "alignItems": "center"}),
            html.Span(formation, style={
                "fontSize": "10px", "fontWeight": "700", "color": "#fff",
                "background": _AZUL, "borderRadius": "6px", "padding": "2px 9px",
            }),
        ], style={"display": "flex", "alignItems": "center",
                  "justifyContent": "space-between", "marginBottom": "10px"}),

        # Resumen de cobertura
        html.Div([
            html.Div([
                html.Div(str(n_cubierto), style={"fontSize": "18px", "fontWeight": "800",
                                                  "color": "#166534", "lineHeight": "1"}),
                html.Div("cubiertas", style={"fontSize": "9px", "color": "#6B7280",
                                             "marginTop": "1px"}),
            ], style={"textAlign": "center", "background": "#DCFCE7", "borderRadius": "8px",
                      "padding": "7px 0", "flex": "1"}),
            html.Div([
                html.Div(str(n_reforzar), style={"fontSize": "18px", "fontWeight": "800",
                                                  "color": "#92400E", "lineHeight": "1"}),
                html.Div("reforzar", style={"fontSize": "9px", "color": "#6B7280",
                                            "marginTop": "1px"}),
            ], style={"textAlign": "center", "background": "#FEF9C3", "borderRadius": "8px",
                      "padding": "7px 0", "flex": "1"}),
            html.Div([
                html.Div(str(n_falta), style={"fontSize": "18px", "fontWeight": "800",
                                               "color": "#991B1B", "lineHeight": "1"}),
                html.Div("faltan", style={"fontSize": "9px", "color": "#6B7280",
                                          "marginTop": "1px"}),
            ], style={"textAlign": "center", "background": "#FEE2E2", "borderRadius": "8px",
                      "padding": "7px 0", "flex": "1"}),
        ], style={"display": "flex", "gap": "8px", "marginBottom": "10px"}),

        # Lista por posición agrupada
        *sections,

        html.Div("Calculado desde la formación base del YAML",
                 style={"fontSize": "9px", "color": "#9CA3AF",
                        "fontStyle": "italic", "marginTop": "10px"}),
    ], className="card-flat")


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

def layout(**_params):
    cp = club_profile()
    sq = cp.get("squad_2025_26", {})
    needs = cp.get("squad_needs_priority", [])
    fin = cp.get("finances_eur", {})
    budget = fin.get("transfer_budget_net_eur", 0)

    players_all = []
    for grp in sq.values():
        if isinstance(grp, list):
            players_all.extend(p for p in grp if isinstance(p, dict))

    # Estilos de juego: construye {yaml_name: role_label} resolviendo nombres OPTA
    try:
        from src.utils.lateral_position import build_lateral_map, ROLE_TYPE_LABELS as _RTL
        _proc = Path(settings()["paths"]["data_processed"])
        _lat  = build_lateral_map(
            _proc / "player_seasons_enriched.parquet",
            _proc / "master_players.parquet",
        )
        _rt_raw = {
            n: rt for n, rt in zip(_lat["name"], _lat["role_type"])
            if rt is not None
        }
        # Resolver nombres YAML completos → etiquetas de estilo
        _resolved_styles = _squad_role_map(players_all, _rt_raw, _RTL)
    except Exception:
        _resolved_styles = {}
        _RTL = {}

    total_mv   = sum(p.get("market_value", 0) for p in players_all)
    today = date.today()
    expiring   = sum(1 for p in players_all
                     if int(str(p.get("contract_end", "9999"))[:4]) <= today.year + 1)
    total_players = len(players_all)
    n_cedidos  = sum(1 for p in players_all if p.get("loan_from"))
    n_cedidos_out = sum(1 for p in players_all if p.get("loan_to"))

    # Tabla editable de contratos
    edit_data = [
        {"Jugador": p.get("name", ""), "Posición": p.get("position", ""),
         "Fin contrato": str(p.get("contract_end", ""))[:10],
         "Valor TM (€)": p.get("market_value", 0) or 0}
        for p in players_all
    ]

    def _kpi(icon, label, value, sub, _grad=None, _light=None, variant=""):
        return html.Div([
            html.Div([html.I(className=f"ti {icon}")], className=f"kpi-icon {variant}"),
            html.Div(value, className="kpi-value"),
            html.Div(label, className="kpi-label"),
            html.Div(sub,   className="kpi-sub"),
        ], className=f"kpi-modern {variant}")

    mv_fmt = f"{total_mv/1e6:.0f}M€" if total_mv >= 1e6 else f"{total_mv:,}€"

    return html.Div([
        dcc.Location(id="plantilla-nav", refresh=True),
        dcc.Location(id="plantilla-reload", refresh=True),

        # ── Hero ─────────────────────────────────────────────────────────────
        html.Div([
            html.Div([
                html.Div([html.I(className="ti ti-users-group",
                           style={"fontSize":"26px","color":"#fff"})],
                    style={"background":"rgba(227,6,19,.20)","borderRadius":"12px",
                           "padding":"10px","marginRight":"18px","flexShrink":"0",
                           "border":"1px solid rgba(227,6,19,.30)"}),
                html.Div([
                    html.Div("PLANTILLA 2026/27", style={"fontSize":"9px","fontWeight":"700",
                        "color":"rgba(255,255,255,.45)","letterSpacing":".14em","marginBottom":"3px"}),
                    html.H1("Rayo Vallecano", style={"fontSize":"22px","fontWeight":"900",
                        "color":"#fff","margin":"0 0 2px","letterSpacing":"-.02em"}),
                    html.Div("Clic en cualquier jugador para ver su perfil completo",
                        style={"fontSize":"10.5px","color":"rgba(255,255,255,.45)"}),
                ]),
            ], style={"display":"flex","alignItems":"center","flex":"1"}),
            html.Div([
                *[html.Div([
                    html.Div(v, style={"fontSize":"22px","fontWeight":"900","color":"#fff","lineHeight":"1"}),
                    html.Div(l, style={"fontSize":"9px","color":"rgba(255,255,255,.45)","fontWeight":"600","marginTop":"2px"}),
                ], style={"textAlign":"center","padding":"0 16px","borderRight":s})
                  for v,l,s in [
                    (str(total_players), "jugadores", "1px solid rgba(255,255,255,.12)"),
                    (mv_fmt, "valor mercado", "1px solid rgba(255,255,255,.12)"),
                    (str(expiring), "contratos urgentes", "none"),
                ]],
            ], style={"display":"flex","alignItems":"center","flexShrink":"0"}),
        ], style={"background":"linear-gradient(135deg,#0A0B0E 0%,#1E2028 60%,#141519 100%)",
                  "borderRadius":"18px","padding":"20px 26px","marginBottom":"18px",
                  "display":"flex","justifyContent":"space-between","alignItems":"center",
                  "boxShadow":"0 8px 32px rgba(0,0,0,.28)","borderLeft":"4px solid #E30613"}),

        # ── KPIs ──────────────────────────────────────────────────────────────
        html.Div("RESUMEN DE PLANTILLA", className="section-label"),
        dbc.Row([
            dbc.Col(_kpi("ti-users","Jugadores",str(total_players),"en plantilla"), md=2),
            dbc.Col(_kpi("ti-coin-euro","Valor de mercado",mv_fmt,"Transfermarkt may-26"), md=2),
            dbc.Col(_kpi("ti-wallet","Presupuesto",f"{budget/1e6:.0f}M€","neto estimado 2026/27","","","success"), md=2),
            dbc.Col(_kpi("ti-alert-triangle","Contratos urgentes",str(expiring),f"vencen ≤{today.year+1}","","","danger"), md=2),
            dbc.Col(_kpi("ti-transfer-in","Cedidos IN",str(n_cedidos),"cesiones de otros clubes","","","warning"), md=2),
            dbc.Col(_kpi("ti-transfer-out","Cedidos OUT",str(n_cedidos_out),"vuelven de cesión","","",""), md=2),
        ], className="g-3 mb-4"),

        html.Div("ANÁLISIS VISUAL", className="section-label"),
        dbc.Row([
            dbc.Col(html.Div(dcc.Graph(figure=_chart_age_scatter(players_all),
                config={"displayModeBar":False}, style={"height":"220px"}),
                className="card-flat", style={"overflow":"hidden","padding":"0"}), md=3),
            dbc.Col(html.Div(dcc.Graph(figure=_chart_position_donut(players_all),
                config={"displayModeBar":False}, style={"height":"220px"}),
                className="card-flat", style={"overflow":"hidden","padding":"0"}), md=3),
            dbc.Col(html.Div(dcc.Graph(figure=_chart_contract_status(players_all),
                config={"displayModeBar":False}, style={"height":"220px"}),
                className="card-flat", style={"overflow":"hidden","padding":"0"}), md=3),
            dbc.Col(html.Div(dcc.Graph(figure=_chart_mv_bars(players_all),
                config={"displayModeBar":False}, style={"height":"220px"}),
                className="card-flat", style={"overflow":"hidden","padding":"0"}), md=3),
        ], className="g-3 mb-4"),

        dbc.Row([
            dbc.Col([
                group_table("goalkeepers", sq.get("goalkeepers", []), _resolved_styles),
                group_table("defenders",   sq.get("defenders",   []), _resolved_styles),
                group_table("midfielders", sq.get("midfielders", []), _resolved_styles),
                group_table("forwards",    sq.get("forwards",    []), _resolved_styles),
            ], md=8),

            dbc.Col([
                html.Div([
                    html.Div("Leyenda contratos", className="section-label"),
                    *[html.Div([
                        html.Div(style={"width": "8px", "height": "8px", "borderRadius": "50%",
                                        "background": c, "flexShrink": "0"}),
                        html.Span(t, style={"fontSize": "12px", "color": "var(--t2)"}),
                    ], style={"display": "flex", "alignItems": "center",
                              "gap": "8px", "marginBottom": "6px"})
                    for c, t in [
                        ("var(--danger)", f"Finaliza ≤{today.year + 1} — acción urgente"),
                        ("var(--warning)", f"Finaliza en {today.year + 2} — vigilar"),
                        ("var(--success)", "Contrato largo — seguro"),
                    ]],
                    html.P("Pasa el ratón sobre el año del contrato para ver la fecha exacta.",
                           style={"fontSize": "10px", "color": "var(--t4)",
                                  "marginTop": "8px", "fontStyle": "italic"}),
                ], className="card-flat", style={"marginBottom": "12px"}),

                _needs_panel(cp, players_all),
            ], md=4),
        ], className="g-3 mb-3"),

        # ── Edición de contratos ──
        html.Div([
            html.Button([
                html.I(className="ti ti-edit", style={"marginRight": "6px"}),
                "Editar datos de contrato y valor",
            ], id="btn-edit-contracts", className="btn-outline",
               style={"fontSize": "12px"}),
            html.Span("Los cambios se guardan en club_profile.yaml",
                      style={"fontSize": "10px", "color": "var(--t4)", "marginLeft": "10px"}),
        ], style={"marginBottom": "8px"}),
        dbc.Collapse([
            html.Div([
                html.Div("Editar contratos y valores de mercado",
                       className="section-label"),
                html.P(
                    "Modifica directamente las celdas. Fin contrato en formato AAAA-MM-DD. "
                    "Valor TM en euros (eAAA-MM-DD. "
                    "Valor TM en euros (ej: 5000000 = 5M€).",
                    style={"fontSize": "11px", "color": "#6B7280", "marginBottom": "12px"}),
                dash_table.DataTable(
                    id="edit-contracts-table",
                    data=edit_data,
                    columns=[
                        {"name": "Jugador", "id": "Jugador", "editable": False},
                        {"name": "Pos.", "id": "Posición", "editable": False},
                        {"name": "Fin contrato", "id": "Fin contrato", "editable": True},
                        {"name": "Valor TM (€)", "id": "Valor TM (€)", "editable": True,
                         "type": "numeric"},
                    ],
                    style_cell={"fontSize": "12px", "fontFamily": "Inter, sans-serif",
                                "padding": "6px 10px", "textAlign": "left"},
                    style_header={"fontWeight": "700", "fontSize": "11px",
                                  "color": "#6B7280", "textTransform": "uppercase",
                                  "letterSpacing": ".05em", "background": "#F9FAFB"},
                    style_data_conditional=[
                        {"if": {"column_editable": True},
                         "background": "#FFFBEB", "borderLeft": "2px solid #F59E0B"},
                    ],
                    page_size=30,
                    style_table={"overflowX": "auto"},
                ),
                html.Div([
                    html.Button("Guardar cambios", id="btn-save-contracts",
                               className="btn-primary",
                               style={"marginTop": "10px", "marginRight": "8px"}),
                    html.Span(id="save-contracts-feedback",
                              style={"fontSize": "11px", "color": "var(--success)"}),
                ]),
            ], className="card-flat"),
        ], id="collapse-edit-contracts", is_open=False),

        criteria_accordion("plantilla"),
    ])


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@callback(
    Output("collapse-edit-contracts", "is_open"),
    Input("btn-edit-contracts", "n_clicks"),
    State("collapse-edit-contracts", "is_open"),
    prevent_initial_call=True,
)
def _toggle_edit(n, is_open):
    return not is_open


def _read_yaml_safe(path: Path) -> dict:
    """Lee un YAML tolerando posibles bytes nulos por escrituras corruptas previas."""
    raw = path.read_bytes()
    if b"\x00" in raw:
        raw = raw.replace(b"\x00", b"")
    return yaml.safe_load(raw.decode("utf-8", "ignore")) or {}


def _write_yaml_atomic(path: Path, data: dict) -> None:
    """Escribe el YAML de forma atomica (temporal + replace) para evitar
    archivos a medio escribir si el proceso se interrumpe."""
    import os
    import tempfile
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


@callback(
    Output("save-contracts-feedback", "children"),
    Output("plantilla-reload", "href"),
    Input("btn-save-contracts", "n_clicks"),
    State("edit-contracts-table", "data"),
    prevent_initial_call=True,
)
def _save_contracts(n, rows):
    if not n or not rows:
        return no_update, no_update
    try:
        data = _read_yaml_safe(CONFIG)
        sq = data.get("squad_2025_26", {})
        name_to_row = {r["Jugador"]: r for r in rows}
        changed = 0
        for grp_key, grp_players in sq.items():
            if not isinstance(grp_players, list):
                continue
            for p in grp_players:
                if not isinstance(p, dict):
                    continue
                row = name_to_row.get(p.get("name", ""))
                if row:
                    p["contract_end"] = row.get("Fin contrato") or p.get("contract_end")
                    try:
                        mv = int(float(row.get("Valor TM (€)", 0) or 0))
                        if mv >= 0:
                            p["market_value"] = mv
                    except (ValueError, TypeError):
                        pass
                    changed += 1
        _write_yaml_atomic(CONFIG, data)
        import time as _time
        href = f"/plantilla?saved={int(_time.time())}"
        return f"✓ Guardado ({changed} jugadores). Actualizando…", href
    except Exception as e:
        return f"Error al guardar: {e}", no_update


@callback(
    Output("plantilla-nav", "href"),
    Input({"type": "plantilla-row", "name": dash.ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def _nav_to_player(clicks):
    import urllib.parse as _up
    ctx = dash.callback_context
    if not ctx.triggered:
        return no_update
    prop = ctx.triggered[0]["prop_id"]
    if not prop or '"name":' not in prop:
        return no_update
    import json as _json
    try:
        id_part = prop.split(".")[0]
        id_dict = _json.loads(id_part)
        name = id_dict.get("name", "")
        if name:
            return f"/jugador?name={_up.quote(name)}&team={_up.quote('Rayo Vallecano')}"
    except Exception:
        pass
    return no_update
