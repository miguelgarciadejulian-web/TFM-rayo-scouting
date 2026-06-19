"""
fetch_tm_search.py
==================
Busca tm_id para los jugadores OPTA que NO estan en player_entity_map.csv.

La API alpha de TM (tmapi-alpha.transfermarkt.technology) solo expone /player/{id}.
Para BUSCAR jugadores por nombre hay que ir a la web de TM.

Estrategia:
  FASE 1: Fuzzy matching vs market_values.csv (sin red, rapido)
  FASE 2: Busqueda via TM website HTML (schnellsuche)
  FASE 3: Busqueda via TM autocomplete JSON (fallback)

Uso:
    pip install rapidfuzz requests pandas beautifulsoup4
    python scripts/fetch_tm_search.py --test-api          # diagnostico previo
    python scripts/fetch_tm_search.py --phase 2 --limit 50 --verbose  # prueba
    python scripts/fetch_tm_search.py --limit 500 --min-minutes 500   # full run
    python scripts/fetch_tm_search.py --dry-run           # sin escribir disco
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

# ── Rutas ────────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).resolve().parents[1]
MASTER_PQ   = ROOT / "data" / "processed" / "master_players.parquet"
MV_CSV      = ROOT / "config" / "market_values.csv"
ENTITY_MAP  = ROOT / "data" / "processed" / "player_entity_map.csv"
RAW_JSON    = ROOT / "data" / "processed" / "tm_api_raw.json"

TM_ALPHA_BASE = "https://tmapi-alpha.transfermarkt.technology"
TM_WEB_BASE   = "https://www.transfermarkt.com"
REQUEST_DELAY = 1.2   # cortesia al servidor
TIMEOUT       = 20
FUZZY_THRESHOLD = 82
CURRENT_SEASONS = {"2026", "2025-2026", "2025/2026"}

HEADERS_ALPHA = {
    "User-Agent": "Mozilla/5.0 (compatible; RayoScoutingTool/1.0)",
    "Accept":     "application/json",
}
HEADERS_WEB = {
    "User-Agent":    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                     " (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept":        "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":       "https://www.transfermarkt.com/",
}
HEADERS_WEB_JSON = {
    **HEADERS_WEB,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
}


# ── Normalización ─────────────────────────────────────────────────────────────
def _norm(s: str) -> str:
    return (
        unicodedata.normalize("NFKD", str(s))
        .encode("ascii", "ignore")
        .decode().lower().strip()
    )

def _surname(name: str) -> str:
    n = _norm(name).replace(".", " ")
    parts = [p for p in n.split() if len(p) > 1]
    return parts[-1] if parts else n

def _expand_opta_name(opta_name: str) -> list[str]:
    n = opta_name.strip()
    parts = n.split()
    if len(parts) >= 2 and re.match(r"^[A-Za-z]\.$", parts[0]):
        surname_part = " ".join(parts[1:])
        return [surname_part, n, parts[0].rstrip(".") + " " + surname_part]
    return [n]

def _tm_id_from_url(url: str | None) -> str | None:
    if not url:
        return None
    m = re.search(r"/portrait/(?:big|small|medium|header)/(\d+)-", str(url))
    if m:
        return m.group(1)
    m = re.search(r"/spieler/(\d+)", str(url))
    return m.group(1) if m else None


# ── Carga de datos ────────────────────────────────────────────────────────────
def load_entity_map() -> pd.DataFrame:
    return pd.read_csv(ENTITY_MAP, dtype={"tm_id": str})

def load_master_players() -> pd.DataFrame:
    df = pd.read_parquet(MASTER_PQ)
    current = df[df["season"].isin(CURRENT_SEASONS)].copy()
    agg = (
        current.groupby(["player_id", "name", "team", "league", "position_primary"])
        .agg(minutes=("minutes", "sum")).reset_index()
    )
    return agg.sort_values("minutes", ascending=False).drop_duplicates("player_id")

def load_market_values() -> pd.DataFrame:
    mv = pd.read_csv(MV_CSV, dtype={"tm_id": str})
    def _clean_tid(x):
        s = str(x or "").strip()
        return str(int(float(s))) if s.replace(".", "").isdigit() else None
    mv["tm_id"]    = mv["tm_id"].apply(_clean_tid)
    mv["_norm"]    = mv["name"].apply(_norm)
    mv["_surname"] = mv["name"].apply(_surname)
    return mv

def load_raw_cache() -> dict:
    if RAW_JSON.exists():
        try:
            return json.loads(RAW_JSON.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def get_unmatched(em: pd.DataFrame, master: pd.DataFrame, min_minutes: int) -> pd.DataFrame:
    unmatched_ids = set(em[em["tm_id"].isna()]["opta_id"].tolist())
    sub = master[master["player_id"].isin(unmatched_ids)].copy()
    sub = sub[sub["minutes"] >= min_minutes]
    em_sub = em[em["opta_id"].isin(sub["player_id"].tolist())][
        ["opta_id", "opta_name", "canonical_name"]
    ]
    merged = sub.merge(em_sub, left_on="player_id", right_on="opta_id", how="left")
    return merged.sort_values("minutes", ascending=False)


# ── Fase 1: Fuzzy matching vs market_values.csv ───────────────────────────────
def phase1_fuzzy(
    unmatched: pd.DataFrame, mv: pd.DataFrame, dry_run: bool, verbose: bool
) -> dict[str, tuple[str, str, float]]:
    try:
        from rapidfuzz import fuzz
    except ImportError:
        print("[FASE 1] Instala: pip install rapidfuzz")
        return {}

    print("\n" + "=" * 60)
    print(f"FASE 1 — Fuzzy vs market_values.csv ({len(mv):,} entradas)")
    print("=" * 60)

    mv_with_id = mv[mv["tm_id"].notna()].copy()

    def _fl(name: str) -> str:
        parts = _norm(name).replace(".", " ").split()
        return parts[0][0] if parts else ""

    mv_with_id["_fl"] = mv_with_id["name"].apply(_fl)
    mv_with_id["_sn"] = mv_with_id["name"].apply(_surname)

    results: dict[str, tuple[str, str, float]] = {}
    found = 0

    for _, row in unmatched.iterrows():
        opta_id  = row["player_id"]
        opta_raw = str(row.get("opta_name") or row.get("name") or "")
        team     = str(row.get("team") or "")
        mins     = float(row.get("minutes") or 0)

        parts_opta  = opta_raw.strip().split()
        has_initial = len(parts_opta) >= 2 and re.match(r"^[A-Za-z]\.$", parts_opta[0])
        opta_initial = _norm(parts_opta[0]).rstrip(".") if has_initial else None
        opta_surname = _norm(" ".join(parts_opta[1:])) if has_initial else _norm(opta_raw)

        candidates = mv_with_id[mv_with_id["_fl"] == opta_initial] if has_initial else mv_with_id
        best_score  = 0.0
        best_tm_row = None

        for _, mv_row in candidates.iterrows():
            sn_score = fuzz.token_sort_ratio(opta_surname, mv_row["_sn"])
            if sn_score < FUZZY_THRESHOLD:
                continue
            full_score = fuzz.token_sort_ratio(
                _norm(opta_raw).replace(".", ""), _norm(mv_row["name"])
            )
            combined = sn_score * 0.6 + full_score * 0.4
            if combined > best_score:
                best_score, best_tm_row = combined, mv_row

        if best_tm_row is not None and best_score >= FUZZY_THRESHOLD:
            tm_id   = str(best_tm_row["tm_id"])
            tm_name = str(best_tm_row["name"])
            if verbose:
                print(f"  OK '{opta_raw}' ({team}, {mins:.0f}min) -> '{tm_name}' [{tm_id}] {best_score:.0f}")
            results[opta_id] = (tm_id, tm_name, best_score)
            found += 1

    print(f"[FASE 1] Matchados: {found:,} / {len(unmatched):,}")
    return results


# ── Busqueda en TM website ─────────────────────────────────────────────────────
def _search_tm_schnellsuche(session: requests.Session, query: str, verbose: bool = False) -> list[dict]:
    """
    Busca en la pagina HTML de Transfermarkt y extrae pares (tm_id, nombre).
    Endpoint: /schnellsuche/ergebnis/schnellsuche?query=QUERY&Kat=Spieler
    """
    url = f"{TM_WEB_BASE}/schnellsuche/ergebnis/schnellsuche"
    try:
        r = session.get(
            url,
            headers=HEADERS_WEB,
            params={"query": query, "Kat": "Spieler"},
            timeout=TIMEOUT,
            allow_redirects=True,
        )
        if not r.ok:
            if verbose:
                print(f"    [HTTP {r.status_code}] para query='{query}'")
            return []

        text = r.text
        candidates = []

        # Patron principal: href="/nombre/profil/spieler/123456"
        for m in re.finditer(r'href="/([^"]+)/profil/spieler/(\d+)"[^>]*>([^<]+)</a>', text, re.I):
            slug, tid, name = m.group(1), m.group(2), m.group(3).strip()
            if name and name not in ("<", ">"):
                candidates.append({"id": tid, "name": name, "slug": slug})

        # Patron alternativo: datos en table de resultados
        if not candidates:
            for m in re.finditer(r'/profil/spieler/(\d+)', text):
                tid = m.group(1)
                if {"id": tid, "name": ""} not in candidates:
                    candidates.append({"id": tid, "name": ""})

        if verbose:
            print(f"    [HTTP {r.status_code}] query='{query}' -> {len(candidates)} candidatos")
        return candidates[:10]

    except requests.RequestException as e:
        if verbose:
            print(f"    [ERR] schnellsuche '{query}': {type(e).__name__}")
        return []


def _search_tm_autocomplete(session: requests.Session, query: str, verbose: bool = False) -> list[dict]:
    """
    Intenta el endpoint de autocompletado JSON de TM.
    """
    endpoints = [
        f"{TM_WEB_BASE}/ceapi/market/ajax/topangebote?query={requests.utils.quote(query)}&type=players",
        f"{TM_WEB_BASE}/_/api/players/search?query={requests.utils.quote(query)}",
        f"{TM_WEB_BASE}/schnellsuche/ergebnis/schnellsuche?query={requests.utils.quote(query)}&Kat=Spieler&jsonResponse=true",
    ]
    for url in endpoints:
        try:
            r = session.get(url, headers=HEADERS_WEB_JSON, timeout=TIMEOUT)
            if r.ok and "application/json" in r.headers.get("content-type", ""):
                data = r.json()
                if isinstance(data, list) and data:
                    return data[:10]
                if isinstance(data, dict):
                    for key in ("players", "results", "suggestions", "data"):
                        val = data.get(key)
                        if isinstance(val, list) and val:
                            return val[:10]
        except requests.RequestException:
            continue
    return []


def _validate_candidate(candidate: dict, opta_name: str, team: str, position: str) -> float:
    """
    Puntua un candidato TM (0-100) por similitud nombre + equipo + posicion.
    Regla DURA: si OPTA tiene inicial (ej. "L. Palmer"), el nombre TM
    debe empezar por esa misma letra. Si no, score=0 (descartado).
    """
    cand_name = str(candidate.get("name") or candidate.get("displayName") or "")
    if not cand_name:
        return 40.0  # id sin nombre = puntuacion baja pero no 0

    # ── Validacion de inicial: "L. Palmer" → primer token del nombre TM debe ser "L*"
    opta_parts = opta_name.strip().split()
    if len(opta_parts) >= 2 and re.match(r"^[A-Za-z]\.$", opta_parts[0]):
        required_initial = _norm(opta_parts[0]).rstrip(".")  # "l"
        cand_parts = _norm(cand_name).replace(".", " ").split()
        cand_first_letter = cand_parts[0][0] if cand_parts else ""
        if cand_first_letter != required_initial:
            return 0.0  # inicial incorrecta → rechazar

    try:
        from rapidfuzz import fuzz
        name_score = fuzz.token_sort_ratio(_norm(opta_name), _norm(cand_name))
    except ImportError:
        name_score = 60.0

    score = name_score * 0.65

    cand_team = str(candidate.get("team") or candidate.get("club") or
                    candidate.get("clubName") or "")
    if cand_team and team:
        try:
            from rapidfuzz import fuzz as _f
            score += _f.partial_ratio(_norm(team), _norm(cand_team)) * 0.25
        except ImportError:
            score += 25.0
    else:
        score += 25.0  # sin info de equipo: bonus neutro

    pos_map = {
        "GK": "goalkeeper", "CB": "defender", "RB": "defender", "LB": "defender",
        "CM": "midfielder", "AM": "midfielder", "DM": "midfielder",
        "LW": "forward",   "RW": "forward",   "ST": "forward",  "CF": "forward",
    }
    cand_pos = str(candidate.get("position") or candidate.get("positionGroupName") or "")
    expected = pos_map.get(position.upper(), "")
    if expected and expected in _norm(cand_pos):
        score += 10.0

    return min(score, 100.0)


def _get_tm_id_from_candidate(c: dict) -> str | None:
    for key in ("id", "tm_id", "spielerId", "playerId"):
        v = c.get(key)
        if v and str(v).isdigit():
            return str(v)
    for key in ("url", "href", "relativeUrl"):
        v = c.get(key)
        if v:
            tid = _tm_id_from_url(str(v))
            if tid:
                return tid
    return None


def _fetch_and_validate_by_id(tm_id: str, session: requests.Session, opta_name: str) -> tuple[str, float] | tuple[None, float]:
    """
    Dado un tm_id candidato, llama al API para verificar nombre y devuelve (nombre_tm, score).
    """
    url = f"{TM_ALPHA_BASE}/player/{tm_id}"
    try:
        r = session.get(url, headers=HEADERS_ALPHA, timeout=TIMEOUT)
        time.sleep(0.3)
        if r.ok:
            d = r.json().get("data", {})
            name_tm = d.get("name") or d.get("shortName") or ""
            if not name_tm:
                return None, 0.0
            try:
                from rapidfuzz import fuzz
                score = fuzz.token_sort_ratio(_norm(opta_name), _norm(name_tm))
            except ImportError:
                score = 70.0
            return name_tm, float(score)
    except requests.RequestException:
        pass
    return None, 0.0


# ── Motor de busqueda ──────────────────────────────────────────────────────────
def search_player_tm_id(
    opta_name: str,
    team: str,
    position: str,
    session: requests.Session,
    verbose: bool = False,
    validate_via_api: bool = True,
) -> tuple[str | None, str, float]:
    """
    Busca el tm_id de un jugador usando TM website.
    Devuelve (tm_id, tm_name, score) o (None, '', 0).
    """
    queries = _expand_opta_name(opta_name)
    best_tm_id   = None
    best_tm_name = ""
    best_score   = 0.0

    for q in queries:
        # Busqueda HTML
        candidates = _search_tm_schnellsuche(session, q, verbose=verbose)

        # Si no hay resultados, intentar autocomplete JSON
        if not candidates:
            candidates = _search_tm_autocomplete(session, q, verbose=verbose)

        for cand in candidates[:8]:
            base_score = _validate_candidate(cand, opta_name, team, position)
            if base_score < 55:
                continue

            tm_id = _get_tm_id_from_candidate(cand)
            if not tm_id:
                continue

            # Validar via API para confirmar nombre real
            if validate_via_api and not cand.get("name"):
                name_tm, api_score = _fetch_and_validate_by_id(tm_id, session, opta_name)
                if not name_tm:
                    continue
                cand["name"] = name_tm
                base_score = max(base_score, api_score * 0.8)

            if base_score > best_score:
                best_score   = base_score
                best_tm_id   = tm_id
                best_tm_name = str(cand.get("name") or "")

        if best_score >= 80:
            break  # suficientemente bueno

    return best_tm_id, best_tm_name, best_score


# ── Fase 2: TM Website Search ──────────────────────────────────────────────────
def phase2_web_search(
    unmatched: pd.DataFrame,
    session: requests.Session,
    limit: int,
    min_score: float,
    dry_run: bool,
    verbose: bool,
) -> dict[str, tuple[str, str, float]]:
    print("\n" + "=" * 60)
    print(f"FASE 2 — TM Website Search (hasta {limit} busquedas)")
    print("=" * 60)

    results: dict[str, tuple[str, str, float]] = {}
    calls = 0
    found = 0

    for _, row in unmatched.iterrows():
        if calls >= limit:
            print(f"[FASE 2] Limite {limit} alcanzado.")
            break

        opta_id  = row["player_id"]
        opta_raw = str(row.get("opta_name") or row.get("name") or "")
        team     = str(row.get("team") or "")
        pos      = str(row.get("position_primary") or "")
        mins     = float(row.get("minutes") or 0)

        tm_id, tm_name, score = search_player_tm_id(
            opta_raw, team, pos, session, verbose=verbose
        )
        calls += 1
        time.sleep(REQUEST_DELAY)

        if tm_id and score >= min_score:
            if verbose:
                print(f"  OK '{opta_raw}' ({team}, {mins:.0f}min)"
                      f" -> '{tm_name}' [{tm_id}] score={score:.0f}")
            results[opta_id] = (tm_id, tm_name, score)
            found += 1
        elif verbose:
            print(f"  X  '{opta_raw}' ({team}, {mins:.0f}min) score={score:.0f}")

    print(f"[FASE 2] Matchados: {found:,} | Busquedas: {calls:,}")
    return results


# ── Aplicar resultados ─────────────────────────────────────────────────────────
def apply_results(
    results: dict[str, tuple[str, str, float]],
    em: pd.DataFrame,
    label: str,
    dry_run: bool,
) -> pd.DataFrame:
    if not results:
        return em
    updated = 0
    for opta_id, (tm_id, tm_name, score) in results.items():
        mask = em["opta_id"] == opta_id
        if mask.any():
            em.loc[mask, "tm_id"]            = tm_id
            em.loc[mask, "tm_name"]          = tm_name
            em.loc[mask, "match_type"]       = f"search_{label}"
            em.loc[mask, "match_confidence"] = round(score, 1)
            em.loc[mask, "last_verified"]    = datetime.now().strftime("%Y-%m-%d")
            updated += 1
    print(f"[{label}] entity_map: +{updated} matches")
    if not dry_run:
        em.to_csv(ENTITY_MAP, index=False)
        print(f"  Guardado: {ENTITY_MAP}")
    else:
        print("  [dry-run] Sin cambios.")
    return em


def fetch_economic_data(new_tm_ids: list[str], session: requests.Session, dry_run: bool):
    if not new_tm_ids:
        return
    print("\n" + "=" * 60)
    print(f"FETCH ECONOMICO — {len(new_tm_ids):,} jugadores nuevos")
    print("=" * 60)

    raw_cache = load_raw_cache()
    new_rows: list[dict] = []
    fetched = 0

    for tm_id in new_tm_ids:
        if str(tm_id) in raw_cache:
            continue
        url = f"{TM_ALPHA_BASE}/player/{tm_id}"
        try:
            r = session.get(url, headers=HEADERS_ALPHA, timeout=TIMEOUT)
            time.sleep(REQUEST_DELAY)
            if r.ok:
                data = r.json()
                raw_cache[str(tm_id)] = data
                d = data.get("data", data)
                mv_val = None
                try:
                    mv_val = float(d.get("marketValueDetails", {}).get("current", {}).get("value") or 0) or None
                except (TypeError, ValueError):
                    pass
                position = d.get("attributes", {}).get("positionGroupName") or ""
                if isinstance(position, dict):
                    position = position.get("name", "")
                name_tm = d.get("name") or d.get("shortName", "")
                attrs = d.get("attributes", {})
                ca = d.get("clubAssignments", [])
                current_club = next(
                    (x for x in ca if isinstance(ca, list) and x.get("type") == "current"),
                    ca[0] if ca else {}
                )
                dob_raw = d.get("lifeDates", {}).get("dateOfBirth")
                dob_str = dob_raw[:10] if isinstance(dob_raw, str) and dob_raw else None
                mv_prev_val = mv_high_val = None
                try:
                    mv_prev_val = float(d.get("marketValueDetails", {}).get("previous", {}).get("value") or 0) or None
                    mv_high_val = float(d.get("marketValueDetails", {}).get("highest", {}).get("value") or 0) or None
                except (TypeError, ValueError):
                    pass
                new_rows.append({
                    "name":                 name_tm,
                    "market_value_eur":     mv_val,
                    "market_value_prev":    mv_prev_val,
                    "market_value_highest": mv_high_val,
                    "contract_until":       attrs.get("contractUntil"),
                    "tm_photo_url":         d.get("portraitUrl"),
                    "tm_id":                tm_id,
                    "age":                  d.get("lifeDates", {}).get("age"),
                    "foot":                 (attrs.get("preferredFoot") or {}).get("name", ""),
                    "height":               attrs.get("height"),
                    "position":             position,
                    "dob":                  dob_str,
                    "alt_position_1":       (attrs.get("firstSidePosition") or {}).get("name"),
                    "alt_position_2":       (attrs.get("secondSidePosition") or {}).get("name"),
                    "birthplace":           d.get("birthPlaceDetails", {}).get("placeOfBirth"),
                    "shirt_number":         current_club.get("shirtNumber"),
                })
                fetched += 1
                print(f"  OK tm_id={tm_id} | {name_tm} | VM={mv_val}")
            elif r.status_code == 429:
                print("  [429] Rate limit — esperando 15s...")
                time.sleep(15)
        except requests.RequestException as e:
            print(f"  [ERR] {tm_id}: {e}")

    print(f"Enriquecidos: {fetched:,}")
    if dry_run:
        print("[dry-run] Sin cambios en disco.")
        return

    if fetched > 0:
        RAW_JSON.write_text(
            json.dumps(raw_cache, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    if new_rows:
        mv_df = pd.read_csv(MV_CSV, dtype={"tm_id": str})
        existing = set(mv_df["tm_id"].dropna().astype(str))
        new_mv = pd.DataFrame(new_rows)
        new_mv = new_mv[~new_mv["tm_id"].isin(existing)]
        if not new_mv.empty:
            mv_df = pd.concat([mv_df, new_mv], ignore_index=True)
            mv_df.to_csv(MV_CSV, index=False)
            print(f"  market_values.csv: +{len(new_mv)} filas")

    try:
        import subprocess
        res = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "fetch_tm_api.py")],
            cwd=str(ROOT), capture_output=True, text=True, timeout=300,
        )
        if res.returncode == 0:
            print("  player_economic.parquet actualizado")
        else:
            print(f"  [WARN] fetch_tm_api.py exit={res.returncode}")
            if res.stderr:
                print("  [STDERR]", res.stderr[-800:])
    except Exception as e:
        print(f"  [WARN] Ejecuta manualmente: python scripts/fetch_tm_api.py ({e})")


# ── Test de conectividad ───────────────────────────────────────────────────────
def test_api_connectivity():
    print("=" * 60)
    print("TEST DE CONECTIVIDAD")
    print("Caso de prueba: 'Pickford' (tm_id=130164 conocido)")
    print("=" * 60)
    session = requests.Session()

    print("\n[1] GET /player/130164 (API directa — debe funcionar):")
    try:
        r = session.get(f"{TM_ALPHA_BASE}/player/130164", headers=HEADERS_ALPHA, timeout=10)
        d = r.json().get("data", {})
        print(f"    HTTP {r.status_code} -> nombre: {d.get('name', '?')}")
    except Exception as e:
        print(f"    ERROR: {e}")

    print("\n[2] TM web schnellsuche HTML (busqueda de jugador):")
    try:
        r = session.get(
            f"{TM_WEB_BASE}/schnellsuche/ergebnis/schnellsuche",
            headers=HEADERS_WEB,
            params={"query": "Pickford", "Kat": "Spieler"},
            timeout=10,
        )
        ids = re.findall(r"/profil/spieler/(\d+)", r.text)
        names = re.findall(r'/profil/spieler/\d+"[^>]*>([^<]+)</a>', r.text)
        print(f"    HTTP {r.status_code} | IDs encontrados: {ids[:5]}")
        print(f"    Nombres encontrados: {names[:5]}")
        if not ids:
            print(f"    HTML preview: {r.text[:300]}")
    except Exception as e:
        print(f"    ERROR: {e}")

    print("\n[3] TM autocomplete JSON:")
    for url in [
        f"{TM_WEB_BASE}/ceapi/market/ajax/topangebote?query=Pickford&type=players",
        f"{TM_WEB_BASE}/_/api/players/search?query=Pickford",
    ]:
        try:
            r = session.get(url, headers=HEADERS_WEB_JSON, timeout=8)
            ct = r.headers.get("content-type", "")
            print(f"    {url.split('/')[-1]}: HTTP {r.status_code} | {ct} | {r.text[:100]}")
        except Exception as e:
            print(f"    ERROR ({url.split('/')[-1]}): {type(e).__name__}")

    print("\nResultados esperados:")
    print("  [1] HTTP 200 con nombre 'Jordan Pickford' -> API basica OK")
    print("  [2] HTTP 200 con IDs [130164, ...] -> Busqueda web OK -> Fase 2 funcionara")
    print("  [2] HTML sin IDs -> TM bloquea scraping -> solo Fase 1 disponible")


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", type=int, choices=[1, 2], default=None)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--min-minutes", type=int, default=100)
    parser.add_argument("--min-score", type=float, default=68.0,
                        help="Score minimo para aceptar un match (default: 68)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--no-fetch", action="store_true")
    parser.add_argument("--test-api", action="store_true")
    args = parser.parse_args()

    if args.test_api:
        test_api_connectivity()
        return

    run_phases = [args.phase] if args.phase else [1, 2]

    print("=" * 60)
    print("fetch_tm_search.py")
    print("=" * 60)
    print(f"Fases: {run_phases} | limite: {args.limit} | min_min: {args.min_minutes} | min_score: {args.min_score}")
    if args.dry_run:
        print("[DRY-RUN]")
    print()

    em     = load_entity_map()
    master = load_master_players()
    mv     = load_market_values()

    unmatched_all = get_unmatched(em, master, args.min_minutes)
    print(f"Sin tm_id con >={args.min_minutes}min: {len(unmatched_all):,}")

    all_new: dict[str, tuple[str, str, float]] = {}
    session = requests.Session()

    if 1 in run_phases:
        unm = set(em[em["tm_id"].isna()]["opta_id"])
        sub = unmatched_all[unmatched_all["player_id"].isin(unm)]
        r1  = phase1_fuzzy(sub, mv, dry_run=args.dry_run, verbose=args.verbose)
        if r1:
            em = apply_results(r1, em, label="fuzzy", dry_run=args.dry_run)
            all_new.update(r1)

    if 2 in run_phases:
        unm = set(em[em["tm_id"].isna()]["opta_id"])
        sub = unmatched_all[unmatched_all["player_id"].isin(unm)]
        print(f"\n[FASE 2] Jugadores a buscar: {len(sub):,}")
        if not sub.empty:
            r2 = phase2_web_search(
                sub, session, limit=args.limit,
                min_score=args.min_score,
                dry_run=args.dry_run, verbose=args.verbose,
            )
            if r2:
                em = apply_results(r2, em, label='web', dry_run=args.dry_run)
                all_new.update(r2)

    print('\n' + '=' * 60)
    print('RESUMEN')
    print('=' * 60)
    print(f'Nuevos matches: {len(all_new):,}')
    print(f'Sin tm_id todavia: {em["tm_id"].isna().sum():,}')

    if all_new and not args.no_fetch and not args.dry_run:
        fetch_economic_data(
            [tid for (tid, _, _) in all_new.values()], session, dry_run=False
        )
    print('\nListo!')


if __name__ == '__main__':
    main()
