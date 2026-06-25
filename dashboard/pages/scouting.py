# -*- coding: utf-8 -*-
"""Página de scouting — filtros modernos, tabla y navegación a perfil."""
from __future__ import annotations
import sys, time, urllib.parse, unicodedata
from pathlib import Path
import dash, pandas as pd
from dash import Input, Output, State, callback, clientside_callback, dash_table, dcc, html, no_update
import dash_bootstrap_components as dbc

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.utils.config import settings
from dashboard.components.display_names import label
from dashboard.components.criteria_block import criteria_accordion  # noqa: E402
from src.utils.leagues import league_name as _league_name
from src.utils.lateral_position import (
    build_lateral_map, LATERAL_LABELS, ROLE_TYPE_LABELS, LATERAL_TO_ROLES,
    lateral_pos_label, role_type_label,
)
from dashboard.data_cache import get_master, get_economic

dash.register_page(__name__, path="/scouting", name="Scouting")

SEASON_ORDER_SC = {
    "2026": 7, "2025-2026": 6, "2025/2026": 6, "2025": 5,
    "2024-2025": 4, "2024": 4, "2023-2024": 3, "2023": 3,
    "2022-2023": 2, "2022": 1, "2021-2022": 1, "2021": 0,
}

S        = settings()
PROC     = Path(S["paths"]["data_processed"])
MASTER   = PROC / "master_players.parquet"
ECONOMIC = PROC / "player_economic.parquet"
ENRICHED = PROC / "player_seasons_enriched.parquet"

DISPLAY_COLS = [
    "name", "lateral_pos", "role_type", "foot", "age", "team", "league",
    "minutes", "goals", "assists", "shots_on_target",
    "tackles_won", "interceptions", "passes_completed_pct",
    "market_value_eur", "contract_until",
]

# ---------------------------------------------------------------------------
# Cache de módulo — _load() es caro, se cachea 5 minutos
# ---------------------------------------------------------------------------
_CACHE: dict = {"df": None, "t": 0.0}
_CACHE_TTL   = 300   # segundos

_FOOT_LABELS = {"right": "Der.", "left": "Izq.", "both": "Ambas",
                "Right": "Der.", "Left": "Izq.", "Both": "Ambas"}


def _norm(s: str) -> str:
    return (unicodedata.normalize("NFKD", str(s))
            .encode("ascii", "ignore").decode().lower().strip())


def _load() -> pd.DataFrame:
    """
    Carga master_players, lo enriquece con datos económicos y deduplica
    a UNA fila por jugador (la temporada más reciente).
    Resultado cacheado 5 min para que los filtros sean instantáneos.
    """
    if _CACHE["df"] is not None and time.time() - _CACHE["t"] < _CACHE_TTL:
        return _CACHE["df"]

    # Usar caché global (ya filtrado a temporada actual)
    df = get_master()
    if df is None or df.empty:
        return pd.DataFrame()

    # ---- Enriquecer con datos económicos ----
    eco = get_economic()
    if eco is not None:
        try:
            _ECO_COLS = ["market_value_eur", "contract_until", "foot", "age", "height", "position"]
            _eco_want = ["opta_id", "canonical_name"] + _ECO_COLS
            eco = eco[[c for c in _eco_want if c in eco.columns]]

            # 1. Merge por opta_id (preciso, vectorizado)
            _merge_cols = [c for c in _ECO_COLS if c in eco.columns]
            eco_by_id = (eco.dropna(subset=["opta_id"])
                         .drop_duplicates("opta_id")
                         .set_index("opta_id")[_merge_cols])
            id_col = "player_id" if "player_id" in df.columns else None
            if id_col:
                df = df.merge(
                    eco_by_id.add_suffix("_eco"),
                    left_on=id_col, right_index=True, how="left"
                )
                for col in _merge_cols:
                    eco_col = f"{col}_eco"
                    if eco_col not in df.columns:
                        continue
                    if col not in df.columns:
                        df[col] = df[eco_col]
                    else:
                        df[col] = df[col].combine_first(df[eco_col])
                df = df[[c for c in df.columns if not c.endswith("_eco")]]

            # 2. Fallback por nombre normalizado
            for _c in _ECO_COLS:
                if _c not in df.columns:
                    df[_c] = None

            eco_name = (eco.assign(_nn=eco["canonical_name"].apply(_norm))
                        .drop_duplicates("_nn")
                        .set_index("_nn"))
            df["_nn"] = df["name"].apply(_norm)
            for col in _ECO_COLS:
                if col in eco_name.columns:
                    mask = df[col].isna()
                    df.loc[mask, col] = df.loc[mask, "_nn"].map(eco_name[col])
            df = df.drop(columns=["_nn"], errors="ignore")

        except Exception:
            pass

    if "contract_until"   not in df.columns: df["contract_until"]   = None
    if "market_value_eur" not in df.columns: df["market_value_eur"] = None

    # ---- Deduplicar: quedarse con la temporada más reciente por jugador ----
    # Esto se hace UNA vez aquí, no en cada callback de filtro
    if "name" in df.columns and "season" in df.columns:
        df["_o"] = df["season"].map(SEASON_ORDER_SC).fillna(0)
        maxo = df.groupby("name")["_o"].transform("max")
        df = df[df["_o"] == maxo].drop_duplicates("name").drop(columns=["_o"])

    # ---- Enriquecer con posicion lateral y tipologia ----
    if ENRICHED.exists() and MASTER.exists():
        try:
            lat_map = build_lateral_map(ENRICHED, MASTER)
            df = df.merge(lat_map[["name", "lateral_pos", "role_type"]],
                          on="name", how="left")
            # Etiquetas legibles para las columnas de display
            df["lateral_pos"] = df["lateral_pos"].map(
                lambda x: x if pd.isna(x) else x)   # keep code (LI/LD/…)
            df["role_type"] = df["role_type"].fillna("")
        except Exception:
            if "lateral_pos" not in df.columns:
                df["lateral_pos"] = None
            if "role_type" not in df.columns:
                df["role_type"] = None
    else:
        if "lateral_pos" not in df.columns:
            df["lateral_pos"] = None
        if "role_type" not in df.columns:
            df["role_type"] = None

    # ---- Enriquecer edad desde market_values.csv (TM) ----
    try:
        mv_csv = PROC.parent / "config" / "market_values.csv"
        if mv_csv.exists():
            mv_df = pd.read_csv(mv_csv, usecols=lambda c: c in ("name", "age", "foot", "position"))
            mv_df = mv_df.dropna(subset=["name"])
            mv_df["_nn"] = mv_df["name"].apply(lambda x: unicodedata.normalize("NFKD", str(x)).encode("ascii","ignore").decode().lower().strip())
            mv_df = mv_df.drop_duplicates("_nn").set_index("_nn")
            if "age" not in df.columns:
                df["age"] = None
            df["_nn"] = df["name"].apply(lambda x: unicodedata.normalize("NFKD", str(x)).encode("ascii","ignore").decode().lower().strip())
            for col in ("age", "foot", "position"):
                if col in mv_df.columns:
                    mask = df[col].isna() if col in df.columns else pd.Series(True, index=df.index)
                    df.loc[mask, col] = df.loc[mask, "_nn"].map(mv_df[col])
            df = df.drop(columns=["_nn"], errors="ignore")
    except Exception:
        pass

    # Precalcular numéricas para filtrado rápido
    def _num(col):
        if col in df.columns:
            return pd.to_numeric(df[col], errors="coerce").fillna(0)
        return pd.Series(0, index=df.index, dtype=float)

    df["_age_n"] = _num("age")
    df["_mv_n"]  = _num("market_value_eur")
    df["_min_n"] = _num("minutes")

    _CACHE["df"] = df
    _CACHE["t"]  = time.time()
    return df


def _opts(values):
    return [{"label": v, "value": v}
            for v in sorted(str(v) for v in values if pd.notna(v) and str(v) != "nan")]


def _filter_chip(id_, label_txt, placeholder, options, multi=True, value=None):
    return html.Div([
        html.Span(label_txt, className="filter-label"),
        dcc.Dropdown(options, multi=multi, id=id_, placeholder=placeholder,
                     value=value, style={"fontSize": "12px"}),
    ])


def layout(**_params):
    df      = _load()
    leagues = ([{"label": _league_name(v), "value": v}
                for v in sorted(str(v) for v in df["league"].unique()
                                if pd.notna(v) and str(v) != "nan")]
               if not df.empty else [])
    player_opt = ([{"label": str(v), "value": str(v)}
                   for v in sorted(df["name"].dropna().unique())]
                  if not df.empty else [])
    foot_opt = ([{"label": _FOOT_LABELS.get(str(v), str(v)), "value": str(v)}
                 for v in sorted(df["foot"].dropna().unique()) if str(v) not in ("nan","")]
                if not df.empty and "foot" in df.columns else [])
    # Filtro posicion lateral
    lat_order = ["LI","LD","DC","MC","MI","MD","EI","ED","DL","PO"]
    lat_present = (set(df["lateral_pos"].dropna().unique())
                   if "lateral_pos" in df.columns else set())
    lat_opt = [{"label": LATERAL_LABELS.get(k, k), "value": k}
               for k in lat_order if k in lat_present]
    # Tipo de jugador (se actualiza via callback)
    role_opt = [{"label": v, "value": k} for k, v in ROLE_TYPE_LABELS.items()]

    return html.Div([
        # Store para navegación — clientside callback navega con window.location.href
        dcc.Store(id="scouting-nav-url", data=None),

        # ── Hero ──────────────────────────────────────────────────────────────
        html.Div([
            html.Div([
                html.Div([html.I(className="ti ti-search",
                           style={"fontSize":"26px","color":"#fff"})],
                    style={"background":"rgba(227,6,19,.20)","borderRadius":"12px",
                           "padding":"10px","marginRight":"18px","flexShrink":"0",
                           "border":"1px solid rgba(227,6,19,.30)"}),
                html.Div([
                    html.Div("BASE DE SCOUTING", style={"fontSize":"9px","fontWeight":"700",
                        "color":"rgba(255,255,255,.45)","letterSpacing":".14em","marginBottom":"3px"}),
                    html.H1("Scouting de Jugadores", style={"fontSize":"22px","fontWeight":"900",
                        "color":"#fff","margin":"0 0 2px","letterSpacing":"-.02em"}),
                    html.Div("Búsqueda avanzada · datos más recientes por jugador",
                        style={"fontSize":"10.5px","color":"rgba(255,255,255,.45)"}),
                ]),
            ], style={"display":"flex","alignItems":"center"}),
        ], style={"background":"linear-gradient(135deg,#0A0B0E 0%,#1E2028 60%,#141519 100%)",
                  "borderRadius":"18px","padding":"20px 26px","marginBottom":"18px",
                  "boxShadow":"0 8px 32px rgba(0,0,0,.28)",
                  "borderLeft":"4px solid #E30613"}),

        html.Div([
            html.Div([
                html.I(className="ti ti-adjustments-horizontal",
                       style={"fontSize":"14px","color":"var(--rayo-red)","marginRight":"7px"}),
                html.Span("FILTROS", style={"fontSize":"9px","fontWeight":"700",
                    "color":"var(--t4)","letterSpacing":".10em"}),
            ], style={"marginBottom":"12px","display":"flex","alignItems":"center"}),
            dbc.Row([
                dbc.Col(_filter_chip("f-player",   "Jugador",          "Todos",  player_opt, multi=False), md=2),
                dbc.Col(_filter_chip("f-lateral",  "Posición",         "Todas",  lat_opt,    multi=True),  md=2),
                dbc.Col(_filter_chip("f-role-type","Tipo de jugador",  "Todos",  role_opt,   multi=True),  md=2),
                dbc.Col(_filter_chip("f-league",   "Liga",             "Todas",  leagues, value=None),  md=2),
                dbc.Col(_filter_chip("f-team",     "Equipo",           "Todos",  []),                      md=2),
                dbc.Col(_filter_chip("f-foot",     "Pie dominante",    "Todos",  foot_opt, multi=False),   md=2),
                dbc.Col(html.Div([
                    html.Span("Edad máx.", className="filter-label"),
                    dcc.Slider(16, 45, 1, value=45, id="f-age",
                               marks={16:"16", 23:"23", 30:"30", 37:"37", 45:"45"},
                               tooltip={"always_visible": True, "placement": "bottom"},
                               updatemode="mouseup"),
                ]), md=2),
            ], className="g-3"),
            dbc.Row([
                dbc.Col(html.Div([
                    html.Span("Valor máx. (M€)", className="filter-label"),
                    dcc.Slider(0, 200, 10, value=200, id="f-mv",
                               marks={0:"0", 50:"50M", 100:"100M", 150:"150M", 200:"200M+"},
                               tooltip={"always_visible": True, "placement": "bottom"},
                               updatemode="mouseup"),
                ]), md=3),
                dbc.Col(html.Div([
                    html.Span("Minutos mín.", className="filter-label"),
                    dcc.Slider(0, 3500, 100, value=500, id="f-min",
                               marks={0:"0", 900:"900", 1800:"1800", 3000:"3000"},
                               tooltip={"always_visible": True, "placement": "bottom"},
                               updatemode="mouseup"),
                ]), md=3),
            ], className="g-3 mt-2"),
        ], className="filter-panel"),

        dbc.Row([
            dbc.Col(html.Div(id="scouting-count",
                             style={"fontSize":"12px","color":"var(--t3)","paddingBottom":"6px"})),
            dbc.Col(html.Div([
                html.I(className="ti ti-hand-click",
                       style={"fontSize":"13px","marginRight":"5px","color":"var(--rayo-red)"}),
                html.Span("Clic en cualquier fila para abrir el perfil",
                          style={"fontSize":"12px","color":"var(--t3)"}),
            ], style={"textAlign":"right","paddingBottom":"6px"})),
        ]),

        dash_table.DataTable(
            id="scouting-table",
            page_size=25,
            sort_action="native",
            filter_action="native",
            style_table={"overflowX": "auto"},
            style_header={
                "backgroundColor": "#0A0B0E",
                "color": "rgba(255,255,255,.82)",
                "fontWeight": "700",
                "fontSize": "10px",
                "textTransform": "uppercase",
                "letterSpacing": "0.07em",
                "padding": "11px 13px",
                "border": "none",
                "borderBottom": "2px solid #E30613",
            },
            style_cell={
                "fontSize": "12.5px",
                "padding": "10px 13px",
                "fontFamily": "Inter, system-ui, sans-serif",
                "border": "none",
                "borderBottom": "1px solid #F3F4F6",
                "color": "#374151",
                "backgroundColor": "#FFFFFF",
                "cursor": "pointer",
            },
            style_data_conditional=[
                {"if": {"row_index": "odd"}, "backgroundColor": "#FCFCFD"},
                {"if": {"state": "selected"},
                 "backgroundColor": "#FEE2E2",
                 "borderLeft": "3px solid #E30613"},
            ],
            style_filter={"fontSize": "12px", "padding": "4px 8px"},
            page_action="native",
        ),

    html.Div(id="scouting-btn-container", style={"marginTop": "14px"}),
        criteria_accordion("scouting"),
])


@callback(Output("f-team", "options"), Input("f-league", "value"))
def update_teams(leagues):
    df = _load()
    if df.empty:
        return []
    if leagues:
        df = df[df["league"].isin(leagues)]
    return _opts(df["team"].dropna().unique())


def _fuzzy_filter(df: pd.DataFrame, query: str) -> pd.DataFrame:
    """Filtro fuzzy sobre nombre: vectorizado, tolerante a tildes y búsquedas parciales."""
    if not query or not query.strip():
        return df
    q = _norm(query.strip())
    # 1. Coincidencia parcial vectorizada (pandas str.contains es ~10x más rápido que apply)
    if "_name_norm" not in df.columns:
        df = df.copy()
        df["_name_norm"] = df["name"].apply(_norm)
    mask_partial = df["_name_norm"].str.contains(q, regex=False, na=False)
    if mask_partial.any():
        # Ordenar: nombre más corto (mejor match relativo) primero
        result = df[mask_partial].copy()
        result["_rank"] = result["_name_norm"].str.len()
        return result.sort_values("_rank").drop(columns=["_rank", "_name_norm"], errors="ignore")
    # 2. Fuzzy matching con difflib (fallback para errores tipográficos)
    from difflib import SequenceMatcher
    scores = df["_name_norm"].apply(lambda n: SequenceMatcher(None, q, n).ratio())
    mask_fuzzy = scores >= 0.55
    if mask_fuzzy.any():
        return df[mask_fuzzy].copy().assign(_fscore=scores[mask_fuzzy]).sort_values(
            "_fscore", ascending=False
        ).drop(columns=["_fscore", "_name_norm"], errors="ignore")
    return df.iloc[0:0]


@callback(
    Output("f-role-type", "options"),
    Input("f-lateral", "value"),
)
def update_role_options(lat_values):
    """Actualiza las opciones de tipologia segun la posicion lateral seleccionada."""
    if not lat_values:
        return [{"label": v, "value": k} for k, v in ROLE_TYPE_LABELS.items()]
    # Mostrar solo roles compatibles con las posiciones seleccionadas
    allowed: set[str] = set()
    for lv in (lat_values if isinstance(lat_values, list) else [lat_values]):
        allowed.update(LATERAL_TO_ROLES.get(lv, []))
    return [{"label": ROLE_TYPE_LABELS[k], "value": k}
            for k in ROLE_TYPE_LABELS if k in allowed]


@callback(
    Output("scouting-table", "data"),
    Output("scouting-table", "columns"),
    Output("scouting-count", "children"),
    Input("f-player",    "value"),
    Input("f-lateral",   "value"),
    Input("f-role-type", "value"),
    Input("f-league",    "value"),
    Input("f-team",      "value"),
    Input("f-foot",      "value"),
    Input("f-age",       "value"),
    Input("f-mv",        "value"),
    Input("f-min",       "value"),
)
def filter_table(player, lat_pos, role_types, leagues, teams, foot, age_max, mv_max_m, min_min):
    df = _load()
    if df.empty:
        return [], [], "Sin datos — ejecuta el ETL primero"

    # Filtro por jugador concreto (tiene prioridad; omite filtros numéricos)
    if player:
        df = df[df["name"] == player]
    else:
        if lat_pos and "lateral_pos" in df.columns:
            lats = lat_pos if isinstance(lat_pos, list) else [lat_pos]
            df = df[df["lateral_pos"].isin(lats)]
        if role_types and "role_type" in df.columns:
            rts = role_types if isinstance(role_types, list) else [role_types]
            df = df[df["role_type"].isin(rts)]
        if leagues: df = df[df["league"].isin(leagues)]
        if teams:   df = df[df["team"].isin(teams)]
        if foot and "foot" in df.columns:
            df = df[df["foot"].astype(str).str.lower() == str(foot).lower()]

        if age_max  is not None and age_max < 45:
            df = df[df["_age_n"] <= age_max]
        # MV: solo filtrar si el slider NO está en el máximo (250)
        # Jugadores sin MV conocido (_mv_n == 0) siempre pasan
        if mv_max_m is not None and mv_max_m < 200:
            df = df[(df["_mv_n"] == 0) | (df["_mv_n"] <= mv_max_m * 1_000_000)]
        if min_min  is not None: df = df[df["_min_n"] >= min_min]

    cols_show = [c for c in DISPLAY_COLS if c in df.columns]
    extra_cols = [c for c in ("player_id", "player_id_src")
                  if c in df.columns and c not in cols_show]
    df_show = df[cols_show + extra_cols].copy().head(1000)

    # Traducir role_type (clave interna → etiqueta legible)
    if "role_type" in df_show.columns:
        df_show["role_type"] = df_show["role_type"].apply(
            lambda x: ROLE_TYPE_LABELS.get(x, x) if x else x
        )
    # Traducir pie dominante (right→Der., left→Izq.)
    if "foot" in df_show.columns:
        df_show["foot"] = df_show["foot"].apply(
            lambda x: _FOOT_LABELS.get(str(x), str(x)) if pd.notna(x) and str(x) not in ("nan","None","") else ""
        )

    if "market_value_eur" in df_show.columns:
        df_show["market_value_eur"] = df_show["market_value_eur"].apply(
            lambda v: f"{v/1e6:.1f}M" if pd.notna(v) and v > 0 else ""
        )
    if "league" in df_show.columns:
        df_show["league"] = df_show["league"].apply(lambda v: _league_name(str(v)) if pd.notna(v) else v)
    if "contract_until" in df_show.columns:
        def _fmt_contract(s):
            if not s or str(s) in ("nan", "None", ""):
                return ""
            return s[:10]
        df_show["contract_until"] = df_show["contract_until"].apply(_fmt_contract)

    for c in df_show.select_dtypes("float").columns:
        if c not in ("_age_n", "_mv_n", "_min_n"):
            df_show[c] = df_show[c].round(2)

    columns = [{"name": label(c), "id": c, "type": "text"} for c in cols_show]
    n_econ = (df["_mv_n"] > 0).sum() if "_mv_n" in df.columns else 0
    count_msg = f"{len(df):,} jugadores encontrados · {n_econ:,} con datos económicos"
    return df_show.to_dict("records"), columns, count_msg


@callback(
    Output("scouting-nav-url", "data"),
    Input("scouting-table", "active_cell"),
    State("scouting-table", "derived_viewport_data"),
    prevent_initial_call=True,
)
def go_to_player(active_cell, view_data):
    if not active_cell or not view_data:
        return no_update
    idx = active_cell.get("row")
    if idx is None or idx >= len(view_data):
        return no_update
    row = view_data[idx]
    pid    = urllib.parse.quote(str(row.get("player_id") or row.get("player_id_src") or row.get("name", "")))
    nombre = urllib.parse.quote(str(row.get("name", "")))
    equipo = urllib.parse.quote(str(row.get("team", "")))
    return f"/jugador?id={pid}&name={nombre}&team={equipo}"


clientside_callback(
    """
    function(url) {
        if (url) {        if (url) {
            window.location.href = url;
        }
        return null;
    }
    """,
    Output("scouting-nav-url", "data", allow_duplicate=True),
    Input("scouting-nav-url", "data"),
    prevent_initial_call=True,
)
