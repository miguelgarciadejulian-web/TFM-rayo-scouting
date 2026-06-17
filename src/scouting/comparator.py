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

# ---------------------------------------------------------------------------
# Métricas del radar — columnas en master_players.parquet
# ---------------------------------------------------------------------------
RADAR_METRICS = [
    ("minutes",             "Minutos"),
    ("goals",               "Goles"),
    ("assists",             "Asistencias"),
    ("shots_on_target",     "Disparos"),
    ("tackles_won",         "Duelos"),
    ("passes_completed",    "Pases"),
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
    score_disponibilidad: float

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
    ):
        self.master   = master_df
        self.economic = economic_df
        self.squad    = squad_info or []
        self._rayo_names   = {p["name"].lower() for p in self.squad}
        self._loan_map     = {p["name"].lower(): p.get("loan_from", "")
                              for p in self.squad if p.get("loan_from")}
        self._homegrown    = {p["name"].lower() for p in self.squad if p.get("homegrown")}

    # ------------------------------------------------------------------ #
    # API pública                                                          #
    # ------------------------------------------------------------------ #

    def compare(self, player_names: list[str]) -> list[PlayerComparison]:
        """Devuelve la comparación para cada nombre, mejor temporada disponible."""
        results = []
        for name in player_names:
            row = self._best_row(name)
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

        fit = round(0.35*s_r + 0.25*s_e + 0.20*s_a + 0.20*s_d, 1)
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
            market_value_eur=mv if mv > 0 else None,
            contract_until=cu,
            fit_score=fit,
            score_rendimiento=s_r,
            score_economico=s_e,
            score_edad=s_a,
            score_disponibilidad=s_d,
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

    def _score_rendimiento(self, row: pd.Series) -> float:
        mins = self._sf(row.get("minutes"))
        if mins <= 0:
            return 10.0
        min_s  = min(100.0, mins / 25.0)
        ga90   = (self._sf(row.get("goals")) + self._sf(row.get("assists"))) / max(mins/90, 1)
        ga_s   = min(100.0, ga90 * 300)
        duel_s = min(100.0, self._sf(row.get("tackles_won")) / max(mins/90, 1) * 150)
        return round((0.5*min_s + 0.3*ga_s + 0.2*duel_s), 1)

    def score_rendimiento_breakdown(self, row: pd.Series) -> dict:
        """Desglosa el score de rendimiento para mostrar en la UI."""
        mins = self._sf(row.get("minutes"))
        if mins <= 0:
            return {"mins": 0, "goals": 0, "assists": 0, "tackles_won": 0,
                    "min_s": 0, "ga_s": 0, "duel_s": 0, "score": 10.0}
        goals   = self._sf(row.get("goals"))
        assists = self._sf(row.get("assists"))
        duels   = self._sf(row.get("tackles_won"))
        min_s   = round(min(100.0, mins / 25.0), 1)
        ga90    = (goals + assists) / max(mins/90, 1)
        ga_s    = round(min(100.0, ga90 * 300), 1)
        duel_s  = round(min(100.0, duels / max(mins/90, 1) * 150), 1)
        score   = round(0.5*min_s + 0.3*ga_s + 0.2*duel_s, 1)
        return {
            "mins": int(mins), "goals": int(goals), "assists": int(assists),
            "tackles_won": int(duels),
            "min_s": min_s, "ga_s": ga_s, "duel_s": duel_s, "score": score,
        }

    def _score_economico(self, mv: float) -> float:
        bp = _budget_params()
        mv_min   = bp.get("mv_min",   _RAYO_MV_MIN_FALLBACK)
        mv_sweet = bp.get("mv_sweet", _RAYO_MV_SWEET_FALLBACK)
        mv_max   = bp.get("mv_max",   _RAYO_MV_MAX_FALLBACK)
        if mv <= 0:
            return 50.0
        if mv <= mv_min:
            return 30.0
        if mv <= mv_sweet:
            return 90.0
        if mv <= mv_max:
            return round(90.0 - 40.0*(mv - mv_sweet)/(mv_max - mv_sweet), 1)
        return 15.0   # demasiado caro

    def score_economico_breakdown(self, mv: float) -> dict:
        """Desglosa el score económico para la UI."""
        bp       = _budget_params()
        mv_min   = bp.get("mv_min",   _RAYO_MV_MIN_FALLBACK)
        mv_sweet = bp.get("mv_sweet", _RAYO_MV_SWEET_FALLBACK)
        mv_max   = bp.get("mv_max",   _RAYO_MV_MAX_FALLBACK)
        score    = self._score_economico(mv)
        if mv <= 0:
            tramo = "Desconocido (sin datos TM)"
        elif mv <= mv_min:
            tramo = f"Por debajo del mínimo ({mv_min/1e6:.1f}M€) → jugador muy económico"
        elif mv <= mv_sweet:
            tramo = f"En zona ideal (≤ {mv_sweet/1e6:.0f}M€) → precio óptimo para Rayo"
        elif mv <= mv_max:
            tramo = f"En zona de negociación ({mv_sweet/1e6:.0f}M–{mv_max/1e6:.0f}M€)"
        else:
            tramo = f"Por encima del presupuesto máximo ({mv_max/1e6:.0f}M€)"
        return {
            "mv_eur": mv, "mv_min": mv_min, "mv_sweet": mv_sweet, "mv_max": mv_max,
            "tramo": tramo, "score": score,
        }

    def _score_edad(self, age: float, pos: str) -> float:
        if age <= 0:
            return 50.0
        prime = {"GK":27,"CB":25,"RB":24,"LB":24,"DM":25,"CM":24,
                 "AM":23,"RW":22,"LW":22,"ST":24}.get(pos, 24)
        decl  = DECLINE_AGE.get(pos, 31)
        if age < prime:
            return round(max(40.0, 80.0 - (prime - age)*5), 1)
        if age <= decl:
            return 90.0
        return round(max(10.0, 90.0 - (age - decl)*8), 1)

    def score_edad_breakdown(self, age: float, pos: str) -> dict:
        """Desglosa el score de edad para la UI."""
        PRIME_AGE = {"GK":27,"CB":25,"RB":24,"LB":24,"DM":25,"CM":24,
                     "AM":23,"RW":22,"LW":22,"ST":24}
        prime = PRIME_AGE.get(pos, 24)
        decl  = DECLINE_AGE.get(pos, 31)
        score = self._score_edad(age, pos)
        if age <= 0:
            fase = "Edad desconocida"
        elif age < prime:
            fase = f"En desarrollo (< {prime} años prime para {pos})"
        elif age <= decl:
            fase = f"En peak ({prime}–{decl} años)"
        else:
            fase = f"En declive (> {decl} años para {pos})"
        return {
            "age": age, "pos": pos, "prime": prime, "decline": decl,
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

    # ------------------------------------------------------------------ #
    # Radar normalizado                                                    #
    # ------------------------------------------------------------------ #

    def _normalize_radar(self, results: list[PlayerComparison]) -> None:
        """Normaliza los 6 metrics de radar a 0-100 entre los jugadores comparados."""
        raw_metrics = {
            "minutes":          [r.minutes          for r in results],
            "goals":            [r.goals             for r in results],
            "assists":          [r.assists           for r in results],
            "shots_on_target":  [r.shots_on_target   for r in results],
            "tackles_won":      [r.tackles_won       for r in results],
            "passes_completed": [r.passes_completed  for r in results],
        }
        for r in results:
            radar = {}
            for metric, values in raw_metrics.items():
                mn, mx = min(values), max(values)
                val = getattr(r, metric)
                radar[metric] = round(100.0*(val-mn)/(mx-mn), 1) if mx > mn else 50.0
            r.radar = radar

    # ------------------------------------------------------------------ #
    # Helpers datos                                                        #
    # ------------------------------------------------------------------ #

    def _best_row(self, name: str) -> pd.Series | None:
        """Busca la mejor fila para un jugador."""
        nl = name.strip().lower()
        mask = self.master["name"].str.lower() == nl
        rows = self.master[mask]
        if not rows.empty:
            return self._dedup_latest(rows).iloc[0]

        parts = nl.split()
        if len(parts) >= 2:
            initial = parts[0][0] + "."
            abbrev  = (initial + " " + " ".join(parts[1:])).lower()
            mask2   = self.master["name"].str.lower() == abbrev
            rows    = self.master[mask2]
            if not rows.empty:
                return self._dedup_latest(rows).iloc[0]

            surname = " ".join(parts[1:])
            mask3   = self.master["name"].str.lower().str.contains(surname, regex=False)
            rows    = self.master[mask3]
            if not rows.empty:
                return self._dedup_latest(rows).iloc[0]

        return None

    def _dedup_latest(self, df: pd.DataFrame) -> pd.DataFrame:
        ORDER = {"2026":7,"2025-2026":6,"2025/2026":6,"2025":5,
                 "2024-2025":4,"2024":4,"2023-2024":3,"2023":3}
        if "season" not in df.columns:
            return df.drop_duplicates("name") if "name" in df.columns else df
        df = df.copy()
        df["_o"] = df["season"].map(ORDER).fillna(0)
        best = df.loc[df.groupby("name")["_o"].idxmax()]
        return best.drop(columns=["_o"]).reset_index(drop=True)

    def _get_mv(self, name: str) -> float:
        if self.economic is None or self.economic.empty:
            return 0.0
        import unicodedata
        def _n(s): return unicodedata.normalize("NFKD",str(s)).encode("ascii","ignore").decode().lower()
        nl = _n(name)
        # 1) por canonical_name
        if "canonical_name" in self.economic.columns:
            mask = self.economic["canonical_name"].apply(_n) == nl
            rows = self.economic[mask]
            if not rows.empty:
                v = rows.iloc[0].get("market_value_eur")
                if v and float(v) > 0:
                    return float(v)
        # 2) por display_name
        if "display_name" in self.economic.columns:
            mask = self.economic["display_name"].apply(_n) == nl
            rows = self.economic[mask]
            if not rows.empty:
                v = rows.iloc[0].get("market_value_eur")
                if v and float(v) > 0:
                    return float(v)
        return 0.0

    def _get_contract(self, name: str) -> str | None:
        if self.economic is None or self.economic.empty:
            return None
        import unicodedata
        def _n(s): return unicodedata.normalize("NFKD",str(s)).encode("ascii","ignore").decode().lower()
        nl = _n(name)
        for col in ("canonical_name", "display_name"):
            if col not in self.economic.columns:
                continue
            mask = self.economic[col].apply(_n) == nl
            rows = self.economic[mask]
            if not rows.empty:
                v = rows.iloc[0].get("contract_until")
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

    master = pd.read_parquet(master_path) if master_path.exists() else pd.DataFrame()
    economic = pd.read_parquet(economic_path) if economic_path.exists() else None

    return FitRayoScorer(master_df=master, economic_df=economic, squad_info=squad_info or [])
