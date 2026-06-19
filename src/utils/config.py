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
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


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
