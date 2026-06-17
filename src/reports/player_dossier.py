"""
player_dossier.py  v3
=====================
Informe PDF moderno y profesional de un jugador.
Diseño tipo scouting report de alto nivel.
"""
from __future__ import annotations
import io
import unicodedata
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, HRFlowable, KeepTogether)
from reportlab.graphics.shapes import Drawing, Rect, String, Line
from reportlab.graphics import renderPDF
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from src.utils.config import settings
from src.profiling.player_profile import (
    career_aggregate, add_role_percentiles, profile_player_row,
    ROLE_LABELS, METRIC_LABELS)
from src.fit.player_fit import evaluate_player_fit
from src.utils.market import get_value

# ── Paleta de color ────────────────────────────────────────────────────────────
C_RED      = colors.HexColor("#E30613")
C_RED_DK   = colors.HexColor("#B0040F")
C_DARK     = colors.HexColor("#111827")
C_DARK2    = colors.HexColor("#1F2937")
C_DARK3    = colors.HexColor("#374151")
C_GREY     = colors.HexColor("#6B7280")
C_LGREY    = colors.HexColor("#9CA3AF")
C_BG       = colors.HexColor("#F8FAFC")
C_WHITE    = colors.white
C_GREEN    = colors.HexColor("#059669")
C_GREEN_BG = colors.HexColor("#ECFDF5")
C_AMBER    = colors.HexColor("#D97706")
C_AMBER_BG = colors.HexColor("#FFFBEB")
C_BLUE     = colors.HexColor("#1D4ED8")
C_BLUE_BG  = colors.HexColor("#EFF6FF")
C_CARD     = colors.HexColor("#FFFFFF")
C_BORDER   = colors.HexColor("#E5E7EB")
C_STRIPE   = colors.HexColor("#F9FAFB")

PAGE_W, PAGE_H = A4
MARGIN = 1.4 * cm
CONTENT_W = PAGE_W - 2 * MARGIN

PROC = Path(settings()["paths"]["data_processed"])

METRIC_GROUPS = {
    "Ataque": ["goals_p90", "total_shots_p90", "shots_on_target_inc_goals_p90",
               "total_touches_in_opposition_box_p90"],
    "Creacion": ["key_passes_attempt_assists_p90", "goal_assists_p90",
                 "successful_dribbles_p90", "successful_crosses_open_play_p90",
                 "through_balls_p90"],
    "Pase": ["total_successful_passes_excl_crosses_corners_p90", "forward_passes_p90",
             "successful_passes_opposition_half_p90", "successful_long_passes_p90"],
    "Defensa": ["tackles_won_p90", "total_tackles_p90", "interceptions_p90",
                "recoveries_p90", "blocks_p90", "total_clearances_p90"],
    "Duelos": ["aerial_duels_won_p90", "ground_duels_won_p90",
               "total_losses_of_possession_p90"],
}

CAREER_TOTALS = [
    ("minutes", "Minutos"), ("goals", "Goles"), ("goal_assists", "Asistencias"),
    ("total_shots", "Tiros"), ("shots_on_target_inc_goals", "Tiros a puerta"),
    ("key_passes_attempt_assists", "Pases clave"), ("successful_dribbles", "Regates"),
    ("total_touches_in_opposition_box", "Toques area rival"),
    ("tackles_won", "Entradas ganadas"), ("interceptions", "Intercepciones"),
    ("recoveries", "Recuperaciones"), ("aerial_duels_won", "Duelos aereos ganados"),
    ("total_clearances", "Despejes"),
]

SEASON_COLS = [
    ("season", "Temp."), ("team", "Equipo"), ("minutes", "Min"),
    ("goals", "G"), ("goal_assists", "A"), ("total_shots", "Tir"),
    ("shots_on_target_inc_goals", "TaP"), ("key_passes_attempt_assists", "PC"),
    ("successful_dribbles", "Reg"), ("total_touches_in_opposition_box", "ToqA"),
    ("successful_passes_opposition_half", "PaseCR"), ("forward_passes", "PaseAd"),
    ("tackles_won", "Ent"), ("interceptions", "Int"), ("recoveries", "Rec"),
    ("aerial_duels_won", "Aer"), ("total_clearances", "Desp"), ("blocks", "Blo"),
]


# ── Helpers ───────────────────────────────────────────────────────────────────
def _n(s):
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()


def _enriched():
    p = PROC / "player_seasons_enriched.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()


def _needs():
    import json
    p = PROC / "squad_profile.json"
    return json.load(open(p, encoding="utf-8")).get("needs", {}) if p.exists() else {}


def _fig_to_img(fig, w_cm, h_ratio=0.62):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=180, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return Image(buf, width=w_cm * cm, height=w_cm * h_ratio * cm)


def _est_salary(mv_eur, league="", minutes=0, age=25, position=""):
    try:
        mv = float(mv_eur or 0)
        if mv <= 0:
            return "n/d"
        ll = str(league).lower()
        if any(x in ll for x in ["primera", "laliga", "spain"]):  r = 0.15
        elif any(x in ll for x in ["segunda", "spain 2"]):        r = 0.10
        elif any(x in ll for x in ["premier", "england"]):        r = 0.18
        elif any(x in ll for x in ["bundesliga", "germany"]):     r = 0.14
        elif any(x in ll for x in ["serie a", "italy"]):          r = 0.13
        elif any(x in ll for x in ["ligue 1", "france"]):         r = 0.12
        else:                                                       r = 0.11
        sc = 0.90 if mv >= 30e6 else (0.95 if mv >= 15e6 else (1.00 if mv >= 5e6 else (1.08 if mv >= 1e6 else 1.15)))
        mins = float(minutes or 0)
        mm_ = 1.10 if mins >= 2500 else (1.05 if mins >= 1800 else (0.95 if mins >= 900 else (0.85 if mins >= 450 else 0.75)))
        am = 1.05 if 24 <= age <= 28 else (1.00 if 22 <= age <= 30 else (0.88 if age <= 21 else (0.92 if age <= 33 else 0.82)))
        pu = str(position).upper()
        pm = 1.08 if pu in ("ST","LW","RW") else (1.03 if pu in ("AM","CM") else (0.95 if pu == "GK" else 1.00))
        sal = mv * r * sc * mm_ * am * pm
        return f"~{sal/1e6:.1f}M EUR/ano" if sal >= 1e6 else f"~{sal/1e3:.0f}K EUR/ano"
    except Exception:
        return "n/d"


# ── Estilos de párrafo ─────────────────────────────────────────────────────────
def _styles():
    base = getSampleStyleSheet()
    return {
        "hero_name": ParagraphStyle("hero_name", parent=base["BodyText"],
            fontName="Helvetica-Bold", fontSize=22, textColor=C_WHITE, leading=26),
        "hero_sub": ParagraphStyle("hero_sub", parent=base["BodyText"],
            fontName="Helvetica", fontSize=10, textColor=colors.HexColor("#FCA5A5"), leading=14),
        "hero_info": ParagraphStyle("hero_info", parent=base["BodyText"],
            fontName="Helvetica", fontSize=8.5, textColor=colors.HexColor("#D1D5DB"), leading=12),
        "section": ParagraphStyle("section", parent=base["BodyText"],
            fontName="Helvetica-Bold", fontSize=10, textColor=C_DARK, leading=14,
            spaceBefore=10, spaceAfter=4),
        "kpi_label": ParagraphStyle("kpi_label", parent=base["BodyText"],
            fontName="Helvetica", fontSize=6.5, textColor=C_LGREY, leading=9),
        "kpi_value": ParagraphStyle("kpi_value", parent=base["BodyText"],
            fontName="Helvetica-Bold", fontSize=13, textColor=C_DARK, leading=16),
        "body": ParagraphStyle("body", parent=base["BodyText"],
            fontName="Helvetica", fontSize=8.5, textColor=C_DARK3, leading=13),
        "small": ParagraphStyle("small", parent=base["BodyText"],
            fontName="Helvetica", fontSize=7.5, textColor=C_GREY, leading=11),
        "italic": ParagraphStyle("italic", parent=base["BodyText"],
            fontName="Helvetica-Oblique", fontSize=7, textColor=C_LGREY, leading=11),
        "tag_green": ParagraphStyle("tag_green", parent=base["BodyText"],
            fontName="Helvetica-Bold", fontSize=7.5, textColor=C_GREEN, leading=10),
        "tag_amber": ParagraphStyle("tag_amber", parent=base["BodyText"],
            fontName="Helvetica-Bold", fontSize=7.5, textColor=C_AMBER, leading=10),
        "tag_blue": ParagraphStyle("tag_blue", parent=base["BodyText"],
            fontName="Helvetica-Bold", fontSize=7.5, textColor=C_BLUE, leading=10),
        "tbl_hd": ParagraphStyle("tbl_hd", parent=base["BodyText"],
            fontName="Helvetica-Bold", fontSize=7.5, textColor=C_WHITE, leading=10),
        "tbl_cell": ParagraphStyle("tbl_cell", parent=base["BodyText"],
            fontName="Helvetica", fontSize=7.5, textColor=C_DARK3, leading=10),
    }


# ── Sección header con borde rojo ─────────────────────────────────────────────
def _section_header(text, st):
    accent = Table([["", Paragraph(text.upper(), st["section"])]],
                   colWidths=[4, CONTENT_W - 4])
    accent.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), C_RED),
        ("BACKGROUND", (1, 0), (1, -1), colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
        ("LEFTPADDING", (1, 0), (1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return KeepTogether([Spacer(1, 6), accent, Spacer(1, 4)])


# ── Tabla con header rojo y filas alternadas ───────────────────────────────────
def _tbl(data, col_widths=None, fs=7.5, hdr_bg=None):
    hdr_bg = hdr_bg or C_DARK
    t = Table(data, repeatRows=1, colWidths=col_widths)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), hdr_bg),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), fs),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, C_STRIPE]),
        ("GRID", (0, 0), (-1, -1), 0.25, C_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    t.setStyle(TableStyle(style))
    return t


# ── Barra de percentil en PDF (Drawing nativa) ────────────────────────────────
def _pct_bar_drawing(value: float, width_pts: float = 200, height_pts: float = 10):
    """Barra de percentil con fondo gris claro y relleno coloreado."""
    d = Drawing(width_pts, height_pts)
    # Fondo
    d.add(Rect(0, 1, width_pts, height_pts - 2,
               fillColor=colors.HexColor("#E5E7EB"), strokeColor=None))
    # Relleno
    fill_w = max(2, (value / 100) * width_pts)
    if value >= 80:   fc = colors.HexColor("#059669")
    elif value >= 60: fc = colors.HexColor("#3B82F6")
    elif value >= 40: fc = colors.HexColor("#F59E0B")
    else:             fc = colors.HexColor("#EF4444")
    d.add(Rect(0, 1, fill_w, height_pts - 2, fillColor=fc, strokeColor=None))
    return d


# ── Gráfico radar mejorado ─────────────────────────────────────────────────────
def _radar_chart(role_scores: dict, pool_role_avg: dict, w_cm=9):
    items = list(role_scores.items())[:8]
    if not items:
        return None
    labs  = [k for k, _ in items]
    vals  = [float(v) for _, v in items]
    avgs  = [float(pool_role_avg.get(k, 50)) for k in labs]
    N = len(labs)
    ang = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()

    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#F8FAFC")

    # Grid rings
    for r in [25, 50, 75, 100]:
        ax.plot(ang + ang[:1], [r] * (N + 1), color="#E5E7EB", linewidth=0.8, zorder=1)

    # Líneas radiales
    for a in ang:
        ax.plot([a, a], [0, 100], color="#E5E7EB", linewidth=0.5, zorder=1)

    # Media (gris)
    av_c = avgs + avgs[:1]
    ac_c = ang + ang[:1]
    ax.fill(ac_c, av_c, color="#9CA3AF", alpha=0.12, zorder=2)
    ax.plot(ac_c, av_c, color="#9CA3AF", linewidth=1.5, linestyle="--",
            label="Media posicion", zorder=3)

    # Jugador (rojo)
    vl_c = vals + vals[:1]
    ax.fill(ac_c, vl_c, color="#E30613", alpha=0.22, zorder=4)
    ax.plot(ac_c, vl_c, color="#E30613", linewidth=2.5, label="Jugador", zorder=5)
    ax.scatter(ang, vals, color="#E30613", s=40, zorder=6)

    ax.set_xticks(ang)
    ax.set_xticklabels(labs, fontsize=7.5, fontweight="bold", color="#374151")
    ax.set_ylim(0, 100)
    ax.set_yticks([])
    ax.spines["polar"].set_visible(False)

    # Leyenda compacta
    p1 = mpatches.Patch(color="#E30613", alpha=0.8, label="Jugador")
    p2 = mpatches.Patch(color="#9CA3AF", alpha=0.6, label="Media posicion")
    ax.legend(handles=[p1, p2], loc="upper right", bbox_to_anchor=(1.38, 1.12),
              fontsize=7, framealpha=0.9, edgecolor="#E5E7EB")

    plt.tight_layout(pad=0.5)
    return _fig_to_img(fig, w_cm, 1.0)


# ── Gráfico Fit Rayo ───────────────────────────────────────────────────────────
def _fit_chart(fit: dict, prof: dict, w_cm=12):
    pot_map = {"muy alto": 95, "alto": 80, "estable": 65, "en meseta": 50, "veterania": 35}
    comps = [
        ("Compatibilidad plantilla (40%)", fit.get("compatibilidad_plantilla", 0)),
        ("Compatibilidad entrenador (25%)", fit.get("compatibilidad_entrenador", 0)),
        ("Rendimiento en rol (20%)", prof.get("primary_score") or 50),
        ("Potencial / edad (15%)", pot_map.get(prof.get("potential", ""), 55)),
    ]
    labels = [c[0] for c in comps]
    scores = [float(c[1]) for c in comps]
    bar_colors = ["#059669" if s >= 70 else ("#F59E0B" if s >= 45 else "#EF4444")
                  for s in scores]

    fig, ax = plt.subplots(figsize=(9, 2.6))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#F8FAFC")

    bars = ax.barh(labels, scores, color=bar_colors, height=0.52,
                   alpha=0.88, edgecolor="white", linewidth=0.5)
    ax.axvline(x=50, color="#D1D5DB", linewidth=1.0, linestyle="--", zorder=0)
    ax.set_xlim(0, 108)
    ax.set_xlabel("Score (0-100)", fontsize=8, color="#6B7280")
    ax.tick_params(labelsize=8, colors="#374151")
    ax.set_facecolor("#F8FAFC")
    for bar, score in zip(bars, scores):
        ax.text(min(score + 2, 104), bar.get_y() + bar.get_height() / 2,
                f"{score:.0f}", va="center", fontsize=9,
                fontweight="bold", color="#111827")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#E5E7EB")
    ax.spines["bottom"].set_color("#E5E7EB")
    fit_10 = fit.get("global_fit_10", "?")
    ax.set_title(f"Fit Rayo  {fit_10}/10", fontsize=11, color="#111827",
                 fontweight="bold", pad=8, loc="left")
    plt.tight_layout(pad=0.4)
    return _fig_to_img(fig, w_cm, 0.38)


# ── Top percentiles chart ──────────────────────────────────────────────────────
def _top_pct_chart(crow, pool, top_n=10, w_cm=12):
    all_m = []
    for grp, metrics in METRIC_GROUPS.items():
        for m in metrics:
            if m not in pool.columns:
                continue
            ser = pd.to_numeric(pool[m], errors="coerce")
            pr  = ser.rank(pct=True) * 100
            idx = pool.index[pool["name"] == crow.get("name")]
            if len(idx) == 0:
                continue
            pct = pr.get(idx[0])
            if pd.notna(pct):
                all_m.append((METRIC_LABELS.get(m, m), float(pct)))
    if not all_m:
        return None
    all_m.sort(key=lambda x: -x[1])
    top = all_m[:top_n]
    labs = [t[0] for t in top]
    vals = [t[1] for t in top]
    bar_colors = ["#059669" if v >= 80 else ("#3B82F6" if v >= 60 else
                  ("#F59E0B" if v >= 40 else "#EF4444")) for v in vals]

    fig, ax = plt.subplots(figsize=(9, max(2.5, len(top) * 0.44)))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#F8FAFC")
    bars = ax.barh(labs, vals, color=bar_colors, height=0.55,
                   alpha=0.88, edgecolor="white", linewidth=0.5)
    ax.axvline(x=50, color="#D1D5DB", linewidth=1.0, linestyle="--", zorder=0)
    ax.set_xlim(0, 110)
    ax.set_xlabel("Percentil vs posicion (0-100)", fontsize=8, color="#6B7280")
    ax.tick_params(labelsize=8, colors="#374151")
    for bar, v in zip(bars, vals):
        ax.text(min(v + 1.5, 107), bar.get_y() + bar.get_height() / 2,
                f"{v:.0f}", va="center", fontsize=9,
                fontweight="bold", color="#111827")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#E5E7EB")
    ax.spines["bottom"].set_color("#E5E7EB")
    ax.set_title(f"Top {top_n} percentiles vs jugadores de la misma posicion",
                 fontsize=9, color="#374151", pad=6, loc="left")
    plt.tight_layout(pad=0.4)
    return _fig_to_img(fig, w_cm, max(0.36, len(top) * 0.054))


# ── KPI card para la franja de KPIs ───────────────────────────────────────────
def _kpi_card(label, value, st, bg=None, fg=None, w=3.0):
    bg  = bg or C_BG
    fg  = fg or C_DARK
    lbl = Paragraph(label, st["kpi_label"])
    val = Paragraph(f'<font color="#{fg.hexval()[2:]}">{value}</font>',
                    ParagraphStyle("kv2", parent=st["kpi_value"],
                                   textColor=fg, fontSize=12))
    t = Table([[lbl], [val]], colWidths=[w * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("BOX", (0, 0), (-1, -1), 0.5, C_BORDER),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
    ]))
    return t


# ── Hero section (portada del jugador) ────────────────────────────────────────
def _build_hero(cname, crow, mv, prof, fit, foto, sal_str, st):
    """Banda oscura de portada con foto, nombre y datos clave."""
    team_s   = str(crow.get("team", ""))
    league_s = str(crow.get("league", "")).replace("_", " ")
    pos_s    = str(mv.get("position") or crow.get("position_group") or "")
    age_s    = str(int(float(mv.get("age") or 0))) if mv.get("age") else "?"
    ht_s     = str(mv.get("height") or "")
    foot_s   = str(mv.get("foot") or "")
    role_lbl = prof.get("primary_role_label", "n/d")
    style_lbl = prof.get("style_label", "n/d")

    bio_parts = []
    if age_s and age_s != "0": bio_parts.append(f"{age_s} años")
    if ht_s:   bio_parts.append(f"{ht_s} m")
    if foot_s: bio_parts.append(f"pie {foot_s}")
    if pos_s:  bio_parts.append(pos_s)
    bio_s = "  ·  ".join(bio_parts)

    # Columna de texto (nombre + datos)
    txt_col = [
        Paragraph(cname, st["hero_name"]),
        Spacer(1, 4),
        Paragraph(f"{team_s}  ·  {league_s}", st["hero_sub"]),
        Spacer(1, 6),
        Paragraph(bio_s, st["hero_info"]),
        Spacer(1, 8),
        Paragraph(
            f'<font color="#FCA5A5"><b>Rol:</b></font> '
            f'<font color="#F9FAFB">{role_lbl}</font>',
            st["hero_info"]),
        Spacer(1, 2),
        Paragraph(
            f'<font color="#FCA5A5"><b>Estilo:</b></font> '
            f'<font color="#F9FAFB">{style_lbl}</font>',
            st["hero_info"]),
    ]
    sec_roles = ", ".join(prof.get("secondary_roles_labels", [])) or "—"
    txt_col += [
        Spacer(1, 2),
        Paragraph(
            f'<font color="#9CA3AF">Roles sec.: {sec_roles}</font>',
            ParagraphStyle("hero_sec", parent=st["hero_info"],
                           fontSize=7.5, textColor=colors.HexColor("#9CA3AF"))),
    ]

    # Si hay foto, la ponemos a la izquierda; si no, solo texto
    if foto:
        hero_inner = Table([[foto, txt_col]],
                           colWidths=[3.2 * cm, CONTENT_W - 3.2 * cm - 8])
        hero_inner.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (0, -1), 12),
            ("LEFTPADDING", (1, 0), (1, -1), 0),
        ]))
    else:
        hero_inner = Table([[txt_col]], colWidths=[CONTENT_W])
        hero_inner.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

    # Wrapper con fondo oscuro
    hero = Table([[hero_inner]], colWidths=[CONTENT_W])
    hero.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_DARK),
        ("TOPPADDING", (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("ROUNDEDCORNERS", [6, 6, 6, 6]),
    ]))
    return hero


# ── Constructor principal ──────────────────────────────────────────────────────
def build_player_dossier(name, team=None):
    enr = _enriched()
    if enr.empty:
        raise ValueError("Sin datos enriquecidos")
    career = career_aggregate(enr)

    cand = career[career["name"].map(_n) == _n(name)]
    if cand.empty:
        cand = career[career["name"].map(_n).str.contains(_n(name).split()[-1], na=False)]
    if cand.empty:
        raise ValueError(f"Jugador '{name}' no encontrado")
    crow  = cand.iloc[0]
    cname = crow["name"]

    enrp  = add_role_percentiles(career)
    prow  = enrp[enrp["name"] == cname].iloc[0]
    prof  = profile_player_row(prow)
    mv    = get_value(cname)
    fit   = evaluate_player_fit(prof, _needs(), "Bloque medio / Equilibrado") if prof.get("primary_role") else {}
    pos   = prow.get("position_group")
    pool  = career[career["position_group"] == pos]

    st = _styles()

    # ── Foto ──────────────────────────────────────────────────────────────────
    foto = None
    purl = mv.get("photo_url") or (
        f"https://img.a.transfermarkt.technology/portrait/big/{mv['tm_id']}.jpg"
        if mv.get("tm_id") else None)
    if purl:
        try:
            import requests
            r = requests.get(purl, timeout=8,
                             headers={"User-Agent": "RayoScoutingTool/1.0"})
            if r.status_code == 200 and r.content:
                try:
                    from PIL import Image as _PIL
                    im = _PIL.open(io.BytesIO(r.content)).convert("RGB")
                    im.thumbnail((360, 480))
                    ob = io.BytesIO()
                    im.save(ob, format="JPEG", quality=88)
                    ob.seek(0)
                    foto = Image(ob, width=3.0 * cm, height=3.8 * cm)
                except Exception:
                    foto = Image(io.BytesIO(r.content), width=3.0 * cm, height=3.8 * cm)
        except Exception:
            foto = None

    # ── Datos de cabecera ─────────────────────────────────────────────────────
    val_s  = f"{mv['value_eur']/1e6:.1f}M EUR" if mv.get("value_eur") else "n/d"
    con_s  = str(mv.get("contract_until", ""))[:10] or "n/d"
    age_v  = int(float(mv.get("age") or 0))
    mins_v = float(crow.get("minutes") or 0)
    league_s = str(crow.get("league", "")).replace("_", " ")
    pos_s  = str(mv.get("position") or pos or "")
    sal_s  = _est_salary(mv.get("value_eur", 0), league_s, mins_v, age_v, pos_s)
    fit_s  = f"{fit['global_fit_10']}/10" if fit else "n/d"
    fit_v  = fit.get("global_fit", 0) if fit else 0

    # Colores del fit score
    if fit_v >= 65:   fit_bg, fit_fg = C_GREEN_BG, C_GREEN
    elif fit_v >= 45: fit_bg, fit_fg = C_AMBER_BG, C_AMBER
    else:             fit_bg, fit_fg = colors.HexColor("#FFF1F2"), colors.HexColor("#9F1239")

    story = []

    # ── Banda de cabecera institucional ──────────────────────────────────────
    hdr_l = Paragraph(
        '<font color="white"><b>RAYO VALLECANO — INFORME DE SCOUTING</b></font>',
        ParagraphStyle("hl", parent=st["body"], textColor=C_WHITE,
                       fontSize=8.5, fontName="Helvetica-Bold"))
    hdr_r = Paragraph(
        f'<font color="#FCA5A5">{date.today().strftime("%d %b %Y").lstrip("0")}</font>',
        ParagraphStyle("hr", parent=st["body"], textColor=colors.HexColor("#FCA5A5"),
                       fontSize=8, alignment=2))
    hdr = Table([[hdr_l, hdr_r]], colWidths=[CONTENT_W * 0.65, CONTENT_W * 0.35])
    hdr.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_RED),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 8))

    # ── Hero oscuro ───────────────────────────────────────────────────────────
    hero = _build_hero(cname, crow, mv, prof, fit, foto, sal_s, st)
    story.append(hero)
    story.append(Spacer(1, 10))

    # ── KPI strip ─────────────────────────────────────────────────────────────
    kpi_w = CONTENT_W / 5
    kpis = Table([[
        _kpi_card("FIT RAYO", fit_s, st, bg=fit_bg, fg=fit_fg, w=kpi_w / cm),
        _kpi_card("VALOR TM", val_s, st, w=kpi_w / cm),
        _kpi_card("SALARIO EST.", sal_s, st, w=kpi_w / cm),
        _kpi_card("CONTRATO", con_s, st, w=kpi_w / cm),
        _kpi_card("MINUTOS HIST.", f"{int(mins_v):,}".replace(",", "."), st, w=kpi_w / cm),
    ]], colWidths=[kpi_w] * 5)
    kpis.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(kpis)
    story.append(Spacer(1, 10))

    # ── Fortalezas / Debilidades ─────────────────────────────────────────────
    if prof.get("strengths") or prof.get("weaknesses"):
        fw_rows = []
        if prof.get("strengths"):
            fw_rows.append([
                Paragraph("● FORTALEZAS", st["tag_green"]),
                Paragraph(";  ".join(prof["strengths"]), st["small"]),
            ])
        if prof.get("weaknesses"):
            fw_rows.append([
                Paragraph("● DEBILIDADES", st["tag_amber"]),
                Paragraph(";  ".join(prof["weaknesses"]), st["small"]),
            ])
        fw_t = Table(fw_rows, colWidths=[3.0 * cm, CONTENT_W - 3.0 * cm])
        fw_t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), C_BG),
            ("BOX", (0, 0), (-1, -1), 0.5, C_BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, C_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(fw_t)
        story.append(Spacer(1, 8))

    # ── Fit Rayo ──────────────────────────────────────────────────────────────
    if fit:
        story.append(_section_header("Fit Rayo — Encaje con el club", st))

        # Gráfico de barras
        fc = _fit_chart(fit, prof, w_cm=CONTENT_W / cm)
        if fc:
            story.append(fc)
            story.append(Spacer(1, 6))

        # Tabla de desglose
        pot_map = {"muy alto": 95, "alto": 80, "estable": 65, "en meseta": 50, "veterania": 35}
        pot_s = pot_map.get(prof.get("potential", ""), 55)
        bd = [
            ["Componente", "Peso", "Score", "Contribucion"],
            ["Compatibilidad plantilla", "40%",
             str(int(fit.get("compatibilidad_plantilla", 0))),
             f"{fit.get('compatibilidad_plantilla', 0) * 0.40:.1f}"],
            ["Compatibilidad entrenador", "25%",
             str(int(fit.get("compatibilidad_entrenador", 0))),
             f"{fit.get('compatibilidad_entrenador', 0) * 0.25:.1f}"],
            ["Rendimiento en rol", "20%",
             str(int(prof.get("primary_score") or 50)),
             f"{(prof.get('primary_score') or 50) * 0.20:.1f}"],
            ["Potencial / edad", "15%", str(pot_s), f"{pot_s * 0.15:.1f}"],
            ["TOTAL FIT RAYO", "100%", "—", f"{fit.get('global_fit', 0):.1f}"],
        ]
        story.append(_tbl(bd, col_widths=[8.5 * cm, 1.8 * cm, 2.5 * cm, 2.5 * cm], fs=8))
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            "Formula: Fit = (Plantilla×0.40) + (Entrenador×0.25) + (Rol×0.20) + "
            "(Potencial×0.15)  →  /100 expresado también como /10. "
            "Potencial: muy alto=95, alto=80, estable=65, en meseta=50, veterania=35.",
            st["italic"]))

    # ── Estimacion salarial ───────────────────────────────────────────────────
    story.append(_section_header("Estimacion salarial bruta anual", st))
    sal_detail = Table([[
        Paragraph(f'<b>Estimacion:</b>', st["body"]),
        Paragraph(f'<font color="#E30613"><b>{sal_s}</b></font>', st["body"]),
        Paragraph(f"VM: {val_s}  ·  Liga: {league_s}  ·  Edad: {age_v}  ·  "
                  f"Pos: {pos_s}  ·  Min: {int(mins_v):,}".replace(",", "."),
                  st["small"]),
    ]], colWidths=[2.8 * cm, 3.0 * cm, CONTENT_W - 5.8 * cm])
    sal_detail.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, C_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(sal_detail)
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Modelo multi-factor: Salario = VM × ratio_liga × escala_VM × mult_min × mult_edad × mult_pos. "
        "Ratio liga: 0.10 (2ª div) → 0.18 (Premier). Referencia titular LaLiga = ~12–18% del VM bruto.",
        st["italic"]))

    # ── Radar + Totales de carrera + Top percentiles (flujo natural) ─────────

    # Calcular medias del pool para el radar
    try:
        pool_profiles = [profile_player_row(r) for _, r in
                         add_role_percentiles(pool).iterrows()
                         if r.get("name") != cname]
        pool_role_avg = {}
        for rp in pool_profiles:
            for k, v in (rp.get("role_scores") or {}).items():
                pool_role_avg.setdefault(k, []).append(float(v))
        pool_role_avg = {k: sum(vs) / len(vs) for k, vs in pool_role_avg.items()}
    except Exception:
        pool_role_avg = {}

    # Layout 2 columnas: radar izquierda | totales de carrera derecha
    radar_img = _radar_chart(prof.get("role_scores", {}), pool_role_avg, w_cm=8.5)

    # Tabla de totales de carrera (derecha)
    mins_tot = float(crow.get("minutes") or 0) or 1
    tot = [["Métrica", "Total", "Por 90'"]]
    for col, lab in CAREER_TOTALS:
        if col in crow.index and pd.notna(crow.get(col)):
            v = float(crow[col])
            p90 = "" if col == "minutes" else f"{v / mins_tot * 90:.2f}"
            tot.append([lab, str(int(v)), p90])
    tot_tbl = _tbl(tot, col_widths=[5.5 * cm, 2.2 * cm, 2.2 * cm], fs=7.5)

    # Radar + Totales en 2 columnas (usando tablas anidadas simples, sin KeepTogether)
    story.append(_section_header("Perfil de rol (radar)", st))

    # Tabla de scores de rol
    rs_data = [["Rol", "Score"]]
    for k, v in list(prof.get("role_scores", {}).items())[:6]:
        rs_data.append([ROLE_LABELS.get(k, k), str(int(v))])
    rs_tbl = _tbl(rs_data, col_widths=[6.5 * cm, 2.2 * cm], fs=7.5)

    L_W = 9.2 * cm
    R_W = CONTENT_W - L_W - 0.4 * cm

    # Celdas con flowables válidos (Image y Table, sin KeepTogether)
    left_cell  = [radar_img, Spacer(1, 6), rs_tbl] if radar_img else [rs_tbl]
    right_hdr  = Paragraph(
        "TOTALES DE CARRERA",
        ParagraphStyle("th2", fontName="Helvetica-Bold", fontSize=9,
                       textColor=C_DARK, leading=12))
    right_cell = [right_hdr, Spacer(1, 6), tot_tbl]

    two_col = Table([[left_cell, right_cell]],
                    colWidths=[L_W, CONTENT_W - L_W])
    two_col.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (1, 0), (1, -1), 10),
    ]))
    story.append(two_col)
    story.append(Spacer(1, 12))

    # ── Top percentiles ───────────────────────────────────────────────────────
    story.append(_section_header("Mejores percentiles vs posicion", st))
    tpc = _top_pct_chart(crow, pool, top_n=10, w_cm=CONTENT_W / cm)
    if tpc:
        story.append(tpc)
        story.append(Paragraph(
            "Verde ≥80 · Azul ≥60 · Ambar ≥40 · Rojo <40. "
            "Comparacion vs jugadores de la misma posicion en el scope OPTA.",
            st["italic"]))

    # ── Percentiles por grupo + tabla de temporadas ────────────────────────────
    story.append(Spacer(1, 12))
    story.append(_section_header("Percentiles por metrica (historico vs posicion)", st))
    story.append(Paragraph(
        "Percentil dentro del grupo de jugadores de la misma posicion. "
        "Valor/90 calculado sobre el total de minutos historicos.",
        st["italic"]))
    story.append(Spacer(1, 6))

    def pct_of(metric):
        if metric not in pool.columns:
            return None
        ser = pd.to_numeric(pool[metric], errors="coerce")
        pr  = ser.rank(pct=True) * 100
        idx = pool.index[pool["name"] == cname]
        return float(pr.get(idx[0])) if len(idx) and pd.notna(pr.get(idx[0])) else None

    def _interp(pc):
        if pc >= 80: return "Elite"
        if pc >= 60: return "Bueno"
        if pc >= 40: return "Medio"
        return "Bajo"

    def _interp_color(pc):
        if pc >= 80: return colors.HexColor("#059669")
        if pc >= 60: return colors.HexColor("#3B82F6")
        if pc >= 40: return colors.HexColor("#F59E0B")
        return colors.HexColor("#EF4444")

    # Tablas de métricas — una tabla por grupo, apiladas secuencialmente
    # Col widths: metrica | val/90 | pct | nivel
    CW_M = [5.5 * cm, 1.8 * cm, 1.4 * cm, 1.8 * cm]
    for grp, metrics in METRIC_GROUPS.items():
        rows = [[grp, "Val/90", "Pct", "Nivel"]]
        data_rows = []
        for m in metrics:
            pc = pct_of(m)
            v90 = ""
            if m in crow.index and pd.notna(crow.get(m)):
                v90 = f"{float(crow[m]):.2f}"
            if pc is not None:
                data_rows.append((METRIC_LABELS.get(m, m), v90, str(int(pc)),
                                   _interp(pc), pc))
        if not data_rows:
            continue
        for (lab, v90, pct_s, nivel, pc_v) in data_rows:
            rows.append([lab, v90, pct_s, nivel])
        t = Table(rows, colWidths=CW_M)
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), C_DARK2),
            ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, C_STRIPE]),
            ("GRID", (0, 0), (-1, -1), 0.25, C_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        for i, (_, _, _, _, pc_v) in enumerate(data_rows, start=1):
            style.append(("TEXTCOLOR", (3, i), (3, i), _interp_color(pc_v)))
            style.append(("FONTNAME", (3, i), (3, i), "Helvetica-Bold"))
        t.setStyle(TableStyle(style))
        story.append(t)
        story.append(Spacer(1, 5))

    # ── Estadisticas por temporada ─────────────────────────────────────────────
    story.append(Spacer(1, 10))
    story.append(_section_header("Estadisticas por temporada (OPTA)", st))
    prows = enr[enr["name"] == cname].copy()
    order = {"2025-2026": 6, "2025": 5, "2024-2025": 4, "2023-2024": 3,
             "2022-2023": 2, "2021-2022": 1}
    prows["_o"] = prows["season"].map(order).fillna(0)
    prows = prows.sort_values("_o", ascending=False)
    cols  = [(c, lbl) for c, lbl in SEASON_COLS if c in prows.columns]
    tdata = [[lbl for _, lbl in cols]]
    for _, rw in prows.iterrows():
        row = []
        for c, _lbl in cols:
            v = rw.get(c)
            if c == "minutes" and pd.notna(v):   v = int(v)
            elif isinstance(v, float) and pd.notna(v) and c != "season": v = int(v)
            row.append("" if pd.isna(v) else str(v))
        tdata.append(row)
    story.append(_tbl(tdata, fs=6.5))

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 12))
    footer_line = Table([["", ""]], colWidths=[CONTENT_W * 0.7, CONTENT_W * 0.3])
    footer_line.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, 0), 0.5, C_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(footer_line)
    story.append(Paragraph(
        f"Generado el {date.today().strftime('%d %b %Y').lstrip('0')}  ·  "
        f"Rayo Vallecano — Direccion Deportiva  ·  "
        f"Datos OPTA ({prof.get('seasons_played','?')} temporadas) + Transfermarkt.  "
        f"Percentiles vs jugadores de la misma posicion en el scope disponible.",
        st["italic"]))

    # ── Build ─────────────────────────────────────────────────────────────────
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=MARGIN, bottomMargin=MARGIN,
        leftMargin=MARGIN, rightMargin=MARGIN,
    )
    doc.build(story)
    buf.seek(0)
    return f"informe_{_n(cname).replace(' ', '_')}.pdf", buf.read()
