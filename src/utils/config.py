# -*- coding: utf-8 -*-
"""Carga de configuración YAML y rutas resueltas."""
from __future__ import annotations
import os
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"


def load_yaml(name: str) -> dict:
    path = CONFIG_DIR / name
    # Lectura tolerante: si una escritura previa dejo bytes nulos en el archivo
    # (corrupcion por escritura interrumpida), los descartamos en lugar de fallar.
    raw = path.read_bytes()
    if b"\x00" in raw:
        raw = raw.replace(b"\x00", b"")
    return yaml.safe_load(raw.decode("utf-8", "ignore"))


def settings() -> dict:
    s = load_yaml("settings.yaml")
    # Resolver rutas relativas a la raíz del proyecto
    for k, v in s.get("paths", {}).items():
        s["paths"][k] = str((ROOT / v).resolve())
    return s


def club_profile() -> dict:
    return load_yaml("club_profile.yaml")


def scouting_profiles() -> dict:
    return load_yaml("scouting_profiles.yaml")
