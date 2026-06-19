# -*- coding: utf-8 -*-
"""
market.py  v2
=============
Carga de datos economicos y contractuales de jugadores.

ARQUITECTURA v2:
  get_value(name, opta_id=None) consulta primero player_economic.parquet
  con fallback a market_values.csv para compatibilidad total.

  Jerarquia de prioridad:
    1. player_overrides.json    (correcciones manuales)
    2. player_economic.parquet  (dataset economico separado, si existe)
    3. market_values.csv        (fuente legacy, siempre disponible)

COMPATIBILIDAD: la firma get_value(name) es identica a v1.
"""
from __future__ import annotations
import unicodedata
from functools import lru_cache
from pathlib import Path

import pandas as pd

ROOT             = Path(__file__).resolve().parents[2]
MV_CSV           = ROOT / "config" / "market_values.csv"
PLAYER_OVERRIDES = ROOT / "data" / "processed" / "player_overrides.json"
ECONOMIC_PARQUET = ROOT / "data" / "processed" / "player_economic.parquet"

BIG_CLUBS = {
    "real madrid", "fc barcelona", "barcelona", "atletico de madrid", "atletico de madrid",
    "club atletico de madrid", "manchester city", "manchester united", "liverpool",
    "chelsea", "arsenal", "tottenham", "paris saint-germain", "psg", "bayern",
    "bayern munich", "fc bayern", "borussia dortmund", "juventus", "inter", "internazionale",
    "ac milan", "milan", "napoli", "as roma", "newcastle", "aston villa",
}


def _norm(s) -> str:
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().strip()


def _surname(name) -> str:
    n = _norm(name).replace(".", " ")
    parts = [p for p in n.split() if len(p) > 1]
    return parts[-1] if parts else n


def _s(v):
    if v is None:
        return None
    s = str(v).strip()
    return s if s not in ("", "nan", "None", "<NA>") else None


def _f(v):
    try:
        f = float(v)
        return f if not pd.isna(f) else None
    except (TypeError, ValueError):
        return None


def is_big_club(team) -> bool:
    t = _norm(team)
    return any(b in t for b in BIG_CLUBS)


def load_overrides() -> dict:
    """Datos de mercado introducidos a mano por el usuario."""
    import json
    if PLAYER_OVERRIDES.exists():
        try:
            return json.load(open(PLAYER_OVERRIDES, encoding="utf-8"))
        except Exception:
            return {}
    return {}


@lru_cache(maxsize=1)
def _load_economic_parquet():
    if not ECONOMIC_PARQUET.exists():
        return None
    try:
        return pd.read_parquet(ECONOMIC_PARQUET)
    except Exception:
        return None


@lru_cache(maxsize=1)
def load_market_values() -> dict:
    """Devuelve {nombre_normalizado: {...}} de market_values.csv."""
    if not MV_CSV.exists():
        return {}
    try:
        df = pd.read_csv(MV_CSV)
    except Exception:
        return {}
    out = {}
    for _, r in df.iterrows():
        key = _norm(r.get("name", ""))
        if not key:
            continue
        tm_id = None
        raw_tm = str(r.get("tm_id", "")).replace(".0", "")
        if raw_tm.isdigit():
            tm_id = raw_tm
        out[key] = {
            "name":          r.get("name"),
            "value_eur":     _f(r.get("market_value_eur")),
            "contract_until": _s(r.get("contract_until")),
            "photo_url":     _s(r.get("tm_photo_url")),
            "tm_id":         tm_id,
            "age":      _s(r.get("age")),
            "foot":     _s(r.get("foot")),
            "height":   _s(r.get("height")),
            "position": _s(r.get("position")),
            "dob":      _s(r.get("dob")),
            "data_source":  "transfermarkt",
            "last_updated": None,
            "match_confidence": None,
        }
    return out


@lru_cache(maxsize=1)
def _load_economic_dict():
    """Devuelve (by_name, by_opta_id) desde player_economic.parquet."""
    df = _load_economic_parquet()
    if df is None:
        return {}, {}
    by_name = {}
    by_opta = {}
    for _, r in df.iterrows():
        rec = {
            "name":               _s(r.get("display_name") or r.get("canonical_name")),
            "value_eur":          _f(r.get("market_value_eur")),
            "contract_until":     _s(r.get("contract_until")),
            "release_clause_eur": _f(r.get("release_clause_eur")),
            "salary_eur_year":    _f(r.get("salary_eur_year")),
            "photo_url":          _s(r.get("photo_url")),
            "tm_id":              _s(r.get("tm_id")),
            "age":                _s(r.get("age")),
            "foot":               _s(r.get("foot")),
            "height":             _s(r.get("height")),
            "position":           _s(r.get("position_tm")),
            "dob":                _s(r.get("dob")),
            "nationality":        _s(r.get("nationality")),
            "club":               _s(r.get("club")),
            "data_source":        _s(r.get("data_source")),
            "last_updated":       _s(r.get("last_updated")),
            "match_confidence":   _f(r.get("match_confidence")),
        }
        cn = _s(r.get("canonical_name", ""))
        if cn:
            by_name[cn] = rec
        oid = _s(r.get("opta_id", ""))
        if oid:
            by_opta[oid] = rec
    return by_name, by_opta


def _get_from_economic(name, opta_id=None) -> dict:
    result = _load_economic_dict()
    if not result or not isinstance(result, tuple):
        return {}
    by_name, by_opta = result
    if opta_id and opta_id in by_opta:
        return by_opta[opta_id]
    nn = _norm(name)
    if nn in by_name:
        return by_name[nn]
    # Surname matching con initial-guard (mismo algoritmo que _match_market)
    sn = _surname(name)
    parts = [p for p in nn.split() if p]
    first_initial = parts[0][0] if parts else None
    is_single = len(parts) == 1
    sn_hits = [(k, v) for k, v in by_name.items() if _surname(k) == sn]
    if first_initial and sn_hits:
        confirmed = [(k, v) for k, v in sn_hits
                     if (k.split() or [""])[0][:1] == first_initial]
        if len(confirmed) == 1:
            return dict(confirmed[0][1])
    elif is_single and sn_hits:
        if len(sn_hits) == 1:
            return dict(sn_hits[0][1])
    return {}


def _match_market(nn: str, sn: str, mv: dict) -> dict:
    """
    Matching con initial-guard para evitar falsos positivos por apellido.

    Algoritmo (en orden de precisión):
      1. Coincidencia exacta (nombre normalizado).
      2. Apellido único + inicial del primer nombre confirma.
      3. Nombre de una sola palabra → prefijo en base TM (e.g. "Yeray" → "Yeray Álvarez").
    """
    # 1. Exacta
    if nn in mv:
        return dict(mv[nn])

    parts = [p for p in nn.split() if p]
    first_initial = parts[0][0] if parts else None
    is_single = len(parts) == 1

    # 2. Apellido con confirmación de inicial
    if first_initial:
        sn_hits = [(k, v) for k, v in mv.items() if _surname(k) == sn]
        # Filtrar por inicial del primer token del nombre TM
        confirmed = [(k, v) for k, v in sn_hits
                     if (k.split() or [""])[0][:1] == first_initial]
        if len(confirmed) == 1:
            return dict(confirmed[0][1])

    # 3. Prefijo para nombres de una sola palabra ("Yeray", "Pedri", "Yuri"…)
    if is_single:
        prefix_hits = [(k, v) for k, v in mv.items() if k.startswith(nn + " ")]
        if len(prefix_hits) == 1:
            return dict(prefix_hits[0][1])

    return {}


def get_value(name, opta_id=None) -> dict:
    """
    Devuelve datos economicos/contractuales del jugador.
    Prioridad: player_overrides.json > player_economic.parquet > market_values.csv
    """
    mv = load_market_values()
    nn = _norm(name)
    sn = _surname(name)

    # 3. Fallback legacy: market_values.csv (matching mejorado)
    legacy = _match_market(nn, sn, mv)

    # 2. Parquet economico (sobreescribe legacy si tiene valor)
    econ = _get_from_economic(name, opta_id)
    merged = dict(legacy)
    for fld, val in econ.items():
        if val is not None:
            merged[fld] = val

    # 1. Overrides manuales (prioridad maxima)
    ov = load_overrides().get(nn)
    if ov:
        for fld in ("value_eur", "contract_until", "photo_url", "age",
                    "foot", "height", "position", "release_clause_eur", "salary_eur_year"):
            if ov.get(fld) not in (None, ""):
                merged[fld] = ov[fld]
        merged["data_source"] = "manual"

    return merged


def expires_soon(contract_until, years=1) -> bool:
    if not contract_until:
        return False
    from datetime import date
    try:
        year = int(str(contract_until)[:4])
        return year <= date.today().year + years
    except (ValueError, TypeError):
        return False


def expires_2026(contract_until) -> bool:
    if not contract_until:
        return False
    return str(contract_until)[:4] in ("2026",)


def invalidate_cache() -> None:
    load_market_values.cache_clear()
    _load_economic_parquet.cache_clear()
    _load_economic_dict.cache_clear()
