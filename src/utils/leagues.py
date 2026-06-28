# -*- coding: utf-8 -*-
"""
leagues.py — Normalización de nombres de liga
==============================================

PROPÓSITO:
    Tabla de correspondencia entre los nombres internos de liga en el dataset
    Opta (formato "Country_League_Name") y sus nombres legibles en español
    para mostrar en la interfaz. También provee el mapeo inverso.

LIGAS INCLUIDAS (19):
    España (Primera, Segunda), Inglaterra (Premier, Championship),
    Alemania (Bundesliga), Italia (Serie A), Francia (Ligue 1, Ligue 2),
    Países Bajos (Eredivisie), Portugal (Primeira Liga), Bélgica,
    Turquía (Süper Lig), Dinamarca (Superliga), México (Liga MX),
    Argentina (Liga Profesional).

USO:
    from src.utils.leagues import league_name, LEAGUE_OPTIONS
    label = league_name("Spain_Primera_Division")  # → "LaLiga"
"""

_LEAGUE_MAP: dict[str, str] = {
    # España
    "Spain_Primera_Division":   "La Liga",
    "Spain_Segunda_Division":   "Segunda División",
    # England
    "England_Premier_League":   "Premier League",
    "England_Championship":     "Championship",
    # Germany
    "Germany_Bundesliga":       "Bundesliga",
    "Germany_2_Bundesliga":     "2. Bundesliga",
    # Italy
    "Italy_Serie_A":            "Serie A",
    # France
    "France_Ligue_1":           "Ligue 1",
    # Portugal
    "Portugal_Primeira_Liga":   "Primeira Liga",
    # Netherlands
    "Netherlands_Eredivisie":   "Eredivisie",
    # Belgium
    "Belgium_First_Division_A": "Pro League",
    # Scotland
    "Scotland_Premiership":     "Scottish Premiership",
    # Turkey
    "Türkiye_Süper_Lig":        "Süper Lig",
    # Americas
    "Argentina_Liga_Profesional":"Liga Profesional",
    "Brazil_Serie_A":           "Brasileirão",
    "Mexico_Liga_MX":           "Liga MX",
    "Chile_Primera_Division":   "Primera División Chile",
    "Colombia_Primera_A":       "Primera A Colombia",
    "USA_MLS":                  "MLS",
}


def league_name(raw: str) -> str:
    """Devuelve el nombre legible de una liga dado su código interno."""
    if not raw:
        return raw
    return _LEAGUE_MAP.get(str(raw), str(raw).replace("_", " "))
