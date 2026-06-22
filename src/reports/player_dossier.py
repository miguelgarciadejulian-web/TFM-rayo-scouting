# -*- coding: utf-8 -*-
"""
player_dossier.py  v4
=====================
Informe PDF premium — diseño corporativo Rayo Vallecano.
Paleta: negro #111827 · rojo #E30613 · blanco.
Graficas oscuras, cabeceras rellenas, espacio minimo.
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
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, KeepTogether)

from src.utils.config import settings
from src.profiling.player_profile import (
    career_aggregate, add_role_percentiles, profile_player_row,
    ROLE_LABELS, METRIC_LABELS)
from src.fit.player_fit import evaluate_player_fit
from src.utils.market import get_value

# Paleta Rayo
C_RED      = colors.HexColor("#E30613")
C_RED_LT   = colors.HexColor("#FCA5A5")
C_BLACK    = colors.HexColor("#0D0D0D")
C_DARK     = colors.HexColor("#111827")
C_DARK2    = colors.HexColor("#1F2937")
C_DARK3    = colors.HexColor("#374151")
C_GREY     = colors.HexColor("#6B7280")
C_LGREY    = colors.HexColor("#9CA3AF")
C_OFFWHITE = colors.HexColor("#F9FAFB")
C_WHITE    = colors.white
C_GREEN    = colors.HexColor("#059669")
C_AMBER    = colors.HexColor("#D97706")
C_BLUE     = colors.HexColor("#2563EB")
C_BORDER   = colors.HexColor("#374151")
C_STRIPE   = colors.HexColor("#F1F5F9")

M_BG    = "#111827"
M_DARK2 = "#1F2937"
M_RED   = "#E30613"
M_WHITE = "#F9FAFB"
M_GREEN = "#059669"
M_AMBER = "#D97706"
M_BLUE  = "#2563EB"

PAGE_W, PAGE_H = A4
MARGIN    = 1.2 * cm
CONTENT_W = PAGE_W - 2 * MARGIN

PROC = Path(settings()["paths"]["data_processed"])

METRIC_GROUPS = {
    "Ataque":   ["goals_p90", "total_shots_p90", "shots_on_target_inc_goals_p90",
                 "total_touches_in_opposition_box_p90"],
    "Creacion": ["key_passes_attempt_assists_p90", "goal_assists_p90",
                 "successful_dribbles_p90", "successful_crosses_open_play_p90"],
    "Pase":     ["total_successful_passes_excl_crosses_corners_p90",
                 "successful_passes_opposition_half_p90", "successful_long_passes_p90"],
    "Defensa":  ["tackles_won_p90", "interceptions_p90",
                 "recoveries_p90", "blocks_p90", "total_clearances_p90"],
    "Duelos":   ["aerial_duels_won_p90", "ground_duels_won_p90",
                 "total_losses_of_possession_p90"],
}

CAREER_TOTALS = [
    ("minutes", "Minutos"), ("goals", "Goles"), ("goal_assists", "Asistencias"),
    ("total_shots", "Tiros"), ("shots_on_target_inc_goals", "T. a puerta"),
    ("key_passes_attempt_assists", "Pases clave"), ("successful_dribbles", "Regates"),
    ("total_touches_in_opposition_box", "Toques area rival"),
    ("tackles_won", "Entradas ganad."), ("interceptions", "Intercepciones"),
    ("recoveries", "Recuperaciones"), ("aerial_duels_won", "Duelos aereos"),
]

SEASON_COLS = [
    ("season", "Temp."), ("team", "Equipo"), ("minutes", "Min"),
    ("goals", "G"), ("goal_assists", "A"), ("total_shots", "Tir"),
    ("shots_on_target_inc_goals", "TaP"), ("key_passes_attempt_assists", "PC"),
    ("successful_dribbles", "Reg"), ("total_touches_in_opposition_box", "ToqA"),
    ("tackles_won", "Ent"), ("interceptions", "Int"), ("recoveries", "Rec"),
    ("aerial_duels_won", "Aer"), ("total_clearances", "Desp"),
]


def _n(s):
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()

def _enriched():
    p = PROC / "player_seasons_enriched.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()

def _needs():
    import json
    p = PROC / "squad_profile.json"
    return json.load(open(p, encoding="utf-8")).get("needs", {}) if p.exists() else {}

def _img(fig, w_cm, h_cm, dpi=150):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return Image(buf, width=w_cm * cm, height=h_cm * cm)

def _est_salary(mv_eur, league="", minutes=0, age=25, position=""):
    try:
        mv = float(mv_eur or 0)
        if mv <= 0: return "n/d"
        ll = str(league).lower()
        if any(x in ll for x in ["primera","laliga","spain_primera"]): r = 0.15
        elif any(x in ll for x in ["segunda","spain_segunda"]):        r = 0.10
        elif any(x in ll for x in ["premier","england"]):              r = 0.18
        elif any(x in ll for x in ["bundesliga","germany"]):           r = 0.14
        elif any(x in ll for x in ["serie","italy"]):                  r = 0.13
        elif any(x in ll for x in ["ligue","france"]):                 r = 0.12
        else:                                                            r = 0.11
        sc  = 0.90 if mv >= 30e6 else (0.95 if mv >= 15e6 else (1.00 if mv >= 5e6 else 1.08))
        mn  = float(minutes or 0)
        mm_ = 1.10 if mn >= 2500 else (1.05 if mn >= 1800 else (0.95 if mn >= 900 else 0.85))
        am  = 1.05 if 24 <= age <= 28 else (1.00 if 22 <= age <= 30 else 0.90)
        pu  = str(position).upper()
        pm  = 1.08 if pu in ("ST","LW","RW") else (1.03 if pu in ("AM","CM") else 1.00)
        sal = mv * r * sc * mm_ * am * pm
        return f"~{sal/1e6:.1f}M EUR/ano" if sal >= 1e6 else f"~{sal/1e3:.0f}K EUR/ano"
    except Exception:
        return "n/d"


def _styles():
    base = getSampleStyleSheet()
    def S(name, **kw):
        return ParagraphStyle(name, parent=base["BodyText"], **kw)
    return {
        "hero_name":  S("hero_name",  fontName="Helvetica-Bold", fontSize=22, textColor=C_WHITE, leading=26),
        "hero_sub":   S("hero_sub",   fontName="Helvetica-Bold", fontSize=10, textColor=C_RED, leading=14),
        "hero_info":  S("hero_info",  fontName="Helvetica", fontSize=9, textColor=colors.HexColor("#D1D5DB"), leading=13),
        "hero_small": S("hero_small", fontName="Helvetica", fontSize=8, textColor=colors.HexColor("#9CA3AF"), leading=11),
        "section":    S("section",    fontName="Helvetica-Bold", fontSize=9.5, textColor=C_WHITE, leading=12),
        "kpi_label":  S("kpi_label",  fontName="Helvetica", fontSize=6.5, textColor=C_LGREY, leading=9),
        "kpi_value":  S("kpi_value",  fontName="Helvetica-Bold", fontSize=13, textColor=C_WHITE, leading=16),
        "body":       S("body",       fontName="Helvetica", fontSize=8.5, textColor=C_DARK3, leading=13),
        "small":      S("small",      fontName="Helvetica", fontSize=7.5, textColor=C_GREY, leading=11),
        "italic":     S("italic",     fontName="Helvetica-Oblique", fontSize=7, textColor=C_GREY, leading=10),
        "tag_green":  S("tag_green",  fontName="Helvetica-Bold", fontSize=7.5, textColor=C_GREEN, leading=10),
        "tag_amber":  S("tag_amber",  fontName="Helvetica-Bold", fontSize=7.5, textColor=C_AMBER, leading=10),
    }


def _section_header(text, st):
    t = Table([[Paragraph(f"  {text.upper()}", st["section"])]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0,0),(-1,-1), C_RED),
        ("TOPPADDING",   (0,0),(-1,-1), 5),
        ("BOTTOMPADDING",(0,0),(-1,-1), 5),
        ("LEFTPADDING",  (0,0),(-1,-1), 6),
        ("RIGHTPADDING", (0,0),(-1,-1), 6),
        ("VALIGN",       (0,0),(-1,-1), "MIDDLE"),
    ]))
    return KeepTogether([Spacer(1,5), t, Spacer(1,3)])


def _tbl(data, col_widths=None, fs=7.5, hdr_bg=None):
    hdr_bg = hdr_bg or C_DARK
    t = Table(data, repeatRows=1, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND",     (0,0),(-1,0), hdr_bg),
        ("TEXTCOLOR",      (0,0),(-1,0), C_WHITE),
        ("FONTNAME",       (0,0),(-1,0), "Helvetica-Bold"),
        ("FONTNAME",       (0,1),(-1,-1), "Helvetica"),
        ("FONTSIZE",       (0,0),(-1,-1), fs),
        ("ROWBACKGROUNDS", (0,1),(-1,-1), [C_WHITE, C_STRIPE]),
        ("GRID",           (0,0),(-1,-1), 0.25, C_BORDER),
        ("VALIGN",         (0,0),(-1,-1), "MIDDLE"),
        ("LEFTPADDING",    (0,0),(-1,-1), 5),
        ("RIGHTPADDING",   (0,0),(-1,-1), 5),
        ("TOPPADDING",     (0,0),(-1,-1), 3),
        ("BOTTOMPADDING",  (0,0),(-1,-1), 3),
    ]))
    return t


def _kpi_card(label, value, st, bg=None, fg=None, w=3.2*cm):
    bg = bg or C_DARK2
    fg = fg or C_WHITE
    lbl = Paragraph(label.upper(), st["kpi_label"])
    val = Paragraph(str(value), ParagraphStyle("kv", fontName="Helvetica-Bold", fontSize=12, textColor=fg, leading=15))
    inner = Table([[lbl],[val]], colWidths=[w-16])
    inner.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
                                ("TOPPADDING",(0,0),(-1,-1),1),("BOTTOMPADDING",(0,0),(-1,-1),1)]))
    card = Table([[inner]], colWidths=[w])
    card.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1), bg),
        ("BOX",(0,0),(-1,-1), 0.5, C_BORDER),
        ("LEFTPADDING",(0,0),(-1,-1), 8),("RIGHTPADDING",(0,0),(-1,-1), 8),
        ("TOPPADDING",(0,0),(-1,-1), 7),("BOTTOMPADDING",(0,0),(-1,-1), 7),
    ]))
    return card


def _radar_chart(role_scores, pool_avg, w_cm=9.5, h_cm=9.0):
    items = list(role_scores.items())[:8]
    if not items: return None
    labs = [ROLE_LABELS.get(k, k) for k,_ in items]
    vals = [float(v) for _,v in items]
    avgs = [float(pool_avg.get(k,50)) for k,_ in items]
    N    = len(labs)
    ang  = np.linspace(0, 2*np.pi, N, endpoint=False).tolist()
    fig, ax = plt.subplots(figsize=(6,6), subplot_kw=dict(polar=True))
    fig.patch.set_facecolor(M_BG); ax.set_facecolor(M_DARK2)
    for r,lw in [(25,.5),(50,1.0),(75,.5),(100,.5)]:
        c = "#6B7280" if r==50 else "#4B5563"
        ls = "--" if r==50 else "-"
        ax.plot(ang+ang[:1], [r]*(N+1), color=c, linewidth=lw, linestyle=ls, zorder=1)
    for a in ang:
        ax.plot([a,a],[0,100], color="#374151", linewidth=0.5, zorder=1)
    av_c = avgs+avgs[:1]; ac_c = ang+ang[:1]
    ax.fill(ac_c, av_c, color="#6B7280", alpha=0.18, zorder=2)
    ax.plot(ac_c, av_c, color="#9CA3AF", linewidth=1.5, linestyle="--", zorder=3)
    vl_c = vals+vals[:1]
    ax.fill(ac_c, vl_c, color=M_RED, alpha=0.30, zorder=4)
    ax.plot(ac_c, vl_c, color=M_RED, linewidth=2.8, zorder=5)
    ax.scatter(ang, vals, color=M_RED, s=50, zorder=6, edgecolors="white", linewidths=0.8)
    ax.set_xticklabels([])
    for i,(lab,v) in enumerate(zip(labs,vals)):
        ax.text(ang[i], 116, f"{lab}\n{int(v)}", ha="center", va="center",
                fontsize=7.5, color=M_WHITE, fontweight="bold", linespacing=1.2)
    ax.set_ylim(0,100); ax.set_yticks([]); ax.spines["polar"].set_visible(False)
    p1 = mpatches.Patch(color=M_RED, alpha=0.8, label="Jugador")
    p2 = mpatches.Patch(color="#9CA3AF", alpha=0.6, label="Media posicion")
    ax.legend(handles=[p1,p2], loc="lower right", bbox_to_anchor=(1.38,-0.05),
              fontsize=7.5, framealpha=0.85, facecolor=M_BG, edgecolor="#374151", labelcolor=M_WHITE)
    plt.tight_layout(pad=0.3)
    return _img(fig, w_cm, h_cm)


def _fit_chart(fit, prof, w_cm=16.5, h_cm=3.2):
    pot_map = {"muy alto":95,"alto":80,"estable":65,"en meseta":50,"veterania":35}
    comps = [
        ("Compatib. plantilla  (40%)",  fit.get("compatibilidad_plantilla",0)),
        ("Compatib. entrenador  (25%)", fit.get("compatibilidad_entrenador",0)),
        ("Rendimiento en rol  (20%)",   prof.get("primary_score") or 50),
        ("Potencial / edad  (15%)",     pot_map.get(prof.get("potential",""), 55)),
    ]
    labels = [c[0] for c in comps]
    scores = [float(c[1]) for c in comps]
    bar_c  = [M_GREEN if s>=68 else (M_AMBER if s>=44 else "#EF4444") for s in scores]
    fig, ax = plt.subplots(figsize=(w_cm*0.44, h_cm*0.44))
    fig.patch.set_facecolor(M_BG); ax.set_facecolor(M_DARK2)
    bars = ax.barh(labels, scores, color=bar_c, height=0.55, alpha=0.92, edgecolor=M_DARK2)
    ax.axvline(x=50, color="#4B5563", linewidth=1.0, linestyle="--", zorder=0)
    ax.set_xlim(0,115)
    ax.tick_params(labelsize=8, colors=M_WHITE)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#374151"); ax.spines["bottom"].set_color("#374151")
    for bar,score in zip(bars,scores):
        ax.text(min(score+2,111), bar.get_y()+bar.get_height()/2,
                f"{score:.0f}", va="center", fontsize=9.5, fontweight="bold", color=M_WHITE)
    fit_10 = fit.get("global_fit_10","?")
    ax.set_title(f"FIT RAYO  {fit_10}/10", fontsize=11, color=M_RED, fontweight="bold", pad=6, loc="left")
    plt.tight_layout(pad=0.3)
    return _img(fig, w_cm, h_cm)


def _top_pct_chart(crow, pool, top_n=12, w_cm=16.5):
    all_m = []
    for grp, metrics in METRIC_GROUPS.items():
        for m in metrics:
            if m not in pool.columns: continue
            ser = pd.to_numeric(pool[m], errors="coerce")
            pr  = ser.rank(pct=True)*100
            idx = pool.index[pool["name"]==crow.get("name")]
            if len(idx)==0: continue
            pct = pr.get(idx[0])
            if pd.notna(pct):
                all_m.append((METRIC_LABELS.get(m,m), float(pct)))
    if not all_m: return None
    all_m.sort(key=lambda x:-x[1])
    top  = all_m[:top_n]
    labs = [t[0] for t in top]; vals = [t[1] for t in top]
    bar_c = [M_GREEN if v>=80 else (M_BLUE if v>=60 else (M_AMBER if v>=40 else "#EF4444")) for v in vals]
    h_cm2 = max(3.0, len(top)*0.50)
    fig, ax = plt.subplots(figsize=(w_cm*0.44, h_cm2*0.44))
    fig.patch.set_facecolor(M_BG); ax.set_facecolor(M_DARK2)
    bars = ax.barh(labs, vals, color=bar_c, height=0.60, alpha=0.92, edgecolor=M_DARK2)
    ax.axvline(x=50, color="#4B5563", linewidth=1.0, linestyle="--", zorder=0)
    ax.set_xlim(0,115)
    ax.tick_params(labelsize=7.5, colors=M_WHITE)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#374151"); ax.spines["bottom"].set_color("#374151")
    for bar,v in zip(bars,vals):
        ax.text(min(v+1.5,111), bar.get_y()+bar.get_height()/2,
                f"{v:.0f}", va="center", fontsize=8.5, fontweight="bold", color=M_WHITE)
    ax.set_title(f"Top {top_n} percentiles vs misma posicion", fontsize=9, color="#D1D5DB", pad=5, loc="left")
    legend_p = [mpatches.Patch(color=M_GREEN,label=">=80 Elite"),
                mpatches.Patch(color=M_BLUE, label=">=60 Bueno"),
                mpatches.Patch(color=M_AMBER,label=">=40 Medio"),
                mpatches.Patch(color="#EF4444",label="<40 Bajo")]
    ax.legend(handles=legend_p, loc="lower right", fontsize=6.5, framealpha=0.8,
              facecolor=M_BG, edgecolor="#374151", labelcolor=M_WHITE, ncol=2)
    plt.tight_layout(pad=0.3)
    return _img(fig, w_cm, h_cm2)


def _group_chart(group_name, metrics, crow, pool, w_cm=8.0):
    rows = []
    for m in metrics:
        if m not in pool.columns: continue
        ser = pd.to_numeric(pool[m], errors="coerce")
        pr  = ser.rank(pct=True)*100
        idx = pool.index[pool["name"]==crow.get("name")]
        if len(idx)==0: continue
        pct = pr.get(idx[0])
        v90 = float(crow[m]) if m in crow.index and pd.notna(crow.get(m)) else None
        if pd.notna(pct):
            rows.append((METRIC_LABELS.get(m,m), float(pct), v90))
    if not rows: return None
    labs  = [r[0] for r in rows]
    vals  = [r[1] for r in rows]
    bar_c = [M_GREEN if v>=80 else (M_BLUE if v>=60 else (M_AMBER if v>=40 else "#EF4444")) for v in vals]
    h_cm2 = max(1.8, len(rows)*0.44)
    fig, ax = plt.subplots(figsize=(w_cm*0.44, h_cm2*0.44))
    fig.patch.set_facecolor(M_BG); ax.set_facecolor(M_DARK2)
    ax.barh(labs, vals, color=bar_c, height=0.62, alpha=0.90, edgecolor=M_DARK2)
    ax.axvline(x=50, color="#4B5563", linewidth=0.8, linestyle="--", zorder=0)
    ax.set_xlim(0,110)
    ax.tick_params(labelsize=6.5, colors=M_WHITE)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#374151"); ax.spines["bottom"].set_color("#374151")
    for i,(r_item) in enumerate(rows):
        v90_s = f"  {r_item[2]:.2f}" if r_item[2] is not None else ""
        ax.text(min(r_item[1]+1,107), i, f"{r_item[1]:.0f}{v90_s}",
                va="center", fontsize=6.5, color=M_WHITE, fontweight="bold")
    ax.set_title(group_name, fontsize=8.5, color=M_RED, fontweight="bold", pad=4, loc="left")
    plt.tight_layout(pad=0.3)
    return _img(fig, w_cm, h_cm2)


def _build_hero(cname, crow, mv, prof, fit, foto, sal_s, st):
    team_s   = str(crow.get("team",""))
    league_s = str(crow.get("league","")).replace("_"," ")
    pos_s    = str(mv.get("position") or crow.get("position_group") or "")
    age_v    = int(float(mv.get("age") or 0)) if mv.get("age") else 0
    ht_s     = str(mv.get("height") or "")
    _ft = {"right":"Der.","left":"Izq.","both":"Ambos","derecho":"Der.","zurdo":"Izq."}
    foot_s   = _ft.get(str(mv.get("foot") or "").strip().lower(), str(mv.get("foot") or ""))
    role_lbl = prof.get("primary_role_label","n/d")
    bio = "  .  ".join(filter(None,[
        f"{age_v} anos" if age_v else None, ht_s or None,
        f"pie {foot_s}" if foot_s else None, pos_s or None,
    ]))
    fit_10 = fit.get("global_fit_10","?") if fit else "?"
    fit_v  = fit.get("global_fit",0) if fit else 0
    fit_col_s = "#059669" if fit_v>=65 else ("#D97706" if fit_v>=45 else "#EF4444")
    txt = [
        Paragraph(cname, st["hero_name"]), Spacer(1,3),
        Paragraph(f"{team_s}  .  {league_s}", st["hero_sub"]), Spacer(1,5),
        Paragraph(bio, st["hero_info"]), Spacer(1,4),
        Paragraph(f'<font color="#9CA3AF">Rol principal:</font> <font color="#F9FAFB"><b>{role_lbl}</b></font>', st["hero_info"]),
        Spacer(1,2),
        Paragraph('<font color="#9CA3AF">Roles sec.:</font> <font color="#D1D5DB">'
                  + ", ".join(prof.get("secondary_roles_labels",[]) or []) + "</font>", st["hero_small"]),
        Spacer(1,6),
        Paragraph(f'<font color="#9CA3AF">Salario est.:</font> <font color="{fit_col_s}"><b>{sal_s}</b></font>', st["hero_info"]),
    ]
    badge_val_st = ParagraphStyle("bv", fontName="Helvetica-Bold", fontSize=28,
                                  textColor=colors.HexColor(fit_col_s), leading=32, alignment=1)
    badge_sub_st = ParagraphStyle("bs", fontName="Helvetica", fontSize=8,
                                  textColor=colors.HexColor("#6B7280"), leading=11, alignment=1)
    badge_lbl_st = ParagraphStyle("bl", fontName="Helvetica", fontSize=7,
                                  textColor=colors.HexColor("#9CA3AF"), leading=9)
    badge_col = [Paragraph("FIT RAYO", badge_lbl_st),
                 Paragraph(str(fit_10), badge_val_st),
                 Paragraph("/ 10", badge_sub_st)]
    BADGE_W = 2.5*cm
    TXT_W   = CONTENT_W - BADGE_W - (3.5*cm if foto else 0) - 0.5*cm
    if foto:
        inner = Table([[foto, txt, badge_col]], colWidths=[3.3*cm, TXT_W, BADGE_W])
        inner.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE"),
            ("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(0,-1),12),
            ("LEFTPADDING",(1,0),(1,-1),0),("RIGHTPADDING",(1,0),(1,-1),8),
            ("ALIGN",(2,0),(2,-1),"CENTER")]))
    else:
        inner = Table([[txt, badge_col]], colWidths=[TXT_W+3.3*cm, BADGE_W])
        inner.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE"),
            ("LEFTPADDING",(0,0),(-1,-1),0),("ALIGN",(1,0),(1,-1),"CENTER")]))
    hero = Table([[inner]], colWidths=[CONTENT_W])
    hero.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),C_DARK),
        ("TOPPADDING",(0,0),(-1,-1),14),("BOTTOMPADDING",(0,0),(-1,-1),14),
        ("LEFTPADDING",(0,0),(-1,-1),14),("RIGHTPADDING",(0,0),(-1,-1),14),
    ]))
    return hero


def build_player_dossier(name, team=None):
    enr = _enriched()
    if enr.empty: raise ValueError("Sin datos enriquecidos")
    career = career_aggregate(enr)
    cand = career[career["name"].map(_n)==_n(name)]
    if cand.empty:
        cand = career[career["name"].map(_n).str.contains(_n(name).split()[-1], na=False)]
    if cand.empty: raise ValueError(f"Jugador '{name}' no encontrado")
    crow  = cand.iloc[0]; cname = crow["name"]
    enrp  = add_role_percentiles(career)
    prow  = enrp[enrp["name"]==cname].iloc[0]
    prof  = profile_player_row(prow)
    mv    = get_value(cname)
    fit   = evaluate_player_fit(prof, _needs(), "Bloque medio / Equilibrado") if prof.get("primary_role") else {}
    pos   = prow.get("position_group")
    pool  = career[career["position_group"]==pos]
    st    = _styles()

    foto = None
    purl = mv.get("photo_url") or (
        f"https://img.a.transfermarkt.technology/portrait/big/{mv['tm_id']}.jpg"
        if mv.get("tm_id") else None)
    if purl:
        try:
            import requests
            r = requests.get(purl, timeout=4, headers={"User-Agent":"RayoScoutingTool/1.0"})
            if r.status_code==200 and r.content:
                try:
                    from PIL import Image as _PIL
                    im = _PIL.open(io.BytesIO(r.content)).convert("RGB")
                    im.thumbnail((360,480))
                    ob = io.BytesIO(); im.save(ob, format="JPEG", quality=88); ob.seek(0)
                    foto = Image(ob, width=3.1*cm, height=3.9*cm)
                except Exception:
                    foto = Image(io.BytesIO(r.content), width=3.1*cm, height=3.9*cm)
        except Exception:
            foto = None

    val_s    = f"{mv['value_eur']/1e6:.1f}M EUR" if mv.get("value_eur") else "n/d"
    con_s    = str(mv.get("contract_until",""))[:10] or "n/d"
    age_v    = int(float(mv.get("age") or 0))
    mins_v   = float(crow.get("minutes") or 0)
    league_s = str(crow.get("league","")).replace("_"," ")
    pos_s    = str(mv.get("position") or pos or "")
    sal_s    = _est_salary(mv.get("value_eur",0), league_s, mins_v, age_v, pos_s)
    fit_s    = f"{fit['global_fit_10']}/10" if fit else "n/d"
    fit_v    = fit.get("global_fit",0) if fit else 0
    fit_bg   = (colors.HexColor("#064E3B") if fit_v>=65 else
                colors.HexColor("#451A03") if fit_v>=45 else colors.HexColor("#450A0A"))
    fit_fg   = (C_GREEN if fit_v>=65 else C_AMBER if fit_v>=45 else colors.HexColor("#EF4444"))
    story = []

    # Cabecera
    hdr_l = Paragraph('<font color="white"><b>RAYO VALLECANO — INFORME DE SCOUTING</b></font>',
                      ParagraphStyle("hl", fontName="Helvetica-Bold", fontSize=9, textColor=C_WHITE, leading=12))
    hdr_r = Paragraph(f'<font color="#FCA5A5">{date.today().strftime("%d %b %Y").lstrip("0")}</font>',
                      ParagraphStyle("hr", fontName="Helvetica", fontSize=8.5, textColor=C_RED_LT, leading=12, alignment=2))
    hdr = Table([[hdr_l,hdr_r]], colWidths=[CONTENT_W*0.65, CONTENT_W*0.35])
    hdr.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),C_BLACK),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10),
        ("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7),
        ("LINEBELOW",(0,0),(-1,-1),2.5,C_RED),
    ]))
    story.append(hdr); story.append(Spacer(1,6))
    story.append(_build_hero(cname, crow, mv, prof, fit, foto, sal_s, st))
    story.append(Spacer(1,6))

    # KPI strip
    kpi_w = CONTENT_W/5
    kpis = Table([[
        _kpi_card("FIT RAYO",      fit_s,  st, bg=fit_bg, fg=fit_fg, w=kpi_w),
        _kpi_card("VALOR TM",      val_s,  st, w=kpi_w),
        _kpi_card("SALARIO EST.",  sal_s,  st, w=kpi_w),
        _kpi_card("CONTRATO",      con_s,  st, w=kpi_w),
        _kpi_card("MINUTOS HIST.", f"{int(mins_v):,}".replace(",","."), st, w=kpi_w),
    ]], colWidths=[kpi_w]*5)
    kpis.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),
        ("LEFTPADDING",(0,0),(-1,-1),2),("RIGHTPADDING",(0,0),(-1,-1),2),
        ("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0)]))
    story.append(kpis); story.append(Spacer(1,5))

    # Fortalezas/Debilidades
    if prof.get("strengths") or prof.get("weaknesses"):
        fw_rows = []
        if prof.get("strengths"):
            fw_rows.append([Paragraph("FORTALEZAS", st["tag_green"]),
                            Paragraph("  .  ".join(prof["strengths"]), st["small"])])
        if prof.get("weaknesses"):
            fw_rows.append([Paragraph("DEBILIDADES", st["tag_amber"]),
                            Paragraph("  .  ".join(prof["weaknesses"]), st["small"])])
        fw_t = Table(fw_rows, colWidths=[3.0*cm, CONTENT_W-3.0*cm])
        fw_t.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(0,-1),C_DARK2),("BACKGROUND",(1,0),(1,-1),C_DARK),
            ("INNERGRID",(0,0),(-1,-1),0.25,C_BORDER),("BOX",(0,0),(-1,-1),0.5,C_BORDER),
            ("VALIGN",(0,0),(-1,-1),"TOP"),
            ("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),
            ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
        ]))
        story.append(fw_t); story.append(Spacer(1,5))

    # Fit Rayo
    if fit:
        story.append(_section_header("Fit Rayo — Encaje con el club", st))
        fc = _fit_chart(fit, prof, w_cm=CONTENT_W/cm)
        if fc: story.append(fc)
        pot_map = {"muy alto":95,"alto":80,"estable":65,"en meseta":50,"veterania":35}
        pot_s = pot_map.get(prof.get("potential",""),55)
        bd = [
            ["Componente","Peso","Score","Contribucion"],
            ["Compatibilidad plantilla","40%",str(int(fit.get("compatibilidad_plantilla",0))),
             f"{fit.get('compatibilidad_plantilla',0)*0.40:.1f}"],
            ["Compatibilidad entrenador","25%",str(int(fit.get("compatibilidad_entrenador",0))),
             f"{fit.get('compatibilidad_entrenador',0)*0.25:.1f}"],
            ["Rendimiento en rol","20%",str(int(prof.get("primary_score") or 50)),
             f"{(prof.get('primary_score') or 50)*0.20:.1f}"],
            ["Potencial / edad","15%",str(pot_s),f"{pot_s*0.15:.1f}"],
            ["TOTAL FIT RAYO","100%","—",f"{fit.get('global_fit',0):.1f}"],
        ]
        story.append(Spacer(1,3))
        story.append(_tbl(bd, col_widths=[8.5*cm,1.8*cm,2.4*cm,2.4*cm], fs=8))
        story.append(Spacer(1,2))
        story.append(Paragraph(
            "Formula: Fit=(Plantilla*0.40)+(Entrenador*0.25)+(Rol*0.20)+(Potencial*0.15). "
            "Potencial: muy alto=95, alto=80, estable=65, en meseta=50, veterania=35.", st["italic"]))

    # Radar + Totales
    story.append(_section_header("Perfil de rol — radar de habilidades", st))
    try:
        pool_profiles = [profile_player_row(r) for _,r in add_role_percentiles(pool).iterrows()
                         if r.get("name")!=cname]
        pool_role_avg = {}
        for rp in pool_profiles:
            for k,v in (rp.get("role_scores") or {}).items():
                pool_role_avg.setdefault(k,[]).append(float(v))
        pool_role_avg = {k:sum(vs)/len(vs) for k,vs in pool_role_avg.items()}
    except Exception:
        pool_role_avg = {}
    radar_img = _radar_chart(prof.get("role_scores",{}), pool_role_avg, w_cm=9.5, h_cm=9.0)
    mins_tot = float(crow.get("minutes") or 0) or 1
    tot = [["Metrica","Total","/90'"]]
    for col,lab in CAREER_TOTALS:
        if col in crow.index and pd.notna(crow.get(col)):
            v = float(crow[col])
            p90 = "" if col=="minutes" else f"{v/mins_tot*90:.2f}"
            tot.append([lab, str(int(v)), p90])
    tot_tbl = _tbl(tot, col_widths=[5.2*cm,2.0*cm,1.8*cm], fs=7.5)
    rs_data = [["Rol","Score"]]
    for k,v in list(prof.get("role_scores",{}).items())[:7]:
        rs_data.append([ROLE_LABELS.get(k,k), str(int(v))])
    rs_tbl = _tbl(rs_data, col_widths=[6.0*cm,1.8*cm], fs=7.5)
    L_W = 9.8*cm; R_W = CONTENT_W - L_W
    left_cell  = ([radar_img, Spacer(1,4), rs_tbl] if radar_img else [rs_tbl])
    right_cell = [Paragraph("TOTALES DE CARRERA",
                             ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=8.5,
                                            textColor=C_DARK, leading=12)),
                  Spacer(1,4), tot_tbl]
    two_col = Table([[left_cell,right_cell]], colWidths=[L_W,R_W])
    two_col.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),
        ("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
        ("LEFTPADDING",(1,0),(1,-1),8)]))
    story.append(two_col)

    # Top percentiles
    story.append(_section_header("Mejores percentiles vs posicion", st))
    tpc = _top_pct_chart(crow, pool, top_n=12, w_cm=CONTENT_W/cm)
    if tpc: story.append(tpc)

    # Grupos de metricas (2 columnas de charts)
    story.append(_section_header("Percentiles por grupo de metricas", st))
    grp_items = list(METRIC_GROUPS.items())
    G_W = (CONTENT_W-0.4*cm)/2
    for i in range(0, len(grp_items), 2):
        row_cells = []
        for grp,metrics in grp_items[i:i+2]:
            gc = _group_chart(grp, metrics, crow, pool, w_cm=G_W/cm)
            row_cells.append([gc] if gc else [Spacer(1,1)])
        while len(row_cells)<2: row_cells.append([Spacer(1,1)])
        gt = Table([row_cells], colWidths=[G_W,G_W])
        gt.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),
            ("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
            ("LEFTPADDING",(1,0),(1,-1),6)]))
        story.append(gt); story.append(Spacer(1,4))

    # Temporadas
    story.append(_section_header("Estadisticas por temporada (OPTA)", st))
    prows = enr[enr["name"]==cname].copy()
    order = {"2025-2026":6,"2025":5,"2024-2025":4,"2023-2024":3,"2022-2023":2,"2021-2022":1}
    prows["_o"] = prows["season"].map(order).fillna(0)
    prows = prows.sort_values("_o", ascending=False)
    cols  = [(c,lbl) for c,lbl in SEASON_COLS if c in prows.columns]
    tdata = [[lbl for _,lbl in cols]]
    for _,rw in prows.iterrows():
        row = []
        for c,_lbl in cols:
            v = rw.get(c)
            if c=="minutes" and pd.notna(v): v = int(v)
            elif isinstance(v,float) and pd.notna(v) and c!="season": v = int(v)
            row.append("" if pd.isna(v) else str(v))
        tdata.append(row)
    story.append(_tbl(tdata, fs=6.5))

    # Footer
    story.append(Spacer(1,8))
    foot = Table([[Paragraph(
        f"Rayo Vallecano . Direccion Deportiva . "
        f"Generado {date.today().strftime('%d %b %Y').lstrip('0')}  .  "
        f"Datos OPTA ({prof.get('seasons_played','?')} temp.) + Transfermarkt  .  Confidencial.",
        st["italic"])]], colWidths=[CONTENT_W])
    foot.setStyle(TableStyle([
        ("LINEABOVE",(0,0),(-1,-1),1.5,C_RED),("BACKGROUND",(0,0),(-1,-1),C_DARK),
        ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
        ("LEFTPADDING",(0,0),(-1,-1),8),
    ]))
    story.append(foot)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            topMargin=MARGIN, bottomMargin=MARGIN,
                            leftMargin=MARGIN, rightMargin=MARGIN)
    doc.build(story)
    buf.seek(0)
    return f"informe_{_n(cname).replace(' ','_')}.pdf", buf.read()
