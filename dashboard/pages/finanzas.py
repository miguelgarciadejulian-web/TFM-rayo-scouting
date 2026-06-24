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
    c = "#DC2626" if year <= 2026 else ("#F59E0B" if year <= 2027 else "#10B981")
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
        "letterSpacing":".06em","padding":"0 10px 8px","borderBottom":"2px solid #FFD600"}

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
        "MUY ALTO": ("#FFF1F2","#DC2626","#9F1239"),
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


# ── Finanzas KPI card helper ──────────────────────────────────────────────────
def _fkpi(icon: str, label: str, value, sub: str, grad1: str, grad2: str, icon_color: str = "#fff"):
    """Gradient-icon KPI card matching the modern design system."""
    return html.Div([
        html.Div([html.I(className=f"ti {icon}",
                         style={"fontSize":"20px","color":icon_color})],
                 style={"width":"40px","height":"40px","borderRadius":"10px",
                        "background":f"linear-gradient(135deg,{grad1},{grad2})",
                        "display":"flex","alignItems":"center","justifyContent":"center",
                        "marginBottom":"10px"}),
        html.P(label, style={"fontSize":"10px","color":"#6B7280","margin":"0 0 2px",
                              "textTransform":"uppercase","letterSpacing":".05em","fontWeight":"600"}),
        html.P(str(value), style={"fontSize":"20px","fontWeight":"800","color":"#1A1A2E",
                                   "margin":"0 0 2px","lineHeight":"1"}),
        html.P(sub, style={"fontSize":"11px","color":"#9CA3AF","margin":"0"}),
    ], style={"background":"#fff","border":"1px solid #E5E7EB","borderRadius":"12px",
              "padding":"16px","boxShadow":"0 2px 8px rgba(0,0,0,.06)"})

def _contract_year_bars(players):
    """Barras de vencimientos de contrato para la pestaña salarios."""
    yr_map = {}
    for p in players:
        yr = str(p.get("contract_end","2030"))[:4]
        yr_map[yr] = yr_map.get(yr, 0) + 1
    total = len(players) or 1
    bars = []
    for yr, cnt in sorted(yr_map.items()):
        color = "#DC2626" if yr <= "2026" else ("#F59E0B" if yr <= "2027" else "#10B981")
        bars.append(html.Div([
            html.Span(yr, style={"fontSize":"10px","color":"#6B7280","width":"34px","flexShrink":"0"}),
            html.Div(style={"flex":"1","height":"8px","background":"#F3F4F6","borderRadius":"99px",
                            "overflow":"hidden","alignSelf":"center"},
                children=html.Div(style={"height":"100%","borderRadius":"99px",
                    "width":f"{cnt/total*100:.0f}%","background":color})),
            html.Span(str(cnt), style={"fontSize":"10px","color":"#374151","marginLeft":"6px","fontWeight":"600"}),
        ], style={"display":"flex","alignItems":"center","gap":"6px","marginBottom":"5px"}))
    return bars


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
            dbc.Col(_fkpi("ti-wallet","Masa salarial base",_fmt(total),"sin bonus","#047857","#10B981"),md=3),
            dbc.Col(_fkpi("ti-receipt","Total con bonus",_fmt(total+bonus),"bonus conocidos","#1D4ED8","#3B82F6"),md=3),
            dbc.Col(_fkpi("ti-chart-bar","Límite LaLiga",_fmt(scl["limit_eur"]),f"#{scl['laliga_ranking']} LaLiga","#6D28D9","#8B5CF6"),md=3),
            dbc.Col(_fkpi("ti-trending-up","Margen disponible",_fmt(scl["limit_eur"]-total),f"{100-pct:.0f}% libre","#065F46","#059669"),md=3),
        ], className="g-3 mb-3"),
        html.Div(id="sal-live-kpis"),
        html.Div([
            html.Div([html.Span("Uso del límite salarial",style={"fontSize":"11px","fontWeight":"600","color":"#374151"}),
                      html.Span(f" {pct:.1f}%",style={"fontSize":"11px","color":"#6B7280","marginLeft":"6px"})],style={"marginBottom":"6px"}),
            html.Div(style={"height":"12px","background":"#F3F4F6","borderRadius":"99px","overflow":"hidden"},
                children=html.Div(style={"height":"100%","width":f"{min(pct,100):.1f}%",
                    "background":"#10B981" if pct<75 else ("#F59E0B" if pct<90 else "#FFD600"),
                    "borderRadius":"99px"})),
        ], style={"background":"#fff","border":"1px solid #E5E7EB","borderRadius":"10px","padding":"14px 18px","marginBottom":"14px"}),
        dbc.Row([
            dbc.Col(html.Div([
                html.P("Contratos y salarios · SalaryLeaks (mar-2026) · Capology",
                       style={"fontSize":"10px","fontWeight":"600","color":"#9CA3AF","textTransform":"uppercase","letterSpacing":".06em","marginBottom":"10px"}),
                html.Div([
                    html.Span("✓ Cláusula confirmada",style={"fontSize":"10px","color":"#166534","background":"#DCFCE7","padding":"2px 8px","borderRadius":"99px","marginRight":"10px"}),
                    html.Span("~ Cláusula estimada",  style={"fontSize":"10px","color":"#6B7280","background":"#F3F4F6","padding":"2px 8px","borderRadius":"99px"}),
                ], style={"marginBottom":"12px"}),
                html.Div(html.Table([
                    html.Thead(html.Tr([html.Th("Jugador",style=HEAD),html.Th("Pos.",style=HEAD),
                        html.Th("Semanal",style=HEAD),html.Th("Anual",style=HEAD),
                        html.Th("Editar (M€/año)",style={**HEAD,"color":"#FFD600"}),
                        html.Th("Bonus",style=HEAD),
                        html.Th("Contrato",style=HEAD),html.Th("Cláusula",style=HEAD)])),
                    html.Tbody(rows),
                ], style={"width":"100%","borderCollapse":"collapse"}), style={"overflowX":"auto"}),
            ], style={"background":"#fff","border":"1px solid #E5E7EB","borderRadius":"10px","padding":"16px 18px","height":"100%"}), md=8),

            dbc.Col([
                html.Div([
                    html.P("Distribución salarial",
                           style={"fontSize":"10px","fontWeight":"700","color":"#9CA3AF","textTransform":"uppercase",
                                  "letterSpacing":".06em","margin":"0 0 4px","textAlign":"center"}),
                    dcc.Graph(
                        figure=apply_theme(go.Figure(go.Pie(
                            labels=[p["name"].split()[-1] for p in sorted(players,key=lambda x:-x["salary_annual"])[:8]],
                            values=[p["salary_annual"]/1e6 for p in sorted(players,key=lambda x:-x["salary_annual"])[:8]],
                            hole=0.52,
                            marker=dict(colors=["#0A0B0E","#E30613","#374151","#6B7280",
                                                "#9CA3AF","#D1D5DB","#F3F4F6","#1E2028"]),
                            textinfo="none",
                            hovertemplate="<b>%{label}</b><br>%{value:.2f}M€/año<br>%{percent}<extra></extra>",
                        )), height=180, transparent=True, compact=True) or go.Figure(),
                        config={"displayModeBar":False},
                    ),
                    html.Div([
                        html.Span([
                            html.Span(style={"display":"inline-block","width":"7px","height":"7px","borderRadius":"50%",
                                             "background":c,"marginRight":"4px","verticalAlign":"middle"}),
                            html.Span(l, style={"fontSize":"9px","color":"#6B7280"}),
                        ], style={"marginRight":"10px"})
                        for c,l in [("#DC2626","Expira 2026"),("#F59E0B","2027"),("#10B981","2028+")]
                    ], style={"display":"flex","justifyContent":"center","flexWrap":"wrap","marginBottom":"12px"}),

                    html.P("Vencimientos de contrato",
                           style={"fontSize":"10px","fontWeight":"700","color":"#9CA3AF","textTransform":"uppercase",
                                  "letterSpacing":".06em","margin":"8px 0 8px","textAlign":"center"}),
                    *_contract_year_bars(players),
                ], style={"background":"#fff","border":"1px solid #E5E7EB","borderRadius":"10px","padding":"14px 16px"}),
            ], md=4),
        ], className="g-3"),
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
            html.Div([html.I(className=f"ti {icon}",style={"fontSize":"15px","color":"#B8960C","marginRight":"8px","width":"20px"}),
                html.Span(label,style={"fontSize":"13px","color":"#374151","flex":"1"}),
                html.Span(note,style={"fontSize":"11px","color":"#9CA3AF","marginRight":"12px"}),
                html.Span(_fmt(value),style={"fontSize":"13px","fontWeight":"700","color":"#1A1A2E","minWidth":"60px","textAlign":"right"}),
            ], style={"display":"flex","alignItems":"center","marginBottom":"6px"}),
            html.Div(style={"height":"5px","background":"#F3F4F6","borderRadius":"99px","overflow":"hidden","marginBottom":"12px"},
                children=html.Div(style={"height":"100%","width":f"{pct:.1f}%","background":"#FFD600","borderRadius":"99px"})),
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
            dbc.Col(_fkpi("ti-arrow-up","Ingresos estimados",_fmt(total_rev),"temporada 2026/27","#047857","#10B981"),md=3),
            dbc.Col(_fkpi("ti-arrow-down","Gastos estimados",_fmt(total_exp),"estructura + plantilla","#9F1239","#FFD600"),md=3),
            dbc.Col(_fkpi("ti-scale","Balance operativo",_fmt(abs(balance)),"superávit" if balance>=0 else "déficit","#047857" if balance>=0 else "#9F1239","#10B981" if balance>=0 else "#FFD600"),md=3),
            dbc.Col(_fkpi("ti-trophy","Conference League",_fmt(rev["conference_league_eur"]),"final 2024-25 (Crystal Palace 1-0)","#92400E","#F59E0B"),md=3),
        ], className="g-3 mb-3"),
        dbc.Row([
            dbc.Col(html.Div([
                html.P("Ingresos",style={"fontSize":"10px","fontWeight":"600","color":"#9CA3AF","textTransform":"uppercase","letterSpacing":".06em","marginBottom":"16px"}),
                rev_row("Derechos TV LaLiga",    rev["tv_laliga_eur"],           "ti-tv",             "est. 2026-27"),
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
                          html.Span(_fmt(total_exp),style={"fontSize":"15px","fontWeight":"700","color":"#B8960C"})],
                         style={"display":"flex","alignItems":"center"}),
            ], style={"background":"#fff","border":"1px solid #E5E7EB","borderRadius":"10px","padding":"16px 18px"}), md=6),
        ], className="g-3"),

        # ── Gráfico comparativa ───────────────────────────────────────────────
        dbc.Row([
            dbc.Col(html.Div([
                html.P("Ingresos", style={"fontSize":"10px","fontWeight":"700","color":"#9CA3AF",
                    "textTransform":"uppercase","letterSpacing":".06em","margin":"0 0 0","textAlign":"center"}),
                dcc.Graph(
                    figure=apply_theme(go.Figure(go.Pie(
                        labels=["Derechos TV","Conference League","Taquilla","Comercial","Otros"],
                        values=[rev["tv_laliga_eur"],rev["conference_league_eur"],rev["matchday_eur"],
                                rev["commercial_sponsorship_eur"],rev["other_eur"]],
                        hole=0.55,
                        marker=dict(colors=["#047857","#059669","#10B981","#34D399","#6EE7B7"]),
                        textinfo="none",
                        hovertemplate="<b>%{label}</b><br>%{value:,.0f}€<br>%{percent}<extra></extra>",
                    )), height=160, transparent=True, compact=True) or go.Figure(),
                    config={"displayModeBar":False},
                ),
            ], style={"background":"#fff","border":"1px solid #E5E7EB","borderRadius":"10px","padding":"12px 16px"}), md=4),

            dbc.Col(html.Div([
                html.P("Gastos", style={"fontSize":"10px","fontWeight":"700","color":"#9CA3AF",
                    "textTransform":"uppercase","letterSpacing":".06em","margin":"0 0 0","textAlign":"center"}),
                dcc.Graph(
                    figure=apply_theme(go.Figure(go.Pie(
                        labels=["Masa salarial","Amortizaciones","Operativos","Traspasos netos"],
                        values=[exp["wage_bill_gross_eur"]+exp["bonus_bill_eur"],
                                exp["amortizations_eur"],exp["operating_costs_eur"],exp["transfers_net_eur"]],
                        hole=0.55,
                        marker=dict(colors=["#9F1239","#B91C1C","#DC2626","#F87171"]),
                        textinfo="none",
                        hovertemplate="<b>%{label}</b><br>%{value:,.0f}€<br>%{percent}<extra></extra>",
                    )), height=160, transparent=True, compact=True) or go.Figure(),
                    config={"displayModeBar":False},
                ),
            ], style={"background":"#fff","border":"1px solid #E5E7EB","borderRadius":"10px","padding":"12px 16px"}), md=4),

            dbc.Col(html.Div([
                html.P("Balance 2026/27", style={"fontSize":"10px","fontWeight":"700","color":"#9CA3AF",
                    "textTransform":"uppercase","letterSpacing":".06em","marginBottom":"12px","textAlign":"center"}),
                html.Div([
                    html.I(className="ti ti-arrow-up",
                           style={"color":"#10B981","fontSize":"14px","marginRight":"6px"}),
                    html.Span("Ingresos", style={"fontSize":"11px","color":"#374151","flex":"1"}),
                    html.Span(_fmt(total_rev), style={"fontSize":"13px","fontWeight":"700","color":"#10B981"}),
                ], style={"display":"flex","alignItems":"center","marginBottom":"8px"}),
                html.Div([
                    html.I(className="ti ti-arrow-down",
                           style={"color":"#DC2626","fontSize":"14px","marginRight":"6px"}),
                    html.Span("Gastos", style={"fontSize":"11px","color":"#374151","flex":"1"}),
                    html.Span(_fmt(total_exp), style={"fontSize":"13px","fontWeight":"700","color":"#DC2626"}),
                ], style={"display":"flex","alignItems":"center","marginBottom":"8px"}),
                html.Div(style={"borderTop":"2px solid #E5E7EB","margin":"10px 0"}),
                html.Div([
                    html.I(className=f"ti ti-{'trending-up' if balance>=0 else 'trending-down'}",
                           style={"color":"#10B981" if balance>=0 else "#DC2626","fontSize":"14px","marginRight":"6px"}),
                    html.Span("Balance", style={"fontSize":"11px","color":"#374151","flex":"1"}),
                    html.Span(("+" if balance>=0 else "")+_fmt(balance),
                              style={"fontSize":"18px","fontWeight":"900",
                                     "color":"#10B981" if balance>=0 else "#DC2626"}),
                ], style={"display":"flex","alignItems":"center"}),
                html.P("superávit" if balance>=0 else "déficit",
                       style={"fontSize":"10px","color":"#9CA3AF","margin":"4px 0 0","textAlign":"right"}),
            ], style={"background":"#fff","border":"1px solid #E5E7EB","borderRadius":"10px","padding":"16px",
                      "height":"100%","display":"flex","flexDirection":"column","justifyContent":"center"}), md=4),
        ], className="g-3 mb-3"),

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
                    style={"background": "#FFD600", "color": "#fff", "border": "none", "borderRadius": "7px",
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
            dbc.Col(_fkpi("ti-alert-triangle","En riesgo ALTO",""+str(muy_alto+alto),"jugadores","#9F1239","#FFD600"),md=3),
            dbc.Col(_fkpi("ti-door-exit","Salidas libres jun-2026",str(len(libres)),"contratos expiran","#78350F","#F59E0B"),md=3),
            dbc.Col(_fkpi("ti-building","Interés confirmado",str(sum(1 for n in news if n.get("interest_level")=="confirmed")),"clubes con oferta real","#1D4ED8","#3B82F6"),md=3),
            dbc.Col(_fkpi("ti-eye","Sondeados",str(sum(1 for n in news if n.get("interest_level")=="sounded")),"sin oferta formal","#374151","#6B7280"),md=3),
        ], className="g-3 mb-3"),

        # Salidas libres
        html.Div([
            html.Div([html.I(className="ti ti-user-x",style={"color":"#FFD600","marginRight":"8px","fontSize":"16px"}),
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
                        html.Th("Cláusula (M€) — editable", style={**HEAD,"color":"#FFD600"}),
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

            # Tarjetas de riesgo dinámicas + gráfico lateral
        dbc.Row([
            dbc.Col(html.Div(id="risk-cards-container"), md=8),
            dbc.Col(html.Div([
                html.P("Distribución de riesgo", style={"fontSize":"10px","fontWeight":"700","color":"#9CA3AF",
                    "textTransform":"uppercase","letterSpacing":".06em","margin":"0 0 6px","textAlign":"center"}),
                dcc.Graph(
                    figure=apply_theme(go.Figure(go.Bar(
                        x=[muy_alto, alto,
                           sum(1 for p in activos if _clause_risk_score(p,news)[1]=="MEDIO"),
                           sum(1 for p in activos if _clause_risk_score(p,news)[1]=="BAJO")],
                        y=["MUY ALTO","ALTO","MEDIO","BAJO"],
                        orientation="h",
                        marker=dict(color=["#991B1B","#DC2626","#F59E0B","#10B981"]),
                        text=[muy_alto, alto,
                              sum(1 for p in activos if _clause_risk_score(p,news)[1]=="MEDIO"),
                              sum(1 for p in activos if _clause_risk_score(p,news)[1]=="BAJO")],
                        textposition="inside",
                        textfont=dict(size=10, color="#fff"),
                        hovertemplate="<b>%{y}</b>: %{x} jugadores<extra></extra>",
                    )), height=180, transparent=True, compact=True) or go.Figure(),
                    config={"displayModeBar":False},
                ),
                html.Div(style={"borderTop":"1px solid #F3F4F6","margin":"10px 0"}),
                html.P("Interés externo", style={"fontSize":"10px","fontWeight":"700","color":"#9CA3AF",
                    "textTransform":"uppercase","letterSpacing":".06em","margin":"0 0 8px","textAlign":"center"}),
                *[html.Div([
                    html.Strong(n["player"].split()[-1],
                               style={"fontSize":"11px","color":"#1A1A2E","flex":"1"}),
                    html.Span(n.get("note","")[:28],
                             style={"fontSize":"10px","color":"#6B7280","fontStyle":"italic","flex":"2"}),
                    html.Span("●", style={"color":"#DC2626" if n.get("interest_level")=="confirmed" else "#F59E0B",
                                         "marginLeft":"6px","fontSize":"8px"}),
                ], style={"display":"flex","alignItems":"center","padding":"4px 0","borderBottom":"1px solid #F9FAFB"})
                  for n in news[:6]],
            ], style={"background":"#F9FAFB","border":"1px solid #E5E7EB","borderRadius":"10px","padding":"14px"}), md=4),
        ], className="g-3"),
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
                html.Div([html.I(className="ti ti-arrow-up-right",style={"color":"#FFD600","marginRight":"8px","fontSize":"16px"}),
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


# ── Tab 5: Simulador de Fichajes ────────────────────────────────────────────
def tab_simulador_fichajes(fin):
    players     = fin["player_salaries"]
    player_opts = [
        {"label": f"{p['name']}  ({p['position']}) · {_fmt(p['salary_annual'])}/año", "value": p["name"]}
        for p in sorted(players, key=lambda x: -x["salary_annual"])
    ]
    master_opts = _load_master_opts(['Spain_Primera_Division','Spain_Segunda_Division',
                                     'England_Premier_League','Germany_Bundesliga',
                                     'Italy_Serie_A','France_Ligue_1','Netherlands_Eredivisie',
                                     'Portugal_Primeira_Liga'])
    inp  = {"width":"100%","padding":"8px 10px","border":"1px solid #E5E7EB","borderRadius":"7px","fontSize":"13px"}
    lbl  = {"fontSize":"11px","color":"#6B7280","marginBottom":"4px","display":"block","fontWeight":"600"}
    btn  = {"background":"#FFD600","color":"#0D0D0D","border":"none","borderRadius":"8px",
            "padding":"12px 28px","fontSize":"14px","fontWeight":"700","cursor":"pointer",
            "width":"100%","marginTop":"16px","letterSpacing":".02em"}
    card = {"background":"#fff","border":"1px solid #E5E7EB","borderRadius":"12px","padding":"18px 20px","height":"100%"}

    return html.Div([
        html.Div([
            html.I(className="ti ti-sparkles", style={"marginRight":"10px","color":"#7C3AED","fontSize":"16px"}),
            html.Span(
                "Analiza si una venta o compra es buena operación para el Rayo. "
                "Introduce los datos y pulsa Analizar — recibirás un score 0-100 con el "
                "razonamiento detallado basado en datos reales del jugador.",
                style={"fontSize":"12px","color":"#5B21B6"}),
        ], style={"background":"#F5F3FF","border":"1px solid #DDD6FE","borderRadius":"10px",
                  "padding":"12px 16px","marginBottom":"20px","display":"flex","alignItems":"center"}),

        dbc.Row([
            dbc.Col(html.Div([
                html.Div([
                    html.I(className="ti ti-arrow-up-right",
                           style={"color":"#B8960C","marginRight":"8px","fontSize":"18px"}),
                    html.Span("Simular Venta",
                              style={"fontSize":"15px","fontWeight":"700","color":"#1A1A2E"}),
                ], style={"display":"flex","alignItems":"center","marginBottom":"14px"}),
                html.Span("Jugador del Rayo que sale", style=lbl),
                dcc.Dropdown(player_opts, multi=False, id="fich-sell-player",
                             placeholder="Selecciona un jugador...", style={"marginBottom":"12px"}),
                html.Div(id="fich-sell-card", style={"marginBottom":"10px"}),
                html.Span("Ingreso acordado por la venta (M€)", style=lbl),
                dcc.Input(id="fich-sell-price", type="number", min=0, step=0.5,
                          placeholder="Ej: 8.5", style=inp),
                html.Div(id="fich-sell-hint", style={"marginTop":"6px"}),
            ], style=card), md=5),

            dbc.Col(html.Div([
                html.Div([
                    html.I(className="ti ti-arrow-down-left",
                           style={"color":"#10B981","marginRight":"8px","fontSize":"18px"}),
                    html.Span("Simular Compra",
                              style={"fontSize":"15px","fontWeight":"700","color":"#1A1A2E"}),
                ], style={"display":"flex","alignItems":"center","marginBottom":"14px"}),
                html.Span("Ligas donde buscar", style=lbl),
                dcc.Dropdown(SIM_LEAGUES, multi=True, id="fich-buy-leagues",
                             value=["Spain_Primera_Division","Spain_Segunda_Division"],
                             placeholder="Elige ligas...", style={"marginBottom":"8px"}),
                html.Span("Jugador a fichar", style=lbl),
                dcc.Dropdown(options=master_opts, id="fich-buy-player",
                             placeholder="Escribe un nombre...", searchable=True, clearable=True,
                             style={"marginBottom":"12px"}),
                html.Div(id="fich-buy-card", style={"marginBottom":"10px"}),
                html.Span("Traspaso acordado (M€)  — 0 si es libre", style=lbl),
                dcc.Input(id="fich-buy-fee", type="number", min=0, step=0.5,
                          placeholder="Ej: 12.0", style=inp),
                html.Div(id="fich-buy-hint", style={"marginTop":"6px"}),
            ], style=card), md=5),

        ], className="g-3"),

        # ── Botón centrado + resultado a ancho completo ───────────────────────
        html.Div(
            html.Button(
                [html.I(className="ti ti-search", style={"marginRight":"10px","fontSize":"16px"}),
                 "Analizar operación"],
                id="fich-analyze-btn", n_clicks=0,
                style={"background":"#1A1A2E","color":"#fff","border":"none","borderRadius":"10px",
                       "padding":"13px 36px","fontSize":"15px","fontWeight":"700","cursor":"pointer",
                       "letterSpacing":".02em","display":"block","margin":"20px auto 0"}),
            style={"textAlign":"center"}
        ),
        dcc.Loading(html.Div(id="fich-result", style={"marginTop":"20px"}),
                    type="dot", color="#7C3AED"),
    ])

# ── Layout ────────────────────────────────────────────────────────────────────
def layout(**_params):
    fin = _load_finances()
    scl = fin.get("squad_cost_limit", {})
    total_sal = sum(p.get("salary_annual",0) for p in fin.get("player_salaries",[]))
    limit     = scl.get("limit_eur", 0)
    pct       = round(total_sal / limit * 100) if limit else 0
    budget    = fin.get("transfer_budget", {}).get("net_eur", 0)

    _tab_style = {"fontSize":"13px","fontWeight":"500","padding":"9px 16px"}
    _tab_sel   = lambda c: {"fontSize":"13px","fontWeight":"700","padding":"9px 16px",
                             "borderTop":f"3px solid {c}","color":c}

    return html.Div([

        # ── Hero ──────────────────────────────────────────────────────────────
        html.Div([
            html.Div([
                html.Div([html.I(className="ti ti-coins",
                           style={"fontSize":"28px","color":"#fff"})],
                    style={"background":"rgba(255,255,255,.15)","borderRadius":"12px",
                           "padding":"10px","marginRight":"18px","flexShrink":"0"}),
                html.Div([
                    html.Div("DIRECCIÓN DEPORTIVA", style={"fontSize":"9px","fontWeight":"700",
                        "color":"rgba(255,255,255,.55)","letterSpacing":".14em","marginBottom":"3px"}),
                    html.H1("Finanzas del Club", style={"fontSize":"22px","fontWeight":"900",
                        "color":"#fff","margin":"0 0 2px"}),
                    html.Div("Salarios · Presupuesto · Riesgo de cláusulas · Simulador · 2026/27",
                        style={"fontSize":"10px","color":"rgba(255,255,255,.5)"}),
                ]),
            ], style={"display":"flex","alignItems":"center","flex":"1"}),
            html.Div([
                *[html.Div([
                    html.Div(v, style={"fontSize":"22px","fontWeight":"900","color":"#fff","lineHeight":"1"}),
                    html.Div(l, style={"fontSize":"9px","color":"rgba(255,255,255,.55)","fontWeight":"600","marginTop":"2px"}),
                ], style={"textAlign":"center","padding":"0 16px","borderRight":s})
                  for v,l,s in [
                    (f"{total_sal/1e6:.1f}M€", "masa salarial", "1px solid rgba(255,255,255,.15)"),
                    (f"{pct}%", "del límite FFP", "1px solid rgba(255,255,255,.15)"),
                    (f"{budget/1e6:.0f}M€", "presupuesto neto", "none"),
                ]],
            ], style={"display":"flex","alignItems":"center","flexShrink":"0"}),
        ], style={"background":"linear-gradient(135deg,#064E3B 0%,#065F46 50%,#047857 100%)",
                  "borderRadius":"18px","padding":"20px 26px","marginBottom":"18px",
                  "display":"flex","justifyContent":"space-between","alignItems":"center",
                  "boxShadow":"0 8px 24px rgba(6,78,59,.25)"}),

        dcc.Tabs(id="fin-tabs", value="salarios",
            style={"marginBottom":"16px","background":"#fff","borderRadius":"14px",
                   "border":"1px solid #E5E7EB","padding":"4px",
                   "boxShadow":"0 2px 8px rgba(0,0,0,.05)"},
            colors={"border":"transparent","primary":"#059669","background":"transparent"},
            children=[
                dcc.Tab(label="💶  Salarios",            value="salarios",
                        style=_tab_style, selected_style=_tab_sel("#059669")),
                dcc.Tab(label="📊  Presupuesto",         value="presupuesto",
                        style=_tab_style, selected_style=_tab_sel("#059669")),
                dcc.Tab(label="🎯  Riesgo cláusulas",    value="riesgo",
                        style=_tab_style, selected_style=_tab_sel("#059669")),
                dcc.Tab(label="🔀  Simulador Económico", value="simulador",
                        style=_tab_style, selected_style=_tab_sel("#059669")),
                dcc.Tab(label="📋  Simulador Fichajes",  value="simulador-fichajes",
                        style=_tab_style, selected_style=_tab_sel("#7C3AED")),
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
    diff_color = "#DC2626" if diff > 0 else "#059669"
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
                      style={"fontSize":"12px","color":"#DC2626" if pct>90 else
                             ("#F59E0B" if pct>75 else "#374151")}),
        ], style={"display":"flex","alignItems":"center","flexWrap":"wrap","gap":"4px"}),
        html.Div(
            html.Div(style={"height":"100%","width":f"{min(pct,100):.1f}%",
                "background":"#10B981" if pct<75 else ("#F59E0B" if pct<90 else "#FFD600"),
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



# ── Helpers de evaluación de operaciones de mercado ─────────────────────────

def _get_role_info(name: str) -> dict:
    """Devuelve lateral_pos y role_type (código + label) para un jugador."""
    try:
        from src.utils.lateral_position import (
            build_lateral_map, LATERAL_LABELS, ROLE_TYPE_LABELS, role_type_label
        )
        import unicodedata as _ud, json as _json
        def _norm(x):
            return _ud.normalize("NFKD", str(x)).encode("ascii","ignore").decode().lower().strip()

        lat_code = role_code = None

        # 1. Lateral map (inferido de datos)
        enriched = PROC_DIR / "player_seasons_enriched.parquet"
        master   = PROC_DIR / "master_players.parquet"
        if enriched.exists() and master.exists():
            lm = build_lateral_map(enriched, master)
            row = lm[lm["name"].astype(str).apply(_norm) == _norm(name)]
            if not row.empty:
                lat_code  = row.iloc[0].get("lateral_pos")
                role_code = row.iloc[0].get("role_type")

        # 2. Override manual (prioridad)
        ov_path = PROC_DIR / "player_overrides.json"
        if ov_path.exists():
            try:
                ov = _json.load(open(ov_path, encoding="utf-8"))
                entry = ov.get(_norm(name), {})
                if entry.get("lateral_pos"): lat_code  = entry["lateral_pos"]
                if entry.get("role_type"):   role_code = entry["role_type"]
            except Exception:
                pass

        return {
            "lat_code":   lat_code,
            "role_code":  role_code,
            "lat_label":  LATERAL_LABELS.get(lat_code, "") if lat_code else "",
            "role_label": role_type_label(role_code) if role_code else "",
        }
    except Exception:
        return {"lat_code": None, "role_code": None, "lat_label": "", "role_label": ""}


def _get_rayo_overlap(lat_code: str | None, role_code: str | None) -> list[dict]:
    """Jugadores del Rayo con la misma posición lateral y/o tipo de rol."""
    if not lat_code and not role_code:
        return []
    try:
        from src.utils.lateral_position import (
            build_lateral_map, LATERAL_LABELS, role_type_label
        )
        import unicodedata as _ud, yaml as _yaml
        def _norm(x):
            return _ud.normalize("NFKD", str(x)).encode("ascii","ignore").decode().lower().strip()

        enriched = PROC_DIR / "player_seasons_enriched.parquet"
        master   = PROC_DIR / "master_players.parquet"
        if not (enriched.exists() and master.exists()):
            return []

        lm = build_lateral_map(enriched, master)

        # Plantilla Rayo actual
        cp_path = ROOT / "config" / "club_profile.yaml"
        with open(cp_path, encoding="utf-8") as f:
            cp = _yaml.safe_load(f)
        rayo_names = set()
        for section in cp.get("squad_2025_26", {}).values():
            if isinstance(section, list):
                for p in section:
                    rayo_names.add(_norm(p["name"]))

        # Dos niveles: por posicion lateral y por perfil exacto (pos+rol)
        lm["_nn"] = lm["name"].astype(str).apply(_norm)
        rayo_lm = lm[lm["_nn"].isin(rayo_names)]

        def _row_dict(r):
            return {
                "name":       r["name"],
                "lat_label":  LATERAL_LABELS.get(r.get("lateral_pos"), "") if r.get("lateral_pos") else "",
                "role_label": role_type_label(r.get("role_type")),
            }

        by_position = []
        if lat_code:
            for _, r in rayo_lm[rayo_lm["lateral_pos"] == lat_code].iterrows():
                by_position.append(_row_dict(r))

        by_profile = []
        if lat_code and role_code:
            mask = (rayo_lm["lateral_pos"] == lat_code) & (rayo_lm["role_type"] == role_code)
            for _, r in rayo_lm[mask].iterrows():
                by_profile.append(_row_dict(r))

        return {"by_position": by_position, "by_profile": by_profile}
    except Exception:
        return {"by_position": [], "by_profile": []}


def _get_player_stats(name: str) -> dict:
    """Stats reales del jugador — TM market data + enriched para minutos/goles."""
    out = {"name": name, "mv": MV_MAP.get(name), "minutes": 0, "goals": 0,
           "assists": 0, "age": None, "position": None, "league": None, "team": None}
    try:
        # ── 1. Fuente primaria: src.utils.market.get_value (TM + club_profile) ──
        try:
            from src.utils.market import get_value as _gv
            tm = _gv(name)
            if tm:
                out["mv"]       = float(tm["value_eur"]) if tm.get("value_eur") else out["mv"]
                out["age"]      = int(float(tm["age"])) if tm.get("age") else None
                out["position"] = str(tm.get("position") or "")
                # team viene siempre del enriched (último equipo donde jugó realmente)
        except Exception:
            pass

        # ── 2. Stats de juego: player_seasons_enriched (temporada más reciente) ─
        s    = settings()
        proc = Path(s["paths"]["data_processed"])
        enr_path = proc / "player_seasons_enriched.parquet"
        if enr_path.exists():
            enr = pd.read_parquet(enr_path)
            _SO = {"2025-2026":6,"2025/2026":6,"2025":5,"2024-2025":4,"2024/2025":4,"2024":4,"2023-2024":3}
            enr["_ord"] = enr["season"].astype(str).map(_SO).fillna(0)
            # Ordenar: temporada desc, luego minutos desc (desempata jugadores con 2 equipos)
            enr = enr.sort_values(["_ord","minutes"], ascending=[False,False])
            # Match exacto primero, luego por apellido
            surname = name.strip().split()[-1].lower() if name.strip() else ""
            mask = enr["name"].astype(str).str.lower() == name.lower()
            if not mask.any() and surname:
                mask = enr["name"].astype(str).str.lower().str.endswith(surname)
            rows = enr[mask]
            if not rows.empty:
                p = rows.iloc[0]
                out["minutes"] = int(float(p["minutes"])) if pd.notna(p.get("minutes")) else 0
                out["goals"]   = int(float(p["goals"]))   if pd.notna(p.get("goals"))   else 0
                _ast = p.get("goal_assists") or p.get("assists") or 0
                out["assists"] = int(float(_ast)) if pd.notna(_ast) else 0
                # Equipo y liga: siempre del enriched (refleja dónde jugó realmente)
                out["team"]   = str(p.get("team","") or "")
                out["league"] = str(p.get("league","") or "")
                if not out["position"]:
                    out["position"] = str(p.get("position_primary","") or p.get("position","") or "")
                if out["age"] is None and pd.notna(p.get("age")):
                    out["age"] = int(float(p["age"]))

        # ── 3. Fallback finances para jugadores del Rayo ─────────────────────
        if out["age"] is None or not out["position"]:
            for fp in _load_finances().get("player_salaries", []):
                if fp["name"].lower() == name.lower():
                    if out["age"] is None:   out["age"]      = fp.get("age")
                    if not out["position"]:  out["position"] = fp.get("position","")
                    if not out["team"]:      out["team"]     = "Rayo Vallecano"
                    break
    except Exception:
        pass
    return out


def _get_squad_needs_roles() -> tuple:
    """Devuelve (missing_roles, reinforce_roles) desde las necesidades reales de plantilla."""
    try:
        from src.squad.needs import squad_decisions as _sd
        import json as _json, yaml as _yaml
        s = settings()
        sp = Path(s["paths"]["data_processed"]) / "squad_current.json"
        cp = Path(s["paths"]["data_processed"]) / "club_profile.yaml"
        squad = _json.load(open(sp, encoding="utf-8")).get("squad", []) if sp.exists() else []
        needs = _yaml.safe_load(open(cp, encoding="utf-8")).get("squad_needs", {}) if cp.exists() else {}
        dec = _sd(squad, needs)
        missing   = [it.get("role", "") for it in dec.get("fichar",   [])]
        reinforce = [it.get("role", "") for it in dec.get("reforzar", [])]
        return missing, reinforce
    except Exception:
        return [], []


def _squad_pos_count(position: str) -> int:
    """Cuántos jugadores del Rayo hay en esa posición."""
    try:
        players = _load_finances().get("player_salaries", [])
        return sum(1 for p in players
                   if position.upper()[:2] in str(p.get("position", "")).upper())
    except Exception:
        return 0


def _evaluate_sale(player_name: str, income_eur: float, pmap: dict) -> dict:
    """Score 0-100 de la calidad de la venta, con razones y fórmulas detalladas."""
    stats   = _get_player_stats(player_name)
    pdata   = pmap.get(player_name, {})
    mv      = stats["mv"] or (pdata.get("salary_annual", 500_000) * 8)
    minutes = stats["minutes"] or 0
    goals   = stats["goals"]   or 0
    assists = stats["assists"] or 0
    age     = stats["age"]     or 27
    income  = income_eur or 0
    score, reasons = 50, []
    g90 = round((goals + assists) / (minutes / 90), 2) if minutes > 90 else 0

    # Factor 1: Precio vs valor TM — peso 40 pts
    if mv > 0 and income > 0:
        r = income / mv
        formula1 = f"Ingreso {_fmt(income)} ÷ Valor TM {_fmt(mv)} = {r:.2f}×  [tramos: ≥1.5×→+40 · ≥1.2×→+28 · ≥0.9×→+12 · ≥0.7×→−8 · ≥0.5×→−22 · <0.5×→−38]"
        if   r >= 1.50: pts, tag = 40, "Precio EXCEPCIONAL — muy por encima del valor de mercado"
        elif r >= 1.20: pts, tag = 28, "Muy buen precio — claramente por encima del valor de mercado"
        elif r >= 0.90: pts, tag = 12, "Precio de mercado — operación justa"
        elif r >= 0.70: pts, tag = -8, f"Precio bajo — dejamos {_fmt(mv-income)} sobre la mesa"
        elif r >= 0.50: pts, tag = -22, f"Malventa — perdemos {_fmt(mv-income)} respecto al valor real"
        else:           pts, tag = -38, f"MALVENTA GRAVE — perdemos {_fmt(mv-income)} respecto al valor real"
    elif income == 0:
        formula1 = "Ingreso = 0€ → sin recuperación económica"
        pts, tag = -15, "Sin ingreso registrado — ¿cesión gratuita?"
    else:
        formula1 = "Valor TM desconocido → ratio no calculable"
        pts, tag = 0, "Valor TM no disponible"
    score += pts; reasons.append(("💰", "Precio de la operación", tag, formula1, pts))

    # Factor 2: Importancia del jugador — peso 28 pts
    formula2 = (f"{minutes} min jugados  ·  {goals} goles + {assists} asistencias = {goals+assists} G+A"
                f"  ·  G+A/90 = ({goals}+{assists}) ÷ ({minutes}/90) = {g90:.2f}"
                f"  [tramos: ≥2500→−25 · ≥1800→−14 · ≥900→+5 · ≥200→+12 · <200→+18]")
    if   minutes >= 2500: pts, tag = -25, f"TITULAR INDISCUTIBLE — {minutes} min, {goals}G+{assists}A ({g90}/90)"
    elif minutes >= 1800: pts, tag = -14, f"Jugador importante — {minutes} min, {goals}G+{assists}A ({g90}/90)"
    elif minutes >= 900:  pts, tag =   5, f"Rotacional — {minutes} min, salida asumible"
    elif minutes >= 200:  pts, tag =  12, f"Suplente con escasos minutos ({minutes} min)"
    else:                 pts, tag =  18, f"Sin protagonismo ({minutes} min) — venta lógica"
    score += pts; reasons.append(("⏱️", "Importancia en el equipo", tag, formula2, pts))

    # Factor 3: Perfil de edad — peso 20 pts
    if   age <= 21: umbral, pts = "≤21 años",  -20
    elif age <= 24: umbral, pts = "22–24 años", -10
    elif age <= 28: umbral, pts = "25–28 años",   5
    elif age <= 31: umbral, pts = "29–31 años",  12
    else:           umbral, pts = ">31 años",    18
    formula3 = (f"Edad = {age} años → tramo '{umbral}' → {'+' if pts>=0 else ''}{pts} pts"
                f"  [tramos: ≤21→−20 · 22-24→−10 · 25-28→+5 · 29-31→+12 · >31→+18]")
    tag3_map = {-20:"Muy joven — se vende potencial proyectable",
                -10:"Joven en desarrollo — venta discutible",
                 5: "Edad óptima — buen momento económico para vender",
                12: "Veterano — se maximiza el valor residual ahora",
                18: "Jugador mayor — vender ahora es lo correcto"}
    score += pts; reasons.append(("📅", "Perfil de edad", tag3_map[pts], formula3, pts))

    # Factor 4: Impacto en plantilla — cobertura por posicion y por perfil exacto
    missing, reinforce = _get_squad_needs_roles()
    pos = stats.get("position") or "?"
    pos_count = _squad_pos_count(pos[:2] if pos else "")
    in_missing   = any(pos.lower() in r.lower() or r.lower() in pos.lower() for r in missing)
    in_reinforce = any(pos.lower() in r.lower() or r.lower() in pos.lower() for r in reinforce)
    role_info   = _get_role_info(player_name)
    overlap     = _get_rayo_overlap(role_info["lat_code"], role_info["role_code"])
    n_pos       = len(overlap["by_position"])   # jugadores Rayo misma posicion lateral
    n_prof      = len(overlap["by_profile"])    # jugadores Rayo mismo perfil exacto (pos+rol)
    lat_lbl     = role_info["lat_label"] or pos
    role_lbl    = role_info["role_label"]
    formula4 = (f"Posicion '{lat_lbl}': {n_pos} jugadores Rayo  ·  "
                f"Perfil exacto '{lat_lbl}+{role_lbl}': {n_prof} jugadores Rayo  ·  "
                f"En lista 'fichar': {'Si' if in_missing else 'No'}  ·  "
                f"En lista 'reforzar': {'Si' if in_reinforce else 'No'}  "
                f"[Necesidad prio+perfil unico→-22 · Necesidad prio→-12 · Posicion cubierta+perfil repetido→+15 · Posicion cubierta→+8]")
    if in_missing and n_prof == 0:
        pts, tag = -22, f"Posicion '{lat_lbl}' NECESARIA y perfil '{role_lbl}' UNICO — venta muy arriesgada"
    elif in_missing:
        pts, tag = -12, f"Posicion '{lat_lbl}' es necesidad prioritaria — la venta la agrava"
    elif in_reinforce and n_prof == 0:
        pts, tag = -8, f"Posicion en lista de refuerzo y perfil unico — salida no ideal"
    elif in_reinforce:
        pts, tag = -3, f"Posicion en lista de refuerzo pero perfil cubierto ({n_prof} jugadores similares)"
    elif n_prof >= 2:
        pts, tag = 15, f"Perfil '{lat_lbl}+{role_lbl}' cubierto por {n_prof} jugadores — venta asumible"
    elif n_pos >= 3:
        pts, tag = 8, f"Posicion '{lat_lbl}' cubierta ({n_pos} jugadores) — venta sin urgencia"
    else:
        pts, tag = 0, f"Posicion '{lat_lbl}' aceptablemente cubierta — impacto moderado"
    score += pts; reasons.append(("🎯", "Impacto en plantilla", tag, formula4, pts))

    score = max(0, min(100, score))
    if   score >= 80: veredicto = "EXCELENTE OPERACIÓN"
    elif score >= 65: veredicto = "BUENA OPERACIÓN"
    elif score >= 50: veredicto = "OPERACIÓN ACEPTABLE"
    elif score >= 35: veredicto = "OPERACIÓN DISCUTIBLE"
    else:             veredicto = "MALA OPERACIÓN"
    raw = {"mv": mv, "income": income, "minutes": minutes, "goals": goals,
           "assists": assists, "g90": g90, "age": age, "position": pos,
           "ratio_precio": round(income/mv, 2) if mv and income else None}
    return {"score": score, "veredicto": veredicto, "reasons": reasons, "tipo": "venta", "raw": raw}


def _evaluate_buy(player_name: str, fee_eur: float, _salary_eur: float) -> dict:
    """Score 0-100 de la calidad del fichaje, con razones y fórmulas detalladas."""
    stats   = _get_player_stats(player_name)
    mv      = stats["mv"]
    minutes = stats["minutes"] or 0
    goals   = stats["goals"]   or 0
    assists = stats["assists"] or 0
    age     = stats["age"]     or 25
    fee     = fee_eur or 0
    score, reasons = 50, []
    g90 = round((goals + assists) / (minutes / 90), 2) if minutes > 90 else 0

    # Factor 1: Precio pagado vs valor TM — peso 40 pts
    if mv and mv > 0:
        if fee == 0:
            r = 0.0
            formula1 = f"Fee = 0€ (libre/cedido) · Valor TM = {_fmt(mv)} → ahorro íntegro del traspaso"
            pts, tag = 35, f"Sin coste de traspaso — valor TM {_fmt(mv)} (libre o cedido)"
        else:
            r = fee / mv
            formula1 = (f"Fee {_fmt(fee)} ÷ Valor TM {_fmt(mv)} = {r:.2f}×"
                        f"  [tramos: ≤0.5×→+40 · ≤0.75×→+28 · ≤1.05×→+12 · ≤1.3×→−10 · ≤1.7×→−25 · >1.7×→−38]")
            if   r <= 0.50: pts, tag = 40, f"CHOLLO ABSOLUTO — ahorramos {_fmt(mv-fee)} vs valor real"
            elif r <= 0.75: pts, tag = 28, f"Muy buen precio — ahorramos {_fmt(mv-fee)} vs valor TM"
            elif r <= 1.05: pts, tag = 12, f"Precio de mercado — operación justa"
            elif r <= 1.30: pts, tag = -10, f"Precio algo alto — pagamos {_fmt(fee-mv)} de más"
            elif r <= 1.70: pts, tag = -25, f"Sobreprecio — pagamos {_fmt(fee-mv)} de más"
            else:           pts, tag = -38, f"SOBREPRECIO GRAVE — pagamos {_fmt(fee-mv)} de más"
    else:
        r = None
        formula1 = "Valor TM desconocido → ratio no calculable"
        pts, tag = 0, "Valor TM no disponible — ratio precio/mercado no calculable"
    score += pts; reasons.append(("💰", "Precio de la operación", tag, formula1, pts))

    # Factor 2: Rendimiento real del jugador — peso 22 pts
    formula2 = (f"{minutes} min · {goals} goles + {assists} asistencias"
                f"  ·  G+A/90 = ({goals}+{assists}) ÷ ({minutes}/90) = {g90:.2f}"
                f"  [tramos: ≥2500→+22 · ≥1800→+14 · ≥900→+5 · <900→−8]")
    if   minutes >= 2500: pts, tag = 22, f"Alto rendimiento — {minutes} min, {goals}G+{assists}A ({g90}/90)"
    elif minutes >= 1800: pts, tag = 14, f"Buen rendimiento — {minutes} min, {goals}G+{assists}A ({g90}/90)"
    elif minutes >= 900:  pts, tag =  5, f"Rendimiento moderado — {minutes} min, potencial a confirmar"
    else:                 pts, tag = -8, f"Pocos datos ({minutes} min) — riesgo deportivo alto"
    score += pts; reasons.append(("📊", "Rendimiento deportivo", tag, formula2, pts))

    # Factor 3: Necesidad de plantilla — cobertura por posicion y por perfil exacto
    missing, reinforce = _get_squad_needs_roles()
    pos       = stats.get("position") or "?"
    pos_count = _squad_pos_count(pos[:2] if pos else "")
    in_miss = any(pos.lower() in r.lower() or r.lower() in pos.lower() for r in missing)
    in_rein = any(pos.lower() in r.lower() or r.lower() in pos.lower() for r in reinforce)
    role_info  = _get_role_info(player_name)
    overlap    = _get_rayo_overlap(role_info["lat_code"], role_info["role_code"])
    n_pos      = len(overlap["by_position"])   # jugadores Rayo misma posicion lateral
    n_prof     = len(overlap["by_profile"])    # jugadores Rayo mismo perfil exacto (pos+rol)
    lat_lbl    = role_info["lat_label"] or pos
    role_lbl   = role_info["role_label"]
    formula3 = (f"Posicion '{lat_lbl}': {n_pos} jugadores Rayo  ·  "
                f"Perfil exacto '{lat_lbl}+{role_lbl}': {n_prof} jugadores Rayo  ·  "
                f"Necesidad 'fichar': {'Si' if in_miss else 'No'}  ·  "
                f"Necesidad 'reforzar': {'Si' if in_rein else 'No'}  "
                f"[Necesidad+hueco perfil→+28 · Necesidad→+20 · Refuerzo+hueco→+12 · Perfil cubierto(2+)→-20 · Posicion cubierta→-10]")
    if in_miss and n_prof == 0:
        pts, tag = 28, f"NECESIDAD PRIORITARIA y perfil '{lat_lbl}+{role_lbl}' SIN cubrir — fichaje ideal"
    elif in_miss:
        pts, tag = 20, f"NECESIDAD PRIORITARIA aunque el perfil ya lo tienen {n_prof} jugadores"
    elif in_rein and n_prof == 0:
        pts, tag = 12, f"Refuerzo necesario y perfil unico — aporta algo diferente"
    elif n_prof >= 2:
        pts, tag = -20, f"Perfil '{lat_lbl}+{role_lbl}' YA cubierto por {n_prof} jugadores — fichaje redundante"
    elif n_prof == 1:
        pts, tag = -8, f"Perfil similar ya cubierto por 1 jugador — solapamiento moderado"
    elif n_pos >= 3:
        pts, tag = -10, f"Posicion '{lat_lbl}' ya tiene {n_pos} jugadores aunque el estilo difiere"
    else:
        pts, tag = -5, f"Posicion '{lat_lbl}' no es prioridad declarada"
    score += pts; reasons.append(("🎯", "Necesidad de plantilla", tag, formula3, pts))

    # Factor 4: Edad y proyección — peso 15 pts
    if   age <= 20: umbral, pts = "≤20 años",  13
    elif age <= 24: umbral, pts = "21–24 años", 15
    elif age <= 27: umbral, pts = "25–27 años",  8
    elif age <= 30: umbral, pts = "28–30 años",  0
    else:           umbral, pts = ">30 años",   -12
    formula4 = (f"Edad = {age} años → tramo '{umbral}' → {'+' if pts>=0 else ''}{pts} pts"
                f"  [tramos: ≤20→+13 · 21-24→+15 · 25-27→+8 · 28-30→0 · >30→−12]")
    tag4_map = {13:"Muy joven — alta proyección, apuesta de futuro",
                15:"Joven con proyección — perfil ideal para el Rayo",
                 8:"Edad óptima — rendimiento inmediato + valor residual",
                 0:"Veterano — rendimiento sin recorrido de reventa",
               -12:"Jugador mayor — bajo valor de reventa futuro"}
    score += pts; reasons.append(("📅", "Perfil de edad", tag4_map[pts], formula4, pts))

    score = max(0, min(100, score))
    is_opp = score >= 60 and not in_miss
    if   is_opp:      veredicto = "BUENA OPORTUNIDAD DE MERCADO"
    elif score >= 80: veredicto = "FICHAJE EXCELENTE"
    elif score >= 65: veredicto = "BUEN FICHAJE"
    elif score >= 50: veredicto = "FICHAJE ACEPTABLE"
    elif score >= 35: veredicto = "FICHAJE DISCUTIBLE"
    else:             veredicto = "MAL FICHAJE"
    raw = {"mv": mv, "fee": fee, "minutes": minutes, "goals": goals,
           "assists": assists, "g90": g90, "age": age, "position": pos,
           "ratio_precio": round(r, 2) if r is not None else None}
    return {"score": score, "veredicto": veredicto, "reasons": reasons, "tipo": "compra", "raw": raw}


def _render_eval_badge(ev: dict):
    """Renderiza el panel de evaluación con score, datos de partida y desglose por factor."""
    if not ev:
        return html.Div()
    score    = ev["score"]
    veredicto = ev["veredicto"]
    reasons  = ev["reasons"]   # (icon, titulo, tag, formula, pts)
    tipo     = ev["tipo"]
    raw      = ev.get("raw", {})

    if   score >= 75: bg, border, txt = "#F0FDF4","#86EFAC","#166534"
    elif score >= 55: bg, border, txt = "#F0F9FF","#BAE6FD","#0C4A6E"
    elif score >= 40: bg, border, txt = "#FFFBEB","#FDE68A","#92400E"
    else:             bg, border, txt = "#FFF1F2","#FECACA","#9F1239"

    bar_c  = "#10B981" if score>=75 else ("#3B82F6" if score>=55 else ("#F59E0B" if score>=40 else "#DC2626"))
    t_icon = "ti-arrow-up-right" if tipo=="venta" else "ti-arrow-down-left"
    t_label = "ANÁLISIS DE VENTA" if tipo=="venta" else "ANÁLISIS DE COMPRA"

    # Datos de partida en chips
    def chip(label, value, highlight=False):
        return html.Div([
            html.Span(label, style={"fontSize":"9px","color":txt,"opacity":".65","display":"block","marginBottom":"1px"}),
            html.Span(str(value), style={"fontSize":"12px","fontWeight":"700","color":txt}),
        ], style={"background":"rgba(0,0,0,.06)","borderRadius":"8px","padding":"5px 9px",
                  "border":"1px solid rgba(0,0,0,.08)" if not highlight else f"1px solid {txt}",
                  "minWidth":"70px","textAlign":"center"})

    precio_key = "income" if tipo=="venta" else "fee"
    precio_lbl = "Ingreso" if tipo=="venta" else "Fee pagado"
    ratio_raw  = raw.get("ratio_precio")
    ratio_str  = f"{ratio_raw:.2f}×" if ratio_raw is not None else "—"

    raw_chips = html.Div([
        chip("Valor TM",   _fmt(raw.get("mv"))),
        chip(precio_lbl,   _fmt(raw.get(precio_key, 0))),
        chip("Ratio precio", ratio_str, highlight=True),
        chip("Minutos",    f"{raw.get('minutes',0):,}"),
        chip("G+A/90",     raw.get("g90", 0)),
        chip("Edad",       f"{raw.get('age','?')} años"),
        chip("Posición",   raw.get("position","?")),
    ], style={"display":"flex","flexWrap":"wrap","gap":"6px","marginBottom":"14px"})

    return html.Div([
        # Cabecera tipo operación
        html.Div([
            html.I(className=f"ti {t_icon}", style={"fontSize":"14px","color":txt,"marginRight":"7px"}),
            html.Span(t_label, style={"fontSize":"10px","fontWeight":"700","color":txt,
                      "textTransform":"uppercase","letterSpacing":".08em"}),
        ], style={"display":"flex","alignItems":"center","marginBottom":"10px"}),

        # Score + barra + veredicto
        dbc.Row([
            dbc.Col([
                html.Div([
                    html.Span(str(score), style={"fontSize":"52px","fontWeight":"900","color":txt,"lineHeight":"1"}),
                    html.Span("/100", style={"fontSize":"13px","color":txt,"opacity":".6",
                              "marginLeft":"3px","alignSelf":"flex-end","paddingBottom":"8px"}),
                ], style={"display":"flex","alignItems":"flex-end","marginBottom":"6px"}),
                html.Div(html.Div(style={"height":"100%","width":f"{score}%","background":bar_c,"borderRadius":"99px"}),
                         style={"height":"10px","background":"rgba(0,0,0,.1)","borderRadius":"99px",
                                "overflow":"hidden","marginBottom":"8px"}),
                html.Span(veredicto, style={"fontSize":"14px","fontWeight":"800","color":txt}),
            ], md=4),
            dbc.Col([
                html.P("Datos utilizados en el cálculo",
                       style={"fontSize":"9px","fontWeight":"700","color":txt,"opacity":".7",
                              "textTransform":"uppercase","letterSpacing":".08em","margin":"0 0 8px"}),
                raw_chips,
            ], md=8),
        ], className="g-2", style={"marginBottom":"16px"}),

        # Desglose por factor
        html.Div([
            html.P("Desglose por factor",
                   style={"fontSize":"9px","fontWeight":"700","color":txt,"opacity":".7",
                          "textTransform":"uppercase","letterSpacing":".08em","margin":"0 0 8px"}),
            *[html.Div([
                # Fila principal: icono + título + tag + puntos
                html.Div([
                    html.Span(icon, style={"fontSize":"15px","marginRight":"8px","flexShrink":"0"}),
                    html.Div([
                        html.Span(titulo, style={"fontSize":"10px","fontWeight":"700","color":txt,
                                  "textTransform":"uppercase","letterSpacing":".04em","display":"block"}),
                        html.Span(tag, style={"fontSize":"12px","color":txt,"lineHeight":"1.4"}),
                    ], style={"flex":"1"}),
                    html.Span(f"{'+' if pts>0 else ''}{pts}",
                              style={"fontSize":"15px","fontWeight":"900","minWidth":"42px","textAlign":"right",
                                     "color":"#166534" if pts>0 else ("#9F1239" if pts<0 else "#6B7280")}),
                ], style={"display":"flex","alignItems":"flex-start","gap":"4px","marginBottom":"4px"}),
                # Fila fórmula
                html.Div(
                    html.Span(formula, style={"fontSize":"10px","color":txt,"opacity":".65","fontFamily":"monospace",
                              "lineHeight":"1.5","wordBreak":"break-word"}),
                    style={"background":"rgba(0,0,0,.04)","borderRadius":"6px","padding":"5px 8px",
                           "marginLeft":"24px","marginBottom":"2px"}
                ),
              ], style={"padding":"8px 0","borderBottom":"1px solid rgba(0,0,0,.07)"})
              for icon, titulo, tag, formula, pts in reasons],
            # Fila total
            html.Div([
                html.Div([
                    html.Span("TOTAL",
                              style={"fontSize":"11px","fontWeight":"800","color":txt,"flex":"1"}),
                    html.Span(f"{score}/100",
                              style={"fontSize":"13px","fontWeight":"900","color":txt}),
                ], style={"display":"flex","padding":"8px 0"}),
                html.Span(
                    "La escala parte de 50 (operación neutra sin datos) y sube o baja según cada factor.",
                    style={"fontSize":"9px","color":txt,"opacity":".5","fontStyle":"italic"}
                ),
            ]),
        ]),
    ], style={"background":bg,"border":f"2px solid {border}","borderRadius":"14px",
              "padding":"18px 20px","marginBottom":"16px"})

@callback(Output("fin-content","children"), Input("fin-tabs","value"))
def render_tab(tab):
    try:
        fin = _load_finances()
        if tab == "salarios":    return tab_salarios(fin)
        if tab == "presupuesto": return tab_presupuesto(fin)
        if tab == "riesgo":              return tab_riesgo(fin)
        if tab == "simulador-fichajes":  return tab_simulador_fichajes(fin)
        return tab_simulador(fin)
    except Exception as e:
        return html.Div([
            html.Strong("Error: ",style={"color":"#DC2626"}),
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
            return html.P("Master no disponible",style={"fontSize":"12px","color":"#DC2626"}), None, None
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
                    "background":"#FFD600","borderRadius":"99px","padding":"2px 9px","marginLeft":"4px"}),
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
        return html.P(str(e),style={"fontSize":"11px","color":"#DC2626"}), None, None

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
            html.Span(_fmt(pmap[n]["salary_annual"]),style={"fontSize":"11px","color":"#FFD600","marginRight":"8px"}),
            html.Span(f"clausula: {_fmt(pmap[n].get('release_clause'))}",style={"fontSize":"10px","color":"#6B7280"}),
        ], style={"display":"flex","alignItems":"center","padding":"5px 0","borderBottom":"1px solid #F3F4F6"})
        for n in out_players if n in pmap
    ])

@callback(Output("sim-results","children"),
          Input("sim-out","value"),Input("sim-new-salary","value"),
          Input("sim-income","value"),Input("sim-fee","value"),
          Input("sim-contract-years","value"),
          Input("sim-player-search","value"))
def update_sim(out_players, new_salary_m, income_m, fee_m, years, player_name):
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

    # ── Evaluación inteligente de la operación ──────────────────────────────
    eval_badges = []
    try:
        if out_players and income > 0:
            split_income = income / max(len(out_players), 1)
            for pname in out_players:
                eval_badges.append(_render_eval_badge(_evaluate_sale(pname, split_income, pmap)))
        elif out_players:
            for pname in out_players:
                eval_badges.append(_render_eval_badge(_evaluate_sale(pname, 0, pmap)))
        if player_name and (fee > 0 or new_sal > 0):
            eval_badges.append(_render_eval_badge(_evaluate_buy(player_name, fee, new_sal)))
    except Exception as _ex:
        eval_badges.append(html.P(f"Error evaluación: {_ex}", style={"fontSize":"11px","color":"#DC2626"}))

    return html.Div([
        *eval_badges,
        html.Div([
            html.I(className=f"ti {'ti-circle-check' if ok else 'ti-alert-triangle'}",
                   style={"fontSize":"18px","color":"#10B981" if ok else "#DC2626","marginRight":"8px"}),
            html.Span(msg, style={"fontSize":"13px","fontWeight":"700","color":"#166534" if ok else "#9F1239"}),
        ], style={"display":"flex","alignItems":"center","marginBottom":"10px",
                  "background":"#F0FDF4" if ok else "#FFF1F2","padding":"10px 12px","borderRadius":"8px"}),

        dcc.Graph(figure=fig_gauge, config=GRAPH_CONFIG_SIMPLE),
        dcc.Graph(figure=fig_bar,   config=GRAPH_CONFIG_SIMPLE),

        html.P("Desglose de coste",
               style={"fontSize":"10px","fontWeight":"700","color":"#9CA3AF","textTransform":"uppercase","margin":"8px 0 4px"}),
        row("Masa salarial actual",        _fmt(base),      "#374151"),
        row("Ahorro por salidas",          f"-{_fmt(saved)}","#10B981"),
        row("Nuevo salario incorporación", f"+{_fmt(new_sal)}","#B8960C"),
        row(f"Amortiz. ({_fmt(fee)}/{years}a)", f"+{_fmt(fee/years if years else fee)}","#B8960C"),
        row("Coste total plantilla",       _fmt(squad_cost), "#1A1A2E"),
        row("Margen vs límite",            _fmt(headroom),   "#10B981" if headroom>=0 else "#DC2626"),
        html.Div(style={"borderTop":"2px solid #E5E7EB","margin":"8px 0"}),
        html.P("Tesorería",
               style={"fontSize":"10px","fontWeight":"700","color":"#9CA3AF","textTransform":"uppercase","margin":"4px 0"}),
        row("Ingresos ventas",    f"+{_fmt(income)}",           "#10B981"),
        row("Traspaso pagado",    f"-{_fmt(fee)}",              "#B8960C"),
        row("Gasto neto",         _fmt(net_spend),              "#B8960C" if net_spend>0 else "#10B981"),
        row("Presupuesto caja",   _fmt(budget_cash),            "#374151"),
        row("Margen de caja",     _fmt(budget_cash-net_spend),  "#10B981" if cash_ok else "#DC2626"),
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
                                 "color": "#166534" if is_in else "#DC2626", "marginRight": "12px"}),
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


# ── Callbacks Simulador Fichajes ────────────────────────────────────────────

@callback(Output("fich-buy-player","options"), Input("fich-buy-leagues","value"))
def _fich_update_players(leagues):
    if not leagues:
        leagues = ['Spain_Primera_Division','Spain_Segunda_Division']
    return _load_master_opts(leagues)


def _role_badge(label: str, color: str = "#6B7280"):
    """Mini badge de texto con fondo tintado."""
    return html.Span(
        label,
        style={"fontSize":"9px","fontWeight":"700","padding":"2px 7px","borderRadius":"99px",
               "background":color + "20","color":color,"border":f"1px solid {color}50",
               "marginRight":"4px"},
    )


@callback(Output("fich-sell-card","children"), Output("fich-sell-hint","children"),
          Input("fich-sell-player","value"))
def _fich_sell_card(player_name):
    if not player_name:
        return html.Div(), html.Div()
    stats = _get_player_stats(player_name)
    mv, mins, age = stats["mv"], stats["minutes"], stats["age"]
    hint = html.Span(
        f"Valor TM estimado: {_fmt(mv)}  ·  Edad: {age}  ·  Minutos: {mins}",
        style={"fontSize":"10px","color":"#9CA3AF","fontStyle":"italic"}
    ) if mv else html.Div()

    role_info  = _get_role_info(player_name)
    lat_label  = role_info["lat_label"]
    role_label = role_info["role_label"]
    lat_code   = role_info["lat_code"]
    role_code  = role_info["role_code"]
    overlap    = _get_rayo_overlap(lat_code, role_code)
    n_pos      = len(overlap["by_position"])
    n_prof     = len(overlap["by_profile"])

    profile_badges = []
    if lat_label:
        profile_badges.append(_role_badge(lat_label, "#3B82F6"))
    if role_label:
        profile_badges.append(_role_badge(role_label, "#8B5CF6"))

    def _player_row(p):
        parts = [html.Span(p["name"], style={"fontSize":"11px","color":"#374151","marginRight":"5px"})]
        if p.get("role_label"):
            parts.append(_role_badge(p["role_label"], "#8B5CF6"))
        return html.Div(parts, style={"display":"flex","alignItems":"center","marginBottom":"1px"})

    # Desglose por posicion
    if n_pos > 0:
        pos_bg, pos_border = ("#F0FDF4","#A7F3D0") if n_pos >= 2 else ("#FFFBEB","#FDE68A")
        pos_lbl_color = "#166534" if n_pos >= 2 else "#92400E"
        pos_section = html.Div([
            html.Div([
                html.Span(f"Posicion {lat_label or '?'}: ", style={"fontSize":"10px","color":pos_lbl_color,"marginRight":"4px","fontWeight":"600"}),
                html.Span(f"{n_pos} jugador{'es' if n_pos!=1 else ''} del Rayo",
                          style={"fontSize":"10px","color":pos_lbl_color}),
            ], style={"display":"flex","alignItems":"center","marginBottom":"3px"}),
            *[_player_row(p) for p in overlap["by_position"]],
        ], style={"background":pos_bg,"borderRadius":"6px","padding":"5px 8px",
                  "border":f"1px solid {pos_border}","marginTop":"5px"})
    else:
        pos_section = html.Div([
            html.Span(f"Posicion {lat_label or '?'}: ", style={"fontSize":"10px","color":"#6366F1","fontWeight":"600","marginRight":"4px"}),
            html.Span("sin cobertura en el Rayo", style={"fontSize":"10px","color":"#6366F1"}),
        ], style={"display":"flex","alignItems":"center","marginTop":"5px",
                  "background":"#EEF2FF","borderRadius":"6px","padding":"5px 8px","border":"1px solid #C7D2FE"})

    # Desglose por perfil exacto
    if n_prof > 0:
        prof_bg, prof_border = ("#FFF7ED","#FED7AA") if n_prof == 1 else ("#FEF3C7","#FDE68A")
        prof_lbl_color = "#92400E"
        prof_section = html.Div([
            html.Div([
                html.Span(f"Perfil exacto ({lat_label}+{role_label}): ", style={"fontSize":"10px","color":prof_lbl_color,"fontWeight":"600","marginRight":"4px"}),
                html.Span(f"{n_prof} jugador{'es' if n_prof!=1 else ''} similar{'es' if n_prof!=1 else ''}",
                          style={"fontSize":"10px","color":prof_lbl_color}),
            ], style={"display":"flex","alignItems":"center","marginBottom":"3px"}),
            *[_player_row(p) for p in overlap["by_profile"]],
        ], style={"background":prof_bg,"borderRadius":"6px","padding":"5px 8px",
                  "border":f"1px solid {prof_border}","marginTop":"4px"})
    elif lat_code or role_code:
        prof_section = html.Div([
            html.I(className="ti ti-alert-triangle",
                   style={"color":"#DC2626","fontSize":"12px","marginRight":"5px"}),
            html.Span(f"Perfil exacto ({lat_label}+{role_label}): UNICO en la plantilla",
                      style={"fontSize":"10px","color":"#9F1239","fontWeight":"600"}),
        ], style={"display":"flex","alignItems":"center","marginTop":"4px",
                  "background":"#FFF1F2","borderRadius":"6px","padding":"5px 8px","border":"1px solid #FECACA"})
    else:
        prof_section = html.Div()

    header_row = html.Div([
        html.Span(player_name, style={"fontSize":"12px","fontWeight":"700","color":"#1A1A2E","marginRight":"8px"}),
        html.Span(stats.get("position") or "?",
                  style={"fontSize":"9px","fontWeight":"700","padding":"1px 6px",
                         "borderRadius":"99px","background":"#F3F4F6","color":"#374151"}),
        *([html.Span(" → ", style={"color":"#9CA3AF","margin":"0 4px"})] + profile_badges if profile_badges else []),
    ], style={"display":"flex","alignItems":"center"})

    card = html.Div([header_row, pos_section, prof_section],
                    style={"background":"#F9FAFB","border":"1px solid #E5E7EB",
                           "borderRadius":"7px","padding":"8px 10px"})
    return card, hint


@callback(Output("fich-buy-card","children"), Output("fich-buy-hint","children"),
          Input("fich-buy-player","value"))
def _fich_buy_card(player_name):
    if not player_name:
        return html.Div(), html.Div()
    stats  = _get_player_stats(player_name)
    mv     = stats["mv"]
    mins   = stats["minutes"] or 0
    goals  = stats["goals"]   or 0
    asts   = stats["assists"] or 0
    age    = stats["age"]
    g90    = (goals + asts) / (mins / 90) if mins > 90 else 0
    hint = html.Span(
        f"Valor TM: {_fmt(mv)}  ·  Edad: {age}  ·  {mins} min  ·  {goals}G+{asts}A ({g90:.2f}/90)",
        style={"fontSize":"10px","color":"#9CA3AF","fontStyle":"italic"}
    ) if mv else html.Div()

    role_info  = _get_role_info(player_name)
    lat_label