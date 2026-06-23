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
    # (campo, etiqueta, ancho_px)  — 10 cols, suma ~650px (deja margen en A4 703px)
    ("season",                    "Temporada", 68),
    ("team",                      "Equipo",   183),
    ("minutes",                   "Min",       58),
    ("goals",                     "G",         36),
    ("goal_assists",               "A",         36),
    ("total_shots",                "Tir",       36),
    ("shots_on_target_inc_goals",  "TaP",       36),
    ("tackles_won",                "Ent",       36),
    ("interceptions",              "Int",       36),
    ("recoveries",                 "Rec",       36),
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


def _page_break() -> str:
    """Salto de pagina explicito — compatible con xhtml2pdf y WeasyPrint."""
    return '<div style="page-break-after:always;margin:0;padding:0;height:0;"></div>'


def _mini_header(cname: str, section: str) -> str:
    """Cabecera minima para paginas 2 y 3 — identifica al jugador."""
    d = date.today().strftime("%d/%m/%Y")
    return (
        f'<table cellpadding="0" cellspacing="0" border="0" width="100%" '
        f'style="border-bottom:2px solid #E30613;margin-bottom:8px;">'
        f'<tr>'
        f'<td style="font-size:8.5pt;font-weight:bold;color:#0D0D0D;padding-bottom:4px;">'
        f'{cname} &mdash; <span style="color:#E30613;">{section}</span></td>'
        f'<td style="text-align:right;font-size:7pt;color:#9CA3AF;padding-bottom:4px;">'
        f'Rayo Vallecano &middot; Confidencial &middot; {d}</td>'
        f'</tr>'
        f'</table>'
    )


def _pbar(label: str, pct: float, note: str = "", label_w: int = 155) -> str:
    """Barra de percentil horizontal — tabla anidada, compatible xhtml2pdf."""
    pct = max(0.0, min(float(pct), 100.0))
    col = GREEN if pct >= 68 else (AMBER if pct >= 44 else LOW)
    note_html = (f'<br/><span style="font-size:5pt;color:#9CA3AF;">{note}</span>'
                 if note else "")
    return (
        f'<table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin:2.5px 0;">'
        f'<tr valign="middle">'
        f'<td width="{label_w}" style="width:{label_w}px;text-align:right;'
        f'padding-right:6px;font-size:6.5pt;color:#374151;vertical-align:middle;">'
        f'{label}{note_html}</td>'
        f'<td style="vertical-align:middle;">'
        f'<table cellpadding="0" cellspacing="0" border="0" width="100%">'
        f'<tr>'
        f'<td width="{pct:.0f}%" style="background-color:{col};height:12px;" height="12">&nbsp;</td>'
        f'<td style="background-color:#EBEBEB;height:12px;" height="12">&nbsp;</td>'
        f'</tr>'
        f'</table>'
        f'</td>'
        f'<td width="30" style="width:30px;font-size:7.5pt;font-weight:bold;'
        f'color:{col};padding-left:5px;vertical-align:middle;text-align:right;">'
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
def _fit_label(v: float) -> str:
    """Etiqueta interpretativa del Fit Rayo (v en escala 0-100)."""
    if v >= 75: return "Excelente encaje"
    if v >= 65: return "Buen encaje"
    if v >= 50: return "Encaje moderado"
    return "Encaje limitado"


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

    fit_v_raw = float(fit_10) * 10 if fit_10 else 0
    gauge_svg  = svg_gauge(fit_10, size=105)
    fit_interp = _fit_label(fit_v_raw)
    fit_col    = GREEN if fit_v_raw >= 60 else (AMBER if fit_v_raw >= 45 else LOW)

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
        + (f'&nbsp;&nbsp;<span style="color:#9CA3AF;">Pais: </span>{nation}' if nation else "")
        + f'</div>'
        f'<div style="font-size:7.5pt;color:#374151;margin-top:2px;">'
        f'<span style="color:#9CA3AF;">Contrato hasta: </span><strong>{contr}</strong>'
        f'&nbsp;&nbsp;<span style="color:#9CA3AF;">Valor TM: </span><strong>{val_s}</strong>'
        f'&nbsp;&nbsp;<span style="color:#9CA3AF;">Sal. est.: </span><strong>{sal_s}</strong>'
        f'</div>'
        f'</td>'
        f'<td width="130" style="width:130px;text-align:center;vertical-align:middle;'
        f'padding:10px 12px;border-left:1px solid #F3F4F6;">'
        f'{gauge_svg}'
        f'<div style="font-size:10pt;font-weight:bold;color:{fit_col};margin-top:2px;">'
        f'{int(round(float(fit_10 or 0)*10))}/100</div>'
        f'<div style="font-size:6pt;font-weight:bold;color:#E30613;text-transform:uppercase;'
        f'letter-spacing:0.5px;">FIT RAYO</div>'
        f'<div style="font-size:6.5pt;color:#374151;margin-top:3px;font-style:italic;">'
        f'{fit_interp}</div>'
        f'</td>'
        f'</tr>'
        f'</table>'
    )


# ─── KPI Strip ────────────────────────────────────────────────────────────────
def _kpi_strip(fit_s, fit_v, val_s, sal_s, con_s, mins_s, goals_tot, asist_tot) -> str:
    # FIT RAYO ya aparece destacado en el gauge del hero — aquí solo datos económicos/rendimiento
    cards = [
        ("VALOR TM",     val_s),
        ("SALARIO EST.", sal_s),
        ("CONTRATO",     con_s),
        ("MIN. TOTALES", mins_s),
        ("G + A",        f'{int(goals_tot)}G &nbsp; {int(asist_tot)}A'),
    ]
    cells = ""
    for i, (label, value) in enumerate(cards):
        bl = "" if i == 0 else "border-left:2px solid white;"
        cells += (
            f'<td style="border:0.5px solid #E5E7EB;border-top:2.5px solid #E30613;'
            f'padding:7px 10px;background-color:white;vertical-align:top;{bl}">'
            f'<div style="font-size:5.5pt;color:#9CA3AF;text-transform:uppercase;'
            f'letter-spacing:0.4px;">{label}</div>'
            f'<div style="font-size:9.5pt;font-weight:bold;color:#0D0D0D;margin-top:2px;">'
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

    def _item_rows(items, color, bg_even, bg_odd):
        rows = ""
        for i, s in enumerate(items):
            bg = bg_even if i % 2 == 0 else bg_odd
            rows += (
                f'<tr style="background-color:{bg};">'
                f'<td style="padding:3px 8px 3px 10px;font-size:7pt;color:#374151;'
                f'border-left:2.5px solid {color};border-bottom:0.3px solid #E5E7EB;">'
                f'{s}</td>'
                f'</tr>'
            )
        return (f'<table cellpadding="0" cellspacing="0" border="0" width="100%" '
                f'style="border-collapse:collapse;">{rows}</table>')

    s_td = (
        f'<td width="260" style="width:260px;background-color:#F0FDF4;'
        f'border:0.5px solid #D1FAE5;padding:6px 8px;vertical-align:top;">'
        f'<div style="font-size:5.5pt;font-weight:bold;color:{GREEN};'
        f'text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px;">Fortalezas</div>'
        f'{_item_rows(strengths, GREEN, "#F0FDF4", "#DCFCE7")}'
        f'</td>'
    ) if strengths else '<td width="260" style="width:260px;"></td>'

    w_td = (
        f'<td style="background-color:#FFFBEB;border:0.5px solid #FDE68A;'
        f'border-left:3px solid white;padding:6px 8px;vertical-align:top;">'
        f'<div style="font-size:5.5pt;font-weight:bold;color:{AMBER};'
        f'text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px;">Debilidades</div>'
        f'{_item_rows(weaknesses, AMBER, "#FFFBEB", "#FEF3C7")}'
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
    return _S("Fit Rayo — Encaje con el club") + bars + tbl + note


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
    """Tabla totales de carrera — las TRES columnas con ancho px explicito.
    xhtml2pdf con table-layout:fixed asigna 0px a columnas sin width explicito,
    haciendo que los valores se solapen. Solucion: anchos fijos en todas las celdas
    y anchura absoluta en la tabla (no %).
    A4 - margenes 1.2cm ≈ 703px: W0+W1+W2 = 345+180+178 = 703px.
    """
    W0, W1, W2 = 345, 180, 178  # Metrica | Total | /90'
    def _th(h, w):
        return (f'<td width="{w}" style="width:{w}px;background-color:#E30613;color:white;'
                f'font-weight:bold;padding:3px 4px;font-size:6.5pt;text-transform:uppercase;">'
                f'{h}</td>')
    def _td(c, w, align="left"):
        return (f'<td width="{w}" style="width:{w}px;padding:3px 4px;color:#111827;'
                f'border-bottom:0.3px solid #E5E7EB;font-size:7pt;text-align:{align};">'
                f'{c}</td>')
    head = _th("Metrica", W0) + _th("Total", W1) + _th("/90'", W2)
    body = ""
    for i, (lab, total, p90) in enumerate(tot_rows):
        bg = "#ffffff" if i % 2 == 0 else "#F9FAFB"
        body += (f'<tr style="background-color:{bg};">'
                 f'{_td(lab, W0)}{_td(total, W1, "right")}{_td(p90, W2, "right")}'
                 f'</tr>')
    return (f'<table cellpadding="0" cellspacing="0" border="0" width="703" '
            f'style="border-collapse:collapse;margin:3px 0;table-layout:fixed;'
            f'page-break-inside:avoid;">'
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
             f'style="margin-top:4px;page-break-inside:avoid;">')
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
            grp_header = (
                f'<div style="font-size:7pt;font-weight:bold;color:#374151;'
                f'background-color:#F3F4F6;border-left:3px solid #E30613;'
                f'padding:3px 8px;margin-bottom:4px;margin-top:6px;">{grp.upper()}</div>'
            )
            content = grp_header
            if rows:
                content += "".join(_pbar(lab, pct, note, label_w=110) for lab, pct, note in rows)
            html += f'<td width="{col_w}" style="width:{col_w}px;{pad_r}vertical-align:top;">{content}</td>'
        if len(pair) == 1:
            html += '<td></td>'
        html += '</tr>'
    html += '</table>'
    return html


# ─── Estadisticas por temporada ───────────────────────────────────────────────
def _seasons_section(enr, cname) -> str:
    prows = enr[enr["name"] == cname].copy()
    if prows.empty:
        return ""
    order = {"2025-2026":6,"2025":5,"2024-2025":4,"2023-2024":3,"2022-2023":2,"2021-2022":1}
    prows["_o"] = prows["season"].map(order).fillna(0)
    prows = prows.sort_values("_o", ascending=False)

    # Solo columnas presentes en los datos
    cols = [(c, lbl, w) for c, lbl, w in SEASON_COLS if c in prows.columns]

    # Cabecera con anchos explícitos (px) — imprescindible para xhtml2pdf
    def _th(lbl, w):
        return (f'<td width="{w}" style="width:{w}px;background-color:#E30613;color:white;'
                f'font-weight:bold;padding:3px 5px;font-size:6pt;text-transform:uppercase;'
                f'white-space:nowrap;">{lbl}</td>')

    def _td(val, w, align="left"):
        return (f'<td width="{w}" style="width:{w}px;padding:3px 5px;font-size:7pt;'
                f'color:#111827;border-bottom:0.3px solid #E5E7EB;text-align:{align};'
                f'white-space:nowrap;">{val}</td>')

    head_html = "".join(_th(lbl, w) for _, lbl, w in cols)
    body_html = ""
    row_count  = 0
    for _, rw in prows.iterrows():
        # Omitir filas sin minutos (temporadas sin datos)
        raw_min = rw.get("minutes")
        if pd.isna(raw_min) or float(raw_min or 0) < 1:
            continue
        bg = "#ffffff" if row_count % 2 == 0 else "#F9FAFB"
        row_cells = ""
        for c, _, w in cols:
            v = rw.get(c)
            if c == "minutes" and pd.notna(v):
                v = int(float(v))
            elif c not in ("season", "team") and isinstance(v, float) and pd.notna(v):
                v = int(v)
            val   = "" if pd.isna(v) else str(v)
            align = "left" if c in ("season", "team") else "right"
            row_cells += _td(val, w, align)
        body_html += f'<tr style="background-color:{bg};">{row_cells}</tr>'
        row_count += 1

    if not body_html:
        return ""

    tbl = (f'<table cellpadding="0" cellspacing="0" border="0" width="100%" '
           f'style="border-collapse:collapse;margin:3px 0;table-layout:fixed;">'
           f'<thead><tr>{head_html}</tr></thead>'
           f'<tbody>{body_html}</tbody>'
           f'</table>')
    leyenda = (f'<div style="font-size:5.5pt;color:#9CA3AF;font-style:italic;margin-top:3px;">'
               f'G=Goles &middot; A=Asistencias &middot; Tir=Tiros totales &middot; '
               f'TaP=Tiros a puerta &middot; Ent=Entradas ganadas &middot; '
               f'Int=Intercepciones &middot; Rec=Recuperaciones'
               f'</div>')
    return _S("Estadisticas por temporada (OPTA)") + tbl + leyenda


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
ta