# -*- coding: utf-8 -*-
"""Pestaña de Finanzas — salarios, presupuesto, riesgo de cláusulas y simulador."""
from __future__ import annotations
import sys, traceback
from pathlib import Path
import dash
from dash import html, dcc, callback, Input, Output, State, ALL, ctx, no_update
import json
import dash_bootstrap_components as dbc
from dash import dash_table
import pandas as pd
import yaml
import plotly.graph_objects as go

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.utils.config import settings
from dashboard.components.criteria_block import criteria_accordion  # noqa: E402
from dashboard.components.chart_theme import apply_theme, RAYO_RED, RAYO_DARK, C_POSITIVE, C_WARNING, GRAPH_CONFIG_SIMPLE  # noqa: E402

dash.register_page(__name__, path="/finanzas", name="Finanzas")

ROOT         = Path(__file__).resolve().parents[2]
FINANCES_CFG = ROOT / "config" / "finances.yaml"

# ── Helpers ───────────────────────────────────────────────────────────────────
def _load_finances():
    with open(FINANCES_CFG, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

PROC_DIR = Path(settings()["paths"]["data_processed"])
FIN_CUSTOM = PROC_DIR / "finances_custom.json"


def _load_custom():
    if FIN_CUSTOM.exists():
        try:
            return json.load(open(FIN_CUSTOM, encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_custom(items):
    FIN_CUSTOM.parent.mkdir(parents=True, exist_ok=True)
    json.dump(items, open(FIN_CUSTOM, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def _base_totals(fin):
    rev = fin["revenues"]; exp = fin["expenses"]
    total_rev = sum(v for v in rev.values() if isinstance(v, (int, float)))
    total_exp = (exp["wage_bill_gross_eur"] + exp["bonus_bill_eur"] +
                 exp["amortizations_eur"] + exp["operating_costs_eur"])
    return total_rev, total_exp

def _fmt(v, unit="€"):
    if v is None: return "—"
    try: v = float(v)
    except: return "—"
    if v >= 1_000_000: return f"{v/1_000_000:.1f}M{unit}"
    if v >= 1_000:     return f"{v/1_000:.0f}K{unit}"
    return f"{v:.0f}{unit}"

def _contract_dot(end_date):
    year = int(str(end_date)[:4])
    c = "#E30613" if year <= 2026 else ("#F59E0B" if year <= 2027 else "#10B981")
    return html.Span(style={"width":"8px","height":"8px","borderRadius":"50%",
                             "background":c,"display":"inline-block","marginRight":"6px"})

def _clause_badge(amount, confirmed):
    if not amount: return html.Span("—", style={"color":"#9CA3AF","fontSize":"12px"})
    label = _fmt(amount)
    if confirmed:
        return html.Span(f"{label} ✓", style={"fontSize":"10px","fontWeight":"600",
            "padding":"2px 8px","borderRadius":"99px","background":"#DCFCE7","color":"#166534"})
    return html.Span(f"{label} ~", style={"fontSize":"10px","fontWeight":"600",
        "padding":"2px 8px","borderRadius":"99px","background":"#F3F4F6","color":"#6B7280"})

CELL = {"fontSize":"12px","padding":"8px 10px","borderBottom":"1px solid #F3F4F6",
        "color":"#374151","verticalAlign":"middle"}
HEAD = {"fontSize":"10px","fontWeight":"600","color":"#9CA3AF","textTransform":"uppercase",
        "letterSpacing":".06em","padding":"0 10px 8px","borderBottom":"2px solid #E30613"}

MV_MAP = {
    "Andrei Rațiu":18e6,"Jorge de Frutos":12e6,"Pep Chavarría":10e6,"Ilias Akhomach":12e6,
    "Augusto Batalla":6.5e6,"Nobel Mendy":6e6,"Isi Palazón":3e6,"Álvaro García":1.8e6,
    "Luiz Felipe":5e6,"Florian Lejeune":2e6,"Pedro Díaz":3e6,"Randy Nteka":1.2e6,
    "Pathé Ciss":2e6,"Unai López":2.5e6,"Fran Pérez":2.2e6,"Alemão":3.5e6,
    "Sergio Camello":2e6,"Abdul Mumin":4e6,"Jozhua Vertrouwd":1.9e6,"Samu Becerra":1.5e6,
    "Dani Cárdenas":1.5e6,"Iván Balliu":0.8e6,"Alfonso Espino":0.8e6,"Óscar Trejo":0.3e6,
    "Carlos Martín":1.1e6,"Óscar Valentín":2.2e6,"Gerard Gumbau":1.5e6,
}

# ── Modelo de riesgo multifactorial ──────────────────────────────────────────
def _clause_risk_score(p, news):
    score, reasons = 0, []
    name = p["name"]

    # 1. Contrato restante
    year_end   = int(str(p.get("contract_end","2030"))[:4])
    years_left = year_end - 2026
    if years_left == 1:
        score += 25; reasons.append(f"🔴 Solo 1 año de contrato (hasta {year_end})")
    elif years_left == 2:
        score += 15; reasons.append(f"🟡 2 años de contrato (hasta {year_end})")
    elif years_left <= 4:
        score += 8;  reasons.append(f"🟢 {years_left} años de contrato")
    else:
        score += 2;  reasons.append(f"🟢 Contrato largo ({years_left} años)")

    # 2. Edad
    age = p.get("age", 28)
    if isinstance(age, str):
        try: age = int(age)
        except: age = 28
    if 22 <= age <= 26:
        score += 25; reasons.append(f"🔴 Edad premium ({age} años) — máximo interés")
    elif 27 <= age <= 29:
        score += 15; reasons.append(f"🟡 Madurez ({age} años) — buen atractivo")
    elif age <= 21:
        score += 20; reasons.append(f"🔴 Muy joven ({age} años) — alto potencial")
    else:
        score += 5;  reasons.append(f"🟢 Edad ({age} años)")

    # 3. Ratio cláusula / valor TM
    clause = p.get("release_clause") or 0
    mv = MV_MAP.get(name, (p.get("salary_annual",500000) or 500000) * 8)
    if clause > 0 and mv > 0:
        r = clause / mv
        if r < 1.5:
            score += 20; reasons.append(f"🔴 Cláusula {_fmt(clause)} < 1.5× TM {_fmt(mv)}")
        elif r < 2.5:
            score += 12; reasons.append(f"🟡 Cláusula {_fmt(clause)} = {r:.1f}× TM")
        elif r < 4:
            score += 6;  reasons.append(f"🟢 Cláusula {_fmt(clause)} = {r:.1f}× TM")
        else:
            score += 2;  reasons.append(f"🟢 Cláusula {_fmt(clause)} = {r:.1f}× TM — disuasoria")

    # 4. Noticias / interés real
    news_map = {n["player"]: n for n in (news or [])}
    ni = news_map.get(name)
    if ni:
        lvl   = ni.get("interest_level","")
        clubs = ni.get("clubs",[])
        note  = ni.get("note","")
        if lvl == "confirmed":
            score += 30; reasons.append(f"🔴 INTERÉS CONFIRMADO: {', '.join(clubs)} · {note}")
        elif lvl == "sounded":
            score += 18; reasons.append(f"🟡 Sondeado: {', '.join(clubs)} · {note}")

    # 5. Posición de alto valor
    if p.get("position") in ("RB","LB") and mv >= 8e6:
        score += 5; reasons.append("🟡 Lateral de valor — alta demanda europea")
    elif p.get("position") in ("RW","LW","ST") and mv >= 8e6:
        score += 5; reasons.append("🟡 Atacante de valor — alta demanda")

    score = min(score, 100)
    if score >= 65:   nivel = "MUY ALTO"
    elif score >= 45: nivel = "ALTO"
    elif score >= 25: nivel = "MEDIO"
    else:             nivel = "BAJO"
    return score, nivel, reasons

def _risk_card(p, news):
    score, nivel, reasons = _clause_risk_score(p, news)
    color_map = {
        "MUY ALTO": ("#FFF1F2","#E30613","#9F1239"),
        "ALTO":     ("#FFFBEB","#F59E0B","#92400E"),
        "MEDIO":    ("#EFF6FF","#3B82F6","#1D4ED8"),
        "BAJO":     ("#F0FDF4","#22C55E","#166534"),
    }
    bg, bar_color, text_color = color_map.get(nivel, ("#F9FAFB","#9CA3AF","#374151"))
    name     = p["name"]
    initials = "".join(w[0].upper() for w in name.split()[:2])
    clause   = p.get("release_clause")
    end_yr   = str(p.get("contract_end","?"))[:4]

    return html.Div([
        html.Div([
            html.Div(initials, style={"width":"32px","height":"32px","borderRadius":"50%",
                "background":"#1A1A2E","color":"#fff","display":"flex","alignItems":"center",
                "justifyContent":"center","fontSize":"10px","fontWeight":"600","flexShrink":"0"}),
            html.Div([
                html.Strong(name, style={"fontSize":"13px","color":"#1A1A2E","display":"block"}),
                html.Span(f"{p.get('position','?')}  ·  contrato hasta {end_yr}",
                          style={"fontSize":"10px","color":"#6B7280"}),
            ], style={"flex":"1","marginLeft":"8px"}),
            html.Span(nivel, style={"fontSize":"9px","fontWeight":"700","padding":"3px 8px",
                "borderRadius":"99px","background":bg,"color":text_color,"flexShrink":"0"}),
        ], style={"display":"flex","alignItems":"center","marginBottom":"8px"}),
        html.Div([
            html.Div(style={"height":"6px","background":"#F3F4F6","borderRadius":"99px","overflow":"hidden"},
                     children=html.Div(style={"height":"100%","width":f"{score}%",
                         "background":bar_color,"borderRadius":"99px"})),
            html.Span(f"Score: {score}/100", style={"fontSize":"10px","color":"#9CA3AF","marginTop":"3px","display":"block"}),
        ], style={"marginBottom":"8px"}),
        html.Div([
            html.Span("Cláusula: ", style={"fontSize":"11px","color":"#6B7280"}),
            _clause_badge(clause, p.get("clause_confirmed",False)),
            html.Span(f"  Salario: {_fmt(p.get('salary_annual'))}/año",
                      style={"fontSize":"11px","color":"#6B7280","marginLeft":"8px"}),
        ], style={"marginBottom":"8px"}),
        html.Div([html.P(r, style={"fontSize":"10px","color":"#374151","margin":"1px 0","lineHeight":"1.5"})
                  for r in reasons]),
    ], style={"background":"#fff",
              "border":f"1px solid {'#FECACA' if nivel=='MUY ALTO' else '#E5E7EB'}",
              "borderRadius":"10px","padding":"12px 14px","boxShadow":"0 1px 3px rgba(0,0,0,.05)"})

# ── Estimadores para el simulador ─────────────────────────────────────────────
def _estimate_salary(mv, age=None):
    if not mv or mv <= 0: return 500_000
    ratio = 0.11 if (age or 26) <= 28 else 0.13
    return round(mv * ratio / 50_000) * 50_000

def _estimate_clause(mv, age=None):
    if not mv or mv <= 0: return 3_000_000
    mult = 3.5 if (age or 26) < 25 else (3.0 if (age or 26) < 29 else 2.0)
    return round(mv * mult / 500_000) * 500_000

RAYO_PLAYERS = {"Álvaro García","Luiz Felipe","Florian Lejeune","Isi Palazón","Augusto Batalla",
    "Pep Chavarría","Óscar Valentín","Jorge de Frutos","Unai López","Fran Pérez",
    "Alemão","Pedro Díaz","Randy Nteka","Andrei Rațiu","Pathé Ciss","Sergio Camello",
    "Gerard Gumbau","Iván Balliu","Alfonso Espino","Óscar Trejo","Ilias Akhomach",
    "Abdul Mumin","Carlos Martín","Dani Cárdenas","Jozhua Vertrouwd","Nobel Mendy","Samu Becerra"}

# Ligas del scope Rayo para el simulador (label legible -> valor en el master)
SIM_LEAGUES = [
    {"label": "LaLiga (España)", "value": "Spain_Primera_Division"},
    {"label": "Segunda (España)", "value": "Spain_Segunda_Division"},
    {"label": "Premier League", "value": "England_Premier_League"},
    {"label": "Championship", "value": "England_Championship"},
    {"label": "Serie A (Italia)", "value": "Italy_Serie_A"},
    {"label": "Bundesliga", "value": "Germany_Bundesliga"},
    {"label": "2. Bundesliga", "value": "Germany_2_Bundesliga"},
    {"label": "Ligue 1", "value": "France_Ligue_1"},
    {"label": "Eredivisie", "value": "Netherlands_Eredivisie"},
    {"label": "Primeira (Portugal)", "value": "Portugal_Primeira_Liga"},
    {"label": "Bélgica", "value": "Belgium_First_Division_A"},
    {"label": "Süper Lig (Turquía)", "value": "Türkiye_Süper_Lig"},
    {"label": "Argentina", "value": "Argentina_Liga_Profesional"},
    {"label": "Brasil", "value": "Brazil_Serie_A"},
    {"label": "Liga MX (México)", "value": "Mexico_Liga_MX"},
    {"label": "MLS (EE.UU.)", "value": "USA_MLS"},
]


_ENR_CACHE = {}


def _career_role(name):
    """Tipo de jugador (rol) calculado desde TODO su histórico de partidos."""
    try:
        from pathlib import Path as _P
        s_ = settings()
        ep = _P(s_["paths"]["data_processed"]) / "player_seasons_enriched.parquet"
        if "df" not in _ENR_CACHE:
            _ENR_CACHE["df"] = pd.read_parquet(ep) if ep.exists() else None
        enr = _ENR_CACHE["df"]
        if enr is None:
            return None
        from src.profiling.player_profile import profile_single_player
        p = profile_single_player(enr, name)
        if not p or not p.get("primary_role"):
            return None
        return p
    except Exception:
        return None


def _load_master_opts(leagues=None):
    """Opciones del simulador filtradas por liga (por defecto scope España)."""
    try:
        s = settings()
        master_path = Path(s["paths"]["data_processed"]) / "master_players.parquet"
        if not master_path.exists():
            return []
        import pyarrow.parquet as pq
        available = pq.read_schema(master_path).names
        want = ["name", "position_primary", "team", "league", "minutes", "goals", "assists"]
        cols = [c for c in want if c in available]
        df = pd.read_parquet(master_path, columns=cols)
    except Exception:
        return []
    if leagues:
        df = df[df["league"].astype(str).isin(leagues)]
    if "name" in df.columns:
        df = df[~df["name"].astype(str).isin(RAYO_PLAYERS)]
    # ordenar por minutos desc para que aparezcan primero los relevantes
    if "minutes" in df.columns:
        df = df.sort_values("minutes", ascending=False)
    df = df.drop_duplicates(subset=["name"]) if "name" in df.columns else df
    opts = []
    for _, row in df.iterrows():
        name = str(row.get("name", ""))
        if not name or name == "nan":
            continue
        team = str(row.get("team", ""))
        league = str(row.get("league", "")).replace("_", " ")
        opts.append({"label": f"{name}  ·  {team}  ({league})", "value": name})
    return opts[:3000]

# ── Tab 1: Salarios ───────────────────────────────────────────────────────────
def tab_salarios(fin):
    players = fin["player_salaries"]
    scl = fin["squad_cost_limit"]
    total = sum(p["salary_annual"] for p in players)
    bonus = sum(p["bonus_annual"] for p in players)
    pct   = total / scl["limit_eur"] * 100

    rows = []
    for i, p in enumerate(sorted(players, key=lambda x: -x["salary_annual"])):
        name = p["name"]
        initials = "".join(w[0].upper() for w in name.split()[:2])
        bg = "#FFF5F5" if int(str(p["contract_end"])[:4]) <= 2026 else ("#fff" if i%2==0 else "#FAFAFA")
        rows.append(html.Tr([
            html.Td(html.Div([
                html.Div(initials, style={"width":"28px","height":"28px","borderRadius":"50%","background":"#1A1A2E",
                    "color":"#fff","display":"inline-flex","alignItems":"center","justifyContent":"center",
                    "fontSize":"9px","fontWeight":"600","flexShrink":"0","marginRight":"8px"}),
                html.Strong(name, style={"fontSize":"12px","color":"#1A1A2E"}),
            ], style={"display":"flex","alignItems":"center"}), style=CELL),
            html.Td(html.Span(p["position"], style={"fontSize":"9px","fontWeight":"700","padding":"1px 6px",
                "borderRadius":"99px","background":"#F3F4F6","color":"#374151"}), style=CELL),
            html.Td(f"{_fmt(p['salary_weekly'])}/sem", style={**CELL,"fontWeight":"600","color":"#1A1A2E"}),
            html.Td(_fmt(p["salary_annual"]),           style={**CELL,"fontWeight":"600"}),
            html.Td(dcc.Input(
                id={"type":"sal-edit","index":p["name"]},
                type="number", min=0, step=0.05, debounce=True,
                placeholder=str(round(p["salary_annual"]/1e6,2)),
                style={"width":"70px","padding":"3px 6px","border":"1px solid #E5E7EB",
                       "borderRadius":"5px","fontSize":"11px","textAlign":"right"},
            ), style={**CELL,"background":"#FFFBEB"}),
            html.Td(f'+{_fmt(p["bonus_annual"])}',      style={**CELL,"color":"#6B7280"}),
            html.Td([_contract_dot(p["contract_end"]),
                     html.Span(str(p["contract_end"])[:4], style={"fontSize":"12px"})], style=CELL),
            html.Td(_clause_badge(p.get("release_clause"), p.get("clause_confirmed",False)), style=CELL),
        ], style={"background":bg}))

    return html.Div([
        dcc.Store(id="sal-overrides", data={}),
        dbc.Row([
            dbc.Col(html.Div([html.P("Masa salarial base",className="kpi-label"),
                html.P(_fmt(total),className="kpi-value"),html.P("sin bonus",className="kpi-sub")],className="kpi-modern"),md=3),
            dbc.Col(html.Div([html.P("Total con bonus",className="kpi-label"),
                html.P(_fmt(total+bonus),className="kpi-value"),html.P("bonus conocidos",className="kpi-sub")],className="kpi-modern"),md=3),
            dbc.Col(html.Div([html.P("Límite LaLiga",className="kpi-label"),
                html.P(_fmt(scl["limit_eur"]),className="kpi-value"),html.P(f"#{scl['laliga_ranking']} LaLiga",className="kpi-sub")],className="kpi-modern"),md=3),
            dbc.Col(html.Div([html.P("Margen disponible",className="kpi-label"),
                html.P(_fmt(scl["limit_eur"]-total),className="kpi-value"),html.P(f"{100-pct:.0f}% libre",className="kpi-sub")],className="kpi-modern"),md=3),
        ], className="g-3 mb-3"),
        html.Div(id="sal-live-kpis"),
        html.Div([
            html.Div([html.Span("Uso del límite salarial",style={"fontSize":"11px","fontWeight":"600","color":"#374151"}),
                      html.Span(f" {pct:.1f}%",style={"fontSize":"11px","color":"#6B7280","marginLeft":"6px"})],style={"marginBottom":"6px"}),
            html.Div(style={"height":"12px","background":"#F3F4F6","borderRadius":"99px","overflow":"hidden"},
                children=html.Div(style={"height":"100%","width":f"{min(pct,100):.1f}%",
                    "background":"#10B981" if pct<75 else ("#F59E0B" if pct<90 else "#E30613"),
                    "borderRadius":"99px"})),
        ], style={"background":"#fff","border":"1px solid #E5E7EB","borderRadius":"10px","padding":"14px 18px","marginBottom":"14px"}),
        html.Div([
            html.P("Contratos y salarios · SalaryLeaks (mar-2026) · Capology",
                   style={"fontSize":"10px","fontWeight":"600","color":"#9CA3AF","textTransform":"uppercase","letterSpacing":".06em","marginBottom":"10px"}),
            html.Div([
                html.Span("✓ Cláusula confirmada",style={"fontSize":"10px","color":"#166534","background":"#DCFCE7","padding":"2px 8px","borderRadius":"99px","marginRight":"10px"}),
                html.Span("~ Cláusula estimada",  style={"fontSize":"10px","color":"#6B7280","background":"#F3F4F6","padding":"2px 8px","borderRadius":"99px"}),
            ], style={"marginBottom":"12px"}),
            html.Div(html.Table([
                html.Thead(html.Tr([html.Th("Jugador",style=HEAD),html.Th("Pos.",style=HEAD),
                    html.Th("Semanal",style=HEAD),html.Th("Anual",style=HEAD),
                    html.Th("Editar (M€/año)",style={**HEAD,"color":"#E30613"}),
                    html.Th("Bonus",style=HEAD),
                    html.Th("Contrato",style=HEAD),html.Th("Cláusula",style=HEAD)])),
                html.Tbody(rows),
            ], style={"width":"100%","borderCollapse":"collapse"}), style={"overflowX":"auto"}),
        ], style={"background":"#fff","border":"1px solid #E5E7EB","borderRadius":"10px","padding":"16px 18px"}),
    ])

# ── Tab 2: Presupuesto ────────────────────────────────────────────────────────
def tab_presupuesto(fin):
    rev = fin["revenues"]
    exp = fin["expenses"]
    total_rev = sum(v for v in rev.values() if isinstance(v,(int,float)))
    total_exp = (exp["wage_bill_gross_eur"] + exp["bonus_bill_eur"] +
                 exp["amortizations_eur"]   + exp["operating_costs_eur"])
    balance = total_rev - total_exp

    def rev_row(label, value, icon, note=""):
        pct = value/total_rev*100
        return html.Div([
            html.Div([html.I(className=f"ti {icon}",style={"fontSize":"15px","color":"#E30613","marginRight":"8px","width":"20px"}),
                html.Span(label,style={"fontSize":"13px","color":"#374151","flex":"1"}),
                html.Span(note,style={"fontSize":"11px","color":"#9CA3AF","marginRight":"12px"}),
                html.Span(_fmt(value),style={"fontSize":"13px","fontWeight":"700","color":"#1A1A2E","minWidth":"60px","textAlign":"right"}),
            ], style={"display":"flex","alignItems":"center","marginBottom":"6px"}),
            html.Div(style={"height":"5px","background":"#F3F4F6","borderRadius":"99px","overflow":"hidden","marginBottom":"12px"},
                children=html.Div(style={"height":"100%","width":f"{pct:.1f}%","background":"#E30613","borderRadius":"99px"})),
        ])
    def exp_row(label, value, icon):
        pct = value/total_exp*100
        return html.Div([
            html.Div([html.I(className=f"ti {icon}",style={"fontSize":"15px","color":"#374151","marginRight":"8px","width":"20px"}),
                html.Span(label,style={"fontSize":"13px","color":"#374151","flex":"1"}),
                html.Span(_fmt(value),style={"fontSize":"13px","fontWeight":"700","color":"#1A1A2E","minWidth":"60px","textAlign":"right"}),
            ], style={"display":"flex","alignItems":"center","marginBottom":"6px"}),
            html.Div(style={"height":"5px","background":"#F3F4F6","borderRadius":"99px","overflow":"hidden","marginBottom":"12px"},
                children=html.Div(style={"height":"100%","width":f"{pct:.1f}%","background":"#374151","borderRadius":"99px"})),
        ])

    return html.Div([
        dbc.Row([
            dbc.Col(html.Div([html.P("Ingresos estimados",className="kpi-label"),html.P(_fmt(total_rev),className="kpi-value"),html.P("temporada 2025/26",className="kpi-sub")],className="kpi-modern"),md=3),
            dbc.Col(html.Div([html.P("Gastos estimados",className="kpi-label"),html.P(_fmt(total_exp),className="kpi-value"),html.P("estructura + plantilla",className="kpi-sub")],className="kpi-modern"),md=3),
            dbc.Col(html.Div([html.P("Balance operativo",className="kpi-label"),html.P(_fmt(abs(balance)),className="kpi-value"),html.P("superávit" if balance>=0 else "déficit",className="kpi-sub")],className=f"kpi-modern {'danger' if balance<0 else ''}"),md=3),
            dbc.Col(html.Div([html.P("Conference League",className="kpi-label"),html.P(_fmt(rev["conference_league_eur"]),className="kpi-value"),html.P("final 2024-25 (Crystal Palace 1-0)",className="kpi-sub")],className="kpi-modern"),md=3),
        ], className="g-3 mb-3"),
        dbc.Row([
            dbc.Col(html.Div([
                html.P("Ingresos",style={"fontSize":"10px","fontWeight":"600","color":"#9CA3AF","textTransform":"uppercase","letterSpacing":".06em","marginBottom":"16px"}),
                rev_row("Derechos TV LaLiga",    rev["tv_laliga_eur"],           "ti-tv",             "est. 2025-26"),
                rev_row("Conference League UEFA",rev["conference_league_eur"],   "ti-trophy",         "final 24-25"),
                rev_row("Taquilla / Matchday",   rev["matchday_eur"],            "ti-ticket",         "Vallecas ~14.700"),
                rev_row("Comercial / Patrocinio",rev["commercial_sponsorship_eur"],"ti-building-store",""),
                rev_row("Otros",                 rev["other_eur"],               "ti-dots",           ""),
                html.Div(style={"borderTop":"1px solid #E5E7EB","paddingTop":"10px","marginTop":"4px"}),
                html.Div([html.Span("TOTAL",style={"fontSize":"11px","fontWeight":"700","color":"#374151","flex":"1"}),
                          html.Span(_fmt(total_rev),style={"fontSize":"15px","fontWeight":"700","color":"#10B981"})],
                         style={"display":"flex","alignItems":"center"}),
            ], style={"background":"#fff","border":"1px solid #E5E7EB","borderRadius":"10px","padding":"16px 18px"}), md=6),
            dbc.Col(html.Div([
                html.P("Gastos",style={"fontSize":"10px","fontWeight":"600","color":"#9CA3AF","textTransform":"uppercase","letterSpacing":".06em","marginBottom":"16px"}),
                exp_row("Masa salarial (base+bonus)",  exp["wage_bill_gross_eur"]+exp["bonus_bill_eur"],"ti-users"),
                exp_row("Amortizaciones traspasos",    exp["amortizations_eur"],  "ti-chart-line-down"),
                exp_row("Costes operativos",           exp["operating_costs_eur"],"ti-building"),
                exp_row("Traspasos netos",             exp["transfers_net_eur"],  "ti-arrows-exchange"),
                html.Div(style={"borderTop":"1px solid #E5E7EB","paddingTop":"10px","marginTop":"4px"}),
                html.Div([html.Span("TOTAL",style={"fontSize":"11px","fontWeight":"700","color":"#374151","flex":"1"}),
                          html.Span(_fmt(total_exp),style={"fontSize":"15px","fontWeight":"700","color":"#E30613"})],
                         style={"display":"flex","alignItems":"center"}),
            ], style={"background":"#fff","border":"1px solid #E5E7EB","borderRadius":"10px","padding":"16px 18px"}), md=6),
        ], className="g-3"),

        # ── Editor de partidas del usuario (ingresos/gastos) ─────────────────
        html.Div([
            html.P("Ajustes del usuario · añade ingresos o gastos con su motivo",
                   style={"fontSize": "13px", "fontWeight": "700", "color": "#1A1A2E", "marginBottom": "4px"}),
            html.P("Cada partida recalcula el balance al instante y se guarda.",
                   style={"fontSize": "11px", "color": "#6B7280", "marginBottom": "12px"}),
            dbc.Row([
                dbc.Col([html.Span("Motivo / concepto", style={"fontSize": "10px", "color": "#6B7280"}),
                    dcc.Input(id="bud-concept", type="text", placeholder="Ej: Venta de Rațiu",
                              style={"width": "100%", "padding": "7px 10px", "border": "1px solid #E5E7EB",
                                     "borderRadius": "7px", "fontSize": "13px"})], md=5),
                dbc.Col([html.Span("Tipo", style={"fontSize": "10px", "color": "#6B7280"}),
                    dcc.Dropdown(id="bud-type", clearable=False, value="ingreso",
                                 options=[{"label": "Ingreso", "value": "ingreso"},
                                          {"label": "Gasto", "value": "gasto"}])], md=3),
                dbc.Col([html.Span("Importe (M€)", style={"fontSize": "10px", "color": "#6B7280"}),
                    dcc.Input(id="bud-amount", type="number", min=0, step=0.5, placeholder="0.0",
                              style={"width": "100%", "padding": "7px 10px", "border": "1px solid #E5E7EB",
                                     "borderRadius": "7px", "fontSize": "13px"})], md=2),
                dbc.Col(html.Button("Añadir", id="bud-add", n_clicks=0,
                    style={"background": "#E30613", "color": "#fff", "border": "none", "borderRadius": "7px",
                           "padding": "8px 16px", "fontSize": "13px", "fontWeight": "600", "cursor": "pointer",
                           "width": "100%", "marginTop": "14px"}), md=2),
            ], className="g-2"),
            dcc.Store(id="bud-refresh", data=0),
            html.Div(id="bud-list", style={"marginTop": "14px"}),
            html.Div(id="bud-balance", style={"marginTop": "12px"}),
        ], style={"background": "#fff", "border": "1px solid #E5E7EB", "borderRadius": "10px",
                  "padding": "16px 18px", "marginTop": "16px"}),
    ])

# ── Tab 3: Riesgo de cláusulas ────────────────────────────────────────────────
def tab_riesgo(fin):
    players = fin["player_salaries"]
    news    = fin.get("transfer_news", [])
    activos = [p for p in players if int(str(p.get("contract_end","2030"))[:4]) > 2026]
    libres  = [p for p in players if int(str(p.get("contract_end","2030"))[:4]) <= 2026]

    muy_alto = sum(1 for p in activos if _clause_risk_score(p,news)[1] == "MUY ALTO")
    alto     = sum(1 for p in activos if _clause_risk_score(p,news)[1] == "ALTO")

    inp_s = {"width":"80px","padding":"4px 7px","border":"1px solid #E5E7EB","borderRadius":"6px",
             "fontSize":"12px","textAlign":"right"}

    return html.Div([
        # Store para overrides de cláusulas (sesión)
        dcc.Store(id="clause-overrides", data={}),

        dbc.Row([
            dbc.Col(html.Div([html.P("En riesgo MUY ALTO + ALTO",className="kpi-label"),html.P(str(muy_alto+alto),className="kpi-value"),html.P("jugadores",className="kpi-sub")],className="kpi-modern danger"),md=3),
            dbc.Col(html.Div([html.P("Salidas libres (jun-2026)",className="kpi-label"),html.P(str(len(libres)),className="kpi-value"),html.P("contratos expiran",className="kpi-sub")],className="kpi-modern danger"),md=3),
            dbc.Col(html.Div([html.P("Interés confirmado",className="kpi-label"),html.P(str(sum(1 for n in news if n.get("interest_level")=="confirmed")),className="kpi-value"),html.P("clubes con oferta/interés real",className="kpi-sub")],className="kpi-modern"),md=3),
            dbc.Col(html.Div([html.P("Sondeados",className="kpi-label"),html.P(str(sum(1 for n in news if n.get("interest_level")=="sounded")),className="kpi-value"),html.P("sin oferta formal",className="kpi-sub")],className="kpi-modern"),md=3),
        ], className="g-3 mb-3"),

        # Salidas libres
        html.Div([
            html.Div([html.I(className="ti ti-user-x",style={"color":"#E30613","marginRight":"8px","fontSize":"16px"}),
                      html.Span("Salidas libres en junio 2026",style={"fontSize":"13px","fontWeight":"600","color":"#1A1A2E"})],
                     style={"display":"flex","alignItems":"center","marginBottom":"10px"}),
            *[html.Div([
                html.Strong(p["name"],style={"fontSize":"12px","color":"#1A1A2E","marginRight":"8px"}),
                html.Span(p["position"],style={"fontSize":"9px","fontWeight":"700","padding":"1px 6px","borderRadius":"99px","background":"#F3F4F6","color":"#374151","marginRight":"8px"}),
                html.Span(f"Salario: {_fmt(p['salary_annual'])}/año",style={"fontSize":"11px","color":"#6B7280","marginRight":"8px"}),
                html.Span(next((n["note"] for n in news if n["player"]==p["name"]),"Fin de contrato"),
                          style={"fontSize":"11px","color":"#9CA3AF","fontStyle":"italic"}),
            ], style={"display":"flex","alignItems":"center","flexWrap":"wrap","gap":"4px",
                      "padding":"8px 0","borderBottom":"1px solid #FECACA"})
            for p in libres],
        ], style={"background":"#FFF1F2","border":"1px solid #FECACA","borderRadius":"10px","padding":"14px 16px","marginBottom":"14px"}),

        # Editor de cláusulas + tarjetas de riesgo
        html.Div([
            html.Div([
                html.P("Score de riesgo — jugadores con contrato vigente",
                       style={"fontSize":"10px","fontWeight":"600","color":"#9CA3AF","textTransform":"uppercase","letterSpacing":".06em","margin":"0 0 2px"}),
                html.P("Factores: contrato restante · edad · ratio cláusula/valor TM · interés real (jun-2026)",
                       style={"fontSize":"11px","color":"#6B7280","margin":"0 0 6px"}),
                html.Span("Puedes editar las cláusulas directamente — el score se recalcula al pulsar ↵ o salir del campo.",
                          style={"fontSize":"10px","color":"#9CA3AF","fontStyle":"italic"}),
            ], style={"marginBottom":"14px"}),

            # Tabla editable de cláusulas
            html.Div([
                html.Table([
                    html.Thead(html.Tr([
                        html.Th("Jugador",    style=HEAD),
                        html.Th("Pos.",       style=HEAD),
                        html.Th("Cláusula (M€) — editable", style={**HEAD,"color":"#E30613"}),
                        html.Th("Confirmada",style=HEAD),
                        html.Th("Valor TM",  style=HEAD),
                        html.Th("Contrato",  style=HEAD),
                    ])),
                    html.Tbody([
                        html.Tr([
                            html.Td(html.Strong(p["name"],style={"fontSize":"12px"}), style=CELL),
                            html.Td(html.Span(p["position"],style={"fontSize":"9px","fontWeight":"700","padding":"1px 6px","borderRadius":"99px","background":"#F3F4F6","color":"#374151"}), style=CELL),
                            html.Td(dcc.Input(
                                id={"type":"clause-edit","index":p["name"]},
                                type="number", min=0, step=0.5,
                                value=round((p.get("release_clause") or 0)/1e6, 1),
                                debounce=True,
                                style=inp_s,
                            ), style=CELL),
                            html.Td(html.Span("✓" if p.get("clause_confirmed") else "~",
                                style={"color":"#166534" if p.get("clause_confirmed") else "#9CA3AF","fontWeight":"700"}), style=CELL),
                            html.Td(_fmt(MV_MAP.get(p["name"])), style=CELL),
                            html.Td([_contract_dot(p["contract_end"]), str(p["contract_end"])[:4]], style=CELL),
                        ])
                        for p in sorted(activos, key=lambda x: -(x.get("release_clause") or 0))
                    ]),
                ], style={"width":"100%","borderCollapse":"collapse"}),
            ], style={"overflowX":"auto","marginBottom":"16px",
                      "border":"1px solid #E5E7EB","borderRadius":"10px"}),

            # Tarjetas de riesgo dinámicas
            html.Div(id="risk-cards-container"),
        ], style={"background":"#fff","border":"1px solid #E5E7EB","borderRadius":"10px","padding":"16px 18px"}),
    ])

# ── Tab 4: Simulador ──────────────────────────────────────────────────────────
def tab_simulador(fin):
    players = fin["player_salaries"]
    scl     = fin["squad_cost_limit"]
    player_opts = [{"label":f"{p['name']} — {_fmt(p['salary_annual'])}/año","value":p["name"]}
                   for p in sorted(players,key=lambda x:-x["salary_annual"])]
    master_opts = _load_master_opts(['Spain_Primera_Division','Spain_Segunda_Division'])
    inp = {"width":"100%","padding":"7px 10px","border":"1px solid #E5E7EB","borderRadius":"7px","fontSize":"13px"}
    lbl = {"fontSize":"11px","color":"#6B7280","marginBottom":"4px","display":"block"}

    return html.Div([
        html.Div([
            html.I(className="ti ti-info-circle",style={"marginRight":"8px","color":"#1D4ED8"}),
            html.Span("Busca un jugador del scope del Rayo. Se auto-rellenan salario estimado y cláusula, editables para simular traspaso negociado.",
                      style={"fontSize":"12px","color":"#1E40AF"}),
        ], style={"background":"#EFF6FF","border":"1px solid #BFDBFE","borderRadius":"10px","padding":"12px 16px","marginBottom":"16px","display":"flex","alignItems":"center"}),

        dbc.Row([
            dbc.Col(html.Div([
                html.Div([html.I(className="ti ti-arrow-up-right",style={"color":"#E30613","marginRight":"8px","fontSize":"16px"}),
                          html.Span("Salidas simuladas",style={"fontSize":"13px","fontWeight":"600","color":"#1A1A2E"})],
                         style={"display":"flex","alignItems":"center","marginBottom":"12px"}),
                html.Span("Jugadores del Rayo que salen",style=lbl),
                dcc.Dropdown(player_opts,multi=True,id="sim-out",placeholder="Selecciona jugadores..."),
                html.Div(style={"height":"1px","background":"#F3F4F6","margin":"14px 0"}),
                html.Span("Ingreso por venta (M€)",style=lbl),
                dcc.Input(id="sim-income",type="number",min=0,value=0,step=0.5,placeholder="0.0",style=inp),
                html.Div(id="sim-out-summary",style={"marginTop":"10px"}),
            ], style={"background":"#fff","border":"1px solid #E5E7EB","borderRadius":"10px","padding":"16px","height":"100%"}),md=4),

            dbc.Col(html.Div([
                html.Div([html.I(className="ti ti-arrow-down-left",style={"color":"#10B981","marginRight":"8px","fontSize":"16px"}),
                          html.Span("Alta simulada",style={"fontSize":"13px","fontWeight":"600","color":"#1A1A2E"})],
                         style={"display":"flex","alignItems":"center","marginBottom":"12px"}),
                html.Span("Ligas a buscar",style=lbl),
                dcc.Dropdown(SIM_LEAGUES, multi=True, id="sim-leagues",
                             value=["Spain_Primera_Division","Spain_Segunda_Division"],
                             placeholder="Elige ligas...", style={"marginBottom":"8px"}),
                html.Span("Buscar jugador",style=lbl),
                dcc.Dropdown(options=master_opts,id="sim-player-search",placeholder="Escribe un nombre...",searchable=True,clearable=True),
                html.Div(id="sim-player-card",style={"marginTop":"10px","marginBottom":"10px"}),
                html.Div(style={"height":"1px","background":"#F3F4F6","margin":"10px 0"}),
                dbc.Row([
                    dbc.Col([html.Span("Salario anual (M€)",style=lbl),
                             dcc.Input(id="sim-new-salary",type="number",min=0,value=None,step=0.05,placeholder="auto",style=inp),
                             html.Span("editable — se auto-rellena",style={"fontSize":"10px","color":"#9CA3AF","marginTop":"3px","display":"block"})],width=6),
                    dbc.Col([html.Span("Cláusula estimada (M€)",style=lbl),
                             dcc.Input(id="sim-player-clause",type="number",min=0,value=None,step=0.5,placeholder="auto",style=inp),
                             html.Span("editable — ~3× valor TM",style={"fontSize":"10px","color":"#9CA3AF","marginTop":"3px","display":"block"})],width=6),
                ], className="g-2"),
                html.Div(style={"height":"1px","background":"#F3F4F6","margin":"10px 0"}),
                dbc.Row([
                    dbc.Col([html.Span("Traspaso acordado (M€)",style={**lbl,"color":"#374151","fontWeight":"600"}),
                             dcc.Input(id="sim-fee",type="number",min=0,value=None,step=0.5,placeholder="Ej: 8.0",style=inp)],width=7),
                    dbc.Col([html.Span("Años contrato",style=lbl),
                             dcc.Input(id="sim-contract-years",type="number",min=1,max=7,value=5,step=1,style=inp)],width=5),
                ], className="g-2"),
                html.Div(id="sim-fee-vs-clause",style={"marginTop":"6px"}),
            ], style={"background":"#fff","border":"1px solid #E5E7EB","borderRadius":"10px","padding":"16px","height":"100%"}),md=4),

            dbc.Col(html.Div(id="sim-results",style={"height":"100%"}),md=4),
        ], className="g-3"),
    ])

# ── Layout ────────────────────────────────────────────────────────────────────
def layout(**_params):
    return html.Div([
        html.Div([
            html.P("DIRECCIÓN DEPORTIVA",style={"fontSize":"10px","fontWeight":"600","color":"#6B7280","letterSpacing":".08em","margin":"0 0 3px"}),
            html.H1("Finanzas del Club",className="page-title"),
            html.P("Salarios · Presupuesto · Riesgo de cláusulas · Simulador de mercado · 2025/26",className="page-subtitle"),
        ], className="page-header"),

        dcc.Tabs(id="fin-tabs",value="salarios",
                 style={"marginBottom":"16px"},
                 colors={"border":"#E5E7EB","primary":"#E30613","background":"#F9FAFB"},
                 children=[
            dcc.Tab(label="💶  Salarios",        value="salarios",
                    style={"fontSize":"13px","fontWeight":"500","padding":"8px 18px"},
                    selected_style={"fontSize":"13px","fontWeight":"600","padding":"8px 18px","borderTop":"3px solid #E30613","color":"#E30613"}),
            dcc.Tab(label="📊  Presupuesto",     value="presupuesto",
                    style={"fontSize":"13px","fontWeight":"500","padding":"8px 18px"},
                    selected_style={"fontSize":"13px","fontWeight":"600","padding":"8px 18px","borderTop":"3px solid #E30613","color":"#E30613"}),
            dcc.Tab(label="🎯  Riesgo cláusulas",value="riesgo",
                    style={"fontSize":"13px","fontWeight":"500","padding":"8px 18px"},
                    selected_style={"fontSize":"13px","fontWeight":"600","padding":"8px 18px","borderTop":"3px solid #E30613","color":"#E30613"}),
            dcc.Tab(label="🔀  Simulador",       value="simulador",
                    style={"fontSize":"13px","fontWeight":"500","padding":"8px 18px"},
                    selected_style={"fontSize":"13px","fontWeight":"600","padding":"8px 18px","borderTop":"3px solid #E30613","color":"#E30613"}),
        ]),
        html.Div(id="fin-content"),
        criteria_accordion("finanzas"),
    ])

# ── Callbacks ─────────────────────────────────────────────────────────────────

@callback(
    Output("sal-live-kpis", "children"),
    Input({"type": "sal-edit", "index": ALL}, "value"),
    Input({"type": "sal-edit", "index": ALL}, "id"),
    prevent_initial_call=False,
)
def _update_sal_kpis(values, ids):
    fin = _load_finances()
    players = fin["player_salaries"]
    scl = fin["squad_cost_limit"]
    base_total = sum(p["salary_annual"] for p in players)
    bonus_total = sum(p["bonus_annual"] for p in players)
    # Apply any overrides
    overrides = {}
    for v, i in zip(values or [], ids or []):
        if v is not None and v > 0:
            overrides[i["index"]] = float(v) * 1_000_000
    if not overrides:
        return html.Div()
    adj_total = sum(
        overrides.get(p["name"], p["salary_annual"]) for p in players
    )
    diff = adj_total - base_total
    pct = adj_total / scl["limit_eur"] * 100
    diff_color = "#E30613" if diff > 0 else "#166534"
    diff_str = (f"+{_fmt(diff)}" if diff >= 0 else f"-{_fmt(abs(diff))}") + " vs. original"
    return html.Div([
        html.Div([
            html.I(className="ti ti-edit",
                   style={"color":"#F59E0B","fontSize":"14px","marginRight":"8px"}),
            html.Span("Salarios editados — impacto en tiempo real:",
                      style={"fontSize":"12px","fontWeight":"600","color":"#374151",
                             "marginRight":"16px"}),
            html.Span(f"Masa ajustada: {_fmt(adj_total)}",
                      style={"fontSize":"12px","fontWeight":"700","color":"#1A1A2E",
                             "marginRight":"16px"}),
            html.Span(diff_str, style={"fontSize":"12px","color":diff_color,
                                       "fontWeight":"600","marginRight":"16px"}),
            html.Span(f"Uso límite LaLiga: {pct:.1f}%",
                      style={"fontSize":"12px","color":"#E30613" if pct>90 else
                             ("#F59E0B" if pct>75 else "#374151")}),
        ], style={"display":"flex","alignItems":"center","flexWrap":"wrap","gap":"4px"}),
        html.Div(
            html.Div(style={"height":"100%","width":f"{min(pct,100):.1f}%",
                "background":"#10B981" if pct<75 else ("#F59E0B" if pct<90 else "#E30613"),
                "borderRadius":"99px"}),
            style={"height":"6px","background":"#F3F4F6","borderRadius":"99px",
                   "overflow":"hidden","marginTop":"8px"},
        ),
    ], style={"background":"#FFFBEB","border":"1px solid #FDE68A","borderRadius":"10px",
              "padding":"12px 16px","marginBottom":"12px"})


@callback(
    Output("risk-cards-container","children"),
    Input({"type":"clause-edit","index":ALL},"value"),
    Input({"type":"clause-edit","index":ALL},"id"),
    prevent_initial_call=False,
)
def update_risk_cards(values, ids):
    fin     = _load_finances()
    players = fin["player_salaries"]
    news    = fin.get("transfer_news",[])

    # Construir dict de overrides desde los inputs
    overrides = {}
    for v, i in zip(values or [], ids or []):
        if v is not None:
            overrides[i["index"]] = float(v) * 1_000_000

    # Aplicar overrides a una copia de los jugadores
    patched = []
    for p in players:
        if int(str(p.get("contract_end","2030"))[:4]) <= 2026:
            continue
        pp = dict(p)
        if pp["name"] in overrides:
            pp["release_clause"] = overrides[pp["name"]]
        patched.append(pp)

    scored = sorted(patched, key=lambda x: -_clause_risk_score(x, news)[0])
    return html.Div(
        [_risk_card(p, news) for p in scored],
        style={"display":"grid","gridTemplateColumns":"repeat(auto-fill,minmax(310px,1fr))","gap":"12px"},
    )


@callback(Output("fin-content","children"), Input("fin-tabs","value"))
def render_tab(tab):
    try:
        fin = _load_finances()
        if tab == "salarios":    return tab_salarios(fin)
        if tab == "presupuesto": return tab_presupuesto(fin)
        if tab == "riesgo":      return tab_riesgo(fin)
        return tab_simulador(fin)
    except Exception as e:
        return html.Div([
            html.Strong("Error: ",style={"color":"#E30613"}),
            html.Code(str(e),style={"fontSize":"12px"}),
            html.Pre(traceback.format_exc(),style={"fontSize":"10px","marginTop":"8px","color":"#6B7280","whiteSpace":"pre-wrap"}),
        ], style={"background":"#FFF1F2","border":"1px solid #FECDD3","borderRadius":"10px","padding":"14px 16px"})

@callback(Output("sim-player-card","children"),Output("sim-new-salary","value"),Output("sim-player-clause","value"),
          Input("sim-player-search","value"))
def fill_player_data(player_name):
    if not player_name: return html.Div(), None, None
    try:
        s = settings()
        master_path = Path(s["paths"]["data_processed"]) / "master_players.parquet"
        if not master_path.exists():
            return html.P("Master no disponible",style={"fontSize":"12px","color":"#E30613"}), None, None
        df  = pd.read_parquet(master_path)
        row = df[df["name"].astype(str).str.lower() == player_name.lower()]
        if row.empty: row = df[df["name"].astype(str).str.contains(player_name,case=False,na=False)]
        if row.empty: return html.P(f"'{player_name}' no encontrado",style={"fontSize":"12px","color":"#9CA3AF"}), None, None
        # elegir la fila más reciente (si jugó en dos equipos la última temporada, el destino nuevo)
        try:
            from src.profiling.player_profile import most_recent_team
            rt = most_recent_team(row)
            sub = row[row["team"] == rt]
            p = sub.iloc[0] if not sub.empty else row.iloc[0]
        except Exception:
            p = row.iloc[0]
        name    = str(p.get("name",""))
        pos     = str(p.get("position_primary","?"))
        team    = str(p.get("team","?"))
        league  = str(p.get("league","?"))
        age     = int(float(p["age"])) if "age" in p.index and pd.notna(p["age"]) else None
        mv_raw  = p.get("market_value_eur") if "market_value_eur" in p.index else None
        mv      = float(mv_raw) if mv_raw and pd.notna(mv_raw) else MV_MAP.get(name)
        mins    = int(float(p["minutes"])) if "minutes" in p.index and pd.notna(p["minutes"]) else None
        goals   = int(float(p["goals"]))   if "goals"   in p.index and pd.notna(p["goals"])   else None
        assists = int(float(p["assists"])) if "assists" in p.index and pd.notna(p["assists"]) else None
        sal_est    = _estimate_salary(mv, age)
        clause_est = _estimate_clause(mv, age)
        initials   = "".join(w[0].upper() for w in name.split()[:2] if w)
        card = html.Div([
            html.Div([
                html.Div(initials,style={"width":"36px","height":"36px","borderRadius":"50%","background":"#1A1A2E",
                    "color":"#fff","display":"flex","alignItems":"center","justifyContent":"center",
                    "fontSize":"11px","fontWeight":"600","flexShrink":"0"}),
                html.Div([
                    html.Div([html.Strong(name,style={"fontSize":"13px","color":"#1A1A2E","marginRight":"6px"}),
                              html.Span(pos,style={"fontSize":"9px","fontWeight":"700","padding":"1px 6px","borderRadius":"99px","background":"#F3F4F6","color":"#374151"})]),
                    html.Div(f"{team}  ·  {league}",style={"fontSize":"11px","color":"#6B7280","marginTop":"2px"}),
                ]),
            ], style={"display":"flex","alignItems":"center","gap":"10px","marginBottom":"8px"}),
            (lambda _p: html.Div([
                html.Span("Tipo de jugador (histórico): ", style={"fontSize":"10px","color":"#9CA3AF"}),
                html.Span(_p["primary_role_label"], style={"fontSize":"11px","fontWeight":"700","color":"#fff",
                    "background":"#E30613","borderRadius":"99px","padding":"2px 9px","marginLeft":"4px"}),
                html.Span(f"  {_p.get('seasons_played','?')} temp · {int(_p.get('minutes') or 0)} min",
                    style={"fontSize":"10px","color":"#9CA3AF","marginLeft":"6px"}),
            ], style={"marginBottom":"8px"}) if _p else html.Span())(_career_role(name)),
            html.Div([
                *([html.Span(f"Edad: {age}",style={"fontSize":"11px","color":"#374151","marginRight":"10px"})] if age else []),
                *([html.Span(f"Valor TM: {_fmt(mv)}",style={"fontSize":"11px","color":"#374151","marginRight":"10px"})] if mv else []),
                *([html.Span(f"Min: {mins}",style={"fontSize":"11px","color":"#374151","marginRight":"8px"})] if mins else []),
                *([html.Span(f"G: {goals}",style={"fontSize":"11px","color":"#374151","marginRight":"8px"})] if goals is not None else []),
                *([html.Span(f"A: {assists}",style={"fontSize":"11px","color":"#374151"})] if assists is not None else []),
            ], style={"display":"flex","flexWrap":"wrap","marginBottom":"5px"}),
            html.Span(f"Sal. est.: {_fmt(sal_est)}/año  ·  Cláusula est.: {_fmt(clause_est)}  (editable abajo →)",
                      style={"fontSize":"10px","color":"#9CA3AF"}),
        ], style={"background":"#F9FAFB","border":"1px solid #E5E7EB","borderRadius":"8px","padding":"10px 12px"})
        return card, round(sal_est/1_000_000,2), round(clause_est/1_000_000,1)
    except Exception as e:
        return html.P(str(e),style={"fontSize":"11px","color":"#E30613"}), None, None

@callback(Output("sim-fee-vs-clause","children"),Input("sim-fee","value"),Input("sim-player-clause","value"))
def show_fee_comparison(fee_m, clause_m):
    if not fee_m or not clause_m: return html.Div()
    diff = (clause_m - fee_m) * 1_000_000
    if diff > 0:
        return html.Div([html.I(className="ti ti-discount",style={"color":"#10B981","marginRight":"6px"}),
            html.Span(f"Acuerdo {_fmt(diff)} por debajo de la cláusula — ahorro para el Rayo",style={"fontSize":"11px","color":"#166534","fontWeight":"500"})],
            style={"background":"#F0FDF4","border":"1px solid #BBF7D0","borderRadius":"7px","padding":"7px 10px","display":"flex","alignItems":"center"})
    elif diff < 0:
        return html.Div([html.I(className="ti ti-alert-triangle",style={"color":"#F59E0B","marginRight":"6px"}),
            html.Span(f"Traspaso supera la clausula en {_fmt(abs(diff))} - revisar",style={"fontSize":"11px","color":"#92400E","fontWeight":"500"})],
            style={"background":"#FFFBEB","border":"1px solid #FDE68A","borderRadius":"7px","padding":"7px 10px","display":"flex","alignItems":"center"})
    return html.Span("Igual a la clausula",style={"fontSize":"11px","color":"#6B7280"})

@callback(Output("sim-out-summary","children"),Input("sim-out","value"))
def show_out_summary(out_players):
    if not out_players: return html.Div()
    fin = _load_finances()
    pmap = {p["name"]:p for p in fin["player_salaries"]}
    return html.Div([
        html.Div([
            html.Span(n,style={"fontSize":"11px","fontWeight":"600","color":"#1A1A2E","flex":"1"}),
            html.Span(_fmt(pmap[n]["salary_annual"]),style={"fontSize":"11px","color":"#E30613","marginRight":"8px"}),
            html.Span(f"clausula: {_fmt(pmap[n].get('release_clause'))}",style={"fontSize":"10px","color":"#6B7280"}),
        ], style={"display":"flex","alignItems":"center","padding":"5px 0","borderBottom":"1px solid #F3F4F6"})
        for n in out_players if n in pmap
    ])

@callback(Output("sim-results","children"),
          Input("sim-out","value"),Input("sim-new-salary","value"),
          Input("sim-income","value"),Input("sim-fee","value"),
          Input("sim-contract-years","value"))
def update_sim(out_players, new_salary_m, income_m, fee_m, years):
    fin = _load_finances()
    pmap  = {p["name"]:p for p in fin["player_salaries"]}
    scl   = fin["squad_cost_limit"]
    base  = scl["current_wage_bill_eur"]
    limit = scl["limit_eur"]
    cur_amort = fin.get("expenses", {}).get("amortizations_eur", 0)
    # presupuesto de fichajes (caja) — del club_profile si existe
    try:
        from src.utils.config import club_profile
        budget_cash = club_profile().get("finances_eur", {}).get("transfer_budget_net_eur", 12_000_000)
    except Exception:
        budget_cash = 12_000_000

    saved   = sum(pmap[n]["salary_annual"] for n in (out_players or []) if n in pmap)
    new_sal = (new_salary_m or 0)*1_000_000
    income  = (income_m or 0)*1_000_000
    fee     = (fee_m or 0)*1_000_000
    years   = int(years) if years else 5

    # Coste de plantilla LaLiga = salarios + amortizaciones
    new_wage  = base - saved + new_sal
    new_amort = cur_amort + (fee / years if years > 0 else fee)
    squad_cost = new_wage + new_amort
    headroom  = limit - squad_cost
    cost_ok   = headroom >= 0

    # Tesorería: gasto neto vs presupuesto de fichajes
    net_spend = fee - income
    cash_ok   = net_spend <= budget_cash

    ok = cost_ok and cash_ok
    if ok:
        msg = "Operacion viable"
    elif not cost_ok and not cash_ok:
        msg = "INVIABLE: excede limite de coste y presupuesto"
    elif not cost_ok:
        msg = "EXCEDE el limite de coste LaLiga"
    else:
        msg = "EXCEDE el presupuesto de fichajes (caja)"

    def row(label, val, color="#1A1A2E"):
        return html.Div([html.Span(label,style={"fontSize":"11px","color":"#6B7280","flex":"1"}),
                         html.Span(val,  style={"fontSize":"13px","fontWeight":"700","color":color})],
                        style={"display":"flex","alignItems":"center","padding":"7px 0","borderBottom":"1px solid #F3F4F6"})

    # ── Gráfico dinámico: comparativa masa salarial + límite ──
    def _m(v): return round(v / 1e6, 2)

    fig_bar = go.Figure()
    categories = ["Masa salarial\nactual", "Masa salarial\nsimulada", "Límite\nLaLiga"]
    values_bar = [_m(base), _m(new_wage), _m(limit)]
    colors_bar = [RAYO_DARK, RAYO_RED if new_wage > limit else C_POSITIVE, C_WARNING]
    fig_bar.add_trace(go.Bar(
        x=categories, y=values_bar,
        marker=dict(color=colors_bar, line=dict(color="white", width=1)),
        text=[f"{v:.1f}M€" for v in values_bar],
        textposition="outside",
        textfont=dict(size=11, color=RAYO_DARK),
        hovertemplate="<b>%{x}</b><br>%{y:.1f}M€<extra></extra>",
    ))
    apply_theme(fig_bar, height=210, transparent=True, compact=True)
    fig_bar.update_layout(
        showlegend=False,
        yaxis_title="M€",
        yaxis_range=[0, max(values_bar) * 1.18],
        title_text="Masa salarial vs Límite LaLiga",
    )

    # ── Gráfico impacto coste LaLiga (gauge de uso del límite) ──
    uso_pct = min(squad_cost / limit * 100, 120) if limit > 0 else 0
    fig_gauge = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=uso_pct,
        number={"suffix": "%", "font": {"size": 26, "color": RAYO_DARK}},
        delta={"reference": base / limit * 100 if limit > 0 else 0,
               "suffix": "%", "font": {"size": 11}},
        title={"text": "Uso del límite LaLiga<br><span style='font-size:10px;color:#6B7280'>Coste plantilla / Límite</span>",
               "font": {"size": 12, "color": RAYO_DARK}},
        gauge={
            "axis": {"range": [0, 120], "ticksuffix": "%",
                     "tickfont": {"size": 9}, "nticks": 7},
            "bar": {"color": RAYO_RED if uso_pct > 100 else (C_WARNING if uso_pct > 85 else C_POSITIVE),
                    "thickness": 0.25},
            "bgcolor": "white",
            "bordercolor": "#E5E7EB",
            "steps": [
                {"range": [0, 85],  "color": "#F0FDF4"},
                {"range": [85, 100], "color": "#FEF9C3"},
                {"range": [100, 120], "color": "#FFF1F2"},
            ],
            "threshold": {"line": {"color": RAYO_RED, "width": 3},
                          "thickness": 0.8, "value": 100},
        },
    ))
    fig_gauge.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        height=180,
        margin=dict(l=20, r=20, t=50, b=10),
    )

    return html.Div([
        html.Div([
            html.I(className=f"ti {'ti-circle-check' if ok else 'ti-alert-triangle'}",
                   style={"fontSize":"18px","color":"#10B981" if ok else "#E30613","marginRight":"8px"}),
            html.Span(msg, style={"fontSize":"13px","fontWeight":"700","color":"#166534" if ok else "#9F1239"}),
        ], style={"display":"flex","alignItems":"center","marginBottom":"10px",
                  "background":"#F0FDF4" if ok else "#FFF1F2","padding":"10px 12px","borderRadius":"8px"}),

        dcc.Graph(figure=fig_gauge, config=GRAPH_CONFIG_SIMPLE),
        dcc.Graph(figure=fig_bar,   config=GRAPH_CONFIG_SIMPLE),

        html.P("Desglose de coste",
               style={"fontSize":"10px","fontWeight":"700","color":"#9CA3AF","textTransform":"uppercase","margin":"8px 0 4px"}),
        row("Masa salarial actual",        _fmt(base),      "#374151"),
        row("Ahorro por salidas",          f"-{_fmt(saved)}","#10B981"),
        row("Nuevo salario incorporación", f"+{_fmt(new_sal)}","#E30613"),
        row(f"Amortiz. ({_fmt(fee)}/{years}a)", f"+{_fmt(fee/years if years else fee)}","#E30613"),
        row("Coste total plantilla",       _fmt(squad_cost), "#1A1A2E"),
        row("Margen vs límite",            _fmt(headroom),   "#10B981" if headroom>=0 else "#E30613"),
        html.Div(style={"borderTop":"2px solid #E5E7EB","margin":"8px 0"}),
        html.P("Tesorería",
               style={"fontSize":"10px","fontWeight":"700","color":"#9CA3AF","textTransform":"uppercase","margin":"4px 0"}),
        row("Ingresos ventas",    f"+{_fmt(income)}",           "#10B981"),
        row("Traspaso pagado",    f"-{_fmt(fee)}",              "#E30613"),
        row("Gasto neto",         _fmt(net_spend),              "#E30613" if net_spend>0 else "#10B981"),
        row("Presupuesto caja",   _fmt(budget_cash),            "#374151"),
        row("Margen de caja",     _fmt(budget_cash-net_spend),  "#10B981" if cash_ok else "#E30613"),
    ], style={"background":"#fff","border":"1px solid #E5E7EB","borderRadius":"10px","padding":"14px 16px"})


# ── Callbacks editor de presupuesto ──────────────────────────────────────────
@callback(Output("bud-refresh", "data"),
          Input("bud-add", "n_clicks"),
          Input({"type": "bud-del", "index": ALL}, "n_clicks"),
          State("bud-concept", "value"), State("bud-type", "value"),
          State("bud-amount", "value"), State("bud-refresh", "data"),
          prevent_initial_call=True)
def _bud_edit(add_n, del_n, concept, tipo, amount, refresh):
    items = _load_custom()
    trig = ctx.triggered_id
    changed = False
    if trig == "bud-add" and concept and amount:
        items.append({"concepto": str(concept).strip(), "tipo": tipo or "ingreso",
                      "importe_eur": float(amount) * 1_000_000})
        changed = True
    elif isinstance(trig, dict) and trig.get("type") == "bud-del":
        idx = trig["index"]
        if 0 <= idx < len(items):
            items.pop(idx); changed = True
    if changed:
        _save_custom(items)
        return (refresh or 0) + 1
    return no_update


@callback(Output("bud-list", "children"), Output("bud-balance", "children"),
          Input("bud-refresh", "data"))
def _bud_render(_r):
    fin = _load_finances()
    base_rev, base_exp = _base_totals(fin)
    items = _load_custom()
    extra_rev = sum(i["importe_eur"] for i in items if i.get("tipo") == "ingreso")
    extra_exp = sum(i["importe_eur"] for i in items if i.get("tipo") == "gasto")
    adj_balance = (base_rev + extra_rev) - (base_exp + extra_exp)

    if not items:
        rows = [html.P("Sin partidas añadidas todavía.", style={"fontSize": "12px", "color": "#9CA3AF"})]
    else:
        rows = []
        for i, it in enumerate(items):
            is_in = it.get("tipo") == "ingreso"
            rows.append(html.Div([
                html.Span("▲ Ingreso" if is_in else "▼ Gasto", style={"fontSize": "10px", "fontWeight": "700",
                    "color": "#166534" if is_in else "#9F1239", "width": "80px", "display": "inline-block"}),
                html.Span(it["concepto"], style={"fontSize": "12px", "color": "#374151", "flex": "1"}),
                html.Span(("+" if is_in else "-") + _fmt(it["importe_eur"]),
                          style={"fontSize": "12px", "fontWeight": "700",
                                 "color": "#166534" if is_in else "#E30613", "marginRight": "12px"}),
                html.Span("x", id={"type": "bud-del", "index": i}, style={"cursor": "pointer",
                    "color": "#9CA3AF", "fontWeight": "700"}),
            ], style={"display": "flex", "alignItems": "center", "padding": "7px 0",
                      "borderBottom": "1px solid #F3F4F6"}))

    bal_color = "#166534" if adj_balance >= 0 else "#9F1239"
    bal_bg = "#F0FDF4" if adj_balance >= 0 else "#FFF1F2"
    balance = html.Div([
        html.Div([
            html.Span("Balance ajustado", style={"fontSize": "11px", "color": "#6B7280", "flex": "1"}),
            html.Span(("Superávit " if adj_balance >= 0 else "Déficit ") + _fmt(abs(adj_balance)),
                      style={"fontSize": "16px", "fontWeight": "700", "color": bal_color}),
        ], style={"display": "flex", "alignItems": "center"}),
        html.Div(f"Base: ingresos {_fmt(base_rev)} - gastos {_fmt(base_exp)}  |  "
                 f"Ajustes: +{_fmt(extra_rev)} / -{_fmt(extra_exp)}",
                 style={"fontSize": "10px", "color": "#9CA3AF", "marginTop": "4px"}),
    ], style={"background": bal_bg, "borderRadius": "8px", "padding": "12px 14px"})
    return html.Div(rows), balance


@callback(Output("sim-player-search", "options"), Input("sim-leagues", "value"))
def _sim_update_leagues(leagues):
    return _load_master_opts(leagues or None)
