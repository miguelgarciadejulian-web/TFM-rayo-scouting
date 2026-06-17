"""
build_economic_dataset.py
=========================
Construye data/processed/player_economic.parquet, el dataset económico/contractual
separado del dataset deportivo (OPTA).

FUENTES (por orden de prioridad de cada campo):
  1. club_profile.yaml        — Plantilla Rayo: fuente de verdad absoluta.
  2. player_overrides.json    — Correcciones manuales del analista.
  3. config/market_values.csv — Datos obtenidos por scraping de Transfermarkt.
  4. player_entity_map.csv    — Para resolver la relación opta_id ↔ tm_id.

ESQUEMA DE SALIDA (player_economic.parquet):
  opta_id, canonical_name, display_name, market_value_eur, contract_until,
  release_clause_eur, salary_eur_year, club, nationality, age, position_tm,
  dob, tm_id, photo_url, data_source, last_updated, match_confidence

Uso:
    python scripts/build_economic_dataset.py
    python scripts/build_economic_dataset.py --no-entity-map   # sin usar entity_map (solo CSV)
"""
from __future__ import annotations
import argparse
import json
import sys
import unicodedata
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils.config import settings, club_profile  # noqa: E402

S        = settings()
PROC     = Path(S["paths"]["data_processed"])
MV_CSV   = ROOT / "config" / "market_values.csv"
OVERRIDES_JSON = PROC / "player_overrides.json"
ENTITY_MAP     = PROC / "player_entity_map.csv"
OUT_PARQUET    = PROC / "player_economic.parquet"

TODAY = str(date.today())


# ── Utilidades ────────────────────────────────────────────────────────────────

def norm(s) -> str:
    if pd.isna(s) or s is None:
        return ""
    t = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return t.lower().strip().replace(".", "").replace("  ", " ")


def _float(v):
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def _str(v) -> str | None:
    s = str(v).strip() if v is not None and not (isinstance(v, float) and pd.isna(v)) else None
    return s if s and s not in ("nan", "None", "") else None


# ── Carga de fuentes ──────────────────────────────────────────────────────────

def load_entity_map() -> pd.DataFrame:
    if not ENTITY_MAP.exists():
        print(f"[WARN] {ENTITY_MAP} no existe. Ejecuta scripts/build_entity_map.py primero.")
        return pd.DataFrame(columns=["opta_id", "tm_id", "canonical_name", "match_confidence"])
    df = pd.read_csv(ENTITY_MAP, dtype=str).fillna("")
    return df


def load_market_values() -> dict[str, dict]:
    """Devuelve {nombre_normalizado: row_dict} de market_values.csv."""
    if not MV_CSV.exists():
        return {}
    df = pd.read_csv(MV_CSV)
    out = {}
    for _, r in df.iterrows():
        key = norm(r.get("name", ""))
        if not key:
            continue
        tm_id = None
        if pd.notna(r.get("tm_id")) and str(r.get("tm_id")).replace(".0", "").isdigit():
            tm_id = str(int(float(r["tm_id"])))
        out[key] = {
            "display_name":      _str(r.get("name")),
            "market_value_eur":  _float(r.get("market_value_eur")),
            "contract_until":    _str(r.get("contract_until")),
            "age":               _float(r.get("age")),
            "dob":               _str(r.get("dob")),
            "position_tm":       _str(r.get("position")),
            "photo_url":         _str(r.get("tm_photo_url")),
            "tm_id":             tm_id,
            "data_source":       "transfermarkt",
            "last_updated":      TODAY,
        }
    return out


def load_overrides() -> dict[str, dict]:
    """Devuelve {nombre_normalizado: override_dict} de player_overrides.json."""
    if not OVERRIDES_JSON.exists():
        return {}
    try:
        return json.load(open(OVERRIDES_JSON, encoding="utf-8"))
    except Exception:
        return {}


def load_club_profile_players() -> list[dict]:
    """Carga los jugadores de la plantilla Rayo desde club_profile.yaml."""
    cp = club_profile()
    squad = cp.get("squad_2025_26", {})
    rows = []
    for _group, players in squad.items():
        for p in players:
            rows.append({
                "display_name":      p.get("name"),
                "canonical_name":    norm(p.get("name", "")),
                "club":              "Rayo Vallecano",
                "nationality":       _str(p.get("nationality")),
                "age":               p.get("age"),
                "position_tm":       p.get("position"),
                "contract_until":    _str(p.get("contract_end")),
                "market_value_eur":  _float(p.get("market_value")),
                "data_source":       "club_profile",
                "last_updated":      TODAY,
                "match_confidence":  "1.00",
            })
    return rows


# ── Construcción del dataset ──────────────────────────────────────────────────

def build(use_entity_map: bool = True) -> pd.DataFrame:
    print("\n📦 Construyendo player_economic.parquet...")

    mv_data    = load_market_values()
    overrides  = load_overrides()
    rayo_squad = load_club_profile_players()
    em_df      = load_entity_map() if use_entity_map else pd.DataFrame()

    print(f"  market_values.csv : {len(mv_data):,} jugadores")
    print(f"  player_overrides  : {len(overrides):,} entradas")
    print(f"  plantilla Rayo    : {len(rayo_squad)} jugadores")
    if not em_df.empty:
        print(f"  entity_map        : {len(em_df):,} entradas ({(em_df['match_confidence'].astype(float) >= 0.90).sum():,} alta confianza)")

    # ── Construir un dict inicial por nombre normalizado desde market_values ──
    rows_by_canon: dict[str, dict] = {}

    for key, mv in mv_data.items():
        rows_by_canon[key] = {
            "opta_id":           None,
            "canonical_name":    key,
            "display_name":      mv.get("display_name"),
            "market_value_eur":  mv.get("market_value_eur"),
            "contract_until":    mv.get("contract_until"),
            "release_clause_eur": None,
            "salary_eur_year":   None,
            "club":              None,
            "nationality":       None,
            "age":               mv.get("age"),
            "position_tm":       mv.get("position_tm"),
            "dob":               mv.get("dob"),
            "tm_id":             mv.get("tm_id"),
            "photo_url":         mv.get("photo_url"),
            "data_source":       mv.get("data_source", "transfermarkt"),
            "last_updated":      mv.get("last_updated", TODAY),
            "match_confidence":  "0.00",  # se actualizará desde entity_map
        }

    # ── Asignar opta_id y match_confidence desde entity_map ──────────────────
    if not em_df.empty:
        # Índice: canonical_name → opta_id + confidence
        em_by_canon = {}
        for _, r in em_df.iterrows():
            cn = norm(r.get("canonical_name", "") or r.get("opta_name", ""))
            em_by_canon[cn] = {
                "opta_id":          r.get("opta_id", ""),
                "tm_id":            r.get("tm_id", "") or None,
                "match_confidence": r.get("match_confidence", "0.00"),
            }
        for canon, row in rows_by_canon.items():
            if canon in em_by_canon:
                em = em_by_canon[canon]
                row["opta_id"]         = em["opta_id"] or None
                row["match_confidence"] = em["match_confidence"]
                if em["tm_id"] and not row.get("tm_id"):
                    row["tm_id"] = em["tm_id"]

    # ── Sobreescribir con datos del club_profile (fuente de verdad Rayo) ──────
    for p in rayo_squad:
        key = p["canonical_name"]
        base = rows_by_canon.get(key, {
            "opta_id":           None,
            "canonical_name":    key,
            "release_clause_eur": None,
            "salary_eur_year":   None,
            "dob":               None,
            "tm_id":             None,
            "photo_url":         None,
        })
        # club_profile tiene prioridad sobre TM para estos campos
        for field in ("display_name", "club", "nationality", "age",
                       "position_tm", "contract_until", "market_value_eur",
                       "data_source", "last_updated", "match_confidence"):
            if p.get(field) is not None:
                base[field] = p[field]
        rows_by_canon[key] = base

    # ── Aplicar overrides manuales (prioridad máxima) ─────────────────────────
    for canon_key, ov in overrides.items():
        if canon_key in rows_by_canon:
            row = rows_by_canon[canon_key]
        else:
            row = {"opta_id": None, "canonical_name": canon_key}
            rows_by_canon[canon_key] = row
        for field in ("market_value_eur", "contract_until", "release_clause_eur",
                       "salary_eur_year", "photo_url", "age", "position_tm"):
            v = ov.get(field)
            if v not in (None, "", "nan"):
                row[field] = v
        row["data_source"]    = "manual"
        row["last_updated"]   = TODAY
        row["match_confidence"] = "1.00"

    # ── Ensamblar DataFrame ───────────────────────────────────────────────────
    SCHEMA_COLS = [
        "opta_id", "canonical_name", "display_name",
        "market_value_eur", "contract_until", "release_clause_eur", "salary_eur_year",
        "club", "nationality", "age", "position_tm", "dob",
        "tm_id", "photo_url",
        "data_source", "last_updated", "match_confidence",
    ]

    records = []
    for _, row in rows_by_canon.items():
        rec = {col: row.get(col) for col in SCHEMA_COLS}
        records.append(rec)

    df = pd.DataFrame(records, columns=SCHEMA_COLS)

    # Tipado
    df["market_value_eur"]    = pd.to_numeric(df["market_value_eur"], errors="coerce")
    df["release_clause_eur"]  = pd.to_numeric(df["release_clause_eur"], errors="coerce")
    df["salary_eur_year"]     = pd.to_numeric(df["salary_eur_year"], errors="coerce")
    df["age"]                 = pd.to_numeric(df["age"], errors="coerce")
    df["match_confidence"]    = pd.to_numeric(df["match_confidence"], errors="coerce").fillna(0)

    # Estadísticas de cobertura
    n = len(df)
    n_mv  = df["market_value_eur"].notna().sum()
    n_con = df["contract_until"].notna().sum()
    n_id  = df["opta_id"].notna().sum()
    n_tm  = df["tm_id"].notna().sum()
    n_ph  = df["photo_url"].notna().sum()

    PROC.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PARQUET, compression="snappy", index=False)

    print(f"\n✅ player_economic.parquet generado: {n:,} jugadores × {df.shape[1]} columnas")
    print(f"   con opta_id         : {n_id:,}  ({100*n_id/max(1,n):.1f}%)")
    print(f"   con tm_id           : {n_tm:,}  ({100*n_tm/max(1,n):.1f}%)")
    print(f"   con market_value    : {n_mv:,}  ({100*n_mv/max(1,n):.1f}%)")
    print(f"   con contract_until  : {n_con:,}  ({100*n_con/max(1,n):.1f}%)")
    print(f"   con photo_url       : {n_ph:,}  ({100*n_ph/max(1,n):.1f}%)")

    # Contratos próximos a vencer (alerta)
    if "contract_until" in df.columns:
        try:
            df_cnt = df.dropna(subset=["contract_until"]).copy()
            df_cnt["_year"] = df_cnt["contract_until"].str[:4].astype(int, errors="ignore")
            expiring = df_cnt[df_cnt["_year"].astype(str).isin(["2026", "2027"])]
            if not expiring.empty:
                print(f"\n⚠️  Contratos que vencen en 2026-2027: {len(expiring)}")
                for _, r in expiring.head(10).iterrows():
                    print(f"   {r.get('display_name', r['canonical_name'])} — {r['contract_until']}")
        except Exception:
            pass

    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-entity-map", action="store_true",
                    help="No usar player_entity_map.csv (solo market_values.csv + club_profile)")
    args = ap.parse_args()
    build(use_entity_map=not args.no_entity_map)


if __name__ == "__main__":
    main()
