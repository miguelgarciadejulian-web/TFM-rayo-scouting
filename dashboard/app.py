"""App Dash - Rayo Vallecano Scouting Tool 2026/27."""
from __future__ import annotations
import tempfile
from pathlib import Path
import dash
from dash import Dash, html, dcc
import dash_bootstrap_components as dbc

# Background callbacks (PDF sin timeout) — requiere: pip install diskcache
try:
    import diskcache
    from dash import DiskcacheManager
    _CACHE_DIR = Path(tempfile.gettempdir()) / "rayo_dash_cache"
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    background_callback_manager = DiskcacheManager(diskcache.Cache(str(_CACHE_DIR)))
except Exception as _e:
    background_callback_manager = None
    print(f"⚠️  Background callbacks desactivados ({type(_e).__name__}: {_e})")

LOGO_URL = "https://upload.wikimedia.org/wikipedia/en/d/d8/Rayo_Vallecano_logo.svg"

# Estructura agrupada del menu lateral
NAV_GROUPS = [
    ("ANALISIS", [
        ("ti-home",         "Inicio",       "/"),
        ("ti-users",        "Plantilla",    "/plantilla"),
        ("ti-search",       "Scouting",     "/scouting"),
        ("ti-git-compare",  "Comparador",   "/comparador"),
    ]),
    ("CUERPO TECNICO", [
        ("ti-chalkboard",   "Entrenadores", "/entrenadores"),
    ]),
    ("ESTRATEGIA", [
        ("ti-clipboard-check", "Decisiones", "/decisiones"),
        ("ti-coin-euro",       "Finanzas",   "/finanzas"),
    ]),
    ("REFERENCIA", [
        ("ti-list-check",   "Criterios",    "/criterios"),
    ]),
]


def sidebar():
    sections = []
    for group_label, items in NAV_GROUPS:
        sections.append(html.Div(group_label, className="sidebar-section"))
        for icon, label, href in items:
            sections.append(
                dcc.Link(
                    [html.I(className=f"ti {icon}"), label],
                    href=href,
                    className="nav-link-sidebar",
                    id=f"nav-{label.lower().replace(' ', '-')}",
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
        html.Div(sections),
        html.Div("TFM - Big Data Deportivo", className="sidebar-footer"),
    ], className="sidebar")


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
    sidebar(),
    html.Div(
        dash.page_container,
        className="main-wrap",
    ),
], style={"display": "flex"})


if __name__ == "__main__":
    # Precalentar caché antes de abrir el servidor
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from dashboard.data_cache import warmup
        warmup()
    except Exception as _e:
        print(f"[WARN] warmup fallido: {_e}")
    app.run(debug=True, host="127.0.0.1", port=8050)
