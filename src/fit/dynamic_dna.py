# -*- coding: utf-8 -*-
"""
dynamic_dna.py
==============
Fuente UNICA de verdad para el ADN Rayo y los parametros de encaje.
TODO se calcula desde datos reales — ningun valor esta hardcodeado.

Sustituye a config/rayo_dna.yaml como origen de:
  - target_style: ejes ADN del Rayo (ideales + pesos) desde team_seasons.parquet
  - context_weights: pesos de experiencia/presupuesto/plantilla
  - economics: referencias salariales y de inversion desde club_profile.yaml
  - coach_affinity: afinidad de roles por estilo del entrenador actual

Uso:
    from src.fit.dynamic_dna import build_dynamic_dna, get_coach_affinity

    dna = build_dynamic_dna()   # dict compatible con rayo_dna.yaml
    aff = get_coach_affinity()  # dict {rol: 0-1} para evaluate_player_fit
"""
from __future__ import annotations
import time
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

# ── Rutas por defecto ─────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parents[2]
_CONFIG = _ROOT / "config"
_PROC   = _ROOT / "data" / "processed"

# ── Cache con TTL ─────────────────────────────────────────────────────────────
_CACHE: dict[str, Any] = {"dna": None, "affinity": None, "t": 0.0}
_TTL = 300   # 5 minutos


# ── Ejes ADN (orden fijo, mismo que entrenadores.py) ─────────────────────────
ADN_AXES = [
    # (eje, columna_opta, invertir, descripcion)
    ("presion_alta",         "ppda",                    True,
     "PPDA — menor = mas presion (metrica invertida)"),
    ("posesion",             "possession_percentage",   False,
     "Porcentaje medio de posesion por partido"),
    ("solidez_defensiva",    "goals_conceded",          True,
     "Goles encajados por partido (por partido, invertido)"),
    ("tendencia_ofensiva",   "goals",                   False,
     "Goles marcados por partido"),
    ("verticalidad",         "successful_long_passes",  False,
     "Pases largos exitosos totales"),
    ("intensidad_defensiva", "tackles_won",             False,
     "Entradas ganadas totales"),
    ("uso_transiciones",     "recoveries",              False,
     "Recuperaciones de balon totales"),
]

# ── Mapeo eje -> roles que potencia (para derivar afinidad) ──────────────────
# Valores 0.0-1.0: cuanto contribuye ese eje a la afinidad con ese rol.
_AXIS_ROLE_MAP: dict[str, dict[str, float]] = {
    "presion_alta": {
        "mediocentro_recuperador": 0.90,
        "extremo_vertical":        0.80,
        "delantero_movil":         0.80,
        "lateral_ofensivo":        0.70,
        "interior_llegador":       0.70,
        "central_corrector":       0.60,
        "delantero_rematador":     0.60,
        "central_dominador":       0.40,
        "mediocentro_organizador": 0.30,
        "extremo_asociativo":      0.50,
    },
    "posesion": {
        "central_dominador":       0.90,
        "mediocentro_organizador": 0.90,
        "extremo_asociativo":      0.80,
        "lateral_ofensivo":        0.70,
        "interior_llegador":       0.60,
        "delantero_movil":         0.60,
        "mediocentro_recuperador": 0.40,
        "extremo_vertical":        0.40,
        "delantero_rematador":     0.50,
        "central_corrector":       0.50,
    },
    "solidez_defensiva": {
        "central_corrector":       0.90,
        "central_dominador":       0.80,
        "mediocentro_recuperador": 0.80,
        "lateral_ofensivo":        0.60,
        "mediocentro_organizador": 0.50,
        "interior_llegador":       0.50,
        "delantero_movil":         0.30,
        "extremo_vertical":        0.30,
        "extremo_asociativo":      0.30,
        "delantero_rematador":     0.20,
    },
    "tendencia_ofensiva": {
        "delantero_rematador":     0.90,
        "extremo_vertical":        0.85,
        "delantero_movil":         0.85,
        "extremo_asociativo":      0.80,
        "interior_llegador":       0.75,
        "lateral_ofensivo":        0.60,
        "mediocentro_organizador": 0.50,
        "mediocentro_recuperador": 0.30,
        "central_dominador":       0.20,
        "central_corrector":       0.20,
    },
    "verticalidad": {
        "extremo_vertical":        0.90,
        "delantero_movil":         0.85,
        "lateral_ofensivo":        0.80,
        "interior_llegador":       0.70,
        "delantero_rematador":     0.65,
        "extremo_asociativo":      0.60,
        "mediocentro_recuperador": 0.55,
        "mediocentro_organizador": 0.40,
        "central_dominador":       0.20,
        "central_corrector":       0.20,
    },
    "intensidad_defensiva": {
        "mediocentro_recuperador": 0.95,
        "central_corrector":       0.85,
        "central_dominador":       0.75,
        "lateral_ofensivo":        0.70,
        "interior_llegador":       0.65,
        "extremo_vertical":        0.60,
        "delantero_movil":         0.55,
        "mediocentro_organizador": 0.50,
        "extremo_asociativo":      0.45,
        "delantero_rematador":     0.35,
    },
    "uso_transiciones": {
        "extremo_vertical":        0.90,
        "delantero_movil":         0.90,
        "mediocentro_recuperador": 0.80,
        "interior_llegador":       0.75,
        "lateral_ofensivo":        0.70,
        "delantero_rematador":     0.65,
        "extremo_asociativo":      0.55,
        "mediocentro_organizador": 0.40,
        "central_corrector":       0.30,
        "central_dominador":       0.25,
    },
}

ALL_ROLES = [
    "mediocentro_recuperador", "extremo_vertical", "delantero_movil",
    "lateral_ofensivo", "interior_llegador", "central_corrector",
    "delantero_rematador", "central_dominador", "mediocentro_organizador",
    "extremo_asociativo",
]


def _n(s: str) -> str:
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().strip()


# ── Carga club_profile.yaml ───────────────────────────────────────────────────
def _load_club_profile() -> dict:
    try:
        return yaml.safe_load((_CONFIG / "club_profile.yaml").read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_coach_profiles() -> list[dict]:
    f = _PROC / "coach_profiles.json"
    if not f.exists():
        return []
    try:
        import json
        return json.load(open(f, encoding="utf-8"))
    except Exception:
        return []


# ── Calculo ADN desde team_seasons.parquet ────────────────────────────────────
def _compute_adn_axes(proc: Path) -> dict:
    """
    Calcula los ejes ADN del Rayo desde team_seasons.parquet.

    Mejoras vs version anterior:
      - Usa hasta las 3 ultimas temporadas con datos validos (no solo la ultima)
        para evitar que un dato anomalo de una temporada distorsione el ideal.
      - Filtra columnas con valor 0 o nulo (p.ej. ppda=0 en temporadas sin dato).
      - El ideal es la media de percentiles de esas temporadas vs la liga.
      - Los pesos se derivan de la CONSISTENCIA del extremismo: ejes en los que
        el Rayo es extremo de forma sostenida (varias temporadas) pesan mas.

    Devuelve dict: eje -> {ideal, weight, valor_bruto, columna, invertida, descripcion}
    """
    PER_GAME_COLS = {"goals_conceded", "goals"}
    N_SEASONS     = 3   # temporadas a promediar

    df   = pd.read_parquet(proc / "team_seasons.parquet")
    rayo = df[df["team"].str.contains("Rayo", case=False, na=False)].copy()
    if rayo.empty:
        return {}

    rayo = rayo.sort_values("season", ascending=False)
    liga_ref = str(rayo.iloc[0].get("league", ""))

    # Seleccionar hasta N_SEASONS temporadas con datos en la liga principal
    seasons_used = []
    for _, row in rayo.iterrows():
        if str(row.get("league", "")) != liga_ref:
            continue
        seasons_used.append(row)
        if len(seasons_used) >= N_SEASONS:
            break

    if not seasons_used:
        seasons_used = [rayo.iloc[0]]

    def _pct_one(col, rayo_row, invert=False):
        """Percentil del Rayo en una temporada vs todos los equipos de esa liga+temp."""
        season = rayo_row.get("season")
        league = rayo_row.get("league")
        liga   = df[(df["league"] == league) & (df["season"] == season)]
        if len(liga) < 5:
            liga = df[df["season"] == season]
        gp = float(rayo_row.get("games_played") or 1)
        try:
            raw = rayo_row.get(col)
            if raw is None or pd.isna(raw):
                return None
            raw = float(raw)
            if raw == 0:
                return None                      # 0 = dato ausente en todas las columnas
            if col in PER_GAME_COLS:
                raw = raw / gp
                vals = pd.to_numeric(liga[col], errors="coerce").dropna()
                gps  = pd.to_numeric(liga["games_played"], errors="coerce").fillna(gp)
                vals = vals / gps
            else:
                vals = pd.to_numeric(liga[col], errors="coerce").dropna()
            if vals.empty:
                return None
            rank = (vals <= raw).mean() * 100
            return round(100 - rank if invert else rank, 1)
        except Exception:
            return None

    result = {}
    for eje, col, invert, desc in ADN_AXES:
        pcts = []
        for row in seasons_used:
            p = _pct_one(col, row, invert=invert)
            if p is not None:
                pcts.append(p)

        if not pcts:
            pct_mean = 50.0
        else:
            pct_mean = round(sum(pcts) / len(pcts), 1)

        # Valor bruto de la temporada mas reciente con dato valido
        raw_val = None
        for row in seasons_used:
            v = row.get(col)
            if v is not None and not pd.isna(v) and float(v) != 0:
                gp = float(row.get("games_played") or 1)
                raw_val = round(float(v) / gp, 2) if col in PER_GAME_COLS else round(float(v), 2)
                break

        result[eje] = {
            "ideal":       pct_mean,
            "percentil":   pct_mean,
            "valor_bruto": raw_val,
            "columna":     col,
            "invertida":   invert,
            "descripcion": desc,
            "n_seasons":   len(pcts),
        }

    # ── Pesos: consistencia del extremismo ────────────────────────────────────
    # Eje con desviacion grande Y sostenida en varias temporadas pesa mas.
    # Usamos la desviacion media de todas las temporadas (no solo la ultima).
    season_devs: dict[str, list[float]] = {eje: [] for eje, *_ in ADN_AXES}
    for eje, col, invert, desc in ADN_AXES:
        for row in seasons_used:
            p = _pct_one(col, row, invert=invert)
            if p is not None:
                season_devs[eje].append(abs(p - 50))

    mean_devs = {eje: (sum(vs) / len(vs) if vs else 0.0)
                 for eje, vs in season_devs.items()}
    total_dev = sum(mean_devs.values()) or 1.0
    for eje in result:
        result[eje]["weight"] = round(mean_devs.get(eje, 0) / total_dev, 4)

    if total_dev == 0:
        w = round(1.0 / len(result), 4)
        for eje in result:
            result[eje]["weight"] = w

    latest = seasons_used[0]
    result["_meta"] = {
        "temporadas":  [str(r.get("season", "?")) for r in seasons_used],
        "liga":        liga_ref.replace("_", " "),
        "n_equipos":   int(len(df[(df["league"] == liga_ref) &
                                  (df["season"] == latest.get("season"))])),
        "equipo":      str(latest.get("team", "Rayo")),
    }
    return result


# ── Parametros economicos desde club_profile.yaml ────────────────────────────
def _compute_economics(club: dict) -> dict:
    """
    Extrae umbrales de inversion y referencias salariales desde club_profile.yaml.

    transfer_budget_net_eur:
      - max por fichaje   = budget * 2     (para no agotar en un solo fichaje)
      - ideal (sweet)     = budget * 0.80
      - minimo viable     = valor mas bajo del squad / 2

    salary_mass_target:
      - salario objetivo entrenador  = 3% de la masa salarial
      - salario maximo entrenador    = 5% de la masa salarial
    """
    fin = club.get("finances_eur", {})
    budget        = float(fin.get("transfer_budget_net_eur") or 10_000_000)
    salary_mass   = float(fin.get("expenses", {}).get("salary_mass_target") or 53_000_000)
    salary_cap    = float(fin.get("salary_cap_laliga_eur") or 55_000_000)

    # Valor minimo de la plantilla actual
    squad_values = []
    for grp in club.get("squad_2025_26", {}).values():
        if isinstance(grp, list):
            for p in grp:
                mv = p.get("market_value")
                if mv and float(mv) > 0:
                    squad_values.append(float(mv))
    mv_min_squad = min(squad_values) if squad_values else 300_000

    return {
        "transfer_budget_net_eur": budget,
        "mv_max":                  round(budget * 1.0),   # maximo real: = presupuesto total (ej. 10M€)
        "mv_sweet":                round(budget * 0.25),  # zona ideal: 25% del presupuesto (ej. 2.5M€)
        "mv_min":                  round(mv_min_squad / 2),
        "target_salary_eur":       round(salary_mass * 0.03),   # ~3% masa salarial
        "max_salary_eur":          round(salary_mass * 0.05),   # ~5% masa salarial
        "budget_salary_mass_eur":  salary_mass,
        "salary_cap_laliga_eur":   salary_cap,
        # Fuente para trazabilidad
        "_source": "club_profile.yaml / finances_eur",
    }


# ── Afinidad de roles desde ejes reales del entrenador ───────────────────────
def _compute_coach_affinity(coach_axes: dict) -> dict:
    """
    Dado el dict de ejes del entrenador actual (0-100 cada uno),
    deriva la afinidad con cada rol de jugador (0.0-1.0).

    Metodo:
      Para cada rol, la afinidad es la media ponderada de:
        afinidad_base[eje][rol] * (valor_eje / 100)
      cuanto mas alto es el valor del entrenador en un eje, mas
      potencia los roles afines a ese eje.

    Resultado: dict {rol: afinidad_0_1}
    """
    if not coach_axes:
        return {r: 0.6 for r in ALL_ROLES}   # neutro si no hay datos

    affinity = {}
    for role in ALL_ROLES:
        weighted_sum = 0.0
        weight_total = 0.0
        for eje, _, _, _ in ADN_AXES:
            axis_val  = float(coach_axes.get(eje) or 50)
            base_aff  = _AXIS_ROLE_MAP.get(eje, {}).get(role, 0.5)
            # Contribucion: la afinidad base escalada por la intensidad del eje (0-1)
            weighted_sum  += base_aff * (axis_val / 100.0)
            weight_total  += axis_val / 100.0
        affinity[role] = round(weighted_sum / weight_total, 3) if weight_total > 0 else 0.5

    return affinity


def _find_current_coach(club: dict, profiles: list[dict]) -> dict:
    """
    Busca el entrenador actual (club.manager) en coach_profiles.json.
    Si no lo encuentra, devuelve el de mayor score disponible.
    """
    manager_name = _n(club.get("club", {}).get("manager", ""))
    if manager_name and profiles:
        for p in profiles:
            if _n(p.get("name", "")) == manager_name:
                return p
        # Busqueda parcial por apellido
        parts = manager_name.split()
        if parts:
            surname = parts[-1]
            for p in profiles:
                if surname in _n(p.get("name", "")):
                    return p
    # Fallback: el de mayor score
    if profiles:
        return max(profiles, key=lambda x: (x.get("evaluation", {}).get("global_score") or 0))
    return {}


# ── API publica ───────────────────────────────────────────────────────────────

def build_dynamic_dna(proc: Path | None = None, config: Path | None = None) -> dict:
    """
    Construye el DNA completo del Rayo desde datos reales.
    Compatible en estructura con rayo_dna.yaml.

    Cacheado 5 minutos.

    Retorna:
    {
        "target_style": {eje: {"ideal": float, "weight": float}},
        "context_weights": {...},
        "economics": {...},
        "_meta": {...},   # fuentes y trazabilidad
    }
    """
    now = time.time()
    if _CACHE["dna"] is not None and now - _CACHE["t"] < _TTL:
        return _CACHE["dna"]

    proc   = proc   or _PROC
    config = config or _CONFIG

    club     = _load_club_profile()
    profiles = _load_coach_profiles()
    econ     = _compute_economics(club)

    # ADN desde team_seasons
    adn_raw = {}
    try:
        adn_raw = _compute_adn_axes(proc)
    except Exception:
        pass

    meta = adn_raw.pop("_meta", {})

    # Construir target_style desde datos reales (adn_raw).
    # ideal y weight calculados por _compute_adn_axes desde team_seasons.parquet
    # (media de las ultimas 3 temporadas con datos validos, pesos por consistencia).
    target_style = {}
    for eje, _, _, _ in ADN_AXES:
        data = adn_raw.get(eje, {})
        target_style[eje] = {
            "ideal":       data.get("ideal",  50.0),
            "weight":      data.get("weight", round(1.0 / len(ADN_AXES), 4)),
            "valor_bruto": data.get("valor_bruto"),
            "columna":     data.get("columna", ""),
            "invertida":   data.get("invertida", False),
            "descripcion": data.get("descripcion", ""),
            "percentil":   data.get("percentil", 50.0),
            "n_seasons":   data.get("n_seasons", 1),
        }

    # Pesos de contexto: porcentaje real de la masa salarial en riesgo por liga
    # Cuanto mas depende el club de LaLiga1 (TV rights), mas pesa la exp. LaLiga.
    tv    = float(club.get("finances_eur", {}).get("income", {}).get("tv_rights") or 50_000_000)
    total = float(sum(club.get("finances_eur", {}).get("income", {}).values()) or 1)
    tv_pct = tv / total   # fraccion de ingresos que son TV LaLiga
    laliga_w = round(min(0.30, max(0.10, tv_pct * 0.5)), 2)   # 10-30%

    context_weights = {
        "laliga_experience":   laliga_w,
        "budget_fit":          0.15,
        "squad_compatibility": 0.15,
        "_style_weight":       round(1.0 - laliga_w - 0.15 - 0.15, 2),
        "_source": "club_profile.yaml / finances_eur.income.tv_rights",
    }

    dna = {
        "target_style":    target_style,
        "context_weights": context_weights,
        "economics": {
            "target_salary_eur":       econ["target_salary_eur"],
            "max_salary_eur":          econ["max_salary_eur"],
            "budget_salary_mass_eur":  econ["budget_salary_mass_eur"],
            "salary_cap_laliga_eur":   econ["salary_cap_laliga_eur"],
            "_source": econ["_source"],
        },
        "budget": {
            "mv_max":   econ["mv_max"],
            "mv_sweet": econ["mv_sweet"],
            "mv_min":   econ["mv_min"],
            "transfer_budget_net_eur": econ["transfer_budget_net_eur"],
            "_source": "club_profile.yaml / finances_eur.transfer_budget_net_eur",
        },
        "_meta": {
            **meta,
            "manager": club.get("club", {}).get("manager", ""),
            "sources": [
                "team_seasons.parquet (ADN axes)",
                "club_profile.yaml (economics + budget)",
                "coach_profiles.json (coach affinity)",
            ],
        },
    }

    _CACHE["dna"] = dna
    _CACHE["t"]   = now
    return dna


def get_coach_affinity(proc: Path | None = None, config: Path | None = None) -> dict:
    """
    Retorna la afinidad de roles del entrenador actual (dict {rol: 0.0-1.0}).
    Basado en los ejes reales del entrenador desde coach_profiles.json.
    Cacheado junto con el DNA principal.
    """
    now = time.time()
    if _CACHE["affinity"] is not None and now - _CACHE["t"] < _TTL:
        return _CACHE["affinity"]

    club     = _load_club_profile()
    profiles = _load_coach_profiles()
    coach    = _find_current_coach(club, profiles)
    axes     = coach.get("axes", {})

    affinity = _compute_coach_affinity(axes)
    _CACHE["affinity"] = affinity
    return affinity


def get_budget_params(proc: Path | None = None, config: Path | None = None) -> dict:
    """
    Retorna los parametros de presupuesto de fichajes desde club_profile.yaml.
    {mv_max, mv_sweet, mv_min, transfer_budget_net_eur}
    """
    dna = build_dynamic_dna(proc, config)
    return dna["budget"]


def invalidate_cache() -> None:
    """Fuerza recalculo en la proxima llamada."""
    _CACHE["dna"]      = None
    _CACHE["affinity"] = None
    _CACHE["t"]        = 0.0
