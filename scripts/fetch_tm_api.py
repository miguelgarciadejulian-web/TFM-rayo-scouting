"""
fetch_tm_api.py
===============
ETL que obtiene datos económicos de jugadores desde la API de Transfermarkt.

Flujo:
  1. Lee master_players.parquet → jugadores de la temporada actual OPTA.
  2. Hace match de nombre OPTA → market_values.csv para obtener tm_id.
  3. Para cada jugador con tm_id llama:
       GET https://tmapi-alpha.transfermarkt.technology/player/{tm_id}
  4. Parsea el JSON y escribe player_economic.parquet.
  5. También actualiza market_values.csv con los nuevos valores.

Uso:
    python scripts/fetch_tm_api.py                # todos los jugadores sin datos
    python scripts/fetch_tm_api.py --sample 20   # prueba con 20 jugadores
    python scripts/fetch_tm_api.py --force        # refetch aunque ya existan datos
    python scripts/fetch_tm_api.py --days 7       # refetch si datos > 7 días
    python scripts/fetch_tm_api.py --limit 100    # máximo 100 llamadas en esta ejecución
    python scripts/fetch_tm_api.py --dry-run      # muestra qué haría sin llamar la API
"""
from __future__ import annotations

import argparse
import json
import time
import unicodedata
from datetime import datetime, date, timedelta
from pathlib import Path
import re
import sys

import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
ROOT          = Path(__file__).resolve().parents[1]
MASTER_PQ     = ROOT / "data" / "processed" / "master_players.parquet"
MV_CSV        = ROOT / "config" / "market_values.csv"
ECONOMIC_PQ   = ROOT / "data" / "processed" / "player_economic.parquet"
RAW_JSON      = ROOT / "data" / "processed" / "tm_api_raw.json"
ENTITY_MAP    = ROOT / "data" / "processed" / "player_entity_map.csv"

TM_API_BASE   = "https://tmapi-alpha.transfermarkt.technology/player"
REQUEST_DELAY = 0.5   # segundos entre llamadas (cortesía al servidor)
TIMEOUT       = 15    # segundos por petición
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; RayoScoutingTool/1.0)",
    "Accept": "application/json",
}

# Temporadas OPTA consideradas "actuales"
CURRENT_SEASONS = {"2026", "2025-2026", "2025/2026"}


# ---------------------------------------------------------------------------
# Utilidades de normalización
# ---------------------------------------------------------------------------
def _norm(s: str) -> str:
    return (
        unicodedata.normalize("NFKD", str(s))
        .encode("ascii", "ignore")
        .decode()
        .lower()
        .strip()
    )


def _surname(name: str) -> str:
    n = _norm(name).replace(".", " ")
    parts = [p for p in n.split() if len(p) > 1]
    return parts[-1] if parts else n


def _first_initial(name: str) -> str | None:
    n = _norm(name).replace(".", " ").strip()
    parts = [p for p in n.split() if p]
    if len(parts) >= 2 and len(parts[0]) == 1:
        return parts[0]   # "j" en "J. Fernandez"
    return None


def _tm_id_from_url(url: str | None) -> str | None:
    """Extrae tm_id numérico de una URL de foto de Transfermarkt."""
    if not url:
        return None
    m = re.search(r"/portrait/(?:big|small|medium|header)/(\d+)-", str(url))
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Carga de fuentes
# ---------------------------------------------------------------------------
def load_master_current() -> pd.DataFrame:
    """Carga jugadores OPTA de la temporada actual."""
    df = pd.read_parquet(MASTER_PQ)
    current = df[df["season"].isin(CURRENT_SEASONS)].copy()
    print(f"[INFO] Jugadores OPTA temporada actual: {len(current):,}")
    return current


def load_market_values() -> pd.DataFrame:
    """Carga market_values.csv con tm_id limpio."""
    mv = pd.read_csv(MV_CSV)
    # Extraer tm_id desde el campo o desde la URL de foto
    def _get_tid(row):
        tid = str(row.get("tm_id", "") or "").replace(".0", "").strip()
        if tid.isdigit():
            return tid
        return _tm_id_from_url(row.get("tm_photo_url"))

    mv["tm_id_clean"] = mv.apply(_get_tid, axis=1)
    mv["_norm"] = mv["name"].apply(_norm)
    mv["_surname"] = mv["name"].apply(_surname)
    print(f"[INFO] market_values.csv: {len(mv):,} filas, {mv['tm_id_clean'].notna().sum():,} con tm_id")
    return mv


def load_entity_map() -> pd.DataFrame | None:
    """Carga player_entity_map.csv si existe."""
    if ENTITY_MAP.exists():
        try:
            return pd.read_csv(ENTITY_MAP)
        except Exception:
            pass
    return None


def load_raw_cache() -> dict:
    """Carga respuestas API ya guardadas (cache incremental)."""
    if RAW_JSON.exists():
        try:
            return json.loads(RAW_JSON.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


# ---------------------------------------------------------------------------
# Matching OPTA → tm_id
# ---------------------------------------------------------------------------
def build_match_index(mv: pd.DataFrame) -> dict:
    """
    Construye tres índices de lookup: exacto, apellido, inicial+apellido.
    Devuelve {norm_key: tm_id}
    """
    has_tid = mv[mv["tm_id_clean"].notna()]

    exact: dict = {}
    by_surname: dict = {}
    by_initial_surname: dict = {}

    for _, r in has_tid.iterrows():
        n = r["_norm"]
        sn = r["_surname"]
        tid = r["tm_id_clean"]

        # índice exacto
        exact[n] = tid

        # índice por apellido (solo si es único)
        if sn not in by_surname:
            by_surname[sn] = tid
        else:
            by_surname[sn] = None  # ambiguo → ignorar

        # índice inicial+apellido — para "J. Pérez" vs "Javier Pérez"
        # Computamos desde el nombre completo: primera letra + apellido
        parts = [p for p in n.replace(".", " ").split() if len(p) > 1]
        if len(parts) >= 2:
            key = parts[0][0] + "." + sn   # "j.perez"
            by_initial_surname.setdefault(key, []).append((n, tid))

    # Mantener solo los inicial+apellido que tienen una coincidencia unívoca
    uniq_is: dict = {}
    for k, lst in by_initial_surname.items():
        if len(lst) == 1:
            uniq_is[k] = lst[0][1]

    return {"exact": exact, "surname": by_surname, "initial_surname": uniq_is}


def match_opta_to_tid(name: str, idx: dict) -> tuple[str | None, str]:
    """
    Busca tm_id para un nombre OPTA.
    Devuelve (tm_id, metodo_match) o (None, "no_match").
    """
    n = _norm(name)
    sn = _surname(name)

    # 1. Exacto
    if n in idx["exact"]:
        return idx["exact"][n], "exact"

    # 2. Inicial + apellido (para nombres abreviados "J. García")
    initial = _first_initial(name)
    if initial:
        k = initial + "." + sn
        if k in idx["initial_surname"]:
            return idx["initial_surname"][k], "initial_surname"

    # 3. Apellido único
    if sn in idx["surname"] and idx["surname"][sn] is not None:
        return idx["surname"][sn], "surname"

    return None, "no_match"


# ---------------------------------------------------------------------------
# Llamada a la API de Transfermarkt
# ---------------------------------------------------------------------------
def fetch_tm_player(tm_id: str, session: requests.Session) -> dict | None:
    """
    Llama https://tmapi-alpha.transfermarkt.technology/player/{tm_id}
    y devuelve el JSON completo, o None si hay error.
    """
    url = f"{TM_API_BASE}/{tm_id}"
    try:
        r = session.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            return r.json()
        elif r.status_code == 404:
            print(f"  [404] tm_id={tm_id} no encontrado en TM API")
            return None
        elif r.status_code == 429:
            print(f"  [429] Rate limit — esperando 5s...")
            time.sleep(5)
            r2 = session.get(url, headers=HEADERS, timeout=TIMEOUT)
            return r2.json() if r2.status_code == 200 else None
        else:
            print(f"  [{r.status_code}] Error para tm_id={tm_id}")
            return None
    except requests.RequestException as e:
        print(f"  [ERR] tm_id={tm_id}: {e}")
        return None


# ---------------------------------------------------------------------------
# Parsing del JSON de respuesta
# ---------------------------------------------------------------------------
def parse_tm_response(data: dict, tm_id: str) -> dict:
    """
    Extrae los campos relevantes del JSON de respuesta de la API TM.

    Estructura real confirmada:
      data.marketValueDetails.current.value          → market_value_eur
      data.marketValueDetails.previous.value         → market_value_prev
      data.marketValueDetails.highest.value          → market_value_highest
      data.attributes.contractUntil                  → contract_until
      data.attributes.height                         → height
      data.attributes.preferredFoot.name             → foot
      data.attributes.position.name                  → position_tm
      data.attributes.firstSidePosition.name         → alt_position_1
      data.attributes.secondSidePosition.name        → alt_position_2
      data.lifeDates.age                             → age
      data.lifeDates.dateOfBirth                     → dob  (string "YYYY-MM-DD")
      data.birthPlaceDetails.placeOfBirth            → birthplace
      data.portraitUrl                               → photo_url
      data.clubAssignments[type=current].shirtNumber → shirt_number
      data.clubAssignments[type=current].isCaptain   → is_captain
    """
    d = data.get("data", data)  # algunos endpoints devuelven directamente

    # Valor de mercado actual
    mv = None
    try:
        mv_raw = (
            d.get("marketValueDetails", {})
            .get("current", {})
            .get("value")
        )
        if mv_raw is not None:
            mv = float(mv_raw)
    except (TypeError, ValueError):
        pass

    # Valor de mercado anterior
    mv_prev = None
    try:
        vp = d.get("marketValueDetails", {}).get("previous", {}).get("value")
        if vp is not None:
            mv_prev = float(vp)
    except (TypeError, ValueError):
        pass

    # Valor de mercado histórico máximo
    mv_highest = None
    try:
        vh = d.get("marketValueDetails", {}).get("highest", {}).get("value")
        if vh is not None:
            mv_highest = float(vh)
    except (TypeError, ValueError):
        pass

    # Contrato
    contract_until = None
    try:
        cu = d.get("attributes", {}).get("contractUntil")
        if cu and str(cu).strip() not in ("", "null", "None"):
            contract_until = str(cu)[:10]
    except (TypeError, AttributeError):
        pass

    # Altura
    height = None
    try:
        h = d.get("attributes", {}).get("height")
        if h:
            height = str(h)
    except (TypeError, AttributeError):
        pass

    # Pie preferido
    foot = None
    try:
        foot = (
            d.get("attributes", {})
            .get("preferredFoot", {})
            .get("name")
        )
    except (TypeError, AttributeError):
        pass

    # Posición principal
    position_tm = None
    try:
        position_tm = (
            d.get("attributes", {})
            .get("position", {})
            .get("name")
        )
    except (TypeError, AttributeError):
        pass

    # Posición alternativa 1
    alt_position_1 = None
    try:
        alt_position_1 = (
            d.get("attributes", {})
            .get("firstSidePosition", {})
            .get("name")
        )
    except (TypeError, AttributeError):
        pass

    # Posición alternativa 2
    alt_position_2 = None
    try:
        alt_position_2 = (
            d.get("attributes", {})
            .get("secondSidePosition", {})
            .get("name")
        )
    except (TypeError, AttributeError):
        pass

    # Edad
    age = None
    try:
        age = d.get("lifeDates", {}).get("age")
        if age is not None:
            age = int(age)
    except (TypeError, ValueError):
        pass

    # Fecha de nacimiento — es un string "YYYY-MM-DD", no un dict
    dob = None
    try:
        dob_raw = d.get("lifeDates", {}).get("dateOfBirth")
        if dob_raw and isinstance(dob_raw, str):
            dob = dob_raw[:10]
        elif dob_raw and isinstance(dob_raw, dict):
            dob = str(dob_raw.get("date", ""))[:10] or None
    except (TypeError, AttributeError):
        pass

    # Lugar de nacimiento
    birthplace = None
    try:
        birthplace = d.get("birthPlaceDetails", {}).get("placeOfBirth") or None
    except (TypeError, AttributeError):
        pass

    # Nacionalidad — nationalities es un dict {nationalityId, secondNationalityId}, sin nombres
    # Usamos passportName como proxy (puede estar en idioma local)
    nationality = None
    try:
        pn = d.get("nationalityDetails", {}).get("passportName")
        if pn and str(pn).strip():
            nationality = str(pn).strip()
    except (TypeError, AttributeError):
        pass

    # Foto
    photo_url = None
    try:
        pu = d.get("portraitUrl")
        if pu and str(pu).startswith("http"):
            photo_url = str(pu)
    except (TypeError, AttributeError):
        pass

    # Club actual + dorsal + capitán (de clubAssignments)
    club_id = None
    shirt_number = None
    is_captain = None
    try:
        ca = d.get("clubAssignments", [])
        if ca and isinstance(ca, list):
            current = next((x for x in ca if x.get("type") == "current"), ca[0])
            club_id      = current.get("clubId")
            shirt_number = current.get("shirtNumber")
            is_captain   = bool(current.get("isCaptain", False))
    except (TypeError, AttributeError, IndexError, StopIteration):
        pass

    # Nombre canónico desde TM
    tm_name = None
    try:
        tm_name = d.get("name") or d.get("shortName") or d.get("displayName")
    except (TypeError, AttributeError):
        pass

    # Cláusula de rescisión (si la API la devuelve)
    release_clause = None
    try:
        rc = d.get("attributes", {}).get("releaseClause")
        if rc:
            release_clause = float(rc)
    except (TypeError, ValueError):
        pass

    return {
        "tm_id":                tm_id,
        "tm_name":              tm_name,
        "market_value_eur":     mv,
        "market_value_prev":    mv_prev,
        "market_value_highest": mv_highest,
        "contract_until":       contract_until,
        "height":               height,
        "foot":                 foot,
        "position_tm":          position_tm,
        "alt_position_1":       alt_position_1,
        "alt_position_2":       alt_position_2,
        "age":                  age,
        "dob":                  dob,
        "birthplace":           birthplace,
        "nationality":          nationality,
        "photo_url":            photo_url,
        "club_id_tm":           club_id,
        "shirt_number":         shirt_number,
        "is_captain":           is_captain,
        "release_clause_eur":   release_clause,
    }


# ---------------------------------------------------------------------------
# Escritura de resultados
# ---------------------------------------------------------------------------
def save_raw_cache(cache: dict) -> None:
    RAW_JSON.parent.mkdir(parents=True, exist_ok=True)
    RAW_JSON.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def build_economic_parquet(
    players: pd.DataFrame,
    economic_by_opta: dict,
    existing: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Combina los datos OPTA con los datos económicos obtenidos de TM.
    Devuelve un DataFrame listo para guardar como player_economic.parquet.
    """
    records = []
    for _, row in players.iterrows():
        opta_id = str(row.get("player_id", "")).strip()
        name    = str(row.get("name", "")).strip()

        econ = economic_by_opta.get(opta_id, {})

        records.append({
            "opta_id":              opta_id,
            "canonical_name":       _norm(name),
            "display_name":         name,
            "market_value_eur":     econ.get("market_value_eur"),
            "market_value_prev":    econ.get("market_value_prev"),
            "market_value_highest": econ.get("market_value_highest"),
            "contract_until":       econ.get("contract_until"),
            "release_clause_eur":   econ.get("release_clause_eur"),
            "salary_eur_year":      None,   # no disponible en TM API
            "nationality":          econ.get("nationality"),
            "age":                  econ.get("age"),
            "position_tm":          econ.get("position_tm"),
            "alt_position_1":       econ.get("alt_position_1"),
            "alt_position_2":       econ.get("alt_position_2"),
            "height":               econ.get("height"),
            "foot":                 econ.get("foot"),
            "dob":                  econ.get("dob"),
            "birthplace":           econ.get("birthplace"),
            "shirt_number":         econ.get("shirt_number"),
            "is_captain":           econ.get("is_captain"),
            "tm_id":                econ.get("tm_id"),
            "club_id_tm":           econ.get("club_id_tm"),
            "photo_url":            econ.get("photo_url"),
            "match_method":         econ.get("match_method"),
            "match_confidence":     econ.get("match_confidence"),
            "data_source":          "transfermarkt_api" if econ.get("tm_id") else None,
            "last_updated":         econ.get("last_updated"),
        })

    new_df = pd.DataFrame(records)

    # Fusionar con datos existentes (preservar datos que no hayamos refrescado)
    if existing is not None and not existing.empty:
        # Filas del nuevo set
        new_ids = set(new_df["opta_id"].dropna())
        # Filas del existente que NO están en el nuevo (otras temporadas, etc.)
        old_rows = existing[~existing["opta_id"].isin(new_ids)]
        combined = pd.concat([new_df, old_rows], ignore_index=True)
    else:
        combined = new_df

    return combined


def update_market_values_csv(mv: pd.DataFrame, economic_by_opta: dict) -> None:
    """
    Actualiza market_values.csv con los valores más recientes obtenidos de la API.
    Sólo modifica filas existentes (no añade nuevas filas).
    """
    updated = 0
    # Construir índice inverso: tm_id → datos económicos
    by_tid: dict = {}
    for _, econ in economic_by_opta.items():
        tid = econ.get("tm_id")
        if tid:
            by_tid[tid] = econ

    for idx, row in mv.iterrows():
        tid = row.get("tm_id_clean")
        if not tid or tid not in by_tid:
            continue
        econ = by_tid[tid]
        changed = False
        if econ.get("market_value_eur") is not None:
            mv.at[idx, "market_value_eur"] = econ["market_value_eur"]
            changed = True
        if econ.get("contract_until"):
            mv.at[idx, "contract_until"] = econ["contract_until"]
            changed = True
        if econ.get("photo_url"):
            mv.at[idx, "tm_photo_url"] = econ["photo_url"]
            changed = True
        if changed:
            updated += 1

    # Guardar (sin la columna auxiliar tm_id_clean)
    save_cols = [c for c in mv.columns if c not in ("tm_id_clean", "_norm", "_surname")]
    mv[save_cols].to_csv(MV_CSV, index=False)
    print(f"[INFO] market_values.csv actualizado: {updated:,} filas modificadas")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def load_all_from_entity_map() -> pd.DataFrame:
    """
    Carga TODOS los jugadores con tm_id en player_entity_map.csv,
    cruzando con player_seasons_enriched.parquet para obtener nombre y equipo.
    Alternativa a load_master_current() cuando queremos procesar más allá
    de la temporada actual.
    """
    em = pd.read_csv(ENTITY_MAP)
    em = em[em["tm_id"].notna()].copy()
    em["tm_id"] = em["tm_id"].astype(str).str.replace(".0", "", regex=False).str.strip()
    em = em[em["tm_id"].str.isdigit()]

    enriched_path = ROOT / "data" / "processed" / "player_seasons_enriched.parquet"
    if enriched_path.exists():
        enr = pd.read_parquet(enriched_path)
        if "season" in enr.columns:
            enr = enr.sort_values("season", ascending=False)
        enr = enr.drop_duplicates(subset=["player_id_src"], keep="first")
        enr = enr.rename(columns={"player_id_src": "opta_id"})
        enr["opta_id"] = enr["opta_id"].astype(str)
        merged = em.merge(enr[["opta_id", "name", "team", "league"]], on="opta_id", how="left")
    else:
        merged = em.copy()
        if "name" not in merged.columns:
            merged["name"] = ""

    merged = merged.rename(columns={"opta_id": "player_id"})
    print(f"[INFO] Jugadores con tm_id en entity_map: {len(merged):,}")
    return merged


def main():
    parser = argparse.ArgumentParser(description="Fetch económico desde TM API")
    parser.add_argument("--sample",          type=int, default=0,
                        help="Modo prueba: sólo N jugadores")
    parser.add_argument("--limit",           type=int, default=0,
                        help="Máximo de llamadas API en esta ejecución")
    parser.add_argument("--days",            type=int, default=0,
                        help="Refetch si los datos tienen más de N días")
    parser.add_argument("--force",           action="store_true",
                        help="Refetch aunque ya existan datos")
    parser.add_argument("--dry-run",         action="store_true",
                        help="Muestra estadísticas sin llamar la API")
    parser.add_argument("--from-entity-map", action="store_true",
                        help="Procesar TODOS los jugadores con tm_id en entity_map "
                             "(no solo la temporada actual de master_players)")
    args = parser.parse_args()

    # ---- Cargar fuentes ----
    print("=" * 60)
    print("fetch_tm_api.py — ETL económico Transfermarkt")
    print("=" * 60)

    if args.from_entity_map:
        current_players = load_all_from_entity_map()
    else:
        current_players = load_master_current()
    mv        = load_market_values()
    raw_cache = load_raw_cache()

    # Cargar parquet existente para merge incremental
    existing_econ = None
    if ECONOMIC_PQ.exists():
        try:
            existing_econ = pd.read_parquet(ECONOMIC_PQ)
            print(f"[INFO] player_economic.parquet existente: {len(existing_econ):,} filas")
        except Exception:
            pass

    # Determinar fecha de corte para --days
    stale_cutoff = None
    if args.days > 0:
        stale_cutoff = (datetime.utcnow() - timedelta(days=args.days)).isoformat()

    # ---- Construir índice de matching ----
    match_idx = build_match_index(mv)

    # ---- Cargar entity_map para lookup directo opta_id → tm_id ----
    em_lookup: dict = {}  # opta_id → (tm_id_str, match_type)
    entity_map_df = load_entity_map()
    if entity_map_df is not None:
        em_has_tid = entity_map_df[entity_map_df["tm_id"].notna()]
        for _, r in em_has_tid.iterrows():
            oid = str(r["opta_id"]).strip()
            tid = str(r["tm_id"]).replace(".0", "").strip()
            mtype = str(r.get("match_type", "entity_map")).strip()
            if oid and tid.isdigit():
                em_lookup[oid] = (tid, mtype)
        print(f"[INFO] entity_map: {len(em_lookup):,} opta_id con tm_id cargados")

    # ---- Hacer match de jugadores OPTA → tm_id ----
    print("\n[INFO] Haciendo match OPTA → tm_id ...")
    matched_count  = 0
    no_match_count = 0
    em_used        = 0

    players_to_fetch: list[dict] = []

    for _, row in current_players.iterrows():
        opta_id = str(row.get("player_id", "")).strip()
        name    = str(row.get("name", "")).strip()

        # Con --from-entity-map el tm_id ya viene en la fila directamente
        if args.from_entity_map and "tm_id" in row and str(row.get("tm_id", "")).strip().isdigit():
            tm_id  = str(row["tm_id"]).strip()
            method = str(row.get("match_type", "entity_map"))
            em_used += 1
        # 1. Lookup directo en entity_map (más fiable que name-matching)
        elif opta_id in em_lookup:
            tm_id, method = em_lookup[opta_id]
            em_used += 1
        else:
            tm_id, method = match_opta_to_tid(name, match_idx)

        confidence = {
            "exact": 1.00, "exact_name": 1.00,
            "initial_surname": 0.85, "exact_surname": 0.80,
            "surname": 0.80, "search_web": 0.75,
        }.get(method, 0.70)

        if tm_id:
            matched_count += 1
        else:
            no_match_count += 1

        # Decidir si hacer fetch
        needs_fetch = False
        if tm_id:
            if args.force:
                needs_fetch = True
            elif tm_id not in raw_cache:
                needs_fetch = True
            elif stale_cutoff and raw_cache[tm_id].get("_fetched_at", "") < stale_cutoff:
                needs_fetch = True

        players_to_fetch.append({
            "opta_id":    opta_id,
            "name":       name,
            "tm_id":      tm_id,
            "method":     method,
            "confidence": confidence,
            "needs_fetch": needs_fetch and bool(tm_id),
        })

    total_matched  = sum(1 for p in players_to_fetch if p["tm_id"])
    total_to_fetch = sum(1 for p in players_to_fetch if p["needs_fetch"])

    print(f"  Jugadores con tm_id:     {total_matched:,} / {len(players_to_fetch):,} "
          f"({100*total_matched/len(players_to_fetch):.1f}%)")
    print(f"  Via entity_map:          {em_used:,}")
    print(f"  Match exacto:            {sum(1 for p in players_to_fetch if p['method'] in ('exact','exact_name')):,}")
    print(f"  Match inicial+apellido:  {sum(1 for p in players_to_fetch if p['method'] in ('initial_surname','exact_surname')):,}")
    print(f"  Match apellido:          {sum(1 for p in players_to_fetch if p['method']=='surname'):,}")
    print(f"  Via web search:          {sum(1 for p in players_to_fetch if p['method']=='search_web'):,}")
    print(f"  Sin match:               {no_match_count:,}")
    print(f"  A fetchear de API:       {total_to_fetch:,}")

    if args.dry_run:
        print("\n[DRY-RUN] Fin de simulación. No se ha llamado la API.")
        # Mostrar algunos ejemplos de sin match
        no_match_examples = [p for p in players_to_fetch if not p["tm_id"]][:15]
        if no_match_examples:
            print("\nEjemplos sin match (primeros 15):")
            for p in no_match_examples:
                print(f"  {p['name']}")
        return

    # ---- Limitar si se pidió --sample o --limit ----
    fetch_list = [p for p in players_to_fetch if p["needs_fetch"]]
    if args.sample > 0:
        import random
        fetch_list = random.sample(fetch_list, min(args.sample, len(fetch_list)))
        print(f"\n[SAMPLE] Modo prueba: fetching {len(fetch_list)} jugadores")
    elif args.limit > 0:
        fetch_list = fetch_list[:args.limit]
        print(f"\n[LIMIT] Limitado a {len(fetch_list)} llamadas")

    # ---- Fetch desde la API ----
    session = requests.Session()
    session.headers.update(HEADERS)

    ok_count    = 0
    err_count   = 0
    total       = len(fetch_list)

    print(f"\n[INFO] Iniciando fetch de {total:,} jugadores...")
    print("-" * 60)

    for i, player in enumerate(fetch_list, 1):
        tm_id = player["tm_id"]
        name  = player["name"]
        pct   = 100 * i / total

        print(f"[{i}/{total} {pct:.0f}%] {name} (tm_id={tm_id})", end=" ... ", flush=True)

        raw = fetch_tm_player(tm_id, session)

        if raw:
            raw["_fetched_at"]    = datetime.utcnow().isoformat()
            raw["_opta_id"]       = player["opta_id"]
            raw["_match_method"]  = player["method"]
            raw_cache[tm_id]      = raw
            ok_count += 1
          