# -*- coding: utf-8 -*-
"""
pdf_base.py
===========
Modulo compartido para generacion de PDFs modernos con WeasyPrint.
Proporciona: paleta, CSS base, SVG gauge, barras CSS, radar matplotlib b64.
"""
from __future__ import annotations
import base64
import io
import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ─── Paleta ──────────────────────────────────────────────────────────────────
RED      = "#E30613"
RED_DK   = "#B8000F"
GREEN    = "#059669"
AMBER    = "#D97706"
LOW      = "#DC2626"
BLUE     = "#2563EB"
BLACK    = "#0D0D0D"
DARK     = "#111827"
DARK2    = "#1F2937"
DARK3    = "#374151"
GREY     = "#6B7280"
LGREY    = "#9CA3AF"
WHITE    = "#FFFFFF"
OFFWHITE = "#F9FAFB"
CARD     = "#F8FAFC"
BORDER   = "#E5E7EB"
GRID     = "#E5E7EB"
GRID2    = "#D1D5DB"
GREEN_LT = "#DCFCE7"
AMBER_LT = "#FEF3C7"
RED_LT   = "#FEE2E2"
STRIPE   = "#F9FAFB"


def score_color(v, hi=68, lo=44):
    """Devuelve color HEX segun valor (verde/ambar/rojo)."""
    v = float(v) if v else 0
    if v >= hi: return GREEN
    if v >= lo: return AMBER
    return LOW


def score_bg(v, hi=68, lo=44):
    """Devuelve color de fondo claro segun valor."""
    v = float(v) if v else 0
    if v >= hi: return GREEN_LT
    if v >= lo: return AMBER_LT
    return RED_LT


def fig_to_b64(fig, dpi=150) -> str:
    """Convierte figura matplotlib a base64 PNG."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


def photo_b64(img_bytes: bytes, max_w=360, max_h=480) -> str:
    """Convierte bytes de imagen a base64 JPEG."""
    try:
        from PIL import Image as _PIL
        im = _PIL.open(io.BytesIO(img_bytes)).convert("RGB")
        im.thumbnail((max_w, max_h))
        out = io.BytesIO()
        im.save(out, format="JPEG", quality=88)
        return base64.b64encode(out.getvalue()).decode()
    except Exception:
        return base64.b64encode(img_bytes).decode()


def svg_gauge(score_10, size=88) -> str:
    """SVG donut gauge inline para score 0-10. Sin dependencias externas."""
    v = round(float(score_10), 1) if score_10 else 0
    col = GREEN if v >= 7 else (AMBER if v >= 5 else LOW)
    r = 34; cx = cy = 50
    circumference = 2 * math.pi * r   # ~213.6
    filled = circumference * v / 10
    score_txt = str(v) if v == int(v) else str(v)
    return (
        f'<svg viewBox="0 0 100 100" width="{size}" height="{size}" xmlns="http://www.w3.org/2000/svg">'
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{GRID2}" stroke-width="10"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{col}" stroke-width="10"'
        f' stroke-dasharray="{filled:.2f} {circumference:.2f}"'
        f' transform="rotate(-90 {cx} {cy})"/>'
        f'<text x="{cx}" y="47" text-anchor="middle" dominant-baseline="middle"'
        f' font-family="Arial,Helvetica,sans-serif" font-size="19" font-weight="bold" fill="{DARK}">{score_txt}</text>'
        f'<text x="{cx}" y="63" text-anchor="middle"'
        f' font-family="Arial,Helvetica,sans-serif" font-size="8" fill="{GREY}">/ 10</text>'
        f'</svg>'
    )


def css_hbar(label, value, max_val=100, note="", label_w="165px") -> str:
    """Una fila de barra horizontal CSS."""
    v = float(value) if value is not None else 0
    col = score_color(v)
    pct = min(v / max_val * 100, 100)
    note_html = f'<span style="color:{LGREY};font-size:6pt;margin-left:2px;">{note}</span>' if note else ""
    return (
        f'<div class="brow">'
        f'<div class="blabel" style="width:{label_w};min-width:{label_w};">{label}</div>'
        f'<div class="btrack"><div class="bfill" style="width:{pct:.1f}%;background:{col};"></div></div>'
        f'<div class="bval" style="color:{col};">{v:.0f}{note_html}</div>'
        f'</div>'
    )


def hbar_chart(rows, label_w="165px") -> str:
    """rows: list de (label, value) o (label, value, note)."""
    bars = "".join(
        css_hbar(r[0], r[1], note=(r[2] if len(r) > 2 else ""), label_w=label_w)
        for r in rows
    )
    return f'<div class="bchart">{bars}</div>'


def html_table(headers, rows, total_row=None) -> str:
    """Tabla HTML con cabecera roja y filas alternadas."""
    th = "".join(f"<td>{h}</td>" for h in headers)
    tr = "".join(
        "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>"
        for row in rows
    )
    tot = ""
    if total_row:
        tot = '<tr class="total-row">' + "".join(f"<td><b>{c}</b></td>" for c in total_row) + "</tr>"
    return f'<table class="tbl"><thead><tr>{th}</tr></thead><tbody>{tr}{tot}</tbody></table>'


def section_header(title: str) -> str:
    return f'<div class="section-hdr">{title.upper()}</div>'


def radar_chart_b64(labels_vals: dict, pool_avg: dict, size_in=5.0) -> str | None:
    """Radar chart matplotlib (tema claro) devuelto como base64 PNG."""
    items = list(labels_vals.items())[:8]
    if len(items) < 3:
        return None
    labs = [str(k) for k, _ in items]
    vals = [float(v) for _, v in items]
    avgs = [float(pool_avg.get(k, 50)) for k, _ in items]
    N    = len(labs)
    ang  = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()

    fig, ax = plt.subplots(figsize=(size_in, size_in), subplot_kw=dict(polar=True))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#F8FAFC")

    for r, lw, ls in [(25, .3, "-"), (50, .7, "--"), (75, .3, "-"), (100, .3, "-")]:
        c = GRID2 if r != 50 else "#B0B8C5"
        ax.plot(ang + ang[:1], [r] * (N + 1), color=c, linewidth=lw, linestyle=ls, zorder=1)
    for a in ang:
        ax.plot([a, a], [0, 100], color=GRID, linewidth=0.4, zorder=1)

    av_c = avgs + avgs[:1]; ac_c = ang + ang[:1]
    ax.fill(ac_c, av_c, color=LGREY, alpha=0.18, zorder=2)
    ax.plot(ac_c, av_c, color=LGREY, linewidth=1.4, linestyle="--", zorder=3)

    vl_c = vals + vals[:1]
    ax.fill(ac_c, vl_c, color=RED, alpha=0.15, zorder=4)
    ax.plot(ac_c, vl_c, color=RED, linewidth=2.3, zorder=5)
    ax.scatter(ang, vals, color=RED, s=38, zorder=6, edgecolors="white", linewidths=0.7)

    ax.set_xticklabels([])
    for i, (lab, v) in enumerate(zip(labs, vals)):
        ax.text(ang[i], 122, f"{lab}\n{int(v)}", ha="center", va="center",
                fontsize=7.5, color=DARK, fontweight="bold", linespacing=1.25)

    ax.set_ylim(0, 100); ax.set_yticks([])
    ax.spines["polar"].set_color(GRID)

    p1 = mpatches.Patch(color=RED,   alpha=0.7, label="Jugador")
    p2 = mpatches.Patch(color=LGREY, alpha=0.6, label="Media posicion")
    ax.legend(handles=[p1, p2], loc="lower right", bbox_to_anchor=(1.42, -0.04),
              fontsize=7.5, framealpha=0.9, facecolor="white",
              edgecolor=GRID, labelcolor=DARK)
    plt.tight_layout(pad=0.3)
    return fig_to_b64(fig)


def adn_chart_b64(axes_vals: dict, dna_target: dict, axes_def: list, size_w=7.5, size_h=4.5) -> str | None:
    """Grafico ADN comparativo (entrenador vs objetivo Rayo). Tema claro."""
    items = [(lab, axes_vals.get(k), dna_target.get(k, {}).get("ideal"))
             for k, lab in axes_def if axes_vals.get(k) is not None]
    if not items:
        return None
    labels      = [i[0] for i in items]
    coach_vals  = [float(i[1]) for i in items]
    target_vals = [float(i[2]) if i[2] is not None else 50.0 for i in items]
    n = len(labels); y = np.arange(n); w = 0.37

    fig, ax = plt.subplots(figsize=(size_w, size_h))
    fig.patch.set_facecolor("white"); ax.set_facecolor("white")

    ax.barh(y + w/2, coach_vals,  w, label="Tecnico",  color=RED,      alpha=0.85, zorder=3)
    ax.barh(y - w/2, target_vals, w, label="ADN Rayo", color="#6B7280", alpha=0.65, zorder=3)

    ax.axvline(x=50, color=GRID2, linewidth=0.9, linestyle="--", zorder=1)
    ax.set_yticks(y); ax.set_yticklabels(labels, fontsize=8.5, color=DARK)
    ax.set_xlim(0, 125)
    ax.tick_params(colors=DARK); ax.xaxis.set_tick_params(color=GRID)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(GRID); ax.spines["bottom"].set_color(GRID)

    for i, (cv, tv) in enumerate(zip(coach_vals, target_vals)):
        diff = cv - tv
        dc   = GREEN if abs(diff) <= 12 else LOW
        ax.text(cv + 1.5, i + w/2, f"{cv:.0f}",     va="center", fontsize=7.5, color=RED,  fontweight="bold")
        ax.text(tv + 1.5, i - w/2, f"{tv:.0f}",     va="center", fontsize=7.5, color=GREY)
        ax.text(119,      i,        f"{diff:+.0f}",  va="center", fontsize=7.5, color=dc,   fontweight="bold")

    ax.set_title("Tecnico (rojo)  vs  ADN objetivo Rayo (gris)          Delta",
                 fontsize=8.5, color=DARK, pad=7, loc="left")
    leg = [mpatches.Patch(color=RED, alpha=0.85, label="Tecnico"),
           mpatches.Patch(color="#6B7280", alpha=0.65, label="ADN Rayo")]
    ax.legend(handles=leg, loc="lower right", fontsize=7.5, framealpha=0.9,
              facecolor="white", edgecolor=GRID, labelcolor=DARK)
    plt.tight_layout(pad=0.4)
    return fig_to_b64(fig)


# ─── CSS base compartido ──────────────────────────────────────────────────────
BASE_CSS = """
@page { size: A4; margin: 1.2cm; }
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: Arial, Helvetica, sans-serif; font-size: 9pt; color: #111827; background: white; line-height: 1.45; }

/* ── Topbar ── */
.topbar { background: #0D0D0D; color: white; padding: 7px 0; display: flex; justify-content: space-between; align-items: center; border-bottom: 2.5px solid #E30613; }
.topbar-l { font-weight: bold; font-size: 8.5pt; color: white; }
.topbar-r { font-size: 8pt; color: #9CA3AF; }

/* ── Hero ── */
.hero { background: white; border: 0.5px solid #E5E7EB; border-top: 3px solid #E30613; display: flex; align-items: center; gap: 14px; padding: 13px 15px; margin-top: 6px; }
.hero-photo { width: 76px; height: 96px; object-fit: cover; border-radius: 3px; border: 0.5px solid #E5E7EB; flex-shrink: 0; }
.hero-info { flex: 1; min-width: 0; }
.hero-name { font-size: 17pt; font-weight: bold; color: #111827; line-height: 1.1; }
.hero-sub  { font-size: 9.5pt; font-weight: bold; color: #E30613; margin-top: 3px; }
.hero-bio  { font-size: 8pt; color: #374151; margin-top: 6px; }
.hero-row  { font-size: 8pt; color: #374151; margin-top: 2px; }
.hero-row .lbl { color: #9CA3AF; }
.gauge-wrap { text-align: center; flex-shrink: 0; }
.gauge-sublbl { font-size: 5.5pt; font-weight: bold; color: #E30613; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 2px; }

/* ── KPI strip ── */
.kpi-row { display: flex; gap: 4px; margin-top: 6px; }
.kpi-card { flex: 1; background: white; border: 0.5px solid #E5E7EB; border-top: 2.5px solid #E30613; padding: 7px 9px; min-width: 0; }
.kpi-label { font-size: 5.5pt; color: #9CA3AF; text-transform: uppercase; letter-spacing: 0.4px; white-space: nowrap; overflow: hidden; }
.kpi-value { font-size: 10pt; font-weight: bold; color: #111827; margin-top: 2px; line-height: 1.15; }

/* ── Strengths / Weaknesses ── */
.sw-row { display: flex; gap: 4px; margin-top: 5px; }
.sw-box { flex: 1; border: 0.5px solid #E5E7EB; padding: 6px 8px; min-width: 0; }
.sw-green { background: #F0FDF4; }
.sw-amber { background: #FFFBEB; }
.sw-title { font-size: 6pt; font-weight: bold; text-transform: uppercase; letter-spacing: 0.3px; margin-bottom: 4px; }
.sw-green .sw-title { color: #059669; }
.sw-amber .sw-title { color: #D97706; }
.pills { display: flex; flex-wrap: wrap; gap: 3px; }
.pill { font-size: 6.5pt; padding: 2px 8px; border-radius: 10px; }
.pill-green { background: #DCFCE7; color: #059669; }
.pill-amber { background: #FEF3C7; color: #D97706; }
.pill-red   { background: #FEE2E2; color: #DC2626; }

/* ── Section header ── */
.section-hdr { background: #E30613; color: white; font-weight: bold; font-size: 7.5pt; text-transform: uppercase; padding: 4px 10px; letter-spacing: 0.5px; margin-top: 9px; margin-bottom: 5px; }

/* ── Bar chart ── */
.bchart { margin: 3px 0; }
.brow { display: flex; align-items: center; margin: 3px 0; gap: 6px; }
.blabel { font-size: 7pt; color: #374151; text-align: right; flex-shrink: 0; }
.btrack { flex: 1; background: #F3F4F6; border-radius: 2px; height: 13px; min-width: 0; }
.bfill  { height: 100%; border-radius: 2px; opacity: 0.88; }
.bval   { font-size: 7.5pt; font-weight: bold; flex-shrink: 0; width: 28px; }

/* ── Two-column layout ── */
.two-col { display: flex; gap: 10px; margin-top: 5px; }
.col-l { flex: 0 0 51%; min-width: 0; }
.col-r { flex: 1; min-width: 0; }

/* ── Tables ── */
.tbl { width: 100%; border-collapse: collapse; font-size: 7pt; margin: 3px 0; }
.tbl thead tr { background: #E30613; }
.tbl thead td { color: white; font-weight: bold; padding: 4px 5px; font-size: 6.5pt; text-transform: uppercase; letter-spacing: 0.2px; }
.tbl tbody tr:nth-child(odd)  { background: white; }
.tbl tbody tr:nth-child(even) { background: #F9FAFB; }
.tbl tbody td { padding: 3.5px 5px; color: #111827; border-bottom: 0.3px solid #E5E7EB; }
.tbl .total-row td { font-weight: bold; background: #F8FAFC !important; border-top: 1px solid #D1D5DB; color: #111827; }

/* ── 2-column grid ── */
.grid2 { display: flex; gap: 8px; margin: 2px 0; }
.grid2-cell { flex: 1; min-width: 0; }
.group-title { font-size: 8pt; font-weight: bold; color: #E30613; margin-bottom: 2px; margin-top: 4px; }
.sub-title   { font-size: 8pt; font-weight: bold; color: #E30613; margin: 4px 0 3px; }

/* ── Badge (entrenador) ── */
.badge { display: inline-block; padding: 4px 14px; border-radius: 4px; font-weight: bold; font-size: 9pt; margin-top: 6px; }
.badge-green { background: #DCFCE7; color: #059669; border: 1px solid #059669; }
.badge-amber { background: #FEF3C7; color: #D97706; border: 1px solid #D97706; }
.badge-red   { background: #FEE2E2; color: #DC2626; border: 1px solid #DC2626; }

/* ── Risk tags ── */
.risk-row { display: flex; gap: 5px; flex-wrap: wrap; margin-top: 5px; }
.risk-tag { font-size: 6.5pt; padding: 2px 8px; border-radius: 10px; border: 0.5px solid; }

/* ── Info box (notas manuales) ── */
.info-box { background: #F8FAFC; border-left: 3px solid #E30613; padding: 7px 10px; margin: 4px 0; font-size: 8pt; color: #374151; }
.info-box .info-label { font-weight: bold; color: #E30613; font-size: 7pt; text-transform: uppercase; letter-spacing: 0.3px; margin-bottom: 2px; }

/* ── Formula note ── */
.formula-note { font-size: 6.5pt; color: #9CA3AF; font-style: italic; margin-top: 3px; }

/* ── Footer ── */
.footer { border-top: 1.5px solid #E30613; margin-top: 14px; padding-top: 5px; font-size: 6pt; color: #9CA3AF; font-style: italic; }
"""


def build_html_doc(body_html: str, title: str = "Informe") -> str:
    """Envuelve body HTML en documento completo con CSS base."""
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>{BASE_CSS}</style>
</head>
<body>
{body_html}
</body>
</html>"""


def html_to_pdf(html: str) -> bytes:
    """Convierte HTML a bytes PDF con WeasyPrint."""
    import weasyprint
    return weasyprint.HTML(string=html).write_pdf()
