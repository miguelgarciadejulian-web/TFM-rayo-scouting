"""
coach_dossier.py
================
Informe PDF ejecutivo de un entrenador — diseno moderno v3.
Dark hero card + KPI strip + pros/contras + radar + ADN comparison + fit eval + teams.
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
C_RED      = colors.HexColor("#E30613")
C_DARK     = colors.HexColor("#111827")
C_DARK2    = colors.HexColor("#1F2937")
C_MID      = colors.HexColor("#374151")
C_GREY     = colors.HexColor("#9CA3AF")
C_BG       = colors.HexColor("#F8FAFC")
C_BORDER   = colors.HexColor("#E2E8F0")
C_GREEN    = colors.HexColor("#166534")
C_AMBER    = colors.HexColor("#92400E")
C_RED_DARK = colors.HexColor("#9F1239")
C_GREEN_BG = colors.HexColor("#F0FDF4")
C_AMBER_BG = colors.HexColor("#FFFBEB")
C_RED_BG   = colors.HexColor("#FFF1F2")
C_WHITE    = colors.white

ROOT = Path(__file__).resolve().parents[2]
PROC = Path(settings()["paths"]["data_processed"])

PAGE_W, PAGE_H = A4
MARG      = 1.6 * cm
CONTENT_W = PAGE_W - 2 * MARG

AXES = [
    ("tendencia_ofensiva",      "Ofensivo"),
    ("solidez_defensiva",       "Defensivo"),
    ("presion_alta",            "Presion"),
    ("posesion",                "Posesion"),
    ("verticalidad",            "Verticalidad"),
    ("intensidad_defensiva",    "Intensidad def."),
    ("uso_transiciones",        "Transiciones"),
    ("flexibilidad_tactica",    "Flexibilidad"),
]

RISK_LABELS = {
    "deportivo":                  "Deportivo",
    "economico":                  "Economico",
    "clausula":                   "Clausula",
    "adaptacion_laliga":          "Adaptacion LaLiga",
    "incompatibilidad_plantilla": "Incompat. plantilla",
}


# ── Helpers ───────────────────────────────────────────────────────────────────
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


def _load_photo_bytes(name):
    url = _coach_photo(name)
    if not url:
        return None
    if url.startswith("/assets/"):
        fp = ROOT / "dashboard" / url.lstrip("/")
        if fp.exists():
            return fp.read_bytes()
    elif url.startswith("http"):
        try:
            import requests
            r = requests.get(url, timeout=10,
                             headers={"User-Agent": "RayoScoutingTool/1.0"})
            if r.status_code == 200 and r.content:
                return r.content
        except Exception:
            pass
    return None


def _scaled_image(img_bytes, w_cm, h_cm):
    try:
        from PIL import Image as _PIL
        im = _PIL.open(io.BytesIO(img_bytes)).convert("RGB")
        im.thumbnail((int(w_cm * 40), int(h_cm * 40)))
        out = io.BytesIO()
        im.save(out, format="JPEG", quality=85)
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
    try:
        from src.fit.dynamic_dna import build_dynamic_dna
        dna = build_dynamic_dna()
        return dna.get("target_style", {})
    except Exception:
        pass
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


# ── Estilos ───────────────────────────────────────────────────────────────────
def _styles():
    base = getSampleStyleSheet()

    def S(name, **kw):
        return ParagraphStyle(name, parent=base["BodyText"], **kw)

    return {
        "hero_name": S("hero_name", fontName="Helvetica-Bold", fontSize=20,
                       textColor=C_WHITE, leading=24),
        "hero_sub":  S("hero_sub",  fontName="Helvetica",      fontSize=10,
                       textColor=C_RED, leading=14),
        "hero_info": S("hero_info", fontName="Helvetica",      fontSize=9,
                       textColor=colors.HexColor("#D1D5DB"), leading=13),
        "kpi_label": S("kpi_label", fontName="Helvetica",      fontSize=7,
                       textColor=C_GREY, leading=10),
        "kpi_value": S("kpi_value", fontName="Helvetica-Bold", fontSize=13,
                       textColor=C_DARK, leading=17),
        "section":   S("section",   fontName="Helvetica-Bold", fontSize=10,
                       textColor=C_WHITE, leading=13),
        "body":      S("body",      fontName="Helvetica",      fontSize=9,
                       textColor=C_MID, leading=13),
        "small":     S("small",     fontName="Helvetica",      fontSize=7.5,
                       textColor=C_GREY, leading=11),
        "italic":    S("italic",    fontName="Helvetica-Oblique", fontSize=7.5,
                       textColor=C_GREY, leading=11),
        "tag_green": S("tag_green", fontName="Helvetica-Bold", fontSize=8,
                       textColor=C_GREEN,    leading=12),
        "tag_amber": S("tag_amber", fontName="Helvetica-Bold", fontSize=8,
                       textColor=C_AMBER,    leading=12),
        "tag_red":   S("tag_red",   fontName="Helvetica-Bold", fontSize=8,
                       textColor=C_RED_DARK, leading=12),
        "cell_hdr":  S("cell_hdr",  fontName="Helvetica-Bold", fontSize=9,
                       textColor=C_DARK, leading=12),
    }


def _section_header(text, st):
    """Header con borde rojo izquierdo — igual que player_dossier v3."""
    accent = Table([[""]], colWidths=[4], rowHeights=[18])
    accent.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (0, 0), C_RED),
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING",   (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 0),
    ]))
    label = Paragraph(
        f"<b>{text.upper()}</b>",
        ParagraphStyle("sh_lbl", fontName="Helvetica-Bold",
                       fontSize=9, textColor=C_DARK, leading=13))
    hdr = Table([[accent, label]], colWidths=[10, CONTENT_W - 10])
    hdr.setStyle(TableStyle([
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING",   (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 0),
        ("LEFTPADDING",  (1, 0), (1, -1), 8),
    ]))
    return hdr


def _tbl(data, col_widths=None, fs=8, hdr_bg=None):
    """Tabla con cabecera oscura y filas alternadas."""
    if hdr_bg is None:
        hdr_bg = C_DARK2
    t = Table(data, repeatRows=1, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND",      (0, 0), (-1, 0), hdr_bg),
        ("TEXTCOLOR",       (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME",        (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",        (0, 0), (-1, -1), fs),
        ("GRID",            (0, 0), (-1, -1), 0.3, C_BORDER),
        ("ROWBACKGROUNDS",  (0, 1), (-1, -1), [colors.white, C_BG]),
        ("VALIGN",          (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",     (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",    (0, 0), (-1, -1), 6),
        ("TOPPADDING",      (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",   (0, 0), (-1, -1), 3),
    ]))
    return t


def _kpi_card(label, value, bg=None, fg=None, w=3.5 * cm):
    if bg is None:
        bg = colors.white
    if fg is None:
        fg = C_DARK
    val_style = ParagraphStyle("kv", fontName="Helvetica-Bold", fontSize=13,
                                textColor=fg, leading=16)
    lbl_style = ParagraphStyle("kl", fontName="Helvetica",      fontSize=7,
                                textColor=C_GREY, leading=10)
    inner = Table([
        [Paragraph(label.upper(), lbl_style)],
        [Paragraph(str(value),    val_style)],
    ], colWidths=[w - 14])
    inner.setStyle(TableStyle([
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING",   (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 1),
    ]))
    card = Table([[inner]], colWidths=[w])
    card.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), bg),
        ("BOX",          (0, 0), (-1, -1), 0.5, C_BORDER),
        ("LEFTPADDING",  (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING",   (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 8),
    ]))
    return card


# ── Graficos ──────────────────────────────────────────────────────────────────
def _radar_chart(axes, w_cm=8.5):
    items = [(lab, axes.get(k)) for k, lab in AXES if axes.get(k) is not None]
    if len(items) < 3:
        return None
    labs = [i[0] for i in items]
    vals = [float(i[1]) for i in items]
    N    = len(labs)
    ang  = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    vals_c = vals + vals[:1]
    ang_c  = ang  + ang[:1]

    fig, ax = plt.subplots(figsize=(5.5, 5.5), subplot_kw=dict(polar=True))
    ax.set_facecolor("#F9FAFB")
    fig.patch.set_facecolor("white")
    for pct in [25, 50, 75]:
        ax.plot(ang_c, [pct] * (N + 1), color="#E5E7EB", linewidth=0.8, zorder=1)
    ax.fill(ang_c, vals_c, color="#E30613", alpha=0.18, zorder=2)
    ax.plot(ang_c, vals_c, color="#E30613", linewidth=2.5, zorder=3)
    ax.scatter(ang, vals, color="#E30613", s=30, zorder=4)
    ax.set_xticks(ang)
    ax.set_xticklabels(labs, fontsize=8, color="#374151")
    ax.set_ylim(0, 100)
    ax.set_yticks([])
    ax.yaxis.set_visible(False)
    ax.spines["polar"].set_color("#E5E7EB")
    ax.grid(False)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return Image(buf, width=w_cm * cm, height=w_cm * cm)


def _adn_chart(axes, dna_target, w_cm=14.0, h_cm=4.5):
    items = [(lab, axes.get(k), dna_target.get(k, {}).get("ideal"))
             for k, lab in AXES if axes.get(k) is not None]
    if not items:
        return None
    labels      = [i[0] for i in items]
    coach_vals  = [float(i[1]) for i in items]
    target_vals = [float(i[2]) if i[2] is not None else 50.0 for i in items]
    x     = np.arange(len(labels))
    width = 0.35
    fig, ax = plt.subplots(figsize=(w_cm * 0.45, h_cm * 0.45))
    ax.set_facecolor("#F9FAFB")
    fig.patch.set_facecolor("white")
    ax.bar(x - width / 2, coach_vals,  width, label="Tecnico",
           color="#E30613", alpha=0.88, zorder=3)
    ax.bar(x + width / 2, target_vals, width, label="ADN Rayo",
           color="#9CA3AF", alpha=0.65, hatch="//", zorder=3)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=20, ha="right", fontsize=7.5)
    ax.set_ylim(0, 118)
    ax.set_ylabel("Score 0-100", fontsize=7.5, color="#6B7280")
    ax.axhline(50, color="#D1D5DB", linewidth=0.8, linestyle="--", zorder=1)
    ax.legend(fontsize=8, loc="upper right", framealpha=0.8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#E5E7EB")
    ax.spines["bottom"].set_color("#E5E7EB")
    ax.tick_params(colors="#6B7280")
    bars = ax.containers
    if len(bars) >= 2:
        for b1, b2 in zip(bars[0], bars[1]):
            diff  = b1.get_height() - b2.get_height()
            color = "#166534" if abs(diff) <= 10 else "#9F1239"
            ax.text(b1.get_x() + b1.get_width() / 2, b1.get_height() + 2,
                    f"{diff:+.0f}", ha="center", fontsize=6.5,
                    color=color, fontweight="bold")
    plt.tight_layout(pad=0.5)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return Image(buf, width=w_cm * cm, height=h_cm * cm)


def _team_seasons_table(name):
    tn  = ROOT / "config" / "coach_tenures.csv"
    tsf = PROC / "team_seasons.parquet"
    if not tn.exists() or not tsf.exists():
        return None
    ten = pd.read_csv(tn)
    ten = ten[ten["coach"].map(_n) == _n(name)]
    if ten.empty:
        return None
    ts   = pd.read_parquet(tsf)
    rows = [["Temp.", "Equipo", "Pos%", "Tiros/p", "Goles/p",
             "Encaj/p", "Recup/p", "PC cero"]]
    for _, t in ten.sort_values("season").iterrows():
        m = ts[
            (ts["league"] == t["league"]) &
            (ts["team"].str.contains(
                str(t["team"]).split()[0], case=False, na=False)) &
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


# ── Constructor principal ─────────────────────────────────────────────────────
def build_coach_dossier(name):
    profiles = json.load(open(PROC / "coach_profiles.json", encoding="utf-8"))
    c = next((x for x in profiles if _n(x["name"]) == _n(name)), None)
    if c is None:
        raise ValueError(f"Entrenador '{name}' no encontrado")

    ev         = c.get("evaluation", {})
    axes       = c.get("axes", {})
    man        = _manual(c["name"])
    dna_target = _load_dna_target()
    st         = _styles()
    story      = []

    # ── Banda roja de encabezado ──────────────────────────────────────────────
    hdr_left = Paragraph(
        "<font color='white'><b>RAYO VALLECANO  —  DIRECCION DEPORTIVA</b></font>",
        ParagraphStyle("hl", fontName="Helvetica-Bold", fontSize=9,
                       textColor=C_WHITE, leading=12))
    hdr_right = Paragraph(
        f"<font color='white'>{date.today().strftime('%d %b %Y').lstrip('0')}</font>",
        ParagraphStyle("hr", fontName="Helvetica", fontSize=9,
                       textColor=C_WHITE, leading=12, alignment=2))
    hdr_row = Table([[hdr_left, hdr_right]],
                    colWidths=[11 * cm, CONTENT_W - 11 * cm])
    hdr_row.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), C_RED),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING",   (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 7),
    ]))
    story.append(hdr_row)
    story.append(Spacer(1, 6))

    # ── Hero card oscuro ──────────────────────────────────────────────────────
    score_10  = ev.get("score_10", 0)
    score_num = float(score_10) if score_10 not in (None, "n/d", "") else 0.0
    if score_num >= 7:
        rec_label, rec_color, rec_bg = "RECOMENDADO",    C_GREEN,    C_GREEN_BG
    elif score_num >= 5:
        rec_label, rec_color, rec_bg = "VALORAR",        C_AMBER,    C_AMBER_BG
    else:
        rec_label, rec_color, rec_bg = "NO RECOMENDADO", C_RED_DARK, C_RED_BG

    img_bytes = _load_photo_bytes(c["name"])
    foto_img  = None
    if img_bytes:
        try:
            foto_img = _scaled_image(img_bytes, 3.0, 3.5)
        except Exception:
            foto_img = None

    hero_texts = [
        Paragraph(c["name"], st["hero_name"]),
        Spacer(1, 4),
        Paragraph(
            f"{c.get('nationality', '')}  ·  {c.get('age', '?')} anos  ·  "
            f"Ultimo club: {c.get('last_club', 'n/d')}",
            st["hero_sub"]),
        Spacer(1, 4),
        Paragraph(f"<b>Estilo:</b>  {c.get('style_main', 'n/d')}", st["hero_info"]),
        Paragraph(", ".join(c.get("style_tags", []) or []), st["hero_info"]),
        Spacer(1, 4),
        Paragraph(
            f"Situacion: {'Libre' if c.get('available') else 'Con equipo'}  ·  "
            f"{c.get('contract_status', '')}",
            st["hero_info"]),
    ]

    if foto_img:
        hero_inner = Table(
            [[foto_img, hero_texts]],
            colWidths=[3.4 * cm, CONTENT_W - 3.4 * cm - 16])
        hero_inner.setStyle(TableStyle([
            ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING",  (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING",  (1, 0), (1, -1), 12),
        ]))
    else:
        hero_inner = Table([[hero_texts]], colWidths=[CONTENT_W - 16])
        hero_inner.setStyle(TableStyle([
            ("LEFTPADDING",  (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))

    hero_card = Table([[hero_inner]], colWidths=[CONTENT_W])
    hero_card.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), C_DARK),
        ("LEFTPADDING",  (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING",   (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 14),
    ]))
    story.append(hero_card)
    story.append(Spacer(1, 8))

    # ── KPI strip ─────────────────────────────────────────────────────────────
    sal_str = _fmt_salary(c.get("salary_estimate_eur"))
    ll_str  = f"{c.get('laliga_seasons', 0)} temp."
    kpi_w   = CONTENT_W / 4

    kpi_strip = Table([[
        _kpi_card("Recomendacion", rec_label, bg=rec_bg, fg=rec_color, w=kpi_w),
        _kpi_card("Fit Rayo",      f"{score_10}/10",   w=kpi_w),
        _kpi_card("Salario est.",  sal_str,             w=kpi_w),
        _kpi_card("Exp. LaLiga",   ll_str,              w=kpi_w),
    ]], colWidths=[kpi_w] * 4)
    kpi_strip.setStyle(TableStyle([
        ("LEFTPADDING",  (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING",   (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 0),
    ]))
    story.append(kpi_strip)
    story.append(Spacer(1, 8))

    # ── Descripcion automatica ────────────────────────────────────────────────
    desc = c.get("description_auto", "")
    if desc:
        story.append(Paragraph(desc, st["body"]))
        story.append(Spacer(1, 6))

    # ── Pros / Contras / Riesgos ──────────────────────────────────────────────
    pros  = (ev.get("pros_auto",    []) or []) + man.get("pros",    [])
    cons  = (ev.get("contras_auto", []) or []) + man.get("contras", [])
    risks = ev.get("risks", {})

    pcr_rows = []
    if pros:
        pcr_rows.append([
            Paragraph("FORTALEZAS", st["tag_green"]),
            Paragraph("  ·  ".join(pros), st["small"]),
        ])
    if cons:
        pcr_rows.append([
            Paragraph("CONTRAS", st["tag_amber"]),
            Paragraph("  ·  ".join(cons), st["small"]),
        ])
    if risks:
        risk_text = "  ·  ".join(
            f"{RISK_LABELS.get(k, k)}: {v}" for k, v in risks.items())
        pcr_rows.append([
            Paragraph("RIESGOS", st["tag_red"]),
            Paragraph(risk_text, st["small"]),
        ])
    if pcr_rows:
        TAG_W = 2.8 * cm
        pcr_t = Table(pcr_rows, colWidths=[TAG_W, CONTENT_W - TAG_W])
        pcr_t.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (0, -1), C_BG),
            ("GRID",         (0, 0), (-1, -1), 0.3, C_BORDER),
            ("VALIGN",       (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING",  (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING",   (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ]))
        story.append(pcr_t)
        story.append(Spacer(1, 8))

    # ── Estilo de juego — radar + tabla comparativa ───────────────────────────
    story.append(_section_header("Estilo de juego", st))
    story.append(Spacer(1, 5))
    story.append(Paragraph(
        "Ejes calculados como percentil del equipo dirigido vs la liga en cada metrica "
        "(team_seasons.parquet). 100 = mejor de la liga en ese eje.",
        st["italic"]))
    story.append(Spacer(1, 6))

    radar_img = _radar_chart(axes, w_cm=8.5)

    # Tabla de ejes comparativa (derecha)
    ax_rows = [["Eje", "Tecnico", "ADN Rayo", "Dif."]]
    for k, lab in AXES:
        if axes.get(k) is None:
            continue
        cv   = int(axes[k])
        tv   = dna_target.get(k, {}).get("ideal")
        diff = cv - tv if tv is not None else None
        ds   = (f"+{abs(int(float(diff)))}"
                if diff is not None and float(diff) >= 0
                else f"-{abs(int(float(diff)))}"
                if diff is not None else "n/d")
        ax_rows.append([
            lab, str(cv),
            str(int(tv)) if tv is not None else "n/d",
            ds,
        ])
    if axes.get("posesion_pct_real") is not None:
        ax_rows.append(["Posesion real", f"{axes['posesion_pct_real']}%", "n/d", "n/d"])
    axes_tbl = _tbl(ax_rows,
                    col_widths=[3.8 * cm, 1.5 * cm, 2.1 * cm, 1.4 * cm],
                    fs=7.5)

    L_W = 9.0 * cm
    R_W = CONTENT_W - L_W
    left_cell  = [radar_img] if radar_img else [Spacer(1, 1)]
    right_cell = [
        Paragraph("COMPARATIVA VS ADN RAYO",
                  ParagraphStyle("rh", fontName="Helvetica-Bold", fontSize=8,
                                 textColor=C_DARK, leading=11)),
        Spacer(1, 5),
        axes_tbl,
    ]
    two_col = Table([[left_cell, right_cell]], colWidths=[L_W, R_W])
    two_col.setStyle(TableStyle([
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING",  (1, 0), (1, -1), 10),
    ]))
    story.append(two_col)
    story.append(Spacer(1, 8))

    # ── Comparativa tactica (grafico de barras) ───────────────────────────────
    story.append(_section_header("Comparativa tactica vs ADN Rayo", st))
    story.append(Spacer(1, 5))
    cmp_chart = _adn_chart(axes, dna_target,
                           w_cm=CONTENT_W / cm, h_cm=4.5)
    if cmp_chart:
        story.append(cmp_chart)
        story.append(Paragraph(
            "Rojo = tecnico  ·  Gris rayado = ADN objetivo Rayo.  "
            "Diferencia en verde si <= 10 pts, rojo si > 10 (posible desajuste).",
            st["italic"]))
    story.append(Spacer(1, 8))

    # ── Evaluacion Fit Rayo ───────────────────────────────────────────────────
    story.append(_section_header("Evaluacion — Fit Rayo", st))
    story.append(Spacer(1, 5))
    story.append(Paragraph(
        f"<b>Score global:</b>  {score_10}/10  "
        f"({float(score_10) * 10:.0f}/100)",
        st["body"]))
    story.append(Spacer(1, 4))

    sub = ev.get("subscores", {})
    sub_labels = {
        "estilo":       ("Cercania al ADN Rayo (estilo tactico)",  "~55%"),
        "laliga":       ("Experiencia LaLiga",                      "15%"),
        "budget":       ("Encaje salarial vs presupuesto",          "15%"),
        "squad_compat": ("Compatibilidad con la plantilla",         "15%"),
    }
    methodo = {
        "estilo":       "Distancia coseno entre ejes del tecnico y ADN Rayo",
        "laliga":       "Temporadas en Primera o Segunda espanola",
        "budget":       "Salario estimado vs. margen del club",
        "squad_compat": "Similitud entre estilo del tecnico y perfil plantilla",
    }
    if sub:
        tbl_data = [["Sub-score", "Peso", "Valor (0-100)", "Metodologia"]]
        for k, (label, weight) in sub_labels.items():
            v = sub.get(k)
            if v is not None:
                tbl_data.append([label, weight, str(int(float(v))),
                                  methodo.get(k, "n/d")])
        if len(tbl_data) > 1:
            story.append(_tbl(tbl_data,
                              col_widths=[4.5 * cm, 1.4 * cm,
                                          2.0 * cm, 8.6 * cm], fs=8))
            story.append(Spacer(1, 4))

    story.append(Paragraph(
        "Formula:  Fit = (Estilo x 0.55) + (LaLiga x 0.15) + (Presupuesto x 0.15) "
        "+ (Compat.plantilla x 0.15)  ->  resultado /100, expresado tambien como /10.  "
        "Estilo: similitud normalizada (distancia coseno) entre los 8 ejes del tecnico "
        "y el ADN objetivo Rayo.  LaLiga: 25 pts/temp en Primera, 10 en Segunda, max 100.",
        st["italic"]))
    story.append(Spacer(1, 8))

    # ── Equipos dirigidos ─────────────────────────────────────────────────────
    tst = _team_seasons_table(c["name"])
    if tst:
        story.append(_section_header("Equipos dirigidos y rendimiento", st))
        story.append(Spacer(1, 5))
        story.append(Paragraph(
            "Metricas promediadas por partido para cada etapa del tecnico.  "
            "Fuente: team_seasons.parquet cruzado con coach_tenures.csv.",
            st["italic"]))
        story.append(Spacer(1, 4))
        col_w = [1.8 * cm, 4.0 * cm, 1.2 * cm, 1.5 * cm,
                 1.5 * cm, 1.5 * cm, 1.5 * cm, 1.5 * cm]
        story.append(_tbl(tst, col_widths=col_w, fs=7.5))
        story.append(Paragraph(
            "Pos% = posesion media  ·  /p = por partido  ·  PC cero = porterias a cero.",
            st["italic"]))
        story.append(Spacer(1, 6))

    # ── Pie de pagina ─────────────────────────────────────────────────────────
    story.append(Spacer(1, 8))
    cov = c.get("coverage", {})
    story.append(Paragraph(
        f"Cobertura: {', '.join(cov.get('teams', []) or ['n/d'])}  ·  "
        f"{cov.get('n_rows', 0)} temporadas en el scope.  "
        f"Generado el {date.today().strftime('%d %b %Y').lstrip('0')}  ·  "
        f"Rayo Vallecano — Direccion Deportiva.  "
        f"Calculos automaticos basados en datos OPTA de equipos.",
        st["italic"]))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=1.0 * cm, bottomMargin=1.2 * cm,
        leftMargin=MARG, rightMargin=MARG,
    )
    doc.build(story)
    buf.seek(0)
    return (
        f"informe_entrenador_{_n(c['name']).replace(' ', '_')}.pdf",
        buf.read(),
    )
