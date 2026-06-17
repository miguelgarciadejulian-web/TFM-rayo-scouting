"""
player_dossier.py
=================
Informe PDF COMPLETO de un jugador: portada profesional, foto, bio Transfermarkt,
perfil del HISTORICO, totales de carrera, Fit Rayo (con formula y pesos), salario
estimado, radar de roles, percentiles de TODAS las metricas y estadisticas por
temporada (OPTA). Transparencia absoluta de calculos.
"""
from __future__ import annotations
import io
import unicodedata
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak)

from src.utils.config import settings
from src.profiling.player_profile import (
    career_aggregate, add_role_percentiles, profile_player_row, ROLE_LABELS, METRIC_LABELS)
from src.fit.player_fit import evaluate_player_fit
from src.utils.market import get_value

# ── Colores ──────────────────────────────────────────────────────────────────
RAYO_RED   = colors.HexColor("#E30613")
RAYO_DARK  = colors.HexColor("#1A1A2E")
C_GREEN    = colors.HexColor("#166534")
C_AMBER    = colors.HexColor("#92400E")
C_LIGHT    = colors.HexColor("#FFF8F8")
C_BORDER   = colors.HexColor("#FECACA")
C_GREY_BG  = colors.HexColor("#FAFAFA")
C_GREY_LN  = colors.HexColor("#E5E7EB")

PROC = Path(settings()["paths"]["data_processed"])

# ── Grupos de metricas p90 ────────────────────────────────────────────────────
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
    "Duelos / perdidas": ["aerial_duels_won_p90", "ground_duels_won_p90",
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


# ── Helpers generales ─────────────────────────────────────────────────────────
def _n(s):
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()


def _enriched():
    p = PROC / "player_seasons_enriched.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()


def _needs():
    import json
    p = PROC / "squad_profile.json"
    return json.load(open(p, encoding="utf-8")).get("needs", {}) if p.exists() else {}


def _fig_img(fig, w_cm=15):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return Image(buf, width=w_cm * cm, height=(w_cm * 0.6) * cm)


# ── Estimacion salarial (modelo multi-factor) ─────────────────────────────────
def _est_salary(market_value_eur, league: str = "", minutes: float = 0,
                age: int = 25, position: str = "") -> str:
    """
    Estimacion salarial bruta anual.
    Factores: liga (35%) + VM (25%) + minutos (20%) + edad (10%) + posicion (10%).
    """
    try:
        mv = float(market_value_eur or 0)
        if mv <= 0:
            return "n/d"

        league_l = str(league).lower()
        if any(x in league_l for x in ["primera", "laliga", "la liga", "spain"]):
            base_ratio = 0.15
        elif any(x in league_l for x in ["segunda", "segunda division", "spain 2"]):
            base_ratio = 0.10
        elif any(x in league_l for x in ["premier", "england"]):
            base_ratio = 0.18
        elif any(x in league_l for x in ["bundesliga", "germany"]):
            base_ratio = 0.14
        elif any(x in league_l for x in ["serie a", "italy"]):
            base_ratio = 0.13
        elif any(x in league_l for x in ["ligue 1", "france"]):
            base_ratio = 0.12
        else:
            base_ratio = 0.11

        if mv >= 30_000_000:
            scale = 0.90
        elif mv >= 15_000_000:
            scale = 0.95
        elif mv >= 5_000_000:
            scale = 1.00
        elif mv >= 1_000_000:
            scale = 1.08
        else:
            scale = 1.15

        mins = float(minutes or 0)
        if mins >= 2500:
            min_mult = 1.10
        elif mins >= 1800:
            min_mult = 1.05
        elif mins >= 900:
            min_mult = 0.95
        elif mins >= 450:
            min_mult = 0.85
        else:
            min_mult = 0.75

        if 24 <= age <= 28:
            age_mult = 1.05
        elif 22 <= age <= 23 or 29 <= age <= 30:
            age_mult = 1.00
        elif age <= 21:
            age_mult = 0.88
        elif 31 <= age <= 33:
            age_mult = 0.92
        else:
            age_mult = 0.82

        pos_u = str(position).upper()
        if pos_u in ("ST", "LW", "RW"):
            pos_mult = 1.08
        elif pos_u in ("AM", "CM"):
            pos_mult = 1.03
        elif pos_u in ("GK",):
            pos_mult = 0.95
        else:
            pos_mult = 1.00

        sal = mv * base_ratio * scale * min_mult * age_mult * pos_mult
        return f"~{sal / 1e6:.1f}M EUR/ano" if sal >= 1_000_000 else f"~{sal / 1e3:.0f}K EUR/ano"
    except (TypeError, ValueError):
        return "n/d"


# ── Graficos ──────────────────────────────────────────────────────────────────
def _radar(role_scores):
    items = list(role_scores.items())[:8]
    if not items:
        return None
    labs = [k for k, _ in items]
    vals = [v for _, v in items]
    ang = np.linspace(0, 2 * np.pi, len(labs), endpoint=False).tolist()
    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
    ax.set_facecolor("#FFF8F8")
    fig.patch.set_facecolor("white")
    ax.plot(ang + ang[:1], vals + vals[:1], color="#E30613", linewidth=2.5)
    ax.fill(ang + ang[:1], vals + vals[:1], color="#E30613", alpha=0.20)
    ax.set_xticks(ang)
    ax.set_xticklabels(labs, fontsize=8)
    ax.set_ylim(0, 100)
    ax.set_yticks([25, 50, 75])
    ax.set_yticklabels(["25", "50", "75"], fontsize=6, color="#9CA3AF")
    ax.grid(color="#E5E7EB", linewidth=0.7)
    return _fig_img(fig, 10)


def _fit_breakdown_chart(fit, prof):
    """Barras horizontales: 4 componentes del Fit Rayo con sus pesos."""
    pot_map = {"muy alto": 95, "alto": 80, "estable": 65, "en meseta": 50, "veterania": 35}
    components = [
        ("Compatibilidad plantilla", fit.get("compatibilidad_plantilla", 0), 0.40),
        ("Compatibilidad entrenador", fit.get("compatibilidad_entrenador", 0), 0.25),
        ("Rendimiento en rol", prof.get("primary_score") or 50, 0.20),
        ("Potencial / edad", pot_map.get(prof.get("potential", ""), 55), 0.15),
    ]
    labels = [f"{c[0]}  ({int(c[2]*100)}%)" for c in components]
    scores = [float(c[1]) for c in components]
    colors_bar = ["#E30613" if s >= 70 else ("#F59E0B" if s >= 45 else "#9CA3AF")
                  for s in scores]
    fig, ax = plt.subplots(figsize=(8, 2.8))
    ax.set_facecolor("#FAFAFA")
    fig.patch.set_facecolor("white")
    bars = ax.barh(labels, scores, color=colors_bar, height=0.5, alpha=0.85)
    ax.axvline(x=50, color="#E5E7EB", linewidth=1, linestyle="--")
    ax.set_xlim(0, 100)
    ax.set_xlabel("Score (0-100)", fontsize=8, color="#6B7280")
    ax.tick_params(labelsize=8)
    for bar, score in zip(bars, scores):
        ax.text(min(score + 2, 96), bar.get_y() + bar.get_height() / 2,
                f"{score:.0f}", va="center", fontsize=8, fontweight="bold", color="#374151")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fit_10 = fit.get("global_fit_10", "?")
    fit_100 = fit.get("global_fit", 0)
    ax.set_title(f"Fit Rayo  {fit_10}/10  ({fit_100:.0f}/100)",
                 fontsize=10, color="#E30613", fontweight="bold", pad=8)
    plt.tight_layout()
    return _fig_img(fig, 14)


def _top_percentiles_chart(crow, pool, top_n=10):
    """Barras horizontales: top percentiles vs grupo posicional."""
    all_metrics = []
    for grp, metrics in METRIC_GROUPS.items():
        for m in metrics:
            if m not in pool.columns:
                continue
            ser = pd.to_numeric(pool[m], errors="coerce")
            pr = ser.rank(pct=True) * 100
            idx = pool.index[pool["name"] == crow.get("name")]
            if len(idx) == 0:
                continue
            pct = pr.get(idx[0])
            if pd.notna(pct):
                all_metrics.append((METRIC_LABELS.get(m, m), float(pct), grp))
    if not all_metrics:
        return None
    all_metrics.sort(key=lambda x: -x[1])
    top = all_metrics[:top_n]
    labels = [t[0] for t in top]
    values = [t[1] for t in top]
    cmap = ["#166534" if v >= 80 else ("#E30613" if v >= 60 else
            ("#F59E0B" if v >= 40 else "#9CA3AF")) for v in values]
    fig, ax = plt.subplots(figsize=(8, max(2.5, len(top) * 0.42)))
    ax.set_facecolor("#FAFAFA")
    fig.patch.set_facecolor("white")
    bars = ax.barh(labels, values, color=cmap, height=0.55, alpha=0.85)
    ax.axvline(x=50, color="#E5E7EB", linewidth=1, linestyle="--")
    ax.set_xlim(0, 105)
    ax.set_xlabel("Percentil vs posicion (0-100)", fontsize=8, color="#6B7280")
    ax.tick_params(labelsize=8)
    for bar, v in zip(bars, values):
        ax.text(min(v + 1.5, 102), bar.get_y() + bar.get_height() / 2,
                f"{v:.0f}", va="center", fontsize=8, fontweight="bold", color="#374151")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_title(f"Top {top_n} percentiles vs jugadores de la misma posicion",
                 fontsize=9, color="#374151", pad=6)
    plt.tight_layout()
    return _fig_img(fig, 14)


# ── Helpers de tabla ──────────────────────────────────────────────────────────
def _tbl(data, head_bg=RAYO_RED, col_widths=None, fs=7):
    t = Table(data, repeatRows=1, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), head_bg),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), fs),
        ("GRID", (0, 0), (-1, -1), 0.3, C_GREY_LN),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, C_GREY_BG]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _kpi_tbl(rows, col_widths=None):
    """Tabla de KPIs con fondo claro."""
    t = Table(rows, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_LIGHT),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.3, C_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


# ── Constructor principal ─────────────────────────────────────────────────────
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
    crow = cand.iloc[0]
    cname = crow["name"]

    enrp = add_role_percentiles(career)
    prow = enrp[enrp["name"] == cname].iloc[0]
    prof = profile_player_row(prow)
    mv = get_value(cname)
    fit = evaluate_player_fit(prof, _needs(), "Bloque medio / Equilibrado") if prof.get("primary_role") else None
    pos = prow.get("position_group")
    pool = career[career["position_group"] == pos]

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], textColor=colors.white,
                        fontSize=20, spaceBefore=0, spaceAfter=0)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], textColor=RAYO_RED,
                        fontSize=11, spaceBefore=10, spaceAfter=2)
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=9, leading=13)
    small = ParagraphStyle("small", parent=styles["BodyText"], fontSize=7.5,
                           textColor=colors.HexColor("#6B7280"), leading=11)
    italic = ParagraphStyle("italic", parent=styles["BodyText"], fontSize=7.5,
                            textColor=colors.HexColor("#9CA3AF"), leading=11,
                            fontName="Helvetica-Oblique")
    formula = ParagraphStyle("formula", parent=styles["BodyText"], fontSize=8,
                             textColor=RAYO_DARK, leading=12, backColor=C_LIGHT,
                             borderPad=4, leftIndent=10, rightIndent=10)
    story = []

    # ── Banda roja de portada ─────────────────────────────────────────────────
    header_text = Paragraph(
        f"<font color='white'><b>RAYO VALLECANO  —  DIRECCION DEPORTIVA</b></font>",
        ParagraphStyle("hdr", parent=styles["BodyText"], fontSize=9,
                       textColor=colors.white, leading=12))
    header_date = Paragraph(
        f"<font color='white'>{date.today().strftime('%d %b %Y').lstrip('0')}</font>",
        ParagraphStyle("hdr_r", parent=styles["BodyText"], fontSize=9,
                       textColor=colors.white, leading=12, alignment=2))
    hdr_row = Table([[header_text, header_date]],
                    colWidths=[11 * cm, 5.5 * cm])
    hdr_row.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), RAYO_RED),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(hdr_row)
    story.append(Spacer(1, 8))

    # ── Foto + bloque bio ─────────────────────────────────────────────────────
    foto = ""
    purl = mv.get("photo_url") or (
        f"https://img.a.transfermarkt.technology/portrait/big/{mv['tm_id']}.jpg"
        if mv.get("tm_id") else None)
    if purl:
        try:
            import requests
            r = requests.get(purl, timeout=8, headers={"User-Agent": "RayoScoutingTool/1.0"})
            if r.status_code == 200 and r.content:
                try:
                    from PIL import Image as _PIL
                    im = _PIL.open(io.BytesIO(r.content)).convert("RGB")
                    im.thumbnail((420, 540))
                    ob = io.BytesIO()
                    im.save(ob, format="JPEG", quality=82)
                    ob.seek(0)
                    foto = Image(ob, width=3.2 * cm, height=4 * cm)
                except Exception:
                    foto = Image(io.BytesIO(r.content), width=3.2 * cm, height=4 * cm)
        except Exception:
            foto = ""

    val_str   = f"{mv['value_eur']/1e6:.1f}M EUR" if mv.get("value_eur") else "n/d"
    con_str   = str(mv["contract_until"])[:10] if mv.get("contract_until") else "n/d"
    age_val   = int(float(mv.get("age") or 0))
    mins_val  = float(crow.get("minutes") or 0)
    league_s  = str(crow.get("league", "")).replace("_", " ")
    pos_s     = str(mv.get("position") or pos or "")
    sal_str   = _est_salary(mv.get("value_eur", 0), league=str(crow.get("league", "")),
                            minutes=mins_val, age=age_val, position=pos_s)
    fit_str   = f"{fit['global_fit_10']}/10" if fit else "n/d"

    bio_bits = []
    if mv.get("age"):
        bio_bits.append(f"{mv['age']} anos")
    if mv.get("height"):
        bio_bits.append(f"{mv['height']} m")
    if mv.get("foot"):
        bio_bits.append(f"pie {mv['foot']}")

    # Columna izquierda: nombre + datos basicos
    name_para = Paragraph(
        f"<b>{cname}</b>",
        ParagraphStyle("nm", parent=styles["BodyText"], fontSize=15,
                       textColor=RAYO_DARK, leading=18, fontName="Helvetica-Bold"))
    team_para = Paragraph(
        f"{crow.get('team', '')}  ·  {league_s}",
        ParagraphStyle("tm", parent=styles["BodyText"], fontSize=9, textColor=RAYO_RED,
                       leading=12))
    bio_para = Paragraph(
        "  ·  ".join(bio_bits) + f"  ·  {pos_s}" if bio_bits else pos_s,
        small)
    role_para = Paragraph(
        f"<b>Rol principal:</b>  {prof.get('primary_role_label', 'n/d')}  "
        f"|  <b>Estilo:</b>  {prof.get('style_label', 'n/d')}",
        body)
    sec_roles = ", ".join(prof.get("secondary_roles_labels", [])) or "—"
    sec_para = Paragraph(f"<b>Roles secundarios:</b>  {sec_roles}", small)
    conf_pot = Paragraph(
        f"<b>Temporadas:</b>  {prof.get('seasons_played', '?')}  "
        f"|  <b>Confianza:</b>  {prof.get('confidence', 'n/d')}  "
        f"|  <b>Potencial:</b>  {prof.get('potential', 'n/d')}  "
        f"|  <b>Riesgo:</b>  {prof.get('risk_level', 'n/d')}",
        small)

    left_col = [name_para, Spacer(1, 3), team_para, Spacer(1, 3),
                bio_para, Spacer(1, 5), role_para, Spacer(1, 2), sec_para,
                Spacer(1, 2), conf_pot]

    # Columna derecha: KPIs en tabla
    fit_color = "#166534" if (fit and fit.get("global_fit", 0) >= 65) else \
                ("#92400E" if (fit and fit.get("global_fit", 0) >= 45) else "#9F1239")
    kpi_data = [
        ["Valor Transfermarkt",   val_str],
        ["Contrato hasta",        con_str],
        ["Fit Rayo",              fit_str],
        ["Salario estimado",      sal_str],
        ["Min. (historico)",      f"{int(mins_val):,}".replace(",", ".")],
    ]
    kpi_t = _kpi_tbl(kpi_data, col_widths=[4 * cm, 3.5 * cm])

    # Tabla principal de portada: foto | info | KPIs
    if foto:
        cw = [3.4 * cm, 7.5 * cm, 5.5 * cm]
        main_row = [[foto, left_col, kpi_t]]
    else:
        cw = [11 * cm, 5.5 * cm]
        main_row = [[left_col, kpi_t]]

    mt = Table([main_row], colWidths=cw)
    mt.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(mt)
    story.append(Spacer(1, 6))

    # Fortalezas / debilidades inline
    if prof.get("strengths") or prof.get("weaknesses"):
        fw_data = []
        if prof.get("strengths"):
            fw_data.append([
                Paragraph("<b>Fortalezas</b>", ParagraphStyle("fw", parent=styles["BodyText"],
                          fontSize=8, textColor=C_GREEN, fontName="Helvetica-Bold")),
                Paragraph("; ".join(prof["strengths"]), small),
            ])
        if prof.get("weaknesses"):
            fw_data.append([
                Paragraph("<b>Debilidades</b>", ParagraphStyle("fw2", parent=styles["BodyText"],
                          fontSize=8, textColor=C_AMBER, fontName="Helvetica-Bold")),
                Paragraph("; ".join(prof["weaknesses"]), small),
            ])
        if fw_data:
            fw_t = Table(fw_data, colWidths=[2.8 * cm, 13.5 * cm])
            fw_t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), C_LIGHT),
                ("GRID", (0, 0), (-1, -1), 0.3, C_BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.append(fw_t)
    story.append(Spacer(1, 4))

    # ── Fit Rayo con formula ──────────────────────────────────────────────────
    if fit:
        story.append(Paragraph("Fit Rayo — Encaje con el club", h2))
        story.append(Paragraph(
            f"<b>Score global:</b>  {fit['global_fit_10']}/10  "
            f"({fit.get('global_fit', 0):.0f}/100)  —  "
            f"{fit.get('compatibilidad_plantilla_txt', '')}",
            body))
        story.append(Spacer(1, 4))

        # Grafico de barras del Fit
        fc = _fit_breakdown_chart(fit, prof)
        if fc:
            story.append(fc)
            story.append(Spacer(1, 4))

        # Tabla de desglose
        pot_map = {"muy alto": 95, "alto": 80, "estable": 65, "en meseta": 50, "veterania": 35}
        pot_score = pot_map.get(prof.get("potential", ""), 55)
        breakdown_data = [
            ["Componente", "Peso", "Score (0-100)", "Contribucion"],
            ["Compatibilidad plantilla", "40%",
             str(int(fit["compatibilidad_plantilla"])),
             str(round(fit["compatibilidad_plantilla"] * 0.40, 1))],
            ["Compatibilidad entrenador", "25%",
             str(int(fit["compatibilidad_entrenador"])),
             str(round(fit["compatibilidad_entrenador"] * 0.25, 1))],
            ["Rendimiento en rol", "20%",
             str(int(prof.get("primary_score") or 50)),
             str(round((prof.get("primary_score") or 50) * 0.20, 1))],
            ["Potencial / edad", "15%",
             str(pot_score),
             str(round(pot_score * 0.15, 1))],
            ["TOTAL FIT RAYO", "100%", "—",
             str(round(fit.get("global_fit", 0), 1))],
        ]
        story.append(_tbl(breakdown_data,
                         col_widths=[7 * cm, 1.8 * cm, 3 * cm, 2.5 * cm], fs=8))

        story.append(Spacer(1, 4))
        story.append(Paragraph(
            "Formula:  Fit = (Compat_plantilla x 0.40) + (Compat_entrenador x 0.25) "
            "+ (Rol x 0.20) + (Potencial x 0.15)  ->  resultado /100, expresado tambien "
            "como /10.  Compat_plantilla: distancia entre el perfil del jugador y las "
            "necesidades detectadas en la plantilla.  Compat_entrenador: similitud de "
            "estilo del jugador con el esquema tatico del staff.  Rol: percentil de "
            "rendimiento historico en su rol principal.  Potencial: valor codificado "
            "segun categoria (muy alto=95, alto=80, estable=65, en meseta=50, veterania=35).",
            italic))

    # ── Estimacion salarial ───────────────────────────────────────────────────
    story.append(Paragraph("Estimacion salarial bruta anual", h2))
    story.append(Paragraph(
        f"<b>Estimacion:</b>  {sal_str}  "
        f"(VM: {val_str}  ·  Liga: {league_s}  ·  Edad: {age_val}  ·  "
        f"Pos: {pos_s}  ·  Min. historicos: {int(mins_val):,}".replace(",", ".") + ")",
        body))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Metodologia salarial (modelo multi-factor):  "
        "Salario = VM x ratio_liga x escala_VM x mult_minutos x mult_edad x mult_posicion.  "
        "Ratio liga: 0.10 (Segunda) a 0.18 (Premier).  "
        "Escala VM: 1.15 (<1M) a 0.90 (>30M) — jugadores de alto valor tienen ratio menor.  "
        "Minutos: 0.75 (< 450 min) a 1.10 (> 2500 min titular indiscutible).  "
        "Edad: 0.82 (>33) a 1.05 (pico 24-28 anos).  "
        "Posicion: ST/LW/RW +8%, AM/CM +3%, GK -5%.  "
        "Referencia: titular LaLiga1 = ~12-18% del VM bruto/ano.",
        italic))

    # ── Totales de carrera ────────────────────────────────────────────────────
    story.append(Paragraph("Totales de carrera (historico disponible)", h2))
    story.append(Paragraph(
        "Suma de todas las temporadas en el scope de datos OPTA. Por-90 calculado "
        "sobre el total de minutos del historico.", italic))
    tot = [["Metrica", "Total bruto", "Por 90 min"]]
    mins_total = float(crow.get("minutes") or 0) or 1
    for col, lab in CAREER_TOTALS:
        if col in crow.index and pd.notna(crow.get(col)):
            v = float(crow[col])
            p90 = "" if col == "minutes" else f"{v / mins_total * 90:.2f}"
            tot.append([lab, str(int(v)), p90])
    story.append(_tbl(tot, col_widths=[7.5 * cm, 3 * cm, 3 * cm], fs=8))

    # ── Perfil de rol ─────────────────────────────────────────────────────────
    story.append(Paragraph("Perfil de rol (radar)", h2))
    story.append(Paragraph(
        "Cada eje es el percentil del jugador en las metricas clave de ese rol, "
        "vs jugadores de su posicion en el scope de datos. 100 = mejor del scope.", italic))
    radar = _radar(prof.get("role_scores", {}))
    if radar:
        story.append(radar)
    rs = [["Rol", "Score 0-100", "Descripcion"]]
    role_descs = {
        "goleador": "Remate, tiros, toques en area",
        "creador": "Pases clave, asistencias, regates",
        "distribuidor": "Pases exitosos, distribucion, posesion",
        "presionador": "Recuperaciones, entradas, intercepciones",
        "defensor": "Despejes, bloqueos, duelos aereos",
        "extremo": "Regates, centros, velocidad de accion",
    }
    for k, v in prof.get("role_scores", {}).items():
        rs.append([k, str(int(v)), role_descs.get(k.lower(), "—")])
    story.append(_tbl(rs, col_widths=[5 * cm, 3 * cm, 8.5 * cm], fs=8))

    # ── Top percentiles ───────────────────────────────────────────────────────
    tpc = _top_percentiles_chart(crow, pool)
    if tpc:
        story.append(Paragraph("Mejores percentiles vs misma posicion", h2))
        story.append(tpc)
        story.append(Paragraph(
            "Verde >= 80  ·  Rojo >= 60  ·  Ambar >= 40  ·  Gris < 40.  "
            "Comparacion vs jugadores de la misma posicion y liga en el scope de datos OPTA.",
            italic))

    # ── Percentiles por metrica (pagina nueva) ────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("Percentiles por metrica (historico vs posicion)", h2))
    story.append(Paragraph(
        "Percentil calculado como rango dentro del grupo de jugadores de la misma "
        "posicion en el scope de datos. Valor/90 = valor por 90 minutos jugados "
        "en el historico del jugador.",
        italic))

    def pct_of(metric):
        if metric not in pool.columns:
            return None
        ser = pd.to_numeric(pool[metric], errors="coerce")
        pr = ser.rank(pct=True) * 100
        idx = pool.index[pool["name"] == cname]
        return float(pr.get(idx[0])) if len(idx) and pd.notna(pr.get(idx[0])) else None

    for grp, metrics in METRIC_GROUPS.items():
        rows = [[grp, "Valor/90", "Percentil", "Interpretacion"]]
        for m in metrics:
            pc = pct_of(m)
            v90 = ""
            if m in crow.index and pd.notna(crow.get(m)):
                v90 = f"{float(crow[m]):.2f}"
            if pc is not None:
                nivel = "Elite" if pc >= 80 else ("Bueno" if pc >= 60 else
                        ("Medio" if pc >= 40 else "Bajo"))
                rows.append([METRIC_LABELS.get(m, m), v90, str(int(pc)), nivel])
        if len(rows) > 1:
            story.append(_tbl(rows,
                              col_widths=[7.5 * cm, 2 * cm, 2 * cm, 2.5 * cm], fs=8))
            story.append(Spacer(1, 4))

    # ── Estadisticas por temporada ────────────────────────────────────────────
    story.append(Paragraph("Estadisticas por temporada (OPTA)", h2))
    prows = enr[enr["name"] == cname].copy()
    order = {"2025-2026": 6, "2025": 5, "2024-2025": 4, "2023-2024": 3,
             "2022-2023": 2, "2021-2022": 1}
    prows["_o"] = prows["season"].map(order).fillna(0)
    prows = prows.sort_values("_o", ascending=False)
    cols = [(c, lbl) for c, lbl in SEASON_COLS if c in prows.columns]
    tdata = [[lbl for _, lbl in cols]]
    for _, rw in prows.iterrows():
        row = []
        for c, _lbl in cols:
            v = rw.get(c)
            if c == "minutes" and pd.notna(v):
                v = int(v)
            elif isinstance(v, float) and pd.notna(v) and c != "season":
                v = int(v)
            row.append("" if pd.isna(v) else str(v))
        tdata.append(row)
    story.append(_tbl(tdata, fs=6))

    # ── Pie de pagina ─────────────────────────────────────────────────────────
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        f"Generado el {date.today().strftime('%d %b %Y').lstrip('0')}  ·  "
        f"Rayo Vallecano — Direccion Deportiva.  "
        f"Datos OPTA ({prof.get('seasons_played','?')} temporadas historicas) + Transfermarkt.  "
        f"Percentiles calculados vs jugadores de la misma posicion en el scope disponible.",
        italic))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            topMargin=1.0 * cm, bottomMargin=1.2 * cm,
                            leftMargin=1.5 * cm, rightMargin=1.5 * cm)
    doc.build(story)
    buf.seek(0)
    return f"informe_{_n(cname).replace(' ', '_')}.pdf", buf.read()
