# -*- coding: utf-8 -*-
"""Mapeo de nombres de columna técnicos → etiquetas legibles en español."""

COL_LABELS = {
    # Identidad
    "name":                   "Jugador",
    "player_id":              "ID",
    "position_primary":       "Posición",
    "position_secondary":     "Posición 2ª",
    "lateral_pos":            "Pos.",
    "role_type":              "Tipo de jugador",
    "age":                    "Edad",
    "nationality":            "Nacionalidad",
    "foot":                   "Pie",
    "team":                   "Equipo",
    "league":                 "Liga",
    "season":                 "Temporada",
    "country":                "País",

    # Contrato / mercado
    "market_value_eur":       "Valor mercado (€)",
    "contract_end":           "Fin contrato",
    "contract_until":         "Fin contrato",
    "release_clause_eur":     "Cláusula (€)",
    "salary_eur_year":        "Salario anual (€)",
    "data_source":            "Fuente económica",
    "last_updated":           "Actualizado",
    "match_confidence":       "Confianza enlace",

    # Participación
    "matches":                "Partidos",
    "starts":                 "Como titular",
    "minutes":                "Minutos jugados",

    # Ofensivas
    "goals":                  "Goles",
    "assists":                "Asistencias",
    "xg":                     "xG",
    "xa":                     "xA",
    "shots":                  "Tiros totales",
    "shots_on_target":        "Tiros a puerta",
    "key_passes":             "Pases clave",
    "dribbles_completed":     "Regates completados",
    "progressive_carries":    "Conducciones progresivas",
    "passes_into_box":        "Toques en área rival",
    "crosses_completed":      "Centros completados",

    # Defensivas
    "tackles_won":            "Entradas ganadas",
    "interceptions":          "Intercepciones",
    "pressures":              "Presiones",
    "ball_recoveries":        "Recuperaciones",
    "aerial_duels_won_pct":   "Duelos aéreos ganados (%)",
    "duels_won_pct":          "Duelos totales ganados (%)",

    # Pase
    "passes_attempted":       "Pases intentados",
    "passes_completed":       "Pases completados",
    "passes_completed_pct":   "Precisión de pase (%)",
    "progressive_passes":     "Pases progresivos",
    "long_passes_completed_pct": "Precisión pase largo (%)",

    # Portero
    "saves":                  "Paradas",
    "goals_against":          "Goles encajados",
    "clean_sheets":           "Porterías a cero",
    "psxg_minus_ga":          "PSxG - GA",

    # Por 90 min
    "goals_p90":              "Goles p90",
    "assists_p90":            "Asistencias p90",
    "shots_p90":              "Tiros p90",
    "key_passes_p90":         "Pases clave p90",
    "tackles_won_p90":        "Entradas p90",
    "interceptions_p90":      "Intercepciones p90",
    "ball_recoveries_p90":    "Recuperaciones p90",
    "progressive_carries_p90":"Conducciones prog. p90",
    "passes_into_box_p90":    "Toques área p90",
    "dribbles_completed_p90": "Regates p90",
    "crosses_completed_p90":  "Centros p90",

    # Disciplina
    "yellow_cards":           "Tarjetas amarillas",
    "red_cards":              "Tarjetas rojas",

    # Meta
    "source":                 "Fuente",
}


def label(col: str) -> str:
    """Devuelve la etiqueta legible de una columna, o el propio nombre si no está mapeado."""
    return COL_LABELS.get(col, col.replace("_", " ").title())


def format_value(col: str, val) -> str:
    """Formatea un valor para mostrarlo en la UI."""
    import math
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "—"
    if col == "market_value_eur":
        return f"{val/1_000_000:.1f}M€" if val >= 1_000_000 else f"{val/1_000:.0f}K€"
    if col in ("passes_completed_pct", "aerial_duels_won_pct", "duels_won_pct",
               "long_passes_completed_pct"):
        return f"{val:.1f}%"
    if isinstance(val, float):
        return f"{val:.2f}"
    return str(val)
