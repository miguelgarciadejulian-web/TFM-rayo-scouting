# -*- coding: utf-8 -*-
"""
coach_dossier.py  v6  (WeasyPrint)
====================================
Informe PDF entrenador — diseno moderno con WeasyPrint + HTML/CSS.
"""
from __future__ import annotations
import csv
import io
import json
import unicodedata
from datetime import date
from pathlib import Path

import pandas as pd

from src.utils.config import settings
from src.reports.pdf_base import (
    score_color, photo_b64, svg_gauge,
    hbar_chart, html_table, section_header,
    radar_chart_b64, adn_chart_b64,
    build_html_doc, html_to_pdf,
    GREEN, AMBER, LOW, LGREY, DARK, GREY, GRID,
)

ROOT = Path(__file__).resolve().parents[2]
PROC = Path(settings()["paths"]["data_processed"])

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
    "estilo":       ("Cercania al ADN Rayo (estilo tactico)", "55%",
                     "Similitud coseno normalizada entre 8 ejes tecnico vs ADN"),
    "laliga":       ("Experiencia LaLiga", "15%",
                     "25 pts/temp 1a  .  10 pts/temp 2a  .  max 100"),
    "budget":       ("Encaje salarial vs presupuesto", "15%",
                     "Salario estimado vs margen salarial del club"),
    "squad_compat": ("Compatibilidad con la plantilla", "15%",
                     "Similitud estilo tecnico vs perfil plantilla actual"),
}


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
        def pg(c): return f"{float(r.get(c) or 0)/g:.1f}"
        rows.append([
            str(t["season"]), str(t["team"])[:22],
            str(int(r.get("possession_percentage") or 0)),
            pg("total_shots"), pg("goals"), pg("goals_conceded"),
            pg("recoveries"), str(int(r.get("clean_sheets") or 0)),
        ])
    return rows if rows else None


# ── HTML builders ─────────────────────────────────────────────────────────────

def _topbar():
    d = date.today().strftime("%d %b %Y").lstrip("0")
    return (f'<div class="topbar">'
            f'<span class="topbar-l">RAYO VALLECANO &mdash; DIRECCION DEPORTIVA</span>'
            f'<span class="topbar-r">{d}</span></div>')

def _hero_html(c, score_10, sal_str, foto_b64_str):
    nationality = c.get("nationality","")
    age         = c.get("age","?")
    last_club   = c.get("last_club","n/d")
    style_main  = c.get("style_main","n/d")
    style_tags  = ", ".join(c.get("style_tags",[]) or [])
    avail       = "Libre" if c.get("available") else "Con contrato"
    ll_seas     = c.get("laliga_seasons", 0)
    contract_s  = c.get("contract_status","")

    photo_html = ""
    if foto_b64_str:
        photo_html = f'<img class="hero-photo" src="data:image/jpeg;base64,{foto_b64_str}" alt="foto">'

    gauge_html = (f'<div class="gauge-wrap">'
                  f'{svg_gauge(score_10, size=84)}'
                  f'<div class="gauge-sublbl">FIT RAYO</div></div>')

    return (
        f'<div class="hero">{photo_html}'
        f'<div class="hero-info">'
        f'<div class="hero-name">{c["name"]}</div>'
        f'<div class="hero-sub">{nationality} &middot; {age} anos &middot; Ult. club: <b>{last_club}</b></div>'
        f'<div class="hero-bio" style="margin-top:6px;"><span class="lbl">Estilo: </span><strong>{style_main}</strong></div>'
        f'<div class="hero-row">{style_tags}</div>'
        f'<div class="hero-row" style="margin-top:4px;"><span class="lbl">Situacion: </span>'
        f'<strong>{avail}</strong>&nbsp;&middot;&nbsp;{contract_s}</div>'
        f'<div class="hero-row"><span class="lbl">Exp. LaLiga: </span>'
        f'<strong>{ll_seas} temp.</strong>&nbsp;&middot;&nbsp;'
        f'<span class="lbl">Salario est.: </span><strong>{sal_str}</strong></div>'
        f'</div>{gauge_html}</div>'
    )

def _kpi_strip(rec_label, rec_col, score_10, sal_str, avail_s, ll_str):
    sc_col = score_color(float(score_10) * 10 if score_10 else 0, hi=70, lo=50)
    cards = [
        ("RECOMENDACION",  f'<span style="color:{rec_col};font-weight:bold;">{rec_label}</span>'),
        ("FIT RAYO",       f'<span style="color:{sc_col};">{score_10}/10</span>'),
        ("SALARIO EST.",   sal_str),
        ("DISPONIBILIDAD", avail_s),
        ("EXP. LALIGA",    ll_str),
    ]
    html = '<div class="kpi-row">'
    for lbl, val in cards:
        html += f'<div class="kpi-card"><div class="kpi-label">{lbl}</div><div class="kpi-value">{val}</div></div>'
    return html + '</div>'

def _badge_and_pills(score_num, rec_label, rec_col, pros, cons, risks):
    cls = "badge-green" if score_num >= 7 else ("badge-amber" if score_num >= 5 else "badge-red")
    html = f'<div style="margin-top:5px;"><span class="badge {cls}">{rec_label}</span></div>'

    if not pros and not cons and not risks:
        return html
    html += '<div class="sw-row" style="margin-top:6px;">'
    if pros:
        pills = "".join(f'<span class="pill pill-green">{p}</span>' for p in pros)
        html += f'<div class="sw-box sw-green"><div class="sw-title">Fortalezas</div><div class="pills">{pills}</div></div>'
    if cons:
        pills = "".join(f'<span class="pill pill-amber">{c}</span>' for c in cons)
        html += f'<div class="sw-box sw-amber"><div class="sw-title">Contras</div><div class="pills">{pills}</div></div>'
    if risks:
        pills = "".join(f'<span class="pill pill-red">{RISK_LABELS.get(k,k)}: {v}</span>' for k,v in risks.items())
        html += (f'<div class="sw-box" style="background:#FFF5F5;border:0.5px solid #FECDD3;">'
                 f'<div class="sw-title" style="color:#DC2626;">Riesgos</div>'
                 f'<div class="pills">{pills}</div></div>')
    return html + '</div>'

def _desc_box(desc):
    if not desc: return ""
    return (f'<div class="info-box" style="margin-top:6px;">'
            f'<div class="info-label">Descripcion</div>{desc}</div>')

def _radar_section(axes, dna_target):
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
        ds   = (f"+{abs(int(diff))}" if diff is not None and diff >= 0
                else f"-{abs(int(diff))}" if diff is not None else "n/d")
        col  = GREEN if (diff is not None and abs(diff) <= 12) else (LOW if diff is not None else GREY)
        rows.append((lab, str(cv), str(tv) if tv is not None else "n/d",
                     f'<span style="color:{col};font-weight:bold;">{ds}</span>'))

    ax_tbl = html_table(["Eje","Tecnico","ADN Rayo","Dif."], rows)
    radar_img = ""
    if radar_b64:
        radar_img = f'<img src="data:image/png;base64,{radar_b64}" style="width:100%;max-width:265px;display:block;margin-bottom:5px;" alt="radar">'
    note = '<div class="formula-note" style="margin-top:4px;">100 = elite &middot; 50 = media &middot; 0 = peor. Percentil del equipo dirigido vs la liga.</div>'

    return (section_header("Estilo de juego — Radar tactico") +
            f'<div class="two-col"><div class="col-l">{radar_img}</div>'
            f'<div class="col-r"><div class="sub-title">Ejes vs ADN Rayo</div>{ax_tbl}{note}</div></div>')

def _adn_section(axes, dna_target):
    b64 = adn_chart_b64(axes, dna_target, AXES)
    if not b64: return ""
    img  = f'<img src="data:image/png;base64,{b64}" style="width:100%;display:block;" alt="ADN">'
    note = ('<div class="formula-note" style="margin-top:3px;">Verde: diferencia &le;12 pts (alineado) &middot; '
            'Rojo: diferencia &gt;12 pts (posible desajuste). Delta = Tecnico &minus; ADN objetivo.</div>')
    return section_header("Comparativa tactica vs ADN Rayo") + img + note

def _fit_eval_section(ev, score_10, score_num):
    sub = ev.get("subscores", {})
    rows, bars = [], []
    for k, (label, weight, method) in SUB_LABELS.items():
        v = sub.get(k)
        if v is not None:
            rows.append((label, weight, str(int(float(v))), method))
            bars.append((f"{label}  ({weight})", float(v)))

    fit_col = score_color(score_num * 10, hi=70, lo=50)
    html  = section_header("Evaluacion — Fit Rayo")
    html += (f'<div style="font-size:11pt;font-weight:bold;color:{fit_col};margin-bottom:6px;">'
             f'Score global: {score_10} / 10</div>')
    if bars:
        html += hbar_chart(bars, label_w="225px")
        html += '<div style="margin-top:6px;"></div>'
    if rows:
        html += html_table(["Sub-score","Peso","Valor /100","Metodologia"], rows)
    html += ('<div class="formula-note" style="margin-top:4px;">'
             'Formula: Fit = (Estilo x 0.55) + (LaLiga x 0.15) + (Presupuesto x 0.15) + (Plantilla x 0.15).'
             '</div>')
    return html

def _seasons_section(c):
    tst = _team_seasons_table(c["name"])
    if not tst: return ""
    headers = ["Temp.","Equipo","Pos%","Tiros/p","Goles/p","Encaj./p","Recup./p","P.cero"]
    note = ('<div class="formula-note" style="margin-top:3px;">Pos% = posesion &middot; /p = por partido &middot; P.cero = porterias a cero.</div>')
    return section_header("Equipos dirigidos — estadisticas de equipo") + html_table(headers, tst) + note

def _footer(c):
    d   = date.today().strftime("%d %b %Y").lstrip("0")
    cov = c.get("coverage", {})
    tms = ", ".join(cov.get("teams",[]) or []) or "n/d"
    n_r = cov.get("n_rows", 0)
    return (f'<div class="footer">Cobertura OPTA: {tms} &middot; {n_r} temporadas &middot; '
            f'Generado {d} &middot; Rayo Vallecano &mdash; Direccion Deportiva &middot; Confidencial</div>')


# ── Funcion principal ─────────────────────────────────────────────────────────

def build_coach_dossier(name):
    profiles = json.load(open(PROC / "coach_profiles.json", encoding="utf-8"))
    c = next((x for x in profiles if _n(x["name"]) == _n(name)), None)
    if c is None:
        raise ValueError(f"Entrenador '{name}' no encontrado")

    ev         = c.get("evaluation", {})
    axes       = c.get("axes", {})
    man        = _manual(c["name"])
    dna_target = _load_dna_target()

    score_10  = ev.get("score_10", 0)
    score_num = float(score_10) if score_10 not in (None,"n/d","") else 0.0

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
    body += _desc_box(c.get("description_auto",""))

    if axes:
        body += _radar_section(axes, dna_target)
        body += _adn_section(axes, dna_target)

    body += _fit_eval_section(ev, score_10, score_num)
    body += _seasons_section(c)
    body += _footer(c)

    html      = build_html_doc(body, title=f"Informe Entrenador {c['name']}")
    pdf_bytes = html_to_pdf(html)
    fname     = f"informe_entrenador_{_n(c['name']).replace(' ','_')}.pdf"
    return fname, pdf_bytes
