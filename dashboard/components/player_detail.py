# -*- coding: utf-8 -*-
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
    career_aggregate, most_recent_team, ROLE_DEFINITIONS, ROLE_LABELS, METRIC_LABELS,
)
from src.fit.player_fit import evaluate_player_fit
from src.utils.market import get_value
from src.utils.leagues import league_name as _league_name
from src.utils.lateral_position import (
    build_lateral_map, lateral_pos_label, role_type_label, LATERAL_LABELS,
)

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


@lru_cache(maxsize=1)
def _player_lookup() -> pd.DataFrame:
    """Tabla precalculada: un registro por jugador con su equipo más reciente.

    Para traspasos de invierno (2 equipos en la misma temporada) se prefiere
    el equipo NUEVO (distinto al de la temporada anterior).
    Cacheada en memoria — se calcula una sola vez al arrancar.
    """
    df = enriched()
    if df.empty:
        return pd.DataFrame(columns=["name", "team", "_name_n"])

    season_order = {"2025-2026": 6, "2025": 5, "2024-2025": 4,
                    "2023-2024": 3, "2022-2023": 2, "2021-2022": 1}
    df2 = df[["name", "team", "season"]].drop_duplicates()
    df2 = df2.copy()
    df2["_so"] = df2["season"].map(season_order).fillna(0)

    # Para cada jugador: equipo de su temporada más reciente
    # Si tiene 2 equipos en esa temporada, tomar el que difiere del anterior
    df2 = df2.sort_values(["name", "_so", "team"], ascending=[True, False, True])

    # Equipo más reciente simple
    latest_simple = df2.drop_duplicates(subset=["name"], keep="first")[["name", "team", "_so"]]

    # Detectar jugadores con 2 equipos en la temporada top → traspaso
    top_so_per = df2.groupby("name")["_so"].max().reset_index().rename(columns={"_so": "_top"})
    df2 = df2.merge(top_so_per, on="name")
    in_top = df2[df2["_so"] == df2["_top"]]
    multi = in_top.groupby("name").filter(lambda g: len(g) > 1)

    if not multi.empty:
        # Para los transferidos: equipo previo (primera temporada anterior)
        prev = (df2[df2["_so"] < df2["_top"]]
                .drop_duplicates(subset=["name"], keep="first")[["name", "team"]]
                .rename(columns={"team": "_prev"}))
        multi2 = multi.merge(prev, on="name", how="left")
        new_clubs = multi2[multi2["team"] != multi2["_prev"]].drop_duplicates(subset=["name"], keep="first")
        transferred_names = set(new_clubs["name"])
        latest_simple = latest_simple[~latest_simple["name"].isin(transferred_names)]
        latest_simple = pd.concat([latest_simple, new_clubs[["name", "team"]]], ignore_index=True)

    latest_simple["_name_n"] = latest_simple["name"].map(_n)
    return latest_simple[["name", "team", "_name_n"]]


def player_options(search: str = "") -> list[dict]:
    """Búsqueda server-side sobre la tabla precalculada. Devuelve hasta 50 resultados."""
    if not search or len(search) < 2:
        return []
    lookup = _player_lookup()
    if lookup.empty:
        return []
    q = _n(search)
    matches = lookup[lookup["_name_n"].str.contains(q, na=False)].sort_values("name").head(50)
    return [{"label": f"{r.name} · {r.team}", "value": f"{r.name}|||{r.team}"}
            for r in matches.itertuples()]


def _find_rows(name, team=None):
    df = enriched()
    if df.empty:
        return df

    # 1. Exact normalized match
    cand = df[df["name"].map(_n) == _n(name)]

    # 2. First-initial + last-name match (handles OPTA abbreviations like "P. Ciss" for "Pathé Ciss")
    if cand.empty:
        parts = _n(name).split()
        if len(parts) >= 2:
            ini = parts[0][0]          # first initial
            last = parts[-1]           # last name
            import re as _re
            pat = _re.compile(
                rf'^{_re.escape(ini)}[\.\s]\s*{_re.escape(last)}$'
            )
            cand = df[df["name"].map(lambda x: bool(pat.match(_n(x))))]

    # 3. Loose last-word partial fallback
    if cand.empty:
        cand = df[df["name"].map(_n).str.contains(_n(name).split()[-1], na=False)]

    # 4. Team filter (applied to whichever step matched)
    if team:
        t = cand[cand["team"].map(_n).str.contains(_n(team).split()[0], na=False)]
        if not t.empty:
            cand = t
    return cand


def _bar(label, pct, value=None):
    pct = 0 if pct is None or pd.isna(pct) else max(0, min(100, pct))
    color = "#10B981" if pct >= 66 else ("#F59E0B" if pct >= 40 else "#DC2626")
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


def _style_transparency(prof: dict, pct_for_fn):
    """Panel colapsable que explica el cálculo del estilo del jugador."""
    if not prof or not prof.get("primary_role"):
        return html.Div()

    primary = prof["primary_role"]
    role_scores = prof.get("role_scores", {})
    role_def = ROLE_DEFINITIONS.get(primary, {})
    weights = role_def.get("weights", {})
    group = role_def.get("group", "")

    # Roles del mismo grupo posicional, ordenados por score desc
    group_roles = sorted(
        [(r, s) for r, s in role_scores.items()
         if ROLE_DEFINITIONS.get(r, {}).get("group") == group],
        key=lambda x: x[1], reverse=True,
    )
    role_rows = []
    for r, s in group_roles:
        is_p = (r == primary)
        role_rows.append(html.Tr([
            html.Td(
                f"{'★ ' if is_p else ''}{ROLE_LABELS.get(r, r)}",
                style={"fontSize": "10px", "padding": "2px 5px",
                       "fontWeight": "700" if is_p else "normal",
                       "color": "#B8960C" if is_p else "#374151"},
            ),
            html.Td(
                f"{s:.0f}",
                style={"fontSize": "10px", "padding": "2px 5px", "textAlign": "right",
                       "fontWeight": "700" if is_p else "normal",
                       "color": "#B8960C" if is_p else "#374151"},
            ),
        ]))

    # Breakdown de métricas del rol principal
    metric_rows = []
    w_used, score_sum = 0.0, 0.0
    for metric, w in sorted(weights.items(), key=lambda x: x[1], reverse=True):
        label = METRIC_LABELS.get(metric, metric)
        pct_val = pct_for_fn(metric)
        if pct_val is not None and not pd.isna(pct_val):
            pf = float(pct_val)
            w_used += w
            score_sum += w * pf
            color = "#15803D" if pf >= 70 else ("#B45309" if pf <= 30 else "#374151")
            metric_rows.append(html.Tr([
                html.Td(label, style={"fontSize": "10px", "padding": "2px 5px", "color": "#374151"}),
                html.Td(f"{w:.0%}", style={"fontSize": "10px", "padding": "2px 5px",
                         "textAlign": "center", "color": "#6B7280"}),
                html.Td(f"{pf:.0f}", style={"fontSize": "10px", "padding": "2px 5px",
                         "textAlign": "right", "fontWeight": "700", "color": color}),
            ]))
        else:
            metric_rows.append(html.Tr([
                html.Td(label, style={"fontSize": "10px", "padding": "2px 5px", "color": "#9CA3AF"}),
                html.Td(f"{w:.0%}", style={"fontSize": "10px", "padding": "2px 5px",
                         "textAlign": "center", "color": "#9CA3AF"}),
                html.Td("—", style={"fontSize": "10px", "padding": "2px 5px",
                         "textAlign": "right", "color": "#9CA3AF"}),
            ]))

    score_display = f"{score_sum / w_used:.1f}" if w_used > 0 else "n/d"
    panel = html.Div([
        html.P(f"Scores del grupo {group}:", style={
            "fontSize": "10px", "fontWeight": "700", "color": "#9CA3AF", "margin": "0 0 3px"}),
        html.Table([html.Tbody(role_rows)],
            style={"width": "100%", "borderCollapse": "collapse", "marginBottom": "8px"}),
        html.P(
            f"Métricas del rol ★ {ROLE_LABELS.get(primary, primary)} "
            f"(peso · percentil vs posición):",
            style={"fontSize": "10px", "fontWeight": "700", "color": "#9CA3AF", "margin": "0 0 3px"}),
        html.Table([
            html.Thead(html.Tr([
                html.Th("Métrica", style={"fontSize": "9px", "color": "#9CA3AF",
                         "padding": "2px 5px", "textAlign": "left"}),
                html.Th("Peso", style={"fontSize": "9px", "color": "#9CA3AF",
                         "padding": "2px 5px", "textAlign": "center"}),
                html.Th("Pct", style={"fontSize": "9px", "color": "#9CA3AF",
                         "padding": "2px 5px", "textAlign": "right"}),
            ])),
            html.Tbody(metric_rows),
        ], style={"width": "100%", "borderCollapse": "collapse"}),
        html.P(
            f"Score = Σ(peso × pct) / Σ(pesos) ≈ {score_display} / 100",
            style={"fontSize": "9px", "color": "#9CA3AF",
                   "fontStyle": "italic", "margin": "5px 0 0"}),
    ], style={"background": "#F9FAFB", "border": "1px solid #E5E7EB",
               "borderRadius": "6px", "padding": "8px 10px", "marginTop": "4px"})

    style_label = prof.get("style_label", "n/d")
    return html.Details([
        html.Summary(
            f"Estilo «{style_label}» — ¿cómo se calcula? ▸",
            style={"fontSize": "10px", "color": "#1D4ED8", "cursor": "pointer",
                   "marginBottom": "4px", "userSelect": "none", "fontWeight": "600"},
        ),
        html.P(
            f"El estilo se asigna automáticamente según el rol principal detectado "
            f"(★ {ROLE_LABELS.get(primary, primary)}). "
            f"El rol se obtiene comparando las métricas del jugador con los pesos de cada rol.",
            style={"fontSize": "9px", "color": "#6B7280", "margin": "0 0 6px",
                   "fontStyle": "italic"},
        ),
        panel,
    ], open=True, style={"marginTop": "4px", "marginBottom": "4px"})


# ── Rendimiento ──────────────────────────────────────────────────────────────
# La lógica está centralizada en src/utils/rendimiento.py
# Aquí solo se renderiza el resultado.

def _col(v):
    if v is None: return "#6B7280"
    if v >= 75:   return "#166534"
    if v >= 55:   return "#1D4ED8"
    if v >= 35:   return "#B45309"
    return "#991B1B"

def _bar_col(v):
    if v is None: return "#E5E7EB"
    if v >= 75:   return "#16A34A"
    if v >= 55:   return "#3B82F6"
    if v >= 35:   return "#F59E0B"
    return "#EF4444"

def _grade(v):
    if v is None:  return "—"
    if v >= 85:    return "Elite"
    if v >= 70:    return "Alto"
    if v >= 55:    return "Medio-alto"
    if v >= 40:    return "Medio"
    if v >= 25:    return "Bajo"
    return "Muy bajo"


def _rendimiento_card(rd: dict) -> html.Div:
    """Tarjeta de Rendimiento a partir del dict devuelto por compute_rendimiento()."""
    overall    = rd.get("score")
    dim_scores = rd.get("dims", [])
    subpos_lbl = rd.get("subpos_label", "—")
    pool_size  = rd.get("pool_size", 0)
    ld         = rd.get("league_diff", 1.0)

    overall_color = _col(overall)
    grade_lbl     = _grade(overall)

    bars = []
    for d in dim_scores:
        score = d["score"]
        bars.append(html.Div([
            html.Div(
                html.Span(d["label"], style={"fontSize": "11px", "color": "#374151"}),
                style={"width": "140px", "flexShrink": "0"},
            ),
            html.Div(style={"flex": "1", "background": "#F3F4F6",
                            "borderRadius": "99px", "height": "8px", "overflow": "hidden"},
                     children=html.Div(style={
                         "height": "100%", "width": f"{score:.0f}%",
                         "background": _bar_col(score), "borderRadius": "99px",
                     })),
            html.Span(f"{score:.0f}", style={
                "fontSize": "11px", "fontWeight": "700",
                "color": _col(score), "width": "30px", "textAlign": "right",
                "marginLeft": "6px",
            }),
        ], style={"display": "flex", "alignItems": "center",
                  "gap": "8px", "marginBottom": "7px"}))

    ld_note = f" · dif. liga ×{ld:.2f}" if ld != 1.0 else ""
    return html.Div([
        html.Div([
            html.Div([
                html.Span("Rendimiento", style={
                    "fontSize": "11px", "fontWeight": "700", "color": "#9CA3AF",
                    "textTransform": "uppercase", "letterSpacing": ".06em",
                }),
                html.Span(f" · {subpos_lbl}", style={
                    "fontSize": "10px", "color": "#9CA3AF",
                }),
            ]),
            html.Div([
                html.Span(f"{overall}" if overall is not None else "—",
                          style={"fontSize": "26px", "fontWeight": "900",
                                 "color": overall_color, "lineHeight": "1"}),
                html.Span("/100", style={"fontSize": "12px", "color": "#9CA3AF",
                                        "marginLeft": "2px"}),
                html.Span(grade_lbl, style={
                    "fontSize": "10px", "fontWeight": "600",
                    "color": overall_color,
                    "background": "#F3F4F6", "borderRadius": "99px",
                    "padding": "2px 8px", "marginLeft": "8px",
                }),
            ], style={"display": "flex", "alignItems": "baseline"}),
        ], style={"display": "flex", "justifyContent": "space-between",
                  "alignItems": "center", "marginBottom": "12px"}),
        html.Div(bars),
        html.P(
            f"Percentiles vs {subpos_lbl.lower()}s con ≥450 min{ld_note}  ·  pool: {pool_size} jugadores",
            style={"fontSize": "9px", "color": "#9CA3AF",
                   "fontStyle": "italic", "margin": "4px 0 0"},
        ),
    ], style={
        "background": "#fff", "border": "1px solid #E5E7EB",
        "borderRadius": "10px", "padding": "14px 18px", "marginBottom": "16px",
    })


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
            "fillcolor": "rgba(255,214,0,0.25)", "line": {"color": "#FFD600"},
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
                 coach_style="Bloque medio / Equilibrado", with_photo=True,
                 extra_header_right=None):
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
            "objectFit": "cover", "borderRadius": "10px", "border": "3px solid #FFD600"})
    else:
        foto_elem = html.Img(src=SILHOUETTE, alt="sin foto",
            style={"width": "120px", "height": "150px", "objectFit": "cover",
                   "borderRadius": "10px", "border": "3px solid #E5E7EB", "background": "#F1F3F5"})

    role_lbl = prof["primary_role_label"] if prof else "n/d"
    fit = evaluate_player_fit(prof, _needs(), coach_style) if prof and prof.get("primary_role") else None

    # ── Posición lateral + tipologia: inferida + override manual ─────────────
    _lat_code      = None
    _role_type_key = None
    try:
        _lat_map   = build_lateral_map(
            PROC / "player_seasons_enriched.parquet",
            PROC / "master_players.parquet",
        )
        _player_row = _lat_map[_lat_map["name"] == str(latest["name"])]
        if not _player_row.empty:
            _lat_code      = _player_row.iloc[0].get("lateral_pos")
            _role_type_key = _player_row.iloc[0].get("role_type")
    except Exception:
        pass
    # Override manual desde player_overrides.json (tiene prioridad)
    try:
        _ov_path = PROC / "player_overrides.json"
        if _ov_path.exists():
            import unicodedata as _uda
            _all_ovs = json.load(open(_ov_path, encoding="utf-8"))
            _key_norm = (_uda.normalize("NFKD", str(latest["name"]))
                         .encode("ascii", "ignore").decode().lower().strip())
            _ov = _all_ovs.get(_key_norm, {})
            if _ov.get("lateral_pos"):
                _lat_code = _ov["lateral_pos"]
            if _ov.get("role_type"):
                _role_type_key = _ov["role_type"]
    except Exception:
        pass

    _lat_label       = LATERAL_LABELS.get(_lat_code, "") if _lat_code else ""
    _role_type_label = role_type_label(_role_type_key)
    _FOOT_TRANS = {"right": "Der.", "left": "Izq.", "both": "Ambos",
                   "der.": "Der.", "izq.": "Izq.", "der": "Der.", "izq": "Izq.",
                   "derecho": "Der.", "zurdo": "Izq.", "ambos": "Ambos",
                   "r": "Der.", "l": "Izq."}
    _foot_raw  = (mvinfo.get("foot") or "").strip().lower()
    _foot_val  = _FOOT_TRANS.get(_foot_raw, "")  # empty if unknown → badge hidden

    header = html.Div([
        foto_elem,
        html.Div([
            html.H2(str(latest["name"]), style={"margin": "0 0 4px", "fontSize": "22px"}),
            html.Div([
                html.Span(real_team, style={"fontSize": "13px", "color": "#374151", "marginRight": "10px"}),
                html.Span(_league_name(real_league), style={"fontSize": "12px", "color": "#6B7280"}),
            ], style={"marginBottom": "6px"}),
            # Badges de posición y rol
            html.Div([
                html.Span(_role_type_label if _role_type_key else role_lbl,
                    style={"fontSize": "12px", "fontWeight": "700", "color": "#0D0D0D",
                    "background": "#FFD600", "borderRadius": "99px", "padding": "3px 12px",
                    "marginRight": "6px"}),
                *([ html.Span(_lat_label, style={
                        "fontSize": "12px", "fontWeight": "700", "color": "#fff",
                        "background": "#111827", "borderRadius": "99px",
                        "padding": "3px 10px", "marginRight": "6px",
                    }) ] if _lat_label else []),
                *([ html.Span(
                        f"Pie: {_foot_val}", style={
                            "fontSize": "11px", "color": "#1D4ED8",
                            "background": "#EFF6FF", "borderRadius": "99px",
                            "padding": "2px 9px", "marginRight": "6px",
                        }) ] if _foot_val else []),
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
                    (f"Altura: {mvinfo['height']} m" if mvinfo.get('height') else None),
                    (f"Pos. TM: {mvinfo['position']}" if mvinfo.get('position') else None),
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
        *([ extra_header_right ] if extra_header_right is not None else []),
        html.A("← Volver al Scouting", href="/scouting", style={"fontSize": "12px",
               "color": "#B8960C", "textDecoration": "none", "alignSelf": "flex-start"}),
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

    # Rendimiento: módulo compartido
    try:
        from src.utils.rendimiento import compute_rendimiento, get_subposition
        import json as _json
        from pathlib import Path as _Path
        from src.utils.config import settings as _settings
        import pandas as _pd_rend
        _proc = _Path(_settings()["paths"]["data_processed"])
        _ov_path = _proc / "player_overrides.json"
        _ov = _json.load(open(_ov_path, encoding="utf-8")) if _ov_path.exists() else {}
        _cfg = _proc.parents[1] / "config" / "market_values.csv"
        _mv = _pd_rend.read_csv(_cfg) if _cfg.exists() else None
        _subpos = get_subposition(latest["name"], overrides=_ov, mv_df=_mv,
                                   position_group=latest.get("position_group"),
                                   lateral_pos=_lat_code, role_type=_role_type_key)
        _rd = compute_rendimiento(latest, enriched(), subpos=_subpos)
    except Exception as _exc:
        _rd = {"score": None, "dims": [], "subpos_label": "—",
               "pool_size": 0, "league_diff": 1.0, "error": str(_exc)}
    rend_card = _rendimiento_card(_rd)

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
        rend_card,
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
                _style_transparency(prof, _pct_for) if prof else html.Div(),
                html.Div([
                    html.Span(f"Confianza: {prof['confidence'] if prof else 'n/d'}",
                             style={"fontSize": "11px", "color": "#6B7280", "marginRight": "12px"}),
                    html.Span(f"Potencial: {prof['potential'] if prof else 'n/d'}",
                             style={"fontSize": "11px", "color": "#6B7280"}),
                ], style={"marginBottom": "8px"}),
                html.P("Fortalezas: " + (", ".join(prof["strengths"]) if prof and prof["strengths"] else "—"),
                       style={"fontSize": "12px", "color": "#166534", "margin": "0 0 4px"}),
                html.P("Debilidades: " + (", ".join(prof["weaknesses"]) if prof and prof["weaknesses"] else "—"),
                       style={"fontSize": "12px", "color": "#991B1B", "margin": "0"}),
            ], md=7),
        ], className="mb-3"),
        html.P("Percentiles por métrica · histórico completo (vs su posición)", style={"fontSize": "11px",
               "fontWeight": "700", "color": "#9CA3AF", "textTransform": "uppercase", "marginBottom": "8px"}),
        dbc.Row(metric_cols),
        html.P("Evolucion por temporada", style={"fontSize": "11px", "fontWeight": "700",
               "color": "#9CA3AF", "textTransform": "uppercase", "margin": "10px 0 8px"}),
        html.Div(html.Table([html.Thead(evo_head), html.Tbody(evo_body)],
                 style={"width": "100%", "borderCollapse": "collapse"}),
                 style={"background": "#fff", "border": "1px solid #E5E7EB", "borderRadius": "10px",
                        "padding": "10px 14px", "overflowX": "auto"}),
    ])
