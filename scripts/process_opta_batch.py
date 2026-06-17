"""Procesa en batch los JSON OPTA en data/opta_json y los consolida a parquet."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
from tqdm import tqdm
from src.utils.config import settings
from src.utils.logging import get_logger
from src.opta.parser import parse_file

log = get_logger("opta_batch")


def main():
    s = settings()
    json_dir = Path(s["paths"]["opta_json"])
    out_dir = Path(s["paths"]["data_processed"])
    out_dir.mkdir(parents=True, exist_ok=True)

    files = list(json_dir.glob("*.json"))
    log.info("Encontrados %d JSON OPTA", len(files))

    frames = []
    for f in tqdm(files, desc="Parsing OPTA"):
        try:
            df = parse_file(f)
            if not df.empty:
                df["source_file"] = f.name
                frames.append(df)
        except Exception as e:
            log.warning("Fallo %s: %s", f.name, e)

    if not frames:
        log.error("No se generaron eventos.")
        return
    events = pd.concat(frames, ignore_index=True)
    out = out_dir / "opta_events.parquet"
    events.to_parquet(out, compression="snappy", index=False)
    log.info("Guardado %s (%d eventos)", out, len(events))


if __name__ == "__main__":
    main()
