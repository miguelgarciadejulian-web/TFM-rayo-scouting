"""
logging.py — Sistema de logging unificado para toda la aplicación
=================================================================

PROPÓSITO:
    Proporciona un logger configurado con formato consistente para todos
    los módulos del proyecto. Centraliza la configuración de niveles,
    formato de timestamp y salida por consola.

FORMATO DE SALIDA:
    2024-01-15 10:30:45 | INFO    | rayo.scouting | Mensaje aquí

FUNCIÓN PRINCIPAL:
    get_logger(name, level) → logging.Logger configurado

USO:
    from src.utils.logging import get_logger
    log = get_logger("mi_modulo")
    log.info("Procesando datos...")
"""
import logging
import sys

_FMT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


def get_logger(name: str = "rayo", level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(level)
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter(_FMT))
    logger.addHandler(h)
    return logger
