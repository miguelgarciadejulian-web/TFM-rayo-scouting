# -*- coding: utf-8 -*-
"""Parser de archivos OPTA JSON → DataFrame de eventos.

Basado en `first class/A_opta event mapping_eng.ipynb`, modernizado.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any
import pandas as pd


_JSONP_RE = re.compile(r"^[^({]*\(\s*(\{.*\})\s*\)\s*;?\s*$", re.DOTALL)


def load_opta_json(path: str | Path) -> dict:
    """Lee JSON OPTA, soportando wrappers JSONP (api.performfeeds.com)."""
    text = Path(path).read_text(encoding="utf-8")
    text = text.strip()
    if not text.startswith("{"):
        m = _JSONP_RE.match(text)
        if m:
            text = m.group(1)
    return json.loads(text)


def _flatten_qualifiers(qs: list[dict] | None) -> dict:
    if not qs:
        return {}
    out = {}
    for q in qs:
        qid = q.get("qualifierId")
        val = q.get("value", True)
        out[f"q{qid}"] = val
    return out


def events_to_dataframe(opta_dict: dict) -> pd.DataFrame:
    """Convierte el JSON OPTA al DataFrame de eventos tabular."""
    live = opta_dict.get("liveData") or opta_dict.get("matchEvents") or {}
    events = live.get("event") if isinstance(live, dict) else opta_dict.get("event", [])
    if not events:
        return pd.DataFrame()

    rows = []
    for e in events:
        row = {
            "event_id": e.get("id"),
            "period_id": e.get("periodId"),
            "minute": e.get("timeMin"),
            "second": e.get("timeSec"),
            "team_id": e.get("contestantId"),
            "player_id": e.get("playerId"),
            "player_name": e.get("playerName"),
            "type_id": e.get("typeId"),
            "type_name": e.get("typeName"),
            "outcome": e.get("outcome"),
            "x": e.get("x"),
            "y": e.get("y"),
        }
        row.update(_flatten_qualifiers(e.get("qualifier")))
        rows.append(row)

    return pd.DataFrame(rows)


def parse_file(path: str | Path) -> pd.DataFrame:
    return events_to_dataframe(load_opta_json(path))
