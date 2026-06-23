"""
fetch_tm_ids.py
===============
Busca el player_id de Transfermarkt para todos los jugadores de las 16 ligas
del scope de Rayo Vallecano que aún NO tienen tm_id en la base de datos.

FUENTES:
  - data/processed/player_seasons_enriched.parquet  → jugadores OPTA a buscar
  - data/processed/player_entity_map.csv            → ya tienen tm_id (skip)
  - data/processed/player_economic.parquet          → también tienen tm_id (skip)
  - config/market_values.csv                        → ídem

OUTPUTS:
  - data/processed/player_entity_map.csv            → actualizado con nuevos tm_id
  - config/market_values.csv                        → actualizado con datos TM
  - data/processed/tm_enrichment_ambiguous.csv      → casos sin resolver (manual)
  - data/processed/tm_enrichment_progress.csv       → checkpoint para reanudar

Uso:
    python scripts/fetch_tm_ids.py                   # todos los jugadores
    python scripts/fetch_tm_ids.py --league Spain_Primera_Division
    python scripts/fetch_tm_ids.py --limit 500       # probar con 500
    python scripts/fetch_tm_ids.py --resume          # reanudar desde checkpoint
    python scripts/fetch_tm_ids.py --dry-run         # solo muestra cuántos hay

Es REANUDABLE: si lo interrumpes y lo vuelves a lanzar con --resume sigue donde lo dejó.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
from bs4 import BeautifulSoup

# ── Rutas ─────────────────────────────────────────────────────────────────────
PROC           = ROOT / "data" / "processed"
ENRICHED       = PROC / "player_seasons_enriched.parquet"
ENTITY_MAP     = PROC / "player_entity_map.csv"
ECONOMIC       = PROC / "player_economic.parquet"
MV_CSV         = ROOT / "config" / "market_values.csv"
AMBIGUOUS_CSV  = PROC / "tm_enrichment_ambiguous.csv"
PROGRESS_CSV   = PROC / "tm_enrichment_progress.csv"

# ── Ligas del scope ───────────────────────────────────────────────────────────
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
    "Türkiye_Süper_Lig",
]

# ── HTTP ───────────────────────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Referer": "https://www.transfermarkt.com/",
}
TM_SEARCH = "https://www.transfermarkt.com/schnellsuche/ergebnis/schnellsuche"

SLEEP_BETWEEN  = 1.2   # segundos entre peticiones
SLEEP_RETRY    = 8.0   # segundos tras un error 429 / timeout
MAX_RETRIES    = 4     # intentos por jugador
RESULTS_LIMIT  = 20    # máximo de resultados de búsqueda a evaluar


# ── Utilidades de normalización ───────────────────────────────────────────────
def _norm(s: str) -> str:
    """Normaliza a ASCII minúsculas sin tildes."""
    return (
        unicodedata.normalize("NFKD", str(s))
        .encode("ascii", "ignore")
        .decode()
        .lower()
        .strip()
    )


def _surname(name: str) -> str:
    """Último token significativo del nombre normalizado."""
    parts = [p for p in _norm(name).replace(".", " ").split() if len(p) > 1]
    return parts[-1] if parts else _norm(name)


def _norm_club(team: str) -> str:
    """Normalización básica de club para comparación."""
    return re.sub(r"[^a-z0-9]", "", _norm(team))


def _club_match(opta_team: str, tm_team: str) -> float:
    """
    Puntúa la similitud de clubs entre 0 y 1.
    1.0  → coincidencia perfecta normalizada
    0.5  → uno contiene al otro
    0.0  → sin relación
    """
    a = _norm_club(opta_team)
    b = _norm_club(tm_team)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.5
    # Intento parcial por tokens
    ta = set(a.split())
    tb = set(b.split())
    if not ta or not tb:
        return 0.0
    overlap = len(ta & tb) / max(len(ta), len(tb))
    return overlap * 0.4


# ── Sesión HTTP ───────────────────────────────────────────────────────────────
def _session():
    """cloudscraper si está disponible (elude Cloudflare), si no requests."""
    try:
        import cloudscraper
        s = cloudscraper.create_scraper()
        print("[INFO] Usando cloudscraper")
        return s
    except ImportError:
        import requests
        s = requests.Session()
        s.headers.update(HEADERS)
        print("[INFO] Usando requests (pip install cloudscraper si hay bloqueos)")
        return s


# ── Parsing de resultados TM ──────────────────────────────────────────────────
def _parse_search_results(html: str) -> list[dict]:
    """
    Extrae todos los resultados de jugadores de la página de búsqueda TM.
    Devuelve lista de: {tm_id, tm_name, tm_club, tm_url, tm_photo_url, market_value_eur}
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []

    # TM muestra los resultados de jugadores en la primera tabla.items
    # dentro de la sección de "Spieler" (jugadores)
    table = soup.select_one("table.items tbody")
    if not table:
        return []

    rows = table.select("tr")
    # Descartar filas de cabecera vacías
    for row in rows[:RESULTS_LIMIT]:
        # Saltar filas auxiliares (odd/even de la misma persona)
        if "bg_Mittelfeld" in row.get("class", []) or row.get("class") == ["odd"]:
            pass  # procesamos todo

        cells = row.select("td")
        if len(cells) < 2:
            continue

        # tm_id desde la imagen de portrait
        tm_id = None
        tm_photo_url = ""
        img = row.select_one("img")
        if img:
            raw = img.get("data-src") or img.get("src") or ""
            m = re.search(r"/portrait/(?:small|medium|big|header)/(\d+)", raw)
            if m:
                tm_id = m.group(1)
                tm_photo_url = (
                    f"https://img.a.transfermarkt.technology/portrait/big/{tm_id}.jpg"
                )

        # Si no lo encontramos en la imagen, intentamos el link de perfil
        link_el = row.select_one("td.hauptlink a, a.spielprofil_tooltip")
        tm_name = ""
        tm_url = ""
        if link_el:
            tm_name = link_el.get_text(strip=True)
            href = link_el.get("href", "")
            tm_url = f"https://www.transfermarkt.com{href}" if href else ""
            if not tm_id:
                # Intentar extraer ID de la URL del perfil
                m = re.search(r"/spieler/(\d+)", href)
                if m:
                    tm_id = m.group(1)

        if not tm_id:
            continue

        # Club del jugador — segunda celda con enlace de texto
        tm_club = ""
        club_links = row.select("td a")
        for cl in club_links:
            href = cl.get("href", "")
            text = cl.get_text(strip=True)
            if "/verein/" in href and text:
                tm_club = text
                break
        if not tm_club:
            # Último recurso: texto de la 4ª columna aprox.
            for cell in cells[2:5]:
                t = cell.get_text(strip=True)
                if t and not t.isdigit() and len(t) > 1:
                    tm_club = t
                    break

        # Valor de mercado (columna final)
        market_value_eur = ""
        for cell in reversed(cells):
            text = cell.get_text(strip=True)
            if re.search(r"[\d.,]+\s*[mk€]", text, re.I):
                market_value_eur = _parse_value(text)
                break

        results.append(
            {
                "tm_id": tm_id,
                "tm_name": tm_name,
                "tm_club": tm_club,
                "tm_url": tm_url,
                "tm_photo_url": tm_photo_url,
                "market_value_eur": market_value_eur,
            }
        )

    return results


def _parse_value(text: str):
    """'EUR3.50m' / '€900k' → euros (int) o '' si no parsea."""
    if not text:
        return ""
    t = (
        text.replace("\xa0", " ")
        .strip()
        .lower()
        .replace("€", "")
        .replace("eur", "")
        .strip()
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


# ── Búsqueda de un jugador ────────────────────────────────────────────────────
def search_player(
    sess, name: str, opta_team: str, retries: int = MAX_RETRIES
) -> tuple[str | None, str, list[dict]]:
    """
    Busca `name` en TM y devuelve:
      (tm_id, reason, candidates)
      - tm_id    : str con el ID si hay match claro, None en otro caso
      - reason   : 'found_exact' | 'found_club' | 'ambiguous' | 'not_found' | 'error'
      - candidates: lista de resultados crudos para el CSV de ambiguos
    """
    for attempt in range(1, retries + 1):
        try:
            r = sess.get(
                TM_SEARCH,
                params={"query": name, "Spieler_page": "0"},
                headers=HEADERS,
                timeout=15,
            )
        except Exception as e:
            if attempt == retries:
                return None, f"error:{e}", []
            time.sleep(SLEEP_RETRY)
            continue

        if r.status_code == 429:
            wait = SLEEP_RETRY * attempt
            print(f"      [429] Rate limit. Esperando {wait}s …")
            time.sleep(wait)
            continue
        if r.status_code != 200:
            if attempt == retries:
                return None, f"error:http{r.status_code}", []
            time.sleep(SLEEP_RETRY)
            continue

        # Éxito — parsear
        candidates = _parse_search_results(r.text)
        if not candidates:
            return None, "not_found", []

        # Filtrar por nombre normalizado
        name_norm = _norm(name)
        name_sur  = _surname(name)
        exact_name = [
            c for c in candidates if _norm(c["tm_name"]) == name_norm
        ]
        surname_match = [
            c for c in candidates if _surname(c["tm_name"]) == name_sur
        ]
        pool = exact_name if exact_name else surname_match if surname_match else candidates

        if not pool:
            return None, "not_found", candidates

        # Si solo un resultado, es el bueno
        if len(pool) == 1:
            return pool[0]["tm_id"], "found_exact", pool

        # Varios → desambiguar por club
        scored = [
            (c, _club_match(opta_team, c["tm_club"])) for c in pool
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        best_score  = scored[0][1]
        second_score = scored[1][1] if len(scored) > 1 else 0.0

        if best_score >= 0.5 and best_score > second_score:
            return scored[0][0]["tm_id"], "found_club", pool

        # Empate o ambigüedad
        return None, "ambiguous", pool

    return None, "error:max_retries", []


# ── Carga de datos ─────────────────────────────────────────────────────────────
def load_known_tm_ids() -> set[str]:
    """Carga todos los opta_id que ya tienen tm_id (en cualquier fuente)."""
    known: set[str] = set()

    # entity_map
    if ENTITY_MAP.exists():
        em = pd.read_csv(ENTITY_MAP)
        col = "opta_id" if "opta_id" in em.columns else em.columns[0]
        has = em[em["tm_id"].notna() & (em["tm_id"].astype(str).str.strip() != "")]
        known.update(has[col].astype(str))

    # economic
    if ECONOMIC.exists():
        ec = pd.read_parquet(ECONOMIC)
        if "tm_id" in ec.columns:
            col = "opta_id" if "opta_id" in ec.columns else "player_id"
            has = ec[ec["tm_id"].notna() & (ec["tm_id"].astype(str).str.strip() != "")]
            if col in ec.columns:
                known.update(has[col].astype(str))

    return known


def load_known_names_with_tm() -> set[str]:
    """
    Carga nombres normalizados que ya tienen tm_id en market_values.csv
    (para evitar buscar por nombre cuando ya está resuelto).
    """
    known: set[str] = set()
    if MV_CSV.exists():
        mv = pd.read_csv(MV_CSV)
        if "tm_id" in mv.columns and "name" in mv.columns:
            has = mv[mv["tm_id"].notna() & (mv["tm_id"].astype(str).str.strip() != "")]
            known.update(has["name"].apply(_norm))
    return known


def load_progress() -> dict[str, dict]:
    """Carga el progreso guardado (checkpoint)."""
    progress: dict[str, dict] = {}
    if PROGRESS_CSV.exists():
        try:
            df = pd.read_csv(PROGRESS_CSV)
            for _, row in df.iterrows():
                progress[str(row["player_id_src"])] = row.to_dict()
        except Exception:
            pass
    return progress


def load_players_to_search(
    leagues: list[str] | None = None,
    limit: int = 0,
) -> pd.DataFrame:
    """
    Devuelve el DataFrame de jugadores únicos (player_id_src, name, team, league, position_group)
    que hay que buscar, excluyendo los que ya tienen tm_id.
    """
    enriched = pd.read_parquet(ENRICHED)

    if leagues:
        enriched = enriched[enriched["league"].isin(leagues)]
    else:
        enriched = enriched[enriched["league"].isin(SCOPE_LEAGUES)]

    # Agrupar por jugador (puede aparecer en varias temporadas)
    # Cogemos la temporada más reciente para tener el equipo actual
    sort_cols = ["player_id_src"]
    if "season" in enriched.columns:
        enriched = enriched.sort_values("season", ascending=False)

    dedup = enriched.drop_duplicates(subset=["player_id_src"], keep="first")[
        ["player_id_src", "name", "team", "league"]
        + (["position_group"] if "position_group" in enriched.columns else [])
    ].copy()
    dedup["player_id_src"] = dedup["player_id_src"].astype(str)

    # Excluir los que ya tienen tm_id por OPTA ID
    known_ids = load_known_tm_ids()
    dedup = dedup[~dedup["player_id_src"].isin(known_ids)]

    # Excluir los que ya aparecen en market_values por nombre
    known_names = load_known_names_with_tm()
    dedup = dedup[~dedup["name"].apply(_norm).isin(known_names)]

    if limit > 0:
        dedup = dedup.head(limit)

    return dedup.reset_index(drop=True)


# ── Escritura de resultados ───────────────────────────────────────────────────
class ResultWriter:
    """Gestiona la escritura incremental de todos los outputs."""

    def __init__(self):
        # Cargar entity_map existente
        if ENTITY_MAP.exists():
            self.entity_map = pd.read_csv(ENTITY_MAP)
        else:
            self.entity_map = pd.DataFrame(
                columns=["opta_id", "tm_id", "match_type", "match_confidence", "updated_at"]
            )

        # Cargar market_values existente
        self.mv_rows: dict[str, dict] = {}
        MV_FIELDS = ["name", "market_value_eur", "contract_until", "tm_photo_url", "tm_id", "age", "foot", "height", "position", "dob"]
        if MV_CSV.exists():
            for _, r in pd.read_csv(MV_CSV).iterrows():
                self.mv_rows[str(r["name"])] = r.to_dict()

        # Buffer de progreso y ambiguos
        self.progress_rows: list[dict] = []
        self.ambiguous_rows: list[dict] = []

        # Cargar progreso existente
        if PROGRESS_CSV.exists():
            existing_prog = pd.read_csv(PROGRESS_CSV)
            self.progress_rows = existing_prog.to_dict("records")

    def record_found(
        self,
        player_id_src: str,
        name: str,
        team: str,
        league: str,
        position: str,
        tm_id: str,
        reason: str,
        candidate: dict,
    ):
        """Registra un match confirmado."""
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

        # entity_map — insertar o actualizar
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

        # market_values — insertar o actualizar
        existing = self.mv_rows.get(name, {})
        self.mv_rows[name] = {
            **existing,
            "name": name,
            "tm_id": tm_id,
            "tm_photo_url": candidate.get("tm_photo_url", existing.get("tm_photo_url", "")),
            "market_value_eur": candidate.get("market_value_eur", existing.get("market_value_eur", "")),
        }

        # Progreso
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

    def record_failed(
        self,
        player_id_src: str,
        name: str,
        team: str,
        league: str,
        position: str,
        reason: str,
        candidates: list[dict],
    ):
        """Registra un caso no resuelto para revisión manual."""
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

        candidates_json = json.dumps(
            [{"tm_id": c["tm_id"], "tm_name": c["tm_name"], "tm_club": c["tm_club"]} for c in candidates[:5]],
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
        """Guarda todos los outputs a disco."""
        # entity_map
        self.entity_map.to_csv(ENTITY_MAP, index=False)

        # market_values — preservar columnas originales
        all_mv_fields = list({col for row in self.mv_rows.values() for col in row})
        # Orden canónico
        canonical = ["name", "market_value_eur", "contract_until", "tm_photo_url", "tm_id",
                     "age", "foot", "height", "position", "dob"]
        ordered = [f for f in canonical if f in all_mv_fields] + \
                  [f for f in all_mv_fields if f not in canonical]
        rows_to_write = [
            {f: row.get(f, "") for f in ordered}
            for row in self.mv_rows.values()
        ]
        with open(MV_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=ordered)
            w.writeheader()
            w.writerows(rows_to_write)

        # progreso (checkpoint)
        pd.DataFrame(self.progress_rows).to_csv(PROGRESS_CSV, index=False)

        # ambiguos
        if self.ambiguous_rows:
            amb_fields = ["player_id_src", "name", "team", "league", "position", "reason", "candidates_json"]
            with open(AMBIGUOUS_CSV, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=amb_fields)
                w.writeheader()
                w.writerows(self.ambiguous_rows)

    def get_processed_ids(self) -> set[str]:
        """IDs ya procesados en esta sesión o sesiones previas."""
        return {str(r["player_id_src"]) for r in self.progress_rows}


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Busca tm_id en Transfermarkt para todos los jugadores del scope")
    ap.add_argument("--league",   help="Filtrar por liga concreta (puede repetirse)", action="append")
    ap.add_argument("--limit",    type=int, default=0, help="Máximo de jugadores a procesar (0 = todos)")
    ap.add_argument("--resume",   action="store_true", help="Reanudar desde el checkpoint guardado")
    ap.add_argument("--dry-run",  action="store_true", help="Solo muestra estadísticas, no busca")
    ap.add_argument("--flush-every", type=int, default=50, help="Guardar a disco cada N jugadores (default 50)")
    args = ap.parse_args()

    print("=" * 60)
    print("fetch_tm_ids.py — Enriquecimiento TM masivo")
    print("=" * 60)

    leagues = args.league or None
    players = load_players_to_search(leagues=leagues, limit=args.limit)
    print(f"[INFO] Jugadores sin tm_id a buscar: {len(players):,}")

    if args.dry_run:
        print(players.head(20).to_string())
        return

    writer = ResultWriter()
    already_done = writer.get_processed_ids()

    # Filtrar los ya procesados en sesiones anteriores
    if args.resume:
        before = len(players)
        players = players[~players["player_id_src"].isin(already_done)]
        print(f"[INFO] Reanudando: {before - len(players):,} ya procesados, quedan {len(players):,}")
    else:
        if already_done:
            print(f"[AVISO] Hay {len(already_done):,} jugadores en el checkpoint. Usa --resume para saltarlos.")

    sess = _session()

    stats = {"found": 0, "not_found": 0, "ambiguous": 0, "error": 0}
    total = len(players)

    print(f"\nIniciando búsqueda de {total:,} jugadores...")
    print(f"Sleep entre peticiones: {SLEEP_BETWEEN}s | Max retries: {MAX_RETRIES}")
    print("-" * 60)

    for i, row in enumerate(players.itertuples(), 1):
        player_id = str(row.player_id_src)
        name      = str(row.name)
        team      = str(row.team)
        league    = str(row.league)
        position  = str(getattr(row, "position_group", ""))

        # Progreso
        pct = i / total * 100
        print(f"[{i:>6}/{total}] ({pct:5.1f}%) {name} | {team} | {league}", end=" → ", flush=True)

        tm_id, reason, candidates = search_player(sess, name, team)

        if tm_id:
            best_candidate = next((c for c in candidates if c["tm_id"] == tm_id), candidates[0] if candidates else {})
            writer.record_found(player_id, name, team, league, position, tm_id, reason, best_candidate)
            stats["found"] += 1
            print(f"OK (tm_id={tm_id}, {reason})")
        elif reason.startswith("error"):
            writer.record_failed(player_id, name, team, league, position, reason, candidates)
            stats["error"] += 1
            print(f"ERROR ({reason})")
        elif reason == "ambiguous":
            writer.record_failed(player_id, name, team, league, position, reason, candidates)
            stats["ambiguous"] += 1
            print(f"AMBIGUO ({len(candidates)} candidatos)")
        else:
            writer.record_failed(player_id, name, team, league, position, "not_found", [])
            stats["not_found"] += 1
            print("NO ENCONTRADO")

        # Flush periódico
        if i % args.flush_every == 0:
            writer.flush()
            found_pct = stats["found"] / i * 100
            print(f"\n    >>> Checkpoint guardado [{i}/{total}] — "
                  f"Encontrados: {stats['found']} ({found_pct:.1f}%) | "
                  f"No encontrados: {stats['not_found']} | "
                  f"Ambiguos: {stats['ambiguous']} | Errores: {stats['error']}\n")

        time.sleep(SLEEP_BETWEEN)

    # Flush final
    writer.flush()

    print("\n" + "=" * 60)
    print("RESUMEN FINAL")
    print("=" * 60)
    print(f"  Buscados         : {total:>8,}")
    print(f"  Encontrados      : {stats['found']:>8,}  ({stats['found']/total*100:.1f}%)")
    print(f"  No encontrados   : {stats['not_found']:>8,}  ({stats['not_found']/total*100:.1f}%)")
    print(f"  Ambiguos         : {stats['ambiguous']:>8,}  ({stats['ambiguous']/total*100:.1f}%)")
    print(f"  Errores          : {stats['error']:>8,}  ({stats['error']/total*100:.1f}%)")
    print()
    print(f"  entity_map       → {ENTITY_MAP}")
    print(f"  market_values    → {MV_CSV}")
    print(f"  checkpoint       → {PROGRESS_CSV}")
    if stats["ambiguous"] + stats["not_found"] > 0:
        print(f"  revisión manual  → {AMBIGUOUS_CSV}")
    print("=" * 60)


if __name__ == "__main__":
    main()
