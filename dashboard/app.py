"""App Dash - Rayo Vallecano Scouting Tool 2026/27."""
from __future__ import annotations
import json as _json
import tempfile
from datetime import date
from pathlib import Path
import dash
from dash import Dash, html, dcc, Input, Output, clientside_callback
import dash_bootstrap_components as dbc

try:
    import diskcache
    from dash import DiskcacheManager
    _CACHE_DIR = Path(tempfile.gettempdir()) / "rayo_dash_cache"
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    background_callback_manager = DiskcacheManager(diskcache.Cache(str(_CACHE_DIR)))
except Exception as _e:
    background_callback_manager = None
    print(f"Background callbacks desactivados: {_e}")

LOGO_URL = "https://upload.wikimedia.org/wikipedia/en/d/d8/Rayo_Vallecano_logo.svg"

NAV_GROUPS = [
    ("ANALISIS", [
        ("ti-layout-dashboard", "Inicio",       "/"),
        ("ti-users",            "Plantilla",    "/plantilla"),
        ("ti-search",           "Scouting",     "/scouting"),
        ("ti-git-compare",      "Comparador",   "/comparador"),
    ]),
    ("CUERPO TECNICO", [
        ("ti-chalkboard",       "Entrenadores", "/entrenadores"),
    ]),
    ("ESTRATEGIA", [
        ("ti-clipboard-check",  "Decisiones",   "/decisiones"),
        ("ti-report-money",     "Finanzas",     "/finanzas"),
    ]),
    ("REFERENCIA", [
        ("ti-list-check",       "Criterios",    "/criterios"),
    ]),
]

PAGE_TITLES = {
    "/":             ("Inicio",       "Panel de direccion deportiva"),
    "/plantilla":    ("Plantilla",    "Rayo Vallecano 2025/26"),
    "/scouting":     ("Scouting",     "Busqueda y analisis de candidatos"),
    "/comparador":   ("Comparador",   "Analisis comparativo de jugadores"),
    "/entrenadores": ("Entrenadores", "Perfiles y encaje tactico"),
    "/decisiones":   ("Decisiones",   "Rankings automaticos de plantilla"),
    "/finanzas":     ("Finanzas",     "Masa salarial y simulacion"),
    "/criterios":    ("Criterios",    "Parametros de scouting"),
}


def sidebar():
    today = date.today()
    sections = []
    for group_label, items in NAV_GROUPS:
        sections.append(html.Div(group_label, className="sidebar-section"))
        for icon, label, href in items:
            sections.append(
                dcc.Link(
                    [html.I(className="ti " + icon), label],
                    href=href,
                    className="nav-link-sidebar",
                    id="nav-" + label.lower().replace(" ", "-"),
                )
            )

    return html.Div([
        html.Div([
            html.Img(src=LOGO_URL, alt="Rayo Vallecano"),
            html.Div([
                "Rayo Vallecano",
                html.Span("Scouting 2026/27"),
            ], className="sidebar-brand"),
        ], className="sidebar-logo"),
        html.Div([
            html.I(className="ti ti-calendar-event"),
            html.Div([
                html.Div("Temporada 2025/26", className="sidebar-season-tag-text"),
                html.Div(
                    "Actualizado " + today.strftime("%d/%m/%Y"),
                    className="sidebar-season-tag-sub",
                ),
            ]),
        ], className="sidebar-season-tag"),
        html.Div(sections, style={"paddingBottom": "8px"}),
        html.Div([
            html.Div("TFM - Big Data Deportivo",
                     style={"fontSize": "10px", "color": "rgba(255,255,255,.18)"}),
            html.Div("Universidad Europea 2026",
                     style={"fontSize": "9px", "color": "rgba(255,255,255,.12)", "marginTop": "2px"}),
        ], className="sidebar-footer"),
    ], className="sidebar")


def topbar():
    return html.Div([
        html.Div(
            id="topbar-content",
            style={"display": "flex", "alignItems": "center", "gap": "10px", "flex": "1"},
        ),
        html.Div([
            html.Div([
                html.I(className="ti ti-circle-dot",
                       style={"fontSize": "8px", "color": "#10B981", "marginRight": "5px"}),
                html.Span("En vivo",
                          style={"fontSize": "10px", "fontWeight": "600", "color": "#059669"}),
            ], style={"display": "flex", "alignItems": "center", "background": "#ECFDF5",
                      "border": "1px solid rgba(5,150,105,.2)", "borderRadius": "99px",
                      "padding": "4px 10px"}),
            html.Div([
                html.I(className="ti ti-database",
                       style={"fontSize": "13px", "marginRight": "5px", "color": "#6B7280"}),
                html.Span("OPTA - TM",
                          style={"fontSize": "10.5px", "color": "#6B7280", "fontWeight": "500"}),
            ], style={"display": "flex", "alignItems": "center", "background": "#F9FAFB",
                      "border": "1px solid #E5E7EB", "borderRadius": "8px", "padding": "4px 10px"}),
        ], style={"display": "flex", "alignItems": "center", "gap": "8px"}),
    ], className="topbar", id="global-topbar")


app = Dash(
    __name__,
    use_pages=True,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        "https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@2.44.0/tabler-icons.min.css",
    ],
    suppress_callback_exceptions=True,
    title="Rayo Scouting Tool",
    **( {"background_callback_manager": background_callback_manager}
        if background_callback_manager else {} ),
)

app.layout = html.Div([
    dcc.Location(id="url-app", refresh=False),
    sidebar(),
    html.Div([
        topbar(),
        dash.page_container,
    ], className="main-wrap"),
], style={"display": "flex"})

# Clientside: titulo del topbar segun ruta
_PT_JS = _json.dumps({k: list(v) for k, v in PAGE_TITLES.items()})

clientside_callback(
    (
        "function(pathname){"
        "var titles=" + _PT_JS + ";"
        "var found=titles[pathname]||['Rayo Scouting',''];"
        "var pill={'display':'inline-flex','alignItems':'center','gap':'5px',"
        "'background':'rgba(227,6,19,.07)','border':'1px solid rgba(227,6,19,.16)',"
        "'color':'#B8000E','fontSize':'9.5px','fontWeight':'700',"
        "'letterSpacing':'.05em','padding':'3px 9px','borderRadius':'99px','textTransform':'uppercase'};"
        "return ["
        "{'type':'I','namespace':'dash_html_components','props':{'className':'ti ti-bolt','style':{'color':'#E30613','fontSize':'15px'}}},"
        "{'type':'Div','namespace':'dash_html_components','props':{'children':found[0],'style':{'fontSize':'14px','fontWeight':'800','color':'#0F1117','letterSpacing':'-.02em'}}},"
        "{'type':'Div','namespace':'dash_html_components','props':{'children':found[1],'style':{'fontSize':'11px','color':'#9CA3AF','fontWeight':'400','marginLeft':'2px'}}},"
        "{'type':'Div','namespace':'dash_html_components','props':{'style':{'flex':'1'}}},"
        "{'type':'Div','namespace':'dash_html_components','props':{'children':'2026/27','style':pill}}"
        "];}"
    ),
    Output("topbar-content", "children"),
    Input("url-app", "pathname"),
)


if __name__ == "__main__":
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from dashboard.data_cache import warmup
        warmup()
    except Exception as _e:
        print(f"[WARN] warmup fallido: {_e}")
    app.run(debug=True, host="127.0.0.1", port=8050)
