"""
fetch_tm_data.py
================
Rellena config/market_values.csv con datos de Transfermarkt (FOTO + VALOR DE
MERCADO + FIN DE CONTRATO + tm_id) para una lista de jugadores.

EJECUTAR EN TU ORDENADOR (necesita salida a internet). El dashboard luego lee
ese CSV sin volver a scrapear, asi que las fotos y los valores salen al instante.

Uso:
    python scripts/fetch_tm_data.py                 # plantilla Rayo + top candidatos por rol
    python scripts/fetch_tm_data.py --rayo          # solo la plantilla del Rayo
    python scripts/fetch_tm_data.py --limit 150     # tope de jugadores a buscar
    python scripts/fetch_tm_data.py --refresh       # reintenta tambien los ya guardados

Es idempotente y reanudable: no vuelve a buscar a quien ya tenga datos salvo --refresh.
Si Transfermarkt bloquea las peticiones, instala cloudscraper:  pip install cloudscraper
"""
from __future__ import annotations
import argparse
import csv
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
from src.utils.config import club_profile  # noqa: E402

MV_CSV = ROOT / "config" / "market_values.csv"
FIELDS = ["name", "market_value_eur", "contract_until", "tm_photo_url", "tm_id"]

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Referer": "https://www.transfermarkt.com/",
}
SEARCH = "https://www.transfermarkt.com/schnellsuche/ergebnis/schnellsuche"


def _session():
    """Sesion: cloudscraper si esta instalado (esquiva Cloudflare), si no requests."""
    try:
        import cloudscraper
        return cloudscraper.create_scraper()
    except Exception:
        import requests
        s = requests.Session()
        s.headers.update(HEADERS)
        return s


def _parse_value(text):
    """'EUR3.50m' / 'EUR900k' -> euros."""
    if not text:
        return None
    t = text.replace("\xa0", " ").strip().lower().replace("€", "").replace("eur", "").strip()
    m = re.search(r"([\d.,]+)\s*([mk])?", t)
    if not m:
        return None
    num = m.group(1).replace(",", ".")
    try:
        val = float(num)
    except ValueError:
        return None
    unit = m.group(2)
    if unit == "m":
        return val * 1_000_000
    if unit == "k":
        return val * 1_000
    return val


def fetch_player(sess, name, team=None):
    """Busca al jugador y extrae foto/valor/contrato del primer resultado + su ficha."""
    from bs4 import BeautifulSoup
    query = f"{name} {team}" if team else name
    try:
        r = sess.get(SEARCH, params={"query": query, "Spieler_page": "0"},
                     headers=HEADERS, timeout=12)
        if r.status_code != 200:
            return None
    except Exception as e:
        print(f"   [red] {name}: {e}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    row = soup.select_one("table.items tbody tr")
    if not row and team:
        time.sleep(0.4)
        return fetch_player(sess, name)
    if not row:
        return None

    out = {"name": name, "market_value_eur": "", "contract_until": "", "tm_photo_url": "", "tm_id": ""}

    img = row.select_one("img.bilderrahmen-fixed, td.hauptlink img, img")
    if img:
        raw = img.get("data-src") or img.get("src") or ""
        m = re.search(r"/portrait/(?:small|medium|big|header)/(\d+)", raw)
        if m:
            out["tm_id"] = m.group(1)
            out["tm_photo_url"] = f"https://img.a.transfermarkt.technology/portrait/big/{m.group(1)}.jpg"

    link = row.select_one("td.hauptlink a")
    profile = f"https://www.transfermarkt.com{link['href']}" if link and link.get("href") else None

    if profile:
        try:
            time.sleep(0.4)
            pr = sess.get(profile, headers=HEADERS, timeout=12)
            psoup = BeautifulSoup(pr.text, "html.parser")
            mv = psoup.select_one("a.data-header__market-value-wrapper, .data-header__market-value-wrapper")
            if mv:
                out["market_value_eur"] = _parse_value(mv.get_text(" ", strip=True)) or ""
            for lab in psoup.select("span.info-table__content--regular, th, .info-table__content"):
                if "contract expires" in lab.get_text(strip=True).lower():
                    sib = lab.find_next("span") or lab.find_next("td")
                    if sib:
                        out["contract_until"] = sib.get_text(strip=True)
                    break
        except Exception:
            pass
    return out


def _candidate_names(limit):
    """Plantilla Rayo + top candidatos por rol (para tener sus valores/fotos)."""
    names = []
    cp = club_profile()
    for grp in cp.get("squad_2025_26", {}).values():
        for p in grp:
            names.append((p["name"], "Rayo Vallecano"))
    try:
        from src.profiling.player_profile import rank_players_for_role, ROLE_DEFINITIONS
        enr = pd.read_parquet(ROOT / "data" / "processed" / "player_seasons_enriched.parquet")
        leagues = ["Spain_Primera_Division", "Spain_Segunda_Division", "France_Ligue_1",
                   "Portugal_Primeira_Liga", "Netherlands_Eredivisie"]
        for role in ROLE_DEFINITIONS:
            rk = rank_players_for_role(enr, role, top_n=12, leagues=leagues)
            for r in rk.itertuples():
                names.append((r.name, r.team))
    except Exception as e:
        print("aviso: no se pudieron anadir candidatos:", e)
    seen, uniq = set(), []
    for n, t in names:
        if n not in seen:
            seen.add(n)
            uniq.append((n, t))
    return uniq[:limit]


def _missing_targets(leagues=None, limit=0):
    """
    Jugadores de la temporada actual sin tm_id en market_values.csv.
    Si leagues es None usa ['Spain_Primera_Division', 'Spain_Segunda_Division'].
    """
    import unicodedata, re

    if leagues is None:
        leagues = ["Spain_Primera_Division", "Spain_Segunda_Division"]

    master = ROOT / "data" / "processed" / "master_players.parquet"
    if not master.exists():
        print("[ERR] No se encuentra master_players.parquet")
        return []

    df = pd.read_parquet(master)
    current = df[df["season"].isin(["2026", "2025-2026", "2025/2026"])]
    if leagues != ["ALL"]:
        current = current[current["league"].isin(leagues)]

    def _norm(s):
        return (unicodedata.normalize("NFKD", str(s))
                .encode("ascii", "ignore").decode().lower().strip())

    def _surname(n):
        parts = [p for p in _norm(n).replace(".", " ").split() if len(p) > 1]
        return parts[-1] if parts else _norm(n)

    # Construir índice de los que ya tienen tm_id
    mv = pd.read_csv(MV_CSV) if MV_CSV.exists() else pd.DataFrame()
    has_tid = set()
    if not mv.empty:
        def _get_tid(row):
            tid = str(row.get("tm_id", "") or "").replace(".0", "").strip()
            if tid.isdigit(): return tid
            url = str(row.get("tm_photo_url", "") or "")
            m = re.search(r"/portrait/(?:big|small|medium|header)/(\d+)-", url)
            return m.group(1) if m else None
        mv["_tid"] = mv.apply(_get_tid, axis=1)
        mv["_n"]   = mv["name"].apply(_norm)
        mv["_sn"]  = mv["name"].apply(_surname)
        # índice exacto
        exact_names = set(mv[mv["_tid"].notna()]["_n"])
        # índice apellido único
        sn_counts = mv[mv["_tid"].notna()]["_sn"].value_counts()
        unique_surnames = set(sn_counts[sn_counts == 1].index)
        has_tid = exact_names  # usamos sólo exacto para ser conservadores

    missing = []
    for _, row in current.iterrows():
        name = str(row.get("name", "")).strip()
        team = str(row.get("team", "")).strip()
        n = _norm(name)
        if n not in has_tid:
            missing.append((name, team))

    # Deduplicar por nombre
    seen, uniq = set(), []
    for name, team in missing:
        if name not in seen:
            seen.add(name)
            uniq.append((name, team))

    print(f"[INFO] Jugadores sin tm_id en {leagues}: {len(uniq)}")
    if limit > 0:
        uniq = uniq[:limit]
        print(f"[INFO] Limitado a {limit}")
    return uniq


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rayo",    action="store_true", help="solo plantilla del Rayo")
    ap.add_argument("--missing", action="store_true",
                    help="jugadores sin tm_id de Primera+Segunda Division espanola")
    ap.add_argument("--missing-all", action="store_true",
                    help="jugadores sin tm_id de TODAS las ligas en OPTA")
    ap.add_argument("--limit",   type=int, default=250)
    ap.add_argument("--refresh", action="store_true", help="reintenta tambien los ya guardados")
    args = ap.parse_args()

    existing = {}
    if MV_CSV.exists():
        for _, r in pd.read_csv(MV_CSV).iterrows():
            existing[str(r["name"])] = r.to_dict()

    if args.rayo:
        cp = club_profile()
        targets = [(p["name"], "Rayo Vallecano") for grp in cp.get("squad_2025_26", {}).values() for p in grp]
    elif args.missing:
        targets = _missing_targets(limit=args.limit)
    elif args.missing_all:
        targets = _missing_targets(leagues=["ALL"], limit=args.limit)
    else:
        targets = _candidate_names(args.limit)

    print(f"Buscando datos de {len(targets)} jugadores en Transfermarkt ...")
    sess = _session()
    done = 0
    for i, (name, team) in enumerate(targets, 1):
        prev = existing.get(name, {})
        has_photo = str(prev.get("tm_photo_url") or "").startswith("http")
        if has_photo and not args.refresh:
            continue
        info = fetch_player(sess, name, team)
        if info:
            for k in ("market_value_eur", "contract_until"):
                if not info.get(k) and prev.get(k) not in (None, "", "nan"):
                    info[k] = prev[k]
            existing[name] = {**prev, **{k: v for k, v in info.items() if v not in (None, "")}, "name": name}
            done += 1
            print(f"  [{i}/{len(targets)}] {name}: foto={'si' if info.get('tm_photo_url') else 'no'} "
                  f"valor={info.get('market_value_eur')} contrato={info.get('contract_until')}")
        time.sleep(0.7)

    rows = []
    for name, d in existing.items():
        rows.append({f: d.get(f, "") for f in FIELDS})
    with open(MV_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"\nOK - {done} jugadores actualizados - {len(rows)} filas en {MV_CSV}")
    print("Reinicia el dashboard para ver fotos y valores.")


if __name__ == "__main__":
    main()
