"""
build_profiles.py
=================
Precalcula los perfiles automaticos (entrenadores y plantilla) y los guarda como
JSON para que el dashboard los lea sin recomputar en cada peticion.

Genera:
  data/processed/coach_profiles.json   -> estilo + evaluacion de cada candidato
  data/processed/squad_profile.json     -> roles de la plantilla + necesidades

Uso:  python scripts/build_profiles.py
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils.config import settings, club_profile  # noqa: E402
from src.profiling.coach_style import build_reference, profile_coach  # noqa: E402
from src.squad.needs import profile_squad, squad_needs  # noqa: E402
from src.profiling.player_profile import rank_players_for_role, ROLE_LABELS  # noqa: E402
from src.fit.coach_fit import evaluate_coach  # noqa: E402

SPAIN_TOP = "Spain_Primera_Division"


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, float):
        return None if pd.isna(o) else o
    return o


def laliga_seasons_for(team_seasons: pd.DataFrame, history_entry: dict) -> int:
    seasons = set()
    for st in history_entry.get("stints", []):
        tm = st.get("team_match")
        for s in st.get("seasons", []):
            hit = team_seasons[
                (team_seasons["league"] == SPAIN_TOP)
                & (team_seasons["team"].str.contains(tm, case=False, na=False))
                & (team_seasons["season"].astype(str) == str(s))
            ]
            if not hit.empty:
                seasons.add(str(s))
    return len(seasons)


def main():
    S = settings()
    proc = Path(S["paths"]["data_processed"])
    ts = pd.read_parquet(proc / "team_seasons.parquet")
    enr = pd.read_parquet(proc / "player_seasons_enriched.parquet")
    cp = club_profile()
    dna = yaml.safe_load(open(ROOT / "config" / "rayo_dna.yaml"))
    coaches_cfg = yaml.safe_load(open(ROOT / "config" / "coaches.yaml"))
    ctx_by_name = {c["name"]: c for c in coaches_cfg.get("coaches", [])}

    # Stints por entrenador desde el CSV de tenencias (editable por el usuario)
    tenures = pd.read_csv(ROOT / "config" / "coach_tenures.csv")
    try:
        meta_df = pd.read_csv(ROOT / "config" / "coach_meta.csv")
        meta_by_name = {r["coach"]: r for _, r in meta_df.iterrows()}
    except Exception:
        meta_by_name = {}
    history_coaches = []
    for coach, grp in tenures.groupby("coach"):
        stints = []
        for team, g2 in grp.groupby("team"):
            stints.append({"team_match": team, "seasons": sorted(g2["season"].astype(str).tolist())})
        history_coaches.append({"name": coach, "stints": stints})
    # añadir entrenadores del shortlist manual que no esten en el CSV (con su historial yaml si existe)
    try:
        legacy = yaml.safe_load(open(ROOT / "config" / "coach_history.yaml")).get("coaches", [])
    except Exception:
        legacy = []
    have = {c["name"] for c in history_coaches}
    for c in legacy:
        if c["name"] not in have:
            history_coaches.append(c)
    history = {"coaches": history_coaches}

    print("Perfilando plantilla del Rayo ...", flush=True)
    sq = profile_squad(cp, enr)
    needs = squad_needs(sq)
    squad_records = _clean(sq.to_dict("records"))
    json.dump({"squad": squad_records, "needs": _clean(needs)},
              open(proc / "squad_profile.json", "w"), ensure_ascii=False, indent=1)
    print(f"  {len(squad_records)} jugadores | faltan: {needs['missing']} | sobran: {needs['over_represented']}")

    print("Generando shortlists de fichaje por rol ...", flush=True)
    label_to_role = {v: k for k, v in ROLE_LABELS.items()}
    target_leagues = ["Spain_Primera_Division", "Spain_Segunda_Division",
                      "France_Ligue_1", "Portugal_Primeira_Liga",
                      "Netherlands_Eredivisie", "Belgium_First_Division_A",
                      "Argentina_Liga_Profesional", "Mexico_Liga_MX"]
    shortlists = {}
    for role_label in (needs.get("missing", []) + needs.get("reinforce", [])):
        role = label_to_role.get(role_label)
        if not role:
            continue
        rk = rank_players_for_role(enr, role, top_n=8, leagues=target_leagues)
        shortlists[role_label] = _clean(rk.to_dict("records")) if not rk.empty else []
    json.dump(shortlists, open(proc / "signing_shortlists.json", "w"),
              ensure_ascii=False, indent=1)
    print(f"  shortlists para: {list(shortlists.keys())}")

    print("Perfilando entrenadores ...", flush=True)
    ref = build_reference(ts)
    out = []
    for c in history.get("coaches", []):
        name = c["name"]
        prof = profile_coach(ref, c)
        ll = laliga_seasons_for(ts, c)
        ctx = dict(ctx_by_name.get(name, {}))
        ctx["laliga_seasons"] = ll
        meta = meta_by_name.get(name)
        if meta is not None:
            if not ctx.get("age") and pd.notna(meta.get("age")):
                ctx["age"] = int(meta["age"])
            if not ctx.get("nationality") and pd.notna(meta.get("nationality")):
                ctx["nationality"] = str(meta["nationality"])
        ev = evaluate_coach(name, prof, ctx, dna, squad_summary=needs)
        rec = {
            "name": name,
            "age": ctx.get("age"),
            "nationality": ctx.get("nationality"),
            "current_club": ctx.get("current_club"),
            "last_club": ctx.get("last_club"),
            "available": ctx.get("available"),
            "contract_status": ctx.get("contract_status"),
            "salary_estimate_eur": ctx.get("salary_estimate_eur"),
            "release_clause_eur": ctx.get("release_clause_eur"),
            "formation_preferred": ctx.get("formation_preferred"),
            "laliga_seasons": ll,
            "style_main": prof.get("style_main"),
            "style_tags": prof.get("style_tags"),
            "description_auto": prof.get("description_auto"),
            "axes": prof.get("axes", {}),
            "coverage": prof.get("coverage", {}),
            "data_partial": prof.get("data_partial", False),
            "evaluation": ev,
        }
        out.append(rec)

    out.sort(key=lambda r: (r["evaluation"].get("global_score") or 0), reverse=True)
    json.dump(_clean(out), open(proc / "coach_profiles.json", "w"),
              ensure_ascii=False, indent=1)
    print(f"  {len(out)} entrenadores. Top-5 por encaje:")
    for r in out[:5]:
        ev = r["evaluation"]
        print(f"   {ev.get('score_10')}/10  {r['name']:24s} | {r['style_main']}")


if __name__ == "__main__":
    main()
