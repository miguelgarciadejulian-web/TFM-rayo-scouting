# -*- coding: utf-8 -*-
"""
comparator.py
=============
Motor del Comparador de Fichajes — Rayo Vallecano 2026/27.

Calcula el índice "Fit Rayo" (0-100) para cada candidato y prepara
los datos para el radar chart y la tabla comparativa.

Componentes del Fit Rayo:
  - Rendimiento      (35%): percentil de minutos, goles, asistencias, recuperaciones
  - Encaje económico (25%): valor de mercado vs. horquilla de inversión de Rayo
  - Perfil de edad   (20%): puntuación por curva de edad/posición
  - Disponibilidad   (20%): contrato expirante, agente libre, cedido con opción, etc.

Integración:
  - Lee master_players.parquet (stats por temporada)
  - Lee player_seasons_enriched.parquet (role_score si disponible)
  - Se usa desde dashboard/pages/comparador.py
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

try:
    from src.utils.market import get_value as _get_tm_value
except Exception:
    _get_tm_value = None  # type: ignore

# ---------------------------------------------------------------------------
# Métricas del radar — columnas en master_players.parquet
# ---------------------------------------------------------------------------
RADAR_METRICS = [
    ("goal_contrib_p90",     "G+A / 90"),
    ("key_passes_p90",       "Creación"),
    ("dribbles_p90",         "Regates"),
    ("ball_recoveries_p90",  "Recuperación"),
    ("tackles_won_p90",      "Duelos"),
    ("pass_accuracy",        "Precisión pase"),
]

RADAR_COLORS = [
    "#E30613", "#1D4ED8", "#166534", "#92400E", "#6B21A8", "#0E7490",
]

# Rayo budget reference (€) — cargado dinamicamente desde club_profile.yaml
# via dynamic_dna.get_budget_params(). Estos fallbacks solo se usan si la carga
# de datos falla; en uso normal se leen de get_budget_params() en _score_economico.
_RAYO_MV_MAX_FALLBACK   = 20_000_000
_RAYO_MV_SWEET_FALLBACK = 8_000_000
_RAYO_MV_MIN_FALLBACK   = 300_000


def _budget_params() -> dict:
    """Lee umbrales de inversion desde club_profile.yaml (con cache en dynamic_dna)."""
    try:
        from src.fit.dynamic_dna import get_budget_params
        return get_budget_params()
    except Exception:
        return {
            "mv_max":   _RAYO_MV_MAX_FALLBACK,
            "mv_sweet": _RAYO_MV_SWEET_FALLBACK,
            "mv_min":   _RAYO_MV_MIN_FALLBACK,
        }

# Decline age by position group
DECLINE_AGE: dict[str, int] = {
    "GK": 35, "CB": 32, "RB": 31, "LB": 31,
    "DM": 32, "CM": 31, "AM": 30,
    "RW": 29, "LW": 29, "ST": 31,
}

# ---------------------------------------------------------------------------
# Dificultad de liga — multiplicador sobre score_rendimiento (0-1)
# Un jugador de Segunda que juega igual que uno de Primera es menos valioso
# porque la liga es más fácil. El rendimiento se escala por este factor.
# ---------------------------------------------------------------------------
LEAGUE_DIFFICULTY: dict[str, float] = {
    # Top 5 ligas europeas → 1.00
    "Spain_Primera_Division":    1.00,
    "England_Premier_League":    1.00,
    "Germany_Bundesliga":        0.99,
    "Italy_Serie_A":             0.99,
    "France_Ligue_1":            0.97,
    # Ligas de nivel medio-alto
    "Portugal_Primeira_Liga":    0.95,
    "Netherlands_Eredivisie":    0.94,
    "Belgium_First_Division_A":  0.93,
    "Türkiye_Süper_Lig":         0.93,
    "England_Championship":      0.92,
    "Scotland_Premiership":      0.90,
    "Germany_2_Bundesliga":      0.90,
    # América y resto
    "Brazil_Serie_A":            0.92,
    "Argentina_Liga_Profesional":0.91,
    "Mexico_Liga_MX":            0.89,
    "USA_MLS":                   0.88,
    "Colombia_Primera_A":        0.87,
    "Chile_Primera_Division":    0.86,
    # Segunda española
    "Spain_Segunda_Division":    0.91,
}
_LEAGUE_DIFF_DEFAULT = 0.85  # para ligas no listadas


def _league_difficulty(league: str | None) -> float:
    if not league:
        return 1.0  # sin dato → no penalizar
    return LEAGUE_DIFFICULTY.get(str(league), _LEAGUE_DIFF_DEFAULT)





# ---------------------------------------------------------------------------
# Dataclass resultado
# ---------------------------------------------------------------------------

@dataclass
class PlayerComparison:
    name:            str
    position:        str
    age:             float
    team:            str
    league:          str
    season:          str
    minutes:         int
    goals:           int
    assists:         int
    shots_on_target: int
    tackles_won:     int
    passes_completed:int
    market_value_eur: float | None
    contract_until:  str | None

    # FitRayo
    fit_score:        float          # 0-100
    score_rendimiento:float
    score_economico:  float
    score_edad:       float
    score_disponibilidad: float | None  # None = jugador Rayo en propiedad (no aplica)
    score_adn_tactico: float = 50.0    # ADN táctico (encaje estilo Rayo)

    # Métricas p90 para radar (combinadas o normalizadas)
    goal_contrib_p90:    float = 0.0   # goals_p90 + assists_p90
    key_passes_p90:      float = 0.0
    dribbles_p90:        float = 0.0
    ball_recoveries_p90: float = 0.0
    tackles_won_p90:     float = 0.0
    pass_accuracy:       float = 0.0   # passes_completed_pct (0-100)

    # Estado en Rayo
    at_rayo:    bool  = False
    loan_from:  str   = ""           # club propietario si es cedido
    homegrown:  bool  = False

    # Explicación narrativa del Fit Rayo
    narrative: dict = field(default_factory=dict)   # {componente: texto}

    # Radar normalizado (0-100)
    radar: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Motor
# ---------------------------------------------------------------------------

class FitRayoScorer:
    """Calcula el Fit Rayo de un conjunto de jugadores."""

    def __init__(
        self,
        master_df: pd.DataFrame,
        economic_df: pd.DataFrame | None = None,
        squad_info: list[dict] | None = None,   # jugadores actuales de Rayo
        enriched_df: pd.DataFrame | None = None,
    ):
        self.master   = master_df
        self.economic = economic_df
        self.squad    = squad_info or []
        # enriched para cálculo de rendimiento por posición
        if enriched_df is not None:
            self.enriched = enriched_df
        else:
            try:
                from src.utils.config import settings
                p = Path(settings()["paths"]["data_processed"]) / "player_seasons_enriched.parquet"
                self.enriched = pd.read_parquet(p) if p.exists() else pd.DataFrame()
            except Exception:
                self.enriched = pd.DataFrame()
        self._rayo_names   = {p["name"].lower() for p in self.squad}
        self._loan_map     = {p["name"].lower(): p.get("loan_from", "")
                              for p in self.squad if p.get("loan_from")}
        self._homegrown    = {p["name"].lower() for p in self.squad if p.get("homegrown")}

    # ------------------------------------------------------------------ #
    # API pública                                                          #
    # ------------------------------------------------------------------ #

    def compare(self, player_names: list[str],
                player_teams: list[str] | None = None) -> list[PlayerComparison]:
        """Devuelve la comparación para cada nombre, mejor temporada disponible.
        Si se pasa player_teams, se usa para desambiguar nombres duplicados."""
        results = []
        teams = player_teams or [None] * len(player_names)
        for name, team in zip(player_names, teams):
            row = self._best_row(name, team=team)
            if row is None:
                continue
            results.append(self._build(row))
        # Calcular radar normalizado entre los jugadores seleccionados
        self._normalize_radar(results)
        results.sort(key=lambda r: r.fit_score, reverse=True)
        return results

    def search_players(self, query: str, position: str | None = None,
                       top_n: int = 50) -> list[tuple[str, str, str]]:
        """Busca jugadores para el selector. Devuelve (nombre, equipo, liga)."""
        df = self.master
        if query and len(query) >= 2:
            mask = df["name"].str.contains(query, case=False, na=False)
            df = df[mask]
        if position:
            # Coincidencia parcial de posición
            df = df[df["position_primary"].str.contains(position, case=False, na=False)]
        # Deduplicar por nombre, quedarse con la temporada más reciente
        df = self._dedup_latest(df)
        return [
            (r["name"], r.get("team", ""), r.get("league", ""))
            for _, r in df.head(top_n).iterrows()
        ]

    # ------------------------------------------------------------------ #
    # Construcción del resultado                                           #
    # ------------------------------------------------------------------ #


    @staticmethod
    def _si(val) -> int:
        """Convierte a int de forma segura (NaN → 0)."""
        try:
            f = float(val)
            return 0 if (f != f) else int(f)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _sf(val) -> float:
        """Convierte a float de forma segura (NaN → 0.0)."""
        try:
            f = float(val)
            return 0.0 if (f != f) else f
        except (TypeError, ValueError):
            return 0.0


    def _lookup_squad(self, parquet_name: str) -> dict | None:
        """Encuentra el dict del squad que corresponde a un nombre del parquet.
        Maneja abreviaturas: 'I. Akhomach' -> 'Ilias Akhomach'.
        """
        pn = parquet_name.strip().lower()
        # 1) Coincidencia directa
        for p in self.squad:
            if p["name"].lower() == pn:
                return p
        # 2) Coincidencia por inicial + apellido(s): "I. Akhomach" -> first[0]=="I" + apellidos
        parts = pn.split()
        if len(parts) >= 2 and parts[0].endswith("."):
            initial  = parts[0][0]
            surnames = " ".join(parts[1:]).lower()
            for p in self.squad:
                yn = p["name"].lower().split()
                if yn[0].startswith(initial) and " ".join(yn[1:]) == surnames:
                    return p
        # 3) Coincidencia solo por apellido(s)
        if len(parts) >= 2:
            surnames = " ".join(parts[1:]).lower()
            matches  = [p for p in self.squad
                        if " ".join(p["name"].lower().split()[1:]) == surnames]
            if len(matches) == 1:
                return matches[0]
        return None

    def _build(self, row: pd.Series) -> PlayerComparison:
        name = str(row.get("name", ""))
        _row_team = str(row.get("team", "") or "")

        # squad_entry primero — fuente más fiable para pos/age de jugadores Rayo
        squad_entry = self._lookup_squad(name)

        # Posición: preferir YAML (más preciso) sobre parquet
        pos = (squad_entry.get("position", "") if squad_entry
               else str(row.get("position_primary", "") or ""))

        # Edad: parquet no tiene columna age — usar YAML cuando disponible
        _age_raw = row.get("age")
        try:
            _age_f = float(_age_raw) if _age_raw is not None else 0.0
            age = 0.0 if (_age_f != _age_f) else _age_f   # NaN → 0
        except (TypeError, ValueError):
            age = 0.0
        if age == 0.0 and squad_entry:
            age = float(squad_entry.get("age", 0) or 0)
        # Fallback edad desde enriched (más rápido que TM API)
        if age == 0.0:
            _enr = self._get_enriched_row(name, team=_row_team)
            if _enr is not None:
                try:
                    _ea = float(_enr.get("age") or 0)
                    age = 0.0 if (_ea != _ea) else _ea
                except (TypeError, ValueError):
                    pass

        # Económico
        mv = self._get_mv(name) or 0
        # Fallback valor de mercado al YAML de la plantilla
        if mv == 0 and squad_entry:
            mv = float(squad_entry.get("market_value", 0) or 0)

        # Contrato: fallback al YAML
        cu = self._get_contract(name)
        if not cu and squad_entry and squad_entry.get("contract_end"):
            cu = str(squad_entry["contract_end"])[:10]

        # Scores
        mins = self._si(row.get("minutes"))
        s_r  = self._score_rendimiento(row)
        s_e  = self._score_economico(mv)
        s_a  = self._score_edad(age, pos)
        s_d  = self._score_disponibilidad(cu, name, squad_entry=squad_entry)
        s_t  = self._score_adn_tactico(row, name)

        # Jugadores del Rayo en PROPIEDAD: disponibilidad no aplica (ya están en plantilla).
        # Se excluye s_d y se normalizan los pesos restantes (/0.90).
        # Cedidos: sí incluyen disponibilidad (propietario externo, coste desconocido).
        is_own_rayo = (squad_entry is not None) and not squad_entry.get("loan_from")
        if is_own_rayo:
            fit = round((0.40*s_r + 0.25*s_t + 0.20*s_e + 0.05*s_a) / 0.90, 1)
            s_d = None  # señal para UI: "no aplica"
        else:
            fit = round(0.40*s_r + 0.25*s_t + 0.20*s_e + 0.05*s_a + 0.10*s_d, 1)

        def _sf(v) -> float:
            """Convierte a float de forma segura (NaN → 0)."""
            try:
                f = float(v) if v is not None else 0.0
                return 0.0 if (f != f) else f
            except (TypeError, ValueError):
                return 0.0

        _pc = PlayerComparison(
            name=name, position=pos, age=age,
            team=str(row.get("team", "")),
            league=str(row.get("league", "")),
            season=str(row.get("season", "")),
            minutes=mins,
            goals=self._si(row.get("goals")),
            assists=self._si(row.get("assists")),
            shots_on_target=self._si(row.get("shots_on_target")),
            tackles_won=self._si(row.get("tackles_won")),
            passes_completed=self._si(row.get("passes_completed")),
            # Métricas p90 para radar
            goal_contrib_p90=round(_sf(row.get("goals_p90")) + _sf(row.get("assists_p90")), 3),
            key_passes_p90=round(_sf(row.get("key_passes_p90")), 3),
            dribbles_p90=round(_sf(row.get("dribbles_completed_p90")), 3),
            ball_recoveries_p90=round(_sf(row.get("ball_recoveries_p90")), 3),
            tackles_won_p90=round(_sf(row.get("tackles_won_p90")), 3),
            pass_accuracy=round(_sf(row.get("passes_completed_pct")), 2),
            market_value_eur=mv if mv > 0 else None,
            contract_until=cu,
            fit_score=fit,
            score_rendimiento=s_r,
            score_economico=s_e,
            score_edad=s_a,
            score_disponibilidad=s_d,
            score_adn_tactico=s_t,
            at_rayo=squad_entry is not None,
            loan_from=squad_entry.get("loan_from", "") if squad_entry else "",
            homegrown=squad_entry.get("homegrown", False) if squad_entry else False,
            radar={},
            narrative={},
        )
        _pc.narrative = self._build_narrative(_pc)
        return _pc

    # ------------------------------------------------------------------ #
    # Scores parciales                                                     #
    # ------------------------------------------------------------------ #


    def _build_narrative(self, r) -> dict:
        """Genera textos explicativos para cada componente del Fit Rayo."""
        texts = {}

        # Rendimiento
        if r.score_rendimiento >= 75:
            texts["rendimiento"] = (
                f"Rendimiento muy alto: {r.minutes} min jugados, "
                f"{r.goals} goles y {r.assists} asistencias. "
                "Encaja en perfil de titular indiscutible."
            )
        elif r.score_rendimiento >= 50:
            texts["rendimiento"] = (
                f"Rendimiento sólido: {r.minutes} min, "
                f"{r.goals}G/{r.assists}A. "
                "Nivel de rotación de calidad."
            )
        else:
            texts["rendimiento"] = (
                f"Rendimiento limitado: solo {r.minutes} min disputados "
                f"con {r.goals} goles y {r.assists} asistencias. "
                "Perfil de suplente o con poco protagonismo."
            )

        # Económico
        mv_str = f"€{r.market_value_eur/1e6:.1f}M" if r.market_value_eur else "desconocido"
        if r.score_economico >= 80:
            texts["economico"] = (
                f"Valor de mercado ({mv_str}) dentro de la horquilla ideal de Rayo "
                "(≤ €8M). Fichaje asequible."
            )
        elif r.score_economico >= 50:
            texts["economico"] = (
                f"Valor ({mv_str}) en el límite del presupuesto de Rayo. "
                "Viable con negociación."
            )
        else:
            texts["economico"] = (
                f"Valor ({mv_str}) elevado para los estándares de Rayo. "
                "Requeriría esfuerzo económico importante o cesión."
            )

        # Edad
        age_ok = r.age and r.age > 0
        if not age_ok:
            texts["edad"] = "Edad desconocida — no disponible en los datos Opta."
        elif r.score_edad >= 80:
            texts["edad"] = (
                f"{r.age:.0f} años — edad prime para su posición ({r.position}). "
                "Máximo valor deportivo y recorrido."
            )
        elif r.score_edad >= 60:
            texts["edad"] = (
                f"{r.age:.0f} años — perfil maduro con experiencia. "
                "Puede aportar 2-3 temporadas de alto nivel."
            )
        else:
            texts["edad"] = (
                f"{r.age:.0f} años — fuera de la curva prime para {r.position}. "
                "Riesgo de rendimiento decreciente."
            )

        # Disponibilidad
        cu = r.contract_until[:10] if r.contract_until else "sin datos"
        if r.at_rayo and not r.loan_from:
            texts["disponibilidad"] = (
                "Jugador de la propia plantilla del Rayo. "
                "Disponibilidad inmediata, sin coste de adquisición."
            )
        elif r.loan_from:
            texts["disponibilidad"] = (
                f"Cedido desde {r.loan_from}. "
                "Negociación posible con el club propietario; no está disponible libremente."
            )
        elif r.score_disponibilidad >= 85:
            texts["disponibilidad"] = (
                f"Contrato expira en {cu}. "
                "Disponible a coste reducido o libre. Oportunidad de mercado."
            )
        elif r.score_disponibilidad >= 65:
            texts["disponibilidad"] = (
                f"Contrato acaba en {cu}. "
                "Ventana de 6-12 meses para negociar en posición de fuerza."
            )
        else:
            texts["disponibilidad"] = (
                f"Contrato vigente hasta {cu}. "
                "La adquisición exigiría traspaso de mercado completo."
            )

        return texts

    def _get_enriched_row(self, name: str, team: str | None = None):
        """Fila más reciente del jugador en enriched (columnas OPTA). Cacheada."""
        if self.enriched.empty:
            return None
        # Cache de resultados por (nombre, team)
        if not hasattr(self, "_enr_row_cache"):
            self._enr_row_cache = {}
        cache_key = (name, team)
        if cache_key in self._enr_row_cache:
            return self._enr_row_cache[cache_key]

        nl = str(name).strip().lower()
        # Índice por nombre (construido una sola vez)
        if not hasattr(self, "_enr_name_lower"):
            self._enr_name_lower = self.enriched["name"].fillna("").str.lower()
        mask = self._enr_name_lower == nl
        rows = self.enriched[mask]
        if rows.empty:
            parts = nl.split()
            if len(parts) >= 2:
                abbrev = f"{parts[0][0]}. {' '.join(parts[1:])}"
                rows = self.enriched[self._enr_name_lower == abbrev]
        if rows.empty:
            self._enr_row_cache[cache_key] = None
            return None
        # Filtrar por team si se especifica (desambiguar homónimos)
        if team and "team" in rows.columns:
            team_rows = rows[rows["team"].str.lower() == team.strip().lower()]
            if not team_rows.empty:
                rows = team_rows
        ORDER = {"2025-2026":6,"2025":5,"2024-2025":4,"2023-2024":3,"2022-2023":2,"2021-2022":1}
        rows = rows.copy()
        rows["_o"] = rows["season"].map(ORDER).fillna(0)
        # Tiebreaker: prefer rows with minutes
        rows["_m"] = pd.to_numeric(rows.get("minutes"), errors="coerce").fillna(0)
        rows["_sort"] = rows["_o"] * 100000 + rows["_m"]
        result = rows.loc[rows["_sort"].idxmax()].drop(["_o", "_m", "_sort"])
        self._enr_row_cache[cache_key] = result
        return result

    def _score_rendimiento(self, row: pd.Series) -> float:
        """Rendimiento via módulo compartido. Usa fila enriched (métricas OPTA)."""
        try:
            from src.utils.rendimiento import compute_rendimiento, get_subposition, \
                precompute_pool_stats, SUBPOS_TO_POOL
            name = str(row.get("name", ""))
            _team = str(row.get("team", "") or "")
            _enr = self._get_enriched_row(name, team=_team)
            enr_row = _enr if _enr is not None else row
            _ov = self._load_overrides_cached()
            _mv = self._load_mv_cached()
            pos_grp = str(enr_row.get("position_group", row.get("position_primary", "")))

            # Obtener lateral_pos y role_type (cacheado)
            _lat_code, _role_type = None, None
            lat_map = self._get_lateral_map_cached()
            if lat_map is not None:
                _player_row = lat_map[lat_map["name"] == name]
                if not _player_row.empty:
                    _lat_code = _player_row.iloc[0].get("lateral_pos")
                    _role_type = _player_row.iloc[0].get("role_type")

            subpos = get_subposition(name, overrides=_ov, mv_df=_mv,
                                     position_group=pos_grp,
                                     lateral_pos=_lat_code, role_type=_role_type)

            # Pool stats cacheados para evitar recálculo en batch
            pool_grp = SUBPOS_TO_POOL.get(subpos, "MID")
            ps = self._get_pool_stats_cached(pool_grp)

            rd = compute_rendimiento(enr_row, self.enriched, subpos=subpos,
                                     role_type=_role_type, pool_stats=ps)
            return round(rd["score"], 1)
        except Exception:
            mins = self._sf(row.get("minutes"))
            if mins <= 0:
                return 10.0
            min_s  = min(100.0, mins / 25.0)
            ga90   = (self._sf(row.get("goals")) + self._sf(row.get("assists"))) / max(mins/90, 1)
            ga_s   = min(100.0, ga90 * 300)
            duel_s = min(100.0, self._sf(row.get("tackles_won")) / max(mins/90, 1) * 150)
            return round(0.5*min_s + 0.3*ga_s + 0.2*duel_s, 1)

    def score_rendimiento_breakdown(self, row: pd.Series) -> dict:
        """Breakdown usando fila enriched (métricas OPTA correctas)."""
        try:
            from src.utils.rendimiento import compute_rendimiento, get_subposition
            name = str(row.get("name", ""))
            _team = str(row.get("team", "") or "")
            _enr = self._get_enriched_row(name, team=_team)
            enr_row = _enr if _enr is not None else row
            _ov = self._load_overrides_cached()
            _mv = self._load_mv_cached()
            pos_grp = str(enr_row.get("position_group", row.get("position_primary", "")))
            subpos = get_subposition(name, overrides=_ov, mv_df=_mv, position_group=pos_grp)
            return compute_rendimiento(enr_row, self.enriched, subpos=subpos)
        except Exception as exc:
            return {"score": 10.0, "subpos": "—", "dims": [], "league_coef": 0.85,
                    "league": str(row.get("league", "") or ""), "error": str(exc)}

    def _load_overrides_cached(self) -> dict:
        if not hasattr(self, "_ov_cache"):
            try:
                import json
                from src.utils.config import settings
                p = Path(settings()["paths"]["data_processed"]) / "player_overrides.json"
                self._ov_cache = json.load(open(p, encoding="utf-8")) if p.exists() else {}
            except Exception:
                self._ov_cache = {}
        return self._ov_cache

    def _load_mv_cached(self):
        if not hasattr(self, "_mv_cache"):
            try:
                from src.utils.config import settings
                cfg = Path(settings()["paths"]["data_processed"]).parents[1] / "config" / "market_values.csv"
                self._mv_cache = pd.read_csv(cfg) if cfg.exists() else None
            except Exception:
                self._mv_cache = None
        return self._mv_cache

    def _get_lateral_map_cached(self):
        """Lateral map cacheado (evita leer parquets en cada llamada)."""
        if not hasattr(self, "_lat_map_cache"):
            try:
                from src.utils.lateral_position import build_lateral_map
                from src.utils.config import settings as _stg
                _proc = Path(_stg()["paths"]["data_processed"])
                self._lat_map_cache = build_lateral_map(
                    _proc / "player_seasons_enriched.parquet",
                    _proc / "master_players.parquet",
                )
            except Exception:
                self._lat_map_cache = None
        return self._lat_map_cache

    def _get_pool_stats_cached(self, pool_grp: str) -> dict | None:
        """Pool stats cacheados por grupo posicional."""
        if not hasattr(self, "_pool_stats_cache"):
            self._pool_stats_cache = {}
        if pool_grp not in self._pool_stats_cache:
            try:
                from src.utils.rendimiento import precompute_pool_stats
                self._pool_stats_cache[pool_grp] = precompute_pool_stats(
                    self.enriched, pool_grp, min_minutes=450)
            except Exception:
                self._pool_stats_cache[pool_grp] = None
        return self._pool_stats_cache[pool_grp]

    def _score_economico(self, mv: float) -> float:
        """
        Encaje económico del Rayo Vallecano. Curva progresiva:
          sin datos      → 50  (neutro: no sabemos el valor)
          ≤ 500K         → 95  (baratísimo, perfecto)
          500K – 3M      → 92  (muy asequible)
          3M – 7M        → 90  (zona ideal Rayo)
          7M – 10M       → 90→70  (empieza a bajar)
          10M – 20M      → 70→20  (declive significativo; a 20M ya débil)
          20M – 40M      → 20→5   (muy difícil)
          40M – 70M      → 5→0    (prácticamente inviable)
          > 70M          → 0      (imposible para el Rayo)
        """
        if mv <= 0:
            return 50.0
        if mv <= 500_000:
            return 95.0
        if mv <= 3_000_000:
            return 92.0
        if mv <= 7_000_000:
            return 90.0
        if mv <= 10_000_000:
            return round(90.0 - 20.0 * (mv - 7_000_000) / 3_000_000, 1)
        if mv <= 20_000_000:
            return round(70.0 - 50.0 * (mv - 10_000_000) / 10_000_000, 1)
        if mv <= 40_000_000:
            return round(20.0 - 15.0 * (mv - 20_000_000) / 20_000_000, 1)
        if mv <= 70_000_000:
            return max(0.0, round(5.0 * (1.0 - (mv - 40_000_000) / 30_000_000), 1))
        return 0.0

    def score_economico_breakdown(self, mv: float) -> dict:
        """Desglosa el score económico para la UI."""
        score = self._score_economico(mv)
        if mv <= 0:
            tramo = "Desconocido (sin datos TM)"
        elif mv <= 500_000:
            tramo = "Baratísimo (≤ 500K€) — encaje perfecto"
        elif mv <= 3_000_000:
            tramo = "Muy asequible (≤ 3M€) — zona ideal"
        elif mv <= 7_000_000:
            tramo = "Zona ideal Rayo (3M–7M€)"
        elif mv <= 10_000_000:
            tramo = "Zona aceptable (7M–10M€) — empieza a bajar"
        elif mv <= 20_000_000:
            tramo = "Caro para el Rayo (10M–20M€) — declive significativo"
        elif mv <= 40_000_000:
            tramo = "Muy difícil (20M–40M€) — casi inviable"
        elif mv <= 70_000_000:
            tramo = "Prácticamente inviable (40M–70M€)"
        else:
            tramo = "Imposible para el Rayo (> 70M€)"
        return {
            "mv_eur": mv,
            "mv_sweet": 7_000_000, "mv_max": 20_000_000,
            "tramo": tramo, "score": score,
        }

    def _score_edad(self, age: float, pos: str) -> float:
        """
        Curva de edad para el Rayo: los jugadores jóvenes son ideales —
        proyección, revalorización y mejor relación calidad/precio.

          ≤ 21 años  → 95  (talento joven, máxima proyección)
          22–25      → 90  (rango ideal de fichaje)
          26–28      → 90→78  (maduro, menos recorrido)
          29–30      → 78→60  (veterano funcional)
          31–33      → 60→35  (inicio declive)
          > 33       → 35→10  (mínimo funcional)
        """
        if age <= 0:
            return 50.0
        if age <= 21:
            return 95.0
        if age <= 25:
            return 90.0
        if age <= 28:
            return round(90.0 - (age - 25) * 4.0, 1)
        if age <= 30:
            return round(78.0 - (age - 28) * 9.0, 1)
        if age <= 33:
            return round(60.0 - (age - 30) * (25.0 / 3.0), 1)
        return round(max(10.0, 35.0 - (age - 33) * 8.0), 1)

    def score_edad_breakdown(self, age: float, pos: str) -> dict:
        """Desglosa el score de edad para la UI."""
        score = self._score_edad(age, pos)
        if age <= 0:
            fase = "Edad desconocida"
        elif age <= 21:
            fase = "Talento joven — máxima proyección y recorrido"
        elif age <= 25:
            fase = "Rango ideal de fichaje (22–25 años)"
        elif age <= 28:
            fase = "Maduro — buen rendimiento, menor proyección"
        elif age <= 30:
            fase = "Veterano funcional — encaje moderado"
        elif age <= 33:
            fase = "Inicio de declive — encaje reducido"
        else:
            fase = "Veterano avanzado — encaje bajo"
        return {
            "age": age, "pos": pos, "prime": 23, "decline": 29,
            "fase": fase, "score": score,
        }

    def score_disponibilidad_breakdown(self, contract_until: str | None, name: str,
                                       squad_entry: dict | None = None,
                                       loan_from: str = "") -> dict:
        """Desglosa el score de disponibilidad para la UI."""
        from datetime import date
        score = self._score_disponibilidad(contract_until, name, squad_entry)
        is_loan = bool(loan_from) or (squad_entry and squad_entry.get("loan_from"))
        is_rayo = (squad_entry is not None) or (name.lower() in self._rayo_names)

        months = None
        if contract_until:
            try:
                y = int(str(contract_until)[:4])
                m = int(str(contract_until)[5:7]) if len(str(contract_until)) >= 7 else 6
                end = date(y, m, 1)
                months = max(0, (end - date.today()).days // 30)
            except Exception:
                pass

        if is_loan:
            situacion = f"Cedido — negociación con club propietario ({loan_from or squad_entry.get('loan_from','')})"
        elif months is not None:
            if months <= 6:
                situacion = f"Contrato expira en {months} meses — disponible libre o a coste mínimo"
            elif months <= 12:
                situacion = f"Contrato expira en {months} meses — ventana de negociación favorable"
            elif months <= 24:
                situacion = f"Contrato vigente ~{months//12} año(s) — traspaso necesario"
            else:
                situacion = f"Contrato largo ({months//12} años) — coste de adquisición elevado"
        else:
            situacion = "Sin datos de contrato"

        bonus_rayo = "+10 por estar en plantilla Rayo" if is_rayo and not is_loan else ""
        return {
            "contract_until": contract_until, "months": months,
            "is_loan": is_loan, "is_rayo": is_rayo,
            "situacion": situacion, "bonus_rayo": bonus_rayo, "score": score,
        }

    def _score_adn_tactico(self, row: pd.Series, name: str) -> float:
        """
        Encaje del jugador con el ADN táctico del Rayo (0-100).
        Basado en: pressing alto, verticalidad, intensidad sin balón.
        Métricas que reflejan el estilo Rayo:
          - recoveries_p90 (pressing alto, recuperar rápido)
          - tackles_won_p90 (intensidad defensiva)
          - forward_passes_p90 (verticalidad)
          - successful_dribbles_p90 (juego directo)
          - total_touches_in_opposition_box_p90 (vocación ofensiva)
        """
        try:
            _team = str(row.get("team", "") or "")
            _enr = self._get_enriched_row(name, team=_team)
            enr_row = _enr if _enr is not None else row
            pos_grp = str(enr_row.get("position_group", row.get("position_primary", "MID"))).upper()

            # Usar pool_stats cacheados
            from src.utils.rendimiento import SUBPOS_TO_POOL
            pool_grp = SUBPOS_TO_POOL.get({"GK": "GK", "DEF": "DEF", "MID": "MID", "FWD": "FWD"}.get(pos_grp, "MID"), "MID")
            _stats = self._get_pool_stats_cached(pool_grp)

            adn_metrics = [
                ("recoveries_p90", 0.30),
                ("tackles_won_p90", 0.25),
                ("forward_passes_p90", 0.20),
                ("successful_dribbles_p90", 0.15),
                ("total_touches_in_opposition_box_p90", 0.10),
            ]

            total_w, total_ws = 0.0, 0.0
            for metric, weight in adn_metrics:
                val = float(enr_row.get(metric) or 0)
                if _stats and metric in _stats:
                    mean, std, n = _stats[metric]
                    if n >= 10 and std > 1e-9:
                        z = (val - mean) / std
                        score = max(3.0, min(97.0, 50.0 + z * 15.0))
                        total_ws += weight * score
                        total_w += weight
                elif metric in self.enriched.columns:
                    # Fallback: calcular directamente (solo si no hay cache)
                    series = pd.to_numeric(self.enriched[metric], errors="coerce").dropna()
                    if len(series) >= 10:
                        pct = float((series < val).sum() / len(series) * 100)
                        total_ws += weight * pct
                        total_w += weight

            if total_w > 0:
                return round(total_ws / total_w, 1)
            return 50.0
        except Exception:
            return 50.0

    def _score_disponibilidad(self, contract_until: str | None, name: str,
                                  squad_entry: dict | None = None) -> float:
        """
        Disponibilidad de adquisición (sin bias de equipo local):
          - Cedido en Rayo (opción de compra) → 70
          - Contrato expirando ≤ 6m           → 95  (+10 si ya en Rayo = 85 máx.)
          - Contrato expirando 7-12m          → 75  (+10 si ya en Rayo = 85 máx.)
          - Contrato expirando 1-2 años       → 50  (+10 si ya en Rayo)
          - Contrato largo (>2 años)          → 25  (+10 si ya en Rayo)
        Los jugadores propios reciben +10 por integración y sin coste de traspaso,
        pero no se les regala un 100 automático independientemente del contrato.
        """
        from datetime import date

        # Cedido en Rayo — propietario externo, coste desconocido
        if squad_entry is not None and squad_entry.get("loan_from"):
            return 70.0
        if name.lower() in self._loan_map:
            return 70.0

        # Usar contract_end del squad_entry si no se pasó contract_until
        if squad_entry is not None and not contract_until:
            contract_until = squad_entry.get("contract_end")

        months = 999
        if contract_until:
            try:
                y = int(str(contract_until)[:4])
                m = int(str(contract_until)[5:7]) if len(str(contract_until)) >= 7 else 6
                end = date(y, m, 1)
                months = max(0, (end - date.today()).days // 30)
            except Exception:
                pass

        if months <= 6:
            base = 95.0
        elif months <= 12:
            base = 75.0
        elif months <= 24:
            base = 50.0
        else:
            base = 25.0

        # Bonus por integración en plantilla (sin coste de adaptación / traspaso)
        is_rayo = (squad_entry is not None) or (name.lower() in self._rayo_names)
        if is_rayo:
            base = min(85.0, base + 10.0)

        return base

    def score_adn_tactico_breakdown(self, row: pd.Series, name: str) -> dict:
        """Desglosa el score de ADN táctico para la UI."""
        try:
            _team = str(row.get("team", "") or "")
            _enr = self._get_enriched_row(name, team=_team)
            enr_row = _enr if _enr is not None else row

            pool = self.enriched
            pos_grp = str(enr_row.get("position_group",
                          row.get("position_primary", "MID"))).upper()
            pool_pos = pool[pool["position_group"].str.upper() == pos_grp].copy()
            pool_pos = pool_pos[
                pd.to_numeric(pool_pos["minutes"], errors="coerce").fillna(0) >= 450
            ]

            adn_metrics = [
                ("recoveries_p90", 0.30, "Recuperaciones (pressing alto)"),
                ("tackles_won_p90", 0.25, "Entradas ganadas (intensidad)"),
                ("forward_passes_p90", 0.20, "Pases verticales (verticalidad)"),
                ("successful_dribbles_p90", 0.15, "Regates completados (juego directo)"),
                ("total_touches_in_opposition_box_p90", 0.10, "Toques en área rival (vocación ofensiva)"),
            ]

            dims = []
            total_w, total_ws = 0.0, 0.0
            for metric, weight, label in adn_metrics:
                val = float(enr_row.get(metric) or 0)
                if metric not in pool_pos.columns:
                    continue
                series = pd.to_numeric(pool_pos[metric], errors="coerce").dropna()
                if len(series) < 5:
                    continue
                pct = float((series < val).sum() / len(series) * 100)
                dims.append({
                    "label": label,
                    "metric": metric,
                    "value_p90": round(val, 2),
                    "percentile": round(pct, 1),
                    "weight": weight,
                })
                total_ws += weight * pct
                total_w += weight

            score = round(total_ws / total_w, 1) if total_w > 0 else 50.0
            return {
                "score": score,
                "pool_size": len(pool_pos),
                "position_group": pos_grp,
                "dims": dims,
                "explanation": (
                    "Mide cuánto encaja el jugador con el estilo táctico del Rayo: "
                    "pressing alto, verticalidad, intensidad sin balón y juego directo. "
                    "Cada métrica se compara con los jugadores de la misma posición (≥450 min)."
                ),
            }
        except Exception as exc:
            return {"score": 50.0, "dims": [], "pool_size": 0,
                    "position_group": "?", "explanation": "", "error": str(exc)}

    # ------------------------------------------------------------------ #
    # Radar normalizado                                                    #
    # ------------------------------------------------------------------ #

    def _normalize_radar(self, results: list[PlayerComparison]) -> None:
        """
        Calcula percentil real de cada jugador vs. el universo del parquet,
        filtrado por grupo posicional (DEF/MID/FWD/GK).

        Métricas del radar (todas per-90 o ratios, para comparación justa):
          - G+A / 90:      goals_p90 + assists_p90  →  goal_contrib_p90
          - Creación:      key_passes_p90
          - Regates:       dribbles_completed_p90   →  dribbles_p90
          - Recuperación:  ball_recoveries_p90
          - Duelos:        tackles_won_p90
          - Precisión pase: passes_completed_pct    →  pass_accuracy
        """
        _POS_GROUP = {
            "GK": "GK",
            "CB": "DEF", "RB": "DEF", "LB": "DEF",
            "DM": "MID", "CM": "MID", "AM": "MID",
            "RW": "FWD", "LW": "FWD", "ST": "FWD",
        }

        # (attr en PlayerComparison, columna(s) en parquet para construir el universo)
        _METRICS: list[tuple[str, str | None]] = [
            ("goal_contrib_p90",    None),               # calculada: goals_p90 + assists_p90
            ("key_passes_p90",      "key_passes_p90"),
            ("dribbles_p90",        "dribbles_completed_p90"),
            ("ball_recoveries_p90", "ball_recoveries_p90"),
            ("tackles_won_p90",     "tackles_won_p90"),
            ("pass_accuracy",       "passes_completed_pct"),
        ]

        # Pre-calcular columna combinada y grupo posicional en master una sola vez
        if not hasattr(self, "_radar_cache"):
            df_m = self.master.copy()
            if "goals_p90" in df_m.columns and "assists_p90" in df_m.columns:
                df_m["_goal_contrib_p90"] = (
                    df_m["goals_p90"].fillna(0) + df_m["assists_p90"].fillna(0)
                )
            else:
                df_m["_goal_contrib_p90"] = 0.0
            # Pre-compute position group for all rows (single pass)
            if "position_primary" in df_m.columns:
                df_m["_pos_group"] = df_m["position_primary"].apply(
                    lambda p: _POS_GROUP.get(str(p).upper().split("/")[0].strip(), "OTHER")
                )
            else:
                df_m["_pos_group"] = "OTHER"
            # Pre-filter by minimum minutes
            if "minutes" in df_m.columns:
                min_thresh = float(df_m["minutes"].quantile(0.25))
                df_m = df_m[df_m["minutes"] >= max(min_thresh, 180)]
            # Cache sub-DataFrames by group
            self._radar_cache = {}
            for grp in ("GK", "DEF", "MID", "FWD"):
                sub = df_m[df_m["_pos_group"] == grp]
                self._radar_cache[grp] = sub if len(sub) >= 20 else df_m
            self._radar_cache["ALL"] = df_m

        for r in results:
            pos_short = (r.position or "").upper().split("/")[0].strip()
            group = _POS_GROUP.get(pos_short)
            df_pos = self._radar_cache.get(group, self._radar_cache["ALL"])

            radar = {}
            for attr, col in _METRICS:
                val = float(getattr(r, attr, 0) or 0)
                ref_col = "_goal_contrib_p90" if attr == "goal_contrib_p90" else col
                if ref_col and ref_col in df_pos.columns:
                    series = df_pos[ref_col].dropna().values
                    if len(series) > 0:
                        pct = float((series < val).sum()) / len(series) * 100.0
                        radar[attr] = round(pct, 1)
                    else:
                        radar[attr] = 50.0
                else:
                    radar[attr] = 50.0
            r.radar = radar

    # ------------------------------------------------------------------ #
    # Helpers datos                                                        #
    # ------------------------------------------------------------------ #

    def _best_row(self, name: str, team: str | None = None) -> pd.Series | None:
        """Busca la mejor fila para un jugador. Cacheada por (nombre, team).
        Busca primero en master, fallback a enriched si no encuentra con team."""
        if not hasattr(self, "_best_row_cache"):
            self._best_row_cache = {}
        cache_key = (name, team)
        if cache_key in self._best_row_cache:
            return self._best_row_cache[cache_key]

        if not hasattr(self, "_master_name_lower"):
            self._master_name_lower = self.master["name"].str.lower()

        nl = name.strip().lower()
        mask = self._master_name_lower == nl
        rows = self.master[mask]

        # Si hay team, filtrar para desambiguar jugadores homónimos
        if not rows.empty and team:
            team_rows = rows[rows["team"].str.lower() == team.strip().lower()]
            if not team_rows.empty:
                rows = team_rows

        if not rows.empty:
            result = self._dedup_latest(rows).iloc[0]
            # Verificar que la fila tenga minutos reales; si no, intentar enriched
            _mins = pd.to_numeric(result.get("minutes"), errors="coerce")
            if pd.notna(_mins) and _mins > 0:
                self._best_row_cache[cache_key] = result
                return result
            # Fila sin minutos — buscar en enriched como fallback
            enr_result = self._best_row_from_enriched(nl, team)
            if enr_result is not None:
                self._best_row_cache[cache_key] = enr_result
                return enr_result
            # Si no hay alternativa en enriched, devolver la de master
            self._best_row_cache[cache_key] = result
            return result

        # Búsqueda por abreviatura en master
        parts = nl.split()
        if len(parts) >= 2:
            initial = parts[0][0] + "."
            abbrev  = (initial + " " + " ".join(parts[1:])).lower()
            mask2   = self._master_name_lower == abbrev
            rows    = self.master[mask2]
            if not rows.empty and team:
                team_rows = rows[rows["team"].str.lower() == team.strip().lower()]
                if not team_rows.empty:
                    rows = team_rows
            if not rows.empty:
                result = self._dedup_latest(rows).iloc[0]
                self._best_row_cache[cache_key] = result
                return result

            surname = " ".join(parts[1:])
            mask3   = self._master_name_lower.str.contains(surname, regex=False)
            rows    = self.master[mask3]
            if not rows.empty and team:
                team_rows = rows[rows["team"].str.lower() == team.strip().lower()]
                if not team_rows.empty:
                    rows = team_rows
            if not rows.empty:
                result = self._dedup_latest(rows).iloc[0]
                self._best_row_cache[cache_key] = result
                return result

        # Último fallback: enriched directamente
        enr_result = self._best_row_from_enriched(nl, team)
        if enr_result is not None:
            self._best_row_cache[cache_key] = enr_result
            return enr_result

        self._best_row_cache[cache_key] = None
        return None

    def _best_row_from_enriched(self, name_lower: str, team: str | None) -> pd.Series | None:
        """Busca en enriched como fallback (tiene más filas que master)."""
        if self.enriched.empty:
            return None
        if not hasattr(self, "_enr_name_lower"):
            self._enr_name_lower = self.enriched["name"].fillna("").str.lower()
        mask = self._enr_name_lower == name_lower
        rows = self.enriched[mask]
        if rows.empty:
            return None
        if team:
            team_rows = rows[rows["team"].str.lower() == team.strip().lower()]
            if not team_rows.empty:
                rows = team_rows
        # Prefer row with most minutes in latest season
        rows = rows.copy()
        ORDER = {"2025-2026":6,"2025":5,"2024-2025":4,"2023-2024":3,"2022-2023":2,"2021-2022":1}
        rows["_o"] = rows["season"].map(ORDER).fillna(0)
        rows["_m"] = pd.to_numeric(rows.get("minutes"), errors="coerce").fillna(0)
        rows["_sort"] = rows["_o"] * 100000 + rows["_m"]
        best = rows.loc[rows["_sort"].idxmax()]
        return best.drop(["_o", "_m", "_sort"])

    def _dedup_latest(self, df: pd.DataFrame) -> pd.DataFrame:
        ORDER = {"2026":7,"2025-2026":6,"2025/2026":6,"2025":5,
                 "2024-2025":4,"2024":4,"2023-2024":3,"2023":3}
        if "season" not in df.columns:
            return df.drop_duplicates("name") if "name" in df.columns else df
        df = df.copy()
        df["_o"] = df["season"].map(ORDER).fillna(0)
        # Tiebreaker: prefer rows with actual minutes played
        df["_m"] = pd.to_numeric(df.get("minutes"), errors="coerce").fillna(0)
        df["_sort"] = df["_o"] * 100000 + df["_m"]
        best = df.loc[df.groupby("name")["_sort"].idxmax()]
        return best.drop(columns=["_o", "_m", "_sort"]).reset_index(drop=True)
        return best.drop(columns=["_o"]).reset_index(drop=True)

    def _get_mv(self, name: str) -> float:
        if self.economic is None or self.economic.empty:
            return 0.0
        import unicodedata
        def _n(s): return unicodedata.normalize("NFKD",str(s)).encode("ascii","ignore").decode().lower()

        # Build normalized lookup dicts once (O(n) single pass instead of O(n) per call)
        if not hasattr(self, "_mv_by_canon"):
            self._mv_by_canon = {}
            self._mv_by_display = {}
            eco = self.economic
            cn_col = eco["canonical_name"].values if "canonical_name" in eco.columns else []
            dn_col = eco["display_name"].values if "display_name" in eco.columns else []
            mv_col = eco["market_value_eur"].values if "market_value_eur" in eco.columns else [None] * len(eco)
            for i in range(len(eco)):
                mv_v = mv_col[i]
                try:
                    mv_f = float(mv_v)
                    if mv_f != mv_f or mv_f <= 0:
                        continue
                except (TypeError, ValueError):
                    continue
                if i < len(cn_col) and cn_col[i] is not None:
                    k = _n(cn_col[i])
                    if k:
                        self._mv_by_canon[k] = mv_f
                if i < len(dn_col) and dn_col[i] is not None:
                    k = _n(dn_col[i])
                    if k:
                        self._mv_by_display[k] = mv_f

        nl = _n(name)
        if nl in self._mv_by_canon:
            return self._mv_by_canon[nl]
        if nl in self._mv_by_display:
            return self._mv_by_display[nl]
        return 0.0

    def _get_contract(self, name: str) -> str | None:
        if self.economic is None or self.economic.empty:
            return None
        import unicodedata
        def _n(s): return unicodedata.normalize("NFKD",str(s)).encode("ascii","ignore").decode().lower()

        # Build normalized index once
        if not hasattr(self, "_eco_norm_idx"):
            self._eco_norm_idx = {}
            for col in ("canonical_name", "display_name"):
                if col in self.economic.columns:
                    self._eco_norm_idx[col] = self.economic[col].apply(_n)

        nl = _n(name)
        for col, norm_series in self._eco_norm_idx.items():
            mask = norm_series == nl
            if mask.any():
                v = self.economic.loc[mask.idxmax(), "contract_until"] if "contract_until" in self.economic.columns else None
                if v and str(v) not in ("nan", "None", ""):
                    return str(v)[:10]
        return None


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------

def load_scorer(proc_path: Path, squad_info: list[dict] | None = None) -> "FitRayoScorer":
    """Carga los parquets y devuelve un FitRayoScorer listo para usar."""
    master_path   = proc_path / "master_players.parquet"
    economic_path = proc_path / "player_economic.parquet"
    enriched_path = proc_path / "player_seasons_enriched.parquet"

    master   = pd.read_parquet(master_path)   if master_path.exists()   else pd.DataFrame()
    economic = pd.read_parquet(economic_path) if economic_path.exists() else None
    enriched = pd.read_parquet(enriched_path) if enriched_path.exists() else pd.DataFrame()

    return FitRayoScorer(master_df=master, economic_df=economic,
                         squad_info=squad_info or [], enriched_df=enriched)
