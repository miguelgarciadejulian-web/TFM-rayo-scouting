"""
coach_dossier.py
================
Informe PDF ejecutivo de un entrenador: portada profesional con recomendacion,
foto, estilo de juego calculado (radar + ejes tácticos), comparativa vs ADN Rayo,
evaluacion detallada (score, subscores con pesos, pros/contras, riesgos),
equipos dirigidos y metodologia de calculo transparente.
"""
from __future__ import annotations
import csv
import io
import json
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
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image)

from src.utils.config import settings

# ── Colores ───────────────────────────────────────────────────────────────────
RAYO_RED  = colors.HexColor("#E30613")
RAYO_DARK = colors.HexColor("#1A1A2E")
C_GREEN   = colors.HexColor("#166534")
C_AMBER   = colors.HexColor("#92400E")
C_LIGHT   = colors.HexColor("#FFF8F8")
C_BORDER  = colors.HexColor("#FECACA")
C_GREY_BG = colors.HexColor("#FAFAFA")
C_GREY_LN = colors.HexColor("#E5E7EB")
C_BLUE_BG = colors.HexColor("#EFF6FF")
C_BLUE    = colors.HexColor("#1D4ED8")

ROOT = Path(__file__).resolve().parents[2]
PROC = Path(settings()["paths"]["data_processed"])

AXES = [
    ("tendencia_ofensiva",    "Ofensivo"),
    ("solidez_defensiva",     "Defensivo"),
    ("presion_alta",          "Presion"),
    ("posesion",              "Posesion"),
    ("verticalidad",          "Verticalidad"),
    ("intensidad_defensiva",  "Intensidad def."),
    ("uso_transiciones",      "Transiciones"),
    ("flexibilidad_tactica",  "Flexibilidad"),
]

RISK_LABELS = {
    "deportivo":                "Deportivo",
    "economico":                "Economico",
    "clausula":                 "Clausula",
    "adaptacion_laliga":        "Adaptacion LaLiga",
    "incompatibilidad_plantilla": "Incompat. plantilla",
}


def _n(s):
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().strip()


def _coach_photo(name):
    f = ROOT / "config" / "coach_photos.csv"
    if f.exists():
        for r in csv.DictReader(open(f, encoding="utf-8")):
            if _n(r.get("entrenador", "")) == _n(name):
                return (r.get("imagen_local") or "").strip() or \
                       (r.get("imagen") or "").strip() or None
    return None


def _scaled_image(img_bytes, w_cm, h_cm):
    try:
        from PIL import Image as _PIL
        im = _PIL.open(io.BytesIO(img_bytes)).convert("RGB")
        im.thumbnail((420, 520))
        out = io.BytesIO()
        im.save(out, format="JPEG", quality=82)
        out.seek(0)
        return Image(out, width=w_cm * cm, height=h_cm * cm)
    except Exception:
        return Image(io.BytesIO(img_bytes), width=w_cm * cm, height=h_cm * cm)


def _manual(name):
    f = PROC / "coach_manual_notes.json"
    if f.exists():
        try:
            return json.load(open(f, encoding="utf-8")).get(name, {})
        except Exception:
            pass
    return {}


def _load_dna_target():
    """
    Carga el ADN objetivo del Rayo desde datos reales (team_seasons.parquet
    y club_profile.yaml), via dynamic_dna.build_dynamic_dna().
    """
    try:
        from src.fit.dynamic_dna import build_dynamic_dna
        dna = build_dynamic_dna()
        return dna.get("target_style", {})
    except Exception:
        pass
    # Fallback: leer el YAML estatico si el modulo dinamico no esta disponible
    try:
        import yaml
        f = ROOT / "config" / "rayo_dna.yaml"
        if f.exists():
            raw = yaml.safe_load(f.read_text(encoding="utf-8"))
            return raw.get("target_style", {})
    except Exception:
        pass
    return {}


def _fmt_salary(v):
    if not v:
        return "n/d"
    return f"{v / 1e6:.1f}M EUR/ano" if v >= 1e6 else f"{v / 1e3:.0f}K EUR/ano"


# ── Graficos ──────────────────────────────────────────────────────────────────
def _fig(fig, w_cm=11):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return Image(buf, width=w_cm * cm, height=w_cm * cm)


def _radar(axes):
    items = [(lab, axes.get(k)) for k, lab in AXES if axes.get(k) is not None]
    if len(items) < 3:
        return None
    labs = [i[0] for i in items]
    vals = [float(i[1]) for i in items]
    ang = np.linspace(0, 2 * np.pi, len(labs), endpoint=False).tolist()
    vals_c = vals + vals[:1]
    ang_c  = ang + ang[:1]
    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
    ax.set_facecolor("#FFF8F8")
    fig.patch.set_facecolor("white")
    ax.plot(ang_c, vals_c, color="#E30613", linewidth=2.5)
    ax.fill(ang_c, vals_c, color="#E30613", alpha=0.20)
    ax.set_xticks(ang)
    ax.set_xticklabels(labs, fontsize=8)
    ax.set_ylim(0, 100)
    ax.set_yticks([25, 50, 75])
    ax.set_yticklabels(["25", "50", "75"], fontsize=6, color="#9CA3AF")
    ax.grid(color="#E5E7EB", linewidth=0.7)
    return _fig(fig, 10)


def _adn_comparison_chart(axes, dna_target):
    """Barras agrupadas: estilo del tecnico (rojo) vs ADN objetivo Rayo (gris)."""
    items = [(lab, axes.get(k), dna_target.get(k, {}).get("ideal"))
             for k, lab in AXES if axes.get(k) is not None]
    if not items:
        return None
    labels     = [i[0] for i in items]
    coach_vals = [float(i[1]) for i in items]
    target_vals = [float(i[2]) if i[2] is not None else 50.0 for i in items]
    x     = np.arange(len(labels))
    width = 0.38
    fig, ax = plt.subplots(figsize=(9, 3.5))
    ax.set_facecolor("#FAFAFA")
    fig.patch.set_facecolor("white")
    bars1 = ax.bar(x - width / 2, coach_vals, width,
                   label="Tecnico", color="#E30613", alpha=0.85)
    bars2 = ax.bar(x + width / 2, target_vals, width,
                   label="ADN Rayo (objetivo)", color="#9CA3AF", alpha=0.65, hatch="//")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=22, ha="right", fontsize=8)
    ax.set_ylim(0, 115)
    ax.set_ylabel("Score 0-100", fontsize=8, color="#6B7280")
    ax.legend(fontsize=8, loc="upper right")
    ax.axhline(50, color="#E5E7EB", linewidth=0.8, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for b1, b2 in zip(bars1, bars2):
        diff  = b1.get_height() - b2.get_height()
        color = "#166534" if abs(diff) <= 10 else "#9F1239"
        ax.text(b1.get_x() + b1.get_width() / 2, b1.get_height() + 2,
                f"{diff:+.0f}", ha="center", fontsize=7, color=color, fontweight="bold")
    ax.set_title("Estilo del tecnico vs ADN objetivo Rayo  (diferencia en rojo si > 10 pts)",
                 fontsize=9, color="#374151", pad=6)
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return Image(buf, width=14 * cm, height=5.5 * cm)


def _team_seasons_table(name):
    tn  = ROOT / "config" / "coach_tenures.csv"
    tsf = PROC / "team_seasons.parquet"
    if not tn.exists() or not tsf.exists():
        return None
    ten = pd.read_csv(tn)
    ten = ten[ten["coach"].map(_n) == _n(name)]
    if ten.empty:
        return None
    ts  = pd.read_parquet(tsf)
    rows = [["Temp.", "Equipo", "Pos%", "Tiros/p", "Goles/p", "Encaj/p", "Recup/p", "PC cero"]]
    for _, t in ten.sort_values("season").iterrows():
        m = ts[
            (ts["league"] == t["league"]) &
            (ts["team"].str.contains(str(t["team"]).split()[0], case=False, na=False)) &
            (ts["season"].astype(str) == str(t["season"]))
        ]
        if m.empty:
            continue
        r = m.iloc[0]
        g = float(r.get("games_played") or 0) or 1
        def pg(c):
            return f"{float(r.get(c) or 0) / g:.1f}"
        rows.append([
            str(t["season"]), str(t["team"])[:22],
            str(int(r.get("possession_percentage") or 0)),
            pg("total_shots"), pg("goals"), pg("goals_conceded"),
            pg("recoveries"), str(int(r.get("clean_sheets") or 0)),
        ])
    return rows if len(rows) > 1 else None


# ── Helpers de tabla ──────────────────────────────────────────────────────────
def _tbl(data, head_bg=RAYO_RED, col_widths=None, fs=8):
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
def build_coach_dossier(name):
    profiles = json.load(open(PROC / "coach_profiles.json", encoding="utf-8"))
    c = next((x for x in profiles if _n(x["name"]) == _n(name)), None)
    if c is None:
        raise ValueError(f"Entrenador '{name}' no encontrado")
    ev   = c.get("evaluation", {})
    axes = c.get("axes", {})
    man  = _manual(c["name"])
    dna_target = _load_dna_target()

    styles = getSampleStyleSheet()
    h2     = ParagraphStyle("h2", parent=styles["Heading2"], textColor=RAYO_RED,
                             fontSize=11, spaceBefore=10, spaceAfter=2)
    body   = ParagraphStyle("body", parent=styles["BodyText"], fontSize=9, leading=13)
    small  = ParagraphStyle("small", parent=styles["BodyText"], fontSize=7.5,
                            textColor=colors.HexColor("#6B7280"), leading=11)
    italic = ParagraphStyle("italic", parent=styles["BodyText"], fontSize=7.5,
                            textColor=colors.HexColor("#9CA3AF"), leading=11,
                            fontName="Helvetica-Oblique")
    story = []

    # ── Banda roja de portada ─────────────────────────────────────────────────
    hdr_left = Paragraph(
        "<font color='white'><b>RAYO VALLECANO  —  DIRECCION DEPORTIVA</b></font>",
        ParagraphStyle("hl", parent=styles["BodyText"], fontSize=9,
                       textColor=colors.white, leading=12))
    hdr_right = Paragraph(
        f"<font color='white'>{date.today().strftime('%d %b %Y').lstrip('0')}</font>",
        ParagraphStyle("hr", parent=styles["BodyText"], fontSize=9,
                       textColor=colors.white, leading=12, alignment=2))
    hdr_row = Table([[hdr_left, hdr_right]], colWidths=[11 * cm, 5.5 * cm])
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

    # ── Foto + bloque info ────────────────────────────────────────────────────
    foto = ""
    url  = _coach_photo(c["name"])
    img_bytes = None
    if url:
        if url.startswith("/assets/"):
            fp = ROOT / "dashboard" / url.lstrip("/")
            if fp.exists():
                img_bytes = fp.read_bytes()
        elif url.startswith("http"):
            try:
                import requests
                r = requests.get(url, timeout=10, headers={"User-Agent": "RayoScoutingTool/1.0"})
                if r.status_code == 200 and r.content:
                    img_bytes = r.content
            except Exception:
                img_bytes = None
    if img_bytes:
        try:
            foto = _scaled_image(img_bytes, 3, 3.6)
        except Exception:
            foto = ""

    score_10  = ev.get("score_10", 0)
    score_num = float(score_10) if score_10 not in (None, "n/d", "") else 0.0

    # Caja de recomendacion segun Fit Rayo
    if score_num >= 7:
        rec_label = "RECOMENDADO"
        rec_color = colors.HexColor("#166534")
        rec_bg    = colors.HexColor("#F0FDF4")
    elif score_num >= 5:
        rec_label = "VALORAR"
        rec_color = colors.HexColor("#92400E")
        rec_bg    = colors.HexColor("#FFFBEB")
    else:
        rec_label = "NO RECOMENDADO"
        rec_color = colors.HexColor("#9F1239")
        rec_bg    = colors.HexColor("#FFF1F2")

    name_para = Paragraph(
        f"<b>{c['name']}</b>",
        ParagraphStyle("nm", parent=styles["BodyText"], fontSize=15,
                       textColor=RAYO_DARK, leading=18, fontName="Helvetica-Bold"))
    sub_para = Paragraph(
        f"{c.get('age', '?')} anos  ·  {c.get('nationality', '')}  ·  "
        f"Ultimo club: {c.get('last_club', 'n/d')}",
        ParagraphStyle("sub", parent=styles["BodyText"], fontSize=9,
                       textColor=RAYO_RED, leading=12))
    avail_para = Paragraph(
        f"Situacion: {'Libre' if c.get('available') else 'Con equipo'}  ·  "
        f"{c.get('contract_status', '')}",
        small)
    style_para = Paragraph(
        f"<b>Estilo:</b>  {c.get('style_main', 'n/d')}",
        body)
    tags_para = Paragraph(
        ", ".join(c.get("style_tags", []) or []), small)

    left_col = [name_para, Spacer(1, 3), sub_para, Spacer(1, 3),
                avail_para, Spacer(1, 5), style_para, Spacer(1, 2), tags_para]

    kpi_data = [
        ["Fit Rayo",              f"{score_10}/10"],
        ["Salario estimado",      _fmt_salary(c.get("salary_estimate_eur"))],
        ["Exp. LaLiga",           f"{c.get('laliga_seasons', 0)} temporadas"],
        ["Recomendacion",         rec_label],
    ]
    kpi_t = _kpi_tbl(kpi_data, col_widths=[4 * cm, 3.5 * cm])
    kpi_t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_LIGHT),
        ("BACKGROUND", (3, 0), (3, 0), rec_bg),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.3, C_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TEXTCOLOR", (1, 3), (1, 3), rec_color),
        ("FONTNAME", (1, 3), (1, 3), "Helvetica-Bold"),
    ]))

    if foto:
        cw = [3.4 * cm, 7.5 * cm, 5.5 * cm]
        main_row = [[foto, left_col, kpi_t]]
    else:
        cw = [11 * cm, 5.5 * cm]
        main_row = [[left_col, kpi_t]]

    mt = Table([main_row], colWidths=cw)
    mt.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(mt)
    story.append(Spacer(1, 8))

    # ── Descripcion automatica ────────────────────────────────────────────────
    desc = c.get("description_auto", "")
    if desc:
        story.append(Paragraph(desc, body))
        story.append(Spacer(1, 6))

    # ── Pros / Contras / Riesgos ──────────────────────────────────────────────
    pros  = (ev.get("pros_auto", []) or []) + man.get("pros", [])
    cons  = (ev.get("contras_auto", []) or []) + man.get("contras", [])
    risks = ev.get("risks", {})

    if pros or cons or risks:
        pcr_rows = []
        if pros:
            pcr_rows.append([
                Paragraph("<b>Pros</b>",
                          ParagraphStyle("p", parent=styles["BodyText"], fontSize=8,
                                         textColor=C_GREEN, fontName="Helvetica-Bold")),
                Paragraph("; ".join(pros), small),
            ])
        if cons:
            pcr_rows.append([
                Paragraph("<b>Contras</b>",
                          ParagraphStyle("c", parent=styles["BodyText"], fontSize=8,
                                         textColor=C_AMBER, fontName="Helvetica-Bold")),
                Paragraph("; ".join(cons), small),
            ])
        if risks:
            risk_text = "  ·  ".join(f"{RISK_LABELS.get(k, k)}: {v}"
                                      for k, v in risks.items())
            pcr_rows.append([
                Paragraph("<b>Riesgos</b>",
                          ParagraphStyle("r", parent=styles["BodyText"], fontSize=8,
                                         textColor=colors.HexColor("#9F1239"),
                                         fontName="Helvetica-Bold")),
                Paragraph(risk_text, small),
            ])
        if pcr_rows:
            pcr_t = Table(pcr_rows, colWidths=[2.5 * cm, 14 * cm])
            pcr_t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), C_LIGHT),
                ("GRID", (0, 0), (-1, -1), 0.3, C_BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.append(pcr_t)
            story.append(Spacer(1, 6))

    # ── Estilo de juego — radar ───────────────────────────────────────────────
    story.append(Paragraph("Estilo de juego (calculado desde datos)", h2))
    story.append(Paragraph(
        "Ejes calculados a partir de las estadisticas medias de los equipos dirigidos por "
        "el tecnico (team_seasons.parquet). Cada eje es el percentil del equipo vs la "
        "liga en esa metrica. 100 = mejor de la liga en ese eje.",
        italic))
    radar = _radar(axes)
    if radar:
        story.append(radar)

    # ── Comparativa vs ADN Rayo ───────────────────────────────────────────────
    story.append(Paragraph("Comparativa: estilo del tecnico vs ADN objetivo Rayo", h2))
    story.append(Paragraph(
        "Las barras rojas son el percentil del tecnico en cada dimension. "
        "Las barras grises son el ADN objetivo del Rayo, calculado desde los datos reales "
        "del equipo (team_seasons.parquet). La diferencia se marca en verde si es <= 10 puntos "
        "o en rojo si es > 10 (posible desajuste tatico).",
        italic))
    cmp_chart = _adn_comparison_chart(axes, dna_target)
    if cmp_chart:
        story.append(cmp_chart)
        story.append(Spacer(1, 4))

    # Tabla numerica de ejes
    ax_rows = [["Eje tactico", "Tecnico (0-100)", "ADN Rayo", "Diferencia", "Valoracion"]]
    for k, lab in AXES:
        if axes.get(k) is None:
            continue
        coach_v  = int(axes[k])
        target_v = dna_target.get(k, {}).get("ideal")
        diff     = coach_v - target_v if target_v is not None else None
        diff_str = f"{diff:+d}" if diff is not None else "—"
        val_str  = ("Alineado" if diff is not None and abs(diff) <= 10 else
                    ("Desajuste leve" if diff is not None and abs(diff) <= 20 else
                     ("Desajuste importante" if diff is not None else "—")))
        ax_rows.append([lab, str(coach_v),
                        str(int(target_v)) if target_v is not None else "—",
                        diff_str, val_str])
    if axes.get("posesion_pct_real") is not None:
        ax_rows.append(["Posesion media real", f"{axes['posesion_pct_real']}%", "—", "—", "—"])
    story.append(_tbl(ax_rows, col_widths=[4.5 * cm, 2.8 * cm, 2.5 * cm, 2.2 * cm, 3.5 * cm]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Metodologia de ejes: se calculan como percentil (0-100) del equipo dirigido "
        "en esa metrica vs el resto de equipos de la misma liga y temporada. "
        "Fuente: team_seasons.parquet (datos OPTA de equipos).",
        italic))

    # ── Evaluacion — Fit Rayo ─────────────────────────────────────────────────
    story.append(Paragraph("Evaluacion — Fit Rayo como candidato", h2))
    sub = ev.get("subscores", {})
    story.append(Paragraph(
        f"<b>Fit Rayo global:</b>  {score_10}/10  ({float(score_10) * 10:.0f}/100)",
        body))
    story.append(Spacer(1, 4))

    sub_labels = {
        "estilo":       ("Cercania al ADN Rayo (estilo tactico)",   "~55%"),
        "laliga":       ("Experiencia LaLiga",                       "15%"),
        "budget":       ("Encaje salarial vs referencia del club",   "15%"),
        "squad_compat": ("Compatibilidad con la plantilla actual",   "15%"),
    }
    if sub:
        tbl_data = [["Sub-score", "Peso", "Valor (0-100)", "Metodologia"]]
        methodo  = {
            "estilo":       "Distancia coseno entre ejes del tecnico y ADN Rayo",
            "laliga":       "Temporadas en Primera o Segunda Division espanola",
            "budget":       "Salario estimado vs. margen presupuestario del club",
            "squad_compat": "Similitud entre estilo del tecnico y perfil de la plantilla",
        }
        for k, (label, weight) in sub_labels.items():
            v = sub.get(k)
            if v is not None:
                tbl_data.append([label, weight, str(int(float(v))), methodo.get(k, "—")])
        if len(tbl_data) > 1:
            story.append(_tbl(tbl_data,
                              col_widths=[4.5 * cm, 1.5 * cm, 2 * cm, 8.5 * cm], fs=8))
            story.append(Spacer(1, 4))

    story.append(Paragraph(
        "Formula:  Fit = (Estilo x 0.55) + (LaLiga x 0.15) + (Presupuesto x 0.15) "
        "+ (Compat.plantilla x 0.15)  ->  resultado /100, expresado tambien como /10.  "
        "Estilo: similitud normalizada entre los 8 ejes del tecnico y el ADN objetivo "
        "del Rayo (distancia euclidea invertida, normalizada 0-100).  "
        "LaLiga: 25 puntos por cada temporada en Primera, 10 en Segunda, max 100.  "
        "Presupuesto: score 100 si el salario estimado cabe en el margen, "
        "reduciendose proporcionalmente.  "
        "Compat. plantilla: alineamiento entre la demanda tactica del tecnico y los "
        "roles disponibles en la plantilla.",
        italic))

    # ── Equipos dirigidos ─────────────────────────────────────────────────────
    tst = _team_seasons_table(c["name"])
    if tst:
        story.append(Paragraph("Equipos dirigidos y rendimiento medio por partido", h2))
        story.append(Paragraph(
            "Metricas promediadas por partido para cada etapa del tecnico. "
            "Fuente: team_seasons.parquet cruzado con coach_tenures.csv.",
            italic))
        t2 = Table(tst, repeatRows=1)
        t2.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), RAYO_RED),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",   (0, 0), (-1, -1), 7),
            ("GRID",       (0, 0), (-1, -1), 0.3, C_GREY_LN),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, C_GREY_BG]),
            ("LEFTPADDING",  (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING",   (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
        ]))
        story.append(t2)
        story.append(Paragraph(
            "Pos% = posesion media  ·  /p = por partido  ·  PC cero = porterias a cero.",
            italic))

    # ── Pie de pagina ─────────────────────────────────────────────────────────
    story.append(Spacer(1, 10))
    cov = c.get("coverage", {})
    story.append(Paragraph(
        f"Cobertura de datos: {', '.join(cov.get('teams', []) or ['—'])}  ·  "
        f"{cov.get('n_rows', 0)} temporadas en el scope.  "
        f"Generado el {date.today().strftime('%d %b %Y').lstrip('0')}  ·  "
        f"Rayo Vallecano — Direccion Deportiva.  "
        f"Calculos automaticos basados en datos OPTA de equipos.",
        italic))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            topMargin=1.0 * cm, bottomMargin=1.2 * cm,
                            leftMargin=1.6 * cm, rightMargin=1.6 * cm)
    doc.build(story)
    buf.seek(0)
    return f"informe_entrenador_{_n(c['name']).replace(' ', '_')}.pdf", buf.read()
