"""
JSON file store. Reads the tournament definition and writes computed snapshots
(current standings, scenarios, bracket projection) to the OUT_DIR so the
frontend can consume them as static files.
"""
from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config
from .models import Game, Pool, Team, Tournament


def load_tournament(path: str | Path | None = None) -> Tournament:
    p = Path(path or config.TOURNAMENT_FILE)
    raw = json.loads(p.read_text(encoding="utf-8"))
    teams = [Team(**t) for t in raw["teams"]]
    pools = [Pool(**pl) for pl in raw["pools"]]
    return Tournament(
        id=raw["id"],
        name=raw["name"],
        division=raw["division"],
        bracket_id=raw["bracket_id"],
        teams=teams,
        pools=pools,
        games=[],   # filled by scraper
        target_team_id=raw.get("target_team_id"),
    )


def write_snapshot(filename: str, payload: Any) -> Path:
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    p = config.OUT_DIR / filename
    p.write_text(json.dumps(_serialize(payload), indent=2, default=_default), encoding="utf-8")
    return p


def _serialize(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return _serialize(asdict(obj))
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize(x) for x in obj]
    return obj


def _default(o):
    if isinstance(o, datetime):
        return o.isoformat()
    raise TypeError(f"not JSON serializable: {type(o).__name__}")


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
