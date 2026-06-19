# -*- coding: utf-8 -*-
"""
coach_dossier.py  v4
====================
Informe PDF premium — diseño corporativo Rayo Vallecano.
Paleta: negro #111827 · rojo #E30613 · blanco.
Gráficas oscuras, cabeceras rellenas, espacio mínimo.
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
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, KeepTogether)

from src.utils.config import settings

C_RED      = colors.HexColor("#E30613")
C_RED_LT   = colors.HexColor("#FCA5A5")
C_BLACK    = colors.HexColor("#0D0D0D")
C_DARK     = colors.HexColor("#111827")
C_DARK2    = colors.HexColor("#1F2937")
C_DARK3    = colors.HexColor("#374151")
C_GREY     = colors.HexColor("#9CA3AF")
C_OFFWHITE = colors.HexColor("#F9FAFB")
C_WHITE    = colors.white
C_GREEN    = colors.HexColor("#059669")
C_AMBER    = colors.HexColor("#D97706")
C_BORDER   = colors.HexColor("#374151")
C_STRIPE   = colors.HexColor("#F1F5F9")

M_BG    = "#111827"
M_DARK2 = "#1F2937"
M_RED   = "#E30613"
M_GREY  = "#6B7280"
M_WHITE = "#F9FAFB"
M_GREEN = "#059669"
M_AMBER = "#D97706"

ROOT  = Path(__file__).resolve().parents[2]
PROC  = Path(settings()["paths"]["data_processed"])
PAGE_W, PAGE_H = A4
MARG      = 1.2 * cm
CONTENT_W = PAGE_W - 2 * MARG

AXES = [
    ("tendencia_ofensiva",   "Ofensivo"),
    ("solidez_defensiva",    "Defensivo"),
    ("presion_alta",         "Presion"),
    ("posesion",             "Posesion"),
    ("verticalidad",         "Verticalidad"),
    ("intensidad_defensiva", "Intens. def."),
    ("uso_transiciones",     "Transiciones"),
    ("flexibilidad_tactica", "Flexibilidad"),
]

RISK_LABELS = {
    "deportivo":                  "Deportivo",
    "economico":                  "Economico",
    "clausula":                   "Clausula",
    "adaptacion_laliga":          "Adapt. LaLiga",
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
        im.save(out, format="JPEG", quality=88)
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
        return build_dynamic_dna().get("target_style", {})
    except Exception:
        pass
    try:
        import yaml
        f = ROOT / "config" / "rayo_dna.yaml"
        if f.exists():
            return yaml.safe_load(f.read_text(encoding="utf-8")).get("target_style", {})
    except Exception:
        pass
    return {}


def _fmt_salary(v):
    if not v:
        return "n/d"
    return f"{v/1e6:.1f}M EUR/anio" if v >= 1e6 else f"{v/1e3:.0f}K EUR/anio"


def _img(fig, w_cm, h_cm, dpi=150):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return Image(buf, width=w_cm * cm, height=h_cm * cm)


def _styles():
    base = getSampleStyleSheet()

    def S(name, **kw):
        return ParagraphStyle(name, parent=base["BodyText"], **kw)

    return {
        "hero_name":  S("hero_name",  fontName="Helvetica-Bold", fontSize=22,
                        textColor=C_WHITE, leading=26),
        "hero_sub":   S("hero_sub",   fontName="Helvetica-Bold", fontSize=10,
                        textColor=C_RED, leading=14),
        "hero_info":  S("hero_info",  fontName="Helvetica", fontSize=9,
                        textColor=colors.HexColor("#D1D5DB"), leading=13),
        "hero_small": S("hero_small", fontName="Helvetica", fontSize=8,
                        textColor=colors.HexColor("#9CA3AF"), leading=11),
        "kpi_label":  S("kpi_label",  fontName="Helvetica", fontSize=6.5,
                        textColor=C_GREY, leading=9),
        "kpi_value":  S("kpi_value",  fontName="Helvetica-Bold", fontSize=13,
                        textColor=C_WHITE, leading=16),
        "section":    S("section",    fontName="Helvetica-Bold", fontSize=9.5,
                        textColor=C_WHITE, leading=12),
        "body":       S("body",       fontName="Helvetica", fontSize=9,
                        textColor=C_DARK3, leading=13),
        "small":      S("small",      fontName="Helvetica", fontSize=7.5,
                        textColor=C_GREY, leading=11),
        "italic":     S("italic",     fontName="Helvetica-Oblique", fontSize=7,
                        textColor=C_GREY, leading=10),
        "tag_green":  S("tag_green",  fontName="Helvetica-Bold", fontSize=7.5,
                        textColor=C_GREEN, leading=10),
        "tag_amber":  S("tag_amber",  fontName="Helvetica-Bold", fontSize=7.5,
                        textColor=C_AMBER, leading=10),
        "tag_red":    S("tag_red",    fontName="Helvetica-Bold", fontSize=7.5,
                        textColor=C_RED, leading=10),
    }


def _section_header(text, st):
    t = Table([[Paragraph(f"  {text.upper()}", st["section"])]],
              colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), C_RED),
        ("TOPPADDING",   (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return KeepTogether([Spacer(1, 5), t, Spacer(1, 3)])


def _tbl(data, col_widths=None, fs=8, hdr_bg=None):
    hdr_bg = hdr_bg or C_DARK
    t = Table(data, repeatRows=1, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0), (-1, 0), hdr_bg),
        ("TEXTCOLOR",      (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME",       (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME",       (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",       (0, 0), (-1, -1), fs),
        ("GRID",           (0, 0), (-1, -1), 0.25, C_BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, C_STRIPE]),
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",    (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 5),
        ("TOPPADDING",     (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 3),
    ]))
    return t


def _kpi_card(label, value, bg=None, fg=None, w=3.8 * cm):
    bg = bg or C_DARK2
    fg = fg or C_WHITE
    lbl = Paragraph(label.upper(),
                    ParagraphStyle("kl", fontName="Helvetica", fontSize=6.5,
                                   textColor=C_GREY, leading=9))
    val = Paragraph(str(value),
                    ParagraphStyle("kv", fontName="Helvetica-Bold", fontSize=12,
                                   textColor=fg, leading=15))
    inner = Table([[lbl], [val]], colWidths=[w - 16])
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
        ("TOPPADDING",   (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 7),
    ]))
    return card


def _radar_chart(axes, dna_target, w_cm=9.5, h_cm=9.0):
    items = [(lab, axes.get(k), dna_target.get(k, {}).get("ideal"))
             for k, lab in AXES if axes.get(k) is not None]
    if len(items) < 3:
        return None

    labs     = [i[0] for i in items]
    vals     = [float(i[1]) for i in items]
    targets  = [float(i[2]) if i[2] is not None else 50.0 for i in items]
    N        = len(labs)
    ang      = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    vals_c   = vals + vals[:1]
    tgt_c    = targets + targets[:1]
    ang_c    = ang + ang[:1]

    fig, ax = plt.subplots(figsize=(6.5, 6.5), subplot_kw=dict(polar=True))
    fig.patch.set_facecolor(M_BG)
    ax.set_facecolor(M_DARK2)

    for r, lw in [(25, 0.4), (50, 1.0), (75, 0.4), (100, 0.4)]:
        c = "#6B7280" if r == 50 else "#4B5563"
        ls = "--" if r == 50 else "-"
        ax.plot(ang_c, [r] * (N + 1), color=c, linewidth=lw,
                linestyle=ls, zorder=1)
    for a in ang:
        ax.plot([a, a], [0, 100], color="#374151", linewidth=0.5, zorder=1)

    ax.fill(ang_c, tgt_c, color="#6B7280", alpha=0.15, zorder=2)
    ax.plot(ang_c, tgt_c, color="#9CA3AF", linewidth=1.5,
            linestyle="--", zorder=3)

    ax.fill(ang_c, vals_c, color=M_RED, alpha=0.28, zorder=4)
    ax.plot(ang_c, vals_c, color=M_RED, linewidth=2.8, zorder=5)
    ax.scatter(ang, vals, color=M_RED, s=50, zorder=6,
               edgecolors=M_WHITE, linewidths=0.8)

    ax.set_xticklabels([])
    for i, (lab, v, tgt) in enumerate(zip(labs, vals, targets)):
        theta = ang[i]
        diff = v - tgt
        diff_s = f"{diff:+.0f}"
        ax.text(theta, 118, f"{lab}\n{int(v)}  ({diff_s})",
                ha="center", va="center", fontsize=7,
                color=M_WHITE, fontweight="bold", linespacing=1.2)

    ax.set_ylim(0, 100)
    ax.set_yticks([])
    ax.spines["polar"].set_visible(False)

    p1 = mpatches.Patch(color=M_RED,    alpha=0.8, label="Tecnico")
    p2 = mpatches.Patch(color="#9CA3AF", alpha=0.6, label="ADN Rayo")
    ax.legend(handles=[p1, p2], loc="lower right",
              bbox_to_anchor=(1.38, -0.05), fontsize=7.5,
              framealpha=0.85, facecolor=M_BG,
              edgecolor="#374151", labelcolor=M_WHITE)

    plt.tight_layout(pad=0.3)
    return _img(fig, w_cm, h_cm)


def _adn_chart(axes, dna_target, w_cm=16.5, h_cm=4.8):
    items = [(lab, axes.get(k), dna_target.get(k, {}).get("ideal"))
             for k, lab in AXES if axes.get(k) is not None]
    if not items:
        return None

    labels      = [i[0] for i in items]
    coach_vals  = [float(i[1]) for i in items]
    target_vals = [float(i[2]) if i[2] is not None else 50.0 for i in items]
    n = len(labels)
    y = np.arange(n)
    w = 0.38

    fig, ax = plt.subplots(figsize=(w_cm * 0.44, h_cm * 0.44))
    fig.patch.set_facecolor(M_BG)
    ax.set_facecolor(M_DARK2)

    b1 = ax.barh(y + w/2, coach_vals, w, label="Tecnico",
                 color=M_RED, alpha=0.90, zorder=3, edgecolor=M_DARK2)
    b2 = ax.barh(y - w/2, target_vals, w, label="ADN Rayo",
                 color="#4B5563", alpha=0.85, zorder=3, edgecolor=M_DARK2)

    ax.axvline(x=50, color="#6B7280", linewidth=0.8, linestyle="--", zorder=1)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8, color=M_WHITE)
    ax.set_xlim(0, 120)
    ax.tick_params(colors=M_WHITE)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#374151")
    ax.spines["bottom"].set_color("#374151")

    for i, (cv, tv) in enumerate(zip(coach_vals, target_vals)):
        diff = cv - tv
        dc   = M_GREEN if abs(diff) <= 10 else "#EF4444"
        ax.text(cv + 1.2, i + w/2, f"{cv:.0f}", va="center",
                fontsize=7.5, color=M_WHITE, fontweight="bold")
        ax.text(tv + 1.2, i - w/2, f"{tv:.0f}", va="center",
                fontsize=7.5, color="#9CA3AF")
        ax.text(115, i + w/2, f"{diff:+.0f}", va="center",
                fontsize=7.5, color=dc, fontweight="bold")

    ax.set_title("Tecnico (rojo)  vs  ADN objetivo Rayo (gris)    Delta",
                 fontsize=9, color="#D1D5DB", pad=6, loc="left")

    legend_patches = [
        mpatches.Patch(color=M_RED,    alpha=0.9, label="Tecnico"),
        mpatches.Patch(color="#4B5563", alpha=0.85, label="ADN Rayo"),
    ]
    ax.legend(handles=legend_patches, loc="lower right", fontsize=7.5,
              framealpha=0.85, facecolor=M_BG, edgecolor="#374151",
              labelcolor=M_WHITE)

    plt.tight_layout(pad=0.3)
    return _img(fig, w_cm, h_cm)


def _score_gauge(score: float, w_cm=4.0, h_cm=2.2):
    fig, ax = plt.subplots(figsize=(w_cm * 0.44, h_cm * 0.44))
    fig.patch.set_facecolor(M_BG)
    ax.set_facecolor(M_BG)
    ax.set_aspect("equal")
    ax.axis("off")

    theta = np.linspace(np.pi, 0, 200)
    r     = 1.0
    ax.plot(np.cos(theta) * r, np.sin(theta) * r,
            color="#374151", linewidth=14, solid_capstyle="round")

    fill_theta = np.linspace(np.pi, np.pi - np.pi * (score / 10), 200)
    col = M_GREEN if score >= 7 else (M_AMBER if score >= 5 else M_RED)
    ax.plot(np.cos(fill_theta) * r, np.sin(fill_theta) * r,
            color=col, linewidth=14, solid_capstyle="round", zorder=2)

    ax.text(0, 0.15, f"{score}", ha="center", va="center",
            fontsize=22, color=M_WHITE, fontweight="bold")
    ax.text(0, -0.25, "FIT RAYO / 10", ha="center", va="center",
            fontsize=7, color="#9CA3AF")

    ax.set_xlim(-1.3, 1.3)
    ax.set_ylim(-0.4, 1.3)
    plt.tight_layout(pad=0.1)
    return _img(fig, w_cm, h_cm)


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
    rows = [["Temp.", "Equipo", "Pos%", "Tiros/p", "Goles/p",
             "Encaj./p", "Recup./p", "P. cero"]]
    for _, t in ten.sort_values("season", ascending=False).iterrows():
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

        def pg(c): return f"{float(r.get(c) or 0)/g:.1f}"

        rows.append([
            str(t["season"]),
            str(t["team"])[:22],
            str(int(r.get("possession_percentage") or 0)),
            pg("total_shots"), pg("goals"), pg("goals_conceded"),
            pg("recoveries"), str(int(r.get("clean_sheets") or 0)),
        ])
    return rows if len(rows) > 1 else None


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

    score_10  = ev.get("score_10", 0)
    score_num = float(score_10) if score_10 not in (None, "n/d", "") else 0.0

    if score_num >= 7:
        rec_label, rec_col, rec_bg = "RECOMENDADO",    C_GREEN, colors.HexColor("#064E3B")
    elif score_num >= 5:
        rec_label, rec_col, rec_bg = "VALORAR",        C_AMBER, colors.HexColor("#451A03")
    else:
        rec_label, rec_col, rec_bg = "NO RECOMENDADO", C_RED,   colors.HexColor("#450A0A")

    # Cabecera
    hdr_l = Paragraph(
        "<font color='white'><b>RAYO VALLECANO — DIRECCION DEPORTIVA</b></font>",
        ParagraphStyle("hl", fontName="Helvetica-Bold", fontSize=9,
                       textColor=C_WHITE, leading=12))
    hdr_r = Paragraph(
        f"<font color='#FCA5A5'>{date.today().strftime('%d %b %Y').lstrip('0')}</font>",
        ParagraphStyle("hr", fontName="Helvetica", fontSize=8.5,
                       textColor=C_RED_LT, leading=12, alignment=2))
    hdr = Table([[hdr_l, hdr_r]],
                colWidths=[CONTENT_W * 0.65, CONTENT_W * 0.35])
    hdr.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), C_BLACK),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING",   (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 7),
        ("LINEBELOW",    (0, 0), (-1, -1), 2.5, C_RED),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 6))

    # Hero card
    img_bytes = _load_photo_bytes(c["name"])
    foto_img  = None
    if img_bytes:
        try:
            foto_img = _scaled_image(img_bytes, 3.2, 3.8)
        except Exception:
            foto_img = None

    gauge = _score_gauge(score_num)

    hero_texts = [
        Paragraph(c["name"], st["hero_name"]),
        Spacer(1, 3),
        Paragraph(
            f"{c.get('nationality', '')}  .  {c.get('age', '?')} anios  .  "
            f"Ultimo club: <b>{c.get('last_club', 'n/d')}</b>",
            st["hero_sub"]),
        Spacer(1, 5),
        Paragraph(
            f'<font color="#9CA3AF">Estilo:</font> '
            f'<font color="#F9FAFB"><b>{c.get("style_main", "n/d")}</b></font>',
            st["hero_info"]),
        Spacer(1, 2),
        Paragraph(
            ", ".join(c.get("style_tags", []) or []),
            st["hero_small"]),
        Spacer(1, 5),
        Paragraph(
            f'<font color="#9CA3AF">Situacion:</font> '
            f'<font color="#F9FAFB">{"Libre" if c.get("available") else "Con equipo"}</font>'
            f'  .  <font color="#9CA3AF">{c.get("contract_status", "")}</font>',
            st["hero_info"]),
        Spacer(1, 2),
        Paragraph(
            f'<font color="#9CA3AF">LaLiga:</font> '
            f'<font color="#F9FAFB">{c.get("laliga_seasons", 0)} temporadas</font>',
            st["hero_info"]),
    ]

    GAUGE_W = 4.4 * cm
    FOTO_W  = 3.4 * cm
    TXT_W   = CONTENT_W - GAUGE_W - (FOTO_W if foto_img else 0) - 0.5 * cm

    if foto_img:
        inner = Table([[foto_img, hero_texts, gauge]],
                      colWidths=[FOTO_W, TXT_W, GAUGE_W])
        inner.setStyle(TableStyle([
            ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING",  (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (0, -1), 12),
            ("LEFTPADDING",  (1, 0), (1, -1), 0),
            ("RIGHTPADDING", (1, 0), (1, -1), 8),
            ("ALIGN",        (2, 0), (2, -1), "CENTER"),
        ]))
    else:
        inner = Table([[hero_texts, gauge]],
                      colWidths=[TXT_W + FOTO_W, GAUGE_W])
        inner.setStyle(TableStyle([
            ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING",  (0, 0), (-1, -1), 0),
            ("ALIGN",        (1, 0), (1, -1), "CENTER"),
        ]))

    hero_card = Table([[inner]], colWidths=[CONTENT_W])
    hero_card.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), C_DARK),
        ("LEFTPADDING",  (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING",   (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 14),
    ]))
    story.append(hero_card)
    story.append(Spacer(1, 6))

    # KPI strip
    sal_str = _fmt_salary(c.get("salary_estimate_eur"))
    ll_str  = f"{c.get('laliga_seasons', 0)} temp."
    avail_s = "Libre" if c.get("available") else "Con contrato"
    kpi_w   = CONTENT_W / 5

    kpi_strip = Table([[
        _kpi_card("Recomendacion", rec_label, bg=rec_bg, fg=rec_col, w=kpi_w),
        _kpi_card("Fit Rayo",      f"{score_10}/10",    w=kpi_w),
        _kpi_card("Salario est.",  sal_str,             w=kpi_w),
        _kpi_card("Disponib.",     avail_s,             w=kpi_w),
        _kpi_card("Exp. LaLiga",   ll_str,              w=kpi_w),
    ]], colWidths=[kpi_w] * 5)
    kpi_strip.setStyle(TableStyle([
        ("LEFTPADDING",  (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING",   (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 0),
    ]))
    story.append(kpi_strip)
    story.append(Spacer(1, 5))

    # Descripcion automatica
    desc = c.get("description_auto", "")
    if desc:
        desc_t = Table([[Paragraph(desc, st["body"])]], colWidths=[CONTENT_W])
        desc_t.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, -1), C_DARK2),
            ("BOX",          (0, 0), (-1, -1), 0.5, C_BORDER),
            ("LEFTPADDING",  (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING",   (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 7),
            ("LINEABOVE",    (0, 0), (-1, -1), 2, C_RED),
        ]))
        story.append(desc_t)
        story.append(Spacer(1, 5))

    # Fortalezas / Contras / Riesgos
    pros  = (ev.get("pros_auto",    []) or []) + man.get("pros",    [])
    cons  = (ev.get("contras_auto", []) or []) + man.get("contras", [])
    risks = ev.get("risks", {})

    pcr_rows = []
    if pros:
        pcr_rows.append([
            Paragraph("FORTALEZAS", st["tag_green"]),
            Paragraph("  .  ".join(pros), st["small"]),
        ])
    if cons:
        pcr_rows.append([
            Paragraph("CONTRAS", st["tag_amber"]),
            Paragraph("  .  ".join(cons), st["small"]),
        ])
    if risks:
        risk_text = "  .  ".join(
            f"{RISK_LABELS.get(k, k)}: {v}" for k, v in risks.items())
        pcr_rows.append([
            Paragraph("RIESGOS", st["tag_red"]),
            Paragraph(risk_text, st["small"]),
        ])
    if pcr_rows:
        TAG_W = 2.8 * cm
        pcr_t = Table(pcr_rows, colWidths=[TAG_W, CONTENT_W - TAG_W])
        pcr_t.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (0, -1), C_DARK2),
            ("BACKGROUND",   (1, 0), (1, -1), C_DARK),
            ("GRID",         (0, 0), (-1, -1), 0.3, C_BORDER),
            ("VALIGN",       (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING",  (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING",   (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ]))
        story.append(pcr_t)
        story.append(Spacer(1, 5))

    # Estilo radar + tabla ejes
    story.append(_section_header("Estilo de juego - radar tactico", st))

    radar_img = _radar_chart(axes, dna_target, w_cm=9.8, h_cm=9.2)

    ax_rows = [["Eje", "Tecnico", "ADN Rayo", "Dif."]]
    for k, lab in AXES:
        if axes.get(k) is None:
            continue
        cv   = int(float(axes[k]))
        tv_r = dna_target.get(k, {}).get("ideal")
        tv   = int(float(tv_r)) if tv_r is not None else None
        diff = cv - tv if tv is not None else None
        ds   = (f"+{abs(int(float(diff)))}" if diff is not None and diff >= 0
                else f"-{abs(int(float(diff)))}" if diff is not None else "n/d")
        ax_rows.append([
            lab, str(cv),
            str(tv) if tv is not None else "n/d",
            ds,
        ])
    if axes.get("posesion_pct_real") is not None:
        ax_rows.append(["Posesion real", f"{axes['posesion_pct_real']}%", "-", "-"])

    axes_tbl = _tbl(ax_rows,
                    col_widths=[3.6 * cm, 1.4 * cm, 2.0 * cm, 1.4 * cm], fs=7.5)

    src_label = {
        "opta":       "Datos OPTA reales",
        "yaml_proxy": "Estimacion (sin datos OPTA - perfil declarado)",
        "none":       "Sin datos en la plataforma",
    }.get(c.get("axes_source", "opta"), "OPTA")

    L_W = 10.0 * cm
    R_W = CONTENT_W - L_W
    left_cell  = [radar_img] if radar_img else [Spacer(1, 1)]
    right_cell = [
        Paragraph("EJES VS ADN RAYO",
                  ParagraphStyle("rh", fontName="Helvetica-Bold",
                                 fontSize=8.5, textColor=C_DARK3, leading=11)),
        Spacer(1, 4),
        axes_tbl,
        Spacer(1, 4),
        Paragraph(
            "100 = elite de liga  .  50 = media  .  0 = peor.  "
            "Percentil del equipo dirigido vs la liga.",
            st["italic"]),
        Spacer(1, 4),
        Paragraph(f"Fuente: {src_label}", st["italic"]),
    ]
    two_col = Table([[left_cell, right_cell]], colWidths=[L_W, R_W])
    two_col.setStyle(TableStyle([
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING",  (1, 0), (1, -1), 10),
    ]))
    story.append(two_col)

    # Comparativa tactica
    story.append(_section_header("Comparativa tactica vs ADN Rayo", st))
    adn_chart = _adn_chart(axes, dna_target, w_cm=CONTENT_W / cm, h_cm=4.8)
    if adn_chart:
        story.append(adn_chart)
        story.append(Paragraph(
            "Verde: diferencia <=10 pts (alineado)  .  "
            "Rojo: diferencia >10 pts (posible desajuste tactico).  "
            "Delta = Tecnico - ADN objetivo Rayo.",
            st["italic"]))

    # Evaluacion Fit Rayo
    story.append(_section_header("Evaluacion - Fit Rayo", st))

    sub = ev.get("subscores", {})
    sub_labels = {
        "estilo":       ("Cercania al ADN Rayo (estilo tactico)",  "~55%"),
        "laliga":       ("Experiencia LaLiga",                      "15%"),
        "budget":       ("Encaje salarial vs presupuesto club",     "15%"),
        "squad_compat": ("Compatibilidad con la plantilla",         "15%"),
    }
    methodo = {
        "estilo":       "Distancia coseno ejes tecnico vs ADN Rayo",
        "laliga":       "25 pts/temp 1a  .  10 pts/temp 2a  .  max 100",
        "budget":       "Salario estimado vs margen salarial del club",
        "squad_compat": "Similitud estilo tecnico vs perfil plantilla",
    }
    if sub:
        tbl_data = [["Sub-score", "Peso", "Valor /100", "Metodologia"]]
        for k, (label, weight) in sub_labels.items():
            v = sub.get(k)
            if v is not None:
                tbl_data.append([label, weight, str(int(float(v))),
                                  methodo.get(k, "n/d")])
        if len(tbl_data) > 1:
            story.append(_tbl(tbl_data,
                              col_widths=[4.5 * cm, 1.2 * cm,
                                          1.8 * cm, 9.0 * cm], fs=8))

    story.append(Spacer(1, 3))
    story.append(Paragraph(
        f"Score global: <b>{score_10}/10</b>  ({score_num*10:.0f}/100)  .  "
        "Formula: Fit = (Estilo x 0.55) + (LaLiga x 0.15) + (Presup. x 0.15) + (Plantilla x 0.15).",
        st["body"]))
    story.append(Spacer(1, 2))
    story.append(Paragraph(
        "Estilo: similitud normalizada (coseno) entre los 8 ejes del tecnico y el ADN "
        "objetivo Rayo. LaLiga: 25 pts/temp en Primera, 10 en Segunda, max. 100.",
        st["italic"]))

    # Equipos dirigidos
    tst = _team_seasons_table(c["name"])
    if tst:
        story.append(_section_header("Equipos dirigidos - estadisticas de equipo", st))
        story.append(Paragraph(
            "Metricas promediadas por partido para cada temporada del tecnico. "
            "Fuente: team_seasons.parquet x coach_tenures.csv.",
            st["italic"]))
        story.append(Spacer(1, 3))
        col_w = [1.8 * cm, 4.0 * cm, 1.2 * cm, 1.5 * cm,
                 1.5 * cm, 1.5 * cm, 1.5 * cm, 1.5 * cm]
        story.append(_tbl(tst, col_widths=col_w, fs=7.5))
        story.append(Paragraph(
            "Pos% = posesion media  .  /p = por partido  .  P. cero = porterias a cero.",
            st["italic"]))

    # Footer
    story.append(Spacer(1, 8))
    cov    = c.get("coverage", {})
    n_rows = cov.get("n_rows", 0)
    teams_s = ", ".join(cov.get("teams", []) or []) or "n/d"
    foot = Table([[
        Paragraph(
            f"Cobertura OPTA: {teams_s}  .  {n_rows} temporadas  .  "
            f"Generado {date.today().strftime('%d %b %Y').lstrip('0')}  .  "
            "Rayo Vallecano - Direccion Deportiva  .  Confidencial.",
            st["italic"]),
    ]], colWidths=[CONTENT_W])
    foot.setStyle(TableStyle([
        ("LINEABOVE",    (0, 0), (-1, -1), 1.5, C_RED),
        ("BACKGROUND",   (0, 0), (-1, -1), C_DARK),
        ("TOPPADDING",   (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ("LEFTPADDING",  (0, 0), (-1, -1), 8),
    ]))
    story.append(foot)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=MARG, bottomMargin=MARG,
        leftMargin=MARG, rightMargin=MARG,
    )
    doc.build(story)
    buf.seek(0)
    return (
        f"informe_entrenador_{_n(c['name']).replace(' ', '_')}.pdf",
        buf.read(),
    )
