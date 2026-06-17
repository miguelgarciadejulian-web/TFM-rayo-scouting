"""
build_master.py
===============
ETL que lee los ZIPs de /Datos, extrae *_jugadores_seasonstats.csv,
los normaliza al esquema canónico y genera data/processed/master_players.parquet.

Uso:
    python scripts/build_master.py              # todos los zips, todas las ligas
    python scripts/build_master.py --quick      # ligas top (rápido, para pruebas)
    python scripts/build_master.py --zip europa # solo el zip de europa
"""
from __future__ import annotations
import argparse, sys, zipfile
from io import BytesIO
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.canonical_schema import COLUMN_ALIASES, CANONICAL_COLUMNS, P90_METRICS
from src.utils.config import settings

# ── Modos de filtrado ─────────────────────────────────────────────────────────
# --quick      : 5 grandes ligas europeas + sus 2as divisiones + ligas top de otras regiones
# --scope_rayo : ligas históricas del Rayo (origen/destino real de sus jugadores 2021-26)
# sin flag     : todas las ligas del zip

QUICK_LEAGUES = {
    # Las 5 grandes + 2as divisiones
    "Spain_Primera_Division",
    "Spain_Segunda_Division",
    "England_Premier_League",
    "England_Championship",
    "Germany_Bundesliga",
    "Germany_2_Bundesliga",
    "Italy_Serie_A",
    "Italy_Serie_B",
    "France_Ligue_1",
    "France_Ligue_2",
    # Otras ligas top europeas
    "Netherlands_Eredivisie",
    "Portugal_Primeira_Liga",
    "Belgium_First_Division_A",
    "Türkiye_Süper_Lig",
    "Scotland_Premiership",
    # Norteamérica
    "Mexico_Liga_MX",
    "USA_MLS",
    # Sudamérica
    "Argentina_Liga_Profesional",
    "Brazil_Serie_A",
    "Chile_Primera_Division",
    "Colombia_Primera_A",
}

# Scope real del Rayo: ligas de origen/destino de sus transferencias 2021-2026
# Cargado dinámicamente desde config/rayo_transfer_history.csv
def _load_scope_rayo() -> set:
    csv_path = ROOT / "config" / "rayo_transfer_history.csv"
    if not csv_path.exists():
        return QUICK_LEAGUES
    df = pd.read_csv(csv_path)
    leagues = set(df["zip_league_name"].dropna().unique())
    leagues.discard("")
    # Añadir siempre las 5 grandes como base mínima
    leagues |= {
        "Spain_Primera_Division", "Spain_Segunda_Division",
        "England_Premier_League", "Germany_Bundesliga",
        "Italy_Serie_A", "France_Ligue_1",
        "Netherlands_Eredivisie", "Portugal_Primeira_Liga",
    }
    return leagues

SCOPE_RAYO_LEAGUES = _load_scope_rayo()

POSITION_MAP = {
    "goalkeeper": "GK", "portero": "GK",
    "defender": "CB",   "defensa": "CB",
    "midfielder": "CM", "centrocampista": "CM", "medio": "CM",
    "forward": "ST",    "delantero": "ST", "attacker": "ST",
}

def normalize_position(pos):
    if pd.isna(pos): return "?"
    return POSITION_MAP.get(str(pos).lower().strip(), str(pos))

def read_csv(zf, entry):
    try:
        raw = zf.open(entry).read()
        try:    return pd.read_csv(BytesIO(raw), low_memory=False)
        except: return pd.read_csv(BytesIO(raw), encoding="latin-1", low_memory=False)
    except Exception as e:
        print(f"  [WARN] {entry}: {e}")
        return None

def normalize(df, source):
    alias = {k.strip(): v for k, v in COLUMN_ALIASES.items()}

    # Renombrar columnas evitando colisiones: si dos columnas mapean al mismo
    # nombre canónico, la segunda se descarta antes del rename.
    rename = {}
    targets_seen = set()
    for c in df.columns:
        target = alias.get(c.strip())
        if target and target not in targets_seen:
            rename[c] = target
            targets_seen.add(target)

    df = df.rename(columns=rename)

    # Eliminar columnas duplicadas que pudieran quedar (por seguridad)
    df = df.loc[:, ~df.columns.duplicated()]

    if "position_primary" in df.columns:
        df["position_primary"] = df["position_primary"].apply(normalize_position)

    if "minutes" in df.columns:
        mins = pd.to_numeric(df["minutes"], errors="coerce").replace(0, pd.NA)
        for m in P90_METRICS:
            if m in df.columns:
                df[f"{m}_p90"] = pd.to_numeric(df[m], errors="coerce") / mins * 90

    if "passes_completed" in df.columns and "passes_attempted" in df.columns:
        df["passes_completed_pct"] = (
            pd.to_numeric(df["passes_completed"], errors="coerce") /
            pd.to_numeric(df["passes_attempted"], errors="coerce").replace(0, pd.NA) * 100
        )

    df["source"] = source
    if not all(c in df.columns for c in ["name", "team", "league", "season"]):
        return pd.DataFrame()

    extra = {"aerial_duels_won_pct", "duels_won_pct", "passes_completed_pct",
             "yellow_cards", "red_cards"}
    keep = set(CANONICAL_COLUMNS) | extra
    return df[[c for c in df.columns if c in keep or c.endswith("_p90")]]

def process_zip(zip_path, mode="all"):
    """
    mode: 'all' | 'quick' | 'scope_rayo'
    """
    frames = []
    print(f"\n📦 {zip_path.name}  [modo: {mode}]")
    league_filter = None
    if mode == "quick":
        league_filter = QUICK_LEAGUES
    elif mode == "scope_rayo":
        league_filter = SCOPE_RAYO_LEAGUES

    with zipfile.ZipFile(zip_path) as zf:
        entries = [e for e in zf.namelist()
                   if e.endswith("_jugadores_seasonstats.csv")
                   and ".ipynb_checkpoints" not in e]
        if league_filter:
            entries = [e for e in entries if any(lg in e for lg in league_filter)]
        print(f"  → {len(entries)} ficheros")
        for i, entry in enumerate(entries):
            df = read_csv(zf, entry)
            if df is None or df.empty: continue
            ndf = normalize(df, f"{zip_path.stem}/{entry}")
            if not ndf.empty: frames.append(ndf)
            if (i+1) % 500 == 0:
                print(f"  … {i+1}/{len(entries)} ({len(frames)} con datos)")
    if not frames: return pd.DataFrame()
    result = pd.concat(frames, ignore_index=True)
    print(f"  ✓ {len(result):,} filas")
    return result

def main():
    p = argparse.ArgumentParser(description="ETL Rayo Scouting Tool")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--quick",       action="store_true",
                   help="5 grandes ligas + 2as divisiones + tops de otras regiones (~rápido)")
    g.add_argument("--scope_rayo",  action="store_true",
                   help="Ligas históricas del Rayo 2021-26 + las 5 grandes (~medio)")
    p.add_argument("--zip", default=None,
                   help="Procesar solo un zip: 'europa', 'norteamerica' o 'sudamerica'")
    args = p.parse_args()

    if args.quick:
        mode = "quick"
    elif args.scope_rayo:
        mode = "scope_rayo"
        print(f"🔭 scope_rayo: {sorted(SCOPE_RAYO_LEAGUES)}")
    else:
        mode = "all"

    s   = settings()
    src = Path(s["paths"]["source_zips"])
    out = Path(s["paths"]["data_processed"])
    out.mkdir(parents=True, exist_ok=True)

    zips = sorted(src.glob("testeo_ligas_*.zip"))
    if args.zip:
        zips = [z for z in zips if args.zip.lower() in z.name]
    if not zips:
        print(f"[ERROR] No hay ZIPs en {src}"); sys.exit(1)

    frames = [df for zp in zips if not (df := process_zip(zp, mode)).empty]
    if not frames:
        print("[ERROR] Sin datos"); sys.exit(1)

    master = pd.concat(frames, ignore_index=True)

    # Homogeneizar tipos mixtos antes de serializar a parquet
    for col in master.select_dtypes(include="object").columns:
        master[col] = master[col].astype(str).replace("nan", pd.NA)

    # Año de FIN de temporada (para comparar correctamente entre formatos)
    # "2025-2026" → 2026 | "2025-26" → 2026 | "2026" → 2026 | "2025" → 2025
    def _season_year(s):
        try:
            parts = str(s).replace("/", "-").split("-")
            if len(parts) >= 2:
                last = parts[-1]
                if len(last) == 4:
                    return int(last)          # "2025-2026" → 2026
                elif len(last) == 2:
                    return int(parts[0][:2] + last)  # "2025-26" → 2026
            return int(parts[0])              # "2026" → 2026
        except Exception:
            return 0

    master["_season_year"] = master["season"].apply(_season_year)

    # Conservar solo la temporada más reciente de cada jugador
    # (evita el problema de "2026" vs "2025-2026" en el filtro del dashboard)
    if "player_id" in master.columns:
        master = (master
                  .sort_values("_season_year", ascending=False)
                  .drop_duplicates(subset=["player_id"], keep="first"))

    master = master.drop(columns=["_season_year"])

    out_file = out / "master_players.parquet"
    master.to_parquet(out_file, compression="snappy", index=False)

    print(f"\n✅ {out_file}")
    print(f"   {len(master):,} jugadores × {master.shape[1]} columnas")
    if "league" in master.columns: print(f"   {master['league'].nunique()} ligas")
    if "season" in master.columns: print(f"   Temporadas: {sorted(master['season'].unique())}")

if __name__ == "__main__":
    main()
