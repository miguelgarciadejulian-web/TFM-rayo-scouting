"""
Script to add loan-returning players to the squad data.
Players: Raúl de Tomás, Miguel Morro, Pelayo Fernández
"""
import pandas as pd
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.utils.config import settings

s = settings()
proc = Path(s["paths"]["data_processed"])

# ============================================================
# 1. Add to market_values.csv
# ============================================================
mv = pd.read_csv("config/market_values.csv")
new_rows = [
    {
        "name": "Raúl de Tomás",
        "market_value_eur": 400000,
        "contract_until": "2027-06-30",
        "tm_photo_url": "https://img.a.transfermarkt.technology/portrait/big/162038-1761864724.jpg",
        "tm_id": 162038,
        "age": 31,
        "foot": "right",
        "height": 1.80,
        "position": "Centre-Forward",
        "dob": "1994-10-17",
    },
    {
        "name": "Miguel Morro",
        "market_value_eur": 300000,
        "contract_until": "2026-06-30",
        "tm_photo_url": "https://img.a.transfermarkt.technology/portrait/big/607780-1698946569.jpg",
        "tm_id": 607780,
        "age": 25,
        "foot": "left",
        "height": 1.95,
        "position": "Goalkeeper",
        "dob": "2000-09-11",
    },
    {
        "name": "Pelayo Fernández",
        "market_value_eur": 500000,
        "contract_until": "2028-06-30",
        "tm_photo_url": "https://img.a.transfermarkt.technology/portrait/big/692208-1.jpg",
        "tm_id": 692208,
        "age": 23,
        "foot": "right",
        "height": 1.93,
        "position": "Centre-Back",
        "dob": "2003-04-29",
    },
]
for row in new_rows:
    exists = mv[mv["name"] == row["name"]]
    if exists.empty:
        mv = pd.concat([mv, pd.DataFrame([row])], ignore_index=True)
        print(f"  [market_values] Added: {row['name']}")
    else:
        print(f"  [market_values] Already exists: {row['name']}")
mv.to_csv("config/market_values.csv", index=False)

# ============================================================
# 2. Add to player_economic.parquet
# ============================================================
eco_path = proc / "player_economic.parquet"
eco = pd.read_parquet(eco_path)

eco_new = [
    {
        "canonical_name": "raul de tomas",
        "display_name": "Raúl de Tomás",
        "market_value_eur": 400000,
        "contract_until": "2027-06-30",
        "tm_id": 162038.0,
        "age": 31,
        "foot": "right",
        "height": "1,80 m",
        "position_tm": "Centre-Forward",
        "nationality": "Spain",
        "dob": "1994-10-17",
        "photo_url": "https://img.a.transfermarkt.technology/portrait/big/162038-1761864724.jpg",
        "club": "Rayo Vallecano",
        "data_source": "transfermarkt_manual",
        "last_updated": "2026-06-26",
        "match_method": "tm_id",
        "match_confidence": 1.0,
    },
    {
        "canonical_name": "miguel morro",
        "display_name": "Miguel Morro",
        "market_value_eur": 300000,
        "contract_until": "2026-06-30",
        "tm_id": 607780.0,
        "age": 25,
        "foot": "left",
        "height": "1,95 m",
        "position_tm": "Goalkeeper",
        "nationality": "Spain",
        "dob": "2000-09-11",
        "photo_url": "https://img.a.transfermarkt.technology/portrait/big/607780-1698946569.jpg",
        "club": "Rayo Vallecano",
        "data_source": "transfermarkt_manual",
        "last_updated": "2026-06-26",
        "match_method": "tm_id",
        "match_confidence": 1.0,
    },
    {
        "canonical_name": "pelayo fernandez",
        "display_name": "Pelayo Fernández",
        "market_value_eur": 500000,
        "contract_until": "2028-06-30",
        "tm_id": 692208.0,
        "age": 23,
        "foot": "right",
        "height": "1,93 m",
        "position_tm": "Centre-Back",
        "nationality": "Spain",
        "dob": "2003-04-29",
        "photo_url": "https://img.a.transfermarkt.technology/portrait/big/692208-1.jpg",
        "club": "Rayo Vallecano",
        "data_source": "transfermarkt_manual",
        "last_updated": "2026-06-26",
        "match_method": "tm_id",
        "match_confidence": 1.0,
    },
]
for row in eco_new:
    exists = eco[eco["canonical_name"] == row["canonical_name"]]
    if exists.empty:
        eco = pd.concat([eco, pd.DataFrame([row])], ignore_index=True)
        print(f"  [player_economic] Added: {row['display_name']}")
    else:
        print(f"  [player_economic] Already exists: {row['display_name']}")

# Fix mixed types before saving
for col in eco.columns:
    if eco[col].dtype == object:
        # Ensure no mixed float/str in object columns
        eco[col] = eco[col].where(eco[col].notna(), None)
# Ensure tm_id is float
eco["tm_id"] = pd.to_numeric(eco["tm_id"], errors="coerce")
eco.to_parquet(eco_path, index=False)

# ============================================================
# 3. Add to squad_profile.json
# ============================================================
squad_path = proc / "squad_profile.json"
data = json.load(open(squad_path, encoding="utf-8"))
squad = data["squad"]
squad_names = {p["name"] for p in squad}

# --- Profile: Raúl de Tomás ---
if "Raúl de Tomás" not in squad_names:
    squad.append({
        "name": "Raúl de Tomás",
        "age": 31,
        "position_cfg": "ST",
        "contract_end": "2027-06-30",
        "market_value": 400000,
        "matched": True,
        "primary_role": "delantero_rematador",
        "primary_role_label": "Delantero rematador",
        "secondary_roles": ["delantero_movil"],
        "style_label": "Delantero de área con volumen de tiro y regate",
        "strengths": [
            "regate (top 30%)",
            "volumen de tiro (top 39%)",
            "presencia en área rival (top 46%)",
        ],
        "weaknesses": [
            "definición (percentil 3)",
            "pase vertical (percentil 3)",
            "pases clave (percentil 6)",
            "recuperaciones (percentil 28)",
        ],
        "risk_level": "alto",
        "potential": "en declive",
        "confidence": "media",
        "minutes": 1277.0,
        "loan_to": "Al-Wakrah SC",
    })
    print("  [squad_profile] Added: Raúl de Tomás")

# --- Profile: Miguel Morro ---
if "Miguel Morro" not in squad_names:
    squad.append({
        "name": "Miguel Morro",
        "age": 25,
        "position_cfg": "GK",
        "contract_end": "2026-06-30",
        "market_value": 300000,
        "matched": True,
        "primary_role": "portero",
        "primary_role_label": "Portero",
        "secondary_roles": [],
        "style_label": "Portero con buen juego de pies",
        "strengths": [
            "pase hacia delante (top 15%)",
        ],
        "weaknesses": [],
        "risk_level": "bajo",
        "potential": "alto",
        "confidence": "baja",
        "minutes": 1170.0,
        "loan_to": "Leixões SC",
    })
    print("  [squad_profile] Added: Miguel Morro")

# --- Profile: Pelayo Fernández ---
if "Pelayo Fernández" not in squad_names:
    squad.append({
        "name": "Pelayo Fernández",
        "age": 23,
        "position_cfg": "CB",
        "contract_end": "2028-06-30",
        "market_value": 500000,
        "matched": True,
        "primary_role": "central_posicional",
        "primary_role_label": "Central posicional",
        "secondary_roles": ["central_corrector"],
        "style_label": "Central de lectura defensiva y juego aéreo",
        "strengths": [
            "intercepciones (top 7%)",
            "juego aéreo (top 24%)",
            "juego en campo rival (top 38%)",
        ],
        "weaknesses": [
            "recuperaciones (percentil 3)",
            "pase hacia delante (percentil 25)",
        ],
        "risk_level": "bajo",
        "potential": "muy alto",
        "confidence": "baja",
        "minutes": 630.0,
        "loan_to": "Cádiz CF",
    })
    print("  [squad_profile] Added: Pelayo Fernández")

data["squad"] = squad
with open(squad_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("\nDone! All 3 loan-returning players added.")
