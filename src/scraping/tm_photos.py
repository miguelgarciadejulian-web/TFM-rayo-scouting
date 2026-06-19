# -*- coding: utf-8 -*-
"""
Obtiene la URL de la foto de un jugador en Transfermarkt a partir de su nombre.
Los resultados se cachean en data/external/cache/tm_photos.json para no
repetir peticiones.

Uso:
    from src.scraping.tm_photos import get_photo_url
    url = get_photo_url("Isi Palazón", team="Rayo Vallecano")
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT       = Path(__file__).resolve().parents[2]
CACHE_FILE = ROOT / "data" / "external" / "cache" / "tm_photos.json"
CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Referer": "https://www.transfermarkt.com/",
}

# URL base de fotos de Transfermarkt
TM_PHOTO_BASE = "https://img.a.transfermarkt.technology/portrait/medium/{tm_id}.jpg?lm=1"
TM_PHOTO_BIG  = "https://img.a.transfermarkt.technology/portrait/big/{tm_id}.jpg?lm=1"
TM_SEARCH_URL = "https://www.transfermarkt.com/schnellsuche/ergebnis/schnellsuche"


def _load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _search_tm(name: str, team: str | None = None) -> dict | None:
    """Busca el jugador en Transfermarkt y devuelve {tm_id, photo_url, tm_url}."""
    query = f"{name} {team}" if team else name
    try:
        r = requests.get(
            TM_SEARCH_URL,
            params={"query": query, "Spieler_page": "0"},
            headers=HEADERS,
            timeout=8,
        )
        r.raise_for_status()
    except Exception as e:
        print(f"[tm_photos] Error de red buscando '{name}': {e}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    # Primer resultado de jugador en la tabla
    row = soup.select_one("table.items tbody tr")
    if not row:
        # Intentar sin equipo si la búsqueda compuesta no devuelve nada
        if team:
            time.sleep(0.5)
            return _search_tm(name)
        return None

    # Foto
    img = row.select_one("img.bilderrahmen-fixed, td.hauptlink img")
    photo_url = None
    if img:
        raw = img.get("data-src") or img.get("src") or ""
        # Extraer tm_id de la URL de la miniatura
        import re
        m = re.search(r"/portrait/(?:small|medium|big)/(\d+)", raw)
        if m:
            tm_id    = m.group(1)
            photo_url = TM_PHOTO_BIG.format(tm_id=tm_id)
        else:
            photo_url = raw

    # URL del perfil
    link = row.select_one("td.hauptlink a")
    tm_url = f"https://www.transfermarkt.com{link['href']}" if link and link.get("href") else None

    return {"photo_url": photo_url, "tm_url": tm_url}


def get_photo_url(name: str, team: str | None = None, force: bool = False) -> str | None:
    """
    Devuelve la URL de la foto del jugador en Transfermarkt.
    Usa caché local para evitar peticiones repetidas.

    Args:
        name:  Nombre del jugador.
        team:  Equipo (mejora la búsqueda, opcional).
        force: Si True, ignora la caché y hace la petición de nuevo.
    """
    cache = _load_cache()
    key   = f"{name}|{team or ''}"

    if not force and key in cache:
        return cache[key].get("photo_url")

    time.sleep(0.3)   # rate limiting cortés
    result = _search_tm(name, team)
    if result:
        cache[key] = result
        _save_cache(cache)
        return result.get("photo_url")

    # NO cacheamos los fallos: así se reintenta en la siguiente carga.
    return None
