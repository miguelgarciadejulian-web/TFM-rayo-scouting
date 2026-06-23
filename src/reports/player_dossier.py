# -*- coding: utf-8 -*-
"""
player_dossier.py  v7  (WeasyPrint + xhtml2pdf)
================================================
Informe PDF jugador — diseno editorial profesional.
Layout: HTML tables (compatible con WeasyPrint y xhtml2pdf).
Paleta corporativa: #E30613 rojo · #0D0D0D negro · blanco.
"""
from __future__ import annotations
import unicodedata
from datetime import date
from pathlib import Path

import pandas as pd

from src.utils.config import settings
from src.profiling.player_profile import (
    career_aggregate, add_role_percentiles, profile_player_row,
    ROLE_LABELS, METRIC_LABELS)
from src.fit.player_fit import evaluate_player_fit
from src.utils.market import get_value
from src.reports.pdf_base import (
    score_color, fig_to_b64, photo_b64,
    svg_gauge, radar_chart_b64,
    html_to_pdf,
    GREEN, AMBER, LOW, RED, LGREY, DARK, GREY,
)

# ─── Rutas ────────────────────────────────────────────────────────────────────
PROC = Path(settings()["paths"]["data_processed"])

# ─── Etiquetas extendidas (sin claves crudas) ─────────────────────────────────
EXTRA_LABELS = {
    "successful_long_passes_p90":                    "pases largos",
    "total_losses_of_possession_p90":                "perdidas de balon",
    "total_touches_in_opposition_box_p90":           "pres. area rival",
    "successful_crosses_open_play_p90":              "centros",
    "successful_passes_opposition_half_p90":         "juego campo rival",
    "total_successful_passes_excl_crosses_corners_p90": "volumen de pase",
    "blocks_p90":                                    "bloqueos",
    "total_clearances_p90":                          "despejes",
    "ground_duels_won_p90":                          "duelos en suelo",
    "aerial_duels_won_p90":                          "juego aereo",
    "goals_p90":                                     "goles",
    "total_shots_p90":                               "volumen de tiro",
    "shots_on_target_inc_goals_p90":                 "tiros a puerta",
    "key_passes_attempt_assists_p90":                "pases clave",
    "goal_assists_p90":                              "asistencias",
    "successful_dribbles_p90":                       "regate",
    "tackles_won_p90":                               "entradas ganadas",
    "interceptions_p90":                             "intercepciones",
    "recoveries_p90":                                "recuperaciones",
}
ALL_LABELS = {**METRIC_LABELS, **EXTRA_LABELS}

# ─── Grupos de metricas ───────────────────────────────────────────────────────
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
    ("minutes",                      "Minutos"),
    ("goals",                        "Goles"),
    ("goal_assists",                  "Asistencias"),
    ("total_shots",                   "Tiros"),
    ("shots_on_target_inc_goals",     "T. a puerta"),
    ("key_passes_attempt_assists",    "Pases clave"),
    ("successful_dribbles",           "Regates"),
    ("total_touches_in_opposition_box","Toques area rival"),
    ("tackles_won",                   "Entradas ganad."),
    ("interceptions",                 "Intercepciones"),
    ("recoveries",                    "Recuperaciones"),
    ("aerial_duels_won",              "Duelos aereos"),
]

SEASON_COLS = [
    ("season", "Temp."), ("team", "Equipo"), ("minutes", "Min"),
    ("goals", "G"), ("goal_assists", "A"), ("total_shots", "Tir"),
    ("shots_on_target_inc_goals", "TaP"), ("key_passes_attempt_assists", "PC"),
    ("successful_dribbles", "Reg"), ("total_touches_in_opposition_box", "ToqA"),
    ("tackles_won", "Ent"), ("interceptions", "Int"), ("recoveries", "Rec"),
    ("aerial_duels_won", "Aer"), ("total_clearances", "Desp"),
]

MATRIX_METRICS = [
    ("Goles",           "goals_p90"),
    ("Asistencias",     "goal_assists_p90"),
    ("Tiro (vol.)",     "total_shots_p90"),
    ("Pases clave",     "key_passes_attempt_assists_p90"),
    ("Regate",          "successful_dribbles_p90"),
    ("Centros",         "successful_crosses_open_play_p90"),
    ("Entradas",        "tackles_won_p90"),
    ("Intercepciones",  "interceptions_p90"),
    ("Recuperaciones",  "recoveries_p90"),
    ("Duelos aereos",   "aerial_duels_won_p90"),
    ("Duelos suelo",    "ground_duels_won_p90"),
    ("Pres. area rival","total_touches_in_opposition_box_p90"),
]


# ─── Helpers de datos ─────────────────────────────────────────────────────────
def _n(s):
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()

def _enriched():
    p = PROC / "player_seasons_enriched.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()

def _needs():
    import json
    p = PROC / "squad_profile.json"
    return json.load(open(p, encoding="utf-8")).get("needs", {}) if p.exists() else {}

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

def _comparator_fit(name: str, proc: Path) -> float | None:
    try:
        import yaml
        from src.scouting.comparator import load_scorer
        cfg_path = proc.parent.parent / "config" / "club_profile.yaml"
        with open(cfg_path, encoding="utf-8") as _f:
            club = yaml.safe_load(_f)
        squad = []
        for section in club.get("squad_2025_26", {}).values():
            if isinstance(section, list):
                squad.extend(section)
        scorer = load_scorer(proc, squad)
        results = scorer.compare([name])
        return float(results[0].fit_score) if results else None
    except Exception:
        return None

def _pct_rank(crow, pool, metric):
    if metric not in pool.columns: return None
    ser = pd.to_numeric(pool[metric], errors="coerce")
    pr  = ser.rank(pct=True) * 100
    idx = pool.index[pool["name"] == crow.get("name")]
    if len(idx) == 0: return None
    pct = pr.get(idx[0])
    return float(pct) if pd.notna(pct) else None


# ═══════════════════════════════════════════════════════════════════════════════
#  HTML BUILDERS — todo con <table> para compatibilidad xhtml2pdf + WeasyPrint
# ═══════════════════════════════════════════════════════════════════════════════

def _S(title: str) -> str:
    """Cabecera de seccion roja."""
    return (
        f'<div style="background-color:#E30613;color:white;font-weight:bold;'
        f'font-size:7pt;text-transform:uppercase;padding:4px 10px;'
        f'letter-spacing:0.6px;margin-top:9px;margin-bottom:4px;">'
        f'{title.upper()}</div>'
    )


def _pbar(label: str, pct: float, note: str = "", label_w: int = 155) -> str:
    """Barra de percentil horizontal — tabla anidada, compatible xhtml2pdf."""
    pct = max(0.0, min(float(pct), 100.0))
    col = GREEN if pct >= 68 else (AMBER if pct >= 44 else LOW)
    note_html = (f'<br/><span style="font-size:5pt;color:#9CA3AF;">{note}</span>'
                 if note else "")
    return (
        f'<table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin:2px 0;">'
        f'<tr valign="middle">'
        f'<td width="{label_w}" style="width:{label_w}px;text-align:right;'
        f'padding-right:5px;font-size:6.5pt;color:#374151;vertical-align:middle;">'
        f'{label}{note_html}</td>'
        f'<td style="vertical-align:middle;">'
        f'<table cellpadding="0" cellspacing="0" border="0" width="100%">'
        f'<tr>'
        f'<td width="{pct:.0f}%" style="background-color:{col};height:10px;" height="10">&nbsp;</td>'
        f'<td style="background-color:#F0F0F0;height:10px;" height="10">&nbsp;</td>'
        f'</tr>'
        f'</table>'
        f'</td>'
        f'<td width="28" style="width:28px;font-size:7pt;font-weight:bold;'
        f'color:{col};padding-left:4px;vertical-align:middle;text-align:right;">'
        f'{pct:.0f}</td>'
        f'</tr>'
        f'</table>'
    )


def _dot(pct: float) -> str:
    """Circulo de color segun percentil."""
    if pct >= 70:
        return f'<span style="color:{GREEN};font-size:10pt;">&#9679;</span>'
    if pct >= 45:
        return f'<span style="color:{AMBER};font-size:10pt;">&#9679;</span>'
    return f'<span style="color:{LOW};font-size:10pt;">&#9679;</span>'


# ─── Topbar ───────────────────────────────────────────────────────────────────
def _topbar() -> str:
    d = date.today().strftime("%d/%m/%Y")
    return (
        f'<table cellpadding="0" cellspacing="0" border="0" width="100%" '
        f'style="background-color:#0D0D0D;border-bottom:2.5px solid #E30613;">'
        f'<tr>'
        f'<td style="padding:6px 10px;color:white;font-weight:bold;font-size:8.5pt;">'
        f'RAYO VALLECANO &mdash; INFORME DE SCOUTING</td>'
        f'<td style="padding:6px 10px;color:#9CA3AF;font-size:8pt;text-align:right;">'
        f'Confidencial &middot; {d}</td>'
        f'</tr>'
        f'</table>'
    )


# ─── Hero card ────────────────────────────────────────────────────────────────
def _hero_html(cname, crow, mv, prof, fit_10, sal_s, foto_b64_str) -> str:
    team_s   = str(crow.get("team", ""))
    league_s = str(crow.get("league", "")).replace("_", " ")
    pos_s    = str(mv.get("position") or crow.get("position_group") or "")
    age_v    = int(float(mv.get("age") or 0)) if mv.get("age") else 0
    ht_s     = str(mv.get("height") or "")
    _ft      = {"right":"Der.","left":"Izq.","both":"Ambos","derecho":"Der.","zurdo":"Izq."}
    foot_s   = _ft.get(str(mv.get("foot") or "").strip().lower(), "")
    role_lbl = prof.get("primary_role_label", "n/d")
    nation   = str(mv.get("nationality") or "")
    contr    = str(mv.get("contract_until",""))[:7] or "n/d"
    val_s    = f"{mv['value_eur']/1e6:.1f}M EUR" if mv.get("value_eur") else "n/d"

    bio_parts = [p for p in [
        f"{age_v} anos" if age_v else None,
        ht_s or None,
        f"Pie {foot_s}" if foot_s else None,
        pos_s or None,
    ] if p]
    bio_s = " &middot; ".join(bio_parts)

    photo_cell = (
        f'<td width="84" style="width:84px;padding:12px 8px 12px 14px;vertical-align:middle;">'
        f'<img src="data:image/jpeg;base64,{foto_b64_str}" width="72" height="90" '
        f'style="border:0.5px solid #E5E7EB;"/>'
        f'</td>'
        if foto_b64_str else
        f'<td width="84" style="width:84px;padding:12px 8px 12px 14px;vertical-align:middle;">'
        f'<div style="width:72px;height:90px;background-color:#F3F4F6;border:0.5px solid #E5E7EB;'
        f'text-align:center;font-size:6pt;color:#9CA3AF;padding-top:38px;">sin foto</div>'
        f'</td>'
    )

    gauge_svg = svg_gauge(fit_10, size=80)

    return (
        f'<table cellpadding="0" cellspacing="0" border="0" width="100%" '
        f'style="border:0.5px solid #E5E7EB;border-top:3px solid #E30613;'
        f'margin-top:6px;background-color:white;">'
        f'<tr>'
        f'{photo_cell}'
        f'<td style="padding:12px 8px;vertical-align:top;">'
        f'<div style="font-size:16pt;font-weight:bold;color:#0D0D0D;line-height:1.1;">{cname}</div>'
        f'<div style="font-size:9pt;font-weight:bold;color:#E30613;margin-top:3px;">'
        f'{team_s} &middot; {league_s}</div>'
        f'<div style="font-size:7.5pt;color:#374151;margin-top:5px;">{bio_s}</div>'
        f'<div style="font-size:7.5pt;color:#374151;margin-top:4px;">'
        f'<span style="color:#9CA3AF;">Rol: </span><strong>{role_lbl}</strong>'
        f'&nbsp;&nbsp;<span style="color:#9CA3AF;">Pais: </span>{nation}</div>'
        f'<div style="font-size:7.5pt;color:#374151;margin-top:2px;">'
        f'<span style="color:#9CA3AF;">Contrato hasta: </span><strong>{contr}</strong>'
        f'&nbsp;&nbsp;<span style="color:#9CA3AF;">Valor TM: </span><strong>{val_s}</strong>'
        f'&nbsp;&nbsp;<span style="color:#9CA3AF;">Sal. est.: </span><strong>{sal_s}</strong>'
        f'</div>'
        f'</td>'
        f'<td width="105" style="width:105px;text-align:center;vertical-align:middle;'
        f'padding:12px 14px;">'
        f'{gauge_svg}'
        f'<div style="font-size:5.5pt;font-weight:bold;color:#E30613;text-transform:uppercase;'
        f'letter-spacing:0.5px;margin-top:3px;">FIT RAYO</div>'
        f'</td>'
        f'</tr>'
        f'</table>'
    )


# ─── KPI Strip ────────────────────────────────────────────────────────────────
def _kpi_strip(fit_s, fit_v, val_s, sal_s, con_s, mins_s, goals_tot, asist_tot) -> str:
    col = GREEN if fit_v >= 65 else (AMBER if fit_v >= 45 else LOW)
    cards = [
        ("FIT RAYO",
         f'<span style="color:{col};font-weight:bold;font-size:10pt;">{fit_s}</span>'),
        ("VALOR TM",      val_s),
        ("SALARIO EST.",  sal_s),
        ("CONTRATO",      con_s),
        ("MIN. TOTALES",  mins_s),
        ("G + A",         f'{int(goals_tot)}G &nbsp; {int(asist_tot)}A'),
    ]
    cells = ""
    for i, (label, value) in enumerate(cards):
        bl = "" if i == 0 else "border-left:2px solid white;"
        cells += (
            f'<td style="border:0.5px solid #E5E7EB;border-top:2.5px solid #E30613;'
            f'padding:7px 8px;background-color:white;vertical-align:top;{bl}">'
            f'<div style="font-size:5.5pt;color:#9CA3AF;text-transform:uppercase;'
            f'letter-spacing:0.4px;">{label}</div>'
            f'<div style="font-size:9pt;font-weight:bold;color:#0D0D0D;margin-top:2px;">'
            f'{value}</div>'
            f'</td>'
        )
    return (
        f'<table cellpadding="0" cellspacing="0" border="0" width="100%" '
        f'style="margin-top:6px;table-layout:fixed;">'
        f'<tr>{cells}</tr>'
        f'</table>'
    )


# ─── Fortalezas / Debilidades ─────────────────────────────────────────────────
def _sw_section(strengths, weaknesses) -> str:
    if not strengths and not weaknesses:
        return ""

    def _pills(items, bg, color):
        return "".join(
            f'<span style="background-color:{bg};color:{color};font-size:6.5pt;'
            f'padding:2px 7px;border-radius:9px;margin:2px 2px;display:inline-block;">'
            f'{s}</span>'
            for s in items
        ) if items else ""

    s_td = (
        f'<td width="260" style="background-color:#F0FDF4;border:0.5px solid #E5E7EB;'
        f'padding:6px 8px;width:260px;vertical-align:top;">'
        f'<div style="font-size:5.5pt;font-weight:bold;color:{GREEN};'
        f'text-transform:uppercase;margin-bottom:4px;">Fortalezas</div>'
        f'{_pills(strengths, "#DCFCE7", GREEN)}'
        f'</td>'
    ) if strengths else '<td></td>'

    w_td = (
        f'<td style="background-color:#FFFBEB;border:0.5px solid #E5E7EB;'
        f'border-left:2px solid white;padding:6px 8px;vertical-align:top;">'
        f'<div style="font-size:5.5pt;font-weight:bold;color:{AMBER};'
        f'text-transform:uppercase;margin-bottom:4px;">Debilidades</div>'
        f'{_pills(weaknesses, "#FEF3C7", AMBER)}'
        f'</td>'
    ) if weaknesses else '<td></td>'

    return (
        f'<table cellpadding="0" cellspacing="0" border="0" width="100%" '
        f'style="margin-top:5px;">'
        f'<tr valign="top">{s_td}{w_td}</tr>'
        f'</table>'
    )


# ─── Fit Rayo ─────────────────────────────────────────────────────────────────
def _fit_section(fit, prof, fit_10) -> str:
    pot_map = {"muy alto":95,"alto":80,"estable":65,"en meseta":50,"veterania":35}
    pot_s   = pot_map.get(prof.get("potential",""), 55)
    comps   = [
        ("Compatib. plantilla  (40%)",  float(fit.get("compatibilidad_plantilla", 0))),
        ("Compatib. entrenador  (25%)", float(fit.get("compatibilidad_entrenador", 0))),
        ("Rendimiento en rol  (20%)",   float(prof.get("primary_score") or 50)),
        ("Potencial / edad  (15%)",     float(pot_s)),
    ]
    fit_col = score_color(float(fit_10) * 10 if fit_10 else 0, hi=70, lo=50)
    title   = (f'<div style="font-size:10pt;font-weight:bold;color:{fit_col};margin-bottom:5px;">'
               f'FIT RAYO &mdash; {fit_10} / 10</div>')
    bars    = "".join(_pbar(lab, val, label_w=200) for lab, val in comps)

    # Breakdown table (HTML puro)
    def _trow(cells, bold=False, bg="#ffffff"):
        style = f'style="background-color:{bg};"'
        tds   = "".join(
            f'<td style="padding:3.5px 5px;color:#111827;border-bottom:0.3px solid #E5E7EB;'
            f'font-size:7pt;{"font-weight:bold;" if bold else ""}">{c}</td>'
            for c in cells
        )
        return f'<tr {style}>{tds}</tr>'

    thead = "".join(
        f'<td style="background-color:#E30613;color:white;font-weight:bold;'
        f'padding:4px 5px;font-size:6.5pt;text-transform:uppercase;">{h}</td>'
        for h in ["Componente","Peso","Score","Contribucion"]
    )
    rows_html = (
        _trow(["Compatibilidad plantilla","40%",str(int(fit.get("compatibilidad_plantilla",0))),
               f"{fit.get('compatibilidad_plantilla',0)*0.40:.1f}"], bg="#ffffff")
        + _trow(["Compatibilidad entrenador","25%",str(int(fit.get("compatibilidad_entrenador",0))),
                 f"{fit.get('compatibilidad_entrenador',0)*0.25:.1f}"], bg="#F9FAFB")
        + _trow(["Rendimiento en rol","20%",str(int(prof.get("primary_score") or 50)),
                 f"{(prof.get('primary_score') or 50)*0.20:.1f}"], bg="#ffffff")
        + _trow(["Potencial / edad","15%",str(pot_s),f"{pot_s*0.15:.1f}"], bg="#F9FAFB")
        + _trow(["TOTAL FIT RAYO","100%","—",f"{fit.get('global_fit',0):.1f}"],
                bold=True, bg="#F8FAFC")
    )
    tbl = (f'<table cellpadding="0" cellspacing="0" border="0" width="100%" '
           f'style="border-collapse:collapse;font-size:7pt;margin:6px 0;">'
           f'<thead><tr>{thead}</tr></thead>'
           f'<tbody>{rows_html}</tbody>'
           f'</table>')
    note = (f'<div style="font-size:6pt;color:#9CA3AF;font-style:italic;margin-top:3px;">'
            f'Formula: Fit = (Plantilla*0.40) + (Entrenador*0.25) + (Rol*0.20) + (Potencial*0.15). '
            f'Potencial: muy alto=95, alto=80, estable=65, en meseta=50, veterania=35.</div>')
    return _S("Fit Rayo — Encaje con el club") + title + bars + tbl + note


# ─── Radar + roles + carrera ──────────────────────────────────────────────────
def _html_table(headers, rows, total_row=None) -> str:
    """Tabla HTML con cabecera roja y filas alternadas."""
    th = "".join(
        f'<td style="background-color:#E30613;color:white;font-weight:bold;'
        f'padding:4px 5px;font-size:6.5pt;text-transform:uppercase;">{h}</td>'
        for h in headers
    )
    tbody = ""
    for i, row in enumerate(rows):
        bg = "#ffffff" if i % 2 == 0 else "#F9FAFB"
        tds = "".join(
            f'<td style="padding:3.5px 5px;color:#111827;'
            f'border-bottom:0.3px solid #E5E7EB;font-size:7pt;">{c}</td>'
            for c in row
        )
        tbody += f'<tr style="background-color:{bg};">{tds}</tr>'
    if total_row:
        tds = "".join(
            f'<td style="padding:3.5px 5px;font-weight:bold;'
            f'border-top:1px solid #D1D5DB;font-size:7pt;">{c}</td>'
            for c in total_row
        )
        tbody += f'<tr style="background-color:#F8FAFC;">{tds}</tr>'
    return (f'<table cellpadding="0" cellspacing="0" border="0" width="100%" '
            f'style="border-collapse:collapse;margin:3px 0;">'
            f'<thead><tr>{th}</tr></thead>'
            f'<tbody>{tbody}</tbody>'
            f'</table>')


def _career_table(tot_rows) -> str:
    """Tabla totales de carrera con anchos FIJOS por celda (evita layout negativo en xhtml2pdf)."""
    # Anchos en px explicitados en cada celda — xhtml2pdf ignora width:% del padre
    # Pagina A4 - margenes 1.2cm = ~703px contenido; 350+175+178=703
    W0, W1 = 350, 175  # Metrica, Total; /90' = resto
    def _th(h, w=None):
        wa = f'width="{w}" style="width:{w}px;' if w else 'style="'
        return (f'<td {wa}background-color:#E30613;color:white;font-weight:bold;'
                f'padding:3px 4px;font-size:6.5pt;text-transform:uppercase;">{h}</td>')
    def _td(c, w=None, align="left"):
        wa = f'width="{w}" style="width:{w}px;' if w else 'style="'
        return (f'<td {wa}padding:3px 4px;color:#111827;'
                f'border-bottom:0.3px solid #E5E7EB;font-size:7pt;text-align:{align};">{c}</td>')
    head = _th("Metrica", W0) + _th("Total", W1) + _th("/90'")
    body = ""
    for i, (lab, total, p90) in enumerate(tot_rows):
        bg = "#ffffff" if i % 2 == 0 else "#F9FAFB"
        body += (f'<tr style="background-color:{bg};">'
                 f'{_td(lab, W0)}{_td(total, W1, "right")}{_td(p90, align="right")}'
                 f'</tr>')
    return (f'<table cellpadding="0" cellspacing="0" border="0" width="100%" '
            f'style="border-collapse:collapse;margin:3px 0;table-layout:fixed;">'
            f'<thead><tr>{head}</tr></thead>'
            f'<tbody>{body}</tbody>'
            f'</table>') if tot_rows else ""


def _radar_section(prof, pool_avg, crow, pool, career_row) -> str:
    labeled_scores = {ROLE_LABELS.get(k, k): v for k, v in prof.get("role_scores", {}).items()}
    radar_b64 = radar_chart_b64(
        labeled_scores,
        {ROLE_LABELS.get(k,k): v for k,v in pool_avg.items()}
    )

    rs_rows = [(ROLE_LABELS.get(k,k), str(int(v)))
               for k,v in list(prof.get("role_scores",{}).items())[:7]]
    rs_tbl = _html_table(["Rol","Score"], rs_rows)

    mins_tot = float(career_row.get("minutes") or 0) or 1
    tot_rows = []
    for col, lab in CAREER_TOTALS:
        if col in career_row.index and pd.notna(career_row.get(col)):
            v   = float(career_row[col])
            p90 = "" if col == "minutes" else f"{v/mins_tot*90:.2f}"
            tot_rows.append((lab, str(int(v)), p90))

    radar_img = (
        f'<img src="data:image/png;base64,{radar_b64}" width="230" height="190" '
        f'style="display:block;margin-bottom:5px;"/>'
        if radar_b64 else ""
    )
    # Radar + roles a la izquierda (layout 2-col, sin 3-col anidado)
    top_layout = (
        f'<table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin-top:4px;">'
        f'<tr valign="top">'
        f'<td width="270" style="width:270px;padding-right:10px;vertical-align:top;">{radar_img}</td>'
        f'<td style="vertical-align:top;">'
        f'<div style="font-size:7.5pt;font-weight:bold;color:#E30613;margin-bottom:4px;">Scores por rol</div>'
        f'{rs_tbl}</td>'
        f'</tr>'
        f'</table>'
    )
    # Totales de carrera: tabla 3-col a ancho COMPLETO con celdas de ancho fijo
    career_section = (
        f'<div style="font-size:7.5pt;font-weight:bold;color:#E30613;'
        f'margin-top:6px;margin-bottom:3px;">Totales de carrera</div>'
        + _career_table(tot_rows)
    ) if tot_rows else ""

    return _S("Perfil de rol — radar de habilidades") + top_layout + career_section


# ─── Matriz de fortalezas (semaforo) ─────────────────────────────────────────
def _strength_matrix(crow, pool) -> str:
    valid = []
    for label, metric in MATRIX_METRICS:
        pct = _pct_rank(crow, pool, metric)
        if pct is not None:
            valid.append((label, pct))
    if not valid:
        return ""

    def _mrow(label, pct):
        dot = _dot(pct)
        if pct >= 70:   bg, col = "#F0FDF4", GREEN
        elif pct >= 45: bg, col = "#FFFBEB", AMBER
        else:           bg, col = "#FEF2F2", LOW
        return (
            f'<tr style="background-color:{bg};">'
            f'<td style="padding:3px 6px;font-size:7pt;color:#374151;">'
            f'{dot}&nbsp;{label}</td>'
            f'<td style="padding:3px 6px;font-size:7pt;font-weight:bold;'
            f'color:{col};text-align:right;">P{pct:.0f}</td>'
            f'</tr>'
        )

    half  = (len(valid) + 1) // 2
    l_rows = "".join(_mrow(l, p) for l, p in valid[:half])
    r_rows = "".join(_mrow(l, p) for l, p in valid[half:])

    return (
        _S("Matriz de fortalezas — semaforo de metricas") +
        f'<table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin-top:4px;">'
        f'<tr valign="top">'
        f'<td width="260" style="width:260px;padding-right:5px;vertical-align:top;">'
        f'<table cellpadding="0" cellspacing="0" border="0" width="100%" '
        f'style="border:0.5px solid #E5E7EB;">{l_rows}</table>'
        f'</td>'
        f'<td style="vertical-align:top;">'
        f'<table cellpadding="0" cellspacing="0" border="0" width="100%" '
        f'style="border:0.5px solid #E5E7EB;">{r_rows}</table>'
        f'</td>'
        f'</tr>'
        f'</table>'
        f'<div style="font-size:6pt;color:#9CA3AF;margin-top:3px;">'
        f'&#9679; Verde = top 30% &nbsp;&#9679; Naranja = percentil 44-70% '
        f'&nbsp;&#9679; Rojo = por debajo de la media de la posicion</div>'
    )


# ─── Top percentiles ──────────────────────────────────────────────────────────
def _top_pct_section(crow, pool, top_n=12) -> str:
    all_m = []
    for grp, metrics in METRIC_GROUPS.items():
        for m in metrics:
            pct = _pct_rank(crow, pool, m)
            if pct is not None:
                label = ALL_LABELS.get(m, m.replace("_p90","").replace("_"," "))
                all_m.append((label, pct))
    if not all_m:
        return ""
    all_m.sort(key=lambda x: -x[1])
    bars = "".join(_pbar(lab, pct, label_w=180) for lab, pct in all_m[:top_n])
    return _S(f"Top {top_n} percentiles vs posicion") + bars


# ─── Percentiles por grupo de metricas ───────────────────────────────────────
def _group_section(crow, pool) -> str:
    grp_items = list(METRIC_GROUPS.items())
    html = _S("Percentiles por grupo de metricas")
    html += (f'<table cellpadding="0" cellspacing="0" border="0" width="100%" '
             f'style="margin-top:4px;">')
    for i in range(0, len(grp_items), 2):
        html += '<tr valign="top">'
        pair = grp_items[i:i+2]
        for j, (grp, metrics) in enumerate(pair):
            rows = []
            for m in metrics:
                pct = _pct_rank(crow, pool, m)
                v90 = float(crow[m]) if m in crow.index and pd.notna(crow.get(m)) else None
                if pct is not None:
                    label = ALL_LABELS.get(m, m.replace("_p90","").replace("_"," "))
                    note  = f"{v90:.2f}/90" if v90 is not None else ""
                    rows.append((label, pct, note))
            # width en atributo px (xhtml2pdf ignora width:% en CSS)
            col_w = 255 if j == 0 else 256
            pad_r = "padding-right:8px;" if j == 0 else ""
            content = (
                f'<div style="font-size:7.5pt;font-weight:bold;color:#E30613;'
                f'margin-bottom:2px;margin-top:3px;">{grp}</div>'
            )
            if rows:
                content += "".join(_pbar(lab, pct, note, label_w=105) for lab, pct, note in rows)
            html += f'<td width="{col_w}" style="width:{col_w}px;{pad_r}vertical-align:top;">{content}</td>'
        if len(pair) == 1:
            html += '<td></td>'
        html += '</tr>'
    html += '</table>'
    return html


# ─── Estadisticas por temporada ───────────────────────────────────────────────
def _seasons_section(enr, cname) -> str:
    prows = enr[enr["name"] == cname].copy()
    order = {"2025-2026":6,"2025":5,"2024-2025":4,"2023-2024":3,"2022-2023":2,"2021-2022":1}
    prows["_o"] = prows["season"].map(order).fillna(0)
    prows = prows.sort_values("_o", ascending=False)
    cols    = [(c, lbl) for c, lbl in SEASON_COLS if c in prows.columns]
    headers = [lbl for _, lbl in cols]
    rows    = []
    for _, rw in prows.iterrows():
        row = []
        for c, _ in cols:
            v = rw.get(c)
            if c == "minutes" and pd.notna(v):                   v = int(v)
            elif isinstance(v, float) and pd.notna(v) and c != "season": v = int(v)
            row.append("" if pd.isna(v) else str(v))
        rows.append(row)
    return _S("Estadisticas por temporada (OPTA)") + _html_table(headers, rows)


# ─── Footer ───────────────────────────────────────────────────────────────────
def _footer(prof) -> str:
    d     = date.today().strftime("%d/%m/%Y")
    temps = prof.get("seasons_played", "?")
    return (
        f'<div style="border-top:1.5px solid #E30613;margin-top:14px;padding-top:5px;'
        f'font-size:6pt;color:#9CA3AF;font-style:italic;">'
        f'Rayo Vallecano &middot; Direccion Deportiva &middot; Generado {d} &middot; '
        f'Datos OPTA ({temps} temp.) + Transfermarkt &middot; Confidencial'
        f'</div>'
    )


# ─── CSS del documento ────────────────────────────────────────────────────────
_CSS = """
@page { size: A4; margin: 1.2cm; }
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: Arial, Helvetica, sans-serif;
    font-size: 9pt;
    color: #111827;
    background: white;
    line-height: 1.4;
}
img { display: block; }
table { border-spacing: 0; }
"""


# ─── Funcion principal ────────────────────────────────────────────────────────
def build_player_dossier(name, team=None):
    enr = _enriched()
    if enr.empty:
        raise ValueError("Sin datos enriquecidos")

    career = career_aggregate(enr)
    cand   = career[career["name"].map(_n) == _n(name)]
    if cand.empty:
        cand = career[career["name"].map(_n).str.contains(_n(name).split()[-1], na=False)]
    if cand.empty:
        raise ValueError(f"Jugador '{name}' no encontrado")

    crow  = cand.iloc[0]; cname = crow["name"]
    enrp  = add_role_percentiles(career)
    prow  = enrp[enrp["name"] == cname].iloc[0]
    prof  = profile_player_row(prow)
    mv    = get_value(cname)
    fit   = evaluate_player_fit(prof, _needs(), "Bloque medio / Equilibrado") if prof.get("primary_role") else {}
    pos   = prow.get("position_group")
    pool  = career[career["position_group"] == pos]

    # Foto
    foto_b64_str = None
    purl = mv.get("photo_url") or (
        f"https://img.a.transfermarkt.technology/portrait/big/{mv['tm_id']}.jpg"
        if mv.get("tm_id") else None
    )
    if purl:
        try:
            import requests
            r = requests.get(purl, timeout=4, headers={"User-Agent": "RayoScoutingTool/1.0"})
            if r.status_code == 200 and r.content:
                foto_b64_str = photo_b64(r.content)
        except Exception:
            foto_b64_str = None

    # Scores
    val_s     = f"{mv['value_eur']/1e6:.1f}M EUR" if mv.get("value_eur") else "n/d"
    con_s     = str(mv.get("contract_until",""))[:10] or "n/d"
    age_v     = int(float(mv.get("age") or 0))
    mins_v    = float(crow.get("minutes") or 0)
    league_s  = str(crow.get("league","")).replace("_"," ")
    pos_s     = str(mv.get("position") or pos or "")
    sal_s     = _est_salary(mv.get("value_eur",0), league_s, mins_v, age_v, pos_s)
    mins_s    = f"{int(mins_v):,}".replace(",",".")
    goals_tot = float(crow.get("goals") or 0)
    asist_tot = float(crow.get("goal_assists") or 0)

    _comp_fit = _comparator_fit(cname, PROC)
    if _comp_fit is not None:
        fit_v  = _comp_fit
        fit_10 = round(_comp_fit / 10, 1)
        fit_s  = f"{fit_10}/10"
    elif fit:
        fit_v  = fit.get("global_fit", 0)
        fit_10 = round(fit_v / 10, 1)
        fit_s  = f"{fit_10}/10"
    else:
        fit_v = 0; fit_10 = 0; fit_s = "n/d"

    if fit:
        fit["_unified_v"]  = fit_v
        fit["_unified_10"] = fit_10

    # Pool avg para radar
    try:
        pool_profiles = [
            profile_player_row(r)
            for _, r in add_role_percentiles(pool).iterrows()
            if r.get("name") != cname
        ]
        pool_role_avg: dict = {}
        for rp in pool_profiles:
            for k, v in (rp.get("role_scores") or {}).items():
                pool_role_avg.setdefault(k, []).append(float(v))
        pool_role_avg = {k: sum(vs)/len(vs) for k, vs in pool_role_avg.items()}
    except Exception:
        pool_role_avg = {}

    # Construir HTML
    body = ""
    body += _topbar()
    body += _hero_html(cname, crow, mv, prof, fit_10, sal_s, foto_b64_str)
    body += _kpi_strip(fit_s, fit_v, val_s, sal_s, con_s, mins_s, goals_tot, asist_tot)
    body += _sw_section(prof.get("strengths",[]), prof.get("weaknesses",[]))
    if fit:
        body += _fit_section(fit, prof, fit_10)
    body += _radar_section(prof, pool_role_avg, crow, pool, crow)
    body += _strength_matrix(crow, pool)
    body += _top_pct_section(crow, pool, top_n=12)
    body += _group_section(crow, pool)
    body += _seasons_section(enr, cname)
    body += _footer(prof)

    full_html = (
        f'<!DOCTYPE html><html lang="es"><head>'
        f'<meta charset="utf-8"><title>Informe {cname}</title>'
        f'<style>{_CSS}</style>'
        f'</head><body>{body}</body></html>'
    )

    pdf_bytes = html_to_pdf(full_html)
    fname = f"informe_{_n(cname).replace(' ', '_')}.pdf"
    return fname, pdf_bytes
