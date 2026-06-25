# -*- coding: utf-8 -*-
"""
coach_dossier.py  v7  (WeasyPrint + xhtml2pdf)
================================================
Informe PDF entrenador — diseno editorial profesional.
Layout: HTML tables (compatible con WeasyPrint y xhtml2pdf).
Paleta corporativa: #E30613 rojo · #0D0D0D negro · blanco.
"""
from __future__ import annotations
import csv
import json
import unicodedata
from datetime import date
from pathlib import Path

import pandas as pd

from src.utils.config import settings
from src.reports.pdf_base import (
    score_color, photo_b64, svg_gauge,
    radar_chart_b64, adn_chart_b64,
    html_to_pdf,
    GREEN, AMBER, LOW, LGREY, DARK, GREY,
)

ROOT = Path(__file__).resolve().parents[2]
PROC = Path(settings()["paths"]["data_processed"])

# ─── Ejes tacticos ────────────────────────────────────────────────────────────
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

SUB_LABELS = {
    "estilo":       ("Cercania ADN Rayo (estilo tactico)", "55%",
                     "Similitud coseno normalizada entre 8 ejes tecnico vs ADN"),
    "laliga":       ("Experiencia LaLiga", "15%",
                     "25 pts/temp 1a  ·  10 pts/temp 2a  ·  max 100"),
    "budget":       ("Encaje salarial vs presupuesto", "15%",
                     "Salario estimado vs margen salarial del club"),
    "squad_compat": ("Compatibilidad con la plantilla", "15%",
                     "Similitud estilo tecnico vs perfil plantilla actual"),
}


# ─── Helpers de datos ─────────────────────────────────────────────────────────
def _n(s):
    return unicodedata.normalize("NFKD", str(s)).encode("ascii","ignore").decode().lower().strip()

def _coach_photo(name):
    f = ROOT / "config" / "coach_photos.csv"
    if f.exists():
        for r in csv.DictReader(open(f, encoding="utf-8")):
            if _n(r.get("entrenador","")) == _n(name):
                return (r.get("imagen_local") or "").strip() or \
                       (r.get("imagen") or "").strip() or None
    return None

def _load_photo_bytes(name):
    url = _coach_photo(name)
    if not url: return None
    if url.startswith("/assets/"):
        fp = ROOT / "dashboard" / url.lstrip("/")
        if fp.exists(): return fp.read_bytes()
    elif url.startswith("http"):
        try:
            import requests
            r = requests.get(url, timeout=10, headers={"User-Agent":"RayoScoutingTool/1.0"})
            if r.status_code == 200 and r.content: return r.content
        except Exception: pass
    return None

def _manual(name):
    f = PROC / "coach_manual_notes.json"
    if f.exists():
        try: return json.load(open(f, encoding="utf-8")).get(name, {})
        except Exception: pass
    return {}

def _load_dna_target():
    try:
        from src.fit.dynamic_dna import build_dynamic_dna
        return build_dynamic_dna().get("target_style", {})
    except Exception: pass
    try:
        import yaml
        f = ROOT / "config" / "rayo_dna.yaml"
        if f.exists(): return yaml.safe_load(f.read_text(encoding="utf-8")).get("target_style",{})
    except Exception: pass
    return {}

def _fmt_salary(v):
    if not v: return "n/d"
    return f"{v/1e6:.1f}M EUR/anio" if v >= 1e6 else f"{v/1e3:.0f}K EUR/anio"

def _team_seasons_table(name):
    tn  = ROOT / "config" / "coach_tenures.csv"
    tsf = PROC / "team_seasons.parquet"
    if not tn.exists() or not tsf.exists(): return None
    ten = pd.read_csv(tn)
    ten = ten[ten["coach"].map(_n) == _n(name)]
    if ten.empty: return None
    ts  = pd.read_parquet(tsf)
    rows = []
    for _, t in ten.sort_values("season", ascending=False).iterrows():
        m = ts[
            (ts["league"] == t["league"]) &
            (ts["team"].str.contains(str(t["team"]).split()[0], case=False, na=False)) &
            (ts["season"].astype(str) == str(t["season"]))
        ]
        if m.empty: continue
        r = m.iloc[0]
        g = float(r.get("games_played") or 0) or 1
        def pg(col): return f"{float(r.get(col) or 0)/g:.1f}"
        rows.append([
            str(t["season"]), str(t["team"])[:22],
            str(int(r.get("possession_percentage") or 0)),
            pg("total_shots"), pg("goals"), pg("goals_conceded"),
            pg("recoveries"), str(int(r.get("clean_sheets") or 0)),
        ])
    return rows if rows else None


# ═══════════════════════════════════════════════════════════════════════════════
#  HTML BUILDERS — HTML tables, compatible xhtml2pdf + WeasyPrint
# ═══════════════════════════════════════════════════════════════════════════════

def _S(title: str) -> str:
    """Cabecera de seccion roja."""
    return (
        f'<div style="background-color:#E30613;color:white;font-weight:bold;'
        f'font-size:7pt;text-transform:uppercase;padding:4px 10px;'
        f'letter-spacing:0.6px;margin-top:9px;margin-bottom:4px;">'
        f'{title.upper()}</div>'
    )


def _pbar(label: str, pct: float, note: str = "", label_w: int = 200) -> str:
    """Barra horizontal — tabla anidada, compatible xhtml2pdf."""
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


def _html_table(headers, rows, note=None) -> str:
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
    html = (f'<table cellpadding="0" cellspacing="0" border="0" width="100%" '
            f'style="border-collapse:collapse;margin:3px 0;">'
            f'<thead><tr>{th}</tr></thead>'
            f'<tbody>{tbody}</tbody>'
            f'</table>')
    if note:
        html += (f'<div style="font-size:6pt;color:#9CA3AF;font-style:italic;margin-top:3px;">'
                 f'{note}</div>')
    return html


# ─── Topbar ───────────────────────────────────────────────────────────────────
def _topbar() -> str:
    d = date.today().strftime("%d/%m/%Y")
    return (
        f'<table cellpadding="0" cellspacing="0" border="0" width="100%" '
        f'style="background-color:#0D0D0D;border-bottom:2.5px solid #E30613;">'
        f'<tr>'
        f'<td style="padding:6px 10px;color:white;font-weight:bold;font-size:8.5pt;">'
        f'RAYO VALLECANO &mdash; ANALISIS DE ENTRENADOR</td>'
        f'<td style="padding:6px 10px;color:#9CA3AF;font-size:8pt;text-align:right;">'
        f'Confidencial &middot; {d}</td>'
        f'</tr>'
        f'</table>'
    )


# ─── Hero card ────────────────────────────────────────────────────────────────
def _hero_html(c, score_10, sal_str, foto_b64_str) -> str:
    nationality = c.get("nationality", "")
    age         = c.get("age", "?")
    last_club   = c.get("last_club", "n/d")
    style_main  = c.get("style_main", "n/d")
    style_tags  = ", ".join(c.get("style_tags", []) or [])
    avail       = "Libre" if c.get("available") else "Con contrato"
    ll_seas     = c.get("laliga_seasons", 0)
    contract_s  = c.get("contract_status", "")

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

    gauge_svg = svg_gauge(score_10, size=80)

    return (
        f'<table cellpadding="0" cellspacing="0" border="0" width="100%" '
        f'style="border:0.5px solid #E5E7EB;border-top:3px solid #E30613;'
        f'margin-top:6px;background-color:white;">'
        f'<tr>'
        f'{photo_cell}'
        f'<td style="padding:12px 8px;vertical-align:top;">'
        f'<div style="font-size:16pt;font-weight:bold;color:#0D0D0D;line-height:1.1;">{c["name"]}</div>'
        f'<div style="font-size:9pt;font-weight:bold;color:#E30613;margin-top:3px;">'
        f'{nationality} &middot; {age} anos &middot; Ult. club: {last_club}</div>'
        f'<div style="font-size:7.5pt;color:#374151;margin-top:5px;">'
        f'<span style="color:#9CA3AF;">Estilo: </span><strong>{style_main}</strong>'
        f'</div>'
        f'<div style="font-size:7.5pt;color:#9CA3AF;margin-top:2px;">{style_tags}</div>'
        f'<div style="font-size:7.5pt;color:#374151;margin-top:4px;">'
        f'<span style="color:#9CA3AF;">Situacion: </span><strong>{avail}</strong>'
        f'&nbsp;&middot;&nbsp;{contract_s}</div>'
        f'<div style="font-size:7.5pt;color:#374151;margin-top:2px;">'
        f'<span style="color:#9CA3AF;">Exp. LaLiga: </span><strong>{ll_seas} temp.</strong>'
        f'&nbsp;&nbsp;<span style="color:#9CA3AF;">Sal. est.: </span><strong>{sal_str}</strong>'
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
def _kpi_strip(rec_label, rec_col, score_10, sal_str, avail_s, ll_str) -> str:
    sc_col = score_color(float(score_10) * 10 if score_10 else 0, hi=70, lo=50)
    cards = [
        ("RECOMENDACION",
         f'<span style="color:{rec_col};font-weight:bold;font-size:9pt;">{rec_label}</span>'),
        ("FIT RAYO",
         f'<span style="color:{sc_col};font-weight:bold;font-size:9pt;">{score_10}/10</span>'),
        ("SALARIO EST.",   sal_str),
        ("DISPONIBILIDAD", avail_s),
        ("EXP. LALIGA",    ll_str),
    ]
    cells = ""
    for i, (lbl, val) in enumerate(cards):
        bl = "" if i == 0 else "border-left:2px solid white;"
        cells += (
            f'<td style="border:0.5px solid #E5E7EB;border-top:2.5px solid #E30613;'
            f'padding:7px 8px;background-color:white;vertical-align:top;{bl}">'
            f'<div style="font-size:5.5pt;color:#9CA3AF;text-transform:uppercase;'
            f'letter-spacing:0.4px;">{lbl}</div>'
            f'<div style="font-size:9pt;font-weight:bold;color:#0D0D0D;margin-top:2px;">'
            f'{val}</div>'
            f'</td>'
        )
    return (
        f'<table cellpadding="0" cellspacing="0" border="0" width="100%" '
        f'style="margin-top:6px;table-layout:fixed;">'
        f'<tr>{cells}</tr>'
        f'</table>'
    )


# ─── Badge + Pros / Contras / Riesgos ─────────────────────────────────────────
def _badge_and_pills(score_num, rec_label, rec_col, pros, cons, risks) -> str:
    # Badge de recomendacion
    if score_num >= 7:   badge_bg, badge_border = "#DCFCE7", GREEN
    elif score_num >= 5: badge_bg, badge_border = "#FEF3C7", AMBER
    else:                badge_bg, badge_border = "#FEE2E2", LOW

    badge = (
        f'<div style="margin-top:6px;">'
        f'<span style="display:inline-block;background-color:{badge_bg};color:{rec_col};'
        f'border:1px solid {badge_border};border-radius:4px;font-weight:bold;font-size:9pt;'
        f'padding:4px 16px;">{rec_label}</span>'
        f'</div>'
    )

    if not pros and not cons and not risks:
        return badge

    def _pills(items, bg, color):
        return "".join(
            f'<span style="background-color:{bg};color:{color};font-size:6.5pt;'
            f'padding:2px 7px;border-radius:9px;margin:2px 2px;display:inline-block;">'
            f'{s}</span>'
            for s in items
        )

    cells = ""
    if pros:
        cells += (
            f'<td style="background-color:#F0FDF4;border:0.5px solid #E5E7EB;'
            f'padding:6px 8px;width:33%;vertical-align:top;">'
            f'<div style="font-size:5.5pt;font-weight:bold;color:{GREEN};'
            f'text-transform:uppercase;margin-bottom:4px;">Fortalezas</div>'
            f'{_pills(pros, "#DCFCE7", GREEN)}'
            f'</td>'
        )
    if cons:
        cells += (
            f'<td style="background-color:#FFFBEB;border:0.5px solid #E5E7EB;'
            f'border-left:2px solid white;padding:6px 8px;width:33%;vertical-align:top;">'
            f'<div style="font-size:5.5pt;font-weight:bold;color:{AMBER};'
            f'text-transform:uppercase;margin-bottom:4px;">Contras</div>'
            f'{_pills(cons, "#FEF3C7", AMBER)}'
            f'</td>'
        )
    if risks:
        risk_pills = "".join(
            f'<span style="background-color:#FEE2E2;color:#DC2626;font-size:6.5pt;'
            f'padding:2px 7px;border-radius:9px;margin:2px 2px;display:inline-block;">'
            f'{RISK_LABELS.get(k,k)}: {v}</span>'
            for k, v in risks.items()
        )
        cells += (
            f'<td style="background-color:#FFF5F5;border:0.5px solid #FECDD3;'
            f'border-left:2px solid white;padding:6px 8px;vertical-align:top;">'
            f'<div style="font-size:5.5pt;font-weight:bold;color:#DC2626;'
            f'text-transform:uppercase;margin-bottom:4px;">Riesgos</div>'
            f'{risk_pills}'
            f'</td>'
        )

    pills_row = (
        f'<table cellpadding="0" cellspacing="0" border="0" width="100%" '
        f'style="margin-top:5px;">'
        f'<tr valign="top">{cells}</tr>'
        f'</table>'
    )
    return badge + pills_row


def _desc_box(desc: str) -> str:
    if not desc: return ""
    return (
        f'<div style="background-color:#F8FAFC;border-left:3px solid #E30613;'
        f'padding:7px 10px;margin:6px 0;font-size:7.5pt;color:#374151;">'
        f'<div style="font-weight:bold;color:#E30613;font-size:7pt;'
        f'text-transform:uppercase;letter-spacing:0.3px;margin-bottom:3px;">Descripcion</div>'
        f'{desc}'
        f'</div>'
    )


def _radar_section(axes, dna_target) -> str:
    vals_dict = {lab: float(axes[k]) for k, lab in AXES if axes.get(k) is not None}
    tgt_dict  = {lab: float(dna_target.get(k, {}).get("ideal", 50)) for k, lab in AXES}
    radar_b64 = radar_chart_b64(vals_dict, tgt_dict)
    rows = []
    for k, lab in AXES:
        if axes.get(k) is None: continue
        cv   = int(float(axes[k]))
        tv_r = dna_target.get(k, {}).get("ideal")
        tv   = int(float(tv_r)) if tv_r is not None else None
        diff = cv - tv if tv is not None else None
        if diff is None:
            ds, diff_col = "n/d", GREY
        elif abs(diff) <= 12:
            ds, diff_col = (f"+{abs(int(diff))}" if diff >= 0 else f"-{abs(int(diff))}"), GREEN
        else:
            ds, diff_col = (f"+{abs(int(diff))}" if diff >= 0 else f"-{abs(int(diff))}"), LOW
        rows.append((lab, str(cv), str(tv) if tv is not None else "n/d",
                     f'<span style="color:{diff_col};font-weight:bold;">{ds}</span>'))
    ax_tbl = _html_table(["Eje","Tecnico","ADN Rayo","Dif."], rows,
                         note="100=elite  |  50=media  |  0=peor. Percentil equipo dirigido vs liga.")
    # Radar centrado arriba + tabla ejes a ancho completo debajo (más legible, compatible xhtml2pdf)
    radar_img = (f'<div style="text-align:center;margin:5px 0 8px 0;">'
                 f'<img src="data:image/png;base64,{radar_b64}" width="300" height="230"/>'
                 f'</div>'
                 if radar_b64 else "")
    return (
        _S("Estilo de juego — Radar tactico") +
        radar_img +
        f'<div style="font-size:7.5pt;font-weight:bold;color:#E30613;margin-bottom:4px;">Ejes vs ADN Rayo</div>' +
        ax_tbl
    )


def _adn_section(axes, dna_target) -> str:
    b64 = adn_chart_b64(axes, dna_target, AXES)
    if not b64: return ""
    return (
        _S("Comparativa tactica vs ADN Rayo") +
        # Ancho fijo en px para xhtml2pdf (width="100%" no funciona en img con xhtml2pdf)
        f'<img src="data:image/png;base64,{b64}" width="527" height="130" style="display:block;"/>'
        f'<div style="font-size:6pt;color:#9CA3AF;font-style:italic;margin-top:3px;">'
        f'Verde: dif &le;12 pts (alineado)  |  Rojo: &gt;12 pts (desajuste). Delta=Tecnico-ADN.</div>'
    )


def _fit_eval_section(ev, score_10, score_num) -> str:
    sub  = ev.get("subscores", {})
    bars = []
    rows = []
    for k, (label, weight, method) in SUB_LABELS.items():
        v = sub.get(k)
        if v is not None:
            bars.append((f"{label}  ({weight})", float(v), method))
            rows.append((label, weight, str(int(float(v))), method))
    fit_col = score_color(score_num * 10, hi=70, lo=50)
    html = _S("Evaluacion — Fit Rayo")
    html += (f'<div style="font-size:11pt;font-weight:bold;color:{fit_col};margin-bottom:6px;">'
             f'Score global: {score_10} / 10</div>')
    if bars:
        html += "".join(_pbar(lab, val, note, label_w=230) for lab, val, note in bars)
        html += '<div style="margin-top:6px;"></div>'
    if rows:
        html += _html_table(["Sub-score","Peso","Valor /100","Metodologia"], rows)
    html += (f'<div style="font-size:6pt;color:#9CA3AF;font-style:italic;margin-top:4px;">'
             f'Formula: Fit=(Estilo x0.55)+(LaLiga x0.15)+(Presupuesto x0.15)+(Plantilla x0.15).</div>')
    return html


def _seasons_section(c) -> str:
    tst = _team_seasons_table(c["name"])
    if not tst: return ""
    headers = ["Temp.","Equipo","Pos%","Tiros/p","Goles/p","Encaj./p","Recup./p","P.cero"]
    return (_S("Equipos dirigidos — estadisticas de equipo") +
            _html_table(headers, tst, note="Pos%=posesion  |  /p=por partido  |  P.cero=porterias a cero."))


def _footer(c) -> str:
    d   = date.today().strftime("%d/%m/%Y")
    cov = c.get("coverage", {})
    tms = ", ".join(cov.get("teams",[]) or []) or "n/d"
    n_r = cov.get("n_rows", 0)
    return (f'<div style="border-top:1.5px solid #E30613;margin-top:14px;padding-top:5px;'
            f'font-size:6pt;color:#9CA3AF;font-style:italic;">'
            f'Cobertura OPTA: {tms}  |  {n_r} temp.  |  Generado {d}  |  '
            f'Rayo Vallecano - Direccion Deportiva  |  Confidencial</div>')


_CSS = (
    "@page { size: A4; margin: 1.2cm; }\n"
    "* { margin: 0; padding: 0; box-sizing: border-box; }\n"
    "body { font-family: Arial, Helvetica, sans-serif; font-size: 9pt; color: #111827; background: white; line-height: 1.4; }\n"
    "img { display: block; }\n"
    "table { border-spacing: 0; }\n"
)


def build_coach_dossier(name):
    profiles = json.load(open(PROC / "coach_profiles.json", encoding="utf-8"))
    c = next((x for x in profiles if _n(x["name"]) == _n(name)), None)
    if c is None:
        raise ValueError(f"Entrenador '{name}' no encontrado")
    ev         = c.get("evaluation", {})
    axes       = c.get("axes", {})
    man        = _manual(c["name"])
    dna_target = _load_dna_target()
    score_10   = ev.get("score_10", 0)
    score_num  = float(score_10) if score_10 not in (None, "n/d", "") else 0.0
    if score_num >= 7:   rec_label, rec_col = "RECOMENDADO",    GREEN
    elif score_num >= 5: rec_label, rec_col = "VALORAR",        AMBER
    else:                rec_label, rec_col = "NO RECOMENDADO", LOW
    sal_str  = _fmt_salary(c.get("salary_estimate_eur"))
    avail_s  = "Libre" if c.get("available") else "Con contrato"
    ll_str   = f"{c.get('laliga_seasons', 0)} temp."
    pros     = (ev.get("pros_auto",[]) or []) + man.get("pros",[])
    cons     = (ev.get("contras_auto",[]) or []) + man.get("contras",[])
    risks    = ev.get("risks", {})
    foto_b64_str = None
    img_bytes = _load_photo_bytes(c["name"])
    if img_bytes:
        try: foto_b64_str = photo_b64(img_bytes)
        except Exception: pass
    body  = _topbar()
    body += _hero_html(c, score_10, sal_str, foto_b64_str)
    body += _kpi_strip(rec_label, rec_col, score_10, sal_str, avail_s, ll_str)
    body += _badge_and_pills(score_num, rec_label, rec_col, pros, cons, risks)
    body += _desc_box(c.get("description_auto", ""))
    if axes:
        body += _radar_section(axes, dna_target)
        body += _adn_section(axes, dna_target)
    body += _fit_eval_section(ev, score_10, score_num)
    body += _seasons_section(c)
    body += _footer(c)
    full_html = (
        '<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">'
        f'<title>Informe Entrenador {c["name"]}</title>'
        f'<style>{_CSS}</style></head><body>{body}</body></html>'
    )
    pdf_bytes = html_to_pdf(full_html)
    fname = f"informe_entrenador_{_n(c['name']).replace(' ','_')}.pdf"
    return fname, pdf_bytes
