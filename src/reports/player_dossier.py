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
