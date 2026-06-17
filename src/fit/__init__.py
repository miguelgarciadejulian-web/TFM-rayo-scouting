"""Encaje (fit) y evaluacion de candidatos: entrenadores y jugadores."""
from .coach_fit import evaluate_coach, coach_laliga_seasons
from .player_fit import evaluate_player_fit

__all__ = ["evaluate_coach", "coach_laliga_seasons", "evaluate_player_fit"]
