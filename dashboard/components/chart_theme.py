# -*- coding: utf-8 -*-
"""
chart_theme.py
==============
Tema visual unificado para todos los gráficos Plotly de la aplicación.
Registra una plantilla "rayo_scouting" y expone helpers de color y layout.

Uso::

    from dashboard.components.chart_theme import apply_theme, RAYO_RED, C_POSITIVE

    fig = go.Figure(...)
    apply_theme(fig)          # aplica defaults + ajustes opcionales
"""
from __future__ import annotations
import plotly.graph_objects as go
import plotly.io as pio

# ── Paleta de colores ────────────────────────────────────────────────────────
RAYO_YELLOW  = "#FFD600"   # amarillo corporativo Rayo Vallecano
RAYO_RED     = "#FFD600"   # alias para compatibilidad con código existente
RAYO_DARK    = "#0D0D0D"   # negro corporativo
RAYO_GRAY    = "#6B7280"
RAYO_LIGHT   = "#F3F4F6"
RAYO_WHITE   = "#FFFFFF"

C_POSITIVE   = "#059669"   # verde esmeralda
C_WARNING    = "#F59E0B"   # ámbar
C_DANGER     = "#DC2626"   # rojo (solo para alertas/errores reales)
C_NEUTRAL    = "#9CA3AF"   # gris neutro
C_BLUE       = "#3B82F6"   # azul referencia
C_PURPLE     = "#7C3AED"   # púrpura acento

# Paleta para series múltiples (orden de prioridad visual)
SERIES_COLORS = [
    RAYO_YELLOW, RAYO_DARK, C_BLUE, C_POSITIVE, C_WARNING, C_PURPLE,
    "#F97316", "#06B6D4", "#8B5CF6", "#10B981",
]

# ── Template Plotly ──────────────────────────────────────────────────────────
_FONT_FAMILY = "'Inter', 'Helvetica Neue', Arial, sans-serif"

_AXIS_COMMON = dict(
    gridcolor="#F0F0F4",
    linecolor="#E5E7EB",
    tickcolor="#E5E7EB",
    tickfont=dict(size=11, color=RAYO_GRAY, family=_FONT_FAMILY),
    title_font=dict(size=11, color="#374151", family=_FONT_FAMILY),
    showgrid=True,
    zeroline=False,
    showline=True,
)

_TEMPLATE = go.layout.Template(
    layout=go.Layout(
        colorway=SERIES_COLORS,
        font=dict(family=_FONT_FAMILY, size=12, color=RAYO_DARK),
        paper_bgcolor=RAYO_WHITE,
        plot_bgcolor=RAYO_WHITE,
        title=dict(
            font=dict(size=13, color=RAYO_DARK, family=_FONT_FAMILY),
            x=0.02, xanchor="left", pad=dict(b=8),
        ),
        xaxis=_AXIS_COMMON,
        yaxis=_AXIS_COMMON,
        legend=dict(
            bgcolor="rgba(255,255,255,0.95)",
            bordercolor="#E5E7EB",
            borderwidth=1,
            font=dict(size=11, color="#374151", family=_FONT_FAMILY),
            itemsizing="constant",
        ),
        hoverlabel=dict(
            bgcolor=RAYO_DARK,
            font=dict(size=11, color="white", family=_FONT_FAMILY),
            bordercolor=RAYO_DARK,
            namelength=-1,
        ),
        margin=dict(l=48, r=24, t=48, b=40),
        colorscale=dict(
            sequential=[[0, "#FFFDE7"], [0.5, RAYO_YELLOW], [1, RAYO_DARK]],
        ),
    )
)

pio.templates["rayo_scouting"] = _TEMPLATE
# No establecemos default global para no interferir con otros; cada fig lo aplica
# Si se quiere global: pio.templates.default = "rayo_scouting"


# ── Helper principal ─────────────────────────────────────────────────────────
def apply_theme(
    fig: go.Figure,
    *,
    height: int | None = None,
    title: str | None = None,
    transparent: bool = False,
    compact: bool = False,
) -> go.Figure:
    """
    Aplica el tema rayo_scouting a una figura existente.

    Parámetros
    ----------
    height      : alto en px (opcional).
    title       : título del gráfico (opcional).
    transparent : usa fondo rgba(0,0,0,0) — para gráficos en tarjetas.
    compact     : márgenes reducidos para gráficos pequeños en panel.
    """
    updates: dict = {"template": "rayo_scouting"}
    if height:
        updates["height"] = height
    if title:
        updates["title_text"] = title
    if transparent:
        updates["paper_bgcolor"] = "rgba(0,0,0,0)"
        updates["plot_bgcolor"] = "rgba(0,0,0,0)"
    if compact:
        updates["margin"] = dict(l=32, r=16, t=36, b=28)
        updates["font"] = dict(size=10)

    fig.update_layout(**updates)
    return fig


# ── Helpers de color ─────────────────────────────────────────────────────────
def score_color(value: float, scale: float = 100.0) -> str:
    """
    Devuelve un color basado en el score (0-scale).
    ≥70%  → verde    |  ≥45% → ámbar    |  <45% → rojo suave
    """
    pct = value / scale
    if pct >= 0.70:
        return C_POSITIVE
    if pct >= 0.45:
        return C_WARNING
    return "#EF4444"


def sequential_reds(n: int) -> list[str]:
    """n colores desde amarillo claro (#FFFDE7) a amarillo Rayo (#FFD600)."""
    base = (255/255, 214/255, 0/255)      # FFD600 en RGB [0,1]
    result = []
    for i in range(n):
        t = i / max(n - 1, 1)
        r = 1.0 - t * (1.0 - base[0])
        g = 1.0 - t * (1.0 - base[1])
        b = 1.0 - t * (1.0 - base[2])
        result.append(f"#{int(r*255):02X}{int(g*255):02X}{int(b*255):02X}")
    return result


def hex_to_rgba(hex_color: str, alpha: float = 0.15) -> str:
    """Convierte #RRGGBB a rgba(r,g,b,a)."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# ── Config estándar para dcc.Graph ───────────────────────────────────────────
GRAPH_CONFIG = {
    "displayModeBar": True,
    "modeBarButtonsToRemove": [
        "zoom2d", "pan2d", "select2d", "lasso2d",
        "zoomIn2d", "zoomOut2d", "autoScale2d",
        "hoverClosestCartesian", "hoverCompareCart