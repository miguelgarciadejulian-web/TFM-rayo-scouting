"""
fetch_player_photos.py
======================
Genera config/player_photos_db.csv con (id_jugador, jugador, imagen, equipo,
opta_name) usando Transfermarkt, y mete las fotos en config/market_values.csv
para que el dashboard las muestre.

Flujo (idea de Miguel):
  1. Para cada equipo del scope, se busca su club en Transfermarkt y se scrapea
     la tabla de plantilla -> (nombre, id de Transfermarkt) de cada jugador.
  2. Con cada id se llama a la API
     https://tmapi-alpha.transfermarkt.technology/player/{id}  (devuelve JSON con
     la URL de la foto 'portrait/big/...').  Esta API es un subdominio y no tiene
     el Cloudflare de la web, asi que responde a peticiones normales.
  3. Se escribe el CSV id/jugador/imagen y se casa con nuestros nombres Opta
     POR APELLIDO dentro del mismo equipo (Opta abrevia: 'F. Lejeune').

EJECUTAR EN TU ORDENADOR (necesita internet). Recomendado:  pip install cloudscraper

Uso:
    python scripts/fetch_player_photos.py                       # LaLiga + Segunda + Rayo
    python scripts/fetch_player_photos.py --leagues Spain_Primera_Division
    python scripts/fetch_player_photos.py --all                 # todos los del scope
    python scripts/fetch_player_photos.py --refresh             # reintenta equipos ya hechos
"""
from __future__ import annotations
import argparse
import csv
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

DB_CSV = ROOT / "config" / "player_photos_db.csv"
MV_CSV = ROOT / "config" / "market_values.csv"
ENRICHED = ROOT / "data" / "processed" / "player_seasons_enriched.parquet"

API_PLAYER = "https://tmapi-alpha.transfermarkt.technology/player/{id}"
WWW = "https://www.transfermarkt.com"
SEARCH = WWW + "/schnellsuche/ergebnis/schnellsuche"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Referer": WWW + "/",
}
API_HEADERS = {"Accept": "application/json", "User-Agent": HEADERS["User-Agent"]}

CURRENT_SEASONS = ["2025-2026", "2025", "2024-2025"]
DEFAULT_LEAGUES = ["Spain_Primera_Division", "Spain_Segunda_Division"]


def _norm(s) -> str:
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().strip()


def _surname(name) -> str:
    n = _norm(name).replace(".", " ")
    parts = [p for p in n.split() if len(p) > 1]
    return parts[-1] if parts else n


def _session():
    try:
        import cloudscraper
        return cloudscraper.create_scraper()
    except Exception:
        import requests
        s = requests.Session()
        s.headers.update(HEADERS)
        return s


_TEAM_IDS_CSV = ROOT / "config" / "team_tm_ids.csv"
_TEAM_OVERRIDES = None


def _team_override(team_name):
    """Lee config/team_tm_ids.csv (team, tm_club_id) si existe."""
    global _TEAM_OVERRIDES
    if _TEAM_OVERRIDES is None:
        _TEAM_OVERRIDES = {}
        if _TEAM_IDS_CSV.exists():
            try:
                for r in csv.DictReader(open(_TEAM_IDS_CSV, encoding="utf-8")):
                    cid = str(r.get("tm_club_id", "")).strip()
                    if cid:
                        _TEAM_OVERRIDES[_norm(r.get("team"))] = cid
            except Exception:
                pass
    return _TEAM_OVERRIDES.get(_norm(team_name))


def _clean_team(name):
    """Limpia el nombre para buscar en Transfermarkt (quita años/fundación)."""
    n = re.sub(r"\b\d{2,4}\b", " ", str(name))   # 1893, 09, 1899...
    n = re.sub(r"\s+", " ", n).strip()
    return n


def find_club_id(sess, team_name: str) -> str | None:
    """Resuelve el id de club de Transfermarkt (override manual -> búsqueda limpia)."""
    # 1) override manual
    tid = _team_override(team_name)
    if tid:
        return tid
    # 2) búsqueda con varias versiones del nombre (limpia primero)
    cleaned = _clean_team(team_name)
    short = re.sub(r"^(FC|VfB|VfL|SV|SC|TSG|BV|BVB|RB|1\.|SpVgg|SD|CD|CA|UD|RC|AC|AS|SS|FK|NK)\s+",
                   "", cleaned, flags=re.IGNORECASE).strip()
    queries = []
    for q in (cleaned, team_name, short):
        if q and q not in queries:
            queries.append(q)
    for q in queries:
        try:
            r = sess.get(SEARCH, params={"query": q}, headers=HEADERS, timeout=12)
            if r.status_code == 200:
                m = re.search(r"/verein/(\d+)", r.text)
                if m:
                    return m.group(1)
        except Exception:
            continue
        time.sleep(0.2)
    return None


def scrape_squad(sess, club_id: str) -> list[tuple[str, str]]:
    """Devuelve [(nombre, tm_player_id)] de la plantilla del club."""
    from bs4 import BeautifulSoup
    url = f"{WWW}/x/kader/verein/{club_id}/plus/1"
    try:
        r = sess.get(url, headers=HEADERS, timeout=12)
        if r.status_code != 200:
            return []
    except Exception:
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    out, seen = [], set()
    for a in soup.select("a[href*='/profil/spieler/']"):
        m = re.search(r"/profil/spieler/(\d+)", a.get("href", ""))
        if not m:
            continue
        pid = m.group(1)
        name = a.get_text(strip=True) or a.get("title", "")
        if pid and name and pid not in seen:
            seen.add(pid)
            out.append((name, pid))
    return out


def _find_image_in_json(obj):
    """Busca recursivamente una URL de retrato en el JSON de la API."""
    if isinstance(obj, str):
        if "img.a.transfermarkt.technology/portrait" in obj:
            return obj.replace("\\/", "/")
        return None
    if isinstance(obj, dict):
        for v in obj.values():
            r = _find_image_in_json(v)
            if r:
                return r
    if isinstance(obj, list):
        for v in obj:
            r = _find_image_in_json(v)
            if r:
                return r
    return None


def _num(v):
    """Convierte número o texto numérico a float (None si no se puede)."""
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        t = v.strip()
        if re.fullmatch(r"[\d.,]+", t):
            try:
                return float(t.replace(".", "").replace(",", ".")) if ("," in t and "." in t) else float(t.replace(",", "."))
            except ValueError:
                return None
        return _parse_money(t)
    return None


def _find_market_value(obj):
    """Busca recursivamente el valor de mercado (en euros) en el JSON de la API."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            if "marketvalue" in kl or "market_value" in kl or kl in ("value", "amount", "marktwert"):
                n = _num(v)
                if n and n > 1000:
                    return n
                if isinstance(v, dict):
                    for vk in ("value", "amount", "raw", "eur", "marketValue"):
                        n = _num(v.get(vk))
                        if n and n > 1000:
                            return n
        for v in obj.values():
            r = _find_market_value(v)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _find_market_value(v)
            if r:
                return r
    return None


def _as_date(v):
    """Devuelve una fecha YYYY-MM-DD desde string ISO o epoch (s/ms)."""
    if isinstance(v, str) and re.search(r"\d{4}-\d{2}", v):
        return v[:10]
    if isinstance(v, (int, float)) and v > 10 ** 8:
        import datetime
        ts = v / 1000 if v > 10 ** 11 else v
        try:
            return datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
        except Exception:
            return None
    return None


_CONTRACT_KEYS = ("contractexpirydate", "contractuntil", "contractexpiry", "contractend",
                  "expires", "expiresat", "expirydate", "until", "vertragsende", "contractexpiration")


def _find_contract(obj):
    """Busca recursivamente la fecha de fin de contrato (clave o anidada)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower().replace("_", "")
            if kl in _CONTRACT_KEYS or ("contract" in kl and any(t in kl for t in ("expir", "until", "end", "date"))):
                d = _as_date(v)
                if d:
                    return d
                if isinstance(v, dict):  # p.ej. contract: {expires: ...}
                    for vk in ("expires", "until", "date", "expiryDate", "end"):
                        d = _as_date(v.get(vk))
                        if d:
                            return d
        for v in obj.values():
            r = _find_contract(v)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _find_contract(v)
            if r:
                return r
    return None


def _parse_money(text):
    if not text:
        return None
    t = str(text).lower().replace("\xa0", " ").replace("€", "").replace("eur", "").strip()
    m = re.search(r"([\d.,]+)\s*([mk])?", t)
    if not m:
        return None
    try:
        val = float(m.group(1).replace(",", "."))
    except ValueError:
        return None
    u = m.group(2)
    return val * 1_000_000 if u == "m" else (val * 1_000 if u == "k" else val)


def fetch_player_api(api_sess, tm_id: str) -> dict:
    """Devuelve foto + valor + contrato + bio del jugador desde tmapi-alpha.

    Estructura real (jun-2026):
      data.portraitUrl                         -> foto
      data.marketValueDetails.current.value    -> valor (EUR)
      data.attributes.contractUntil            -> fin de contrato
      data.lifeDates.age / dateOfBirth         -> edad / nacimiento
      data.attributes.preferredFoot.name       -> pie
      data.attributes.height                   -> altura
      data.attributes.position.name            -> posición
    """
    out = {"image": f"https://img.a.transfermarkt.technology/portrait/big/{tm_id}.jpg",
           "value": "", "contract": "", "age": "", "dob": "", "foot": "", "height": "",
           "position": "", "shirt": ""}
    try:
        r = api_sess.get(API_PLAYER.format(id=tm_id), headers=API_HEADERS, timeout=12)
        if r.status_code != 200:
            return out
        j = r.json()
        d = j.get("data", j) if isinstance(j, dict) else j
        attrs = d.get("attributes", {}) or {}
        life = d.get("lifeDates", {}) or {}
        mvc = (d.get("marketValueDetails", {}) or {}).get("current", {}) or {}

        out["image"] = d.get("portraitUrl") or _find_image_in_json(d) or out["image"]
        if isinstance(out["image"], str):
            out["image"] = out["image"].replace("\\/", "/")
        out["value"] = mvc.get("value") or _find_market_value(d) or ""
        out["contract"] = attrs.get("contractUntil") or _find_contract(d) or ""
        out["age"] = life.get("age", "") or ""
        out["dob"] = life.get("dateOfBirth", "") or ""
        out["foot"] = (attrs.get("preferredFoot", {}) or {}).get("name", "") or ""
        out["height"] = attrs.get("height", "") or ""
        out["position"] = ((attrs.get("position", {}) or {}).get("name", "")
                           or attrs.get("positionGroupName", "")) or ""
        cas = d.get("clubAssignments", [])
        if cas and isinstance(cas, list):
            out["shirt"] = cas[0].get("shirtNumber", "") or ""
    except Exception:
        pass
    return out


def scope_teams(leagues) -> list[tuple[str, str]]:
    df = pd.read_parquet(ENRICHED, columns=["team", "league", "season"])
    df = df[df["season"].isin(CURRENT_SEASONS)]
    if leagues:
        df = df[df["league"].isin(leagues)]
    teams = df[["team", "league"]].drop_duplicates().values.tolist()
    # Rayo siempre
    if not any("Rayo" in t for t, _ in teams):
        teams.append(["Rayo Vallecano de Madrid", "Spain_Primera_Division"])
    return [(t, l) for t, l in teams]


def opta_names_for_team(team: str) -> list[str]:
    df = pd.read_parquet(ENRICHED, columns=["name", "team", "season"])
    df = df[(df["team"] == team) & (df["season"].isin(CURRENT_SEASONS))]
    return sorted(df["name"].dropna().unique().tolist())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--leagues", nargs="*", default=None)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    leagues = None if args.all else (args.leagues or DEFAULT_LEAGUES)
    teams = scope_teams(leagues)
    print(f"Equipos a procesar: {len(teams)}")

    # cargar DB existente
    db = {}
    if DB_CSV.exists():
        for _, r in pd.read_csv(DB_CSV).iterrows():
            db[str(r["id_jugador"])] = r.to_dict()
    done_teams = {str(r.get("equipo")) for r in db.values()} if not args.refresh else set()

    web = _session()
    try:
        import requests
        api = requests.Session()
    except Exception:
        api = web

    unresolved = []
    for i, (team, league) in enumerate(teams, 1):
        if team in done_teams and not args.refresh:
            continue
        print(f"[{i}/{len(teams)}] {team} ...", flush=True)
        club_id = find_club_id(web, team)
        if not club_id:
            print("   club no encontrado -> apuntado para completar a mano")
            unresolved.append((team, league))
            continue
        squad = scrape_squad(web, club_id)
        if not squad:
            print("   plantilla vacia")
            continue
        opta = opta_names_for_team(team)
        opta_by_surname = {}
        for o in opta:
            opta_by_surname.setdefault(_surname(o), o)

        for tm_name, tm_id in squad:
            opta_match = opta_by_surname.get(_surname(tm_name), "")
            info = fetch_player_api(api, tm_id)
            db[tm_id] = {"id_jugador": tm_id, "jugador": tm_name, "imagen": info["image"],
                         "valor_eur": info["value"], "contrato": info["contract"],
                         "edad": info.get("age", ""), "nacimiento": info.get("dob", ""),
                         "pie": info.get("foot", ""), "altura": info.get("height", ""),
                         "posicion": info.get("position", ""), "dorsal": info.get("shirt", ""),
                         "equipo": team, "opta_name": opta_match}
            time.sleep(0.25)
        print(f"   {len(squad)} jugadores · {sum(1 for n,_ in squad if _surname(n) in opta_by_surname)} casados con Opta")
        time.sleep(0.5)

        # guardado incremental
        _write_db(db)

    _merge_into_market_values(db)
    if unresolved:
        _append_unresolved(unresolved)
        print(f"\n{len(unresolved)} equipos NO resueltos -> escritos en {_TEAM_IDS_CSV}")
        print("Abre ese CSV, rellena su 'tm_club_id' (lo ves en la URL de TM: /verein/ID) y reejecuta.")
    print(f"\nOK · {len(db)} jugadores en {DB_CSV}")
    print("Fotos/valores volcados a market_values.csv. Reinicia el dashboard.")


def _append_unresolved(unresolved):
    """Añade los equipos no resueltos a team_tm_ids.csv con id en blanco (para completar)."""
    existing = {}
    if _TEAM_IDS_CSV.exists():
        for r in csv.DictReader(open(_TEAM_IDS_CSV, encoding="utf-8")):
            existing[r.get("team", "")] = r.get("tm_club_id", "")
    for team, _lg in unresolved:
        existing.setdefault(team, "")
    with open(_TEAM_IDS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["team", "tm_club_id"])
        w.writeheader()
        for team, cid in sorted(existing.items()):
            w.writerow({"team": team, "tm_club_id": cid})


def _write_db(db):
    fields = ["id_jugador", "jugador", "imagen", "valor_eur", "contrato", "edad", "nacimiento",
              "pie", "altura", "posicion", "dorsal", "equipo", "opta_name"]
    with open(DB_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for d in db.values():
            w.writerow({k: d.get(k, "") for k in fields})


def _merge_into_market_values(db):
    """Vuelca las fotos en market_values.csv usando el nombre Opta casado."""
    fields = ["name", "market_value_eur", "contract_until", "tm_photo_url", "tm_id",
              "age", "foot", "height", "position", "dob"]
    rows = {}
    if MV_CSV.exists():
        for _, r in pd.read_csv(MV_CSV).iterrows():
            rows[str(r["name"])] = {k: r.get(k, "") for k in fields}
    for d in db.values():
        opta = d.get("opta_name") or d.get("jugador")
        if not opta:
            continue
        cur = rows.get(opta, {k: "" for k in fields})
        cur["name"] = opta
        cur["tm_photo_url"] = d.get("imagen", "")
        cur["tm_id"] = d.get("id_jugador", "")
        for src, dst in [("valor_eur", "market_value_eur"), ("contrato", "contract_until"),
                         ("edad", "age"), ("pie", "foot"), ("altura", "height"),
                         ("posicion", "position"), ("nacimiento", "dob")]:
            if d.get(src) not in (None, "", "nan"):
                cur[dst] = d.get(src)
        rows[opta] = cur
    with open(MV_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows.values():
            w.writerow({k: r.get(k, "") for k in fields})


if __name__ == "__main__":
    main()
