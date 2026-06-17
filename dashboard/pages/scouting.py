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

DISPLAY_COLS = [
    "name", "position_primary", "age", "team", "league",
    "minutes", "goals", "assists", "shots_on_target",
    "tackles_won", "interceptions", "passes_completed_pct",
    "market_value_eur", "contract_until",
]

# ---------------------------------------------------------------------------
# Cache de módulo — _load() es caro, se cachea 5 minutos
# ---------------------------------------------------------------------------
_CACHE: dict = {"df": None, "t": 0.0}
_CACHE_TTL   = 300   # segundos


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

    if not MASTER.exists():
        return pd.DataFrame()

    df = pd.read_parquet(MASTER)

    # ---- Enriquecer con datos económicos ----
    if ECONOMIC.exists():
        try:
            eco = pd.read_parquet(ECONOMIC, columns=[
                "opta_id", "canonical_name",
                "market_value_eur", "contract_until",
            ])

            # 1. Merge por opta_id (preciso, vectorizado)
            eco_by_id = (eco.dropna(subset=["opta_id"])
                         .drop_duplicates("opta_id")
                         .set_index("opta_id")[["market_value_eur", "contract_until"]])
            id_col = "player_id" if "player_id" in df.columns else None
            if id_col:
                df = df.merge(
                    eco_by_id.add_suffix("_eco"),
                    left_on=id_col, right_index=True, how="left"
                )
                for col in ("market_value_eur", "contract_until"):
                    eco_col = f"{col}_eco"
                    if col not in df.columns:
                        df[col] = df[eco_col]
                    else:
                        df[col] = df[col].combine_first(df[eco_col])
                df = df[[c for c in df.columns if not c.endswith("_eco")]]

            # 2. Fallback por nombre normalizado (vectorizado, sin bucle)
            if "contract_until" not in df.columns:
                df["contract_until"] = None
            if "market_value_eur" not in df.columns:
                df["market_value_eur"] = None

            eco_name = (eco.assign(_nn=eco["canonical_name"].apply(_norm))
                        .drop_duplicates("_nn")
                        .set_index("_nn"))
            name_to_mv = eco_name["market_value_eur"].to_dict()
            name_to_cu = eco_name["contract_until"].to_dict()

            df["_nn"] = df["name"].apply(_norm)
            mask_mv = df["market_value_eur"].isna()
            mask_cu = df["contract_until"].isna()
            df.loc[mask_mv, "market_value_eur"] = df.loc[mask_mv, "_nn"].map(name_to_mv)
            df.loc[mask_cu, "contract_until"]   = df.loc[mask_cu, "_nn"].map(name_to_cu)
            df = df.drop(columns=["_nn"], errors="ignore")

        except Exception:
            pass
    else:
        if "contract_until"   not in df.columns: df["contract_until"]   = None
        if "market_value_eur" not in df.columns: df["market_value_eur"] = None

    # ---- Deduplicar: quedarse con la temporada más reciente por jugador ----
    # Esto se hace UNA vez aquí, no en cada callback de filtro
    if "name" in df.columns and "season" in df.columns:
        df["_o"] = df["season"].map(SEASON_ORDER_SC).fillna(0)
        maxo = df.groupby("name")["_o"].transform("max")
        df = df[df["_o"] == maxo].drop_duplicates("name").drop(columns=["_o"])

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


def _filter_chip(id_, label_txt, placeholder, options, multi=True):
    return html.Div([
        html.Span(label_txt, className="filter-label"),
        dcc.Dropdown(options, multi=multi, id=id_, placeholder=placeholder,
                     style={"fontSize": "12px"}),
    ])


def layout(**_params):
    df      = _load()
    leagues = ([{"label": _league_name(v), "value": v}
                for v in sorted(str(v) for v in df["league"].unique()
                                if pd.notna(v) and str(v) != "nan")]
               if not df.empty else [])
    pos_opt = _opts(df["position_primary"].unique())  if not df.empty else []

    return html.Div([
        # Store para navegación — clientside callback navega con window.location.href
        dcc.Store(id="scouting-nav-url", data=None),

        html.Div([
            html.H1("Scouting", className="page-title"),
            html.P("Búsqueda avanzada de jugadores · datos más recientes por jugador",
                   className="page-subtitle"),
        ], className="page-header"),

        # Buscador con autocomplete
        html.Div([
            html.I(className="ti ti-search",
                   style={"fontSize": "16px", "color": "#E30613",
                          "marginRight": "10px", "alignSelf": "center", "flexShrink": "0"}),
            dcc.Dropdown(
                id="f-search",
                placeholder="Escribe 2+ letras para buscar (Ej: Mba → Mbappé, Mbangula...)",
                options=[],
                value=None,
                multi=False,
                clearable=True,
                optionHeight=44,
                style={"flex": "1", "fontSize": "13px", "border": "none",
                       "fontFamily": "Inter, system-ui, sans-serif"},
            ),
            html.Span("↵ selecciona", style={"fontSize": "10px", "color": "#9CA3AF",
                                              "marginLeft": "8px", "flexShrink": "0", "whiteSpace": "nowrap"}),
        ], style={"display": "flex", "alignItems": "center", "marginBottom": "12px",
                  "background": "#FFF1F2", "border": "1px solid #FECACA",
                  "borderRadius": "10px", "padding": "8px 14px"}),

        html.Div([
            html.P("Filtros", className="card-modern-title"),
            dbc.Row([
                dbc.Col(_filter_chip("f-pos",    "Posición", "Todas",  pos_opt), md=2),
                dbc.Col(_filter_chip("f-league", "Liga",     "Todas",  leagues), md=2),
                dbc.Col(_filter_chip("f-team",   "Equipo",   "Todos",  []),      md=2),
                dbc.Col(html.Div([
                    html.Span("Edad máx.", className="filter-label"),
                    dcc.Slider(16, 40, 1, value=30, id="f-age",
                               marks={16:"16", 23:"23", 30:"30", 37:"37", 40:"40"},
                               tooltip={"always_visible": True, "placement": "bottom"},
                               updatemode="mouseup"),
                ]), md=2),
                dbc.Col(html.Div([
                    html.Span("Valor máx. (M€)", className="filter-label"),
                    dcc.Slider(0, 100, 5, value=100, id="f-mv",
                               marks={0:"0", 25:"25M", 50:"50M", 100:"100M"},
                               tooltip={"always_visible": True, "placement": "bottom"},
                               updatemode="mouseup"),
                ]), md=2),
                dbc.Col(html.Div([
                    html.Span("Minutos mín.", className="filter-label"),
                    dcc.Slider(0, 3500, 100, value=500, id="f-min",
                               marks={0:"0", 900:"900", 1800:"1800", 3000:"3000"},
                               tooltip={"always_visible": True, "placement": "bottom"},
                               updatemode="mouseup"),
                ]), md=2),
            ], className="g-3"),
        ], className="filter-panel"),

        dbc.Row([
            dbc.Col(html.Div(id="scouting-count",
                             style={"fontSize": "12px", "color": "#6B7280", "paddingBottom": "6px"})),
            dbc.Col(html.Div([
                html.I(className="ti ti-hand-click",
                       style={"fontSize": "13px", "marginRight": "5px"}),
                html.Span("Haz clic en cualquier fila para abrir el perfil del jugador",
                          style={"fontSize": "12px", "color": "#6B7280"}),
            ], style={"textAlign": "right", "paddingBottom": "6px"})),
        ]),

        dash_table.DataTable(
            id="scouting-table",
            page_size=25,
            sort_action="native",
            filter_action="native",
            style_table={"overflowX": "auto"},
            style_header={
                "backgroundColor": "#1A1A2E",
                "color": "white",
                "fontWeight": "600",
                "fontSize": "11px",
                "textTransform": "uppercase",
                "letterSpacing": "0.05em",
                "padding": "10px 12px",
                "border": "none",
            },
            style_cell={
                "fontSize": "13px",
                "padding": "9px 12px",
                "fontFamily": "Inter, system-ui, sans-serif",
                "border": "none",
                "borderBottom": "1px solid #E5E7EB",
            "color": "#1A1A2E",
            "backgroundColor": "#FFFFFF",
            "cursor": "pointer",
        },
        style_data_conditional=[
            {"if": {"row_index": "odd"},
             "backgroundColor": "#FAFAFA"},
            {"if": {"state": "selected"},
             "backgroundColor": "#FDE8E8",
             "borderLeft": "3px solid #E30613"},
        ],
        style_filter={"fontSize": "12px", "padding": "4px 8px"},
        page_action="native",
    ),

    html.Div(id="scouting-btn-container", style={"marginTop": "14px"}),
        criteria_accordion("scouting"),
])


@callback(
    Output("f-search", "options"),
    Input("f-search", "search_value"),
)
def _autocomplete_search(sv):
    if not sv or len(sv.strip()) < 2:
        return []
    df = _load()
    if df.empty:
        return []
    matches = _fuzzy_filter(df, sv).head(20)
    opts = []
    for _, row in matches.iterrows():
        name  = row.get("name", "")
        team  = row.get("team", "")
        league = _league_name(str(row.get("league", ""))) if row.get("league") else ""
        pos   = row.get("position_primary", "")
        parts = [x for x in [team, league] if x]
        sub   = " · ".join(parts)
        label = f"{name}  ({pos})" + (f"  —  {sub}" if sub else "")
        opts.append({"label": label, "value": name})
    return opts


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
    Output("scouting-table", "data"),
    Output("scouting-table", "columns"),
    Output("scouting-count", "children"),
    Input("f-pos",    "value"),
    Input("f-league", "value"),
    Input("f-team",   "value"),
    Input("f-age",    "value"),
    Input("f-mv",     "value"),
    Input("f-min",    "value"),
    Input("f-search", "value"),
    Input("f-search", "search_value"),
)
def filter_table(pos, leagues, teams, age_max, mv_max_m, min_min, search, search_text):
    # search = valor seleccionado del dropdown; search_text = lo que se está escribiendo
    search = search or search_text
    df = _load()
    if df.empty:
        return [], [], "Sin datos — ejecuta el ETL primero"

    # Buscador fuzzy (tiene prioridad sobre otros filtros de texto)
    if search and search.strip():
        df = _fuzzy_filter(df, search)
    else:
        if pos:     df = df[df["position_primary"].isin(pos)]
        if leagues: df = df[df["league"].isin(leagues)]
        if teams:   df = df[df["team"].isin(teams)]

    if age_max  is not None: df = df[df["_age_n"] <= age_max]
    if mv_max_m is not None: df = df[df["_mv_n"]  <= mv_max_m * 1_000_000]
    if min_min  is not None: df = df[df["_min_n"] >= min_min]

    cols_show = [c for c in DISPLAY_COLS if c in df.columns]
    extra_cols = [c for c in ("player_id", "player_id_src")
                  if c in df.columns and c not in cols_show]
    df_show = df[cols_show + extra_cols].copy().head(500)

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
        if (url) {
            window.location.href = url;
        }
        return null;
    }
    """,
    Output("scouting-nav-url", "data", allow_duplicate=True),
    Input("scouting-nav-url", "data"),
    prevent_initial_call=True,
)
