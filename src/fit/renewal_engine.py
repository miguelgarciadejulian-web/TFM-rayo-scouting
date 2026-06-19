# -*- coding: utf-8 -*-
"""
renewal_decision.py
===================
Motor de decisión automática de renovaciones de contrato para Rayo Vallecano.

Para cada jugador de la plantilla con contrato próximo a vencer, genera:
  - Recomendación: una de 5 opciones (renovar / no_renovar / vender /
                   renovar_y_ceder / renovar_proteger_valor)
  - Score de renovación: 0-100
  - Explicación automática: factores positivos, negativos, riesgos y oportunidades
  - Nivel de confianza: bajo / medio / alto

Arquitectura:
  - Servicio puro Python — sin dependencias de Dash ni de la UI.
  - Lee datos de: club_profile.yaml, player_seasons_enriched.parquet,
    player_economic.parquet (opcional).
  - Se integra en dashboard/pages/decisiones.py como nueva sección visual.
  - Extiende (no reemplaza) squad_decisions() de decisions.py.

Variables del modelo
--------------------
Rendimiento (40%)
  - minutos_pct:      % de minutos jugados sobre el total posible (90 * n_partidos)
  - rating_interno:   score de rol (0-100) desde player_profile.py
  - evolucion:        tendencia de rendimiento (últimas 2 temporadas si existen)

Edad y ciclo vital (20%)
  - age_score:        puntuación por edad según curva de rendimiento por posición
  - potential:        potencial declarado ('muy alto', 'alto', 'estable', 'en meseta', 'veterania')

Situación económica (20%)
  - value_score:      valor de mercado relativo a la media de la plantilla
  - salary_risk:      estimación del coste de renovación
  - revalorizacion:   tendencia del valor de mercado

Situación contractual (20%)
  - meses_restantes:  meses hasta expiración
  - riesgo_salida:    si puede salir libre en ≤ 6 meses → riesgo alto
  - clausula:         existencia de cláusula de rescisión protege el valor
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Literal

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tipos y constantes
# ---------------------------------------------------------------------------

Recommendation = Literal[
    "renovar",
    "no_renovar",
    "vender",
    "renovar_y_ceder",
    "renovar_proteger_valor",
]

Confidence = Literal["bajo", "medio", "alto"]

RECOMMENDATION_LABELS: dict[str, str] = {
    "renovar":               "Renovar",
    "no_renovar":            "No renovar",
    "vender":                "Vender",
    "renovar_y_ceder":       "Renovar y ceder",
    "renovar_proteger_valor":"Renovar para proteger valor",
}

RECOMMENDATION_ICONS: dict[str, str] = {
    "renovar":               "ti-refresh",
    "no_renovar":            "ti-x",
    "vender":                "ti-cash",
    "renovar_y_ceder":       "ti-arrow-right",
    "renovar_proteger_valor":"ti-shield",
}

RECOMMENDATION_COLORS: dict[str, tuple[str, str]] = {
    "renovar":               ("#DCFCE7", "#166534"),
    "no_renovar":            ("#FEE2E2", "#991B1B"),
    "vender":                ("#FFF7ED", "#9A3412"),
    "renovar_y_ceder":       ("#FFFBEB", "#854D0E"),
    "renovar_proteger_valor":("#EFF6FF", "#1D4ED8"),
}

# Edad de declive por grupo posicional (a partir de la cual el ciclo baja)
DECLINE_AGE: dict[str, int] = {
    "GK": 35, "CB": 32, "RB": 31, "LB": 31,
    "DM": 32, "CM": 31, "AM": 30,
    "RW": 29, "LW": 29, "ST": 31,
}

# Umbral de minutos para considerar titularidad (de 3200 min posibles ≈ 34 jornadas × 90)
TITULAR_MIN = 1800
ROTACION_MIN = 900


# ---------------------------------------------------------------------------
# Dataclass de resultado
# ---------------------------------------------------------------------------

@dataclass
class RenewalResult:
    name: str
    position: str
    age: float
    contract_end: str
    months_remaining: int
    market_value_eur: float | None

    # Scores parciales (0-100)
    score_rendimiento: float
    score_edad: float
    score_economico: float
    score_contractual: float
    renewal_score: float        # score final ponderado 0-100

    recommendation: Recommendation
    confidence: Confidence

    # Narrativa
    positivos: list[str] = field(default_factory=list)
    negativos: list[str] = field(default_factory=list)
    riesgos:   list[str] = field(default_factory=list)
    oportunidades: list[str] = field(default_factory=list)

    # Metadata
    minutes: int = 0
    role_score: float | None = None
    role_label: str = ""
    data_quality: str = "estimado"  # "completo" / "parcial" / "estimado"


# ---------------------------------------------------------------------------
# Motor de cálculo
# ---------------------------------------------------------------------------

class RenewalEngine:
    """Calcula la recomendación de renovación para cada jugador de la plantilla."""

    def __init__(
        self,
        enriched_df: pd.DataFrame,
        economic_df: pd.DataFrame | None = None,
        squad_avg_value: float = 3_000_000,
        horizon_months: int = 18,   # solo analiza contratos que vencen en ≤ horizon_months
    ):
        self.enriched    = enriched_df
        self.economic    = economic_df
        self.squad_avg   = max(squad_avg_value, 500_000)
        self.horizon     = horizon_months
        self._today      = date.today()

    # ------------------------------------------------------------------ #
    # Punto de entrada público                                             #
    # ------------------------------------------------------------------ #

    def analyze_squad(self, squad: list[dict]) -> list[RenewalResult]:
        """Analiza todos los jugadores de la plantilla y devuelve resultados ordenados."""
        results: list[RenewalResult] = []
        for player in squad:
            try:
                r = self._analyze_player(player)
                if r is not None:
                    results.append(r)
            except Exception as exc:
                logger.warning("renewal_decision: error en %s: %s", player.get("name"), exc)
        # Ordenar: primero los que vencen antes + peor score
        results.sort(key=lambda r: (r.months_remaining, -r.renewal_score))
        return results

    def analyze_expiring(self, squad: list[dict]) -> list[RenewalResult]:
        """Solo jugadores con contrato dentro del horizonte temporal."""
        all_results = self.analyze_squad(squad)
        return [r for r in all_results if r.months_remaining <= self.horizon]

    # ------------------------------------------------------------------ #
    # Análisis individual                                                  #
    # ------------------------------------------------------------------ #

    def _analyze_player(self, player: dict) -> RenewalResult | None:
        name         = player.get("name", "")
        position     = player.get("position", "")
        age          = float(player.get("age") or 0)
        contract_end = str(player.get("contract_end") or "")
        mv_raw       = player.get("market_value") or 0
        market_value = float(mv_raw) if mv_raw else None

        if not contract_end or len(contract_end) < 4:
            return None

        months_remaining = self._months_to(contract_end)

        # ── Rendimiento desde parquet enriquecido ──
        perf   = self._get_performance(name)
        minutes    = int(perf.get("minutes") or 0)
        role_score = perf.get("role_score")       # 0-100 o None
        role_label = perf.get("role_label", "")

        # ── Datos económicos (parquet económico si existe) ──
        econ = self._get_economic(name)
        if market_value is None and econ.get("market_value_eur"):
            market_value = float(econ["market_value_eur"])
        release_clause = econ.get("release_clause_eur")

        # ── Scores parciales ──
        s_rend   = self._score_rendimiento(minutes, role_score, age, position)
        s_edad   = self._score_edad(age, position)
        s_econ   = self._score_economico(market_value, release_clause)
        s_contr  = self._score_contractual(months_remaining, release_clause)

        # Score final ponderado — proteger contra NaN
        import math
        def _safe(v: float, default: float = 50.0) -> float:
            try:
                return v if (v is not None and not math.isnan(float(v))) else default
            except (TypeError, ValueError):
                return default

        renewal_score = round(
            0.40 * _safe(s_rend) +
            0.20 * _safe(s_edad) +
            0.20 * _safe(s_econ) +
            0.20 * _safe(s_contr),
            1,
        )

        # ── Recomendación y narrativa ──
        rec, pos, neg, rie, opp = self._recommend(
            name, age, position, minutes, role_score, market_value,
            release_clause, months_remaining, renewal_score, s_rend, s_edad,
        )

        # ── Confianza ──
        confidence = self._confidence(minutes, perf.get("seasons_played", 0), market_value)

        # ── Calidad del dato ──
        if minutes > 0 and market_value and market_value > 0:
            quality = "completo"
        elif minutes > 0 or (market_value and market_value > 0):
            quality = "parcial"
        else:
            quality = "estimado"

        return RenewalResult(
            name=name,
            position=position,
            age=age,
            contract_end=contract_end,
            months_remaining=months_remaining,
            market_value_eur=market_value,
            score_rendimiento=s_rend,
            score_edad=s_edad,
            score_economico=s_econ,
            score_contractual=s_contr,
            renewal_score=renewal_score,
            recommendation=rec,
            confidence=confidence,
            positivos=pos,
            negativos=neg,
            riesgos=rie,
            oportunidades=opp,
            minutes=minutes,
            role_score=role_score,
            role_label=role_label,
            data_quality=quality,
        )

    # ------------------------------------------------------------------ #
    # Scores parciales                                                     #
    # ------------------------------------------------------------------ #

    def _score_rendimiento(self, minutes: int, role_score: float | None,
                           age: float, position: str) -> float:
        """Rendimiento: 40% minutos, 60% role_score (si disponible)."""
        # Minutos → 0-100
        if minutes >= TITULAR_MIN:
            min_s = 100.0
        elif minutes >= ROTACION_MIN:
            min_s = 60.0 + 40.0 * (minutes - ROTACION_MIN) / (TITULAR_MIN - ROTACION_MIN)
        elif minutes > 0:
            min_s = 20.0 + 40.0 * minutes / ROTACION_MIN
        else:
            min_s = 10.0   # sin datos → penalización moderada

        import math as _math
        if role_score is not None:
            rs_f = float(role_score)
            if not _math.isnan(rs_f):
                return round(0.4 * min_s + 0.6 * rs_f, 1)
        return round(min_s, 1)

    def _score_edad(self, age: float, position: str) -> float:
        """Edad: máximo en prime, declive después del peak."""
        if age <= 0:
            return 50.0
        # Edad de mayor rendimiento según posición
        prime_start = {"GK": 27, "CB": 25, "RB": 24, "LB": 24,
                       "DM": 25, "CM": 24, "AM": 23,
                       "RW": 22, "LW": 22, "ST": 24}.get(position, 24)
        decline     = DECLINE_AGE.get(position, 31)
        if age < prime_start:
            # Joven con potencial — score basado en cercanía al prime
            return round(max(40.0, 80.0 - (prime_start - age) * 5), 1)
        if age <= decline:
            return 90.0   # prime
        # Post-decline: baja 8 puntos por año
        return round(max(10.0, 90.0 - (age - decline) * 8), 1)

    def _score_economico(self, market_value: float | None,
                         release_clause: float | None) -> float:
        """Económico: valor de mercado relativo al squad_avg."""
        if not market_value or market_value <= 0:
            return 50.0   # sin datos → neutro
        ratio = market_value / self.squad_avg
        # < 0.5× avg → bajo valor → no compensaría salario renovado
        # > 2× avg   → activo muy valioso → proteger o vender bien
        if ratio >= 2.0:
            return 85.0
        if ratio >= 1.0:
            return 70.0
        if ratio >= 0.5:
            return 50.0
        return 30.0

    def _score_contractual(self, months: int,
                            release_clause: float | None) -> float:
        """Contractual: urgencia (menos meses → más urgente renovar o decidir)."""
        # Si ya tiene cláusula, el riesgo de fuga sin compensación es menor
        clause_bonus = 10.0 if release_clause and release_clause > 0 else 0.0
        if months <= 3:
            return round(10.0 + clause_bonus, 1)   # urgentísimo
        if months <= 6:
            return round(25.0 + clause_bonus, 1)
        if months <= 12:
            return round(50.0 + clause_bonus, 1)
        if months <= 18:
            return round(70.0 + clause_bonus, 1)
        return round(90.0 + clause_bonus, 1)

    # ------------------------------------------------------------------ #
    # Lógica de recomendación                                             #
    # ------------------------------------------------------------------ #

    def _recommend(
        self, name: str, age: float, position: str, minutes: int,
        role_score: float | None, market_value: float | None,
        release_clause: float | None, months: int, final_score: float,
        s_rend: float, s_edad: float,
    ) -> tuple[Recommendation, list, list, list, list]:

        pos:  list[str] = []
        neg:  list[str] = []
        rie:  list[str] = []
        opp:  list[str] = []

        # ── Factores narrativos ──
        if minutes >= TITULAR_MIN:
            pos.append(f"Titular habitual ({minutes:,} min — alta participación)")
        elif minutes >= ROTACION_MIN:
            pos.append(f"Rotación relevante ({minutes:,} min)")
        else:
            neg.append(f"Pocos minutos esta temporada ({minutes:,})")

        if role_score and role_score >= 70:
            pos.append(f"Alto rendimiento en su perfil (score {role_score:.0f}/100)")
        elif role_score and role_score >= 50:
            pos.append(f"Rendimiento correcto (score {role_score:.0f}/100)")
        elif role_score:
            neg.append(f"Rendimiento por debajo de la media (score {role_score:.0f}/100)")

        age_ok = s_edad >= 70
        if age_ok:
            pos.append(f"En edad óptima para su posición ({age:.0f} años)")
        elif s_edad >= 45:
            pos.append(f"Todavía en ciclo productivo ({age:.0f} años)")
        else:
            neg.append(f"Edad avanzada para su posición ({age:.0f} años — curva descendente)")

        mv = market_value or 0
        if mv >= self.squad_avg * 1.5:
            pos.append(f"Valor de mercado alto ({mv/1e6:.1f}M€ — {mv/self.squad_avg:.1f}× media plantilla)")
            opp.append("Posible ingreso relevante si se vende en mercado favorable")
        elif mv > 0 and mv < self.squad_avg * 0.4:
            neg.append(f"Valor de mercado bajo ({mv/1e6:.1f}M€)")

        if months <= 6:
            rie.append(f"Riesgo de salida a coste 0 en {months} meses — decisión urgente")
        elif months <= 12:
            rie.append(f"Contrato expira en {months} meses — negociación necesaria")

        if release_clause and release_clause > 0:
            pos.append(f"Cláusula de rescisión activa ({release_clause/1e6:.1f}M€) — valor protegido")
        else:
            rie.append("Sin cláusula de rescisión — puede salir libre sin compensación")

        # ── Árbol de decisión ──
        rec = self._decision_tree(
            age, position, minutes, role_score, mv, months, final_score, s_edad,
        )

        # Oportunidades adicionales según recomendación
        if rec == "renovar_y_ceder":
            opp.append("Cesión a liga secundaria incrementaría su valor y experiencia")
        if rec == "renovar_proteger_valor":
            opp.append("Renovar protege el activo ante salida gratuita en pocos meses")
        if rec == "vender":
            opp.append("Ventana de venta: máximo retorno antes de pérdida total de valor")
        if rec == "no_renovar":
            pos.append("Liberar ficha y presupuesto para un perfil más joven o necesario")

        return rec, pos, neg, rie, opp

    def _decision_tree(
        self, age: float, position: str, minutes: int, role_score: float | None,
        market_value: float, months: int, final_score: float, s_edad: float,
    ) -> Recommendation:
        """Árbol de decisión por reglas — documentado y ajustable."""
        rs   = role_score or 50.0
        mv   = market_value or 0
        decl = DECLINE_AGE.get(position, 31)

        # 1. Joven con poco rodaje → renovar y ceder
        if age <= 21 and minutes < ROTACION_MIN:
            return "renovar_y_ceder"

        # 2. Veterano en declive y poco valor → no renovar
        if age >= decl + 2 and rs < 50 and mv < self.squad_avg * 0.3:
            return "no_renovar"

        # 3. Veterano pero con valor residual alto → vender antes de que expire
        if age >= decl and mv >= self.squad_avg * 0.8 and months <= 12:
            return "vender"

        # 4. Jugador valioso, contrato corto, sin cláusula → renovar para proteger valor
        if mv >= self.squad_avg * 1.2 and months <= 12:
            return "renovar_proteger_valor"

        # 5. Titular o rotación con buen rendimiento → renovar
        if minutes >= ROTACION_MIN and rs >= 55 and s_edad >= 50:
            return "renovar"

        # 6. Score general alto → renovar
        if final_score >= 65:
            return "renovar"

        # 7. Score medio-bajo, veterano → no renovar
        if final_score < 40 and age >= decl:
            return "no_renovar"

        # 8. Por defecto → renovar con condiciones
        return "renovar"

    # ------------------------------------------------------------------ #
    # Nivel de confianza                                                  #
    # ------------------------------------------------------------------ #

    def _confidence(self, minutes: int, seasons_played: int,
                    market_value: float | None) -> Confidence:
        """Confianza basada en cantidad y calidad de datos disponibles."""
        points = 0
        if minutes >= ROTACION_MIN:     points += 2
        elif minutes > 0:               points += 1
        if seasons_played >= 2:         points += 1
        if market_value and market_value > 0: points += 1
        if points >= 4:  return "alto"
        if points >= 2:  return "medio"
        return "bajo"

    # ------------------------------------------------------------------ #
    # Helpers de datos                                                    #
    # ------------------------------------------------------------------ #

    def _get_performance(self, name: str) -> dict:
        """Extrae métricas de rendimiento desde player_seasons_enriched."""
        if self.enriched.empty:
            return {}
        # Usar la temporada más reciente disponible para este jugador
        _ORDER = {"2026": 7, "2025-2026": 6, "2025/2026": 6, "2025": 5,
                  "2024-2025": 4, "2024": 4}
        mask = self.enriched["name"].astype(str).str.lower() == name.lower()
        rows = self.enriched[mask]
        if rows.empty:
            # Intentar match normalizado
            import unicodedata
            def _n(s): return unicodedata.normalize("NFKD", str(s)).encode("ascii","ignore").decode().lower()
            rows = self.enriched[self.enriched["name"].apply(_n) == _n(name)]
        if rows.empty:
            return {}
        rows = rows.copy()
        rows["_o"] = rows["season"].astype(str).map(_ORDER).fillna(0)
        best = rows.sort_values("_o", ascending=False).iloc[0]

        # Intentar obtener role_score desde player_profile si está disponible
        role_score = None
        role_label = ""
        try:
            from src.profiling.player_profile import (
                profile_player_row, add_role_percentiles, ROLE_LABELS,
            )
            # Calcular percentiles solo sobre la fila del jugador (rápido)
            group = rows.sort_values("_o", ascending=False).head(1)
            grp_full = self.enriched[
                self.enriched["season"].isin(list(_ORDER.keys()))
            ]
            if "position_group" in grp_full.columns:
                pos_g = best.get("position_group")
                if pos_g:
                    grp_full = grp_full[grp_full["position_group"] == pos_g]
            pct_df = add_role_percentiles(grp_full)
            row_pct = pct_df[pct_df["name"].astype(str).str.lower() == name.lower()]
            if not row_pct.empty:
                prof = profile_player_row(row_pct.iloc[0])
                role_score = prof.get("primary_score")
                role_label = ROLE_LABELS.get(prof.get("primary_role", ""), "")
        except Exception:
            pass

        return {
            "minutes":       int(best.get("minutes") or 0),
            "role_score":    role_score,
            "role_label":    role_label,
            "seasons_played": len(rows),
        }

    def _get_economic(self, name: str) -> dict:
        """Extrae datos económicos del parquet económico si existe."""
        if self.economic is None or self.economic.empty:
            return {}
        import unicodedata
        def _n(s): return unicodedata.normalize("NFKD", str(s)).encode("ascii","ignore").decode().lower()
        mask = self.economic["display_name"].apply(_n) == _n(name)
        rows = self.economic[mask]
        if rows.empty:
            mask2 = self.economic["canonical_name"].apply(_n) == _n(name)
            rows  = self.economic[mask2]
        if rows.empty:
            return {}
        r = rows.iloc[0]
        return {
            "market_value_eur":  r.get("market_value_eur"),
            "release_clause_eur": r.get("release_clause_eur"),
            "contract_until":    r.get("contract_until"),
        }

    def _months_to(self, contract_end: str) -> int:
        """Meses hasta la fecha de expiración del contrato."""
        try:
            end = datetime.strptime(str(contract_end)[:10], "%Y-%m-%d").date()
            delta = (end - self._today)
            return max(0, delta.days // 30)
        except ValueError:
            try:
                year = int(str(contract_end)[:4])
                end  = date(year, 6, 30)
                return max(0, (end - self._today).days // 30)
            except Exception:
                return 999


# ---------------------------------------------------------------------------
# Función de conveniencia para usar desde la UI
# ---------------------------------------------------------------------------

def load_and_analyze(
    proc_path: Path,
    club_squad: list[dict],
    horizon_months: int = 18,
) -> list[RenewalResult]:
    """
    Carga los parquets necesarios y ejecuta el análisis completo.

    Parámetros:
        proc_path      : Path a data/processed/
        club_squad     : lista de jugadores de club_profile.yaml
        horizon_months : solo analiza contratos que vencen en ≤ N meses

    Devuelve lista de RenewalResult ordenada por urgencia.
    """
    enriched_path = proc_path / "player_seasons_enriched.parquet"
    economic_path = proc_path / "player_economic.parquet"

    enriched: pd.DataFrame = pd.DataFrame()
    economic: pd.DataFrame | None = None

    if enriched_path.exists():
        try:
            enriched = pd.read_parquet(enriched_path)
        except Exception as exc:
            logger.error("renewal_decision: no se pudo cargar enriched: %s", exc)

    if economic_path.exists():
        try:
            economic = pd.read_parquet(economic_path)
        except Exception as exc:
            logger.warning("renewal_decision: no se pudo cargar economic: %s", exc)


    # Media de valor de mercado
    values = [float(p["market_value"]) for p in club_squad if p.get("market_value")]
    squad_avg = sum(values) / len(values) if values else 3_000_000

    engine = RenewalEngine(
        enriched_df=enriched,
        economic_df=economic,
        squad_avg_value=squad_avg,
        horizon_months=horizon_months,
    )
    return engine.analyze_expiring(club_squad)
