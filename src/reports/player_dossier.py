# -*- coding: utf-8 -*-
"""
player_dossier.py  v6  (WeasyPrint)
=====================================
Informe PDF jugador — diseno moderno con WeasyPrint + HTML/CSS.
Paleta corporativa: rojo #E30613 / blanco / negro.
"""
from __future__ import annotations
import io
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
    score_color, score_bg, fig_to_b64, photo_b64,
    svg_gauge, hbar_chart, html_table, section_header,
    radar_chart_b64, build_html_doc, html_to_pdf,
    GREEN, AMBER, LOW, RED, LGREY, DARK, GREY,
)


# ─── Rutas ───────────────────────────────────────────────────────────────────
PROC = Path(settings()["paths"]["data_processed"])

# ─── Constantes de metricas ───────────────────────────────────────────────────
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


# ─── Helpers ─────────────────────────────────────────────────────────────────
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
    """Percentil del jugador en una metrica vs pool."""
    if metric not in pool.columns: return None
    ser = pd.to_numeric(pool[metric], errors="coerce")
    pr  = ser.rank(pct=True) * 100
    idx = pool.index[pool["name"] == crow.get("name")]
    if len(idx) == 0: return None
    pct = pr.get(idx[0])
    return float(pct) if pd.notna(pct) else None


# ─── Construccion HTML ────────────────────────────────────────────────────────

def _topbar() -> str:
    d = date.today().strftime("%d %b %Y").lstrip("0")
    return (f'<div class="topbar">'
            f'<span class="topbar-l">RAYO VALLECANO &mdash; INFORME DE SCOUTING</span>'
            f'<span class="topbar-r">{d}</span>'
            f'</div>')


def _hero_html(cname, crow, mv, prof, fit_v, fit_10, sal_s, foto_b64_str) -> str:
    team_s   = str(crow.get("team", ""))
    league_s = str(crow.get("league", "")).replace("_", " ")
    pos_s    = str(mv.get("position") or crow.get("position_group") or "")
    age_v    = int(float(mv.get("age") or 0)) if mv.get("age") else 0
    ht_s     = str(mv.get("height") or "")
    _ft = {"right":"Der.","left":"Izq.","both":"Ambos","derecho":"Der.","zurdo":"Izq."}
    foot_s   = _ft.get(str(mv.get("foot") or "").strip().lower(), "")
    role_lbl = prof.get("primary_role_label", "n/d")
    sec_roles = ", ".join(prof.get("secondary_roles_labels", []) or [])

    bio_parts = filter(None, [
        f"{age_v} anos" if age_v else None,
        ht_s or None,
        f"Pie {foot_s}" if foot_s else None,
        pos_s or None,
    ])
    bio_s = "  &middot;  ".join(bio_parts)

    photo_html = ""
    if foto_b64_str:
        photo_html = f'<img class="hero-photo" src="data:image/jpeg;base64,{foto_b64_str}" alt="foto">'

    gauge_svg = svg_gauge(fit_10, size=84)
    gauge_html = (f'<div class="gauge-wrap">'
                  f'{gauge_svg}'
                  f'<div class="gauge-sublbl">FIT RAYO</div>'
                  f'</div>')

    return (
        f'<div class="hero">'
        f'{photo_html}'
        f'<div class="hero-info">'
        f'<div class="hero-name">{cname}</div>'
        f'<div class="hero-sub">{team_s} &middot; {league_s}</div>'
        f'<div class="hero-bio">{bio_s}</div>'
        f'<div class="hero-row" style="margin-top:5px;">'
        f'<span class="lbl">Rol principal: </span><strong>{role_lbl}</strong>'
        f'</div>'
        f'<div class="hero-row">'
        f'<span class="lbl">Roles sec.: </span>{sec_roles}'
        f'</div>'
        f'<div class="hero-row" style="margin-top:4px;">'
        f'<span class="lbl">Salario est.: </span><strong>{sal_s}</strong>'
        f'</div>'
        f'</div>'
        f'{gauge_html}'
        f'</div>'
    )


def _kpi_strip(fit_s, fit_v, val_s, sal_s, con_s, mins_s) -> str:
    col = score_color(fit_v, hi=65, lo=45)
    cards = [
        ("FIT RAYO",      f'<span style="color:{col};font-size:10.5pt;font-weight:bold;">{fit_s}</span>'),
        ("VALOR TM",      val_s),
        ("SALARIO EST.",  sal_s),
        ("CONTRATO",      con_s),
        ("MINUTOS HIST.", mins_s),
    ]
    html = '<div class="kpi-row">'
    for label, value in cards:
        html += (f'<div class="kpi-card">'
                 f'<div class="kpi-label">{label}</div>'
                 f'<div class="kpi-value">{value}</div>'
                 f'</div>')
    html += '</div>'
    return html


def _sw_html(strengths, weaknesses) -> str:
    if not strengths and not weaknesses:
        return ""
    html = '<div class="sw-row">'
    if strengths:
        pills = "".join(f'<span class="pill pill-green">{s}</span>' for s in strengths)
        html += (f'<div class="sw-box sw-green">'
                 f'<div class="sw-title">Fortalezas</div>'
                 f'<div class="pills">{pills}</div>'
                 f'</div>')
    if weaknesses:
        pills = "".join(f'<span class="pill pill-amber">{w}</span>' for w in weaknesses)
        html += (f'<div class="sw-box sw-amber">'
                 f'<div class="sw-title">Debilidades</div>'
                 f'<div class="pills">{pills}</div>'
                 f'</div>')
    html += '</div>'
    return html


def _fit_section(fit, prof, fit_10) -> str:
    pot_map = {"muy alto":95,"alto":80,"estable":65,"en meseta":50,"veterania":35}
    pot_s   = pot_map.get(prof.get("potential",""), 55)
    comps = [
        ("Compatib. plantilla  (40%)",  float(fit.get("compatibilidad_plantilla", 0))),
        ("Compatib. entrenador  (25%)", float(fit.get("compatibilidad_entrenador", 0))),
        ("Rendimiento en rol  (20%)",   float(prof.get("primary_score") or 50)),
        ("Potencial / edad  (15%)",     float(pot_s)),
    ]
    bars = hbar_chart(comps, label_w="190px")

    # Title with score
    fit_col = score_color(float(fit_10) * 10 if fit_10 else 0, hi=7, lo=5)
    title_html = (f'<div style="font-size:10pt;font-weight:bold;color:{fit_col};margin-bottom:5px;">'
                  f'FIT RAYO &mdash; {fit_10} / 10</div>')

    # Breakdown table
    bd_rows = [
        ("Compatibilidad plantilla", "40%", str(int(fit.get("compatibilidad_plantilla",0))),
         f"{fit.get('compatibilidad_plantilla',0)*0.40:.1f}"),
        ("Compatibilidad entrenador", "25%", str(int(fit.get("compatibilidad_entrenador",0))),
         f"{fit.get('compatibilidad_entrenador',0)*0.25:.1f}"),
        ("Rendimiento en rol", "20%", str(int(prof.get("primary_score") or 50)),
         f"{(prof.get('primary_score') or 50)*0.20:.1f}"),
        ("Potencial / edad", "15%", str(pot_s), f"{pot_s*0.15:.1f}"),
    ]
    tbl = html_table(
        ["Componente","Peso","Score","Contribucion"],
        bd_rows,
        total_row=("TOTAL FIT RAYO", "100%", "—", f"{fit.get('global_fit',0):.1f}"),
    )
    note = ('<div class="formula-note">Formula: Fit = (Plantilla*0.40) + (Entrenador*0.25) +'
            ' (Rol*0.20) + (Potencial*0.15). Potencial: muy alto=95, alto=80, estable=65,'
            ' en meseta=50, veterania=35.</div>')

    return section_header("Fit Rayo — Encaje con el club") + title_html + bars + '<div style="margin-top:6px;"></div>' + tbl + note


def _radar_section(prof, pool_avg, crow, pool, career_row) -> str:
    # Radar chart
    role_labels_map = {k: ROLE_LABELS.get(k, k) for k in prof.get("role_scores", {})}
    labeled_scores  = {ROLE_LABELS.get(k, k): v for k, v in prof.get("role_scores", {}).items()}
    radar_b64 = radar_chart_b64(labeled_scores, {ROLE_LABELS.get(k,k): v for k,v in pool_avg.items()})

    # Roles table
    rs_rows = [(ROLE_LABELS.get(k,k), str(int(v)))
               for k,v in list(prof.get("role_scores",{}).items())[:7]]
    rs_tbl = html_table(["Rol","Score"], rs_rows)

    # Totals table
    mins_tot = float(career_row.get("minutes") or 0) or 1
    tot_rows = []
    for col, lab in CAREER_TOTALS:
        if col in career_row.index and pd.notna(career_row.get(col)):
            v   = float(career_row[col])
            p90 = "" if col == "minutes" else f"{v/mins_tot*90:.2f}"
            tot_rows.append((lab, str(int(v)), p90))
    tot_tbl = html_table(["Metrica","Total","/90'"], tot_rows)

    radar_img_html = ""
    if radar_b64:
        radar_img_html = f'<img src="data:image/png;base64,{radar_b64}" style="width:100%;max-width:260px;display:block;margin-bottom:5px;" alt="radar">'

    return (
        section_header("Perfil de rol — radar de habilidades") +
        f'<div class="two-col">'
        f'<div class="col-l">{radar_img_html}{rs_tbl}</div>'
        f'<div class="col-r">'
        f'<div class="sub-title">Totales de carrera</div>'
        f'{tot_tbl}'
        f'</div>'
        f'</div>'
    )


def _top_pct_section(crow, pool, top_n=12) -> str:
    all_m = []
    for grp, metrics in METRIC_GROUPS.items():
        for m in metrics:
            pct = _pct_rank(crow, pool, m)
            if pct is not None:
                all_m.append((METRIC_LABELS.get(m, m), pct))
    if not all_m:
        return ""
    all_m.sort(key=lambda x: -x[1])
    top = all_m[:top_n]
    bars = hbar_chart(top, label_w="200px")
    return section_header(f"Top {top_n} percentiles vs posicion") + bars


def _group_section(crow, pool) -> str:
    html = section_header("Percentiles por grupo de metricas")
    grp_items = list(METRIC_GROUPS.items())
    for i in range(0, len(grp_items), 2):
        html += '<div class="grid2">'
        for grp, metrics in grp_items[i:i+2]:
            rows = []
            for m in metrics:
                pct = _pct_rank(crow, pool, m)
                v90 = float(crow[m]) if m in crow.index and pd.notna(crow.get(m)) else None
                if pct is not None:
                    note = f"{v90:.2f}/90" if v90 is not None else ""
                    rows.append((METRIC_LABELS.get(m,m), pct, note))
            if rows:
                bars = hbar_chart(rows, label_w="130px")
                html += f'<div class="grid2-cell"><div class="group-title">{grp}</div>{bars}</div>'
            else:
                html += '<div class="grid2-cell"></div>'
        html += '</div>'
    return html


def _seasons_section(enr, cname) -> str:
    prows = enr[enr["name"] == cname].copy()
    order = {"2025-2026":6,"2025":5,"2024-2025":4,"2023-2024":3,"2022-2023":2,"2021-2022":1}
    prows["_o"] = prows["season"].map(order).fillna(0)
    prows = prows.sort_values("_o", ascending=False)
    cols  = [(c, lbl) for c, lbl in SEASON_COLS if c in prows.columns]
    headers = [lbl for _, lbl in cols]
    rows = []
    for _, rw in prows.iterrows():
        row = []
        for c, _ in cols:
            v = rw.get(c)
            if c == "minutes" and pd.notna(v): v = int(v)
            elif isinstance(v, float) and pd.notna(v) and c != "season": v = int(v)
            row.append("" if pd.isna(v) else str(v))
        rows.append(row)
    return section_header("Estadisticas por temporada (OPTA)") + html_table(headers, rows)


def _footer(prof) -> str:
    d = date.today().strftime("%d %b %Y").lstrip("0")
    temps = prof.get("seasons_played","?")
    return (f'<div class="footer">'
            f'Rayo Vallecano &middot; Direccion Deportiva &middot; '
            f'Generado {d} &middot; '
            f'Datos OPTA ({temps} temp.) + Transfermarkt &middot; Confidencial'
            f'</div>')


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

    # ── Foto ──────────────────────────────────────────────────────────────
    foto_b64_str = None
    purl = mv.get("photo_url") or (
        f"https://img.a.transfermarkt.technology/portrait/big/{mv['tm_id']}.jpg"
        if mv.get("tm_id") else None)
    if purl:
        try:
            import requests
            r = requests.get(purl, timeout=4, headers={"User-Agent":"RayoScoutingTool/1.0"})
            if r.status_code == 200 and r.content:
                foto_b64_str = photo_b64(r.content)
        except Exception:
            foto_b64_str = None

    # ── Scores ────────────────────────────────────────────────────────────
    val_s  = f"{mv['value_eur']/1e6:.1f}M EUR" if mv.get("value_eur") else "n/d"
    con_s  = str(mv.get("contract_until",""))[:10] or "n/d"
    age_v  = int(float(mv.get("age") or 0))
    mins_v = float(crow.get("minutes") or 0)
    league_s = str(crow.get("league","")).replace("_"," ")
    pos_s    = str(mv.get("position") or pos or "")
    sal_s    = _est_salary(mv.get("value_eur",0), league_s, mins_v, age_v, pos_s)
    mins_s   = f"{int(mins_v):,}".replace(",",".")

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

    # ── Pool avg para radar ────────────────────────────────────────────────
    try:
        pool_profiles = [profile_player_row(r) for _, r in add_role_percentiles(pool).iterrows()
                         if r.get("name") != cname]
        pool_role_avg: dict = {}
        for rp in pool_profiles:
            for k, v in (rp.get("role_scores") or {}).items():
                pool_role_avg.setdefault(k, []).append(float(v))
        pool_role_avg = {k: sum(vs)/len(vs) for k, vs in pool_role_avg.items()}
    except Exception:
        pool_role_avg = {}

    # ── Construir HTML ─────────────────────────────────────────────────────
    body = ""
    body += _topbar()
    body += _hero_html(cname, crow, mv, prof, fit_v, fit_10, sal_s, foto_b64_str)
    body += _kpi_strip(fit_s, fit_v, val_s, sal_s, con_s, mins_s)
    body += _sw_html(prof.get("strengths",[]), prof.get("weaknesses",[]))

    if fit:
        body += _fit_section(fit, prof, fit_10)

    body += _radar_section(prof, pool_role_avg, crow, pool, crow)
    body += _top_pct_section(crow, pool, top_n=12)
    body += _group_section(crow, pool)
    body += _seasons_section(enr, cname)
    body += _footer(prof)

    html = build_html_doc(body, title=f"Informe {cname}")
    pdf_bytes = html_to_pdf(html)

    fname = f"informe_{_n(cname).replace(' ', '_')}.pdf"
    return fname, pdf_bytes
