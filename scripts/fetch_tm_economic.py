"""
fetch_tm_economic.py
====================
Scraping mejorado de Transfermarkt para obtener datos económicos y contractuales
completos de los jugadores del scope.

MEJORAS respecto a fetch_tm_data.py:
  - Usa el tm_id de player_entity_map.csv para ir directamente al perfil del jugador
    (sin búsqueda por nombre, eliminando falsos positivos).
  - Extrae: valor de mercado, contrato, historial de valores, pie, altura, dob, nac.
  - Modo --incremental: solo actualiza jugadores con last_updated > DAYS_STALE días.
  - Genera tm_economic_raw.json para trazabilidad, separado de market_values.csv.
  - Respeta market_values.csv: actualiza los campos económicos sin borrar las fotos.

Uso:
    python scripts/fetch_tm_economic.py                      # scope Rayo + candidatos
    python scripts/fetch_tm_economic.py --rayo               # solo plantilla Rayo
    python scripts/fetch_tm_economic.py --incremental        # solo desactualizados
    python scripts/fetch_tm_economic.py --limit 200          # máximo de jugadores
    python scripts/fetch_tm_economic.py --by-name            # búsqueda por nombre (fallback)
    python scripts/fetch_tm_economic.py --days-stale 14      # umbral de días para actualizar

REQUISITOS:
    pip install requests beautifulsoup4 lxml
    (Opcional) pip install cloudscraper   # para evitar bloqueos de Cloudflare
"""
from __future__ import annotations
import argparse
import csv
import json
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils.config import settings, club_profile  # noqa: E402

S    = settings()
PROC = Path(S["paths"]["data_processed"])

MV_CSV          = ROOT / "config" / "market_values.csv"
ENTITY_MAP      = PROC / "player_entity_map.csv"
TM_RAW_JSON     = PROC / "tm_economic_raw.json"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Referer": "https://www.transfermarkt.com/",
}
TM_BASE   = "https://www.transfermarkt.com"
TM_SEARCH = f"{TM_BASE}/schnellsuche/ergebnis/schnellsuche"
TM_PROFILE = f"{TM_BASE}/spieler/profil/spieler"   # + /{tm_id}
SLEEP_MIN  = 0.8   # segundos entre peticiones
SLEEP_MAX  = 1.4


def _norm(s) -> str:
    t = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return t.lower().strip()


def _session():
    """Sesión con cloudscraper si disponible, si no requests estándar."""
    try:
        import cloudscraper
        s = cloudscraper.create_scraper()
        print("[INFO] Usando cloudscraper (esquiva Cloudflare)")
        return s
    except ImportError:
        import requests
        s = requests.Session()
        s.headers.update(HEADERS)
        return s


def _parse_value(text) -> float | None:
    """'€3.50m' / '€900k' / '3,5 Mio. €' -> euros."""
    if not text:
        return None
    t = str(text).replace("\xa0", " ").strip().lower()
    t = t.replace("€", "").replace("eur", "").replace(",", ".").strip()
    m = re.search(r"([\d.]+)\s*([mk]|mio|mill)?", t)
    if not m:
        return None
    try:
        val = float(m.group(1))
    except ValueError:
        return None
    unit = (m.group(2) or "").strip()
    if unit in ("m", "mio", "mill"):
        return val * 1_000_000
    if unit == "k":
        return val * 1_000
    return val


def _parse_date(text) -> str | None:
    """'Jun 30, 2028' / '30.06.2028' / '2028-06-30' -> 'YYYY-MM-DD'."""
    if not text:
        return None
    t = str(text).strip()
    for fmt in ("%b %d, %Y", "%d.%m.%Y", "%Y-%m-%d", "%B %d, %Y"):
        try:
            return datetime.strptime(t, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Año solo
    m = re.search(r"\b(20\d{2})\b", t)
    if m:
        return f"{m.group(1)}-06-30"
    return None


def fetch_by_tm_id(sess, tm_id: str, name: str = "") -> dict | None:
    """Obtiene datos del perfil TM directo por tm_id (más fiable que por búsqueda)."""
    from bs4 import BeautifulSoup
    url = f"{TM_PROFILE}/{tm_id}"
    try:
        r = sess.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            return None
    except Exception as e:
        print(f"   [ERR] {name} (tm_id={tm_id}): {e}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    out = {"tm_id": tm_id, "name": name, "source": "tm_id_direct"}

    # Valor de mercado
    mv_el = soup.select_one(".data-header__market-value-wrapper, [class*='market-value']")
    if mv_el:
        out["market_value_eur"] = _parse_value(mv_el.get_text(" ", strip=True))

    # Info table (contrato, dob, nacionalidad, pie, altura)
    for row in soup.select(".info-table__content-row, .info-table tr"):
        label_el = row.select_one(".info-table__content--regular, th, .info-table__content-row--right")
        value_el = row.select_one(".info-table__content--bold, td, .info-table__content-row--left")
        if not label_el or not value_el:
            continue
        label = label_el.get_text(strip=True).lower()
        value = value_el.get_text(strip=True)
        if "contract" in label or "contrato" in label:
            out["contract_until"] = _parse_date(value)
        elif "date of birth" in label or "fecha" in label and "nacim" in label:
            out["dob"] = _parse_date(value)
            age_m = re.search(r"\((\d+)\)", value)
            if age_m:
                out["age"] = int(age_m.group(1))
        elif "nationality" in label or "nacionalidad" in label:
            out["nationality"] = value
        elif "foot" in label or "pie" in label:
            out["foot"] = value
        elif "height" in label or "altura" in label:
            out["height"] = value
        elif "position" in label or "posicion" in label or "posición" in label:
            out["position"] = value
        elif "club" in label and "current" in label:
            out["club"] = value

    # Foto
    img = soup.select_one(".data-header__profile-image img, img.data-header__profile-image")
    if img:
        src = img.get("src") or img.get("data-src") or ""
        m = re.search(r"/portrait/(?:small|medium|big|header)/(\d+)", src)
        if m:
            out["tm_photo_url"] = f"https://img.a.transfermarkt.technology/portrait/big/{m.group(1)}.jpg"

    out["last_updated"] = str(date.today())
    return out


def fetch_by_name_search(sess, name: str, team: str = "") -> dict | None:
    """Búsqueda por nombre (fallback cuando no hay tm_id). Mismo método que fetch_tm_data.py."""
    from bs4 import BeautifulSoup
    query = f"{name} {team}".strip()
    try:
        r = sess.get(TM_SEARCH, params={"query": query, "Spieler_page": "0"},
                     headers=HEADERS, timeout=12)
        if r.status_code != 200:
            return None
    except Exception as e:
        print(f"   [ERR] búsqueda {name}: {e}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    row = soup.select_one("table.items tbody tr")
    if not row and team:
        time.sleep(0.4)
        return fetch_by_name_search(sess, name)
    if not row:
        return None

    # Extraer tm_id de la imagen
    tm_id = None
    img = row.select_one("img.bilderrahmen-fixed, td.hauptlink img, img")
    if img:
        raw = img.get("data-src") or img.get("src") or ""
        m = re.search(r"/portrait/(?:small|medium|big|header)/(\d+)", raw)
        if m:
            tm_id = m.group(1)

    if tm_id:
        time.sleep(SLEEP_MIN)
        return fetch_by_tm_id(sess, tm_id, name)

    return None


# ── Gestión del CSV de market_values ─────────────────────────────────────────

def load_mv_dict() -> dict[str, dict]:
    """Carga market_values.csv como dict {nombre: row_dict}."""
    if not MV_CSV.exists():
        return {}
    df = pd.read_csv(MV_CSV)
    return {str(r["name"]): r.to_dict() for _, r in df.iterrows()}


MV_FIELDS = ["name", "market_value_eur", "contract_until", "tm_photo_url",
             "tm_id", "age", "foot", "height", "position", "dob"]

# campos adicionales que persist en raw JSON pero no en market_values.csv
RAW_EXTRA_FIELDS = ["nationality", "club", "last_updated"]


def save_mv_dict(mv: dict[str, dict]) -> None:
    rows = []
    for name, d in mv.items():
        rows.append({f: d.get(f, "") for f in MV_FIELDS})
    with open(MV_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MV_FIELDS)
        w.writeheader()
        w.writerows(rows)


def save_raw_json(raw: dict[str, dict]) -> None:
    PROC.mkdir(parents=True, exist_ok=True)
    with open(TM_RAW_JSON, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)


# ── Generación de targets ─────────────────────────────────────────────────────

def get_targets(rayo_only: bool, limit: int) -> list[tuple[str, str, str | None]]:
    """
    Devuelve lista de (name, team, tm_id_or_None).
    tm_id se obtiene de player_entity_map.csv cuando existe.
    """
    targets: list[tuple[str, str, str | None]] = []

    # 1) Plantilla Rayo
    cp = club_profile()
    for _grp, players in cp.get("squad_2025_26", {}).items():
        for p in players:
            targets.append((p["name"], "Rayo Vallecano", None))

    if rayo_only:
        return targets[:limit]

    # 2) Top candidatos de scouting (de signing_shortlists.json si existe)
    shortlists_path = PROC / "signing_shortlists.json"
    if shortlists_path.exists():
        try:
            sl = json.load(open(shortlists_path, encoding="utf-8"))
            for _role, candidates in sl.items():
                for c in candidates:
                    if c.get("name"):
                        targets.append((c["name"], c.get("team", ""), None))
        except Exception:
            pass

    # 3) Enriquecer con tm_id desde entity_map
    if ENTITY_MAP.exists():
        em = pd.read_csv(ENTITY_MAP, dtype=str).fillna("")
        em_dict = {}
        for _, r in em.iterrows():
            if r.get("tm_id"):
                em_dict[_norm(r.get("opta_name", ""))] = r["tm_id"]
        targets = [
            (name, team, em_dict.get(_norm(name)))
            for name, team, _ in targets
        ]

    # Deduplicar
    seen: set[str] = set()
    unique: list[tuple[str, str, str | None]] = []
    for name, team, tm_id in targets:
        if name not in seen:
            seen.add(name)
            unique.append((name, team, tm_id))

    return unique[:limit]


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rayo",        action="store_true", help="Solo plantilla Rayo")
    ap.add_argument("--incremental", action="store_true", help="Solo jugadores desactualizados")
    ap.add_argument("--by-name",     action="store_true", help="Forzar búsqueda por nombre (sin tm_id)")
    ap.add_argument("--limit",       type=int, default=300)
    ap.add_argument("--days-stale",  type=int, default=30, help="Días para considerar dato desactualizado")
    args = ap.parse_args()

    mv   = load_mv_dict()
    raw  = json.load(open(TM_RAW_JSON, encoding="utf-8")) if TM_RAW_JSON.exists() else {}

    targets = get_targets(rayo_only=args.rayo, limit=args.limit)
    print(f"\nTargets: {len(targets)} jugadores")

    stale_cutoff = (date.today() - timedelta(days=args.days_stale)).isoformat()
    sess = _session()
    updated = 0

    for i, (name, team, tm_id) in enumerate(targets, 1):
        # Comprobar si necesita actualización
        if args.incremental:
            existing_raw = raw.get(name, {})
            last = str(existing_raw.get("last_updated") or "")
            if last >= stale_cutoff:
                continue  # datos frescos, saltar

        if args.by_name:
            tm_id = None  # forzar búsqueda por nombre

        if tm_id:
            info = fetch_by_tm_id(sess, tm_id, name)
        else:
            info = fetch_by_name_search(sess, name, team)

        if info:
            # Actualizar raw JSON (fuente de trazabilidad)
            raw[name] = {**raw.get(name, {}), **info, "opta_name": name}

            # Actualizar market_values.csv (preservando lo que ya había)
            prev = mv.get(name, {})
            merged = dict(prev)
            merged["name"] = name
            field_map = {
                "market_value_eur": "market_value_eur",
                "contract_until":   "contract_until",
                "tm_photo_url":     "tm_photo_url",
                "tm_id":            "tm_id",
                "age":              "age",
                "foot":             "foot",
                "height":           "height",
                "position":         "position",
                "dob":              "dob",
            }
            for raw_f, mv_f in field_map.items():
                v = info.get(raw_f)
                if v not in (None, "", "nan"):
                    merged[mv_f] = v
            mv[name] = merged
            updated += 1

            print(f"  [{i}/{len(targets)}] {name}: "
                  f"valor={info.get('market_value_eur')} "
                  f"contrato={info.get('contract_until')} "
                  f"tm_id={info.get('tm_id', tm_id)}")
        else:
            print(f"  [{i}/{len(targets)}] {name}: sin datos")

        # Guardar cada 20 para no perder progreso
        if i % 20 == 0:
            save_mv_dict(mv)
            save_raw_json(raw)

        time.sleep(SLEEP_MIN + (SLEEP_MAX - SLEEP_MIN) * (i % 3) / 3)

    save_mv_dict(mv)
    save_raw_json(raw)

    print(f"\n✅ {updated} jugadores actualizados")
    print(f"   market_values.csv: {len(mv)} entradas")
    n_mv  = sum(1 for v in mv.values() if v.get("market_value_eur") not in (None, "", "nan"))
    n_con = sum(1 for v in mv.values() if v.get("contract_until") not in (None, "", "nan"))
    print(f"   con market_value : {n_mv} ({100*n_mv/max(1,len(mv)):.1f}%)")
    print(f"   con contract_until: {n_con} ({100*n_con/max(1,len(mv)):.1f}%)")
    print("\nEjecuta ahora:")
    print("  python scripts/build_entity_map.py")
    print("  python scripts/build_economic_dataset.py")


if __name__ == "__main__":
    main()
