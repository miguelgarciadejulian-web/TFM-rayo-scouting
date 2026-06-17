"""Tests del motor de perfilado y encaje (jugadores y entrenadores)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.profiling.player_profile import (
    add_role_percentiles, profile_player_row, ROLE_DEFINITIONS, ROLE_LABELS,
)
from src.profiling.coach_style import build_reference, coach_axes, describe_style
from src.fit.player_fit import evaluate_player_fit
from src.fit.coach_fit import evaluate_coach
from src.fit.decisions import squad_decisions

PROC = ROOT / "data" / "processed"


# ── Fixtures de datos sinteticos ─────────────────────────────────────────────
def _synthetic_players(n=60):
    rng = np.random.default_rng(7)
    rows = []
    for i in range(n):
        grp = ["FWD", "MID", "DEF", "GK"][i % 4]
        rows.append({
            "name": f"P{i}", "team": f"T{i%6}", "league": "L1", "season": "2024-2025",
            "position_group": grp, "minutes": 2000,
            "goals_p90": rng.random(), "total_shots_p90": rng.random()*3,
            "shots_on_target_inc_goals_p90": rng.random()*1.5,
            "total_touches_in_opposition_box_p90": rng.random()*6,
            "key_passes_attempt_assists_p90": rng.random()*2,
            "goal_assists_p90": rng.random()*0.4, "successful_dribbles_p90": rng.random()*3,
            "successful_crosses_open_play_p90": rng.random()*2,
            "successful_passes_opposition_half_p90": rng.random()*30,
            "forward_passes_p90": rng.random()*40,
            "total_successful_passes_excl_crosses_corners_p90": rng.random()*60,
            "through_balls_p90": rng.random()*0.5, "tackles_won_p90": rng.random()*3,
            "total_tackles_p90": rng.random()*4, "interceptions_p90": rng.random()*3,
            "recoveries_p90": rng.random()*9, "blocks_p90": rng.random(),
            "total_clearances_p90": rng.random()*6, "aerial_duels_won_p90": rng.random()*4,
            "ground_duels_won_p90": rng.random()*6, "total_losses_of_possession_p90": rng.random()*15,
        })
    return pd.DataFrame(rows)


def test_role_definitions_have_valid_groups():
    for role, d in ROLE_DEFINITIONS.items():
        assert d["group"] in {"GK", "DEF", "MID", "FWD"}
        assert role in ROLE_LABELS
        assert abs(sum(d["weights"].values())) > 0


def test_percentiles_and_profile_assigns_role():
    df = _synthetic_players()
    enr = add_role_percentiles(df)
    pct_cols = [c for c in enr.columns if c.endswith("__pct")]
    assert pct_cols, "no se generaron percentiles"
    row = enr[enr.position_group == "FWD"].iloc[0]
    prof = profile_player_row(row)
    assert prof["primary_role"] in ROLE_DEFINITIONS
    assert ROLE_DEFINITIONS[prof["primary_role"]]["group"] == "FWD"
    assert 0 <= prof["primary_score"] <= 100


def test_low_minutes_marks_insufficient():
    df = _synthetic_players(8)
    df["minutes"] = 100  # por debajo del minimo
    enr = add_role_percentiles(df)
    prof = profile_player_row(enr.iloc[0])
    assert prof["confidence"] == "insuficiente"


def test_player_fit_prioritises_missing_roles():
    prof = {"primary_role": "central_dominador", "primary_score": 70, "potential": "alto",
            "secondary_roles_labels": []}
    needs = {"missing": ["Central dominador"], "reinforce": [], "over_represented": []}
    fit_missing = evaluate_player_fit(prof, needs, "Posicional / Dominio de balon")
    prof2 = dict(prof, primary_role="interior_llegador")
    needs2 = {"missing": [], "reinforce": [], "over_represented": ["Interior llegador"]}
    fit_over = evaluate_player_fit(prof2, needs2, "Posicional / Dominio de balon")
    assert fit_missing["compatibilidad_plantilla"] > fit_over["compatibilidad_plantilla"]


def test_describe_style_outputs_text():
    axes = {"tendencia_ofensiva": 70, "solidez_defensiva": 65, "presion_alta": 72,
            "posesion": 60, "verticalidad": 55, "intensidad_defensiva": 68,
            "uso_transiciones": 70, "posesion_pct_real": 53}
    desc = describe_style(axes)
    assert desc["style_main"]
    assert len(desc["description_auto"]) > 20
    assert isinstance(desc["style_tags"], list)


def test_decisions_recommend_signing_missing():
    squad = [
        {"name": "Viejo", "age": 34, "contract_end": "2026-06-30", "primary_role": "lateral_defensivo",
         "primary_role_label": "Lateral defensivo", "confidence": "alta", "minutes": 2000, "market_value": 1e6},
        {"name": "Joven", "age": 19, "contract_end": "2028-06-30", "primary_role": "extremo_vertical",
         "primary_role_label": "Extremo vertical", "confidence": "baja", "minutes": 400, "market_value": 5e5},
    ]
    needs = {"missing": ["Central dominador"], "reinforce": ["Portero"], "over_represented": []}
    dec = squad_decisions(squad, needs)
    assert any(f["role"] == "Central dominador" for f in dec["fichar"])
    assert any(c["name"] == "Joven" for c in dec["ceder"])
    assert any(v["name"] == "Viejo" for v in dec["vender"])


# ── Tests de integracion con datos reales (si existen los parquet) ──────────
@pytest.mark.skipif(not (PROC / "team_seasons.parquet").exists(), reason="sin team_seasons.parquet")
def test_coach_axes_real_data():
    ts = pd.read_parquet(PROC / "team_seasons.parquet")
    ref = build_reference(ts)
    axes = coach_axes(ref, [("CA Osasuna", "2022-2023")])
    assert axes["_coverage"]["n_rows"] >= 1
    assert 0 <= axes.get("posesion_pct_real", 50) <= 100


@pytest.mark.skipif(not (PROC / "player_seasons_enriched.parquet").exists(), reason="sin enriquecido")
def test_rayo_squad_profiles_real():
    enr = pd.read_parquet(PROC / "player_seasons_enriched.parquet")
    pool = enr[(enr.league == "Spain_Primera_Division") & (enr.season == "2024-2025")]
    enr_p = add_role_percentiles(pool)
    val = enr_p[enr_p.name.str.contains("Valent", na=False)]
    assert not val.empty
    prof = profile_player_row(val.iloc[0])
    # Valentin es un mediocentro de corte/recuperacion
    assert prof["primary_role"] == "mediocentro_recuperador"


@pytest.mark.skipif(not (PROC / "player_seasons_enriched.parquet").exists(), reason="sin enriquecido")
def test_signing_shortlist_returns_ballplaying_cbs():
    from src.profiling.player_profile import rank_players_for_role
    enr = pd.read_parquet(PROC / "player_seasons_enriched.parquet")
    rk = rank_players_for_role(enr, "central_dominador", top_n=5,
                               leagues=["Spain_Primera_Division", "Portugal_Primeira_Liga"])
    assert not rk.empty
    assert (rk["role_score"] >= 70).all()  # candidatos de alto nivel en el rol
    assert "role_label" in rk.columns
