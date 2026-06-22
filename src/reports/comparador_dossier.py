# -*- coding: utf-8 -*-
"""
comparador_dossier.py
=====================
PDF comparativo de jugadores — diseño corporativo Rayo Vallecano.
Genera un informe moderno con radar, métricas y veredicto.
"""
from __future__ import annotations
import io
from datetime import date
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, HRFlowable)

# ── Paleta ──────────────────────────────────────────────────────────────────
C_RED    = colors.HexColor("#E30613")
C_DARK   = colors.HexColor("#111827")
C_DARK2  = colors.HexColor("#1F2937")
C_DARK3  = colors.HexColor("#374151")
C_GREY   = colors.HexColor("#6B7280")
C_LGREY  = colors.HexColor("#9CA3AF")
C_WHITE  = colors.white
C_GREEN  = colors.HexColor("#059669")
C_AMBER  = colors.HexColor("#D97706")
C_STRIPE = colors.HexColor("#F3F4F6")
C_HEADER = colors.HexColor("#1F2937")

PLAYER_COLORS = ["#E30613", "#2563EB", "#059669", "#D97706", "#7C3AED", "#0891B2"]
MPL_COLORS    = PLAYER_COLORS

M_BG    = "#111827"
M_DARK2 = "#1F2937"
M_RED   = "#E30613"
M_WHITE = "#F9FAFB"

PAGE_W, PAGE_H = A4
MARGIN    = 1.8 * cm
CONTENT_W = PAGE_W - 2 * MARGIN


# ── Radar metric definitions (must match comparator.py RADAR_METRICS keys) ──
RADAR_KEYS   = ["goal_contrib_p90", "key_passes_p90", "dribbles_p90",
                "ball_recoveries_p90", "tackles_won_p90", "pass_accuracy"]
RADAR_LABELS = ["G+A/90", "Creación", "Regates", "Recuperación", "Duelos", "Precisión pase"]

# Metrics shown in the comparison table (label, result attr/pct key, is_percentile)
TABLE_METRICS = [
    ("G+A por 90 min",           "goal_contrib_p90",    True),
    ("Pases clave por 90 min",   "key_passes_p90",      True),
    ("Regates exitosos por 90",  "dribbles_p90",        True),
    ("Recuperaciones por 90",    "ball_recoveries_p90", True),
    ("Duelos ganados por 90",    "tackles_won_p90",     True),
    ("Precisión de pase",        "pass_accuracy",       True),
    ("Minutos jugados",          "minutes",             False),
]


# ── Styles ───────────────────────────────────────────────────────────────────
def _build_styles():
    ss = getSampleStyleSheet()
    def _s(name, **kw):
        return ParagraphStyle(name, parent=ss["Normal"], **kw)
    return {
        "title":       _s("t",  fontName="Helvetica-Bold", fontSize=18, textColor=C_WHITE,
                           leading=22, alignment=0),
        "cover_sub":   _s("cs", fontName="Helvetica", fontSize=9, textColor=C_LGREY,
                           leading=13, alignment=0),
        "section":     _s("se", fontName="Helvetica-Bold", fontSize=9, textColor=C_RED,
                           leading=12, spaceAfter=4, spaceBefore=8,
                           textTransform="uppercase"),
        "body":        _s("b",  fontName="Helvetica", fontSize=9, textColor=C_DARK3,
                           leading=13),
        "small":       _s("sm", fontName="Helvetica", fontSize=8, textColor=C_LGREY,
                           leading=11),
        "bold_dark":   _s("bd", fontName="Helvetica-Bold", fontSize=10,
                           textColor=C_DARK, leading=13),
        "player_name": _s("pn", fontName="Helvetica-Bold", fontSize=12,
                           textColor=C_DARK, leading=15),
        "note":        _s("nt", fontName="Helvetica-Oblique", fontSize=7.5,
                           textColor=C_LGREY, leading=11),
    }


# ── Matplotlib helpers ────────────────────────────────────────────────────────
def _fig_to_image(fig, w_cm=17, h_cm=8):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    buf.seek(0)
    plt.close(fig)
    return Image(buf, width=w_cm * cm, height=h_cm * cm)


def _radar_chart(names: list[str], radar_data: list[dict], h_cm=9.0) -> Image:
    """Radar chart. radar_data[i] is a dict {key: percentile 0-100}."""
    N      = len(RADAR_LABELS)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(7, h_cm * 0.85),
                           subplot_kw={"polar": True}, facecolor=M_BG)
    ax.set_facecolor(M_DARK2)
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_rlim(0, 100)
    ax.set_rticks([25, 50, 75, 100])
    ax.set_yticklabels(["25", "50", "75", "100"], color="#6B7280", fontsize=6)
    ax.tick_params(colors="#6B7280")
    ax.spines["polar"].set_color("#374151")
    ax.grid(color="#374151", linewidth=0.6)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(RADAR_LABELS, color=M_WHITE, fontsize=7.5, fontweight="bold")

    for i, (name, rdata) in enumerate(zip(names, radar_data)):
        c = MPL_COLORS[i % len(MPL_COLORS)]
        v = [float(rdata.get(k, 0) or 0) for k in RADAR_KEYS]
        v += v[:1]
        ax.plot(angles, v, color=c, linewidth=2, linestyle="solid")
        ax.fill(angles, v, alpha=0.14, color=c)

    legend_h = [mpatches.Patch(color=MPL_COLORS[i % len(MPL_COLORS)],
                               label=n.split()[-1][:14])
                for i, n in enumerate(names)]
    ax.legend(handles=legend_h, loc="lower right",
              bbox_to_anchor=(1.42, -0.05), fontsize=8,
              framealpha=0.75, facecolor=M_DARK2, edgecolor="#374151",
              labelcolor=M_WHITE)
    plt.tight_layout(pad=0.3)
    return _fig_to_image(fig, w_cm=14, h_cm=h_cm)


def _bar_chart(names: list[str], metric_data: list[tuple[str, list[float]]],
               title: str, h_cm=5.5) -> Image:
    """Horizontal grouped bar chart (percentile scale 0-100)."""
    n_metrics = len(metric_data)
    n_players = len(names)
    fig, ax = plt.subplots(figsize=(8, h_cm * 0.9), facecolor=M_BG)
    ax.set_facecolor(M_DARK2)
    y_pos = np.arange(n_metrics)
    bar_h = 0.8 / n_players
    for i, name in enumerate(names):
        c = MPL_COLORS[i % len(MPL_COLORS)]
        vals = [md[1][i] if i < len(md[1]) else 0 for md in metric_data]
        offset = (i - (n_players - 1) / 2) * bar_h
        bars = ax.barh(y_pos + offset, vals, height=bar_h * 0.9,
                       color=c, alpha=0.88, edgecolor=M_BG)
        for bar, v in zip(bars, vals):
            if v and v > 2:
                ax.text(min(v + 1.5, 103), bar.get_y() + bar.get_height() / 2,
                        f"{v:.0f}", va="center", fontsize=7, fontweight="bold",
                        color=M_WHITE)
    ax.set_yticks(y_pos)
    ax.set_yticklabels([md[0] for md in metric_data], color=M_WHITE, fontsize=8)
    ax.set_xlim(0, 115)
    ax.set_xlabel("Percentil vs misma posición", color="#6B7280", fontsize=8)
    ax.set_title(title, color=M_RED, fontsize=9.5, fontweight="bold", pad=5, loc="left")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#374151")
    ax.spines["bottom"].set_color("#374151")
    ax.tick_params(colors="#6B7280")
    legend_p = [mpatches.Patch(color=MPL_COLORS[i % len(MPL_COLORS)],
                               label=n.split()[-1][:12])
                for i, n in enumerate(names)]
    ax.legend(handles=legend_p, loc="lower right", fontsize=7.5,
              framealpha=0.75, facecolor=M_DARK2, edgecolor="#374151",
              labelcolor=M_WHITE)
    plt.tight_layout(pad=0.3)
    return _fig_to_image(fig, w_cm=14, h_cm=h_cm)


def _score_bar_chart(names: list[str], score_components: list[dict],
                     has_rayo_player: bool = False, h_cm=4.0) -> Image:
    """Grouped bar for Fit Rayo components. Excludes Disponibilidad when Rayo player present."""
    if has_rayo_player:
        components = ["Rendimiento", "Encaje económico", "Perfil de edad"]
        keys       = ["score_rendimiento", "score_economico", "score_edad"]
    else:
        components = ["Rendimiento", "Encaje económico", "Perfil de edad", "Disponibilidad"]
        keys       = ["score_rendimiento", "score_economico", "score_edad", "score_disponibilidad"]

    n     = len(names)
    y_pos = np.arange(len(components))
    bar_h = 0.8 / n
    fig, ax = plt.subplots(figsize=(8, h_cm * 0.9), facecolor=M_BG)
    ax.set_facecolor(M_DARK2)
    for i, name in enumerate(names):
        c    = MPL_COLORS[i % len(MPL_COLORS)]
        vals = [float(score_components[i].get(k) or 0) for k in keys]
        offset = (i - (n - 1) / 2) * bar_h
        bars = ax.barh(y_pos + offset, vals, height=bar_h * 0.9,
                       color=c, alpha=0.88, edgecolor=M_BG)
        for bar, v in zip(bars, vals):
            if v > 2:
                ax.text(min(v + 1, 103), bar.get_y() + bar.get_height() / 2,
                        f"{v:.0f}", va="center", fontsize=7, fontweight="bold",
                        color=M_WHITE)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(components, color=M_WHITE, fontsize=8)
    ax.set_xlim(0, 115)
    ax.set_title("Desglose Fit Rayo (0-100 por componente)", color=M_RED,
                 fontsize=9, fontweight="bold", pad=4, loc="left")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#374151")
    ax.spines["bottom"].set_color("#374151")
    ax.tick_params(colors="#6B7280")
    legend_p = [mpatches.Patch(color=MPL_COLORS[i % len(MPL_COLORS)],
                               label=nm.split()[-1][:12])
                for i, nm in enumerate(names)]
    ax.legend(handles=legend_p, loc="lower right", fontsize=7,
              framealpha=0.75, facecolor=M_DARK2, edgecolor="#374151",
              labelcolor=M_WHITE)
    plt.tight_layout(pad=0.3)
    return _fig_to_image(fig, w_cm=14, h_cm=h_cm)


# ── Player header cards ───────────────────────────────────────────────────────
def _header_table(names: list[str], results: list[Any], st: dict) -> Table:
    n     = len(names)
    col_w = CONTENT_W / n

    cells = []
    for i, (name, r) in enumerate(zip(names, results)):
        c_hex = PLAYER_COLORS[i % len(PLAYER_COLORS)]
        fit   = getattr(r, "fit_score", 0) or 0
        mv    = getattr(r, "market_value_eur", None)
        mv_s  = f"{mv/1e6:.1f}M €" if mv else "n/d"
        cont  = str(getattr(r, "contract_until", "") or "")[:4] or "n/d"
        age   = getattr(r, "age", None) or "—"
        team  = getattr(r, "team", "") or "—"
        pos   = getattr(r, "position", "") or "—"
        fit_c = "#059669" if fit >= 65 else ("#D97706" if fit >= 45 else "#E30613")

        mini_tbl = Table([[
            Paragraph("Fit Rayo", st["small"]),
            Paragraph("Valor TM", st["small"]),
            Paragraph("Contrato", st["small"]),
            Paragraph("Edad", st["small"]),
        ], [
            Paragraph(f'<font color="{fit_c}"><b>{fit:.0f}/100</b></font>', st["bold_dark"]),
            Paragraph(f"<b>{mv_s}</b>", st["bold_dark"]),
            Paragraph(
                f'<b><font color="{"#E30613" if cont in ("2025","2026","2027") else "#1F2937"}">'
                f'{cont}</font></b>', st["bold_dark"]),
            Paragraph(f"<b>{age}</b>", st["bold_dark"]),
        ]], colWidths=[col_w * 0.26] * 4,
            style=TableStyle([
                ("TOPPADDING",    (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING",   (0, 0), (-1, -1), 0),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
            ]))

        cells.append([
            Paragraph(f'<font color="{c_hex}">■</font> {name}', st["player_name"]),
            Spacer(1, 2),
            Paragraph(team, st["body"]),
            Paragraph(pos, st["small"]),
            Spacer(1, 5),
            mini_tbl,
        ])

    tbl = Table([cells], colWidths=[col_w] * n)
    ts  = TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
        ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#FAFAFA")),
    ])
    for i in range(n):
        ts.add("LINEABOVE", (i, 0), (i, 0), 3,
               colors.HexColor(PLAYER_COLORS[i % len(PLAYER_COLORS)]))
    tbl.setStyle(ts)
    return tbl


# ── Metrics table ─────────────────────────────────────────────────────────────
def _metrics_table(names: list[str], results: list[Any],
                   pct_map: dict[str, dict], st: dict) -> Table:
    """
    Comparison table. For is_percentile metrics, values come from pct_map (0-100).
    For raw metrics (minutes), value comes from result attr directly.
    """
    n = len(names)
    col_w_metric = CONTENT_W * 0.36
    col_w_player = (CONTENT_W * 0.50) / n
    col_w_winner = CONTENT_W * 0.14

    header_row = [Paragraph("Métrica", ParagraphStyle(
        "th",  parent=st["small"], fontName="Helvetica-Bold", textColor=C_WHITE))]
    for nm in names:
        header_row.append(Paragraph(nm.split()[-1][:12], ParagraphStyle(
            "th2", parent=st["small"], fontName="Helvetica-Bold", textColor=C_WHITE)))
    header_row.append(Paragraph("Mejor", ParagraphStyle(
        "th3", parent=st["small"], fontName="Helvetica-Bold", textColor=C_WHITE)))

    rows    = [header_row]
    ts_cmds = [
        ("BACKGROUND",    (0, 0), (-1, 0), C_HEADER),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 7),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 7),
        ("GRID",          (0, 0), (-1, -1), 0.4, colors.HexColor("#E5E7EB")),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]

    for row_i, (label, key, is_pct) in enumerate(TABLE_METRICS):
        bg       = colors.HexColor("#F9FAFB") if row_i % 2 == 0 else colors.white
        real_row = row_i + 1
        ts_cmds.append(("BACKGROUND", (0, real_row), (-1, real_row), bg))

        vals = []
        for r in results:
            if is_pct:
                pm = pct_map.get(getattr(r, "name", ""), {})
                v  = pm.get(key)
                if v is not None:
                    try:
                        v = float(v)
                    except Exception:
                        v = None
            else:
                raw = getattr(r, key, None)
                try:
                    v = float(raw) if raw is not None else None
                except Exception:
                    v = None
            vals.append(v)

        winner_idx = None
        valid      = [(v, i) for i, v in enumerate(vals) if v is not None]
        if valid:
            winner_idx = max(valid, key=lambda x: x[0])[1]

        data_row = [Paragraph(label, st["body"])]
        for i, v in enumerate(vals):
            if v is None:
                cell = Paragraph("—", st["small"])
            else:
                c_hex  = PLAYER_COLORS[i % len(PLAYER_COLORS)]
                suffix = '<font color="#9CA3AF"><i> pct</i></font>' if is_pct else ""
                cell   = Paragraph(
                    f'<font color="{c_hex}"><b>{v:.0f}</b></font>{suffix}',
                    st["bold_dark"])
            data_row.append(cell)

        if winner_idx is not None:
            wc    = PLAYER_COLORS[winner_idx % len(PLAYER_COLORS)]
            wname = names[winner_idx].split()[-1][:10]
            data_row.append(Paragraph(f'<font color="{wc}">▶ {wname}</font>', st["small"]))
        else:
            data_row.append(Paragraph("—", st["small"]))

        rows.append(data_row)

    col_widths = [col_w_metric] + [col_w_player] * n + [col_w_winner]
    tbl = Table(rows, colWidths=col_widths)
    tbl.setStyle(TableStyle(ts_cmds))
    return tbl


# ── Verdict table ─────────────────────────────────────────────────────────────
def _verdict_table(names: list[str], results: list[Any],
                   has_rayo_player: bool, st: dict) -> Table:
    fits     = [getattr(r, "fit_score", 0) or 0 for r in results]
    best_idx = int(np.argmax(fits))

    rows = []
    for i, (name, r) in enumerate(zip(names, results)):
        c_hex   = PLAYER_COLORS[i % len(PLAYER_COLORS)]
        fit     = fits[i]
        is_best = (i == best_idx)
        fit_c   = "#059669" if fit >= 65 else ("#D97706" if fit >= 45 else "#E30613")
        badge   = "⭐ RECOMENDADO" if is_best else ""

        breakdown = (
            f"Rendimiento: {getattr(r,'score_rendimiento',0) or 0:.0f}  ·  "
            f"Económico: {getattr(r,'score_economico',0) or 0:.0f}  ·  "
            f"Edad: {getattr(r,'score_edad',0) or 0:.0f}"
        )
        if not has_rayo_player:
            breakdown += f"  ·  Disponibilidad: {getattr(r,'score_disponibilidad',0) or 0:.0f}"

        rows.append([
            Paragraph(f'<font color="{c_hex}">■</font>  {name}', st["player_name"]),
            Paragraph(f'<font color="{fit_c}"><b>{fit:.0f}/100</b></font>', st["bold_dark"]),
            Paragraph(breakdown, st["small"]),
            Paragraph(f'<font color="#059669"><b>{badge}</b></font>' if badge else "",
                      st["body"]),
        ])

    tbl = Table(rows, colWidths=[CONTENT_W * 0.28, CONTENT_W * 0.16,
                                  CONTENT_W * 0.40, CONTENT_W * 0.16])
    ts  = TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ("GRID",          (0, 0), (-1, -1), 0.4, colors.HexColor("#E5E7EB")),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND",    (0, best_idx), (-1, best_idx), colors.HexColor("#F0FDF4")),
        ("LINEABOVE",     (0, best_idx), (-1, best_idx), 1.5, C_GREEN),
        ("LINEBELOW",     (0, best_idx), (-1, best_idx), 1.5, C_GREEN),
    ])
    tbl.setStyle(ts)
    return tbl


# ── Main build function ───────────────────────────────────────────────────────
def build_comparador_dossier(results: list[Any],
                              pct_map: dict[str, dict] | None = None) -> tuple[str, bytes]:
    """
    Build the comparador PDF.

    results : list of ComparisonResult with attrs: name, fit_score, team, at_rayo,
              radar (dict metric_key→percentile 0-100), score_*, market_value_eur,
              contract_until, age, position, minutes, etc.
    pct_map : optional override; if None, uses r.radar from each result.

    Returns (filename, pdf_bytes).
    """
    names = [getattr(r, "name", f"Jugador {i+1}") for i, r in enumerate(results)]
    n     = len(names)

    # ── Build pct_map from r.radar if not provided ───────────────────────────
    if pct_map is None:
        pct_map = {}
    for r in results:
        nm = getattr(r, "name", "")
        if nm not in pct_map or not pct_map.get(nm):
            radar = getattr(r, "radar", None) or {}
            pct_map[nm] = {k: float(v) for k, v in radar.items() if v is not None}

    # ── Detect Rayo players → exclude Disponibilidad ─────────────────────────
    has_rayo = any(
        "Rayo" in (getattr(r, "team", "") or "")
        for r in results
    )

    # ── Filename: apellidos de los jugadores ─────────────────────────────────
    def _safe(s: str) -> str:
        import unicodedata
        s = unicodedata.normalize("NFD", s)
        return "".join(c for c in s
                       if unicodedata.category(c) != "Mn" and (c.isalnum() or c in "_-"))

    surnames = [_safe(nm.split()[-1]) for nm in names]
    fname    = "comparativa_" + "_".join(surnames) + ".pdf"

    # ── PDF build ─────────────────────────────────────────────────────────────
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=MARGIN, bottomMargin=MARGIN)
    st    = _build_styles()
    story = []

    # ── Cover band (2-row, 1-col table — avoids overflow) ────────────────────
    today     = date.today().strftime("%d/%m/%Y")
    sub_extra = ("  ·  Disponibilidad excluida (jugador del Rayo en comparación)"
                 if has_rayo else "")
    cover = Table([
        [Paragraph("RAYO VALLECANO · COMPARATIVA DE FICHAJES", st["title"])],
        [Paragraph(f"Generado el {today}  ·  {n} jugadores{sub_extra}", st["cover_sub"])],
    ], colWidths=[CONTENT_W])
    cover.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_DARK),
        ("TOPPADDING",    (0, 0), (0, 0),   14),
        ("BOTTOMPADDING", (0, 0), (0, 0),   3),
        ("TOPPADDING",    (0, 1), (0, 1),   2),
        ("BOTTOMPADDING", (0, 1), (0, 1),   12),
        ("LEFTPADDING",   (0, 0), (-1, -1), 16),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 16),
        ("LINEBELOW",     (0, 1), (-1, 1),  3, C_RED),
    ]))
    story.append(cover)
    story.append(Spacer(1, 10))

    # ── Player cards ─────────────────────────────────────────────────────────
    story.append(Paragraph("RESUMEN DE JUGADORES", st["section"]))
    story.append(_header_table(names, results, st))
    story.append(Spacer(1, 8))

    # ── Radar chart ──────────────────────────────────────────────────────────
    has_radar = any(
        any(pct_map.get(nm, {}).get(k) is not None for k in RADAR_KEYS)
        for nm in names
    )
    if has_radar:
        story.append(Paragraph("RADAR — PERCENTILES POR POSICIÓN", st["section"]))
        radar_data = [pct_map.get(nm, {}) for nm in names]
        try:
            story.append(_radar_chart(names, radar_data, h_cm=9.0))
        except Exception:
            pass
        story.append(Spacer(1, 6))

    # ── Bar chart — key metrics ───────────────────────────────────────────────
    plot_metrics = [
        ("G+A/90",          "goal_contrib_p90"),
        ("Pases clave/90",  "key_passes_p90"),
        ("Regates/90",      "dribbles_p90"),
        ("Recuperación/90", "ball_recoveries_p90"),
        ("Duelos/90",       "tackles_won_p90"),
        ("Precisión pase",  "pass_accuracy"),
    ]
    metric_data = []
    for label, key in plot_metrics:
        vals = [float(pct_map.get(nm, {}).get(key) or 0) for nm in names]
        if any(v > 0 for v in vals):
            metric_data.append((label, vals))

    if metric_data:
        story.append(Paragraph("MÉTRICAS CLAVE — PERCENTIL VS MISMA POSICIÓN", st["section"]))
        try:
            story.append(_bar_chart(names, metric_data,
                                    "Percentil (100 = mejor de su posición)", h_cm=5.5))
        except Exception:
            pass
        story.append(Spacer(1, 6))

    # ── Fit Rayo breakdown ────────────────────────────────────────────────────
    score_comps = []
    has_scores  = False
    for r in results:
        d = {
            "score_rendimiento":    getattr(r, "score_rendimiento", 0) or 0,
            "score_economico":      getattr(r, "score_economico", 0) or 0,
            "score_edad":           getattr(r, "score_edad", 0) or 0,
            "score_disponibilidad": getattr(r, "score_disponibilidad", 0) or 0,
        }
        if any(v > 0 for v in d.values()):
            has_scores = True
        score_comps.append(d)

    if has_scores:
        story.append(Paragraph("FIT RAYO — DESGLOSE DE COMPONENTES", st["section"]))
        if has_rayo:
            story.append(Paragraph(
                "⚠ Disponibilidad excluida: un jugador del Rayo siempre puntúa 100 "
                "(bajo contrato), lo que distorsionaría la comparación.",
                st["note"]))
            story.append(Spacer(1, 3))
        try:
            story.append(_score_bar_chart(names, score_comps,
                                          has_rayo_player=has_rayo, h_cm=3.8))
        except Exception:
            pass
        story.append(Spacer(1, 6))

    # ── Metrics comparison table ──────────────────────────────────────────────
    story.append(Paragraph("TABLA COMPARATIVA DE MÉTRICAS", st["section"]))
    story.append(Paragraph(
        "Los valores en pct indican el percentil del jugador respecto a su misma posición "
        "(100 = mejor de la muestra).",
        st["note"]))
    story.append(Spacer(1, 4))
    try:
        story.append(_metrics_table(names, results, pct_map, st))
    except Exception as e:
        story.append(Paragraph(f"Error generando tabla: {e}", st["small"]))
    story.append(Spacer(1, 10))

    # ── Verdict ───────────────────────────────────────────────────────────────
    story.append(HRFlowable(width=CONTENT_W, thickness=1.5, color=C_RED, spaceAfter=6))
    story.append(Paragraph("VEREDICTO FINAL", st["section"]))
    try:
        story.append(_verdict_table(names, results, has_rayo, st))
    except Exception:
        pass
    story.append(Spacer(1, 8))

    # ── Methodology note ──────────────────────────────────────────────────────
    method = (
        "Metodología · Fit Rayo = Rendimiento (35%) + Perfil edad (20%) + "
        "Encaje económico (25%)"
    )
    if not has_rayo:
        method += " + Disponibilidad (20%)"
    method += (
        ". Percentiles calculados vs jugadores de la misma posición y liga. "
        "Datos: Transfermarkt · OPTA · SalaryLeaks (2026)."
    )
    story.append(Paragraph(method, st["note"]))

    doc.build(story)
    return fname, buf.getvalue()
