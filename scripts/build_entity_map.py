"""
build_entity_map.py
===================
Construye data/processed/player_entity_map.csv, la tabla pivote que relaciona
de forma fiable el ID OPTA de cada jugador con su ID de Transfermarkt (tm_id).

PROCESO EN 4 NIVELES (confianza decreciente):
  1. exact_name       — nombre OPTA normalizado == nombre TM normalizado (score 1.00)
  2. exact_surname    — apellido(s) coinciden + posición coincide             (score 0.90)
  3. fuzzy            — RapidFuzz ≥ FUZZY_THRESHOLD                           (score 0.70–0.84)
  4. manual           — entrada en config/entity_overrides.csv (score 1.00)

Sólo los niveles 1-2 se persisten como enlace activo.
El nivel 3 (fuzzy) se marca como "revisar" en el informe de calidad pero SÍ se incluye.
El nivel 4 (manual) tiene prioridad sobre cualquier nivel automático.

Uso:
    python scripts/build_entity_map.py                # actualización incremental
    python scripts/build_entity_map.py --rebuild      # reconstrucción completa
    python scripts/build_entity_map.py --report       # sólo genera informe de calidad
"""
from __future__ import annotations
import argparse
import sys
import unicodedata
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils.config import settings  # noqa: E402

# ── Rutas ─────────────────────────────────────────────────────────────────────
S = settings()
PROC = Path(S["paths"]["data_processed"])
ENTITY_MAP = PROC / "player_entity_map.csv"
ENTITY_OVERRIDES = ROOT / "config" / "entity_overrides.csv"  # overrides manuales
MV_CSV = ROOT / "config" / "market_values.csv"

# ── Parámetros de matching ────────────────────────────────────────────────────
FUZZY_THRESHOLD = 85      # RapidFuzz score mínimo para nivel 3
MIN_MINUTES     = 200     # Mínimo de minutos para considerar al jugador en el scope

# ── Mapa de posiciones OPTA → grupo TM ───────────────────────────────────────
POS_GROUP = {
    "GK": "GK",
    "CB": "DEF", "RB": "DEF", "LB": "DEF", "DEF": "DEF",
    "DM": "MID", "CM": "MID", "AM": "MID", "MID": "MID",
    "RW": "FWD", "LW": "FWD", "ST": "FWD", "FWD": "FWD",
    "?": "?",
}

TM_POS_GROUP = {
    "goalkeeper": "GK",
    "centre-back": "DEF", "left-back": "DEF", "right-back": "DEF",
    "central midfield": "MID", "defensive midfield": "MID",
    "attacking midfield": "MID", "left midfield": "MID", "right midfield": "MID",
    "left winger": "FWD", "right winger": "FWD", "centre-forward": "FWD",
    "second striker": "FWD",
}


# ── Utilidades ────────────────────────────────────────────────────────────────

def norm(s) -> str:
    """Normaliza nombre: sin tildes, minúsculas, sin puntos, sin espacios extra."""
    if pd.isna(s) or s is None:
        return ""
    t = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return t.lower().strip().replace(".", "").replace("  ", " ")


def surnames(name: str) -> list[str]:
    """Extrae apellidos del nombre normalizado (heurística: últimas 1-2 palabras)."""
    parts = norm(name).split()
    # Eliminar iniciales (una sola letra)
    parts = [p for p in parts if len(p) > 1]
    if not parts:
        return []
    # Si tiene ≥ 3 partes, los dos últimos son apellidos; si no, el último
    return parts[-2:] if len(parts) >= 3 else parts[-1:]


def surname_key(name: str) -> str:
    """Clave de apellido para comparación rápida."""
    s = surnames(name)
    return " ".join(s) if s else norm(name)


def pos_group(pos) -> str:
    if pd.isna(pos) or not pos:
        return "?"
    return POS_GROUP.get(str(pos).upper().strip(), "?")


def tm_pos_group(pos) -> str:
    if pd.isna(pos) or not pos:
        return "?"
    return TM_POS_GROUP.get(str(pos).lower().strip(), "?")


def pos_compatible(pg1: str, pg2: str) -> bool:
    """Dos grupos posicionales son compatibles si son iguales o alguno es desconocido."""
    if pg1 == "?" or pg2 == "?":
        return True
    return pg1 == pg2


# ── Carga de datos ────────────────────────────────────────────────────────────

def load_opta_players() -> pd.DataFrame:
    """Carga el universo de jugadores OPTA (player_id_src, name, position, team)."""
    enriched_path = PROC / "player_seasons_enriched.parquet"
    if not enriched_path.exists():
        print("[WARN] player_seasons_enriched.parquet no encontrado; usando master_players.parquet")
        enriched_path = PROC / "master_players.parquet"
    df = pd.read_parquet(enriched_path)

    # Normalizar columnas según el fichero disponible
    id_col = "player_id_src" if "player_id_src" in df.columns else "player_id"
    pos_col = "position_raw" if "position_raw" in df.columns else "position_primary"

    df = df.rename(columns={id_col: "opta_id", pos_col: "position_opta"})
    df["opta_id"] = df["opta_id"].astype(str).str.strip()
    df["name"]    = df["name"].astype(str).str.strip()

    # Coger la temporada más reciente de cada jugador
    season_order = {"2025-2026": 6, "2025": 5, "2024-2025": 4, "2023-2024": 3,
                    "2022-2023": 2, "2022": 1, "2021-2022": 1, "2026": 7}
    df["_so"] = df["season"].map(season_order).fillna(0)
    df = (df.sort_values("_so", ascending=False)
            .drop_duplicates(subset=["opta_id"], keep="first"))

    # Solo jugadores con minutos suficientes para reducir ruido
    if "minutes" in df.columns:
        df = df[pd.to_numeric(df["minutes"], errors="coerce").fillna(0) >= MIN_MINUTES]

    keep = ["opta_id", "name", "position_opta", "team", "league"]
    return df[[c for c in keep if c in df.columns]].reset_index(drop=True)


def load_tm_players() -> pd.DataFrame:
    """Carga el universo TM de market_values.csv."""
    if not MV_CSV.exists():
        print(f"[WARN] {MV_CSV} no encontrado")
        return pd.DataFrame(columns=["name", "tm_id", "position", "market_value_eur", "contract_until"])
    df = pd.read_csv(MV_CSV)
    df["tm_id"] = df["tm_id"].apply(
        lambda x: str(int(x)) if pd.notna(x) and str(x).replace(".0", "").isdigit() else None
    )
    return df


def load_overrides() -> pd.DataFrame:
    """Carga overrides manuales de config/entity_overrides.csv.

    Formato del CSV:
        opta_id,tm_id,canonical_name,notes
    """
    if not ENTITY_OVERRIDES.exists():
        return pd.DataFrame(columns=["opta_id", "tm_id", "canonical_name"])
    return pd.read_csv(ENTITY_OVERRIDES, dtype=str).fillna("")


def load_existing_map() -> pd.DataFrame:
    """Carga la tabla de entidad existente (para actualización incremental)."""
    if not ENTITY_MAP.exists():
        return pd.DataFrame()
    return pd.read_csv(ENTITY_MAP, dtype=str).fillna("")


# ── Motor de matching ─────────────────────────────────────────────────────────

def build_entity_map(rebuild: bool = False) -> pd.DataFrame:
    print("\n📋 Cargando datos...")
    opta   = load_opta_players()
    tm_df  = load_tm_players()
    manual = load_overrides()

    print(f"  OPTA: {len(opta):,} jugadores únicos (con ≥{MIN_MINUTES} min)")
    print(f"  TM  : {len(tm_df):,} entradas en market_values.csv")
    print(f"  Overrides manuales: {len(manual)}")

    existing = load_existing_map() if not rebuild else pd.DataFrame()

    # Índice TM por nombre normalizado
    tm_df["_norm_name"]   = tm_df["name"].apply(norm)
    tm_df["_tm_pos_grp"]  = tm_df["position"].apply(tm_pos_group)
    tm_by_norm = tm_df.groupby("_norm_name")

    # Índice TM por apellido(s)
    tm_df["_surname_key"] = tm_df["name"].apply(surname_key)
    tm_by_surname = tm_df.groupby("_surname_key")

    # Índice de overrides manuales: opta_id → {tm_id, canonical_name}
    ov_by_optaid = {}
    for _, r in manual.iterrows():
        ov_by_optaid[str(r["opta_id"]).strip()] = r.to_dict()

    # Índice de jugadores ya en el mapa existente (para incremental)
    existing_ids: set[str] = set()
    existing_rows: list[dict] = []
    if not existing.empty and "opta_id" in existing.columns:
        existing_ids = set(existing["opta_id"].tolist())
        existing_rows = existing.to_dict("records")

    rows: list[dict] = list(existing_rows)
    stats = {"exact": 0, "surname": 0, "fuzzy": 0, "manual": 0, "unmatched": 0}

    # Intentar importar rapidfuzz para nivel 3
    try:
        from rapidfuzz import fuzz
        use_fuzzy = True
    except ImportError:
        use_fuzzy = False
        print("  [INFO] rapidfuzz no instalado; matching fuzzy deshabilitado (pip install rapidfuzz)")

    print("\n🔍 Matching OPTA ↔ TM...")
    for _, row in opta.iterrows():
        opta_id  = str(row["opta_id"])
        opta_nm  = str(row["name"])
        opta_pos = pos_group(row.get("position_opta", "?"))

        # — Skip si ya está en el mapa (modo incremental) y NO hay override nuevo
        if not rebuild and opta_id in existing_ids and opta_id not in ov_by_optaid:
            continue

        result = None

        # ── NIVEL 4: override manual (prioridad máxima) ───────────────────────
        if opta_id in ov_by_optaid:
            ov = ov_by_optaid[opta_id]
            result = {
                "opta_id":          opta_id,
                "opta_name":        opta_nm,
                "tm_id":            ov.get("tm_id", ""),
                "tm_name":          "",
                "canonical_name":   ov.get("canonical_name", norm(opta_nm)),
                "match_type":       "manual",
                "match_confidence": "1.00",
                "last_verified":    str(date.today()),
            }
            stats["manual"] += 1

        # ── NIVEL 1: exact_name ───────────────────────────────────────────────
        if result is None:
            nn = norm(opta_nm)
            if nn in tm_by_norm.groups:
                candidates = tm_df.loc[tm_by_norm.groups[nn]]
                # Si hay varios candidatos con el mismo nombre normalizado,
                # preferir el que tenga posición compatible
                compatible = candidates[candidates["_tm_pos_grp"].apply(
                    lambda p: pos_compatible(opta_pos, p))]
                best = compatible.iloc[0] if not compatible.empty else candidates.iloc[0]
                result = {
                    "opta_id":          opta_id,
                    "opta_name":        opta_nm,
                    "tm_id":            best["tm_id"] or "",
                    "tm_name":          best["name"],
                    "canonical_name":   nn,
                    "match_type":       "exact_name",
                    "match_confidence": "1.00",
                    "last_verified":    str(date.today()),
                }
                stats["exact"] += 1

        # ── NIVEL 2: exact_surname ────────────────────────────────────────────
        if result is None:
            sk = surname_key(opta_nm)
            if sk and sk in tm_by_surname.groups:
                candidates = tm_df.loc[tm_by_surname.groups[sk]]
                compatible = candidates[candidates["_tm_pos_grp"].apply(
                    lambda p: pos_compatible(opta_pos, p))]
                if len(compatible) == 1:
                    best = compatible.iloc[0]
                    result = {
                        "opta_id":          opta_id,
                        "opta_name":        opta_nm,
                        "tm_id":            best["tm_id"] or "",
                        "tm_name":          best["name"],
                        "canonical_name":   norm(opta_nm),
                        "match_type":       "exact_surname",
                        "match_confidence": "0.90",
                        "last_verified":    str(date.today()),
                    }
                    stats["surname"] += 1
                elif len(compatible) > 1:
                    # Varios candidatos con mismo apellido y posición compatible
                    # → guardar como fuzzy con baja confianza para revisión
                    pass

        # ── NIVEL 3: fuzzy (solo auxiliar) ───────────────────────────────────
        if result is None and use_fuzzy:
            nn = norm(opta_nm)
            best_score = 0
            best_tm    = None
            for _, tm_row in tm_df.iterrows():
                score = fuzz.token_sort_ratio(nn, tm_row["_norm_name"])
                if score > best_score and pos_compatible(opta_pos, tm_row["_tm_pos_grp"]):
                    best_score = score
                    best_tm    = tm_row
            if best_score >= FUZZY_THRESHOLD and best_tm is not None:
                confidence = round(0.70 + (best_score - FUZZY_THRESHOLD) / (100 - FUZZY_THRESHOLD) * 0.14, 2)
                result = {
                    "opta_id":          opta_id,
                    "opta_name":        opta_nm,
                    "tm_id":            best_tm["tm_id"] or "",
                    "tm_name":          best_tm["name"],
                    "canonical_name":   norm(opta_nm),
                    "match_type":       "fuzzy",
                    "match_confidence": str(confidence),
                    "last_verified":    str(date.today()),
                }
                stats["fuzzy"] += 1

        # ── Sin match ─────────────────────────────────────────────────────────
        if result is None:
            result = {
                "opta_id":          opta_id,
                "opta_name":        opta_nm,
                "tm_id":            "",
                "tm_name":          "",
                "canonical_name":   norm(opta_nm),
                "match_type":       "unmatched",
                "match_confidence": "0.00",
                "last_verified":    str(date.today()),
            }
            stats["unmatched"] += 1

        # Eliminar entrada anterior si existe (en modo rebuild o override)
        rows = [r for r in rows if r.get("opta_id") != opta_id]
        rows.append(result)

    df_out = pd.DataFrame(rows, columns=[
        "opta_id", "opta_name", "tm_id", "tm_name", "canonical_name",
        "match_type", "match_confidence", "last_verified"
    ])

    # Ordenar para facilitar revisión manual
    df_out = df_out.sort_values(["match_confidence", "opta_name"], ascending=[True, True])

    PROC.mkdir(parents=True, exist_ok=True)
    df_out.to_csv(ENTITY_MAP, index=False, encoding="utf-8")

    total = len(df_out)
    print(f"\n✅ player_entity_map.csv generado: {total:,} entradas")
    print(f"   exact_name : {stats['exact']:5,}  ({100*stats['exact']/max(1,total):.1f}%)")
    print(f"   exact_surn : {stats['surname']:5,}  ({100*stats['surname']/max(1,total):.1f}%)")
    print(f"   fuzzy      : {stats['fuzzy']:5,}  ({100*stats['fuzzy']/max(1,total):.1f}%)")
    print(f"   manual     : {stats['manual']:5,}  ({100*stats['manual']/max(1,total):.1f}%)")
    print(f"   unmatched  : {stats['unmatched']:5,}  ({100*stats['unmatched']/max(1,total):.1f}%)")
    print(f"\n   Confianza alta (≥0.90) : {(df_out['match_confidence'].astype(float) >= 0.90).sum():,}")
    print(f"   Pendientes de revisión : {(df_out['match_confidence'].astype(float) < 0.85).sum():,}")

    return df_out


def generate_quality_report(entity_map: pd.DataFrame | None = None) -> None:
    """Genera un informe HTML de calidad del matching."""
    if entity_map is None:
        if not ENTITY_MAP.exists():
            print("[ERROR] player_entity_map.csv no encontrado. Ejecuta primero sin --report")
            return
        entity_map = pd.read_csv(ENTITY_MAP)

    entity_map["match_confidence"] = pd.to_numeric(entity_map["match_confidence"], errors="coerce").fillna(0)

    total   = len(entity_map)
    high    = (entity_map["match_confidence"] >= 0.90).sum()
    medium  = ((entity_map["match_confidence"] >= 0.70) & (entity_map["match_confidence"] < 0.90)).sum()
    low     = (entity_map["match_confidence"] < 0.70).sum()
    by_type = entity_map["match_type"].value_counts().to_dict()

    pending = entity_map[entity_map["match_confidence"] < 0.85].sort_values("match_confidence")

    rows_html = ""
    for _, r in pending.iterrows():
        conf = float(r["match_confidence"])
        color = "#FCA5A5" if conf < 0.70 else "#FDE68A"
        rows_html += (
            f"<tr style='background:{color}'>"
            f"<td>{r['opta_id']}</td>"
            f"<td>{r['opta_name']}</td>"
            f"<td>{r['tm_name'] or '—'}</td>"
            f"<td>{r['tm_id'] or '—'}</td>"
            f"<td>{r['match_type']}</td>"
            f"<td>{conf:.2f}</td>"
            f"</tr>\n"
        )

    html = f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8">
<title>Informe de Calidad del Matching — Rayo Scouting Tool</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 40px; color: #1A1A2E; }}
  h1 {{ color: #E30613; }} h2 {{ color: #1A1A2E; border-bottom: 2px solid #E30613; padding-bottom: 6px; }}
  .stat-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin: 20px 0; }}
  .stat-card {{ background: #F9FAFB; border: 1px solid #E5E7EB; border-radius: 10px; padding: 16px; text-align: center; }}
  .stat-num {{ font-size: 2em; font-weight: bold; color: #E30613; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  th {{ background: #1A1A2E; color: white; padding: 8px 12px; text-align: left; }}
  td {{ padding: 7px 12px; border-bottom: 1px solid #E5E7EB; }}
  .pct {{ font-size: 0.85em; color: #6B7280; }}
</style>
</head>
<body>
<h1>Informe de Calidad del Matching</h1>
<p>Fecha de generación: {date.today()} — Rayo Vallecano Herramienta de Dirección Deportiva</p>

<h2>Resumen</h2>
<div class="stat-grid">
  <div class="stat-card"><div class="stat-num">{total:,}</div><div>Total jugadores</div></div>
  <div class="stat-card"><div class="stat-num" style="color:#059669">{high:,}</div><div>Confianza alta ≥0.90</div><div class="pct">{100*high/max(1,total):.1f}%</div></div>
  <div class="stat-card"><div class="stat-num" style="color:#D97706">{medium:,}</div><div>Confianza media 0.70–0.89</div><div class="pct">{100*medium/max(1,total):.1f}%</div></div>
  <div class="stat-card"><div class="stat-num" style="color:#E30613">{low:,}</div><div>Sin match / baja confianza</div><div class="pct">{100*low/max(1,total):.1f}%</div></div>
</div>

<h2>Distribución por tipo de matching</h2>
<table><tr><th>Tipo</th><th>N</th><th>%</th></tr>
{"".join(f"<tr><td>{k}</td><td>{v}</td><td>{100*v/max(1,total):.1f}%</td></tr>" for k, v in sorted(by_type.items(), key=lambda x: -x[1]))}
</table>

<h2>Jugadores pendientes de revisión manual (confianza &lt; 0.85)</h2>
<p>Para corregir un enlace, añade una línea a <code>config/entity_overrides.csv</code>:</p>
<pre>opta_id,tm_id,canonical_name,notes</pre>
<table>
<tr><th>opta_id</th><th>Nombre OPTA</th><th>Nombre TM propuesto</th><th>tm_id propuesto</th><th>Tipo</th><th>Confianza</th></tr>
{rows_html}
</table>
</body></html>"""

    out = ROOT / "data" / "reports_out" / "matching_quality_report.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"\n📊 Informe de calidad: {out}")


def main():
    ap = argparse.ArgumentParser(description="Construye player_entity_map.csv")
    ap.add_argument("--rebuild", action="store_true", help="Reconstruye desde cero")
    ap.add_argument("--report",  action="store_true", help="Solo genera informe de calidad")
    args = ap.parse_args()

    if args.report:
        generate_quality_report()
    else:
        em = build_entity_map(rebuild=args.rebuild)
        generate_quality_report(em)


if __name__ == "__main__":
    main()
