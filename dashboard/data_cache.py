"""
data_cache.py — Caché centralizada de datos en memoria
======================================================

PROPÓSITO:
    Gestiona la carga y almacenamiento en memoria de los datasets principales
    de la aplicación, evitando que cada página lea los parquet desde disco
    repetidamente. Implementa el patrón Singleton con carga lazy.

DATASETS CACHEADOS:
    1. master_players.parquet (11,846 jugadores) → get_master()
       Contiene: nombre, equipo, liga, posición, edad, métricas agregadas.
    2. player_economic.parquet (17,406 registros) → get_economic()
       Contiene: valor de mercado, salario, fin de contrato, agente.

FUNCIÓN warmup():
    Se llama al arrancar la app (en app.py __main__) para precargar ambos
    datasets en memoria antes de que llegue la primera petición HTTP.
    Reporta tiempos de carga por consola.

PATRÓN DE USO:
    from dashboard.data_cache import get_master, get_economic
    df  = get_master()    # DataFrame pandas — siempre la misma instancia
    eco = get_economic()  # Mismo objeto para todas las páginas
"""
from __future__ import annotations

import time
import unicodedata
from pathlib import Path
from typing import Optional

import pandas as pd

from src.utils.config import settings

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
_cfg  = settings()
_PROC = Path(_cfg["paths"]["data_processed"])

MASTER_PATH   = _PROC / "master_players.parquet"
ECONOMIC_PATH = _PROC / "player_economic.parquet"
ENRICHED_PATH = _PROC / "player_seasons_enriched.parquet"

# Temporadas que se consideran "actuales"
CURRENT_SEASONS = {"2026", "2025-2026", "2025/2026"}

# TTL de la caché (5 minutos) — refresca si el archivo cambió
_TTL = 300.0

# ---------------------------------------------------------------------------
# Estado interno
# ---------------------------------------------------------------------------
_STATE: dict = {
    "master":   {"df": None, "mtime": 0.0, "t": 0.0},
    "economic": {"df": None, "mtime": 0.0, "t": 0.0},
    "enriched": {"df": None, "mtime": 0.0, "t": 0.0},
}


def _file_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _is_stale(key: str, path: Path) -> bool:
    s = _STATE[key]
    if s["df"] is None:
        return True
    if time.monotonic() - s["t"] < _TTL:
        return False  # dentro del TTL, no verificar mtime
    return _file_mtime(path) != s["mtime"]


# ---------------------------------------------------------------------------
# master_players — solo temporada actual
# ---------------------------------------------------------------------------
def get_master(force: bool = False) -> pd.DataFrame:
    """
    Devuelve master_players filtrado a la temporada actual (2025-2026 / 2026).
    Se carga una vez y se reutiliza durante _TTL segundos.
    """
    if not force and not _is_stale("master", MASTER_PATH):
        return _STATE["master"]["df"]

    if not MASTER_PATH.exists():
        return pd.DataFrame()

    t0 = time.monotonic()
    df = pd.read_parquet(MASTER_PATH)

    # Filtrar solo temporada actual
    df = df[df["season"].isin(CURRENT_SEASONS)].copy()

    _STATE["master"]["df"]    = df
    _STATE["master"]["mtime"] = _file_mtime(MASTER_PATH)
    _STATE["master"]["t"]     = time.monotonic()

    elapsed = time.monotonic() - t0
    print(f"[data_cache] master_players cargado: {len(df):,} filas ({elapsed:.2f}s)")
    return df


# ---------------------------------------------------------------------------
# player_economic
# ---------------------------------------------------------------------------
def get_economic(force: bool = False) -> Optional[pd.DataFrame]:
    """
    Devuelve player_economic.parquet.
    Devuelve None si el archivo no existe o está corrupto.
    """
    if not force and not _is_stale("economic", ECONOMIC_PATH):
        return _STATE["economic"]["df"]

    if not ECONOMIC_PATH.exists():
        return None

    t0 = time.monotonic()
    try:
        df = pd.read_parquet(ECONOMIC_PATH)
    except Exception as e:
        print(f"[data_cache] player_economic.parquet error: {e}")
        _STATE["economic"]["df"] = None
        return None

    _STATE["economic"]["df"]    = df
    _STATE["economic"]["mtime"] = _file_mtime(ECONOMIC_PATH)
    _STATE["economic"]["t"]     = time.monotonic()

    elapsed = time.monotonic() - t0
    print(f"[data_cache] player_economic cargado: {len(df):,} filas ({elapsed:.2f}s)")
    return df


# ---------------------------------------------------------------------------
# player_seasons_enriched (usado por comparador)
# ---------------------------------------------------------------------------
def get_enriched(force: bool = False) -> Optional[pd.DataFrame]:
    """
    Devuelve player_seasons_enriched.parquet completo.
    """
    if not force and not _is_stale("enriched", ENRICHED_PATH):
        return _STATE["enriched"]["df"]

    if not ENRICHED_PATH.exists():
        return None

    t0 = time.monotonic()
    try:
        df = pd.read_parquet(ENRICHED_PATH)
    except Exception as e:
        print(f"[data_cache] player_seasons_enriched.parquet error: {e}")
        _STATE["enriched"]["df"] = None
        return None

    _STATE["enriched"]["df"]    = df
    _STATE["enriched"]["mtime"] = _file_mtime(ENRICHED_PATH)
    _STATE["enriched"]["t"]     = time.monotonic()

    elapsed = time.monotonic() - t0
    print(f"[data_cache] player_seasons_enriched cargado: {len(df):,} filas ({elapsed:.2f}s)")
    return df


# ---------------------------------------------------------------------------
# Precalentamiento al inicio (llamar desde app.py)
# ---------------------------------------------------------------------------
def warmup() -> None:
    """
    Precarga todos los datasets en memoria al iniciar la app.
    Llamar desde app.py antes de server.run() para que el primer
    usuario no sufra la latencia de carga.
    """
    print("[data_cache] Precargando datos...")
    get_master(force=True)
    get_economic(force=True)
    # No precargamos enriched (12MB) salvo que comparador lo necesite al inicio
    print("[data_cache] Precarga completada.")
