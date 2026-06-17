"""build_player_enriched.py - tabla enriquecida de jugadores-temporada (~130 metricas Opta)."""
from __future__ import annotations
import argparse, io, re, sys, unicodedata, zipfile
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.utils.config import settings  # noqa: E402
from scripts.build_team_seasons import QUICK_LEAGUES, _load_scope_rayo, snake  # noqa: E402

_AGG_RE = re.compile(r"/([^/]+)/(\d{4}-\d{4}|\d{4})/equipos/jugadores_seasonstats\.csv$")

POSITION_GROUP = {
    "goalkeeper": "GK", "portero": "GK",
    "defender": "DEF", "defensa": "DEF",
    "midfielder": "MID", "centrocampista": "MID", "medio": "MID",
    "forward": "FWD", "delantero": "FWD", "attacker": "FWD",
}

P90_SOURCE = [
    "goals", "goal_assists", "total_shots", "shots_on_target_inc_goals",
    "key_passes_attempt_assists", "successful_dribbles", "total_touches_in_opposition_box",
    "tackles_won", "total_tackles", "interceptions", "recoveries", "blocks",
    "total_clearances", "aerial_duels_won", "aerial_duels", "ground_duels_won",
    "successful_crosses_open_play", "successful_passes_opposition_half",
    "successful_long_passes", "forward_passes", "through_balls",
    "total_successful_passes_excl_crosses_corners", "total_losses_of_possession",
]

TEXT_COLS = {
    "name", "team", "league", "season", "position_raw", "position_group",
    "player_id", "player_id_src", "root_folder", "equipo_folder", "liga",
    "temporada", "competition", "source",
}

def _read_minutes(df):
    for c in ("minutes", "time_played"):
        if c in df.columns:
            return pd.to_numeric(df[c], errors="coerce")
    return pd.Series([pd.NA] * len(df))

def _slug(s):
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().replace(" ", "_")

def extract_zip(zip_path, scope):
    frames = []
    with zipfile.ZipFile(zip_path) as zf:
        entries = [n for n in zf.namelist() if n.endswith("equipos/jugadores_seasonstats.csv")]
        for entry in entries:
            m = _AGG_RE.search("/" + entry)
            if not m:
                continue
            league, season = m.group(1), m.group(2)
            if scope is not None and league not in scope:
                continue
            try:
                df = pd.read_csv(io.BytesIO(zf.read(entry)), low_memory=False)
            except Exception:
                continue
            if df.empty:
                continue
            df.columns = [snake(c) for c in df.columns]
            df["league"] = league
            df["season"] = season
            frames.append(df)
    return frames

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", choices=["rayo", "quick", "all"], default="rayo")
    ap.add_argument("--zip", choices=["europa", "norteamerica", "sudamerica"], default=None)
    args = ap.parse_args()

    S = settings()
    zips_dir = Path(S["paths"]["source_zips"])
    out_path = Path(S["paths"]["data_processed"]) / "player_seasons_enriched.parquet"
    scope = {"rayo": _load_scope_rayo(), "quick": QUICK_LEAGUES, "all": None}[args.scope]
    if scope is not None:
        print("[scope=%s] %d ligas" % (args.scope, len(scope)))

    zip_files = sorted(zips_dir.glob("testeo_ligas_*.zip"))
    if args.zip:
        zip_files = [z for z in zip_files if args.zip in z.name]

    frames = []
    for zp in zip_files:
        print("-> %s ..." % zp.name, flush=True)
        fs = extract_zip(zp, scope)
        print("   %d liga-temporadas" % len(fs))
        frames.extend(fs)
    if not frames:
        print("Sin datos.")
        return

    df = pd.concat(frames, ignore_index=True, sort=False)
    rename = {"nombre": "name", "equipo": "team", "posicion": "position_raw",
              "id": "player_id_src", "dorsal": "shirt_number", "time_played": "minutes"}
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    if "position_raw" in df.columns:
        df["position_group"] = df["position_raw"].astype(str).str.lower().map(POSITION_GROUP)
    else:
        df["position_group"] = "?"
    df["player_id"] = df["name"].map(_slug) + "_" + df.get("team", pd.Series([""] * len(df))).map(_slug)
    minutes = _read_minutes(df).replace(0, pd.NA)
    for col in P90_SOURCE:
        if col in df.columns:
            df[col + "_p90"] = pd.to_numeric(df[col], errors="coerce") / minutes * 90
    for c in df.columns:
        if c in TEXT_COLS:
            df[c] = df[c].astype(str)
        elif df[c].dtype == object:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.sort_values(["league", "season", "team", "name"]).reset_index(drop=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, compression=S["output"]["parquet_compression"], index=False)
    print("OK %d jugadores-temporada x %d columnas -> %s" % (len(df), df.shape[1], out_path))
    print("  posiciones:", df["position_group"].value_counts().to_dict())
    print("  ligas: %d - temporadas: %s" % (df["league"].nunique(), sorted(df["season"].unique())))

if __name__ == "__main__":
    main()
