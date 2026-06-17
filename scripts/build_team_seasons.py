"""
build_team_seasons.py
=====================
ETL que lee los ZIP de /Datos, extrae los `jsons/seasonstats.json` de cada
equipo-temporada y construye `data/processed/team_seasons.parquet`.

Cada fila = un (equipo, liga, temporada) con las ~106 métricas de equipo de Opta
(posesión, pases, tiros, recuperaciones, duelos, etc.). Esta tabla es la base
sobre la que `src/profiling/coach_style.py` infiere el ESTILO DE JUEGO de los
entrenadores por código (sin descripciones manuales).

Uso:
    python scripts/build_team_seasons.py                 # scope Rayo (por defecto)
    python scripts/build_team_seasons.py --scope all     # todas las ligas del zip
    python scripts/build_team_seasons.py --scope quick    # 5 grandes + tops
    python scripts/build_team_seasons.py --zip europa    # solo un zip

El parquet existente `master_players.parquet` NO se toca.
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import unicodedata
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils.config import settings  # noqa: E402

# ── Scopes de ligas (alineados con build_master.py) ──────────────────────────
QUICK_LEAGUES = {
    "Spain_Primera_Division", "Spain_Segunda_Division",
    "England_Premier_League", "England_Championship",
    "Germany_Bundesliga", "Germany_2_Bundesliga",
    "Italy_Serie_A", "Italy_Serie_B",
    "France_Ligue_1", "France_Ligue_2",
    "Netherlands_Eredivisie", "Portugal_Primeira_Liga",
    "Belgium_First_Division_A", "Scotland_Premiership",
    "Mexico_Liga_MX", "USA_MLS",
    "Argentina_Liga_Profesional", "Brazil_Serie_A",
    "Chile_Primera_Division", "Colombia_Primera_A",
}


def _load_scope_rayo() -> set:
    """Ligas de origen/destino real del Rayo + las grandes europeas como base."""
    csv_path = ROOT / "config" / "rayo_transfer_history.csv"
    leagues: set[str] = set()
    if csv_path.exists():
        df = pd.read_csv(csv_path, on_bad_lines="skip", engine="python")
        if "zip_league_name" in df.columns:
            leagues = set(df["zip_league_name"].dropna().astype(str).unique())
        leagues.discard("")
        leagues.discard("nan")
    leagues |= {
        "Spain_Primera_Division", "Spain_Segunda_Division",
        "England_Premier_League", "England_Championship",
        "Germany_Bundesliga", "Germany_2_Bundesliga",
        "Italy_Serie_A", "France_Ligue_1", "France_Ligue_2",
        "Netherlands_Eredivisie", "Portugal_Primeira_Liga",
        "Belgium_First_Division_A", "Türkiye_Süper_Lig",
    }
    return leagues


# Patrón de ruta dentro del zip: <root>/<League>/<Season>/equipos/<Team>/jsons/seasonstats.json
_SS_RE = re.compile(r"/([^/]+)/(\d{4}-\d{4}|\d{4})/equipos/([^/]+)/jsons/seasonstats\.json$")
_MATCH_RE = "jsons/matches_equipo.json"


def snake(name: str) -> str:
    """Convierte un nombre de stat Opta a snake_case estable."""
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    s = s.lower()
    s = re.sub(r"[()%/&.+-]", " ", s)
    s = re.sub(r"\s+", "_", s.strip())
    s = re.sub(r"_+", "_", s)
    return s.strip("_")


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _games_from_players(d: dict) -> int | None:
    """Estima partidos del equipo como el máximo de 'Games Played' de su plantilla.

    Lee del propio seasonstats.json (lista `player`), evitando abrir
    matches_equipo.json (mucho más pesado) por cada equipo.
    """
    best = 0
    for p in d.get("player", []) or []:
        for st in p.get("stat", []) or []:
            if st.get("name") in ("Games Played", "Appearances"):
                v = _to_float(st.get("value"))
                if v and v > best:
                    best = v
    return int(best) or None


def extract_zip(zip_path: Path, scope: set | None) -> list[dict]:
    """Extrae una fila por equipo-temporada del zip dado."""
    rows: list[dict] = []
    with zipfile.ZipFile(zip_path) as zf:
        entries = [n for n in zf.namelist() if n.endswith("jsons/seasonstats.json")]
        for entry in entries:
            m = _SS_RE.search("/" + entry)
            if not m:
                continue
            league, season, team_folder = m.group(1), m.group(2), m.group(3)
            if scope is not None and league not in scope:
                continue
            try:
                d = json.loads(zf.read(entry).decode("utf-8", "ignore"))
            except json.JSONDecodeError:
                continue
            cont = d.get("contestant", {}) or {}
            stat_list = cont.get("stat", []) or []
            if not stat_list:
                continue
            row = {
                "team": cont.get("name", team_folder.replace("_", " ")),
                "team_folder": team_folder,
                "league": league,
                "season": season,
                "team_id": cont.get("id"),
                "competition": (d.get("competition", {}) or {}).get("name"),
                "source": "opta_seasonstats",
            }
            for st in stat_list:
                if isinstance(st, dict) and "name" in st:
                    row[snake(st["name"])] = _to_float(st.get("value"))
            row["games_played"] = _games_from_players(d)
            rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", choices=["rayo", "quick", "all"], default="rayo")
    ap.add_argument("--zip", choices=["europa", "norteamerica", "sudamerica"], default=None)
    args = ap.parse_args()

    S = settings()
    zips_dir = Path(S["paths"]["source_zips"])
    out_path = Path(S["paths"]["data_processed"]) / "team_seasons.parquet"

    scope = {"rayo": _load_scope_rayo(), "quick": QUICK_LEAGUES, "all": None}[args.scope]
    if scope is not None:
        print(f"[scope={args.scope}] {len(scope)} ligas")

    zip_files = sorted(zips_dir.glob("testeo_ligas_*.zip"))
    if args.zip:
        zip_files = [z for z in zip_files if args.zip in z.name]

    all_rows: list[dict] = []
    for zp in zip_files:
        print(f"→ {zp.name} …", flush=True)
        rows = extract_zip(zp, scope)
        print(f"   {len(rows)} equipos-temporada")
        all_rows.extend(rows)

    if not all_rows:
        print("Sin datos. Revisa el scope o las rutas.")
        return

    df = pd.DataFrame(all_rows)
    # Rellenar stats de evento-cero ausentes con 0 (penaltis fallados, etc.)
    num_cols = df.select_dtypes("number").columns
    df[num_cols] = df[num_cols].fillna(0)
    df = df.sort_values(["league", "season", "team"]).reset_index(drop=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, compression=S["output"]["parquet_compression"], index=False)
    print(f"\n✓ {len(df)} filas · {df.shape[1]} columnas → {out_path}")
    print(f"  ligas: {df['league'].nunique()} · temporadas: {sorted(df['season'].unique())}")


if __name__ == "__main__":
    main()
