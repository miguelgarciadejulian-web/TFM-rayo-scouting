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
    Image, KeepTogether, HRFlowable)

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

# Player accent colors (up to 6)
PLAYER_COLORS = ["#E30613","#2563EB","#059669","#D97706","#7C3AED","#0891B2"]
MPL_COLORS    = PLAYER_COLORS

M_BG    = "#111827"
M_DARK2 = "#1F2937"
M_RED   = "#E30613"
M_WHITE = "#F9FAFB"

PAGE_W, PAGE_H = A4
MARGIN = 1.8 * cm
CONTENT_W = PAGE_W - 2 * MARGIN


# ── Styles ───────────────────────────────────────────────────────────────────
def _build_styles():
    ss = getSampleStyleSheet()
    def _s(name, **kw):
        return ParagraphStyle(name, parent=ss["Normal"], **kw)
    return {
        "title":     _s("t", fontName="Helvetica-Bold", fontSize=22, textColor=C_WHITE,
                         leading=26, alignment=1),
        "subtitle":  _s("su", fontName="Helvetica", fontSize=11, textColor=C_LGREY,
                         leading=14, alignment=1),
        "section":   _s("se", fontName="Helvetica-Bold", fontSize=10, textColor=C_RED,
                         leading=13, spaceAfter=4, spaceBefore=10,
                         textTransform="uppercase"),
        "body":      _s("b",  fontName="Helvetica", fontSize=9, textColor=C_DARK3,
                         leading=13),
        "small":     _s("sm", fontName="Helvetica", fontSize=8, textColor=C_LGREY,
                         leading=11),
        "bold_dark": _s("bd", fontName="Helvetica-Bold", fontSize=10,
                         textColor=C_DARK, leading=13),
        "player_name": _s("pn", fontName="Helvetica-Bold", fontSize=13,
                           textColor=C_DARK, leading=16),
        "verdict_win": _s("vw", fontName="Helvetica-Bold", fontSize=11,
                           textColor=C_GREEN, leading=14),
        "verdict_tie": _s("vt", fontName="Helvetica-Bold", fontSize=11,
                           textColor=C_AMBER, leading=14),
    }


# ── Matplotlib helpers ────────────────────────────────────────────────────────
def _fig_to_image(fig, w_cm=17, h_cm=8):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    buf.seek(0)
    plt.close(fig)
    return Image(buf, width=w_cm * cm, height=h_cm * cm)


def _radar_chart(names: list[str], data: list[dict], labels: list[str], h_cm=9.5) -> Image:
    """Draw overlapping radar for all players."""
    N = len(labels)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(7, h_cm * 0.85),
                           subplot_kw={"polar": True}, facecolor=M_BG)
    ax.set_facecolor(M_DARK2)
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_rlim(0, 100)
    ax.set_rticks([25, 50, 75, 100])
    ax.set_yticklabels(["25", "50", "75", "100"],
                       color="#6B7280", fontsize=6)
    ax.tick_params(colors="#6B7280")
    ax.spines["polar"].set_color("#374151")
    ax.grid(color="#374151", linewidth=0.6)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, color=M_WHITE, fontsize=7.5, fontweight="bold")

    for i, (name, vals) in enumerate(zip(names, data)):
        c = MPL_COLORS[i % len(MPL_COLORS)]
        v = [vals.get(k, 0) or 0 for k in labels] + [vals.get(labels[0], 0) or 0]
        ax.plot(angles, v, color=c, linewidth=2, linestyle="solid")
        ax.fill(angles, v, alpha=0.13, color=c)
        # peak label on highest axis
        peak_idx = np.argmax(v[:-1])
        ax.annotate(name.split()[-1][:8],
                    xy=(angles[peak_idx], v[peak_idx]),
                    xytext=(angles[peak_idx], min(v[peak_idx] + 12, 105)),
                    color=c, fontsize=6.5, fontweight="bold", ha="center")

    legend_handles = [
        mpatches.Patch(color=MPL_COLORS[i % len(MPL_COLORS)], label=n.split()[-1][:14])
        for i, n in enumerate(names)
    ]
    ax.legend(handles=legend_handles, loc="lower right",
              bbox_to_anchor=(1.4, -0.05), fontsize=7.5,
              framealpha=0.7, facecolor=M_DARK2, edgecolor="#374151",
              labelcolor=M_WHITE)
    plt.tight_layout(pad=0.3)
    return _fig_to_image(fig, w_cm=14, h_cm=h_cm)


def _bar_chart(names: list[str], metric_data: list[tuple[str, list[float]]],
               title: str, h_cm=5.5) -> Image:
    """Horizontal grouped bar chart for key metrics."""
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
            if v and v > 0:
                ax.text(min(v + 1.5, 103), bar.get_y() + bar.get_height() / 2,
                        f"{v:.0f}", va="center", fontsize=7, fontweight="bold",
                        color=M_WHITE)
    ax.set_yticks(y_pos)
    ax.set_yticklabels([md[0] for md in metric_data], color=M_WHITE, fontsize=8)
    ax.set_xlim(0, 110)
    ax.set_xlabel("Percentil", color="#6B7280", fontsize=8)
    ax.set_title(title, color=M_RED, fontsize=10, fontweight="bold", pad=5, loc="left")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#374151")
    ax.spines["bottom"].set_color("#374151")
    ax.tick_params(colors="#6B7280")
    legend_p = [mpatches.Patch(color=MPL_COLORS[i % len(MPL_COLORS)],
                               label=n.split()[-1][:12])
                for i, n in enumerate(names)]
    ax.legend(handles=legend_p, loc="lower right", fontsize=7,
              framealpha=0.7, facecolor=M_DARK2, edgecolor="#374151",
              labelcolor=M_WHITE)
    plt.tight_layout(pad=0.3)
    return _fig_to_image(fig, w_cm=14, h_cm=h_cm)


def _score_bar_chart(names: list[str], score_components: list[dict], h_cm=4.5) -> Image:
    """Stacked / grouped bar for Fit Rayo component scores."""
    components = ["Rendimiento", "Económico", "Edad", "Disponibilidad"]
    keys = ["score_rendimiento", "score_economico", "score_edad", "score_disponibilidad"]
    n = len(names)
    y_pos = np.arange(len(components))
    bar_h = 0.8 / n
    fig, ax = plt.subplots(figsize=(8, h_cm * 0.9), facecolor=M_BG)
    ax.set_facecolor(M_DARK2)
    for i, name in enumerate(names):
        c = MPL_COLORS[i % len(MPL_COLORS)]
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
    ax.set_xlim(0, 110)
    ax.set_title("Desglose Fit Rayo (0-100 por componente)", color=M_RED,
                 fontsize=9, fontweight="bold", pad=4, loc="left")
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#374151"); ax.spines["bottom"].set_color("#374151")
    ax.tick_params(colors="#6B7280")
    legend_p = [mpatches.Patch(color=MPL_COLORS[i % len(MPL_COLORS)],
                               label=n.split()[-1][:12])
                for i, n in enumerate(names)]
    ax.legend(handles=legend_p, loc="lower right", fontsize=7,
              framealpha=0.7, facecolor=M_DARK2, edgecolor="#374151",
              labelcolor=M_WHITE)
    plt.tight_layout(pad=0.3)
    return _fig_to_image(fig, w_cm=14, h_cm=h_cm)


# ── Header page ───────────────────────────────────────────────────────────────
def _header_table(names: list[str], results: list[Any], st: dict) -> Table:
    """One-row table with one column per player showing key data."""
    n = len(names)
    col_w = CONTENT_W / n

    header_cells = []
    for i, (name, r) in enumerate(zip(names, results)):
        c_hex = PLAYER_COLORS[i % len(PLAYER_COLORS)]
        c_rl  = colors.HexColor(c_hex)
        fit   = getattr(r, "fit_score", None) or 0
        fit_c = C_GREEN if fit >= 65 else (C_AMBER if fit >= 45 else C_RED)
        mv    = getattr(r, "market_value_eur", None)
        mv_s  = f"{mv/1e6:.1f}M €" if mv else "n/d"
        cont  = str(getattr(r, "contract_until", "") or "")[:4] or "n/d"
        age   = getattr(r, "age", None) or "—"
        team  = getattr(r, "team", "") or "—"
        pos   = getattr(r, "position", "") or "—"
        role_lbl = getattr(r, "primary_role_label", "") or pos

        cell_content = [
            Paragraph(f'<font color="{c_hex}">■</font> {name}', st["player_name"]),
            Spacer(1, 3),
            Paragraph(team, st["body"]),
            Paragraph(pos, st["small"]),
            Spacer(1, 4),
            Table([[
                Paragraph("Fit Rayo", st["small"]),
                Paragraph("Valor TM", st["small"]),
                Paragraph("Contrato", st["small"]),
                Paragraph("Edad", st["small"]),
            ], [
                Paragraph(f'<font color="{"#059669" if fit>=65 else "#D97706" if fit>=45 else "#E30613"}">'
                           f'<b>{fit:.0f}/100</b></font>', st["bold_dark"]),
                Paragraph(f"<b>{mv_s}</b>", st["bold_dark"]),
                Paragraph(f"<b>{cont}</b>",
                          ParagraphStyle("cx", parent=st["bold_dark"],
                                         textColor=colors.HexColor(
                                             "#E30613" if cont in ("2025","2026","2027") else "#1F2937"))),
                Paragraph(f"<b>{age}</b>", st["bold_dark"]),
            ]], colWidths=[col_w*0.27]*4,
            style=TableStyle([
                ("TOPPADDING",    (0,0),(-1,-1), 2),
                ("BOTTOMPADDING", (0,0),(-1,-1), 2),
                ("LEFTPADDING",   (0,0),(-1,-1), 0),
                ("RIGHTPADDING",  (0,0),(-1,-1), 4),
            ])),
        ]
        header_cells.append(cell_content)

    tbl = Table([header_cells], colWidths=[col_w] * n)
    ts  = TableStyle([
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING",   (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 10),
        ("GRID",         (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
        ("BACKGROUND",   (0, 0), (-1, -1), colors.HexColor("#FAFAFA")),
        ("ROUNDEDCORNERS", [6],),
    ])
    for i in range(n):
        c_hex = PLAYER_COLORS[i % len(PLAYER_COLORS)]
        ts.add("LINEABOVE", (i, 0), (i, 0), 3, colors.HexColor(c_hex))
    tbl.setStyle(ts)
    return tbl


# ── Metrics table ─────────────────────────────────────────────────────────────
def _metrics_table(names, results, pct_map: dict[str, dict], st: dict) -> Table:
    """Table: metric | p1 | p2 | ... | winner"""
    KEY_METRICS = [
        ("Contribución goles+asist / 90", "goal_contrib_p90"),
        ("Pases completados / 90",        "passes_completed_p90"),
        ("Regates exitosos / 90",         "dribbles_p90"),
        ("Duelos ganados / 90",           "tackles_won_p90"),
        ("Presión exitosa / 90",          "pressures_p90"),
        ("Pases clave / 90",              "key_passes_p90"),
        ("Disparos a puerta / 90",        "shots_on_target_p90"),
        ("Minutos jugados",               "minutes"),
    ]
    n = len(names)
    col_w_metric = CONTENT_W * 0.38
    col_w_player = (CONTENT_W * 0.50) / n
    col_w_winner = CONTENT_W * 0.12

    header_row = [Paragraph("Métrica", ParagraphStyle("th", parent=st["small"],
                             fontName="Helvetica-Bold", textColor=C_WHITE))]
    for nm in names:
        header_row.append(Paragraph(nm.split()[-1][:10],
                          ParagraphStyle("th2", parent=st["small"],
                                         fontName="Helvetica-Bold", textColor=C_WHITE)))
    header_row.append(Paragraph("Mejor", ParagraphStyle("th3", parent=st["small"],
                                fontName="Helvetica-Bold", textColor=C_WHITE)))

    rows = [header_row]
    ts_cmds = [
        ("BACKGROUND",   (0,0), (-1,0), C_HEADER),
        ("TOPPADDING",   (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",(0,0), (-1,-1), 5),
        ("LEFTPADDING",  (0,0), (-1,-1), 7),
        ("RIGHTPADDING", (0,0), (-1,-1), 7),
        ("GRID",         (0,0), (-1,-1), 0.4, colors.HexColor("#E5E7EB")),
        ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
    ]

    for row_i, (label, key) in enumerate(KEY_METRICS):
        row_bg = colors.HexColor("#F9FAFB") if row_i % 2 == 0 else colors.white
        real_row = row_i + 1
        ts_cmds.append(("BACKGROUND", (0, real_row), (-1, real_row), row_bg))

        vals = []
        for r in results:
            # try percentile first, then raw value normalized
            pm = pct_map.get(getattr(r, "name", ""), {})
            v = pm.get(key)
            if v is None:
                raw = getattr(r, key, None)
                if raw is not None:
                    try:
                        v = min(float(raw) / 90 * 100, 100)
                    except Exception:
                        v = None
            vals.append(v)

        winner_idx = None
        if any(v is not None for v in vals):
            valid = [(v, i) for i, v in enumerate(vals) if v is not None]
            winner_idx = max(valid, key=lambda x: x[0])[1]

        data_row = [Paragraph(label, st["body"])]
        for i, v in enumerate(vals):
            if v is None:
                cell = Paragraph("—", st["small"])
            else:
                c_hex = PLAYER_COLORS[i % len(PLAYER_COLORS)]
                cell = Paragraph(f'<font color="{c_hex}"><b>{v:.0f}</b></font>', st["bold_dark"])
            data_row.append(cell)

        if winner_idx is not None:
            wc = PLAYER_COLORS[winner_idx % len(PLAYER_COLORS)]
            wname = names[winner_idx].split()[-1][:10]
            data_row.append(Paragraph(f'<font color="{wc}">▶ {wname}</font>', st["small"]))
        else:
            data_row.append(Paragraph("—", st["small"]))

        rows.append(data_row)

    col_widths = [col_w_metric] + [col_w_player]*n + [col_w_winner]
    tbl = Table(rows, colWidths=col_widths)
    tbl.setStyle(TableStyle(ts_cmds))
    return tbl


# ── Verdict ───────────────────────────────────────────────────────────────────
def _verdict_table(names, results, st: dict) -> Table:
    fits = [getattr(r, "fit_score", 0) or 0 for r in results]
    best_idx = int(np.argmax(fits))
    best_name = names[best_idx]
    best_fit  = fits[best_idx]

    rows = []
    for i, (name, r) in enumerate(zip(names, results)):
        c_hex = PLAYER_COLORS[i % len(PLAYER_COLORS)]
        fit   = fits[i]
        is_best = (i == best_idx)
        badge  = "⭐ RECOMENDADO" if is_best else ""
        fit_c  = "#059669" if fit >= 65 else "#D97706" if fit >= 45 else "#E30613"
        rows.append([
            Paragraph(f'<font color="{c_hex}">■</font>  {name}', st["player_name"]),
            Paragraph(f'<font color="{fit_c}"><b>Fit Rayo: {fit:.0f}/100</b></font>', st["bold_dark"]),
            Paragraph(f'Rendimiento: {getattr(r,"score_rendimiento",0) or 0:.0f} · '
                      f'Económico: {getattr(r,"score_economico",0) or 0:.0f} · '
                      f'Edad: {getattr(r,"score_edad",0) or 0:.0f}',
                      st["small"]),
            Paragraph(f'<font color="#059669"><b>{badge}</b></font>' if badge else "", st["body"]),
        ])

    tbl = Table(rows, colWidths=[CONTENT_W*0.30, CONTENT_W*0.25,
                                  CONTENT_W*0.30, CONTENT_W*0.15])
    ts  = TableStyle([
        ("TOPPADDING",    (0,0), (-1,-1), 8),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ("LEFTPADDING",   (0,0), (-1,-1), 10),
        ("RIGHTPADDING",  (0,0), (-1,-1), 10),
        ("GRID",          (0,0), (-1,-1), 0.4, colors.HexColor("#E5E7EB")),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("BACKGROUND",    (0, best_idx), (-1, best_idx), colors.HexColor("#F0FDF4")),
        ("LINEABOVE",     (0, best_idx), (-1, best_idx), 1.5, C_GREEN),
    ])
    tbl.setStyle(ts)
    return tbl


# ── Main build function ───────────────────────────────────────────────────────
def build_comparador_dossier(results: list[Any],
                              pct_map: dict[str, dict] | None = None) -> tuple[str, bytes]:
    """
    Builds the comparador PDF.

    results : list of ComparisonResult (or similar objects with .name, .fit_score, etc.)
    pct_map : dict[player_name -> dict[metric_key -> percentile 0-100]]
    Returns (filename, bytes).
    """
    pct_map = pct_map or {}
    names   = [getattr(r, "name", f"Jugador {i+1}") for i, r in enumerate(results)]
    n       = len(names)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=MARGIN, bottomMargin=MARGIN)
    st  = _build_styles()
    story = []

    # ── Cover band ──────────────────────────────────────────────────────────
    today = date.today().strftime("%d/%m/%Y")
    cover = Table([[
        Paragraph("RAYO VALLECANO · COMPARATIVA DE FICHAJES", st["title"]),
        Paragraph(f"Informe generado el {today}  ·  {n} jugadores comparados", st["subtitle"]),
    ]], colWidths=[CONTENT_W])
    cover.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), C_DARK),
        ("TOPPADDING",    (0,0), (-1,-1), 14),
        ("BOTTOMPADDING", (0,0), (-1,-1), 12),
        ("LEFTPADDING",   (0,0), (-1,-1), 16),
        ("RIGHTPADDING",  (0,0), (-1,-1), 16),
        ("LINEBELOW",     (0,-1), (-1,-1), 3, C_RED),
    ]))
    story.append(cover)
    story.append(Spacer(1, 12))

    # ── Player header cards ──────────────────────────────────────────────────
    story.append(Paragraph("RESUMEN DE JUGADORES", st["section"]))
    story.append(_header_table(names, results, st))
    story.append(Spacer(1, 10))

    # ── Radar chart ─────────────────────────────────────────────────────────
    radar_metrics_map = None
    radar_labels = []
    if pct_map:
        # Pick the most populated metrics across all players
        all_keys: dict[str, int] = {}
        for pm in pct_map.values():
            for k, v in pm.items():
                if v is not None and "_p90" in k:
                    all_keys[k] = all_keys.get(k, 0) + 1
        top_keys = sorted(all_keys, key=lambda k: -all_keys[k])[:8]
        radar_labels = [k.replace("_p90","").replace("_"," ").title()
                        for k in top_keys]
        radar_data = []
        for nm in names:
            pm = pct_map.get(nm, {})
            radar_data.append({radar_labels[i]: pm.get(k, 0) or 0
                                for i, k in enumerate(top_keys)})

        story.append(Paragraph("RADAR — PERCENTILES POR POSICIÓN", st["section"]))
        try:
            story.append(_radar_chart(names, radar_data, radar_labels, h_cm=9))
        except Exception:
            pass
        story.append(Spacer(1, 6))

    # ── Bar chart (key metrics percentiles) ─────────────────────────────────
    if pct_map:
        KEY_PLOT = [
            ("G+A/90",         "goal_contrib_p90"),
            ("Pases clave/90", "key_passes_p90"),
            ("Regates/90",     "dribbles_p90"),
            ("Duelos gan./90", "tackles_won_p90"),
            ("Presión/90",     "pressures_p90"),
            ("Disparos/90",    "shots_on_target_p90"),
        ]
        metric_data = []
        for label, key in KEY_PLOT:
            vals = [float(pct_map.get(nm, {}).get(key) or 0) for nm in names]
            if any(v > 0 for v in vals):
                metric_data.append((label, vals))
        if metric_data:
            story.append(Paragraph("MÉTRICAS CLAVE — PERCENTIL VS MISMA POSICIÓN", st["section"]))
            try:
                story.append(_bar_chart(names, metric_data,
                                         "Percentil (100 = mejor de su liga y posición)", h_cm=5.5))
            except Exception:
                pass
            story.append(Spacer(1, 6))

    # ── Fit Rayo breakdown chart ─────────────────────────────────────────────
    score_comps = []
    has_scores = False
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
        try:
            story.append(_score_bar_chart(names, score_comps, h_cm=4.5))
        except Exception:
            pass
        story.append(Spacer(1, 6))

    # ── Metrics comparison table ─────────────────────────────────────────────
    story.append(Paragraph("TABLA COMPARATIVA DE MÉTRICAS", st["section"]))
    try:
        story.append(_metrics_table(names, results, pct_map, st))
    except Exception as e:
        story.append(Paragraph(f"Error generando tabla: {e}", st["small"]))
    story.append(Spacer(1, 10))

    # ── Verdict ──────────────────────────────────────────────────────────────
    story.append(HRFlowable(width=CONTENT_W, thickness=1.5, color=C_RED, spaceAfter=8))
    story.append(Paragraph("VEREDICTO FINAL", st["section"]))
    try:
        story.append(_verdict_table(names, results, st))
    except Exception:
        pass
    story.append(Spacer(1, 8))

    # ── Methodology note ─────────────────────────────────────────────────────
    story.append(Paragraph(
        "Metodología: Fit Rayo = 0.40×Rendimiento + 0.30×Cobertura plantilla + "
        "0.20×Estilo ADN Rayo + 0.10×Potencial edad. "
        "Percentiles calculados vs misma posición y liga. "
        "Datos: Transfermarkt · OPTA · SalaryLeaks (2026).",
        st["small"]))

    doc.build(story)
    pdf_bytes = buf.getvalue()
    fname = "comparativa_fichajes_rayo.pdf"
    return fname, pdf_bytes
