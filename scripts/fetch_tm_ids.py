"""
fetch_tm_ids.py
===============
Busca el player_id de Transfermarkt para todos los jugadores de las 16 ligas
del scope de Rayo Vallecano que aun NO tienen tm_id en la base de datos.

LOGICA DE MATCHING:
  1. Extraer apellido e inicial del nombre OPTA  ("S. Galesio" -> inicial=S, apellido=Galesio)
  2. Buscar en TM por apellido solo              (busca "Galesio", encuentra "Santiago Galesio")
  3. Filtrar candidatos cuyo apellido coincida
  4. De esos, filtrar los que la inicial coincida con la primera letra del nombre TM
  5. Si queda 1 -> match 100% confirmado
  6. Si quedan varios -> desambiguar por club (tolerante con diferencias de nombre)
  7. Si no se puede resolver -> CSV de revision manual

FUENTES:
  - data/processed/player_seasons_enriched.parquet  -> jugadores OPTA a buscar
  - data/processed/player_entity_map.csv            -> ya tienen tm_id (skip)
  - data/processed/player_economic.parquet          -> tambien tienen tm_id (skip)
  - config/market_values.csv                        -> idem

OUTPUTS:
  - data/processed/player_entity_map.csv            -> actualizado con nuevos tm_id
  - config/market_values.csv                        -> actualizado con datos TM
  - data/processed/tm_enrichment_ambiguous.csv      -> casos sin resolver (manual)
  - data/processed/tm_enrichment_progress.csv       -> checkpoint para reanudar

Uso:
    python scripts/fetch_tm_ids.py                   # todos los jugadores
    python scripts/fetch_tm_ids.py --league Spain_Primera_Division
    python scripts/fetch_tm_ids.py --limit 500
    python scripts/fetch_tm_ids.py --resume          # reanudar desde checkpoint
    python scripts/fetch_tm_ids.py --dry-run         # solo muestra cuantos hay
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
from bs4 import BeautifulSoup

# Rutas
PROC          = ROOT / "data" / "processed"
ENRICHED      = PROC / "player_seasons_enriched.parquet"
ENTITY_MAP    = PROC / "player_entity_map.csv"
ECONOMIC      = PROC / "player_economic.parquet"
MV_CSV        = ROOT / "config" / "market_values.csv"
AMBIGUOUS_CSV = PROC / "tm_enrichment_ambiguous.csv"
PROGRESS_CSV  = PROC / "tm_enrichment_progress.csv"

SCOPE_LEAGUES = [
    "Argentina_Liga_Profesional",
    "Belgium_First_Division_A",
    "Denmark_Superliga",
    "England_Championship",
    "England_Premier_League",
    "France_Ligue_1",
    "France_Ligue_2",
    "Germany_2_Bundesliga",
    "Germany_Bundesliga",
    "Italy_Serie_A",
    "Mexico_Liga_MX",
    "Netherlands_Eredivisie",
    "Portugal_Primeira_Liga",
    "Spain_Primera_Division",
    "Spain_Segunda_Division",
    "Turkiye_Super_Lig",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Referer": "https://www.transfermarkt.com/",
}
TM_SEARCH     = "https://www.transfermarkt.com/schnellsuche/ergebnis/schnellsuche"
SLEEP_BETWEEN = 1.2
SLEEP_RETRY   = 8.0
MAX_RETRIES   = 4
RESULTS_LIMIT = 20


# ── Normalizacion ─────────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    return (
        unicodedata.normalize("NFKD", str(s))
        .encode("ascii", "ignore")
        .decode()
        .lower()
        .strip()
    )


def _surname(name: str) -> str:
    parts = [p for p in _norm(name).replace(".", " ").split() if len(p) > 1]
    return parts[-1] if parts else _norm(name)


def _norm_club(team: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _norm(team))


# Palabras que NO son distintivas en un nombre de club
_CLUB_STOP = {
    "fc", "cf", "ac", "ca", "sc", "rc", "cd", "ud", "sd", "as", "rcd",
    "vfb", "bsc", "psv", "ajax", "club", "atletico", "athletic", "deportivo",
    "sporting", "racing", "union", "united", "city", "real", "de", "la",
    "el", "los", "las", "del", "and", "und", "van", "den",
}


def _club_tokens(team: str) -> set[str]:
    tokens = set(_norm(team).split())
    return tokens - _CLUB_STOP


def _club_keyword(team: str) -> str:
    """Palabra mas distintiva del club para incluir en la busqueda TM."""
    tokens = [t for t in _club_tokens(team) if len(t) > 3]
    if not tokens:
        return ""
    return max(tokens, key=len)


def _club_match(opta_team: str, tm_team: str) -> float:
    """
    Similitud de clubs entre 0 y 1.
    Ejemplos:
      "CA Rosario Central" vs "Rosario Central"  -> 1.0 (tokens iguales tras quitar stopwords)
      "CA Tigre"           vs "Tigre"             -> 1.0
      "CA River Plate"     vs "River Plate"       -> 1.0
      "Bayern Munich"      vs "FC Bayern Munchen" -> 0.8 (token overlap)
    """
    if not opta_team or not tm_team:
        return 0.0

    # Comparacion directa normalizada
    a = _norm_club(opta_team)
    b = _norm_club(tm_team)
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.8

    # Comparacion por tokens significativos
    ta = _club_tokens(opta_team)
    tb = _club_tokens(tm_team)
    ta = {t for t in ta if len(t) > 2}
    tb = {t for t in tb if len(t) > 2}
    if not ta or not tb:
        return 0.0

    # Match exacto de tokens
    exact_overlap = len(ta & tb) / max(len(ta), len(tb))
    if exact_overlap > 0:
        return round(exact_overlap, 2)

    # Match parcial: un token de 'a' empieza igual que un token de 'b' (primeros 4 chars)
    partial = sum(
        1 for t in ta
        if any(t[:4] == u[:4] for u in tb if len(u) >= 4)
    )
    if partial:
        return round(partial / max(len(ta), len(tb)) * 0.6, 2)

    return 0.0


# ── Parsing del nombre OPTA ───────────────────────────────────────────────────

def _parse_opta_name(name: str) -> tuple[str, str]:
    """
    Extrae (inicial, apellido) del formato OPTA.

    "S. Galesio"       -> ("S", "Galesio")
    "F.J. Torres"      -> ("F", "Torres")
    "Santiago Galesio" -> ("S", "Galesio")
    "De Bruyne"        -> ("",  "De Bruyne")
    "K. De Bruyne"     -> ("K", "De Bruyne")
    """
    name = name.strip()
    # Formato "X." o "X.Y." seguido de apellido
    m = re.match(r"^([A-Z])\.[A-Z.]*\s+(.+)$", name, re.UNICODE)
    if m:
        return m.group(1).upper(), m.group(2).strip()
    # Formato "Nombre Apellido(s)"
    # Si el primer token tiene mas de 3 chars, es un nombre real (ej. "Santiago Galesio")
    # Si tiene <= 3 chars sin punto, es probablemente un prefijo del apellido (ej. "De Bruyne", "Van Dijk")
    parts = name.split()
    if len(parts) >= 2 and len(parts[0]) > 3:
        return parts[0][0].upper(), " ".join(parts[1:])
    return "", name


def _initial_matches(opta_initial: str, tm_name: str) -> bool:
    """Verifica que la inicial OPTA coincide con la primera letra del nombre TM."""
    if not opta_initial:
        return True
    tm_parts = tm_name.strip().split()
    if not tm_parts:
        return False
    return _norm(tm_parts[0])[:1] == _norm(opta_initial)[:1]


# ── Sesion HTTP ───────────────────────────────────────────────────────────────

def _session():
    try:
        import cloudscraper
        s = cloudscraper.create_scraper()
        print("[INFO] Usando cloudscraper")
        return s
    except ImportError:
        import requests
        s = requests.Session()
        s.headers.update(HEADERS)
        print("[INFO] Usando requests (instala cloudscraper si hay bloqueos)")
        return s


# ── Parsing de resultados TM ──────────────────────────────────────────────────

def _parse_value(text: str):
    if not text:
        return ""
    t = (
        text.replace("\xa0", " ").strip().lower()
        .replace("€", "").replace("eur", "").strip()
    )
    m = re.search(r"([\d.,]+)\s*([mk])?", t)
    if not m:
        return ""
    try:
        val = float(m.group(1).replace(",", "."))
    except ValueError:
        return ""
    unit = m.group(2)
    if unit == "m":
        return int(val * 1_000_000)
    if unit == "k":
        return int(val * 1_000)
    return int(val)


def _parse_search_results(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    table = soup.select_one("table.items tbody")
    if not table:
        return []

    for row in table.select("tr")[:RESULTS_LIMIT]:
        cells = row.select("td")
        if len(cells) < 2:
            continue

        tm_id = None
        tm_photo_url = ""
        img = row.select_one("img")
        if img:
            raw = img.get("data-src") or img.get("src") or ""
            m = re.search(r"/portrait/(?:small|medium|big|header)/(\d+)", raw)
            if m:
                tm_id = m.group(1)
                tm_photo_url = (
                    "https://img.a.transfermarkt.technology"
                    "/portrait/big/{}.jpg".format(m.group(1))
                )

        link_el = row.select_one("td.hauptlink a, a.spielprofil_tooltip")
        tm_name = ""
        tm_url = ""
        if link_el:
            tm_name = link_el.get_text(strip=True)
            href = link_el.get("href", "")
            tm_url = "https://www.transfermarkt.com{}".format(href) if href else ""
            if not tm_id:
                m = re.search(r"/spieler/(\d+)", href)
                if m:
                    tm_id = m.group(1)

        if not tm_id:
            continue

        tm_club = ""
        for cl in row.select("td a"):
            href = cl.get("href", "")
            text = cl.get_text(strip=True)
            if "/verein/" in href and text:
                tm_club = text
                break
        if not tm_club:
            for cell in cells[2:5]:
                t = cell.get_text(strip=True)
                if t and not t.isdigit() and len(t) > 1:
                    tm_club = t
                    break

        market_value_eur = ""
        for cell in reversed(cells):
            text = cell.get_text(strip=True)
            if re.search(r"[\d.,]+\s*[mk€]", text, re.I):
                market_value_eur = _parse_value(text)
                break

        results.append({
            "tm_id": tm_id,
            "tm_name": tm_name,
            "tm_club": tm_club,
            "tm_url": tm_url,
            "tm_photo_url": tm_photo_url,
            "market_value_eur": market_value_eur,
        })

    return results


# ── Busqueda de un jugador ────────────────────────────────────────────────────

def _tm_get(sess, query: str, retries: int) -> tuple[int, str]:
    for attempt in range(1, retries + 1):
        try:
            r = sess.get(
                TM_SEARCH,
                params={"query": query, "Spieler_page": "0"},
                headers=HEADERS,
                timeout=15,
            )
            if r.status_code == 429:
                wait = SLEEP_RETRY * attempt
                print("      [429] Rate limit. Esperando {}s ...".format(wait))
                time.sleep(wait)
                continue
            return r.status_code, r.text
        except Exception as e:
            if attempt == retries:
                return -1, str(e)
            time.sleep(SLEEP_RETRY)
    return -1, "max_retries"


def _search_and_filter(sess, query: str, sur_norm: str, opta_initial: str,
                       retries: int) -> tuple[list[dict], list[dict]]:
    """
    Hace GET a TM con `query`, devuelve (pool_filtrado, candidates_raw).
    pool_filtrado = candidatos que pasan filtro de apellido + inicial.
    """
    status, html = _tm_get(sess, query, retries)
    if status != 200:
        return [], []
    candidates = _parse_search_results(html)
    if not candidates:
        return [], []

    # Filtro apellido
    surname_pool = [c for c in candidates if _norm(_surname(c["tm_name"])) == sur_norm]
    pool = surname_pool if surname_pool else []

    # Filtro inicial
    if pool and opta_initial:
        ip = [c for c in pool if _initial_matches(opta_initial, c["tm_name"])]
        if ip:
            pool = ip

    return pool, candidates


def search_player(
    sess, name: str, opta_team: str, retries: int = MAX_RETRIES
) -> tuple[str | None, str, list[dict]]:
    """
    Busca el jugador en TM y devuelve (tm_id, reason, candidates).

    Flujo de busquedas (de mas a menos especifica):
      1. Apellido + palabra clave del club  ("Fernandez Rosario")
         -> Si unico match: 100% confirmado
      2. Solo apellido                      ("Fernandez")
         -> Filtrar por apellido + inicial
         -> Si unico: confirmado
         -> Si varios: desambiguar por club
      3. Nombre completo OPTA               ("G. Fernandez")
         -> Para casos donde apellido = nombre de ciudad/club
      4. Si siguen varios con mismo score de club -> ambiguo
    """
    opta_initial, opta_surname = _parse_opta_name(name)
    sur_norm    = _norm(opta_surname)
    club_kw     = _club_keyword(opta_team)

    # ── Busqueda 1: apellido + palabra clave del club ────────────────────────
    # "Fernandez Rosario" -> mucho mas especifico que solo "Fernandez"
    if club_kw:
        query1 = "{} {}".format(opta_surname, club_kw)
        pool, candidates = _search_and_filter(sess, query1, sur_norm, opta_initial, retries)
        if len(pool) == 1:
            return pool[0]["tm_id"], "found_exact", pool
        if len(pool) > 1:
            # Con nombre de club en query, intentar desambiguar directamente
            scored = sorted(
                [(c, _club_match(opta_team, c["tm_club"])) for c in pool],
                key=lambda x: x[1], reverse=True,
            )
            best, second = scored[0][1], (scored[1][1] if len(scored) > 1 else 0.0)
            if best > second:
                return scored[0][0]["tm_id"], "found_club", pool
        time.sleep(SLEEP_BETWEEN)

    # ── Busqueda 2: solo apellido ────────────────────────────────────────────
    pool, candidates = _search_and_filter(sess, opta_surname, sur_norm, opta_initial, retries)

    # Si no hay resultados con apellido correcto, probar con nombre completo OPTA
    if not pool:
        time.sleep(SLEEP_BETWEEN)
        pool, candidates = _search_and_filter(sess, name, sur_norm, opta_initial, retries)
        # Si aun sin apellido en resultados, usar todos los del nombre completo
        if not pool and candidates:
            ip = [c for c in candidates if _initial_matches(opta_initial, c["tm_name"])]
            pool = ip if ip else candidates

    if not pool:
        return None, "not_found", candidates

    # ── Un solo resultado -> confirmado ──────────────────────────────────────
    if len(pool) == 1:
        return pool[0]["tm_id"], "found_exact", pool

    # ── Varios -> desambiguar por club ───────────────────────────────────────
    scored = sorted(
        [(c, _club_match(opta_team, c["tm_club"])) for c in pool],
        key=lambda x: x[1], reverse=True,
    )
    best_score   = scored[0][1]
    second_score = scored[1][1] if len(scored) > 1 else 0.0

    # Si hay UN ganador claro (cualquier margen con al menos algo de score)
    if best_score > 0 and best_score > second_score:
        return scored[0][0]["tm_id"], "found_club", pool

    # Si quedan solo 2 y los scores son iguales pero uno tiene club info y el otro no
    if len(pool) == 2 and best_score == second_score and best_score == 0.0:
        # Intentar una tercera busqueda con nombre completo + club keyword
        if club_kw:
            time.sleep(SLEEP_BETWEEN)
            pool3, _ = _search_and_filter(
                sess, "{} {}".format(name, club_kw), sur_norm, opta_initial, retries
            )
            if len(pool3) == 1:
                return pool3[0]["tm_id"], "found_exact", pool3

    # Paso 6: ambiguo -> CSV de revision manual
    return None, "ambiguous", pool


# ── Carga de datos ────────────────────────────────────────────────────────────

def load_known_tm_ids() -> set[str]:
    known: set[str] = set()
    if ENTITY_MAP.exists():
        em = pd.read_csv(ENTITY_MAP)
        col = "opta_id" if "opta_id" in em.columns else em.columns[0]
        has = em[em["tm_id"].notna() & (em["tm_id"].astype(str).str.strip() != "")]
        known.update(has[col].astype(str))
    if ECONOMIC.exists():
        ec = pd.read_parquet(ECONOMIC)
        if "tm_id" in ec.columns:
            col = "opta_id" if "opta_id" in ec.columns else "player_id"
            has = ec[ec["tm_id"].notna() & (ec["tm_id"].astype(str).str.strip() != "")]
            if col in ec.columns:
                known.update(has[col].astype(str))
    return known


def load_known_names_with_tm() -> set[str]:
    known: set[str] = set()
    if MV_CSV.exists():
        mv = pd.read_csv(MV_CSV)
        if "tm_id" in mv.columns and "name" in mv.columns:
            has = mv[mv["tm_id"].notna() & (mv["tm_id"].astype(str).str.strip() != "")]
            known.update(has["name"].apply(_norm))
    return known


def load_players_to_search(leagues: list[str] | None = None, limit: int = 0) -> pd.DataFrame:
    enriched = pd.read_parquet(ENRICHED)
    if leagues:
        enriched = enriched[enriched["league"].isin(leagues)]
    else:
        enriched = enriched[enriched["league"].isin(SCOPE_LEAGUES)]

    if "season" in enriched.columns:
        enriched = enriched.sort_values("season", ascending=False)

    cols = ["player_id_src", "name", "team", "league"]
    if "position_group" in enriched.columns:
        cols.append("position_group")
    dedup = enriched.drop_duplicates(subset=["player_id_src"], keep="first")[cols].copy()
    dedup["player_id_src"] = dedup["player_id_src"].astype(str)

    known_ids   = load_known_tm_ids()
    known_names = load_known_names_with_tm()
    dedup = dedup[~dedup["player_id_src"].isin(known_ids)]
    dedup = dedup[~dedup["name"].apply(_norm).isin(known_names)]

    if limit > 0:
        dedup = dedup.head(limit)

    return dedup.reset_index(drop=True)


# ── Escritura de resultados ───────────────────────────────────────────────────

MV_CANONICAL = [
    "name", "market_value_eur", "contract_until", "tm_photo_url",
    "tm_id", "age", "foot", "height", "position", "dob",
]


class ResultWriter:

    def __init__(self):
        if ENTITY_MAP.exists():
            self.entity_map = pd.read_csv(ENTITY_MAP)
        else:
            self.entity_map = pd.DataFrame(
                columns=["opta_id", "tm_id", "match_type", "match_confidence", "updated_at"]
            )

        self.mv_rows: dict[str, dict] = {}
        if MV_CSV.exists():
            for _, r in pd.read_csv(MV_CSV).iterrows():
                self.mv_rows[str(r["name"])] = r.to_dict()

        self.progress_rows: list[dict] = []
        self.ambiguous_rows: list[dict] = []

        if PROGRESS_CSV.exists():
            try:
                self.progress_rows = pd.read_csv(PROGRESS_CSV).to_dict("records")
            except Exception:
                pass

    def _now(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    def record_found(self, player_id_src, name, team, league, position, tm_id, reason, candidate):
        now = self._now()
        mask = self.entity_map["opta_id"].astype(str) == player_id_src
        new_row = {
            "opta_id": player_id_src,
            "tm_id": tm_id,
            "match_type": "search_web",
            "match_confidence": 0.9 if reason == "found_club" else 0.95,
            "updated_at": now,
        }
        if mask.any():
            for col, val in new_row.items():
                self.entity_map.loc[mask, col] = val
        else:
            self.entity_map = pd.concat(
                [self.entity_map, pd.DataFrame([new_row])], ignore_index=True
            )

        existing = self.mv_rows.get(name, {})
        self.mv_rows[name] = {
            **existing,
            "name": name,
            "tm_id": tm_id,
            "tm_photo_url": candidate.get("tm_photo_url", existing.get("tm_photo_url", "")),
            "market_value_eur": candidate.get("market_value_eur", existing.get("market_value_eur", "")),
        }

        self.progress_rows.append({
            "player_id_src": player_id_src,
            "name": name,
            "team": team,
            "league": league,
            "position": position,
            "status": "found",
            "tm_id": tm_id,
            "reason": reason,
            "processed_at": now,
        })

    def record_failed(self, player_id_src, name, team, league, position, reason, candidates):
        now = self._now()
        candidates_json = json.dumps(
            [{"tm_id": c["tm_id"], "tm_name": c["tm_name"], "tm_club": c["tm_club"]}
             for c in candidates[:5]],
            ensure_ascii=False,
        )
        self.ambiguous_rows.append({
            "player_id_src": player_id_src,
            "name": name,
            "team": team,
            "league": league,
            "position": position,
            "reason": reason,
            "candidates_json": candidates_json,
        })
        self.progress_rows.append({
            "player_id_src": player_id_src,
            "name": name,
            "team": team,
            "league": league,
            "position": position,
            "status": reason,
            "tm_id": "",
            "reason": reason,
            "processed_at": now,
        })

    def flush(self):
        self.entity_map.to_csv(ENTITY_MAP, index=False)

        all_fields = list({col for row in self.mv_rows.values() for col in row})
        ordered = [f for f in MV_CANONICAL if f in all_fields] + \
                  [f for f in all_fields if f not in MV_CANONICAL]
        rows_out = [{f: row.get(f, "") for f in ordered} for row in self.mv_rows.values()]
        with open(MV_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=ordered)
            w.writeheader()
            w.writerows(rows_out)

        pd.DataFrame(self.progress_rows).to_csv(PROGRESS_CSV, index=False)

        if self.ambiguous_rows:
            amb_fields = ["player_id_src", "name", "team", "league", "position",
                          "reason", "candidates_json"]
            with open(AMBIGUOUS_CSV, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=amb_fields)
                w.writeheader()
                w.writerows(self.ambiguous_rows)

    def get_processed_ids(self) -> set[str]:
        return {str(r["player_id_src"]) for r in self.progress_rows}


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--league",      action="append", help="Filtrar por liga")
    ap.add_argument("--limit",       type=int, default=0)
    ap.add_argument("--resume",      action="store_true")
    ap.add_argument("--dry-run",     action="store_true")
    ap.add_argument("--flush-every", type=int, default=50)
    args = ap.parse_args()

    print("=" * 60)
    print("fetch_tm_ids.py -- Enriquecimiento TM masivo")
    print("=" * 60)

    players = load_players_to_search(leagues=args.league, limit=args.limit)
    print("[INFO] Jugadores sin tm_id a buscar: {:,}".format(len(players)))

    if args.dry_run:
        print(players.head(20).to_string())
        return

    writer = ResultWriter()
    already_done = writer.get_processed_ids()

    if args.resume and already_done:
        before = len(players)
        players = players[~players["player_id_src"].isin(already_done)]
        print("[INFO] Reanudando: {:,} ya procesados, quedan {:,}".format(
            before - len(players), len(players)))

    sess  = _session()
    stats = {"found": 0, "not_found": 0, "ambiguous": 0, "error": 0}
    total = len(players)

    print("\nIniciando busqueda de {:,} jugadores...".format(total))
    print("Sleep: {}s | Max retries: {}".format(SLEEP_BETWEEN, MAX_RETRIES))
    print("-" * 60)

    for i, row in enumerate(players.itertuples(), 1):
        player_id = str(row.player_id_src)
        name      = str(row.name)
        team      = str(row.team)
        league    = str(row.league)
        position  = str(getattr(row, "position_group", ""))

        pct = i / total * 100
        print("[{:>6}/{}] ({:5.1f}%) {} | {} | {}".format(
            i, total, pct, name, team, league), end=" -> ", flush=True)

        tm_id, reason, candidates = search_player(sess, name, team)

        if tm_id:
            best = next((c for c in candidates if c["tm_id"] == tm_id),
                        candidates[0] if candidates else {})
            writer.record_found(player_id, name, team, league, position, tm_id, reason, best)
            stats["found"] += 1
            print("OK (tm_id={}, {})".format(tm_id, reason))
        elif reason.startswith("error"):
            writer.record_failed(player_id, name, team, league, position, reason, candidates)
            stats["error"] += 1
            print("ERROR ({})".format(reason))
        elif reason == "ambiguous":
            writer.record_failed(player_id, name, team, league, position, reason, candidates)
            stats["ambiguous"] += 1
            print("AMBIGUO ({} candidatos)".format(len(candidates)))
        else:
            writer.record_failed(player_id, name, team, league, position, "not_found", [])
            stats["not_found"] += 1
            print("NO ENCONTRADO")

        if i % args.flush_every == 0:
            writer.flush()
            print("\n    >>> Checkpoint [{}/{}] -- Encontrados: {} ({:.1f}%) | "
                  "No encontrados: {} | Ambiguos: {} | Errores: {}\n".format(
                      i, total, stats["found"], stats["found"] / i * 100,
                      stats["not_found"], stats["ambiguous"], stats["error"]))

        time.sleep(SLEEP_BETWEEN)

    writer.flush()

    print("\n" + "=" * 60)
    print("RESUMEN FINAL")
    print("=" * 60)
    print("  Buscados         : {:>8,}".format(total))
    print("  Encontrados      : {:>8,}  ({:.1f}%)".format(
        stats["found"], stats["found"] / total * 100))
    print("  No encontrados   : {:>8,}  ({:.1f}%)".format(
        stats["not_found"], stats["not_found"] / total * 100))
    print("  Ambiguos         : {:>8,}  ({:.1f}%)".format(
        stats["ambiguous"], stats["ambiguous"] / total * 100))
    print("  Errores          : {:>8,}  ({:.1f}%)".format(
        stats["error"], stats["error"] / total * 100))
    print()
    print("  entity_map    ->", ENTITY_MAP)
    print("  market_values ->", MV_CSV)
    print("  checkpoint    ->", PROGRESS_CSV)
    if stats["ambiguous"] + stats["not_found"] > 0:
        print("  revision manual ->", AMBIGUOUS_CSV)
    print("=" * 60)


if __name__ == "__main__":
    main()
