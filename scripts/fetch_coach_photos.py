"""
fetch_coach_photos.py
=====================
Rellena config/coach_photos.csv con la FOTO de cada entrenador. Fuentes (en orden):
  1) Wikipedia (es y en): resuelve el artículo por búsqueda y coge la imagen
     principal del infobox (original o miniatura grande).
  2) Wikidata (propiedad P18 = imagen): respaldo que cubre a casi todos.

EJECUTAR EN TU ORDENADOR (necesita internet).

Uso:
    python scripts/fetch_coach_photos.py
    python scripts/fetch_coach_photos.py --refresh     # rehace los que ya tienen foto
    python scripts/fetch_coach_photos.py --download     # además descarga el .jpg a assets/coaches/
"""
from __future__ import annotations
import argparse
import csv
import json
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
META = ROOT / "config" / "coach_meta.csv"
OUT = ROOT / "config" / "coach_photos.csv"
ASSETS = ROOT / "dashboard" / "assets" / "coaches"
UA = {"User-Agent": "RayoScoutingTool/1.0 (TFM academic project)"}
FOOTBALL = ("entrenador", "futbol", "fútbol", "football", "soccer", "coach", "manager",
            "futbolista", "técnico")


def _slug(s):
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().replace(" ", "_")


def _get(url, retries=2):
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except Exception as e:  # reintento ante throttling/errores puntuales
            last = e
            time.sleep(1.0 + attempt)
    raise last


# ── Wikipedia (una sola consulta por idioma: busca, resuelve redirecciones y
#    devuelve la imagen del infobox en la misma llamada) ───────────────────────
def wiki_image(name):
    for lang in ("es", "en"):
        url = (f"https://{lang}.wikipedia.org/w/api.php?action=query&format=json"
               f"&generator=search&gsrsearch={urllib.parse.quote(name)}&gsrnamespace=0&gsrlimit=3"
               f"&prop=pageimages&piprop=original|thumbnail&pithumbsize=600&redirects=1")
        try:
            d = _get(url)
        except Exception:
            continue
        pages = list((d.get("query", {}) or {}).get("pages", {}).values())
        # ordenar por el ranking de búsqueda y coger la primera con imagen
        pages.sort(key=lambda pg: pg.get("index", 99))
        for pg in pages:
            src = (pg.get("original", {}) or {}).get("source") or (pg.get("thumbnail", {}) or {}).get("source")
            if src:
                return src
    return None


# ── Wikidata (P18) ───────────────────────────────────────────────────────────
def wikidata_image(name):
    try:
        s = _get("https://www.wikidata.org/w/api.php?action=wbsearchentities"
                 f"&search={urllib.parse.quote(name)}&language=es&uselang=es&type=item&limit=6&format=json")
    except Exception:
        return None
    cands = s.get("search", [])
    # priorizar entidades cuya descripción suene a fútbol
    cands.sort(key=lambda c: 0 if any(f in (c.get("description", "") or "").lower() for f in FOOTBALL) else 1)
    for c in cands[:6]:
        try:
            cl = _get("https://www.wikidata.org/w/api.php?action=wbgetclaims"
                      f"&entity={c['id']}&property=P18&format=json")
            claims = cl.get("claims", {}).get("P18", [])
            if claims:
                fname = claims[0]["mainsnak"]["datavalue"]["value"]
                return ("https://commons.wikimedia.org/wiki/Special:FilePath/"
                        + urllib.parse.quote(fname.replace(" ", "_")) + "?width=600")
        except Exception:
            continue
    return None


def find_image(name):
    return wiki_image(name) or wikidata_image(name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--download", action="store_true")
    args = ap.parse_args()

    existing = {}
    if OUT.exists():
        for r in csv.DictReader(open(OUT, encoding="utf-8")):
            existing[r["entrenador"]] = r
    coaches = [r["coach"] for r in csv.DictReader(open(META, encoding="utf-8"))]
    if args.download:
        ASSETS.mkdir(parents=True, exist_ok=True)

    ok = 0
    for i, name in enumerate(coaches, 1):
        prev = existing.get(name, {})
        if str(prev.get("imagen", "")).startswith("http") and not args.refresh:
            continue
        img = find_image(name)
        local = ""
        if img and args.download:
            try:
                dest = ASSETS / f"{_slug(name)}.jpg"
                req = urllib.request.Request(img, headers=UA)
                with urllib.request.urlopen(req, timeout=25) as r, open(dest, "wb") as f:
                    f.write(r.read())
                local = f"/assets/coaches/{dest.name}"
            except Exception:
                local = ""
        existing[name] = {"entrenador": name, "tm_id": prev.get("tm_id", ""),
                          "imagen": img or "", "imagen_local": local or prev.get("imagen_local", "")}
        print(f"  [{i}/{len(coaches)}] {name}: {'OK' if img else 'sin imagen'}" + (" (descargada)" if local else ""))
        if img:
            ok += 1
        time.sleep(0.5)

    fields = ["entrenador", "tm_id", "imagen", "imagen_local"]
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for d in existing.values():
            w.writerow({k: d.get(k, "") for k in fields})
    print(f"\nOK · {ok}/{len(coaches)} con foto · {OUT}")
    print("Reinicia el dashboard para verlas.")


if __name__ == "__main__":
    main()
