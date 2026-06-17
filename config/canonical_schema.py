"""Esquema canónico del Master Scouting.

Cualquier dataset ingerido se mapea a estas columnas antes de unirse al master.
El módulo `src/etl/normalize.py` lee este archivo para generar mapeos automáticos.
"""

CANONICAL_COLUMNS = {
    # Identidad
    "player_id": "str",          # slug(name) + '_' + dob
    "name": "str",
    "dob": "date",
    "age": "int",
    "nationality": "str",
    "second_nationality": "str",
    "foot": "str",               # left | right | both

    # Posición / club
    "position_primary": "str",   # GK, CB, RB, LB, DM, CM, AM, RW, LW, ST
    "position_secondary": "str",
    "team": "str",
    "league": "str",
    "country": "str",
    "season": "str",             # "2025/2026"

    # Contrato y mercado
    "contract_end": "date",
    "market_value_eur": "float",
    "salary_eur_year": "float",
    "agent": "str",

    # Minutos
    "matches": "int",
    "starts": "int",
    "minutes": "int",

    # Ofensivas
    "goals": "int",
    "assists": "int",
    "xg": "float",
    "xa": "float",
    "shots": "int",
    "shots_on_target": "int",
    "key_passes": "int",
    "dribbles_completed": "int",
    "progressive_carries": "int",
    "passes_into_box": "int",
    "crosses_completed": "int",

    # Defensivas
    "tackles_won": "int",
    "interceptions": "int",
    "pressures": "int",
    "ball_recoveries": "int",
    "aerial_duels_won_pct": "float",
    "duels_won_pct": "float",

    # Pase
    "passes_completed": "int",
    "passes_attempted": "int",
    "passes_completed_pct": "float",
    "progressive_passes": "int",
    "long_passes_completed_pct": "float",

    # Portero
    "saves": "int",
    "goals_against": "int",
    "clean_sheets": "int",
    "psxg_minus_ga": "float",

    # Físicas (si están disponibles)
    "distance_covered_p90": "float",
    "sprints_p90": "float",

    # Tarjetas
    "yellow_cards": "int",
    "red_cards": "int",

    # Metadatos
    "source": "str",             # fbref | transfermarkt | opta | original_dataset
    "last_updated": "date",
}

# Alias: nombre de columna en CSV origen → nombre canónico.
# Clave = exactamente como aparece en los CSV de _jugadores_seasonstats.csv
COLUMN_ALIASES = {
    # Identidad
    "nombre":                                               "name",
    "equipo":                                               "team",
    "liga":                                                 "league",
    "posicion":                                             "position_primary",
    "temporada":                                            "season",
    "id":                                                   "player_id",

    # Participación
    "Time Played":                                          "minutes",
    "Appearances":                                          "matches",
    "Games Played":                                         "matches",
    "Starts":                                               "starts",

    # Goles y asistencias
    "Goals":                                                "goals",
    "Goal Assists":                                         "assists",

    # Tiros
    "Total Shots":                                          "shots",
    "Shots On Target ( inc goals )":                        "shots_on_target",

    # Creación
    "Key Passes (Attempt Assists)":                         "key_passes",
    "Successful Dribbles":                                  "dribbles_completed",
    "Progressive Carries":                                  "progressive_carries",
    "Total Touches In Opposition Box":                      "passes_into_box",
    "Successful Crosses open play":                         "crosses_completed",

    # Defensa
    "Tackles Won":                                          "tackles_won",
    "Interceptions":                                        "interceptions",
    "Recoveries":                                           "ball_recoveries",

    # Pases
    "Total Passes":                                         "passes_attempted",
    "Total Successful Passes ( Excl Crosses & Corners ) ":  "passes_completed",
    "Total Successful Passes ( Excl Crosses & Corners )":   "passes_completed",

    # Portero
    "Saves Made":                                           "saves",
    "Goals Conceded":                                       "goals_against",
    "Clean Sheets":                                         "clean_sheets",

    # Tarjetas
    "Yellow Cards":                                         "yellow_cards",
    "Total Red Cards":                                      "red_cards",

    # FBRef (fuente complementaria)
    "Player":       "name",
    "Squad":        "team",
    "Comp":         "league",
    "Pos":          "position_primary",
    "Min":          "minutes",
    "Gls":          "goals",
    "Ast":          "assists",
    "xG":           "xg",
    "xAG":          "xa",
}

# Métricas que se calculan automáticamente por 90 min si están en bruto.
P90_METRICS = [
    "goals", "assists", "xg", "xa", "shots", "shots_on_target",
    "key_passes", "dribbles_completed", "progressive_carries",
    "passes_into_box", "crosses_completed", "tackles_won",
    "interceptions", "pressures", "ball_recoveries",
    "progressive_passes",
]
