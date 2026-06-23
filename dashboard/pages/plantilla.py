# -*- coding: utf-8 -*-
"""Página de plantilla actual del Rayo — diseño moderno con visualizaciones."""
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
    initials = "".join(w[0].upper() for w in name.split()[:2] if w)
    year = int(str(end)[:4]) if end else 9999
    row_bg = "#FFF5F5" if year <= 2026 else ("#FFFFFF" if i % 2 == 0 else "#FAFAFA")
    # role_map aquí ya es {yaml_name: label} (pre-resuelto por _squad_role_map)
    role_label  = (role_map or {}).get(name, "")
    is_inferred = bool(role_label)
    if not role_label:
        role_label = _POS_STYLE_FALLBACK.get(pos.upper(), "Sin datos")
    return html.Tr([
        html.Td(html.Div([
            html.Div(initials, style={
                "width": "32px", "height": "32px", "borderRadius": "50%",
                "background": _AZUL, "color": "#fff",
                "display": "flex", "alignItems": "center", "justifyContent": "center",
                "fontSize": "11px", "fontWeight": "600", "flexShrink": "0",
            }),
            html.Div([
                html.Span(name, style={"fontSize": "13px", "fontWeight": "600", "color": _AZUL}),
                (html.Span(f" cedido de {loan}", style={
                    "fontSize": "10px", "color": "#1D4ED8", "marginLeft": "6px",
                    "background": "#EFF6FF", "borderRadius": "6px", "padding": "1px 6px",
                }) if loan else html.Span()),
            ]),
        ], style={"display": "flex", "alignItems": "center", "gap": "10px"})),
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
    ], style={"background": "#fff", "border": "1px solid #E5E7EB", "borderRadius": "10px",
              "padding": "16px 18px", "marginBottom": "12px",
              "boxShadow": "0 1px 3px rgba(0,0,0,.06)"})


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
    """Panel de transparencia: formación → objetivo por posición → actual."""
    from datetime import date as _date
    today = _date.today()

    formation = (cp.get("tactics", {}) or {}).get("base_formation", "4-2-3-1") or "4-2-3-1"
    formation = str(formation).strip().replace(" ", "-")
    target = _POS_TARGETS.get(formation, _POS_TARGETS["4-2-3-1"])

    # Contar jugadores actuales por posición y agrupar para alertas de contrato
    counts: dict[str, int] = {}
    pos_players: dict[str, list] = {}
    for p in players_all:
        pos = str(p.get("position", "")).upper()
        if pos in target:
            counts[pos] = counts.get(pos, 0) + 1
            pos_players.setdefault(pos, []).append(p)

    rows = []
    for pos, needed in sorted(target.items(), key=lambda x: list(target.keys()).index(x[0])):
        if needed == 0:
            continue
        have  = counts.get(pos, 0)
        delta = have - needed

        if delta >= 0:
            status_color = "#166534"
            status_bg    = "#F0FDF4"
            status_txt   = "✓ Cubierto"
            # Alerta de contratos en posiciones cubiertas
            plist = pos_players.get(pos, [])
            _years = []
            for _p in plist:
                try:
                    _years.append(int(str(_p.get("contract_end", "9999"))[:4]))
                except (ValueError, TypeError):
                    _years.append(9999)
            urgent = sum(1 for y in _years if y <= today.year)
            warn   = sum(1 for y in _years if today.year < y <= today.year + 1)
            if urgent > 0:
                contract_chip = html.Span(
                    f"⚠ {urgent} expira{'n' if urgent > 1 else ''} en {today.year}",
                    title="Posición cubierta pero con contratos urgentes",
                    style={"fontSize": "9px", "fontWeight": "600", "color": "#991B1B",
                           "background": "#FEE2E2", "borderRadius": "4px",
                           "padding": "1px 6px", "marginLeft": "5px",
                           },
                )
            elif warn > 0:
                contract_chip = html.Span(
                    f"~ {warn} expira{'n' if warn > 1 else ''} {today.year + 2}",
                    title="Posición cubierta pero hay contratos por vigilar",
                    style={"fontSize": "9px", "fontWeight": "600", "color": "#92400E",
                           "background": "#FEF3C7", "borderRadius": "4px",
                           "padding": "1px 6px", "marginLeft": "5px",
                           },
                )
            else:
                contract_chip = html.Span()
        elif delta == -1:
            status_color  = "#92400E"
            status_bg     = "#FFFBEB"
            status_txt    = "⚠ Reforzar"
            contract_chip = html.Span()
        else:
            status_color  = "#991B1B"
            status_bg     = "#FFF1F2"
            status_txt    = "✗ Falta"
            contract_chip = html.Span()

        rows.append(html.Tr([
            html.Td(html.Span(pos, style={
                "background": POS_COLOR.get(pos, ("#F3F4F6", "#374151"))[0],
                "color": POS_COLOR.get(pos, ("#F3F4F6", "#374151"))[1],
                "padding": "2px 8px", "borderRadius": "99px",
                "fontSize": "10px", "fontWeight": "700",
            })),
            html.Td(_POS_LABEL.get(pos, pos), style={"fontSize": "11px", "color": "#374151", "padding": "5px 8px"}),
            html.Td(str(needed), style={"fontSize": "11px", "textAlign": "center",
                                        "color": "#6B7280", "padding": "5px 8px"}),
            html.Td(str(have), style={"fontSize": "11px", "textAlign": "center",
                                      "fontWeight": "700", "color": "#1A1A2E", "padding": "5px 8px"}),
            html.Td(html.Div([
                html.Span(status_txt, style={
                    "fontSize": "10px", "fontWeight": "600", "color": status_color,
                    "background": status_bg, "padding": "2px 8px", "borderRadius": "99px",
                }),
                contract_chip,
            ], style={"display": "flex", "alignItems": "center", "flexWrap": "wrap", "gap": "4px"}),
            style={"padding": "5px 8px"}),
        ], style={"borderBottom": "1px solid #F3F4F6"}))

    return html.Div([
        html.Div([
            html.I(className="ti ti-layout-list", style={"color": _ROJO, "marginRight": "6px"}),
            html.Span("Necesidades 2026/27", style={
                "fontSize": "10px", "fontWeight": "700", "color": "#9CA3AF",
                "textTransform": "uppercase", "letterSpacing": ".06em",
            }),
        ], style={"marginBottom": "8px"}),
        html.Div([
            html.Span("Formación base: ", style={"fontSize": "10px", "color": "#9CA3AF"}),
            html.Span(formation, style={"fontSize": "10px", "fontWeight": "700",
                                        "color": _AZUL, "marginRight": "8px"}),
            html.Span("(desde club_profile.yaml → tactics.base_formation)",
                      style={"fontSize": "9px", "color": "#9CA3AF", "fontStyle": "italic"}),
        ], style={"marginBottom": "8px"}),
        html.Table([
            html.Thead(html.Tr([
                html.Th("Pos.", style={"fontSize": "9px", "color": "#9CA3AF",
                                       "textTransform": "uppercase", "padding": "4px 8px",
                                       "borderBottom": f"2px solid {_ROJO}"}),
                html.Th("Rol", style={"fontSize": "9px", "color": "#9CA3AF",
                                      "textTransform": "uppercase", "padding": "4px 8px",
                                      "borderBottom": f"2px solid {_ROJO}"}),
                html.Th("Objetivo", style={"fontSize": "9px", "color": "#9CA3AF",
                                           "textTransform": "uppercase", "padding": "4px 8px",
                                           "textAlign": "center",
                                           "borderBottom": f"2px solid {_ROJO}"}),
                html.Th("Actual", style={"fontSize": "9px", "color": "#9CA3AF",
                                         "textTransform": "uppercase", "padding": "4px 8px",
                                         "textAlign": "center",
                                         "borderBottom": f"2px solid {_ROJO}"}),
                html.Th("Estado", style={"fontSize": "9px", "color": "#9CA3AF",
                                          "textTransform": "uppercase", "padding": "4px 8px",
                                          "borderBottom": f"2px solid {_ROJO}"}),
            ])),
            html.Tbody(rows),
        ], style={"width": "100%", "borderCollapse": "collapse", "marginBottom": "10px"}),
        html.Div([
            html.Span("Metodología: ", style={"fontSize": "9px", "fontWeight": "700", "color": "#6B7280"}),
            html.Span(
                "Los objetivos por posición se calculan automáticamente desde la formación base. "
                "El recuento actual usa las posiciones del YAML (name, position) — "
                "no valores estáticos definidos a mano.",
                style={"fontSize": "9px", "color": "#9CA3AF", "fontStyle": "italic"},
            ),
        ]),
    ], style={"background": "#fff", "border": "1px solid #E5E7EB", "borderRadius": "10px",
              "padding": "14px 16px", "boxShadow": "0 1px 3px rgba(0,0,0,.06)"})


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

    # Tabla editable de contratos
    edit_data = [
        {"Jugador": p.get("name", ""), "Posición": p.get("position", ""),
         "Fin contrato": str(p.get("contract_end", ""))[:10],
         "Valor TM (€)": p.get("market_value", 0) or 0}
        for p in players_all
    ]

    def _kpi(icon, label, value, sub, grad, light):
        return html.Div([
            html.Div([html.I(className=f"ti {icon}", style={"fontSize":"18px","color":"#fff"})],
                style={"background":grad,"borderRadius":"10px","width":"38px","height":"38px",
                       "display":"flex","alignItems":"center","justifyContent":"center",
                       "marginBottom":"10px","boxShadow":"0 3px 8px rgba(0,0,0,.14)"}),
            html.Div(value, style={"fontSize":"24px","fontWeight":"900","color":"#1A1A2E","lineHeight":"1","marginBottom":"2px"}),
            html.Div(label, style={"fontSize":"11px","fontWeight":"700","color":"#1A1A2E","marginBottom":"1px"}),
            html.Div(sub,   style={"fontSize":"10px","color":"#6B7280"}),
        ], style={"background":light,"border":"1px solid rgba(0,0,0,.06)","borderRadius":"14px",
                  "padding":"14px 16px","height":"100%","boxShadow":"0 2px 6px rgba(0,0,0,.05)"})

    mv_fmt = f"{total_mv/1e6:.0f}M€" if total_mv >= 1e6 else f"{total_mv:,}€"

    return html.Div([
        dcc.Location(id="plantilla-nav", refresh=True),

        # ── Hero ─────────────────────────────────────────────────────────────
        html.Div([
            html.Div([
                html.Div([html.I(className="ti ti-users-group",
                           style={"fontSize":"28px","color":"#fff"})],
                    style={"background":"rgba(255,255,255,.15)","borderRadius":"12px",
                           "padding":"10px","marginRight":"18px","flexShrink":"0"}),
                html.Div([
                    html.Div("PLANTILLA 2026/27", style={"fontSize":"9px","fontWeight":"700",
                        "color":"rgba(255,255,255,.55)","letterSpacing":".14em","marginBottom":"3px"}),
                    html.H1("Rayo Vallecano", style={"fontSize":"22px","fontWeight":"900",
                        "color":"#fff","margin":"0 0 2px"}),
                    html.Div("Clic en cualquier jugador para ver su perfil completo",
                        style={"fontSize":"10px","color":"rgba(255,255,255,.5)"}),
                ]),
            ], style={"display":"flex","alignItems":"center","flex":"1"}),
            html.Div([
                *[html.Div([
                    html.Div(v, style={"fontSize":"22px","fontWeight":"900","color":"#fff","lineHeight":"1"}),
                    html.Div(l, style={"fontSize":"9px","color":"rgba(255,255,255,.55)","fontWeight":"600","marginTop":"2px"}),
                ], style={"textAlign":"center","padding":"0 16px","borderRight":s})
                  for v,l,s in [
                    (str(total_players), "jugadores", "1px solid rgba(255,255,255,.15)"),
                    (mv_fmt, "valor mercado", "1px solid rgba(255,255,255,.15)"),
                    (str(expiring), "contratos urgentes", "none"),
                ]],
            ], style={"display":"flex","alignItems":"center","flexShrink":"0"}),
        ], style={"background":"linear-gradient(135deg,#1E40AF 0%,#1D4ED8 60%,#2563EB 100%)",
                  "borderRadius":"18px","padding":"20px 26px","marginBottom":"18px",
                  "display":"flex","justifyContent":"space-between","alignItems":"center",
                  "boxShadow":"0 8px 24px rgba(30,64,175,.25)"}),

        # ── KPIs ──────────────────────────────────────────────────────────────
        html.P("RESUMEN DE PLANTILLA", style={"fontSize":"9px","fontWeight":"700","color":"#6B7280",
               "letterSpacing":".08em","marginBottom":"10px"}),
        dbc.Row([
            dbc.Col(_kpi("ti-users","Jugadores",str(total_players),"en plantilla",
                "linear-gradient(135deg,#1E40AF,#3B82F6)","#EFF6FF"), md=2),
            dbc.Col(_kpi("ti-coin-euro","Valor de mercado",mv_fmt,"Transfermarkt may-26",
                "linear-gradient(135deg,#5B21B6,#8B5CF6)","#F5F3FF"), md=2),
            dbc.Col(_kpi("ti-wallet","Presupuesto",f"{budget/1e6:.0f}M€","neto estimado 2026/27",
                "linear-gradient(135deg,#065F46,#10B981)","#ECFDF5"), md=2),
            dbc.Col(_kpi("ti-alert-triangle","Contratos urgentes",str(expiring),f"vencen ≤{today.year+1}",
                "linear-gradient(135deg,#DC2626,#EF4444)","#FFF1F2"), md=2),
            dbc.Col(_kpi("ti-transfer-in","Cedidos",str(n_cedidos),"cesiones de otros clubes",
                "linear-gradient(135deg,#78350F,#F59E0B)","#FFFBEB"), md=2),
            dbc.Col(_kpi("ti-layout-grid","Líneas","4","GK · DEF · MED · DEL",
                "linear-gradient(135deg,#374151,#6B7280)","#F9FAFB"), md=2),
        ], className="g-3 mb-4"),

        html.P("ANÁLISIS VISUAL", style={"fontSize":"9px","fontWeight":"700",
               "color":"#6B7280","letterSpacing":".08em","marginBottom":"10px"}),
        dbc.Row([
            dbc.Col(html.Div(dcc.Graph(figure=_chart_age_scatter(players_all),
                config={"displayModeBar":False}, style={"height":"220px"}),
                style={"background":"#fff","borderRadius":"12px","border":"1px solid #E5E7EB",
                       "overflow":"hidden","boxShadow":"0 1px 5px rgba(0,0,0,.05)"}), md=3),
            dbc.Col(html.Div(dcc.Graph(figure=_chart_position_donut(players_all),
                config={"displayModeBar":False}, style={"height":"220px"}),
                style={"background":"#fff","borderRadius":"12px","border":"1px solid #E5E7EB",
                       "overflow":"hidden","boxShadow":"0 1px 5px rgba(0,0,0,.05)"}), md=3),
            dbc.Col(html.Div(dcc.Graph(figure=_chart_contract_status(players_all),
                config={"displayModeBar":False}, style={"height":"220px"}),
                style={"background":"#fff","borderRadius":"12px","border":"1px solid #E5E7EB",
                       "overflow":"hidden","boxShadow":"0 1px 5px rgba(0,0,0,.05)"}), md=3),
            dbc.Col(html.Div(dcc.Graph(figure=_chart_mv_bars(players_all),
                config={"displayModeBar":False}, style={"height":"220px"}),
                style={"background":"#fff","borderRadius":"12px","border":"1px solid #E5E7EB",
                       "overflow":"hidden","boxShadow":"0 1px 5px rgba(0,0,0,.05)"}), md=3),
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
                    html.P("Leyenda contratos", style={"fontSize": "10px", "fontWeight": "600",
                        "color": "#9CA3AF", "textTransform": "uppercase",
                        "letterSpacing": ".06em", "marginBottom": "10px"}),
                    *[html.Div([
                        html.Div(style={"width": "8px", "height": "8px", "borderRadius": "50%",
                                        "background": c, "flexShrink": "0"}),
                        html.Span(t, style={"fontSize": "12px", "color": "#374151"}),
                    ], style={"display": "flex", "alignItems": "center",
                              "gap": "8px", "marginBottom": "6px"})
                    for c, t in [
                        ("#DC2626", f"Finaliza ≤{today.year + 1} — acción urgente"),
                        ("#F59E0B", f"Finaliza en {today.year + 2} — vigilar"),
                        ("#10B981", "Contrato largo — seguro"),
                    ]],
                    html.P("Pasa el ratón sobre el año del contrato para ver la fecha exacta.",
                           style={"fontSize": "10px", "color": "#9CA3AF",
                                  "marginTop": "8px", "fontStyle": "italic"}),
                ], style={"background": "#fff", "border": "1px solid #E5E7EB", "borderRadius": "10px",
                          "padding": "14px 16px", "marginBottom": "12px",
                          "boxShadow": "0 1px 3px rgba(0,0,0,.06)"}),

                _needs_panel(cp, players_all),
            ], md=4),
        ], className="g-3 mb-3"),

        # ── Edición de contratos ──
        html.Div([
            dbc.Button([
                html.I(className="ti ti-edit", style={"marginRight": "6px"}),
                "Editar datos de contrato y valor",
            ], id="btn-edit-contracts", color="light", size="sm",
               style={"fontSize": "12px", "border": "1px solid #D1D5DB"}),
            html.Span("Los cambios se guardan en club_profile.yaml",
                      style={"fontSize": "10px", "color": "#9CA3AF", "marginLeft": "10px"}),
        ], style={"marginBottom": "8px"}),
        dbc.Collapse([
            html.Div([
                html.P("Editar contratos y valores de mercado",
                       style={"fontSize": "12px", "fontWeight": "600",
                              "color": "#374151", "marginBottom": "8px"}),
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
                    dbc.Button("Guardar cambios", id="btn-save-contracts",
                               color="danger", size="sm",
                               style={"marginTop": "10px", "marginRight": "8px"}),
                    html.Span(id="save-contracts-feedback",
                              style={"fontSize": "11px", "color": "#166534"}),
                ]),
            ], style={"background": "#fff", "border": "1px solid #E5E7EB",
                      "borderRadius": "10px", "padding": "16px 18px",
                      "boxShadow": "0 1px 3px rgba(0,0,0,.06)"}),
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


@callback(
    Output("save-contracts-feedback", "children"),
    Input("btn-save-contracts", "n_clicks"),
    State("edit-contracts-table", "data"),
    prevent_initial_call=True,
)
def _save_contracts(n, rows):
    if not n or not rows:
        return no_update
    try:
        data = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
        sq = data.get("squad_2025_26", {})
        name_to_row = {r["Jugador"]: r for r in rows}
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
        CONFIG.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                          encoding="utf-8")
        return "✓ Guardado correctamente"
    except Exception as e:
        return f"Error: {e}"


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