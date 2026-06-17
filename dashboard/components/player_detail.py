"""
player_detail.py
================
Construye la vista detallada de un jugador: foto (Transfermarkt), percentiles de
todas las métricas por grupos, evolución por temporada, radar de roles y el
perfil/encaje automáticos. Todo desde player_seasons_enriched.parquet.
"""
from __future__ import annotations
import json
import unicodedata
from functools import lru_cache
from pathlib import Path

import pandas as pd
from dash import html, dcc
import dash_bootstrap_components as dbc

from src.utils.config import settings
from src.profiling.player_profile import (
    add_role_percentiles, profile_player_row, profile_single_player,
    career_aggregate, most_recent_team, ROLE_DEFINITIONS, ROLE_LABELS,
)
from src.fit.player_fit import evaluate_player_fit
from src.utils.market import get_value
from src.utils.leagues import league_name as _league_name

def _s(v) -> str | None:
    """None si el valor es vacío/nan."""
    if v is None:
        return None
    s = str(v).strip()
    return s if s not in ("", "nan", "None", "<NA>") else None

PROC = Path(settings()["paths"]["data_processed"])

import urllib.parse as _urlp
_SIL_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 120'>"
    "<rect width='100' height='120' fill='#F1F3F5'/>"
    "<circle cx='50' cy='44' r='21' fill='#B6BCC4'/>"
    "<path d='M16 116 C16 86 84 86 84 116 Z' fill='#B6BCC4'/></svg>"
)
SILHOUETTE = "data:image/svg+xml;utf8," + _urlp.quote(_SIL_SVG)

PLAYER_PHOTOS = PROC / "player_photos.json"


def _photo_override(key):
    if PLAYER_PHOTOS.exists():
        try:
            return json.load(open(PLAYER_PHOTOS, encoding="utf-8")).get(key)
        except Exception:
            return None
    return None

# Grupos de métricas para mostrar (col_p90 -> etiqueta)
METRIC_GROUPS = {
    "Ataque": [
        ("goals_p90", "Goles"), ("total_shots_p90", "Tiros"),
        ("shots_on_target_inc_goals_p90", "Tiros a puerta"),
        ("total_touches_in_opposition_box_p90", "Toques en área rival"),
    ],
    "Creación": [
        ("key_passes_attempt_assists_p90", "Pases clave"), ("goal_assists_p90", "Asistencias"),
        ("successful_dribbles_p90", "Regates"), ("successful_crosses_open_play_p90", "Centros"),
        ("through_balls_p90", "Pases entre líneas"),
    ],
    "Pase": [
        ("total_successful_passes_excl_crosses_corners_p90", "Pases completados"),
        ("forward_passes_p90", "Pases hacia delante"),
        ("successful_passes_opposition_half_p90", "Pases en campo rival"),
        ("successful_long_passes_p90", "Pases largos"),
    ],
    "Defensa": [
        ("tackles_won_p90", "Entradas ganadas"), ("interceptions_p90", "Intercepciones"),
        ("recoveries_p90", "Recuperaciones"), ("blocks_p90", "Bloqueos"),
        ("total_clearances_p90", "Despejes"), ("aerial_duels_won_p90", "Duelos aéreos"),
        ("ground_duels_won_p90", "Duelos en suelo"),
    ],
}

SEASON_ORDER = {"2025-2026": 6, "2025": 5, "2024-2025": 4, "2023-2024": 3,
                "2022-2023": 2, "2021-2022": 1}


@lru_cache(maxsize=1)
def enriched() -> pd.DataFrame:
    p = PROC / "player_seasons_enriched.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()


def _n(s):
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()


def _needs():
    p = PROC / "squad_profile.json"
    if p.exists():
        return json.load(open(p, encoding="utf-8")).get("needs", {})
    return {}


def player_options(min_minutes: int = 1000):
    """Opciones para el buscador: jugadores con minutos en las 2 últimas temporadas."""
    df = enriched()
    if df.empty:
        return []
    recent = df[df["season"].isin(["2024-2025", "2025-2026", "2025"])]
    recent = recent[pd.to_numeric(recent["minutes"], errors="coerce").fillna(0) >= min_minutes]
    opts = (recent[["name", "team"]].drop_duplicates()
            .assign(lbl=lambda d: d["name"] + " · " + d["team"]))
    return [{"label": r.lbl, "value": f"{r.name}|||{r.team}"} for r in opts.itertuples()]


def _find_rows(name, team=None):
    df = enriched()
    if df.empty:
        return df
    cand = df[df["name"].map(_n) == _n(name)]
    if cand.empty:
        cand = df[df["name"].map(_n).str.contains(_n(name).split()[-1], na=False)]
    if team:
        t = cand[cand["team"].map(_n).str.contains(_n(team).split()[0], na=False)]
        if not t.empty:
            cand = t
    return cand


def _bar(label, pct, value=None):
    pct = 0 if pct is None or pd.isna(pct) else max(0, min(100, pct))
    color = "#10B981" if pct >= 66 else ("#F59E0B" if pct >= 40 else "#E30613")
    return html.Div([
        html.Span(label, style={"fontSize": "11px", "color": "#374151", "width": "150px",
                                "display": "inline-block"}),
        html.Div(style={"height": "8px", "background": "#F3F4F6", "borderRadius": "99px",
                        "flex": "1", "overflow": "hidden"},
                 children=html.Div(style={"height": "100%", "width": f"{pct}%",
                                          "background": color, "borderRadius": "99px"})),
        html.Span(f"{int(pct)}", style={"fontSize": "10px", "color": "#6B7280", "width": "44px",
                  "textAlign": "right", "marginLeft": "6px"}),
    ], style={"display": "flex", "alignItems": "center", "gap": "6px", "marginBottom": "5px"})


def _radar(role_scores: dict):
    """Radar plotly de los scores de rol del jugador."""
    if not role_scores:
        return html.Div()
    items = list(role_scores.items())[:8]
    cats = [k for k, _ in items] + [items[0][0]]
    vals = [v for _, v in items] + [items[0][1]]
    fig = {
        "data": [{
            "type": "scatterpolar", "r": vals, "theta": cats, "fill": "toself",
            "fillcolor": "rgba(227,6,19,0.25)", "line": {"color": "#E30613"},
            "name": "Rol",
        }],
        "layout": {
            "polar": {"radialaxis": {"visible": True, "range": [0, 100], "tickfont": {"size": 8}},
                      "angularaxis": {"tickfont": {"size": 9}}},
            "showlegend": False, "margin": {"l": 60, "r": 60, "t": 20, "b": 20},
            "height": 320, "paper_bgcolor": "rgba(0,0,0,0)",
        },
    }
    return dcc.Graph(figure=fig, config={"displayModeBar": False})


def build_detail(name, team=None, league=None, age=None,
                 coach_style="Bloque medio / Equilibrado", with_photo=True):
    rows = _find_rows(name, team)
    if rows.empty:
        return dbc.Alert(f"No hay datos Opta de '{name}' en el scope actual.", color="warning")

    rows = rows.assign(_o=rows["season"].map(SEASON_ORDER).fillna(0)).sort_values("_o", ascending=False)
    real_team = most_recent_team(rows)
    latest_rows = rows[rows["team"] == real_team]
    latest = latest_rows.iloc[0] if not latest_rows.empty else rows.iloc[0]
    real_league = latest["league"]
    real_season = latest["season"]

    prof = profile_single_player(enriched(), latest["name"], team=real_team, age=age)
    pool = career_aggregate(enriched())

    foto = None
    tm_url = None
    _opta_id = _s(latest.get("player_id_src") or latest.get("player_id"))
    mvinfo = get_value(str(latest["name"]), opta_id=_opta_id)
    if mvinfo.get("photo_url"):
        foto = mvinfo["photo_url"]
    elif mvinfo.get("tm_id"):
        foto = f"https://img.a.transfermarkt.technology/portrait/big/{mvinfo['tm_id']}.jpg"
    if not foto:
        foto = _photo_override(f"{latest['name']}|{real_team}")
    if with_photo and not foto:
        try:
            from src.scraping.tm_photos import get_photo_url, _load_cache
            foto = get_photo_url(str(latest["name"]), team=str(real_team))
            tm_url = _load_cache().get(f"{latest['name']}|{real_team}", {}).get("tm_url")
        except Exception:
            foto = None
    if foto:
        foto_elem = html.Img(src=foto, style={"width": "120px", "height": "150px",
            "objectFit": "cover", "borderRadius": "10px", "border": "3px solid #E30613"})
    else:
        foto_elem = html.Img(src=SILHOUETTE, alt="sin foto",
            style={"width": "120px", "height": "150px", "objectFit": "cover",
                   "borderRadius": "10px", "border": "3px solid #E5E7EB", "background": "#F1F3F5"})

    role_lbl = prof["primary_role_label"] if prof else "n/d"
    fit = evaluate_player_fit(prof, _needs(), coach_style) if prof and prof.get("primary_role") else None

    header = html.Div([
        foto_elem,
        html.Div([
            html.H2(str(latest["name"]), style={"margin": "0 0 4px", "fontSize": "22px"}),
            html.Div([
                html.Span(real_team, style={"fontSize": "13px", "color": "#374151", "marginRight": "10px"}),
                html.Span(_league_name(real_league), style={"fontSize": "12px", "color": "#6B7280"}),
            ], style={"marginBottom": "6px"}),
            html.Div([
                html.Span(role_lbl, style={"fontSize": "12px", "fontWeight": "700", "color": "#fff",
                    "background": "#E30613", "borderRadius": "99px", "padding": "3px 12px"}),
                html.Span(f"{latest.get('position_raw','')}", style={"fontSize": "11px",
                    "color": "#6B7280", "marginLeft": "8px"}),
                (html.A("Ver en Transfermarkt", href=tm_url, target="_blank",
                        style={"fontSize": "11px", "marginLeft": "10px", "color": "#1D4ED8"})
                 if tm_url else html.Span()),
            ]),
            html.Div([
                (html.Span(f"Valor: {mvinfo['value_eur']/1e6:.1f}M EUR" if mvinfo.get('value_eur') else "Valor: n/d",
                    style={"fontSize": "11px", "background": "#EFF6FF", "color": "#1D4ED8",
                           "borderRadius": "99px", "padding": "2px 9px", "marginRight": "6px"})),
                (html.Span(f"Contrato: {str(mvinfo['contract_until'])[:10]}" if mvinfo.get('contract_until') else "Contrato: n/d",
                    style={"fontSize": "11px",
                           "background": "#FEE2E2" if str(mvinfo.get('contract_until', ''))[:4] in ("2026", "2027") else "#F3F4F6",
                           "color": "#991B1B" if str(mvinfo.get('contract_until', ''))[:4] in ("2026", "2027") else "#374151",
                           "borderRadius": "99px", "padding": "2px 9px", "marginRight": "6px"})),
                *([ html.Span(
                    f"Cláusula: {mvinfo['release_clause_eur']/1e6:.1f}M EUR",
                    style={"fontSize": "11px", "background": "#FFF7ED", "color": "#92400E",
                           "borderRadius": "99px", "padding": "2px 9px"})
                ] if mvinfo.get("release_clause_eur") else []),
            ], style={"marginTop": "6px"}),
            html.Div([
                html.Span(t, style={"fontSize": "11px", "background": "#F3F4F6", "color": "#374151",
                                    "borderRadius": "99px", "padding": "2px 9px", "marginRight": "6px"})
                for t in [
                    (f"Edad: {mvinfo['age']}" if mvinfo.get('age') else None),
                    (f"Pie: {mvinfo['foot']}" if mvinfo.get('foot') else None),
                    (f"Altura: {mvinfo['height']} m" if mvinfo.get('height') else None),
                    (f"Pos. TM: {mvinfo['position']}" if mvinfo.get('position') else None),
                    (f"Nac.: {mvinfo['nationality']}" if mvinfo.get('nationality') else None),
                ] if t
            ], style={"marginTop": "6px"}),
            html.Div([
                html.Span(
                    f"Datos: {mvinfo.get('data_source','TM')} · "
                    f"Actualizado: {str(mvinfo.get('last_updated',''))[:10] or 'desconocido'}",
                    style={"fontSize": "10px", "color": "#9CA3AF", "fontStyle": "italic"}
                ),
            ], style={"marginTop": "4px"}) if mvinfo.get("data_source") or mvinfo.get("last_updated") else html.Div(),
        ], style={"flex": "1"}),
        html.A("← Volver al Scouting", href="/scouting", style={"fontSize": "12px",
               "color": "#E30613", "textDecoration": "none", "alignSelf": "flex-start"}),
    ], style={"display": "flex", "gap": "18px", "alignItems": "flex-start", "marginBottom": "18px"})

    def _pct_for(metric):
        if metric not in pool.columns:
            return None
        vals = pd.to_numeric(pool[metric], errors="coerce")
        mins = pd.to_numeric(pool["minutes"], errors="coerce").fillna(0)
        ranked = vals.where(mins >= 450)
        pser = ranked.rank(pct=True) * 100
        match = pool.index[pool["name"] == latest["name"]]
        if len(match) == 0 or pd.isna(pser.get(match[0])):
            return None
        return float(pser.get(match[0]))

    metric_cols = []
    for grp, metrics in METRIC_GROUPS.items():
        bars = []
        for col, lab in metrics:
            pct = _pct_for(col)
            if pct is not None:
                bars.append(_bar(lab, pct))
        if bars:
            metric_cols.append(dbc.Col(html.Div([
                html.P(grp, style={"fontSize": "11px", "fontWeight": "700", "color": "#9CA3AF",
                       "textTransform": "uppercase", "letterSpacing": ".05em", "marginBottom": "8px"}),
                *bars,
            ], style={"background": "#fff", "border": "1px solid #E5E7EB", "borderRadius": "10px",
                      "padding": "14px 16px", "height": "100%"}), md=6, className="mb-3"))

    evo_cols = [("season", "Temp."), ("team", "Equipo"), ("minutes", "Min"),
                ("goals", "G"), ("goal_assists", "A"), ("total_shots", "Tiros"),
                ("key_passes_attempt_assists", "PC"), ("successful_dribbles", "Reg"),
                ("tackles_won", "Ent"), ("interceptions", "Int"), ("recoveries", "Rec")]
    evo_cols = [(c, l) for c, l in evo_cols if c in rows.columns]
    evo_head = html.Tr([html.Th(l, style={"fontSize": "10px", "color": "#9CA3AF", "padding": "4px 8px",
                        "textAlign": "left"}) for _, l in evo_cols])
    evo_body = []
    for _, r in rows.sort_values("_o", ascending=False).iterrows():
        tds = []
        for c, _l in evo_cols:
            v = r.get(c)
            if c == "minutes" and pd.notna(v):
                v = int(v)
            elif isinstance(v, float) and pd.notna(v):
                v = int(v) if c not in ("season",) else v
            tds.append(html.Td("—" if pd.isna(v) else str(v), style={"fontSize": "11px",
                       "padding": "4px 8px", "color": "#374151", "borderTop": "1px solid #F3F4F6"}))
        evo_body.append(html.Tr(tds))

    radar = _radar(prof["role_scores"]) if prof else html.Div()

    return html.Div([
        header,
        dbc.Row([
            dbc.Col([
                html.P("Perfil de rol (radar)", style={"fontSize": "11px", "fontWeight": "700",
                       "color": "#9CA3AF", "textTransform": "uppercase", "marginBottom": "4px"}),
                radar,
            ], md=5),
            dbc.Col([
                html.P("Resumen automático", style={"fontSize": "11px", "fontWeight": "700",
                       "color": "#9CA3AF", "textTransform": "uppercase", "marginBottom": "8px"}),
                html.P(f"Rol principal: {role_lbl}", style={"fontSize": "13px", "margin": "0 0 4px"}),
                html.P(f"Estilo: {prof['style_label'] if prof else 'n/d'}",
                       style={"fontSize": "12px", "color": "#1D4ED8", "margin": "0 0 4px"}),
                html.P(f"Roles secundarios: {', '.join(prof['secondary_roles_labels']) if prof and prof['secondary_roles_labels'] else '—'}",
                       style={"fontSize": "12px", "color": "#6B7280", "margin": "0 0 8px"}),
                html.Div([
                    html.Span(f"Confianza: {prof['confidence'] if prof else 'n/d'}", style={"fontSize": "10px",
                        "background": "#F3F4F6", "borderRadius": "99px", "padding": "2px 8px", "marginRight": "5px"}),
                    html.Span(f"Riesgo: {prof['risk_level'] if prof else 'n/d'}", style={"fontSize": "10px",
                        "background": "#FEF3C7", "borderRadius": "99px", "padding": "2px 8px", "marginRight": "5px"}),
                ]),
                html.P(fit["compatibilidad_plantilla_txt"] if fit else "", style={"fontSize": "11px",
                       "color": "#374151", "marginTop": "8px", "fontStyle": "italic"}),
            ], md=7),
        ], className="mb-3"),
        html.P("Percentiles por métrica · histórico completo (vs su posición)", style={"fontSize": "11px",
               "fontWeight": "700", "color": "#9CA3AF", "textTransform": "uppercase", "marginBottom": "8px"}),
        dbc.Row(metric_cols),
        html.P("Evolución por temporada", style={"fontSize": "11px", "fontWeight": "700",
               "color": "#9CA3AF", "textTransform": "uppercase", "margin": "10px 0 8px"}),
        html.Div(html.Table([html.Thead(evo_head), html.Tbody(evo_body)],
                 style={"width": "100%", "borderCollapse": "collapse"}),
                 style={"background": "#fff", "border": "1px solid #E5E7EB", "borderRadius": "10px",
                        "padding": "10px 14px", "overflowX": "auto"}),
    ])
