"""
coach_style.py
==============
Inferencia AUTOMATICA del estilo de juego de un entrenador por reglas en Python,
usando EXCLUSIVAMENTE los datos de la plataforma (`team_seasons.parquet`).

No hay descripciones escritas a mano: dado el historial de un tecnico
(equipo + temporadas, hecho factual de `config/coach_history.yaml`), se agregan
las metricas de equipo de Opta de esos equipos-temporada y se derivan:

  Ejes cuantitativos (0-100, percentil vs su misma liga):
    - tendencia_ofensiva     : produccion ofensiva (tiros, ocasiones, juego en campo rival)
    - solidez_defensiva      : goles encajados (inverso) y porterias a cero
    - presion_alta           : recuperaciones + entradas + faltas (proxy de presion)
    - posesion               : % de posesion
    - verticalidad           : peso del pase largo / juego directo
    - intensidad_defensiva   : entradas + intercepciones + duelos + faltas por partido
    - uso_transiciones       : juego directo y vertical sin dominar el balon
    - flexibilidad_tactica   : variabilidad de su estilo entre temporadas/equipos

  Ejes contextuales (proxy, claramente marcados):
    - desarrollo_jovenes     : se calcula con datos de plantilla si existen; si no, n/d
    - adaptacion_presupuesto : rendimiento relativo al gasto (si hay dato), si no proxy

Tambien genera una DESCRIPCION TEXTUAL automatica basada en umbrales sobre estos
ejes (reglas en `describe_style`).
"""
from __future__ import annotations
import numpy as np
import pandas as pd

# ── Metricas de equipo (por partido) usadas en los ejes ─────────────────────
PER_GAME_METRICS = [
    "total_shots", "shots_on_target_inc_goals", "goals", "goals_conceded",
    "successful_passes_opposition_half", "key_passes_attempt_assists",
    "successful_long_passes", "total_passes", "open_play_passes",
    "recoveries", "tackles_won", "interceptions", "duels", "aerial_duels_won",
    "total_fouls_conceded", "successful_crosses_open_play", "successful_dribbles",
    "corners_won", "clean_sheets",
]

# Ejes -> combinacion de metricas por-partido (peso). Documentado y editable.
# Cada metrica se percentila dentro de la liga antes de combinarse.
AXES = {
    "tendencia_ofensiva": {
        "total_shots": 0.28, "shots_on_target_inc_goals": 0.22, "goals": 0.22,
        "key_passes_attempt_assists": 0.16, "successful_passes_opposition_half": 0.12,
    },
    "solidez_defensiva": {
        "goals_conceded": -0.55, "clean_sheets": 0.45,
    },
    "presion_alta": {
        "recoveries": 0.40, "tackles_won": 0.22, "interceptions": 0.20,
        "total_fouls_conceded": 0.18,
    },
    "intensidad_defensiva": {
        "tackles_won": 0.26, "interceptions": 0.24, "duels": 0.22,
        "total_fouls_conceded": 0.16, "aerial_duels_won": 0.12,
    },
    "verticalidad": {
        "successful_long_passes": 0.55, "successful_passes_opposition_half": 0.25,
        "successful_dribbles": 0.20,
    },
}

# Posesion se toma directa del % (no percentil) y tambien percentilada.
# uso_transiciones y flexibilidad se calculan aparte.

AXIS_LABELS = {
    "tendencia_ofensiva": "Tendencia ofensiva",
    "solidez_defensiva": "Solidez defensiva",
    "presion_alta": "Presion alta",
    "posesion": "Posesion",
    "verticalidad": "Verticalidad",
    "intensidad_defensiva": "Intensidad defensiva",
    "uso_transiciones": "Uso de transiciones",
    "flexibilidad_tactica": "Flexibilidad tactica",
    "desarrollo_jovenes": "Desarrollo de jovenes",
    "adaptacion_presupuesto": "Adaptacion a presupuesto reducido",
}


def _per_game(df: pd.DataFrame) -> pd.DataFrame:
    """Convierte stats acumuladas en por-partido usando games_played."""
    out = df.copy()
    g = pd.to_numeric(out.get("games_played"), errors="coerce").replace(0, np.nan)
    g = g.fillna(g.median() if g.notna().any() else 38)
    for m in PER_GAME_METRICS:
        if m in out.columns:
            out[f"{m}__pg"] = pd.to_numeric(out[m], errors="coerce") / g
    return out


def build_reference(team_seasons: pd.DataFrame) -> pd.DataFrame:
    """Tabla de referencia con metricas por-partido y percentiles por liga.

    Se calcula una sola vez y se reutiliza para todos los entrenadores.
    """
    ref = _per_game(team_seasons)
    for m in PER_GAME_METRICS:
        col = f"{m}__pg"
        if col in ref.columns:
            ref[f"{col}__pct"] = ref.groupby("league")[col].rank(pct=True) * 100
    # posesion percentil
    if "possession_percentage" in ref.columns:
        ref["possession__pct"] = ref.groupby("league")["possession_percentage"].rank(pct=True) * 100
    return ref


def _axis_value(rows_pct: pd.DataFrame, weights: dict) -> float:
    """Combina percentiles (media de filas del entrenador) en un eje 0-100."""
    acc, wsum = 0.0, 0.0
    for metric, w in weights.items():
        col = f"{metric}__pg__pct"
        if col in rows_pct.columns:
            val = rows_pct[col].mean(skipna=True)
            if pd.notna(val):
                # peso negativo: invertir percentil
                v = (100 - val) if w < 0 else val
                acc += abs(w) * v
                wsum += abs(w)
    return round(acc / wsum, 1) if wsum > 0 else float("nan")


def coach_axes(reference: pd.DataFrame, team_season_keys: list[tuple[str, str]]) -> dict:
    """Calcula los ejes de estilo de un entrenador.

    team_season_keys: lista de (team_match, season) donde team_match es un texto
    que debe aparecer en el nombre del equipo (p.ej. 'Osasuna').
    Devuelve dict con ejes 0-100, posesion media, n_seasons y cobertura.
    """
    mask = pd.Series(False, index=reference.index)
    matched = []
    for team_match, season in team_season_keys:
        sub = (
            reference["team"].str.contains(team_match, case=False, na=False)
            & (reference["season"].astype(str) == str(season))
        )
        if sub.any():
            mask = mask | sub
            matched.append((team_match, season))
    rows = reference[mask]

    if rows.empty:
        return {"_coverage": {"matched": [], "requested": team_season_keys, "n_rows": 0}}

    axes = {}
    for axis, weights in AXES.items():
        axes[axis] = _axis_value(rows, weights)

    # Posesion (media directa del % real)
    if "possession_percentage" in rows.columns:
        axes["posesion_pct_real"] = round(
            pd.to_numeric(rows["possession_percentage"], errors="coerce").mean(), 1
        )
        axes["posesion"] = round(rows["possession__pct"].mean(skipna=True), 1) \
            if "possession__pct" in rows.columns else float("nan")

    # Uso de transiciones: vertical + ofensivo pero SIN dominar posesion
    vert = axes.get("verticalidad", np.nan)
    poss = axes.get("posesion", np.nan)
    off = axes.get("tendencia_ofensiva", np.nan)
    if pd.notna(vert) and pd.notna(poss):
        axes["uso_transiciones"] = round(
            np.clip(0.5 * vert + 0.3 * (100 - poss) + 0.2 * (off if pd.notna(off) else 50), 0, 100), 1
        )

    # Flexibilidad tactica: variabilidad del estilo entre temporadas
    if len(rows) >= 2 and "possession_percentage" in rows.columns:
        poss_std = pd.to_numeric(rows["possession_percentage"], errors="coerce").std()
        shots_std = rows.get("total_shots__pg", pd.Series(dtype=float)).std()
        # mas dispersion => mas flexible (normalizado a escala razonable)
        flex = np.clip((poss_std or 0) * 6 + (shots_std or 0) * 8, 0, 100)
        axes["flexibilidad_tactica"] = round(float(flex), 1)
    else:
        axes["flexibilidad_tactica"] = float("nan")

    axes["_coverage"] = {
        "matched": matched,
        "requested": team_season_keys,
        "n_rows": int(len(rows)),
        "teams": sorted(rows["team"].unique().tolist()),
        "seasons": sorted(rows["season"].astype(str).unique().tolist()),
    }
    return axes


# ── Descripcion textual automatica por reglas ───────────────────────────────
def _band(v, lo=40, hi=66):
    if pd.isna(v):
        return None
    return "bajo" if v < lo else ("alto" if v >= hi else "medio")


def describe_style(axes: dict) -> dict:
    """Genera estilo principal, etiquetas y descripcion textual por umbrales."""
    off = axes.get("tendencia_ofensiva", np.nan)
    deff = axes.get("solidez_defensiva", np.nan)
    press = axes.get("presion_alta", np.nan)
    poss = axes.get("posesion", np.nan)
    vert = axes.get("verticalidad", np.nan)
    intens = axes.get("intensidad_defensiva", np.nan)
    trans = axes.get("uso_transiciones", np.nan)

    tags = []
    # Bloque / linea
    if _band(press) == "alto":
        tags.append("Presion alta")
    elif _band(press) == "bajo":
        tags.append("Bloque medio-bajo")
    else:
        tags.append("Bloque medio")
    # Balon
    if _band(poss) == "alto":
        tags.append("Dominio de balon")
    elif _band(poss) == "bajo":
        tags.append("Sin balon / reactivo")
    if _band(vert) == "alto":
        tags.append("Juego directo / vertical")
    elif _band(vert) == "bajo":
        tags.append("Juego elaborado")
    if _band(off) == "alto":
        tags.append("Vocacion ofensiva")
    if _band(deff) == "alto":
        tags.append("Solidez defensiva")
    if _band(intens) == "alto":
        tags.append("Alta intensidad")
    if _band(trans) == "alto":
        tags.append("Peligro en transicion")

    # Estilo principal (combinacion dominante)
    if _band(poss) == "alto" and _band(press) == "alto":
        style_main = "Presion alta / Posicional"
    elif _band(poss) == "alto":
        style_main = "Posicional / Dominio de balon"
    elif _band(press) == "alto" and _band(vert) == "alto":
        style_main = "Presion alta / Transiciones"
    elif _band(deff) == "alto" and _band(poss) == "bajo":
        style_main = "Bloque solido / Reactivo"
    elif _band(vert) == "alto":
        style_main = "Juego directo / Transiciones"
    else:
        style_main = "Bloque medio / Equilibrado"

    # Texto descriptivo
    def lvl(v):
        b = _band(v)
        return {"alto": "elevada", "medio": "media", "bajo": "reducida", None: "n/d"}[b]

    parts = []
    if pd.notna(poss):
        if axes.get("posesion_pct_real") is not None:
            parts.append(
                f"Equipos con una posesion media del {axes['posesion_pct_real']}% "
                f"(percentil {int(poss)} de su liga)."
            )
    if pd.notna(press):
        parts.append(f"Intensidad de presion {lvl(press)} y intensidad defensiva {lvl(intens)}.")
    if pd.notna(vert):
        directo = "tiende al juego directo y vertical" if _band(vert) == "alto" else (
            "prioriza la elaboracion y el pase corto" if _band(vert) == "bajo"
            else "alterna juego directo y elaboracion")
        parts.append(f"En salida {directo}.")
    if pd.notna(off) and pd.notna(deff):
        if _band(off) == "alto" and _band(deff) == "alto":
            bal = "perfil de doble fase muy completo (ofensivo y defensivo)"
        elif _band(off) == "alto":
            bal = "perfil de marcada vocacion ofensiva"
        elif _band(deff) == "alto":
            bal = "perfil de prioridad defensiva y orden"
        else:
            bal = "perfil equilibrado entre ataque y defensa"
        parts.append(f"Muestra un {bal}.")
    if pd.notna(trans) and _band(trans) == "alto":
        parts.append("Genera peligro especialmente en transiciones rapidas.")

    description = " ".join(parts) if parts else "Datos insuficientes para describir el estilo."

    return {
        "style_main": style_main,
        "style_tags": tags,
        "description_auto": description,
    }


def profile_coach(reference: pd.DataFrame, history_entry: dict) -> dict:
    """Perfil completo de un entrenador a partir de su entrada de historial.

    history_entry debe incluir 'stints': lista de {team_match, seasons:[...]}.
    """
    keys = []
    for stint in history_entry.get("stints", []):
        tm = stint.get("team_match") or stint.get("team")
        for s in stint.get("seasons", []):
            keys.append((tm, str(s)))
    axes = coach_axes(reference, keys)
    cov = axes.get("_coverage", {})
    if cov.get("n_rows", 0) == 0:
        return {
            "axes": {}, "style_main": "Sin datos en la plataforma",
            "style_tags": [], "description_auto":
            "No hay temporadas de este tecnico cubiertas por los datos disponibles.",
            "coverage": cov, "data_partial": True,
        }
    desc = describe_style(axes)
    requested = len(keys)
    matched = cov.get("n_rows", 0)
    return {
        "axes": {k: v for k, v in axes.items() if not k.startswith("_")},
        "style_main": desc["style_main"],
        "style_tags": desc["style_tags"],
        "description_auto": desc["description_auto"],
        "coverage": cov,
        "data_partial": matched < requested,
        "coverage_ratio": round(matched / requested, 2) if requested else 0.0,
    }
